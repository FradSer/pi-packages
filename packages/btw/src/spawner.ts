/**
 * btw spawner — runs a side question in a fresh, read-only child Pi process.
 *
 * The child runs with `--no-session`, so the side exchange never enters the
 * main session history. It is restricted to a strict tool allowlist
 * (read, grep, find, ls): it can verify facts in the codebase, but can
 * never modify, create, or delete anything. `bash`, `edit`, and `write`
 * are explicitly excluded.
 */

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

/** Read-only builtin tools the side question may use. */
export const READ_ONLY_TOOLS = ["read", "grep", "find", "ls"];

/** Writable / executable tools that are always excluded. */
export const EXCLUDED_TOOLS = ["bash", "edit", "write"];

const PROMPT_ARG_LIMIT = 8000;
const OUTPUT_CAP = 16_000;
export const DEFAULT_TIMEOUT_MS = 180_000;

export interface BtwUsage {
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
  totalTokens: number;
  cost: number;
}

export interface BtwResult {
  text: string;
  usage?: BtwUsage;
  timedOut: boolean;
  exitCode: number;
  stderr: string;
}

export interface RunBtwOptions {
  /** The side question asked by the user. */
  question: string;
  /** Read-only excerpt of recent session conversation. */
  context: string;
  /** Working directory for the child (the current session cwd). */
  cwd: string;
  /** Model pattern (e.g. "anthropic/claude-sonnet-4-5"). Defaults to the child's configured model. */
  model?: string;
  /** Abort signal — aborts the child process. */
  signal?: AbortSignal;
  /** Kill the child after this many milliseconds (default: 180s). */
  timeoutMs?: number;
}

type JsonEvent = {
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

/**
 * Parse the JSONL output of a `pi --print --mode json` side run.
 * Returns the final assistant text and the last reported usage.
 */
export function parseBtwOutput(stdout: string): { text: string; usage?: BtwUsage } {
  let text = "";
  let usage: BtwUsage | undefined;
  for (const line of stdout.split("\n")) {
    if (!line.trim()) continue;
    let event: JsonEvent;
    try {
      event = JSON.parse(line) as JsonEvent;
    } catch {
      continue;
    }
    if (event.type !== "message_end" || event.message?.role !== "assistant") continue;
    const parts = (event.message.content ?? [])
      .filter((part) => part.type === "text" && typeof part.text === "string")
      .map((part) => part.text as string)
      .join("");
    if (parts.trim()) text = parts;
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
  return { text: text.trim(), usage };
}

function truncate(text: string, cap: number): string {
  if (text.length <= cap) return text;
  return `${text.slice(0, cap)}\n... [truncated ${text.length - cap} chars]`;
}

/** Whether a file is the pi coding-agent CLI script (verified against its package manifest). */
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

/**
 * Resolve how to launch the side-question Pi process.
 *
 * Resolution order:
 *   1. `process.argv[1]` — the current Pi process entry, verified against the
 *      package manifest (avoids mistaking unrelated scripts for the CLI).
 *   2. The installed `@earendil-works/pi-coding-agent` package's `dist/cli.js`.
 *   3. A `pi` binary on PATH (best effort).
 */
export function resolvePiCli(): { command: string; args: string[] } | undefined {
  const argv1 = process.argv[1];
  if (argv1 && isPiPackageScript(argv1)) {
    return { command: process.execPath, args: [path.resolve(argv1)] };
  }

  try {
    const entry = fileURLToPath(import.meta.resolve("@earendil-works/pi-coding-agent"));
    const packageRoot = path.dirname(path.dirname(entry));
    const cliPath = path.join(packageRoot, "dist", "cli.js");
    if (fs.existsSync(cliPath)) {
      return { command: process.execPath, args: [cliPath] };
    }
  } catch {
    // Package resolution is best-effort; fall through to PATH.
  }

  return { command: "pi", args: [] };
}

/** Compose the prompt for the side-question child: instructions + context + question. */
export function buildBtwPrompt(question: string, context: string): string {
  const lines = [
    'You are answering a quick side question ("btw") about the current coding session.',
    "You have read-only tools (read, grep, find, ls). Use them to verify facts in the codebase when helpful.",
    "You must NOT modify, create, or delete any files.",
    "Answer concisely and directly.",
  ];
  if (context.trim()) {
    lines.push("", "=== Recent session context (read-only excerpt) ===", context);
  }
  lines.push("", "=== Side question ===", question);
  return lines.join("\n");
}

/**
 * Run a side question in a child Pi process.
 *
 * The child exits when done; the resolved BtwResult carries the final
 * assistant text plus token/cost usage from the JSONL event stream.
 */
export function runBtw(options: RunBtwOptions): Promise<BtwResult> {
  return new Promise<BtwResult>((resolve) => {
    const cli = resolvePiCli();
    if (!cli) {
      resolve({
        text: "",
        timedOut: false,
        exitCode: 1,
        stderr: "Could not resolve the Pi CLI. Install @earendil-works/pi-coding-agent.",
      });
      return;
    }

    const args: string[] = [
      ...cli.args,
      "--print",
      "--mode",
      "json",
      "--no-session",
      "--tools",
      READ_ONLY_TOOLS.join(","),
      "--exclude-tools",
      EXCLUDED_TOOLS.join(","),
    ];
    if (options.model) args.push("--model", options.model);

    let promptDirectory: string | undefined;
    const cleanupPrompt = () => {
      if (!promptDirectory) return;
      try {
        fs.rmSync(promptDirectory, { recursive: true, force: true });
      } catch {
        // Cleanup must not hide the child process result.
      }
      promptDirectory = undefined;
    };

    try {
      const prompt = buildBtwPrompt(options.question, options.context);
      if (prompt.length > PROMPT_ARG_LIMIT) {
        promptDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "btw-"));
        const promptFile = path.join(promptDirectory, "question.md");
        fs.writeFileSync(promptFile, prompt, { mode: 0o600 });
        args.push(`@${promptFile}`);
      } else {
        args.push(prompt);
      }
    } catch (error) {
      cleanupPrompt();
      resolve({
        text: "",
        timedOut: false,
        exitCode: 1,
        stderr: error instanceof Error ? error.message : String(error),
      });
      return;
    }

    let child;
    try {
      child = spawn(cli.command, args, {
        cwd: options.cwd,
        env: process.env,
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (error) {
      cleanupPrompt();
      resolve({
        text: "",
        timedOut: false,
        exitCode: 1,
        stderr: error instanceof Error ? error.message : String(error),
      });
      return;
    }

    const stdoutChunks: string[] = [];
    const stderrChunks: string[] = [];
    let timedOut = false;
    let settled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const settle = (result: BtwResult) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      cleanupPrompt();
      resolve(result);
    };

    child.stdout?.on("data", (chunk: Buffer) => stdoutChunks.push(chunk.toString()));
    child.stderr?.on("data", (chunk: Buffer) => stderrChunks.push(chunk.toString()));
    child.on("error", (error) => {
      settle({
        text: "",
        timedOut,
        exitCode: 1,
        stderr: error instanceof Error ? error.message : String(error),
      });
    });
    child.on("close", (code) => {
      const parsed = parseBtwOutput(stdoutChunks.join(""));
      settle({
        text: truncate(parsed.text, OUTPUT_CAP),
        usage: parsed.usage,
        timedOut,
        exitCode: code ?? 0,
        stderr: truncate(stderrChunks.join("").trim(), OUTPUT_CAP),
      });
    });

    const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, timeoutMs);
    timer.unref?.();

    if (options.signal) {
      if (options.signal.aborted) child.kill("SIGTERM");
      else options.signal.addEventListener("abort", () => child.kill("SIGTERM"), { once: true });
    }
  });
}
