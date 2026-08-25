/**
 * Guardrails — the harness surface of continual learning: declarative
 * tool-call policies that evolve through layered JSON config. Matching calls
 * are blocked with corrective guidance (the "more correct prompt") or gated
 * behind user confirmation.
 *
 * Policies live in ~/.pi/agent/guardrails.json (+ .local) and
 * <project>/.pi/guardrails.json (+ .local). Curated defaults ship with the
 * package and can be disabled by name from any layer.
 */

import fs from "node:fs";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
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

let cached: { mtime: number; value: ResolvedWithPaths } | undefined;

function resolveConfig(cwd: string): ResolvedWithPaths {
  const paths = configPaths(cwd);
  let newest = 0;
  for (const file of Object.values(paths)) {
    try {
      newest = Math.max(newest, fs.statSync(file).mtimeMs);
    } catch {
      /* absent file */
    }
  }
  if (cached && cached.mtime === newest) return cached.value;
  const config = mergeLayers([defaultLayer(), ...loadLayers(cwd)]);
  cached = { mtime: newest, value: { config, paths } };
  return cached.value;
}

export default function registerGuardrails(pi: ExtensionAPI) {
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
      );
      if (choice === "Allow once") return undefined;
      return { block: true, reason: `${decision.reason}\n(blocked by user choice)` };
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
