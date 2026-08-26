/**
 * Shared runtime helpers for FradSer pi packages.
 *
 * Everything lives in this single file on purpose: a zero-internal-import
 * module resolves identically under Node's native type stripping, tsx, pi's
 * extension loader, and tsc with any moduleResolution — no extensionless
 * specifier or allowImportingTsExtensions edge cases.
 */

// ── TUI ─────────────────────────────────────────────────────────────
// Spinner cadence matching pi's native " ⠋ Working..." loader and the
// accent/muted/dim style language used by overlay and console UIs
// (packages/btw is the canonical layout).

/** Braille spinner frames, identical to pi's native loader row. */
export const PI_SPINNER_FRAMES: string[] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

/** Spinner frame interval matching pi's native loader cadence. */
export const PI_SPINNER_INTERVAL_MS = 120;

/** Minimal structural view of pi's TUI theme: only fg() is needed. */
export interface PiThemeLike {
  fg(color: string, text: string): string;
}

/** Format the shared label shown when a teammate task starts. */
export function formatAgentTaskLabel(agentDescription: string, teammate: string, taskName: string): string {
  return `Agent (${agentDescription}) · @${teammate} · ${taskName}`;
}

/** Normalize a task prompt into the compact name shown in the TUI. */
export function formatAgentTaskName(prompt: string, fallback: string, maxLength = 80): string {
  const normalized = prompt.replace(/\s+/g, " ").trim() || fallback;
  return normalized.length <= maxLength ? normalized : `${normalized.slice(0, maxLength - 3)}...`;
}

/** Lifecycle row kind shared by background and coordination tools. */
export type ToolLifecycleKind = "started" | "event";

/** Shared lifecycle row specification. Consumers adapt it to Pi's TUI types. */
export interface ToolLifecycleSpec {
  kind: ToolLifecycleKind;
  tool: string;
  subject: string;
  /** Optional semantic label such as `created`, `listed`, or `to @name`. */
  label?: string;
  details?: readonly string[];
}

/** Format the compact tool event label used by background operations. */
export function formatToolEventLabel(
  kind: ToolLifecycleKind | "listed" | "created" | "gathered",
  description: string,
  tool = "monitor",
): string {
  return `[${safeDisplayText(tool)}] ${kind} · ${safeDisplayText(description)}`;
}

/** Build the common one-line lifecycle title for a tool result. */
export function formatToolLifecycleTitle(spec: ToolLifecycleSpec): string {
  const prefix = spec.label ?? spec.kind;
  return `[${safeDisplayText(spec.tool)}] ${safeDisplayText(prefix)} · ${safeDisplayText(spec.subject)}`;
}

/** Build a started-row specification. */
export function startedToolLifecycle(tool: string, subject: string): ToolLifecycleSpec {
  return { kind: "started", tool, subject };
}

/** Build an event-row specification with optional expandable details. */
export function eventToolLifecycle(
  tool: string,
  subject: string,
  options: { label?: string; details?: readonly string[] } = {},
): ToolLifecycleSpec {
  return { kind: "event", tool, subject, label: options.label, details: options.details };
}

/** Return a bounded lifecycle detail block for an expanded result. */
export function formatToolLifecycleDetails(spec: ToolLifecycleSpec, maxLines = 50): string[] {
  return (spec.details ?? []).slice(0, Math.max(0, maxLines)).map((line) => safeDisplayText(line));
}

/** Return the first safe non-empty line from a failed tool result. */
export function formatToolErrorLine(value: unknown, fallback = "Tool failed."): string {
  const line = safeDisplayText(value).split("\n").find((entry) => entry.trim());
  return line?.trim() || fallback;
}

/** Pi-independent adapters for the shared started/event row contract. */
export interface ToolLifecycleRenderOptions<T> {
  width: number;
  expanded?: boolean;
  expandHint?: string;
  titleStyle: (text: string) => string;
  detailStyle: (text: string) => string;
  truncate: (text: string, width: number) => string;
  line: (text: string) => T;
}

/**
 * Render one lifecycle row and, when expanded, its bounded detail lines.
 * Consumers provide Pi's Text/Box adapter, theme, and ANSI-aware truncator;
 * pi-kit owns the started-vs-event behavior so extensions cannot drift.
 */
export function renderToolLifecycle<T>(
  spec: ToolLifecycleSpec,
  options: ToolLifecycleRenderOptions<T>,
): T[] {
  if (options.width <= 0) return [];
  const title = options.titleStyle(formatToolLifecycleTitle(spec));
  const details = formatToolLifecycleDetails(spec);
  const collapsed = spec.kind === "started" || !options.expanded;
  if (collapsed) {
    const hint = spec.kind === "event" && details.length > 0 ? (options.expandHint ?? "") : "";
    return [options.line(options.truncate(`${title}${hint}`, options.width))];
  }
  return [
    options.line(options.truncate(title, options.width)),
    ...details.map((detail) => options.line(options.truncate(options.detailStyle(detail), options.width))),
  ];
}

/**
 * Format the dim expand hint appended to a collapsed transcript row
 * (" · ctrl+o to expand"), the same visual language as teammate report
 * rows. Callers pass the configured key text resolved by the host, e.g.
 * keyHint("app.tools.expand", "to expand").
 */
export function formatExpandHint(keyHintText: string, theme: PiThemeLike): string {
  return theme.fg("dim", ` · ${keyHintText}`);
}

/**
 * Strips ANSI/OSC escape sequences and control characters from untrusted
 * display text (registry values, process output) so it cannot inject
 * terminal commands or corrupt TUI layout.
 */
export function safeDisplayText(value: unknown): string {
  return String(value)
    .replace(/\u001b(?:\[[0-?]*[ -/]*[@-~]|\][^\u0007]*(?:\u0007|\u001b\\)|[@-_])/g, "")
    .replace(/(?:\u009b[0-?]*[ -/]*[@-~]|\u009d[^\u0007]*(?:\u0007|\u009c)|\u0090[^\u0007]*(?:\u0007|\u009c)|\u0098[^\u0007]*(?:\u0007|\u009c)|\u009e[^\u0007]*(?:\u0007|\u009c)|\u009f[^\u0007]*(?:\u0007|\u009c))/g, "")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\u0080-\u009f]/g, "");
}

/** Format the colored-prefix portion of an incoming or outgoing message label. */
export function formatAgentMessagePrefix(direction: "from" | "to", count = 1): string {
  const label = count === 1 ? "message" : `${count} messages`;
  return `[${label}] ${direction} `;
}

/** Format a compact teammate message label. */
export function formatAgentMessageLabel(teammate: string, direction: "from" | "to" = "from", count = 1): string {
  return `${formatAgentMessagePrefix(direction, count)}@${teammate}`;
}

/** Style callbacks shared by overlay/console UIs (the btw style language). */
export interface PiThemeStyle {
  accent: (s: string) => string;
  muted: (s: string) => string;
  dim: (s: string) => string;
  border: (s: string) => string;
  success: (s: string) => string;
  error: (s: string) => string;
  fg: (color: string, text: string) => string;
}

/** Adapt a pi theme to the shared style-callback language. */
export function createPiThemeStyle(theme: PiThemeLike): PiThemeStyle {
  return {
    accent: (s) => theme.fg("accent", s),
    muted: (s) => theme.fg("muted", s),
    dim: (s) => theme.fg("dim", s),
    border: (s) => theme.fg("border", s),
    success: (s) => theme.fg("success", s),
    error: (s) => theme.fg("error", s),
    fg: (color, s) => theme.fg(color, s),
  };
}

// ── Overlay layout helpers ──────────────────────────────────────────
// Shared by btw, plan-mode, and other overlay UIs.

/**
 * Compute the maximum body height for an overlay panel.
 * Caps at the given fraction of terminal rows (default 40%).
 */
export function maxBodyHeight(rows: number, fraction = 0.4): number {
  return Math.max(3, Math.floor(rows * fraction));
}

/**
 * Build Markdown theme callbacks from the shared style language.
 * Returns an object matching pi-tui's MarkdownTheme shape.
 */
export function buildMarkdownThemeCallbacks(style: PiThemeStyle): {
  heading: (t: string) => string;
  link: (t: string) => string;
  linkUrl: (t: string) => string;
  code: (t: string) => string;
  codeBlock: (t: string) => string;
  codeBlockBorder: (t: string) => string;
  quote: (t: string) => string;
  quoteBorder: (t: string) => string;
  hr: () => string;
  listBullet: (t: string) => string;
  bold: (t: string) => string;
  italic: (t: string) => string;
  strikethrough: (t: string) => string;
  underline: (t: string) => string;
} {
  return {
    heading: (t) => style.accent(t),
    link: (t) => style.accent(t),
    linkUrl: (t) => style.dim(t),
    code: (t) => style.accent(t),
    codeBlock: (t) => t,
    codeBlockBorder: (t) => style.border(t),
    quote: (t) => style.muted(t),
    quoteBorder: (t) => style.border(t),
    hr: () => "__OVERLAY_SEPARATOR__",
    listBullet: (t) => style.accent(t),
    bold: (t) => style.accent(t),
    italic: (t) => style.muted(t),
    strikethrough: (t) => style.dim(t),
    underline: (t) => t,
  };
}

/**
 * Pad a line to the given width with trailing spaces.
 */
export function padLine(line: string, width: number): string {
  // Simple approximation: visible width ≈ string length for most cases.
  // For precise ANSI-aware width, use pi-tui's visibleWidth.
  const visible = line.replace(/\x1b\[[0-9;]*m/g, "").length;
  return visible >= width ? line : line + " ".repeat(width - visible);
}

/**
 * Compute scroll window bounds for a scrollable panel.
 * Returns the slice of lines to display.
 */
export function computeScrollWindow(
  lines: string[],
  scroll: number,
  maxBody: number,
): { start: number; end: number; clampedScroll: number } {
  const viewport = Math.min(lines.length, maxBody);
  const max = Math.max(0, lines.length - viewport);
  const clampedScroll = Math.min(scroll, max);
  return { start: clampedScroll, end: clampedScroll + viewport, clampedScroll };
}

// ── Worker process helpers ──────────────────────────────────────────
// Shared by plan-mode, agent-teams, and btw for spawning child Pi processes.

import * as fs from "node:fs";
import * as path from "node:path";
import { spawn, type ChildProcess, type SpawnOptions } from "node:child_process";
import { fileURLToPath } from "node:url";

/** Result of resolving how to launch a Pi CLI process. */
export interface PiCliResolution {
  /** Command to execute — either a runtime (node/bun) or a `pi` binary. */
  command: string;
  /** Leading args: the CLI script path when running via a runtime, else empty. */
  args: string[];
}

/** Usage stats from a Pi worker run. */
export interface PiWorkerUsage {
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
  totalTokens: number;
  cost: number;
}

/** Result of a Pi worker run. */
export interface PiWorkerResult {
  text: string;
  usage?: PiWorkerUsage;
  exitCode: number;
  stderr: string;
}

/** Live state extracted from a spawned worker's JSON-mode output. */
export interface PiWorkerProgressUpdate {
  text: string;
  activeTool?: string;
  liveThinking?: string;
  turns: number;
}

/** Options for running a Pi worker. */
export interface RunPiWorkerOptions {
  /** Prompt to send to the worker. */
  prompt: string;
  /** Working directory for the child. */
  cwd: string;
  /** Tools to allow (comma-separated or array). */
  tools?: string | string[];
  /** Model to use (e.g. "anthropic/claude-3-5-sonnet"). */
  model?: string;
  /** Abort signal to cancel the worker. */
  signal?: AbortSignal;
  /** Additional environment variables. */
  env?: Record<string, string | undefined>;
  /** Additional CLI arguments. */
  extraArgs?: string[];
  /** Called when JSON-mode output reveals live worker activity. */
  onUpdate?: (update: PiWorkerProgressUpdate) => void;
}

/** Bounded grace period before a cancellation escalates from SIGTERM to SIGKILL. */
export const DEFAULT_TERMINATION_GRACE_MS = 5_000;

const processGroupChildren = new WeakSet<ChildProcess>();
const closedChildren = new WeakSet<ChildProcess>();

/** Spawn a Pi child in its own process group where the platform supports it. */
export function spawnPiChild(command: string, args: string[], options: SpawnOptions = {}): ChildProcess {
  const child = spawn(command, args, {
    ...options,
    detached: process.platform === "win32" ? false : true,
  });
  if (process.platform !== "win32") processGroupChildren.add(child);
  child.once("close", () => closedChildren.add(child));
  return child;
}

/**
 * Resolve how to launch a Pi CLI process.
 *
 * Resolution order:
 *   1. `process.argv[1]` — the current Pi process entry, verified against the
 *      exact coding-agent package manifest.
 *   2. The installed coding-agent package's `dist/cli.js`.
 *   3. A `pi` binary on PATH (best effort).
 */
export function resolvePiCli(): PiCliResolution {
  const argv1 = process.argv[1];
  if (argv1 && isPiPackageScript(argv1)) {
    return { command: process.execPath, args: [path.resolve(argv1)] };
  }

  const installed = resolveInstalledPiCli();
  if (installed) return installed;

  return { command: "pi", args: [] };
}

function isPiPackageScript(filePath: string): boolean {
  try {
    const resolved = fs.realpathSync(filePath);
    if (!/\.(mjs|cjs|js)$/.test(resolved)) return false;
    let dir = path.dirname(resolved);
    while (dir !== path.dirname(dir)) {
      const pkgPath = path.join(dir, "package.json");
      if (fs.existsSync(pkgPath)) {
        const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf-8")) as { name?: unknown };
        return pkg.name === "@earendil-works/pi-coding-agent";
      }
      dir = path.dirname(dir);
    }
  } catch {
    // Unreadable paths are simply not candidates.
  }
  return false;
}

function resolveInstalledPiCli(): PiCliResolution | undefined {
  try {
    const entry = fileURLToPath(import.meta.resolve("@earendil-works/pi-coding-agent"));
    const packageRoot = path.dirname(path.dirname(entry));
    const cliPath = path.join(packageRoot, "dist", "cli.js");
    if (fs.existsSync(cliPath)) return { command: process.execPath, args: [cliPath] };
  } catch {
    // Package resolution is best-effort; fall through to PATH.
  }
  return undefined;
}

/**
 * Run a Pi worker child process and return the result.
 *
 * Spawns `pi --print --mode json --no-session` with the given prompt and tools.
 * Parses the JSONL output to extract the final text and usage stats.
 */
export async function runPiWorker(options: RunPiWorkerOptions): Promise<PiWorkerResult> {
  const { prompt, cwd, tools, model, signal, env, extraArgs, onUpdate } = options;
  const cli = resolvePiCli();

  const args = [...cli.args, "--print", "--mode", "json", "--no-session"];
  if (model) args.push("--model", model);
  if (tools) {
    const toolStr = Array.isArray(tools) ? tools.join(",") : tools;
    args.push("--tools", toolStr);
  }
  if (extraArgs) args.push(...extraArgs);
  args.push(prompt);

  return new Promise((resolve) => {
    let stdout = "";
    let stderr = "";
    let stdoutBuffer = "";
    const progress = createPiWorkerProgress();
    const emitProgress = () => onUpdate?.({
      text: progress.text,
      activeTool: progress.activeTool,
      liveThinking: progress.thinking,
      turns: progress.turns,
    });

    const child = spawnPiChild(cli.command, args, {
      cwd,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, ...env },
    });

    let termination: Promise<boolean> | undefined;
    const abortHandler = () => {
      termination ??= terminateChildProcess(child);
    };
    signal?.addEventListener("abort", abortHandler, { once: true });

    child.stdout?.on("data", (chunk) => {
      const text = chunk.toString();
      stdout += text;
      stdoutBuffer += text;
      const lines = stdoutBuffer.split("\n");
      stdoutBuffer = lines.pop() ?? "";
      let changed = false;
      for (const line of lines) changed = applyPiWorkerProgress(progress, line) || changed;
      if (changed) emitProgress();
    });

    child.stderr?.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("close", (code) => {
      signal?.removeEventListener("abort", abortHandler);

      const { text, usage } = parsePiWorkerOutput(stdout);
      resolve({
        text,
        usage,
        exitCode: code ?? 1,
        stderr,
      });
    });

    child.on("error", (err) => {
      signal?.removeEventListener("abort", abortHandler);
      resolve({
        text: "",
        exitCode: 1,
        stderr: err.message,
      });
    });
  });
}

/**
 * Parse the JSONL output of a `pi --print --mode json` worker run.
 * Returns the final assistant text and the last reported usage.
 */
export function parsePiWorkerOutput(stdout: string): { text: string; usage?: PiWorkerUsage } {
  let text = "";
  let usage: PiWorkerUsage | undefined;

  for (const line of stdout.split("\n")) {
    if (!line.trim()) continue;
    let event: {
      type?: string;
      message?: {
        role?: string;
        content?: Array<{ type?: string; text?: string }>;
        usage?: {
          input?: number;
          output?: number;
          cacheRead?: number;
          cacheWrite?: number;
          totalTokens?: number;
          cost?: { total?: number };
        };
      };
    };
    try {
      event = JSON.parse(line);
    } catch {
      continue;
    }
    if (event.type !== "message_end" || event.message?.role !== "assistant") continue;
    const parts = (event.message.content ?? [])
      .filter((part) => part.type === "text" && typeof part.text === "string")
      .map((part) => part.text as string);
    if (parts.length > 0) text = parts.join("\n");
    const u = event.message.usage;
    if (u) {
      usage = {
        input: u.input ?? 0,
        output: u.output ?? 0,
        cacheRead: u.cacheRead ?? 0,
        cacheWrite: u.cacheWrite ?? 0,
        totalTokens: u.totalTokens ?? 0,
        cost: u.cost?.total ?? 0,
      };
    }
  }
  return { text, usage };
}

/**
 * Terminate a child process gracefully, escalating to SIGKILL if needed.
 * Resolution is based on the child's close event, not only its exit code.
 */
export async function terminateChildProcess(
  child: ChildProcess,
  graceMs = DEFAULT_TERMINATION_GRACE_MS,
): Promise<boolean> {
  const closedAfterTerm = waitForClose(child, graceMs);
  if (!isChildRunning(child)) return closedAfterTerm;

  if (!signalChild(child, "SIGTERM")) return closedAfterTerm;
  if (await closedAfterTerm) return true;
  if (!isChildRunning(child)) return false;

  const closedAfterKill = waitForClose(child, graceMs);
  if (!signalChild(child, "SIGKILL")) return closedAfterKill;
  return closedAfterKill;
}

function isChildRunning(child: ChildProcess): boolean {
  return child.exitCode === null && child.signalCode === null;
}

function signalChild(child: ChildProcess, signal: NodeJS.Signals): boolean {
  if (process.platform !== "win32" && child.pid && processGroupChildren.has(child)) {
    try {
      process.kill(-child.pid, signal);
      return true;
    } catch {
      // Fall through to the direct child signal when the process group is gone.
    }
  }
  try {
    return child.kill(signal);
  } catch {
    return false;
  }
}

interface PiWorkerProgressState {
  text: string;
  thinking: string;
  toolcallArgs: string;
  activeTool?: string;
  turns: number;
}

function createPiWorkerProgress(): PiWorkerProgressState {
  return { text: "", thinking: "", toolcallArgs: "", turns: 0 };
}

function applyPiWorkerProgress(state: PiWorkerProgressState, line: string): boolean {
  if (!line.trim()) return false;
  let event: {
    type?: string;
    assistantMessageEvent?: { type?: string; delta?: string; toolCall?: { name?: string } };
    message?: { role?: string; content?: Array<{ type?: string; text?: string }> };
  };
  try {
    event = JSON.parse(line) as typeof event;
  } catch {
    return false;
  }
  if (event.type === "message_end" && event.message?.role === "assistant") {
    state.turns++;
    const text = extractTextContent(event.message.content, "");
    if (text.trim()) state.text = text;
    return true;
  }
  if (event.type !== "message_update" || !event.assistantMessageEvent) return false;
  const update = event.assistantMessageEvent;
  switch (update.type) {
    case "text_delta":
      state.activeTool = undefined;
      state.text += update.delta ?? "";
      return true;
    case "thinking_delta":
      state.activeTool = undefined;
      state.thinking += update.delta ?? "";
      return true;
    case "toolcall_start":
      state.toolcallArgs = "";
      state.activeTool = undefined;
      return true;
    case "toolcall_delta":
      state.toolcallArgs += update.delta ?? "";
      state.activeTool = toolcallLabel(state.toolcallArgs) ?? state.activeTool;
      return true;
    case "toolcall_end":
      state.activeTool = undefined;
      state.toolcallArgs = "";
      return true;
    default:
      return false;
  }
}

function toolcallLabel(rawArgs: string): string | undefined {
  try {
    const args = JSON.parse(rawArgs) as Record<string, unknown>;
    if (typeof args.command === "string" && args.command.trim()) return `bash: ${truncateInline(args.command, 40)}`;
    if (typeof args.path === "string" && args.path.trim()) return `file: ${path.basename(args.path.trim())}`;
    if (typeof args.query === "string" && args.query.trim()) return `search: ${truncateInline(args.query, 40)}`;
  } catch {
    // Tool-call arguments are incomplete while they stream.
  }
  return undefined;
}

function truncateInline(text: string, cap: number): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  return oneLine.length <= cap ? oneLine : `${oneLine.slice(0, cap).trimEnd()} ...`;
}

function waitForClose(child: ChildProcess, graceMs: number): Promise<boolean> {
  if (closedChildren.has(child)) return Promise.resolve(true);
  return new Promise((resolve) => {
    let settled = false;
    const onClose = () => {
      closedChildren.add(child);
      finish(true);
    };
    const timer = setTimeout(() => finish(false), graceMs);
    timer.unref?.();

    function finish(closed: boolean): void {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      child.off("close", onClose);
      resolve(closed);
    }

    child.once("close", onClose);
  });
}

// ── Messages ────────────────────────────────────────────────────────

/**
 * Extract plain text from a pi message content value (string or content-block
 * array). Non-text blocks (images, tool calls, thinking) contribute nothing.
 * Returns the joined text, possibly empty; callers own trim/empty semantics.
 */
export function extractTextContent(content: unknown, separator = "\n"): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  const texts: string[] = [];
  for (const part of content) {
    if (typeof part !== "object" || part === null) continue;
    const block = part as { type?: unknown; text?: unknown };
    if (block.type === "text" && typeof block.text === "string") texts.push(block.text);
  }
  return texts.join(separator);
}

// ── Model selection ─────────────────────────────────────────────────
// Shared across memory, recap, and vision for selecting a model from the
// registry via the interactive TUI menu (ctx.ui.select/input).

/**
 * Return the trimmed string when it is non-empty, otherwise undefined.
 * Shared by readConfig functions across packages.
 */
export function nonEmpty(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/**
 * Parse a "provider/model" reference string into its parts. Invalid formats
 * (no slash, leading/trailing slash, empty) return undefined.
 */
export function parseModelRef(
  value: string | undefined,
): { provider: string; model: string } | undefined {
  const ref = nonEmpty(value);
  if (!ref) return undefined;
  const separator = ref.indexOf("/");
  if (separator <= 0 || separator === ref.length - 1) return undefined;
  return { provider: ref.slice(0, separator), model: ref.slice(separator + 1) };
}

/**
 * Format a config's provider and model as "provider/model". Returns the bare
 * model when only the model is set, or undefined when neither is set.
 */
export function modelRef(config: { provider?: string; model?: string }): string | undefined {
  if (config.provider && config.model) return `${config.provider}/${config.model}`;
  return config.model;
}

/** Format a model as "provider/id". */
export function modelLabel(model: { provider: string; id: string }): string {
  return `${model.provider}/${model.id}`;
}

/** Sort models in-place by provider/id label. */
export function sortModels<T extends { provider: string; id: string }>(models: T[]): T[] {
  return models.sort((a, b) => modelLabel(a).localeCompare(modelLabel(b)));
}

/** Minimal UI surface for interactive model selection via ctx.ui.select. */
export interface MenuUi {
  select(label: string, options: string[]): Promise<string | undefined>;
  notify(msg: string, type?: "error" | "info" | "warning"): void;
}

/** Minimal UI surface for interactive model entry via ctx.ui.input. */
export interface InputUi {
  input(label: string, defaultValue?: string): Promise<string | undefined>;
  notify(msg: string, type?: "error" | "info" | "warning"): void;
}

/**
 * Interactive model selection via ctx.ui.select. Pass the available models
 * (already filtered and sorted by the caller), the current model reference
 * (for the "current" marker), and an optional title. Returns the selected
 * provider/model pair, or undefined when the dialog is cancelled or no models
 * are available.
 */
export async function selectModelFromMenu(
  ui: MenuUi,
  models: { provider: string; id: string; name: string }[],
  currentModel: string | undefined,
  title?: string,
): Promise<{ provider: string; model: string } | undefined> {
  if (models.length === 0) {
    ui.notify("No models are available in the model registry.", "warning");
    return undefined;
  }
  const options = models.map((model) => {
    const current = modelLabel(model) === currentModel ? " · current" : "";
    return `${modelLabel(model)} · ${model.name}${current}`;
  });
  const selected = await ui.select(title ?? "Select a model", options);
  if (!selected) return undefined;
  const model = models[options.indexOf(selected)];
  if (!model) return undefined;
  return { provider: model.provider, model: model.id };
}

// ── Model search ────────────────────────────────────────────────────

/**
 * Searchable text for one model: the provider-prefixed label first, then the
 * display name — mirroring pi's own /model selector ranking where exact
 * provider-prefixed queries rank ahead of bare model ids.
 */
export function modelSearchText(model: { provider: string; id: string; name?: string }): string {
  const label = modelLabel(model);
  return model.name && model.name !== model.id ? `${label} · ${model.name}` : label;
}

/** Pure type-to-filter controller shared by interactive model pickers. The
 * filter callback is injected by the host (typically @earendil-works/pi-tui's
 * fuzzyFilter), keeping this module free of UI dependencies. Typing refilters
 * from the full item list and resets the selection to the best match;
 * navigation clamps within the filtered results. */
export interface SearchPicker<T> {
  /** Current query text. */
  query(): string;
  /** Items matching the current query (the full list when the query is empty). */
  results(): T[];
  /** Selected item, or undefined when no results remain. */
  selected(): T | undefined;
  /** Index of the selection within results(). */
  selectedIndex(): number;
  /** Append typed text; refilters and moves the selection to the top result. */
  type(text: string): void;
  /** Remove the last query character; refilters. */
  backspace(): void;
  /** Clear the query entirely; restores the full list in original order. */
  clear(): void;
  /** Move the selection up; clamps at the first result. */
  up(): void;
  /** Move the selection down; clamps at the last result. */
  down(): void;
}

/** Create a search picker over a fixed item list with an injected filter. */
export function createSearchPicker<T>(
  items: readonly T[],
  options: {
    filter: (items: T[], query: string, getText: (item: T) => string) => T[];
    getText: (item: T) => string;
  },
): SearchPicker<T> {
  let query = "";
  let filtered = [...items];
  let index = 0;
  const refilter = () => {
    filtered = query ? options.filter([...items], query, options.getText) : [...items];
    index = 0;
  };
  return {
    query: () => query,
    results: () => filtered,
    selected: () => filtered[index],
    selectedIndex: () => index,
    type: (text) => {
      query += text;
      refilter();
    },
    backspace: () => {
      if (!query) return;
      query = query.slice(0, -1);
      refilter();
    },
    clear: () => {
      query = "";
      refilter();
    },
    up: () => {
      index = Math.max(0, index - 1);
    },
    down: () => {
      index = Math.max(0, Math.min(filtered.length - 1, index + 1));
    },
  };
}

/** Options for enterModelFromInput. */
export interface EnterModelOptions {
  /** Dialog label shown to the user. */
  label?: string;
  /** Called when the user submits empty input (not on cancel). Default: notify an error. */
  onEmpty?: () => void;
}

/**
 * Interactive model entry via ctx.ui.input. Validates the input as a
 * "provider/model" reference and checks that the model exists in the registry.
 * Returns the parsed provider/model pair, or undefined when the dialog is
 * cancelled, the input is empty, or validation fails. Empty input notifies an
 * error unless an onEmpty handler is provided.
 */
export async function enterModelFromInput(
  ui: InputUi,
  modelRegistry: { find(provider: string, model: string): unknown },
  currentModel: string | undefined,
  options?: EnterModelOptions,
): Promise<{ provider: string; model: string } | undefined> {
  const value = await ui.input(
    options?.label ?? "Model (provider/model format):",
    currentModel ?? "",
  );
  if (value === undefined) return undefined;
  const trimmed = value.trim();
  if (!trimmed) {
    if (options?.onEmpty) {
      options.onEmpty();
    } else {
      ui.notify(
        "Enter a model in provider/model format (e.g. anthropic/claude-3-5-haiku)",
        "error",
      );
    }
    return undefined;
  }
  const ref = parseModelRef(trimmed);
  if (!ref) {
    ui.notify(
      "Enter a model in provider/model format (e.g. anthropic/claude-3-5-haiku)",
      "error",
    );
    return undefined;
  }
  if (!modelRegistry.find(ref.provider, ref.model)) {
    ui.notify(
      `Model ${ref.provider}/${ref.model} was not found in the model registry`,
      "error",
    );
    return undefined;
  }
  return ref;
}