/**
 * Minimal plan mode for Pi.
 *
 * Inspired by Claude Code's plan mode: toggle read-only planning, explore
 * the codebase, design a plan, then exit to implement. Supports a dedicated
 * planning model that is automatically activated on entry and restored on exit.
 *
 * Commands:
 *   /plan              Toggle plan mode (menu)
 *   /plan start        Enter plan mode directly
 *   /plan exit         Leave plan mode
 *   /plan model        Set the dedicated planning model
 *   /plan status       Show current plan mode state
 */

import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import type {
  ExtensionAPI,
  ExtensionCommandContext,
  ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { CONFIG_DIR_NAME } from "@earendil-works/pi-coding-agent";
import type { Api, Model } from "@earendil-works/pi-ai";
import {
  createPiThemeStyle,
  enterModelFromInput,
  modelLabel,
  modelRef,
  parseModelRef,
  sortModels,
} from "@fradser/pi-kit";
import { type PlanModeConfig, readPlanModeConfig, writePlanModeConfig } from "./config";
import { runPlanWorker } from "./plan-worker";
import { createPlanOverlay, type PlanAction } from "./plan-overlay";

// ── Constants ───────────────────────────────────────────────────────

function planFilePath(sessionFile: string | undefined, cwd: string): string {
  const key = crypto
    .createHash("sha256")
    .update(sessionFile ?? cwd)
    .digest("hex")
    .slice(0, 16);
  return path.join(process.env.HOME ?? "~", CONFIG_DIR_NAME, "agent", "plans", `${key}.md`);
}

function getPlanPath(ctx: ExtensionContext): string {
  return planFilePath(ctx.sessionManager.getSessionFile(), ctx.cwd);
}

function buildPlanPrompt(planPath: string): string {
  return `# Plan Mode

You are in plan mode. Explore the codebase and design an implementation plan. DO NOT write or edit any files yet.

## Rules
- Use ONLY read-only tools (read, grep, find, ls, and read-only bash commands)
- DO NOT edit, write, or modify any files (except the plan file below)
- Ask clarifying questions when requirements are ambiguous
- Write your plan to ${planPath} when ready

## Process
1. **Explore**: Read relevant files, understand existing patterns and architecture
2. **Clarify**: Ask questions about ambiguities before designing
3. **Design**: Consider multiple approaches, identify trade-offs
4. **Plan**: Write a concrete implementation plan to ${planPath} with:
   - Context: why this change is needed
   - Approach: recommended solution with alternatives considered
   - Files to modify (specific paths)
   - Step-by-step implementation order
   - Verification: how to test the changes

When the plan is ready, tell the user to review ${planPath} and approve before implementation begins.`;
}

// ── State ───────────────────────────────────────────────────────────

let pi: ExtensionAPI;
let planModeActive = false;
let previousModelId: string | undefined;
let config: PlanModeConfig;

// ── Helpers ─────────────────────────────────────────────────────────

function getPlanModels(ctx: ExtensionContext): Model<Api>[] {
  const all = ctx.modelRegistry.getAvailable();
  return sortModels([...all]);
}

function configuredModelLabel(): string {
  const ref = modelRef(config);
  return ref ?? "(not configured)";
}

function isReadOnlyBash(command: string): boolean {
  const trimmed = command.trim();
  if (!trimmed) return true;
  if (/[;|&`$>]/.test(trimmed)) return false;
  const tokens = trimmed.split(/\s+/);
  const cmd = tokens[0]?.replace(/^(\/[\w/]*)?/, "").split("/").pop() ?? "";
  const SAFE = new Set([
    "cat", "head", "tail", "less", "wc", "file", "stat",
    "grep", "egrep", "fgrep", "rg",
    "find", "fd",
    "ls", "dir", "tree", "pwd",
    "git",
    "echo", "printf",
    "sort", "uniq", "diff",
    "jq", "yq",
    "which", "type",
    "date", "uptime",
  ]);
  return SAFE.has(cmd);
}

async function switchToPlanModel(ctx: ExtensionContext): Promise<void> {
  if (!config.provider || !config.model) return;
  const target = ctx.modelRegistry.find(config.provider, config.model);
  if (!target) {
    ctx.ui.notify(
      `Plan model ${config.provider}/${config.model} not found in registry`,
      "warning",
    );
    return;
  }
  if (ctx.model) previousModelId = modelLabel(ctx.model);
  const ok = await pi.setModel(target);
  if (!ok) {
    ctx.ui.notify(
      `Could not switch to plan model ${modelLabel(target)} — no API key?`,
      "warning",
    );
  }
}

async function restoreModel(ctx: ExtensionContext): Promise<void> {
  if (!previousModelId) return;
  const ref = parseModelRef(previousModelId);
  previousModelId = undefined;
  if (!ref) return;
  const target = ctx.modelRegistry.find(ref.provider, ref.model);
  if (target) await pi.setModel(target);
}

// ── Menu ────────────────────────────────────────────────────────────

async function showMenu(ctx: ExtensionCommandContext): Promise<void> {
  const currentModel = ctx.model ? modelLabel(ctx.model) : "(none)";

  if (!planModeActive) {
    const choice = await ctx.ui.select("Plan mode is off", [
      "Start plan mode",
      `Set plan model (current: ${configuredModelLabel()})`,
      "Show status",
    ]);
    if (!choice) return;

    if (choice === "Start plan mode") {
      await enterPlanMode(ctx);
    } else if (choice.startsWith("Set plan model")) {
      await chooseModel(ctx);
    } else if (choice === "Show status") {
      showStatus(ctx);
    }
    return;
  }

  const choice = await ctx.ui.select("Plan mode is active", [
    `Model: ${currentModel} (plan: ${configuredModelLabel()})`,
    "Exit plan mode",
    "Set plan model",
  ]);
  if (!choice) return;

  if (choice === "Exit plan mode") {
    await exitPlanMode(ctx);
  } else if (choice.startsWith("Model:")) {
    await chooseModel(ctx);
  } else if (choice === "Set plan model") {
    await chooseModel(ctx);
  }
}

async function chooseModel(ctx: ExtensionCommandContext): Promise<void> {
  const models = getPlanModels(ctx);
  const current = modelRef(config);

  const choice = await ctx.ui.select("Plan model", [
    ...models.map((m) => {
      const label = modelLabel(m);
      return label === current ? `${label} (current)` : label;
    }),
    "Enter provider/model manually",
    "Clear plan model (use session model)",
  ]);
  if (!choice) return;

  if (choice === "Enter provider/model manually") {
    const result = await enterModelFromInput(ctx.ui, ctx.modelRegistry, current, {
      label: "Plan model",
    });
    if (!result) return;
    config = { ...config, ...result };
    writePlanModeConfig(config);
    ctx.ui.notify(`Plan model set to ${result.provider}/${result.model}`, "info");
    return;
  }

  if (choice === "Clear plan model (use session model)") {
    config = { provider: undefined, model: undefined };
    writePlanModeConfig(config);
    ctx.ui.notify("Plan model cleared — will use the session model", "info");
    return;
  }

  const selected = models.find((m) => choice.startsWith(modelLabel(m)));
  if (selected) {
    config = { provider: selected.provider, model: selected.id };
    writePlanModeConfig(config);
    ctx.ui.notify(`Plan model set to ${modelLabel(selected)}`, "info");
  }
}

function showStatus(ctx: ExtensionContext): void {
  const lines = [
    `Plan mode: ${planModeActive ? "active" : "off"}`,
    `Plan model: ${configuredModelLabel()}`,
    `Session model: ${ctx.model ? modelLabel(ctx.model) : "(none)"}`,
    `Plan file: ${getPlanPath(ctx)}`,
  ];
  ctx.ui.notify(lines.join("\n"), "info");
}

// ── Enter / Exit ────────────────────────────────────────────────────

async function enterPlanMode(ctx: ExtensionContext): Promise<void> {
  planModeActive = true;
  await switchToPlanModel(ctx);
  const active = ctx.model ? modelLabel(ctx.model) : "(none)";
  ctx.ui.notify(
    `Plan mode enabled. Read-only exploration. Model: ${active}`,
    "info",
  );
}

async function exitPlanMode(ctx: ExtensionContext): Promise<void> {
  planModeActive = false;
  await restoreModel(ctx);
  const active = ctx.model ? modelLabel(ctx.model) : "(none)";
  ctx.ui.notify(`Plan mode disabled. Model: ${active}`, "info");
}

// ── Extension ───────────────────────────────────────────────────────

export default function planMode(extensionApi: ExtensionAPI): void {
  pi = extensionApi;
  config = readPlanModeConfig();

  pi.registerCommand("plan", {
    description: "Plan mode — read-only exploration and planning before implementation",
    handler: async (args, ctx) => {
      const prompt = args.trim();
      const sub = prompt.toLowerCase();

      if (!sub) {
        if (!ctx.hasUI) {
          ctx.ui.notify("Usage: /plan start | /plan exit | /plan model | /plan status", "error");
          return;
        }
        await showMenu(ctx);
        return;
      }

      if (sub === "start") {
        await enterPlanMode(ctx);
        return;
      }

      if (sub === "exit" || sub === "off") {
        await exitPlanMode(ctx);
        return;
      }

      if (sub === "status") {
        showStatus(ctx);
        return;
      }

      if (sub === "model") {
        const rest = prompt.slice("model".length).trim();
        if (rest) {
          const ref = parseModelRef(rest);
          if (!ref) {
            ctx.ui.notify("Usage: /plan model provider/model", "error");
            return;
          }
          const found = ctx.modelRegistry.find(ref.provider, ref.model);
          if (!found) {
            ctx.ui.notify(`Model ${ref.provider}/${ref.model} not found in registry`, "error");
            return;
          }
          config = { ...config, ...ref };
          writePlanModeConfig(config);
          ctx.ui.notify(`Plan model set to ${ref.provider}/${ref.model}`, "info");
          return;
        }
        if (!ctx.hasUI) {
          ctx.ui.notify("Usage: /plan model provider/model", "error");
          return;
        }
        await chooseModel(ctx);
        return;
      }

      // /plan <prompt> — spawn parallel explore workers + plan writer
      const planPath = getPlanPath(ctx);
      ctx.ui.notify(`Starting plan workers... Plan will be written to ${planPath}`, "info");

      // Enter plan mode (blocks mutating tools in main session)
      await enterPlanMode(ctx);

      // Spawn the plan workers in the background
      const workerModel = config.model ? `${config.provider}/${config.model}` : undefined;
      runPlanWorker({
        prompt,
        cwd: ctx.cwd,
        planPath,
        model: workerModel,
        signal: ctx.signal,
        onProgress: (msg) => ctx.ui.notify(msg, "info"),
      }).then(async (result) => {
        if (result.timedOut) {
          ctx.ui.notify("Plan workers timed out", "error");
          return;
        }
        if (result.exitCode !== 0) {
          ctx.ui.notify(`Plan generation failed: ${result.stderr}`, "error");
          return;
        }

        // Show usage summary
        if (result.totalUsage) {
          const { totalTokens, cost } = result.totalUsage;
          ctx.ui.notify(
            `Plan complete. ${result.exploreResults.length} explore workers + 1 plan writer. ${totalTokens} tokens, $${cost.toFixed(4)}`,
            "info",
          );
        }

        // Plan generated successfully — show plan overlay
        if (!ctx.hasUI) {
          ctx.ui.notify(`Plan written to ${planPath}`, "info");
          return;
        }

        const planContent = fs.existsSync(planPath) ? fs.readFileSync(planPath, "utf-8") : "";
        if (!planContent) {
          ctx.ui.notify("Plan file is empty", "warning");
          return;
        }

        // Show the plan overlay with action menu
        const action = await ctx.ui.custom<PlanAction | undefined>((tui, theme, _kb, done) => {
          const style = createPiThemeStyle(theme);
          const overlay = createPlanOverlay(tui, style, {
            planPath,
            planContent,
            onClose: () => done(undefined),
            onAction: (action) => done(action),
          });
          return overlay;
        }, {
          overlay: true,
          overlayOptions: {
            anchor: "bottom-center",
            width: "100%",
            maxHeight: "80%",
            margin: { bottom: 0 },
          },
        });

        if (!action) return;

        if (action === "implement-here") {
          // Exit plan mode and send the plan as context
          await exitPlanMode(ctx);
          pi.sendUserMessage(
            `The plan has been written to ${planPath}. Please implement it now.\n\n${planContent}`,
          );
        } else if (action === "implement-fresh") {
          // Create a new session with the plan
          await exitPlanMode(ctx);
          
          // Use newSession to create a fresh session
          const commandCtx = ctx as ExtensionCommandContext;
          if (typeof commandCtx.newSession === "function") {
            const parentSession = ctx.sessionManager.getSessionFile();
            await commandCtx.newSession({
              parentSession,
              withSession: async (newCtx) => {
                // Send the plan as the first message in the new session
                newCtx.ui.notify("Fresh implementation session started with plan context.", "info");
                pi.sendUserMessage(
                  `Implement this plan:\n\n${planContent}`,
                );
              },
            });
          } else {
            ctx.ui.notify("Note: Fresh session creation not available in this context. Use 'Implement here' instead.", "warning");
          }
        } else if (action === "view-plan") {
          // Show the full plan in a scrollable overlay
          await ctx.ui.custom<void>((tui, theme, _kb, done) => {
            const style = createPiThemeStyle(theme);
            const overlay = createPlanOverlay(tui, style, {
              planPath,
              planContent,
              onClose: () => done(undefined),
              onAction: () => done(undefined),
            });
            return overlay;
          }, {
            overlay: true,
            overlayOptions: {
              anchor: "bottom-center",
              width: "100%",
              maxHeight: "90%",
              margin: { bottom: 0 },
            },
          });
        } else if (action === "stay") {
          // Do nothing, stay in plan mode
        } else if (action === "exit") {
          await exitPlanMode(ctx);
        }
      }).catch((err) => {
        ctx.ui.notify(`Plan worker error: ${err.message}`, "error");
      });
    },
  });

  // Block mutating tools in plan mode (except the plan file)
  pi.on("tool_call", async (event, ctx) => {
    if (!planModeActive) return;

    const allowedPlanPath = getPlanPath(ctx);

    if (event.toolName === "write") {
      const input = event.input as { path?: string };
      if (input.path && path.resolve(input.path) === path.resolve(allowedPlanPath)) {
        return; // Allow writing to the plan file
      }
      return {
        block: true,
        reason: `Plan mode blocks write. Write your plan to ${allowedPlanPath} instead.`,
      };
    }

    if (event.toolName === "edit") {
      const input = event.input as { path?: string };
      if (input.path && path.resolve(input.path) === path.resolve(allowedPlanPath)) {
        return; // Allow editing the plan file
      }
      return {
        block: true,
        reason: `Plan mode blocks edit. Write your plan to ${allowedPlanPath} instead.`,
      };
    }

    if (event.toolName === "bash") {
      const command =
        typeof event.input === "object" && event.input !== null
          ? String((event.input as Record<string, unknown>).command ?? "")
          : "";
      if (!isReadOnlyBash(command)) {
        return {
          block: true,
          reason: `Plan mode blocks this bash command. Only read-only commands are allowed.`,
        };
      }
    }
  });

  // Inject planning prompt
  pi.on("before_agent_start", async (event, ctx) => {
    if (!planModeActive) return;
    const planPath = getPlanPath(ctx);
    return { systemPrompt: `${event.systemPrompt}\n\n${buildPlanPrompt(planPath)}` };
  });
}
