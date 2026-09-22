/**
 * Minimal plan mode for Pi.
 *
 * Run a minimal read-only child, save its plan, then choose where to implement
 * through the native TUI. Legacy interactive planning remains available.
 *
 * Commands:
 *   /plan <prompt>     Plan in a minimal read-only child
 *   /plan              Toggle plan mode (menu)
 *   /plan start        Enter plan mode directly
 *   /plan exit         Leave plan mode
 *   /plan model        Set the dedicated planning model
 *   /plan status       Show current plan mode state
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type {
  ExtensionAPI,
  ExtensionCommandContext,
  ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { truncateToWidth } from "@earendil-works/pi-tui";
import type { Api, Model } from "@earendil-works/pi-ai";
import {
  createLiveActivityWidget,
  enterModelFromInput,
  modelLabel,
  modelRef,
  notifyPi,
  parseModelRef,
  renderPiWidgetRow,
  searchModelFromPicker,
  sortModels,
} from "@fradser/pi-kit";
import { type PlanModeConfig, readPlanModeConfig, writePlanModeConfig } from "./config";
import {
  runPlanWorker,
  type PlanWorkerUpdate,
} from "./plan-worker";

// ── Constants ───────────────────────────────────────────────────────

const CONFIG_DIR_NAME = ".pi";
const READ_ONLY_TOOLS = new Set(["read", "grep", "find", "ls"]);

function expandTilde(filepath: string): string {
  if (filepath === "~" || filepath.startsWith("~/")) {
    const home = process.env.HOME ?? os.homedir();
    return path.join(home, filepath.slice(1));
  }
  return filepath;
}

function reservePlanPath(topic: string): string {
  const slug = Array.from(topic.normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, ""))
    .slice(0, 60).join("").replace(/-$/g, "") || "plan";
  const agentDir = process.env.PI_CODING_AGENT_DIR
    ? expandTilde(process.env.PI_CODING_AGENT_DIR)
    : path.join(process.env.HOME ?? os.homedir(), CONFIG_DIR_NAME, "agent");
  const directory = path.resolve(agentDir, "plans");
  fs.mkdirSync(directory, { recursive: true });
  for (let suffix = 1; ; suffix++) {
    const candidate = path.join(directory, `${slug}${suffix === 1 ? "" : `-${suffix}`}.md`);
    try {
      fs.closeSync(fs.openSync(candidate, "wx"));
      return candidate;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
    }
  }
}

function getPlanPath(_ctx: ExtensionContext): string {
  return activePlanPath ?? "";
}

function ensurePlanPath(topic: string): string {
  if (!activePlanPath) {
    activePlanPath = reservePlanPath(topic);
    pi.appendEntry("plan-mode-path", { path: activePlanPath });
  }
  return activePlanPath;
}

function restorePlanPath(ctx: ExtensionContext): void {
  cancelPlanJob(ctx);
  activePlanPath = undefined;
  activePlanRequest = undefined;
  awaitingPlanRequest = false;
  for (const entry of ctx.sessionManager.getBranch()) {
    if (entry.type === "custom" && entry.customType === "plan-mode-path") {
      const data = entry.data as { path?: unknown } | undefined;
      if (typeof data?.path === "string" && path.isAbsolute(data.path) && data.path.endsWith(".md")) {
        activePlanPath = data.path;
      }
    }
  }
}

function buildPlanPrompt(planPath: string): string {
  return `# Plan Mode

You are in plan mode. Your FIRST step is read-only exploration — understand the codebase before designing anything. DO NOT write or edit any files yet.

## Rules
- Use ONLY read-only tools (read, grep, find, ls, and read-only bash commands)
- DO NOT edit, write, or modify any files (except the plan file below)
- Ask clarifying questions when requirements are ambiguous

## Process
1. **Explore FIRST**: Before writing any plan, read relevant files, understand existing patterns and architecture.
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
let awaitingPlanRequest = false;
let activePlanPath: string | undefined;
let lastCommandCtx: ExtensionCommandContext | undefined;
let planJob: AbortController | undefined;

function cancelPlanJob(ctx: ExtensionContext): void {
  const job = planJob;
  planJob = undefined;
  job?.abort();
  clearPlanWorkerWidget(ctx);
}

const planWorkerUpdates = new Map<string, PlanWorkerUpdate>();
let planWidgetContext: ExtensionContext | undefined;
const planWorkerWidget = createLiveActivityWidget({
  key: "plan-workers",
  placement: "aboveEditor",
  fit: truncateToWidth,
});

function activePlanWorkerActivities() {
  return [...planWorkerUpdates.values()].map((worker) => ({
    id: worker.id,
    identity: `${worker.id} (${worker.label})`,
    activity: worker.detail ?? "Working...",
    status: worker.status,
  }));
}

function startPlanWorkerWidget(ctx: ExtensionContext): void {
  planWorkerUpdates.clear();
  planWidgetContext = ctx;
}

function updatePlanWorkerWidget(update: PlanWorkerUpdate): void {
  planWorkerUpdates.set(update.id, update);
  planWorkerWidget.update(planWidgetContext, activePlanWorkerActivities());
}

function clearPlanWorkerWidget(ctx: ExtensionContext): void {
  planWorkerUpdates.clear();
  planWidgetContext = undefined;
  planWorkerWidget.clear(ctx);
}

function setPlanModeIndicator(ctx: ExtensionContext, active: boolean): void {
  if (ctx.mode !== "tui") return;
  if (!active) {
    ctx.ui.setWidget("plan-mode-indicator", undefined);
    return;
  }
  ctx.ui.setWidget("plan-mode-indicator", (_tui, theme) => ({
    render: (width: number) => {
      const line = theme.fg("warning", "plan mode on");
      return [renderPiWidgetRow(line, width, truncateToWidth)];
    },
    invalidate: () => {},
  }), { placement: "belowEditor" });
}

function isExecutionRequest(text: string): boolean {
  // Only a complete affirmative instruction can release the write guard.
  // Mentions, questions, quotations, and negated instructions stay in plan mode.
  const request = text.trim().replace(/[.!。！]+$/, "").trim();
  return /^(?:please\s+)?(?:(?:exit|leave)\s+plan\s*mode|implement\s+(?:the\s+)?plan)$/i.test(request)
    || /^(?:请\s*)?(?:(?:退出|离开)\s*(?:plan\s*mode|计划模式)|(?:开始|继续|确认|直接)执行|执行(?:这个|该)?计划)$/i.test(request);
}

async function reviewCurrentPlan(ctx: ExtensionContext): Promise<void> {
  cancelPlanJob(ctx);
  const job = new AbortController();
  planJob = job;
  try {
    await showPlanReview(ctx, activePlanRequest ?? "current plan", job.signal);
  } finally {
    if (planJob === job) planJob = undefined;
  }
}

async function showPlanReview(ctx: ExtensionContext, _request: string, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return;
  const planPath = getPlanPath(ctx);
  const planContent = fs.existsSync(planPath) ? fs.readFileSync(planPath, "utf-8") : "";
  if (!planContent.trim()) {
    notifyPi(ctx.ui, "No completed plan is available yet.", "warning");
    return;
  }
  if (!ctx.hasUI) {
    notifyPi(ctx.ui, `Plan written to ${planPath}`, "info");
    if (ctx.mode === "print") process.stderr.write(`Plan written to ${planPath}\n`);
    return;
  }
  const action = await ctx.ui.select(`Plan ready: ${planPath}`, [
    "Implement in current session", "Implement in new session", "Stay in plan mode",
  ], { signal });
  if (signal.aborted) return;
  if (!action || action === "Stay in plan mode") {
    notifyPi(ctx.ui, "Plan kept. Use /plan review when ready to implement.", "info");
    return;
  }
  const implementation = `Implement this plan:\nPlan file: ${planPath}\n\n${planContent}`;
  if (action === "Implement in current session") {
    await exitPlanMode(ctx);
    pi.sendUserMessage(implementation);
    return;
  }
  if (action !== "Implement in new session") return;
  const commandCtx = typeof (ctx as ExtensionCommandContext).newSession === "function"
    ? ctx as ExtensionCommandContext : lastCommandCtx;
  if (!commandCtx) {
    notifyPi(ctx.ui, "New session unavailable. The plan remains ready for review.", "warning");
    return;
  }
  const parentSession = ctx.sessionManager.getSessionFile();
  await exitPlanMode(ctx);
  try {
    const result = await commandCtx.newSession({
      parentSession,
      setup: async (sessionManager) => {
        sessionManager.appendCustomEntry("plan-mode-path", { path: planPath });
      },
      withSession: async (newCtx) => {
        await newCtx.sendUserMessage(implementation);
      },
    });
    if (!result.cancelled) return;
    notifyPi(ctx.ui, "New session cancelled. The plan remains ready for review.", "info");
  } catch (error) {
    notifyPi(ctx.ui, `New session unavailable: ${error instanceof Error ? error.message : String(error)}`, "error");
  }
  await enterPlanMode(ctx, false);
  awaitingPlanRequest = false;
}

async function runSubagentPlan(ctx: ExtensionCommandContext, request: string): Promise<void> {
  cancelPlanJob(ctx);
  const planPath = ensurePlanPath(request);
  const job = new AbortController();
  planJob = job;
  try {
    await enterPlanMode(ctx, false);
    if (planJob !== job) return;
    activePlanRequest = undefined;
    awaitingPlanRequest = false;
    startPlanWorkerWidget(ctx);
    const result = await runPlanWorker({
      prompt: request,
      cwd: ctx.cwd,
      planPath,
      model: modelRef(config) ?? (ctx.model ? modelLabel(ctx.model) : undefined),
      signal: job.signal,
      onUpdate: (update) => { if (planJob === job) updatePlanWorkerWidget(update); },
    });
    if (planJob !== job || job.signal.aborted) return;
    clearPlanWorkerWidget(ctx);
    if (result.exitCode !== 0) {
      reportPlanningFailure(ctx, result.stderr);
      return;
    }
    await showPlanReview(ctx, request, job.signal);
  } catch (error) {
    if (planJob !== job || job.signal.aborted) return;
    reportPlanningFailure(ctx, error instanceof Error ? error.message : String(error));
  } finally {
    if (planJob === job) {
      clearPlanWorkerWidget(ctx);
      planJob = undefined;
    }
  }
}

function reportPlanningFailure(ctx: ExtensionContext, detail: string): void {
  const message = `Planning failed: ${detail}`;
  notifyPi(ctx.ui, message, "error");
  if (!ctx.hasUI && ctx.mode === "print") process.stderr.write(`${message}\n`);
}

// ── Helpers ─────────────────────────────────────────────────────────

function getPlanModels(ctx: ExtensionContext): Model<Api>[] {
  const all =
    typeof ctx.modelRegistry.getAll === "function"
      ? ctx.modelRegistry.getAll()
      : ctx.modelRegistry.getAvailable();
  return sortModels([...all]);
}

function configuredModelLabel(): string {
  const ref = modelRef(config);
  return ref ?? "(not configured)";
}

function isReadOnlyBash(command: string): boolean {
  if (/[\x00-\x1f\x7f`$\\]/.test(command.replace(/\t/g, " "))) return false;
  if (!command.trim()) return true;
  const stages: string[][] = [];
  let tokens: string[] = [];
  let word = "";
  let started = false;
  let quote = "";
  const finishWord = () => {
    if (started) tokens.push(word);
    word = "";
    started = false;
  };
  for (let i = 0; i < command.length; i++) {
    const char = command[i];
    if (quote) {
      if (char === quote) quote = "";
      else word += char;
    } else if (char === "'" || char === '\"') {
      quote = char;
      started = true;
    } else if (char === " " || char === "\t") {
      finishWord();
    } else if (char === "|" || char === "&") {
      finishWord();
      if (!tokens.length || (char === "&" && command[++i] !== "&")) return false;
      stages.push(tokens);
      tokens = [];
    } else {
      if (/[;<>()[\]{}#*?~]/.test(char)) return false;
      word += char;
      started = true;
    }
  }
  finishWord();
  if (quote || !tokens.length) return false;
  stages.push(tokens);
  return stages.every(isReadOnlyCommand);
}

function isReadOnlyCommand([cmd, ...args]: string[]): boolean {
  const options = args.filter((arg) => arg.startsWith("-"));
  const safe = new Set([
    "cat", "head", "tail", "wc", "stat", "grep", "egrep", "fgrep",
    "ls", "dir", "pwd", "echo", "which", "type", "uptime",
  ]);
  if (safe.has(cmd)) return true;
  if (cmd === "jq") return true;
  if (cmd === "diff") return options.every((arg) => /^-[abBiqrsyuUwW0-9]+$/.test(arg)
    || ["--brief", "--recursive", "--unified", "--ignore-all-space", "--ignore-space-change"].includes(arg));
  if (cmd === "printf") return !args[0]?.startsWith("-");
  if (cmd === "uniq") return args.length <= 1 && !options.length;
  if (cmd === "date") return args.every((arg) => arg.startsWith("+"));
  if (cmd === "file") return options.every((arg) => /^-[bchiIkLnNprsvz0]+$/.test(arg));
  if (cmd === "sort") return options.every((arg) => /^-[bdfghinMnrRsuVz]+$/.test(arg));
  if (cmd === "tree") return options.every((arg) => /^-[adfFlpugsiDhrt]+$/.test(arg));
  if (cmd === "find") {
    return options.every((arg) => new Set([
      "-H", "-L", "-P", "-name", "-iname", "-path", "-ipath", "-type",
      "-maxdepth", "-mindepth", "-size", "-mtime", "-mmin", "-newer",
      "-print", "-print0", "-ls", "-prune", "-empty", "-o", "-a", "-not",
    ]).has(arg));
  }
  if (cmd === "rg" || cmd === "fd") {
    return options.every((arg) => /^-[nliwsvcrHh0ABC0-9]+$/.test(arg)
      || ["--files", "--hidden", "--no-ignore", "--glob", "--type", "-g", "-t"].includes(arg));
  }
  if (cmd === "git") return isReadOnlyGit(args);
  return false;
}

function isReadOnlyGit([subcommand, ...args]: string[]): boolean {
  if (["branch", "tag", "remote"].includes(subcommand)) {
    return args.every((arg) => ["--list", "-l", "-v", "-vv", "-a", "-r"].includes(arg));
  }
  if (!["status", "log", "diff", "show", "ls-files", "rev-parse", "describe", "blame", "grep", "shortlog"].includes(subcommand)) return false;
  return args.every((arg) => !arg.startsWith("-") || /^-\d+$/.test(arg)
    || /^--(?:format|pretty|max-count|since|until|author|grep)=/.test(arg) || [
    "--", "--oneline", "--stat", "--shortstat", "--name-only", "--name-status",
    "--cached", "--staged", "--no-pager", "--no-ext-diff", "--no-textconv",
    "--short", "--porcelain", "--all", "--graph", "--decorate", "--abbrev-ref",
    "--show-toplevel", "--verify", "--tags", "--always", "--long", "-n", "-p",
    "-s", "-b", "-u", "-w", "-M", "-C",
  ].includes(arg));
}

async function switchToPlanModel(ctx: ExtensionContext): Promise<void> {
  if (!config.provider || !config.model) return;
  const target = ctx.modelRegistry.find(config.provider, config.model);
  if (!target) {
    notifyPi(ctx.ui,
      `Plan model ${config.provider}/${config.model} not found in registry`,
      "warning",
    );
    return;
  }
  if (ctx.model) previousModelId = modelLabel(ctx.model);
  const ok = await pi.setModel(target);
  if (!ok) {
    notifyPi(ctx.ui,
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
    await reviewCurrentPlan(ctx);
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

  const selected = await searchModelFromPicker(
    ctx.ui,
    models,
    current,
    { title: "Plan model" },
  );
  if (selected) {
    config = { ...config, ...selected };
    writePlanModeConfig(config);
    notifyPi(ctx.ui, `Plan model set to ${selected.provider}/${selected.model}`, "info");
    return;
  }

  const choice = await ctx.ui.select("Plan model", [
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
    notifyPi(ctx.ui, `Plan model set to ${result.provider}/${result.model}`, "info");
    return;
  }

  config = { provider: undefined, model: undefined };
  writePlanModeConfig(config);
  notifyPi(ctx.ui, "Plan model cleared — will use the session model", "info");
}

function showStatus(ctx: ExtensionContext): void {
  const lines = [
    `Plan mode: ${planModeActive ? "active" : "off"}`,
    `Plan model: ${configuredModelLabel()}`,
    `Session model: ${ctx.model ? modelLabel(ctx.model) : "(none)"}`,
    `Plan file: ${getPlanPath(ctx) || "(waiting for a planning request)"}`,
  ];
  notifyPi(ctx.ui, lines.join("\n"), "info");
}

// ── Enter / Exit ────────────────────────────────────────────────────

async function enterPlanMode(ctx: ExtensionContext, switchModel = true): Promise<void> {
  if (planModeActive) return;
  planModeActive = true;
  awaitingPlanRequest = true;
  if (switchModel) await switchToPlanModel(ctx);
  setPlanModeIndicator(ctx, true);
  const active = ctx.model ? modelLabel(ctx.model) : "(none)";
  notifyPi(ctx.ui,
    `Plan mode enabled. Read-only exploration. Model: ${active}`,
    "info",
  );
}

async function exitPlanMode(ctx: ExtensionContext): Promise<void> {
  cancelPlanJob(ctx);
  planModeActive = false;
  activePlanRequest = undefined;
  awaitingPlanRequest = false;
  setPlanModeIndicator(ctx, false);
  await restoreModel(ctx);
  const active = ctx.model ? modelLabel(ctx.model) : "(none)";
  notifyPi(ctx.ui, `Plan mode disabled. Model: ${active}`, "info");
}

// ── Extension ───────────────────────────────────────────────────────

export default function planMode(extensionApi: ExtensionAPI): void {
  pi = extensionApi;
  config = readPlanModeConfig();

  pi.on("session_start", (_event, ctx) => restorePlanPath(ctx));
  pi.on("session_tree", (_event, ctx) => restorePlanPath(ctx));

  pi.on("input", async (event, ctx) => {
    if (!planModeActive || event.source === "extension" || !isExecutionRequest(event.text)) return;
    await exitPlanMode(ctx);
  });

  pi.on("agent_settled", (_event, ctx) => {
    if (!planModeActive || !activePlanRequest || planJob) return;
    const planPath = getPlanPath(ctx);
    const planContent = fs.existsSync(planPath) ? fs.readFileSync(planPath, "utf-8") : "";
    if (!planContent.trim()) return;

    const request = activePlanRequest;
    activePlanRequest = undefined;
    const job = new AbortController();
    planJob = job;
    // Review can replace the session, which waits for lifecycle handlers to return.
    const review = showPlanReview(ctx, request, job.signal);
    void review.catch((error: unknown) => {
      if (planJob !== job) return;
      notifyPi(ctx.ui, `Plan review failed: ${error instanceof Error ? error.message : String(error)}`, "error");
    }).finally(() => {
      if (planJob === job) planJob = undefined;
    });
  });

  pi.registerCommand("plan", {
    description: "Plan mode — read-only exploration and planning before implementation",
    handler: async (args, ctx) => {
      lastCommandCtx = ctx;
      const prompt = args.trim();
      const sub = prompt.toLowerCase();

      if (!sub) {
        if (!ctx.hasUI) {
          notifyPi(ctx.ui, "Usage: /plan start | /plan exit | /plan model | /plan status", "error");
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
        await reviewCurrentPlan(ctx);
        return;
      }

      if (/^model(?:\s|$)/i.test(prompt)) {
        const rest = prompt.slice("model".length).trim();
        if (rest) {
          const ref = parseModelRef(rest);
          if (!ref) {
            notifyPi(ctx.ui, "Usage: /plan model provider/model", "error");
            return;
          }
          const found = ctx.modelRegistry.find(ref.provider, ref.model);
          if (!found) {
            notifyPi(ctx.ui, `Model ${ref.provider}/${ref.model} not found in registry`, "error");
            return;
          }
          config = { ...config, ...ref };
          writePlanModeConfig(config);
          notifyPi(ctx.ui, `Plan model set to ${ref.provider}/${ref.model}`, "info");
          return;
        }
        if (!ctx.hasUI) {
          notifyPi(ctx.ui, "Usage: /plan model provider/model", "error");
          return;
        }
        await chooseModel(ctx);
        return;
      }

      // Await the child in the command so print mode also owns its lifetime.
      await runSubagentPlan(ctx, prompt);

    },
  });

  // Block mutating tools in plan mode (except the plan file)
  pi.on("tool_call", async (event, ctx) => {
    if (!planModeActive) return;

    // Extensions can replace built-ins under the same name. Authorize the
    // registered source before trusting either the name or plan-file arguments.
    const tool = pi.getAllTools().find((candidate) => candidate.name === event.toolName);
    if (tool?.sourceInfo.source !== "builtin") {
      return { block: true, reason: "Plan mode blocks extension and unknown tools, including overrides of built-in names." };
    }

    const allowedPlanPath = getPlanPath(ctx);

    if (event.toolName === "write") {
      const input = event.input as { path?: string };
      if (allowedPlanPath && input.path && path.resolve(ctx.cwd, input.path) === allowedPlanPath) {
        return; // Allow writing to the plan file
      }
      return {
        block: true,
        reason: `Plan mode blocks write. Write your plan to ${allowedPlanPath} instead.`,
      };
    }

    if (event.toolName === "edit") {
      const input = event.input as { path?: string };
      if (allowedPlanPath && input.path && path.resolve(ctx.cwd, input.path) === allowedPlanPath) {
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
      return;
    }

    if (!READ_ONLY_TOOLS.has(event.toolName)) {
      return { block: true, reason: "Plan mode blocks extension tools. Use read, grep, find, ls, read-only bash, or write/edit the assigned plan file." };
    }
  });

  pi.on("session_shutdown", async (_event, ctx) => {
    clearPlanWorkerWidget(ctx);
    setPlanModeIndicator(ctx, false);
    activePlanRequest = undefined;
    awaitingPlanRequest = false;
    previousModelId = undefined;
    lastCommandCtx = undefined;
    cancelPlanJob(ctx);
    planModeActive = false;
  });

  // Inject planning prompt
  pi.on("before_agent_start", async (event, _ctx) => {
    if (!planModeActive) return;
    if (awaitingPlanRequest) {
      activePlanRequest ??= event.prompt;
      awaitingPlanRequest = false;
    }
    const planPath = ensurePlanPath(event.prompt);
    return { systemPrompt: `${event.systemPrompt}\n\n${buildPlanPrompt(planPath)}` };
  });
}
