/**
 * pi-memory-fradser — native pi /memory command.
 *
 * Replaces the /skill:consolidate skill surface with a pi-native command menu:
 *
 *   /memory
 *     Auto-memory: on
 *     1. Select memory model
 *     2. Enter provider/model manually
 *     3. Consolidate memory now        (inline procedure from procedures/consolidate.md)
 *     4. Edit user instructions        (~/.pi/agent/AGENTS.md)
 *     5. Edit project instructions     (./AGENTS.md or ./CLAUDE.md — whichever exists)
 *     6. Open memory folder
 *     7. Toggle auto-memory
 *
 * Auto-memory on → `before_agent_start` injects prompt guidance that tells the
 * LLM to actively capture durable decisions/preferences into memory when needed.
 * Existing memories are always injected into the system prompt; the toggle only
 * controls the auto-write guidance. Consolidation uses a separately selected
 * Pi model when configured.
 */

import fs from "fs/promises";
import path from "path";
import os from "os";
import { spawn } from "node:child_process";
import * as nodeFs from "node:fs";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
  enterModelFromInput,
  modelRef,
  parseModelRef,
  PI_SPINNER_FRAMES,
  selectModelFromMenu,
  sortModels,
} from "@fradser/pi-kit";
import { CONFIG_DIR_NAME } from "@earendil-works/pi-coding-agent";
import {
  memoryConfigPath,
  readMemoryConfig,
  writeMemoryConfig,
  type MemoryConfig,
} from "./config";

export function getEscapedCwd(cwd: string): string {
  return cwd.replace(/\//g, "-");
}

export interface MemoryEntry {
  filename: string;
  source: "harness" | "public";
  content: string;
}

export async function loadAndDeduplicateMemories(cwd: string): Promise<MemoryEntry[]> {
  const escaped = getEscapedCwd(cwd);
  const homeDir = os.homedir();

  // Pi harness memory location (project-scoped, includes private files)
  const harnessDir = path.join(homeDir, CONFIG_DIR_NAME, "agent", "memory", escaped);
  const publicDir = path.join(cwd, ".memory");
  const memoriesMap = new Map<string, MemoryEntry>();

  // 1. Read public .memory/ first
  try {
    const files = await fs.readdir(publicDir);
    for (const file of files) {
      if (file.endsWith(".md") && file.toLowerCase() !== "memory.md") {
        const filePath = path.join(publicDir, file);
        const content = await fs.readFile(filePath, "utf-8");
        memoriesMap.set(file, {
          filename: file,
          source: "public",
          content,
        });
      }
    }
  } catch (err: unknown) {
    // ENOENT (dir missing) and other errors: skip silently
    void err;
  }

  // 2. Read harness location (takes precedence, includes private files)
  try {
    const files = await fs.readdir(harnessDir);
    for (const file of files) {
      if (file.endsWith(".md") && file.toLowerCase() !== "memory.md") {
        const filePath = path.join(harnessDir, file);
        const content = await fs.readFile(filePath, "utf-8");
        memoriesMap.set(file, {
          filename: file,
          source: "harness",
          content,
        });
      }
    }
  } catch (err: unknown) {
    // ENOENT (dir missing) and other errors: skip silently
    void err;
  }

  return Array.from(memoriesMap.values());
}

export function formatMemoriesBlock(memories: MemoryEntry[]): string {
  if (memories.length === 0) return "";

  const lines = ["# Active Project Memories\n"];
  for (const item of memories) {
    lines.push(`## Memory: ${item.filename}`);
    lines.push(item.content.trim());
    lines.push("");
  }

  return lines.join("\n");
}

// ── auto-memory settings (user-level, persisted) ───────────────────

interface MemorySettings {
  autoMemory: boolean;
}

let memoryConfig: MemoryConfig = readMemoryConfig();

function settingsFilePath(): string {
  return path.join(os.homedir(), CONFIG_DIR_NAME, "agent", "memory", "settings.json");
}

async function readSettings(): Promise<MemorySettings> {
  try {
    const raw = await fs.readFile(settingsFilePath(), "utf-8");
    const parsed = JSON.parse(raw) as Partial<MemorySettings>;
    return {
      autoMemory: parsed.autoMemory ?? true,
    };
  } catch {
    return {
      autoMemory: true,
    };
  }
}

async function writeSettings(s: MemorySettings): Promise<void> {
  await fs.mkdir(path.dirname(settingsFilePath()), { recursive: true });
  await fs.writeFile(settingsFilePath(), JSON.stringify(s, null, 2) + "\n", "utf-8");
}

// ── auto-memory guidance (injected when enabled) ───────────────────

const AUTO_MEMORY_GUIDANCE = `

## Auto-memory

You maintain a durable project memory. When you encounter a decision, user
preference, lesson, gotcha, or non-obvious project fact during this session,
**write it down immediately** — do not wait for a memory command:

- Search existing memory files first; if one covers the topic, edit it instead of creating a near-duplicate.
- One decision per file. Format: frontmatter (name, description, type) + **Why** + **How to apply** + **Related** [[links]].
- Mirror safe technical content to the project's \`.memory/\`; keep private content (credentials, personal preferences) harness-only.
- Do not log pure operations or timelines — those belong in git history.

Run \`/memory\` to review, edit, or consolidate memory at any time.
`;

// ── locate this package (consolidate procedure doc) ────────────────

async function pathExists(p: string): Promise<boolean> {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}

/**
 * Project instructions live in AGENTS.md (pi-native) or CLAUDE.md (Claude Code
 * convention) — pi loads either from cwd, so they are the same concept under
 * two names. Prefer AGENTS.md, fall back to CLAUDE.md, default to AGENTS.md.
 */
async function resolveProjectInstructionsFile(
  cwd: string,
): Promise<{ path: string; display: string }> {
  const agents = path.join(cwd, "AGENTS.md");
  const claude = path.join(cwd, "CLAUDE.md");
  if (await pathExists(agents)) return { path: agents, display: "./AGENTS.md" };
  if (await pathExists(claude)) return { path: claude, display: "./CLAUDE.md" };
  return { path: agents, display: "./AGENTS.md" };
}

/**
 * Resolve the shipped package root from this extension module. This works for
 * npm, git, and local installs without depending on Pi's settings format or
 * the active project's directory.
 */
function resolvePackageDir(): string {
  const extensionDir = path.dirname(fileURLToPath(import.meta.url));
  return path.resolve(extensionDir, "..");
}

// ── background consolidation ("dreaming") ─────────────────────────

function isPiPackageScript(filePath: string): boolean {
  try {
    const resolved = nodeFs.realpathSync(filePath);
    if (!/\.(mjs|cjs|js)$/.test(resolved)) return false;
    let dir = path.dirname(resolved);
    while (dir !== path.dirname(dir)) {
      const pkgPath = path.join(dir, "package.json");
      if (nodeFs.existsSync(pkgPath)) {
        const pkg = JSON.parse(nodeFs.readFileSync(pkgPath, "utf-8")) as { name?: unknown };
        return pkg.name === "@earendil-works/pi-coding-agent";
      }
      dir = path.dirname(dir);
    }
  } catch {
    // Unreadable paths are not candidates
  }
  return false;
}

/**
 * Resolve the Pi CLI for child-process spawning: the current process entry
 * (verified against the package manifest), the installed package's
 * dist/cli.js, or a `pi` binary on PATH (best effort).
 */
function resolvePiCli(): { command: string; args: string[] } | undefined {
  const argv1 = process.argv[1];
  if (argv1 && isPiPackageScript(argv1)) {
    return { command: process.execPath, args: [path.resolve(argv1)] };
  }
  try {
    const entry = fileURLToPath(import.meta.resolve("@earendil-works/pi-coding-agent"));
    const packageRoot = path.dirname(path.dirname(entry));
    const cliPath = path.join(packageRoot, "dist", "cli.js");
    if (nodeFs.existsSync(cliPath)) {
      return { command: process.execPath, args: [cliPath] };
    }
  } catch {
    // best effort — fall through to PATH
  }
  return { command: "pi", args: [] };
}

interface DreamState {
  active: boolean;
}

interface ChildJsonEvent {
  type?: string;
  toolCallId?: string;
  toolName?: string;
  args?: Record<string, unknown>;
  result?: unknown;
  isError?: boolean;
  error?: unknown;
  message?: {
    role?: string;
    content?: unknown;
  };
}

export interface ConsolidationEvidence {
  completedToolWork: boolean;
  fullValidatorPassed: boolean;
  gatesReported: boolean;
  lastJsonError: string;
  toolArgsByCallId: Map<string, Record<string, unknown>>;
}

export function createConsolidationEvidence(): ConsolidationEvidence {
  return {
    completedToolWork: false,
    fullValidatorPassed: false,
    gatesReported: false,
    lastJsonError: "",
    toolArgsByCallId: new Map(),
  };
}

function textFromJson(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(textFromJson).join("\n");
  if (value && typeof value === "object") {
    return Object.values(value as Record<string, unknown>).map(textFromJson).join("\n");
  }
  return "";
}

function isFullValidatorPass(event: ChildJsonEvent): boolean {
  const command = typeof event.args?.command === "string" ? event.args.command : "";
  if (!command.includes("validate-consolidate.py") || event.isError) return false;

  const match = /PASSED\s+checks=([a-z,]+)/i.exec(textFromJson(event.result));
  if (!match) return false;
  const checks = new Set(match[1].split(","));
  return ["cluster", "staleness", "report", "privacy"].every((check) => checks.has(check));
}

function hasCompletedGateReport(text: string): boolean {
  return Array.from({ length: 8 }, (_, index) => index + 1).every((gate) =>
    new RegExp(`\\bG${gate}\\b[^\\n]{0,120}\\b(?:pass|passed|complete|completed)\\b`, "i").test(text),
  );
}

export function recordConsolidationEvent(
  evidence: ConsolidationEvidence,
  event: ChildJsonEvent,
): void {
  if (typeof event.error === "string") evidence.lastJsonError = event.error;

  if (event.type === "tool_execution_start" && event.toolCallId && event.args) {
    evidence.toolArgsByCallId.set(event.toolCallId, event.args);
  }

  if (event.type === "tool_execution_end" && !event.isError) {
    evidence.completedToolWork = true;
    const args = event.toolCallId ? evidence.toolArgsByCallId.get(event.toolCallId) : undefined;
    if (isFullValidatorPass({ ...event, args })) evidence.fullValidatorPassed = true;
  }

  if (event.type === "message_end" && event.message?.role === "assistant") {
    if (hasCompletedGateReport(textFromJson(event.message.content))) {
      evidence.gatesReported = true;
    }
  }
}

export function missingConsolidationEvidence(evidence: ConsolidationEvidence): string[] {
  const missing: string[] = [];
  if (!evidence.completedToolWork) missing.push("completed tool work");
  if (!evidence.fullValidatorPassed) missing.push("a passing full validator");
  if (!evidence.gatesReported) missing.push("a G1–G8 passed gate report");
  return missing;
}

const DREAM_TIMEOUT_MS = 20 * 60 * 1000;

let dreamingTimer: NodeJS.Timeout | undefined;
let dreamingActivity = "";

function setDreamingWidget(ctx: ExtensionContext): void {
  if (ctx.mode !== "tui") return;

  if (dreamingTimer) {
    clearInterval(dreamingTimer);
    dreamingTimer = undefined;
  }

  ctx.ui.setWidget("memory-dreaming", (tui, theme) => {
    let frameIndex = 0;
    dreamingTimer = setInterval(() => {
      frameIndex++;
      tui.requestRender();
    }, 80);
    dreamingTimer.unref?.();

    return {
      render: (_width: number) => {
        const frame = PI_SPINNER_FRAMES[frameIndex % PI_SPINNER_FRAMES.length];
        const icon = theme?.fg ? theme.fg("accent", frame) : frame;
        const text = theme?.fg ? theme.fg("accent", "Dreaming...") : "Dreaming...";
        const detail = dreamingActivity
          ? theme?.fg
            ? theme.fg("muted", ` · ${dreamingActivity}`)
            : ` · ${dreamingActivity}`
          : "";
        // Leading space aligns the spinner with the native " ⠋ Working...\" row.
        return [` ${icon} ${text}${detail}`];
      },
      invalidate: () => {},
      dispose: () => {
        if (dreamingTimer) {
          clearInterval(dreamingTimer);
          dreamingTimer = undefined;
        }
      },
    };
  });
}

function availableMemoryModels(ctx: ExtensionContext) {
  const models = ctx.scopedModels.length > 0
    ? ctx.scopedModels.map((scoped) => scoped.model)
    : ctx.modelRegistry.getAvailable();
  return sortModels(models);
}

function configuredMemoryModel(): string {
  return modelRef(memoryConfig) ?? "(not configured)";
}

function saveMemoryConfig(next: MemoryConfig): void {
  memoryConfig = next;
  writeMemoryConfig(memoryConfig);
}

async function chooseMemoryModel(ctx: ExtensionContext): Promise<void> {
  const result = await selectModelFromMenu(
    ctx.ui,
    availableMemoryModels(ctx),
    configuredMemoryModel(),
    "Select a memory model",
  );
  if (!result) return;
  saveMemoryConfig(result);
  ctx.ui.notify(`Memory model set to ${result.provider}/${result.model}`, "info");
}

async function enterMemoryModel(ctx: ExtensionContext): Promise<void> {
  const result = await enterModelFromInput(ctx.ui, ctx.modelRegistry, modelRef(memoryConfig), { label: "Memory model" });
  if (!result) return;
  saveMemoryConfig(result);
  ctx.ui.notify(`Memory model set to ${result.provider}/${result.model}`, "info");
}

async function setMemoryModel(value: string, ctx: ExtensionContext): Promise<void> {
  const ref = parseModelRef(value);
  if (!ref) {
    ctx.ui.notify("Enter a model in provider/model format", "error");
    return;
  }
  if (!ctx.modelRegistry.find(ref.provider, ref.model)) {
    ctx.ui.notify(`Model ${ref.provider}/${ref.model} was not found in the model registry`, "error");
    return;
  }
  saveMemoryConfig(ref);
  ctx.ui.notify(`Memory model set to ${ref.provider}/${ref.model}`, "info");
}

function clearDreamingWidget(ctx: ExtensionContext): void {
  dreamingActivity = "";
  if (ctx.mode === "tui") ctx.ui.setWidget("memory-dreaming", undefined);
}

/**
 * Run the consolidation procedure in the background so the current session
 * stays responsive. The configured memory model is passed to the background
 * run when available. A "dreaming" widget shows progress until it exits.
 */
async function spawnAsyncConsolidation(
  ctx: ExtensionContext,
  state: DreamState,
  opts: { pkgDir: string; cwd: string; sessionFile?: string; reason: string },
): Promise<void> {
  const procedure = (
    await fs.readFile(path.join(opts.pkgDir, "procedures", "consolidate.md"), "utf-8")
  ).replaceAll("{{PKG_DIR}}", opts.pkgDir);
  const harnessDir = path.join(
    os.homedir(),
    CONFIG_DIR_NAME,
    "agent",
    "memory",
    getEscapedCwd(opts.cwd),
  );

  const taskText = [
    `Task: run the memory consolidation procedure below for the project at ${opts.cwd}.`,
    `- Reason: ${opts.reason}`,
    `- Session file (Step 0: capture durable content from its tail): ${opts.sessionFile ?? "none"}`,
    `- Harness memory dir: ${harnessDir}`,
    `- Public memory dir: ${opts.cwd}/.memory`,
    "",
    procedure,
  ].join("\n");

  const cli = resolvePiCli();
  if (!cli) {
    ctx.ui.notify("Memory consolidation: could not resolve the Pi CLI", "error");
    return;
  }

  const tempDir = nodeFs.mkdtempSync(path.join(os.tmpdir(), "memory-dream-"));
  const taskFile = path.join(tempDir, "task.md");
  nodeFs.writeFileSync(taskFile, taskText, { mode: 0o600 });

  let child;
  try {
    const modelArgs = memoryConfig.provider && memoryConfig.model
      ? ["--model", `${memoryConfig.provider}/${memoryConfig.model}`]
      : [];
    child = spawn(
      cli.command,
      [...cli.args, "--print", "--mode", "json", "--no-session", ...modelArgs, `@${taskFile}`],
      { cwd: opts.cwd, env: process.env, stdio: ["ignore", "pipe", "pipe"] },
    );
  } catch (err: unknown) {
    nodeFs.rmSync(tempDir, { recursive: true, force: true });
    ctx.ui.notify(`Memory consolidation spawn failed: ${(err as Error).message}`, "error");
    return;
  }

  state.active = true;
  setDreamingWidget(ctx);

  let stdoutBuffer = "";
  const evidence = createConsolidationEvidence();
  const handleJsonLine = (line: string): void => {
    if (!line.trim()) return;
    try {
      const event = JSON.parse(line) as ChildJsonEvent;
      recordConsolidationEvent(evidence, event);
      if (event.type !== "tool_execution_start" || !event.toolName) return;

      const name = event.toolName;
      let detail = "";
      if (event.args) {
        if (typeof event.args.path === "string") {
          detail = path.basename(event.args.path);
        } else if (typeof event.args.command === "string") {
          const cmd = event.args.command.trim();
          if (cmd.includes("validate-consolidate")) {
            detail = "validate-consolidate.py";
          } else {
            const compact = cmd.replace(/\s+/g, " ");
            detail = compact.length > 32 ? `${compact.slice(0, 32)}…` : compact;
          }
        }
      }
      dreamingActivity = name === "bash" ? detail : detail ? `${name} ${detail}` : name;
    } catch {
      // ignore non-JSON output
    }
  };
  child.stdout?.on("data", (chunk: Buffer) => {
    stdoutBuffer += chunk.toString();
    const lines = stdoutBuffer.split("\n");
    stdoutBuffer = lines.pop() || "";
    for (const line of lines) handleJsonLine(line);
  });

  let stderr = "";
  child.stderr.on("data", (c: Buffer) => {
    stderr += c.toString();
  });

  const timer = setTimeout(() => child.kill("SIGKILL"), DREAM_TIMEOUT_MS);
  timer.unref?.();

  let finished = false;
  const finish = (code: number | null, error?: Error): void => {
    if (finished) return;
    finished = true;
    if (stdoutBuffer) handleJsonLine(stdoutBuffer);
    clearTimeout(timer);
    state.active = false;
    clearDreamingWidget(ctx);
    try {
      nodeFs.rmSync(tempDir, { recursive: true, force: true });
    } catch {
      // best effort
    }
    if (error) {
      ctx.ui.notify(`Memory dreaming failed to start: ${error.message}`, "error");
    } else if (code === 0) {
      const missing = missingConsolidationEvidence(evidence);
      if (missing.length === 0) {
        ctx.ui.notify("Memory dreaming complete — memory consolidated.", "info");
      } else {
        const detail = stderr.trim() || evidence.lastJsonError;
        ctx.ui.notify(
          `Memory dreaming finished without verified consolidation: missing ${missing.join(", ")}${detail ? ` (${detail.slice(-300)})` : ""}`,
          "warning",
        );
      }
    } else {
      const errReason = stderr.trim() || evidence.lastJsonError || `exit code ${code}`;
      ctx.ui.notify(
        `Memory dreaming failed: ${errReason.slice(-300)}`,
        "error",
      );
    }
  };

  child.on("error", (err) => finish(null, err));
  child.on("close", (code) => finish(code));
  child.unref();
}

async function editInstructions(ctx: ExtensionCommandContext, filePath: string): Promise<void> {
  let current = "";
  try {
    current = await fs.readFile(filePath, "utf-8");
  } catch {
    // new file — start empty
  }

  if (ctx.mode !== "tui") {
    ctx.ui.notify(`Instructions file: ${filePath}`, "info");
    return;
  }

  const edited = await ctx.ui.editor(`Edit ${filePath}:`, current);
  if (edited === undefined) return; // cancelled

  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, edited, "utf-8");
  ctx.ui.notify(`Saved ${filePath}`, "info");
}

// ── extension ──────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  const dreamState: DreamState = { active: false };

  // Inject existing memories + auto-memory guidance before every turn
  pi.on("session_start", () => {
    memoryConfig = readMemoryConfig();
  });

  pi.on("before_agent_start", async (event, ctx) => {
    const cwd = ctx.cwd || process.cwd();
    const memories = await loadAndDeduplicateMemories(cwd);
    const settings = await readSettings();

    if (memories.length === 0 && !settings.autoMemory) return;

    let systemPrompt = event.systemPrompt || "";
    if (memories.length > 0) {
      systemPrompt = systemPrompt
        ? systemPrompt + "\n\n" + formatMemoriesBlock(memories)
        : formatMemoriesBlock(memories);
    }
    if (settings.autoMemory) {
      systemPrompt = systemPrompt + AUTO_MEMORY_GUIDANCE;
    }
    return { systemPrompt };
  });

  // /memory command with the management menu
  pi.registerCommand("memory", {
    description: "Manage project memory: model, instructions, memory folder, consolidation",
    handler: async (args, ctx) => {
      const command = args.trim();
      if (command === "model") {
        await chooseMemoryModel(ctx);
        return;
      }
      if (command.startsWith("model ")) {
        await setMemoryModel(command.slice("model ".length).trim(), ctx);
        return;
      }
      if (command === "show" || command === "status") {
        ctx.ui.notify(`Memory model: ${configuredMemoryModel()}\nConfig file: ${memoryConfigPath()}`, "info");
        return;
      }

      const settings = await readSettings();
      const status = settings.autoMemory ? "on" : "off";
      const cwd = ctx.cwd || process.cwd();
      const escaped = getEscapedCwd(cwd);
      const harnessDir = path.join(os.homedir(), CONFIG_DIR_NAME, "agent", "memory", escaped);
      const home = os.homedir();
      const pkgDir = await resolvePackageDir();
      const procedureFile = path.join(pkgDir, "procedures", "consolidate.md");
      const projectInstructions = await resolveProjectInstructionsFile(cwd);

      const options = [
        `Select memory model (current: ${configuredMemoryModel()})`,
        "Enter provider/model manually",
        "Consolidate memory now",
        "Edit user instructions (~/.pi/agent/AGENTS.md)",
        `Edit project instructions (${projectInstructions.display})`,
        "Open memory folder",
        `Toggle auto-memory (currently ${status})`,
      ];

      if (!ctx.hasUI) {
        ctx.ui.notify(
          [
            `Auto-memory: ${status}`,
            `Memory model: ${configuredMemoryModel()}`,
            `Harness memory: ${harnessDir}`,
            `Public memory: ${cwd}/.memory`,
            `Consolidate procedure: ${procedureFile}`,
          ].join("\n"),
          "info",
        );
        return;
      }

      const choice = await ctx.ui.select(`Auto-memory: ${status}\n\nMemory management:`, options);
      if (!choice) return; // cancelled

      if (choice.startsWith("Select memory model")) {
        await chooseMemoryModel(ctx);
      } else if (choice === "Enter provider/model manually") {
        await enterMemoryModel(ctx);
      } else if (choice.startsWith("Consolidate memory now")) {
        if (dreamState.active) {
          ctx.ui.notify("Memory consolidation is already running in background.", "info");
          return;
        }
        ctx.ui.notify("Starting memory consolidation in the background…", "info");
        await spawnAsyncConsolidation(ctx, dreamState, {
          pkgDir,
          cwd,
          sessionFile: ctx.sessionManager?.getSessionFile(),
          reason: "Consolidate the project memory now (user-invoked via /memory menu).",
        });
      } else if (choice.startsWith("Edit user instructions")) {
        await editInstructions(ctx, path.join(home, CONFIG_DIR_NAME, "agent", "AGENTS.md"));
      } else if (choice.startsWith("Edit project instructions")) {
        await editInstructions(ctx, projectInstructions.path);
      } else if (choice.startsWith("Open memory folder")) {
        await fs.mkdir(harnessDir, { recursive: true });
        if (ctx.mode === "tui" && process.platform === "darwin") {
          await pi.exec("open", [harnessDir]);
          ctx.ui.notify(`Opened ${harnessDir}`, "info");
        } else {
          ctx.ui.notify(`Memory folder: ${harnessDir}`, "info");
        }
      } else if (choice.startsWith("Toggle auto-memory")) {
        const next = { ...settings, autoMemory: !settings.autoMemory };
        await writeSettings(next);
        ctx.ui.notify(`Auto-memory: ${next.autoMemory ? "on" : "off"}`, "info");
      }
    },
  });

  // /consolidate — dedicated one-shot consolidation trigger, sibling of
  // /memory (no menu). Kept separate from /memory so the management menu
  // stays focused on instructions + settings. Consolidation runs in the
  // background, so the active session remains responsive.
  pi.registerCommand("consolidate", {
    description: "Consolidate project memory now",
    handler: async (_args, ctx) => {
      const cwd = ctx.cwd || process.cwd();
      const pkgDir = await resolvePackageDir();
      const procedureFile = path.join(pkgDir, "procedures", "consolidate.md");

      if (!ctx.hasUI) {
        ctx.ui.notify(`Consolidate procedure: ${procedureFile}`, "info");
        return;
      }

      if (dreamState.active) {
        ctx.ui.notify("Memory consolidation is already running.", "info");
        return;
      }

      ctx.ui.notify("Starting memory consolidation in the background…", "info");
      await spawnAsyncConsolidation(ctx, dreamState, {
        pkgDir,
        cwd,
        sessionFile: ctx.sessionManager?.getSessionFile(),
        reason: "Consolidate the project memory now (user-invoked via /consolidate command).",
      });
    },
  });
}
