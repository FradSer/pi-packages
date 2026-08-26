/**
 * Guardrails — the harness surface of continual learning: declarative
 * tool-call policies that evolve through layered JSON config. Matching calls
 * are blocked with corrective guidance (the "more correct prompt") or gated
 * behind user confirmation.
 *
 * Policies live in ~/.pi/agent/harness.json (+ .local) and
 * <project>/.pi/harness.json (+ .local). Curated defaults ship with the
 * package and can be disabled by name from any layer.
 */

import fs from "node:fs";
import { parseSkillBlock, type ExtensionAPI, type BeforeAgentStartEvent } from "@earendil-works/pi-coding-agent";
import { DEFAULT_POLICIES, evaluate, mergeLayers } from "./guardrail-engine.ts";
import { configPaths, loadLayers } from "./guardrail-config.ts";
import type { PolicyLayer, ResolvedConfig } from "./guardrail-types.ts";

interface ResolvedWithPaths {
  config: ResolvedConfig;
  paths: ReturnType<typeof configPaths>;
}

function defaultLayer(): PolicyLayer {
  return {
    source: "built-in defaults",
    policies: DEFAULT_POLICIES as unknown as Array<Record<string, unknown>>,
  };
}

function appendSystemGuidance(systemPrompt: string, guidance: string): string {
  if (systemPrompt.includes(guidance)) return systemPrompt;
  return systemPrompt ? `${systemPrompt}\n\n${guidance}` : guidance;
}

export function skillPromptTarget(
  event: Pick<BeforeAgentStartEvent, "prompt">,
  config: ResolvedConfig,
): { name: string; prompt: string; target: "system" | "user" } | undefined {
  const skill = parseSkillBlock(event.prompt);
  if (!skill) return undefined;
  const guidance = config.skillPrompts[skill.name];
  if (!guidance) return undefined;
  return { name: skill.name, ...guidance };
}

/** The confirm gate blocks the agent loop while its dialog waits, so an
 * unattended session must fail closed after a bounded wait instead of
 * hanging. pi renders the remaining time as a live countdown. */
const GUARDRAILS_CONFIRM_TIMEOUT_MS = 60_000;

let cached: { key: string; value: ResolvedWithPaths } | undefined;

// Pi shares one context among before_agent_start handlers in a turn, while
// creating a fresh event for each one. Module scope also covers an accidental
// duplicate extension registration; each later turn receives a new context.
const injectedUserPromptContexts = new WeakSet<object>();

function resolveConfig(cwd: string, agentDir?: string): ResolvedWithPaths {
  const paths = configPaths(cwd, agentDir);
  // Cache key covers every file's mtime: a max-only key goes stale when a
  // newer project file masks later edits to an older user file.
  let cacheKey = "";
  for (const file of Object.values(paths)) {
    try {
      cacheKey += `${file}:${fs.statSync(file).mtimeMs};`;
    } catch {
      cacheKey += `${file}:-;`;
    }
  }
  if (cached && cached.key === cacheKey) return cached.value;
  const config = mergeLayers([defaultLayer(), ...loadLayers(cwd, agentDir)]);
  cached = { key: cacheKey, value: { config, paths } };
  return cached.value;
}

export default function registerGuardrails(pi: ExtensionAPI) {
  pi.on("before_agent_start", (event, ctx) => {
    const cwd = ctx.cwd || process.cwd();
    const { config } = resolveConfig(cwd);
    const matched = skillPromptTarget(event, config);
    if (!matched) return undefined;

    if (matched.target === "system") {
      return { systemPrompt: appendSystemGuidance(event.systemPrompt, matched.prompt) };
    }
    if (injectedUserPromptContexts.has(ctx)) return undefined;
    injectedUserPromptContexts.add(ctx);
    return {
      message: {
        customType: "skill-prompt-guidance",
        content: matched.prompt,
        display: false,
        details: { skill: matched.name, target: "user" },
      },
    };
  });

  pi.on("tool_call", async (event, ctx) => {
    const cwd = ctx.cwd || process.cwd();
    const { config } = resolveConfig(cwd);
    const decision = evaluate(config, {
      toolName: event.toolName,
      args: (event.input ?? {}) as Record<string, unknown>,
    });
    if (!decision) return undefined;

    if (decision.action === "confirm") {
      if (!ctx.hasUI) {
        return { block: true, reason: `${decision.reason}\n(no UI available to confirm)` };
      }
      const choice = await ctx.ui.select(
        `guardrails: ${decision.policyName}\n\nAllow this call?`,
        ["Allow once", "Block"],
        { timeout: GUARDRAILS_CONFIRM_TIMEOUT_MS },
      );
      if (choice === "Allow once") return undefined;
      // select resolves undefined on timeout — the same fail-closed outcome
      // as an explicit Block, with a reason that says which happened.
      const timedOut = choice === undefined;
      return {
        block: true,
        reason: `${decision.reason}\n(${timedOut ? "blocked: confirmation timed out" : "blocked by user choice"})`,
      };
    }

    return { block: true, reason: decision.reason };
  });

  pi.registerCommand("guardrails", {
    description: "Show active tool-call guardrails: sources, policies, config paths",
    handler: async (_args, ctx) => {
      const cwd = ctx.cwd || process.cwd();
      const { config, paths } = resolveConfig(cwd);
      const lines = [
        `policies: ${config.policies.length ? config.policies.map((p) => p.name).join(", ") : "(none)"}`,
        `skill prompts: ${Object.keys(config.skillPrompts).length ? Object.keys(config.skillPrompts).join(", ") : "(none)"}`,
        "built-in defaults are active unless disabled by name",
        "config paths:",
        `  ${paths.user}`,
        `  ${paths.userLocal} (optional)`,
        `  ${paths.project}`,
        `  ${paths.projectLocal} (optional)`,
      ];
      if (config.errors.length) {
        lines.push(
          `errors (${config.errors.length}):`,
          ...config.errors.slice(0, 5).map((e) => `  - ${e}`),
        );
      }
      ctx.ui.notify(lines.join("\n"), "info");
    },
  });
}
