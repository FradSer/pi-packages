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
import { spawn, type ChildProcess } from "node:child_process";

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
  timedOut: boolean;
  exitCode: number;
  stderr: string;
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
  /** Timeout in milliseconds. */
  timeoutMs?: number;
  /** Additional environment variables. */
  env?: Record<string, string | undefined>;
  /** Additional CLI arguments. */
  extraArgs?: string[];
}

/**
 * Resolve how to launch a Pi CLI process.
 *
 * Resolution order:
 *   1. `process.argv[1]` — the current Pi process entry, verified against the
 *      package manifest (avoids mistaking unrelated scripts for the CLI).
 *   2. A `pi` binary on PATH (best effort).
 *
 * Note: This function does not attempt to resolve the pi-coding-agent package
 * directly, as that would create a dependency on pi core. Callers that need
 * package resolution should implement it themselves.
 */
export function resolvePiCli(): PiCliResolution {
  const argv1 = process.argv[1];
  if (argv1 && isPiPackageScript(argv1)) {
    return { command: process.execPath, args: [path.resolve(argv1)] };
  }

  // Fall back to PATH lookup
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
        return typeof pkg.name === "string" && pkg.name.includes("pi");
      }
      dir = path.dirname(dir);
    }
  } catch {
    // Unreadable paths are simply not candidates.
  }
  return false;
}

/**
 * Run a Pi worker child process and return the result.
 *
 * Spawns `pi --print --mode json --no-session` with the given prompt and tools.
 * Parses the JSONL output to extract the final text and usage stats.
 */
export async function runPiWorker(options: RunPiWorkerOptions): Promise<PiWorkerResult> {
  const { prompt, cwd, tools, model, signal, timeoutMs, env, extraArgs } = options;
  const cli = resolvePiCli();

  const args = [...cli.args, "--print", "--mode", "json", "--no-session", "--cwd", cwd];
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
    let timedOut = false;

    const child = spawn(cli.command, args, {
      cwd,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, ...env },
    });

    const timeout = timeoutMs
      ? setTimeout(() => {
          timedOut = true;
          child.kill("SIGTERM");
        }, timeoutMs)
      : null;

    const abortHandler = () => child.kill("SIGTERM");
    signal?.addEventListener("abort", abortHandler, { once: true });

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("close", (code) => {
      if (timeout) clearTimeout(timeout);
      signal?.removeEventListener("abort", abortHandler);

      const { text, usage } = parsePiWorkerOutput(stdout);
      resolve({
        text,
        usage,
        timedOut,
        exitCode: code ?? 1,
        stderr,
      });
    });

    child.on("error", (err) => {
      if (timeout) clearTimeout(timeout);
      signal?.removeEventListener("abort", abortHandler);
      resolve({
        text: "",
        timedOut: false,
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
 * Returns true if the process was terminated, false if it was already dead.
 */
export async function terminateChildProcess(
  child: ChildProcess,
  graceMs = 5000,
): Promise<boolean> {
  if (child.exitCode !== null || child.signalCode !== null) return false;

  const closedAfterTerm = waitForClose(child, graceMs);
  try {
    if (!child.kill("SIGTERM")) {
      void closedAfterTerm;
      return false;
    }
  } catch {
    void closedAfterTerm;
    return false;
  }
  if (await closedAfterTerm) return true;
  if (child.exitCode !== null || child.signalCode !== null) return false;

  const closedAfterKill = waitForClose(child, graceMs);
  try {
    if (!child.kill("SIGKILL")) {
      void closedAfterKill;
      return false;
    }
  } catch {
    void closedAfterKill;
    return false;
  }
  return closedAfterKill;
}

function waitForClose(child: ChildProcess, timeoutMs: number): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    const onClose = () => finish(true);
    const timer = setTimeout(() => finish(false), timeoutMs);
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