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
import { truncateToWidth } from "@earendil-works/pi-tui";
import type { Api, Model } from "@earendil-works/pi-ai";
import {
  createPiThemeStyle,
  enterModelFromInput,
  modelLabel,
  modelRef,
  parseModelRef,
  PI_SPINNER_FRAMES,
  PI_SPINNER_INTERVAL_MS,
  sortModels,
} from "@fradser/pi-kit";
import { type PlanModeConfig, readPlanModeConfig, writePlanModeConfig } from "./config";
import {
  runPlanWorker,
  type PlanWorkerUpdate,
} from "./plan-worker";
import { createPlanOverlay, type PlanAction } from "./plan-overlay";

// ── Constants ───────────────────────────────────────────────────────

const CONFIG_DIR_NAME = ".pi";
const PLAN_REVIEW_TIMEOUT_MS = 30_000;

function planFilePath(sessionFile: string | undefined, cwd: string): string {
  const key = crypto
    .createHash("sha256")
    .update(sessionFile ?? cwd)
    .digest("hex")
    .slice(0, 16);
  const agentDir = process.env.PI_CODING_AGENT_DIR ?? path.join(process.env.HOME ?? "~", CONFIG_DIR_NAME, "agent");
  return path.join(agentDir, "plans", `${key}.md`);
}

function getPlanPath(ctx: ExtensionContext): string {
  return planFilePath(ctx.sessionManager.getSessionFile(), ctx.cwd);
}

function buildPlanPrompt(planPath: string): string {
  return `# Plan Mode

You are in plan mode. Your FIRST step is read-only exploration — understand the codebase before designing anything. DO NOT write or edit any files yet.

## Rules
- Use ONLY read-only tools (read, grep, find, ls, and read-only bash commands)
- DO NOT edit, write, or modify any files (except the plan file below)
- Ask clarifying questions when requirements are ambiguous
- You may use plan mode's built-in workers for parallel exploration when the task benefits from it

## Process
1. **Explore FIRST**: Before writing any plan, read relevant files, understand existing patterns and architecture. Use workers for parallel exploration when the codebase is large or spans multiple areas.
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
let activePlanRequest: string | undefined;
let planHandling = false;

const planWorkerUpdates = new Map<string, PlanWorkerUpdate>();
let planWidgetTui: { requestRender(): void } | undefined;
let planSpinnerTimer: ReturnType<typeof setInterval> | undefined;
let planSpinnerFrame = 0;

function renderPlanWorkerLines(width: number, theme: { fg(color: string, text: string): string; bold(text: string): string }): string[] {
  return [...planWorkerUpdates.values()].map((worker) => {
    const marker = worker.status === "running"
      ? theme.fg("warning", `${PI_SPINNER_FRAMES[planSpinnerFrame]}`)
      : worker.status === "completed"
        ? theme.fg("success", "✓")
        : worker.status === "failed"
          ? theme.fg("error", "✗")
          : theme.fg("muted", "○");
    const name = theme.bold(worker.id);
    const phase = theme.fg("muted", `(${worker.label})`);
    const activity = worker.detail ?? "Working...";
    const detail = ` · ${activity}`;
    const line = ` ${marker} ${name} ${phase}${detail}`;
    return truncateToWidth(line, Math.max(10, width - 1));
  });
}

function startPlanWorkerWidget(ctx: ExtensionContext): void {
  if (ctx.mode !== "tui") return;
  planWorkerUpdates.clear();
  planSpinnerFrame = 0;
  if (planSpinnerTimer) clearInterval(planSpinnerTimer);
  planSpinnerTimer = setInterval(() => {
    planSpinnerFrame = (planSpinnerFrame + 1) % PI_SPINNER_FRAMES.length;
    planWidgetTui?.requestRender();
  }, PI_SPINNER_INTERVAL_MS);
  planSpinnerTimer.unref?.();
  ctx.ui.setWidget("plan-workers", (tui, theme) => {
    planWidgetTui = tui;
    return {
      render: (width: number) => renderPlanWorkerLines(width, theme),
      invalidate: () => {},
      dispose: () => {
        if (planWidgetTui === tui) planWidgetTui = undefined;
      },
    };
  }, { placement: "aboveEditor" });
}

function updatePlanWorkerWidget(update: PlanWorkerUpdate): void {
  planWorkerUpdates.set(update.id, update);
  planWidgetTui?.requestRender();
}

function clearPlanWorkerWidget(ctx: ExtensionContext): void {
  if (planSpinnerTimer) {
    clearInterval(planSpinnerTimer);
    planSpinnerTimer = undefined;
  }
  planWidgetTui = undefined;
  planWorkerUpdates.clear();
  if (ctx.mode === "tui") ctx.ui.setWidget("plan-workers", undefined);
}

function setPlanModeIndicator(ctx: ExtensionContext, active: boolean): void {
  if (ctx.mode !== "tui") return;
  if (!active) {
    ctx.ui.setWidget("plan-mode-indicator", undefined);
    return;
  }
  ctx.ui.setWidget("plan-mode-indicator", (_tui, theme) => ({
    render: (width: number) => {
      const line = ` ${theme.fg("warning", "⏸")} ${theme.fg("warning", "plan mode on")}`;
      return [truncateToWidth(line, Math.max(10, width - 1))];
    },
    invalidate: () => {},
  }), { placement: "belowEditor" });
}

function isExecutionRequest(text: string): boolean {
  return /(?:退出|离开)\s*(?:plan\s*mode|计划模式)|(?:exit|leave)\s+plan\s*mode|(?:开始|继续|确认|直接)执行|执行(?:这个|该)?计划|implement\s+(?:the\s+)?plan/i.test(text);
}

function buildMainSessionPlanPrompt(planPath: string, request: string): string {
  return `Plan this request in the current session:

${request}

IMPORTANT: Start with read-only exploration FIRST. Read relevant files, understand the codebase, and identify affected areas before designing a plan. You may use plan mode's built-in workers for parallel exploration when the task spans multiple files or areas. Do not edit project files.

Decide first whether this is simple enough to plan directly or needs additional worker research. Write the final plan to ${planPath}.

When the plan is ready, explain:
1. The recommended implementation plan.
2. Which files would change and how.
3. How it will be verified.
4. End with exactly one marker: "Worker research: required" or "Worker research: not-needed". Decide this yourself; do not ask the user to start workers.`;
}

function buildWorkerResearchPrompt(planPath: string, request: string, planContent: string): string {
  return `Perform additional worker research for this plan request:

${request}

Existing main-session plan:
${planContent}

Use workers only where they add useful independent research. Do not rewrite the plan unless the research finds a concrete gap. Write any updates to ${planPath}.`;
}

async function showPlanReview(ctx: ExtensionContext, _request: string): Promise<void> {
  if (!ctx.hasUI) {
    ctx.ui.notify(`Plan written to ${getPlanPath(ctx)}`, "info");
    return;
  }

  const planPath = getPlanPath(ctx);
  const planContent = fs.existsSync(planPath) ? fs.readFileSync(planPath, "utf-8") : "";
  if (!planContent.trim()) {
    ctx.ui.notify(`The main session has not written a plan to ${planPath} yet.`, "warning");
    return;
  }

  const action = await ctx.ui.custom<PlanAction | undefined>((tui, theme, _kb, done) => {
    const timeout = setTimeout(() => done("implement-fresh"), PLAN_REVIEW_TIMEOUT_MS);
    timeout.unref?.();
    const style = createPiThemeStyle(theme);
    return createPlanOverlay(tui, style, {
      planPath,
      planContent,
      onClose: () => {
        clearTimeout(timeout);
        done(undefined);
      },
      onAction: (selected) => {
        clearTimeout(timeout);
        done(selected);
      },
    });
  }, {
    overlay: true,
    overlayOptions: {
      anchor: "bottom-center",
      width: "100%",
      margin: { bottom: 0 },
    },
  });

  if (!action) return;
  if (action === "stay") return;
  if (action === "exit") {
    await exitPlanMode(ctx);
    return;
  }
  if (action === "view-plan") {
    await ctx.ui.custom<void>((tui, theme, _kb, done) => {
      const style = createPiThemeStyle(theme);
      return createPlanOverlay(tui, style, {
        planPath,
        planContent,
        onClose: () => done(undefined),
        onAction: () => done(undefined),
      });
    }, {
      overlay: true,
      overlayOptions: {
        anchor: "bottom-center",
        width: "100%",
        margin: { bottom: 0 },
      },
    });
    return;
  }
  if (action === "implement-here") {
    await exitPlanMode(ctx);
    pi.sendUserMessage(
      `The plan has been written to ${planPath}. Please implement it now.\n\n${planContent}`,
    );
    return;
  }
  if (action === "implement-fresh") {
    await exitPlanMode(ctx);
    const commandCtx = ctx as ExtensionCommandContext;
    if (typeof commandCtx.newSession !== "function") {
      ctx.ui.notify("Fresh session unavailable — implementing in the current session.", "warning");
      pi.sendUserMessage(`The plan has been written to ${planPath}. Please implement it now.\n\n${planContent}`);
      return;
    }
    const parentSession = ctx.sessionManager.getSessionFile();
    await commandCtx.newSession({
      parentSession,
      withSession: async (newCtx) => {
        newCtx.ui.notify("Fresh implementation session started with plan context.", "info");
        await newCtx.sendUserMessage(`Implement this plan:\n\n${planContent}`);
      },
    });
    return;
  }

}

function requiresWorkerResearch(planContent: string): boolean {
  return /worker research\s*:\s*(?:required|needed|yes)\b/i.test(planContent);
}

async function runWorkerResearch(ctx: ExtensionContext, request: string, planContent: string): Promise<void> {
  const planPath = getPlanPath(ctx);
  const workerModel = modelRef(config) ?? (ctx.model ? modelLabel(ctx.model) : undefined);
  ctx.ui.notify(`Starting optional worker research... Plan will be written to ${planPath}`, "info");
  startPlanWorkerWidget(ctx);
  try {
    const result = await runPlanWorker({
      prompt: buildWorkerResearchPrompt(planPath, request, planContent),
      cwd: ctx.cwd,
      planPath,
      model: workerModel,
      signal: ctx.signal,
      onProgress: (message) => ctx.ui.notify(message, "info"),
      onUpdate: updatePlanWorkerWidget,
    });
    if (result.exitCode !== 0) {
      ctx.ui.notify(`Worker research failed: ${result.stderr}`, "error");
      return;
    }
    ctx.ui.notify("Optional worker research complete.", "info");
    await showPlanReview(ctx, request);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    ctx.ui.notify(`Worker research error: ${message}`, "error");
  } finally {
    clearPlanWorkerWidget(ctx);
  }
}

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
    "echo", "printf",
    "sort", "uniq", "diff",
    "jq", "yq",
    "which", "type",
    "date", "uptime",
  ]);
  if (cmd !== "git") return SAFE.has(cmd);
  const gitSubcommand = tokens[1]?.replace(/^--[^ ]+$/, "");
  return new Set([
    "status", "log", "diff", "show", "branch", "ls-files", "rev-parse",
    "describe", "remote", "tag", "blame", "grep", "shortlog",
  ]).has(gitSubcommand ?? "");
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
    "Review current plan",
    "Exit plan mode",
    "Set plan model",
  ]);
  if (!choice) return;

  if (choice === "Review current plan") {
    await showPlanReview(ctx, activePlanRequest ?? "current plan");
  } else if (choice === "Exit plan mode") {
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
  setPlanModeIndicator(ctx, true);
  const active = ctx.model ? modelLabel(ctx.model) : "(none)";
  ctx.ui.notify(
    `Plan mode enabled. Read-only exploration. Model: ${active}`,
    "info",
  );
}

async function exitPlanMode(ctx: ExtensionContext): Promise<void> {
  planModeActive = false;
  activePlanRequest = undefined;
  setPlanModeIndicator(ctx, false);
  await restoreModel(ctx);
  const active = ctx.model ? modelLabel(ctx.model) : "(none)";
  ctx.ui.notify(`Plan mode disabled. Model: ${active}`, "info");
}

// ── Extension ───────────────────────────────────────────────────────

export default function planMode(extensionApi: ExtensionAPI): void {
  pi = extensionApi;
  config = readPlanModeConfig();

  pi.on("input", async (event, ctx) => {
    if (!planModeActive || !isExecutionRequest(event.text)) return;
    await exitPlanMode(ctx);
  });

  pi.on("agent_end", async (_event, ctx) => {
    if (!planModeActive || !activePlanRequest || planHandling) return;
    const planPath = getPlanPath(ctx);
    const planContent = fs.existsSync(planPath) ? fs.readFileSync(planPath, "utf-8") : "";
    if (!planContent.trim()) return;

    const request = activePlanRequest;
    activePlanRequest = undefined;
    planHandling = true;
    try {
      if (requiresWorkerResearch(planContent)) {
        await runWorkerResearch(ctx, request, planContent);
      } else {
        await showPlanReview(ctx, request);
      }
    } finally {
      planHandling = false;
    }
  });

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

      if (sub === "review") {
        await showPlanReview(ctx, activePlanRequest ?? "current plan");
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

      // /plan <prompt> starts planning in the main session. Worker research is
      // deliberately deferred until the user explicitly asks for it.
      const planPath = getPlanPath(ctx);
      await enterPlanMode(ctx);
      activePlanRequest = prompt;
      planHandling = false;
      const planPrompt = buildMainSessionPlanPrompt(planPath, prompt);
      pi.sendUserMessage(planPrompt, { deliverAs: "followUp" });
      return;

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

  pi.on("session_shutdown", async (_event, ctx) => {
    clearPlanWorkerWidget(ctx);
    setPlanModeIndicator(ctx, false);
    activePlanRequest = undefined;
    planHandling = false;
  });

  // Inject planning prompt
  pi.on("before_agent_start", async (event, ctx) => {
    if (!planModeActive) return;
    const planPath = getPlanPath(ctx);
    return { systemPrompt: `${event.systemPrompt}\n\n${buildPlanPrompt(planPath)}` };
  });
}
