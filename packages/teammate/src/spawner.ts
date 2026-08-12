/**
 * Teammate spawner — spawns real child Pi processes as workers.
 *
 * A teammate becomes "real" by running its assigned task in a fresh,
 * non-interactive Pi CLI process (`--print`), with its own model and tool
 * scope. stdout/stderr are captured and reported back through the callback
 * so the board can record the outcome on the task.
 */

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import type { WorkerUsage } from "./types";

export interface SpawnPiWorkerOptions {
  /** Task description — the actual work the worker executes. */
  description: string;
  /** Optional model pattern for the child (e.g. "anthropic/claude-sonnet-4"). */
  model?: string;
  /** Optional tool allowlist for the child. */
  tools?: string[];
  /** Working directory for the child (defaults to the parent's cwd). */
  cwd?: string;
  /** Abort signal — aborts the child process. */
  signal?: AbortSignal;
  /** Kill the worker after this many milliseconds (undefined = no timeout). */
  timeoutMs?: number;
  /** Output parsing mode. "json" (default) parses usage from JSONL output. */
  mode?: "json" | "text";
  /** Called once with the captured output when the child exits. */
  onExit: (result: { pid: number; exitCode: number; stdout: string; stderr: string; usage?: WorkerUsage; timedOut: boolean }) => void;
  /** Called when the child could not be spawned at all. */
  onError?: (error: Error) => void;
}

export interface SpawnedWorker {
  pid: number;
}

const TASK_ARG_LIMIT = 8000;
const OUTPUT_CAP = 16_000;

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
 * Parse the JSONL output of a `pi --print --mode json` worker run.
 * Returns the final assistant text and the last reported usage.
 */
export function parseWorkerOutput(stdout: string): { text: string; usage?: WorkerUsage } {
  let text = "";
  let usage: WorkerUsage | undefined;
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

export interface PiCliResolution {
  /** Command to execute — either a runtime (node/bun) or a `pi` binary. */
  command: string;
  /** Leading args: the CLI script path when running via a runtime, else empty. */
  args: string[];
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
 * Resolve how to launch a worker Pi process.
 *
 * Resolution order:
 *   1. `process.argv[1]` — the current Pi process entry, verified against the
 *      package manifest (avoids mistaking unrelated scripts for the CLI).
 *   2. The installed `@earendil-works/pi-coding-agent` package's `dist/cli.js`.
 *   3. A `pi` binary on PATH (best effort).
 */
export function resolvePiCli(): PiCliResolution | undefined {
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

/**
 * Spawn a child Pi process that executes the task description in
 * non-interactive mode. Returns immediately with the child pid; the outcome
 * is delivered via `onExit` / `onError`.
 */
export function spawnPiWorker(options: SpawnPiWorkerOptions): SpawnedWorker | { error: string } {
  const cli = resolvePiCli();
  if (!cli) {
    return { error: "Could not resolve the Pi CLI. Set PI_SUBAGENT_PI_BINARY or install @earendil-works/pi-coding-agent." };
  }

  const args: string[] = [...cli.args, "--print", "--mode", "json", "--no-session"];
  if (options.model) args.push("--model", options.model);
  if (options.tools && options.tools.length > 0) args.push("--tools", options.tools.join(","));

  const taskText = `Task: ${options.description}`;
  if (taskText.length > TASK_ARG_LIMIT) {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "teammate-"));
    const taskFile = path.join(tempDir, "task.md");
    fs.writeFileSync(taskFile, taskText, { mode: 0o600 });
    args.push(`@${taskFile}`);
  } else {
    args.push(taskText);
  }

  let child;
  try {
    child = spawn(cli.command, args, {
      cwd: options.cwd,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) };
  }

  const stdoutChunks: string[] = [];
  const stderrChunks: string[] = [];
  let timedOut = false;
  child.stdout.on("data", (chunk: Buffer) => stdoutChunks.push(chunk.toString()));
  child.stderr.on("data", (chunk: Buffer) => stderrChunks.push(chunk.toString()));

  let timer: ReturnType<typeof setTimeout> | undefined;
  if (options.timeoutMs) {
    timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, options.timeoutMs);
    timer.unref?.();
  }

  child.on("error", (error) => {
    if (timer) clearTimeout(timer);
    options.onError?.(error);
  });

  child.on("close", (code) => {
    if (timer) clearTimeout(timer);
    const rawStdout = stdoutChunks.join("");
    const parsed = (options.mode ?? "json") === "json"
      ? parseWorkerOutput(rawStdout)
      : { text: rawStdout.trim(), usage: undefined };
    const stdout = truncate(parsed.text, OUTPUT_CAP);
    const stderr = truncate(stderrChunks.join("").trim(), OUTPUT_CAP);
    options.onExit({ pid: child.pid ?? 0, exitCode: code ?? 0, stdout, stderr, usage: parsed.usage, timedOut });
  });

  if (options.signal) {
    if (options.signal.aborted) child.kill("SIGTERM");
    else options.signal.addEventListener("abort", () => child.kill("SIGTERM"), { once: true });
  }

  return { pid: child.pid ?? 0 };
}
