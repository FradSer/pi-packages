/**
 * Guardrails — the harness surface of continual learning: declarative
 * tool-call policies that evolve through layered JSON config. Matching calls
 * are blocked with corrective guidance (the "more correct prompt") or gated
 * behind user confirmation.
 *
 * Policies live in user-shared ~/.pi/agent/harness.json, project-shared
 * <project>/.pi/harness.json, and project-personal harness.local.json. Curated defaults ship with the
 * package and can be disabled by name from any layer.
 */

import fs from "node:fs";
import type { Stats } from "node:fs";
import path from "node:path";
import { isDeepStrictEqual } from "node:util";
import { ToolExecutionComponent, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { createStaticToolLifecycleMessageRenderer, eventToolLifecycle, notifyPi, safeDisplayText } from "@fradser/pi-kit";
import { evaluate, validatePolicyDeclaration, validateSkillPromptDeclaration } from "./guardrail-engine.ts";
import { configPaths, resolveHarnessConfig } from "./guardrail-config.ts";

interface HarnessPolicyEvent {
  kind: "policy-matched";
  policy: string;
  action: "block" | "confirm" | "observe";
  tool: string;
  reason: string;
  outcome: "observed" | "allowed once" | "blocked by rule" | "blocked by user choice" | "blocked: confirmation timed out" | "no UI available to confirm";
  source: string;
  file: string;
}

type HarnessEventData = HarnessPolicyEvent;

function harnessSourcePath(source: string | undefined, paths: ReturnType<typeof configPaths>): string {
  switch (source) {
    case "user":
      return paths.user;
    case "project":
      return paths.project;
    case "project.local":
      return paths.projectLocal;
    default:
      return "(built-in)";
  }
}

function withinRoot(root: string, candidate: string): boolean {
  const relative = path.relative(root, candidate);
  return relative === "" || (relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative));
}

async function deepestExistingDirectory(candidate: string): Promise<string> {
  let current = candidate;
  while (true) {
    try {
      const stat = await fs.promises.lstat(current);
      if (stat.isSymbolicLink()) throw new Error(`Harness target parent is a symlink: ${current}`);
      if (!stat.isDirectory()) throw new Error(`Harness target parent is not a directory: ${current}`);
      return current;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      const parent = path.dirname(current);
      if (parent === current) throw error;
      current = parent;
    }
  }
}

export async function assertHarnessTargetContained(targetFile: string, workspace?: string): Promise<void> {
  const target = path.resolve(targetFile);
  const root = path.resolve(workspace ?? path.dirname(target));
  if (!withinRoot(root, target)) throw new Error(`Harness target is outside the workspace: ${targetFile}`);

  const existingRoot = await deepestExistingDirectory(root);
  const existingRootReal = await fs.promises.realpath(existingRoot);
  const prospectiveRootReal = path.join(existingRootReal, path.relative(existingRoot, root));
  let current = existingRoot;
  const parent = path.dirname(target);
  const segments = path.relative(existingRoot, parent).split(path.sep).filter(Boolean);
  for (const segment of segments) {
    current = path.join(current, segment);
    let stat: Stats;
    try {
      stat = await fs.promises.lstat(current);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
      throw error;
    }
    if (stat.isSymbolicLink()) throw new Error(`Harness target parent is a symlink: ${current}`);
    if (!stat.isDirectory()) throw new Error(`Harness target parent is not a directory: ${current}`);
    if (withinRoot(root, current)) {
      const currentReal = await fs.promises.realpath(current);
      if (!withinRoot(prospectiveRootReal, currentReal)) throw new Error(`Harness target parent resolves outside the workspace: ${current}`);
    }
  }
}

async function readHarnessTarget(targetFile: string): Promise<Buffer | null> {
  let stat: Stats;
  try {
    stat = await fs.promises.lstat(targetFile);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
  if (stat.isSymbolicLink() || !stat.isFile()) {
    throw new Error(`Harness target is not a regular file: ${targetFile}`);
  }
  return fs.promises.readFile(targetFile);
}

export async function ensureHarnessTarget(targetFile: string, workspace?: string): Promise<{ path: string; created: boolean }> {
  await assertHarnessTargetContained(targetFile, workspace);
  const existing = await readHarnessTarget(targetFile);
  if (existing) return { path: targetFile, created: false };

  await fs.promises.mkdir(path.dirname(targetFile), { recursive: true });
  await assertHarnessTargetContained(targetFile, workspace);
  const initial = `${JSON.stringify({ policies: [], disabled: [], skillPrompts: {} }, null, 2)}\n`;
  let handle: fs.promises.FileHandle | undefined;
  let created = false;
  try {
    handle = await fs.promises.open(targetFile, "wx", 0o600);
    await handle.writeFile(initial, "utf8");
    await handle.sync();
    created = true;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
  } finally {
    await handle?.close().catch(() => {});
  }

  const verified = await readHarnessTarget(targetFile);
  if (!verified) throw new Error(`Harness target could not be read after initialization: ${targetFile}`);
  try {
    const parsed = JSON.parse(verified.toString("utf8")) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error(`Harness target is not a JSON object: ${targetFile}`);
    }
  } catch (error) {
    throw new Error(`Harness target could not be verified: ${(error as Error).message}`);
  }
  return { path: targetFile, created };
}

export const ensureGlobalHarnessTarget = ensureHarnessTarget;

export interface ResolvedHarnessTarget {
  request: string;
  targetFile: string;
  scope: "project.local" | "project" | "user";
  scopeLabel: string;
}

export function resolveHarnessTarget(
  rawArgs: string,
  cwd: string,
  agentDir?: string,
): ResolvedHarnessTarget {
  const paths = configPaths(cwd, agentDir);
  const trimmed = rawArgs.trim();

  let scope: "project.local" | "project" | "user" = "project.local";
  let request = trimmed;

  const flagMatch = trimmed.match(
    /^(--global-shared|--user-shared|--global|--user|--shared|--project-local|--project|--repo|--local|-g|-p|-l)\b\s*(.*)$/i,
  );

  if (flagMatch) {
    const flag = flagMatch[1].toLowerCase();
    request = flagMatch[2].trim();
    if (flag === "--global-shared" || flag === "--user-shared" || flag === "--global" || flag === "--user" || flag === "-g") {
      scope = "user";
    } else if (flag === "--shared" || flag === "--project" || flag === "--repo" || flag === "-p") {
      scope = "project";
    } else {
      scope = "project.local";
    }
  }

  let targetFile: string;
  let scopeLabel: string;
  switch (scope) {
    case "user":
      targetFile = paths.user;
      scopeLabel = "global shared harness.json";
      break;
    case "project":
      targetFile = paths.project;
      scopeLabel = "project shared harness.json (git-tracked)";
      break;
    case "project.local":
    default:
      targetFile = paths.projectLocal;
      scopeLabel = "project personal harness.local.json";
      break;
  }

  return { request, targetFile, scope, scopeLabel };
}

export function buildHarnessRulePrompt(request: string, targetFile: string, scopeLabel?: string, availableSkills: readonly string[] = []): string {
  const label = scopeLabel ?? (targetFile.endsWith("harness.local.json") ? "personal harness.local.json" : "harness.json");
  const skillRegistry = availableSkills.length ? availableSkills.join(", ") : "(none registered in this session)";
  return [
    "Create or update one Pi harness rule from the user's request below. This is an explicit write task, not a research task.",
    "",
    `User request: ${request}`,
    "",
    "Required creation protocol:",
    `- The only allowed target is ${targetFile}, the ${label}. Do not modify other harness files, memory, or unrelated files.`,
    `- Treat ${targetFile} as authoritative. Do not use find, fffind, grep, rg, read-directory, or any other discovery step to locate a different harness file.`,
    `- Execute this exact sequence: read ${targetFile} directly; if it is missing, immediately call the write tool with path=${targetFile}; then read ${targetFile} again to verify it.`,
    `- If ${targetFile} returns ENOENT, create it at that exact path instead of searching elsewhere. The write tool creates missing parent directories.`,
    `- For a missing target, write this complete initial JSON object before adding the requested rule: {"policies":[],"disabled":[],"skillPrompts":{}}.`,
    "- Preserve every existing policy, disabled entry, and skill prompt, and make the smallest change that satisfies the request.",
    `- Registered skill keys for this session (the only valid skillPrompts names): ${skillRegistry}`,
    "- Translate the request into a concrete declarative policy or skillPrompts entry. Policy names are descriptive identifiers; skillPrompts names must be exact registered skill keys above.",
    "- A skillPrompts value must be an object with a non-empty prompt string and target exactly \"system\" or \"user\" (optionally userMessagePattern); never write a bare string.",
    "- Reject or report any unknown skillPrompts key rather than writing an inert entry. Do not treat reading the JSON back as proof the skill prompt triggers; trigger-test the exact expanded skill invocation, or report that the runtime trigger was not verified.",
    "- Generalize project lessons through evidence -> reusable error class -> supported mechanism. Describe the behavior to preserve or prevent before choosing a regex gate or semantic instruction.",
    "- Treat incident document tokens, row numbers, or verbatim phrases as evidence, not rule boundaries. Retain resource identifiers only for an explicit resource-specific user requirement; do not confuse the authoritative harness output path with the resources a rule governs.",
    "- Transfer-test the candidate against another same-kind document and a rephrasing of the same mistake, and verify unrelated actions remain allowed. Generalize the error class without widening the action surface: no blanket confirmation of all writes.",
    "- For semantic instructions that regex cannot safely recognize, prefer skillPrompts only for an actual available skill established by the supplied context. Do not invent a skill. Guidance applies only to its matching expanded skill invocation, not a plain read of SKILL.md; it is not global interception or guaranteed project-wide semantic enforcement.",
    "- If neither a narrow tool-call gate nor an established skill invocation safely represents the lesson, report the limitation and do not add a rule. This safety exception takes precedence over the instruction to perform a rule change; keep the exact target creation protocol unchanged.",
    "- A policy may use only name, phase (tool-call, output, or artifact), tools, paths, artifactPaths, pattern or patterns, optional require, action, and reason. Do not write scope or rule: those fields are unsupported and the policy will be rejected.",
    "- Existing rules default to phase=tool-call and remain pre-execution regex gates. Use phase=output for final assistant text, or phase=artifact with artifactPaths for files produced by bash or another command tool; artifact checks read actual regular files after execution.",
    "- Existing guardrails are regex-based tool-call gates only; post-generation checks are deterministic regex checks with bounded corrective follow-ups. Do not represent runtime probes, token checks, process cleanup, or arbitrary generated code execution as policy behavior.",
    "- Keep the rule narrowly scoped to the requested tools, argument paths, and content; choose block or confirm deliberately.",
    `- Write the complete valid JSON back to ${targetFile}, then read that same path back and verify the resulting structure and behavior. Do not stop after describing the rule.`,
    "- If the request is ambiguous or cannot be represented safely, explain the issue instead of guessing or changing a different file.",
    "- Do not merely explain what should be done: perform the change and report the exact rule name and file changed.",
  ].join("\n");
}

export function validateHarnessWrite(input: unknown, availableSkills: ReadonlySet<string>, previous?: unknown): string[] {
  if (!input || typeof input !== "object" || Array.isArray(input)) return ["harness write input must be an object"];
  const value = input as Record<string, unknown>;
  const parsed = value.content;
  if (typeof parsed !== "string") return ["harness write content must be JSON text"];
  let json: unknown;
  try { json = JSON.parse(parsed); } catch { return ["harness write content must be valid JSON"]; }
  if (!json || typeof json !== "object" || Array.isArray(json)) return ["harness config must be an object"];
  const config = json as Record<string, unknown>;
  const prior = previous && typeof previous === "object" && !Array.isArray(previous)
    ? previous as Record<string, unknown>
    : {};
  const errors: string[] = [];

  if (!Array.isArray(config.policies)) {
    errors.push("policies must be an array");
  } else {
    config.policies.forEach((policy, index) => {
      errors.push(...validatePolicyDeclaration(policy).map((error) => `policies[${index}] ${error}`));
    });
  }

  if (!Array.isArray(config.disabled)) {
    errors.push("disabled must be an array");
  } else {
    config.disabled.forEach((name, index) => {
      if (typeof name !== "string" || !name.trim()) errors.push(`disabled[${index}] must be a non-empty policy name string`);
    });
  }

  if (!config.skillPrompts || typeof config.skillPrompts !== "object" || Array.isArray(config.skillPrompts)) {
    errors.push("skillPrompts must be an object");
  } else {
    const priorPrompts = prior.skillPrompts && typeof prior.skillPrompts === "object" && !Array.isArray(prior.skillPrompts)
      ? prior.skillPrompts as Record<string, unknown>
      : {};
    for (const [name, entry] of Object.entries(config.skillPrompts)) {
      if (Object.prototype.hasOwnProperty.call(priorPrompts, name) && isDeepStrictEqual(priorPrompts[name], entry)) continue;
      errors.push(...validateSkillPromptDeclaration(name, entry, availableSkills));
    }
  }

  const supported = new Set(["policies", "disabled", "skillPrompts"]);
  for (const [name, entry] of Object.entries(config)) {
    if (supported.has(name)) continue;
    if (!Object.prototype.hasOwnProperty.call(prior, name)) {
      errors.push(`unsupported top-level field "${name}" cannot be added by a harness write`);
    } else if (!isDeepStrictEqual(prior[name], entry)) {
      errors.push(`pre-existing top-level field "${name}" must be preserved unchanged`);
    }
  }
  for (const name of Object.keys(prior)) {
    if (!supported.has(name) && !Object.prototype.hasOwnProperty.call(config, name)) {
      errors.push(`pre-existing top-level field "${name}" must be preserved unchanged`);
    }
  }
  return errors;
}

/** The confirm gate blocks the agent loop while its dialog waits, so an
 * unattended session must fail closed after a bounded wait instead of
 * hanging. pi renders the remaining time as a live countdown. */
const GUARDRAILS_CONFIRM_TIMEOUT_MS = 60_000;

export default function registerGuardrails(pi: ExtensionAPI) {
  pi.registerEntryRenderer("harness-event", (entry, { expanded }, theme) => {
    const details = entry.data as HarnessEventData | undefined;
    if (details?.kind === "policy-matched") {
      const reason = safeDisplayText(details.reason);
      const label = details.action === "observe"
        ? "policy observed"
        : details.action === "confirm" && details.outcome === "allowed once"
          ? "policy allowed"
          : "policy blocked";
      return createStaticToolLifecycleMessageRenderer({
        createSpec: () => eventToolLifecycle("harness", reason, {
          label,
          details: [
            `policy=${details.policy}`,
            `action=${details.action}`,
            `outcome=${details.outcome}`,
            `tool=${details.tool}`,
            `source=${details.source}`,
            `file=${details.file}`,
            "",
            "reason:",
            reason,
          ],
        }),
        expandHint: "ctrl+o to expand",
        fit: truncateToWidth,
        visibleWidth,
        wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
        hostComponent: ToolExecutionComponent,
      })({ content: "", details }, { expanded }, theme);
    }
    const message = "harness policy event";
    return createStaticToolLifecycleMessageRenderer({
      createSpec: () => eventToolLifecycle("harness", message, { label: "event" }),
      expandHint: "ctrl+o to expand",
      fit: truncateToWidth,
      visibleWidth,
      wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
      hostComponent: ToolExecutionComponent,
    })({ content: "", details }, { expanded }, theme);
  });

  pi.on("tool_call", async (event, ctx) => {
    const cwd = ctx.cwd || process.cwd();
    const { config, paths } = resolveHarnessConfig(cwd);
    if (event.toolName === "write" || event.toolName === "edit") {
      const input = (event.input ?? {}) as Record<string, unknown>;
      const target = typeof input.path === "string" ? input.path : "";
      const targetPath = path.resolve(cwd, target);
      const harnessPaths = new Set(Object.values(paths).map((file) => path.resolve(file)));
      if (harnessPaths.has(targetPath)) {
        if (event.toolName === "edit") return { block: true, reason: "Harness configuration requires a complete validated JSON write. Read the target, preserve its entries, and use write instead of edit." };
        try {
          await assertHarnessTargetContained(targetPath, targetPath === path.resolve(paths.user) ? undefined : cwd);
        } catch (error) {
          return { block: true, reason: `Unsafe harness target: ${(error as Error).message}` };
        }
        const availableSkills = new Set(pi.getCommands().filter((command) => command.source === "skill").map((command) => command.name.replace(/^skill:/, "")));
        let previous: unknown;
        try { previous = JSON.parse(fs.readFileSync(targetPath, "utf8")); } catch { /* new target or malformed predecessor */ }
        const errors = validateHarnessWrite(input, availableSkills, previous);
        if (errors.length) return { block: true, reason: `Invalid harness configuration: ${errors.join("; ")}` };
      }
    }
    const decision = evaluate(config, {
      toolName: event.toolName,
      args: (event.input ?? {}) as Record<string, unknown>,
    });
    if (!decision) return undefined;

    const source = decision.source ?? "unknown";
    const file = harnessSourcePath(decision.source, paths);
    const cleanReason = decision.cleanReason ?? decision.reason;

    if (decision.action === "observe") {
      pi.appendEntry("harness-event", {
        kind: "policy-matched",
        policy: decision.policyName,
        action: "observe",
        tool: event.toolName,
        reason: cleanReason,
        outcome: "observed",
        source,
        file,
      });
      return undefined;
    }

    if (decision.action === "confirm") {
      if (!ctx.hasUI) {
        pi.appendEntry("harness-event", {
          kind: "policy-matched",
          policy: decision.policyName,
          action: "confirm",
          tool: event.toolName,
          reason: cleanReason,
          outcome: "no UI available to confirm",
          source,
          file,
        });
        return { block: true, reason: `${decision.reason}\n(no UI available to confirm)` };
      }
      const choice = await ctx.ui.select(
        `harness: ${decision.policyName}\n\n${cleanReason}\n\nAllow this call?`,
        ["Allow once", "Block"],
        { timeout: GUARDRAILS_CONFIRM_TIMEOUT_MS },
      );
      if (choice === "Allow once") {
        pi.appendEntry("harness-event", {
          kind: "policy-matched",
          policy: decision.policyName,
          action: "confirm",
          tool: event.toolName,
          reason: cleanReason,
          outcome: "allowed once",
          source,
          file,
        });
        return undefined;
      }
      // select resolves undefined on timeout — the same fail-closed outcome
      // as an explicit Block, with a reason that says which happened.
      const timedOut = choice === undefined;
      const outcome = timedOut ? "blocked: confirmation timed out" : "blocked by user choice";
      pi.appendEntry("harness-event", {
        kind: "policy-matched",
        policy: decision.policyName,
        action: "confirm",
        tool: event.toolName,
        reason: cleanReason,
        outcome,
        source,
        file,
      });
      return {
        block: true,
        reason: `${decision.reason}\n(${outcome})`,
      };
    }

    pi.appendEntry("harness-event", {
      kind: "policy-matched",
      policy: decision.policyName,
      action: "block",
      tool: event.toolName,
      reason: cleanReason,
      outcome: "blocked by rule",
      source,
      file,
    });
    return { block: true, reason: decision.reason };
  });

  pi.registerCommand("harness", {
    description: "Show active guardrails or create a rule from a prompt (default: project-local, --global for user, --shared for repo)",
    handler: async (rawArgs, ctx) => {
      const cwd = ctx.cwd || process.cwd();
      const { request, targetFile, scope, scopeLabel } = resolveHarnessTarget(rawArgs, cwd);
      if (request) {
        try {
          await ensureHarnessTarget(targetFile, scope === "user" ? undefined : cwd);
        } catch (error) {
          notifyPi(ctx.ui, `Cannot prepare harness target: ${(error as Error).message}`, "error");
          return;
        }
        const availableSkills = pi.getCommands()
          .filter((command) => command.source === "skill")
          .map((command) => command.name.replace(/^skill:/, ""));
        pi.sendUserMessage(buildHarnessRulePrompt(request, targetFile, scopeLabel, availableSkills), { deliverAs: "followUp" });
        return;
      }
      const { config, paths } = resolveHarnessConfig(cwd);
      const availableSkills = new Set(pi.getCommands().filter(command => command.source === 'skill').map(command => command.name.replace(/^skill:/, '')));
      const activeSkills = Object.keys(config.skillPrompts).filter(name => availableSkills.has(name));
      const inactiveSkills = Object.keys(config.skillPrompts).filter(name => !availableSkills.has(name));
      const lines = [
        `policies: ${config.policies.length ? config.policies.map((p) => p.name).join(", ") : "(none)"}`,
        `skill prompts (registered; trigger not verified): ${activeSkills.length ? activeSkills.join(", ") : "(none)"}`,
        `inactive skill prompts (no registered skill): ${inactiveSkills.length ? inactiveSkills.join(", ") : "(none)"}`,
        "built-in defaults are active unless disabled by name",
        "config paths:",
        `  ${paths.user}`,
        `  ${paths.project}`,
        `  ${paths.projectLocal} (optional)`,
      ];
      if (config.errors.length) {
        lines.push(
          `errors (${config.errors.length}):`,
          ...config.errors.slice(0, 5).map((e) => `  - ${e}`),
        );
      }
      notifyPi(ctx.ui, lines.join("\n"), "info");
    },
  });
}
