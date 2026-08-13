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

/**
 * Build the autonomous guardian-loop prompt for a spawned worker.
 *
 * The worker is NOT a one-shot task runner: it processes its assigned task,
 * then keeps watching its mailbox (via the shared state file) and processing
 * new messages until IT decides to close (idle window, explicit stop, or work
 * complete). The parent never polls — it awaits the worker's own exit.
 */
export function buildAutonomousPrompt(opts: {
  name: string;
  role: string;
  taskId?: string;
  taskTitle?: string;
  stateFile: string;
  timeoutSec: number;
}): string {
  const taskLine = opts.taskId
    ? `\nAssigned task: [${opts.taskId}]${opts.taskTitle ? ` ${opts.taskTitle}` : ""}\nWrite your progress and final report into tasks["${opts.taskId}"] (status → completed/failed, result = final report).`
    : "\nNo assigned task — your job is purely to watch and process the mailbox.";

  return `You are a FULLY AUTONOMOUS teammate named "${opts.name}" (role: ${opts.role}) in a pi multi-agent team.

Shared state file (JSON — read and write it): ${opts.stateFile}
Shape: { "teammates": {...}, "mailboxes": { "${opts.name}": [ {id, from, to, subject, body, taskId, timestamp, read} ] }, "tasks": { "<id>": {id, title, assignee, status, result, ...} } }${taskLine}

YOUR AUTONOMOUS LOOP:
1. Work on the assigned task first (if any). Reflect progress in the state file as you go.
2. Keep watching YOUR mailbox: read mailboxes["${opts.name}"] from the state file, then wait between checks (e.g. \`sleep 30\` in bash). Process EVERY unread message (read:false): do the requested work, write your reply into mailboxes[<from>] (use "agent" when from is team-leader/agent), and mark the source message read:true in the file.
3. You may ALSO proactively message the team leader (the user's own window): write an update into mailboxes["agent"] (from: "${opts.name}", subject, body) whenever you finish a meaningful milestone, hit a blocker, or need a decision — e.g. { "from": "${opts.name}", "to": "agent", "subject": "Task done", "body": "...", "timestamp": <ms>, "read": false, "id": "msg_<unique>" }. The leader sees these as "message(s) to you" in the team panel.
4. YOU decide when to close. Close when ANY holds:
   - The assigned task is done AND no new messages arrived for ~2-3 minutes of watching (close sooner if you judge nothing else is coming).
   - You receive an explicit stop/shutdown message.
   - You processed everything and further waiting is pointless.
   When closing: put your final report into tasks["<taskId>"].result (if a task is assigned) and EXIT with a concise final summary as your last message.
4. NEVER run indefinitely: no task + no messages → close after a short idle window (~1-2 minutes). The hard wall-clock cap is ${opts.timeoutSec}s — close well before it.

Technical notes:
- Read the file: \`cat ${opts.stateFile}\` or a python one-liner.
- Update the file ATOMICALLY (write a temp file, then mv it) so concurrent writers never see partial JSON.
- Use bash to sleep between polls. Do NOT modify other teammates' mailboxes or other tasks — only your own mailbox, your replies, and your assigned task.`;
}

export interface SpawnPiWorkerOptions {
  /** Worker identity — used to register the child so the panel can interrupt/stop it. */
  workerName?: string;
  /** Task description — the actual work the worker executes. */
  description: string;
  /** Optional model pattern for the child (e.g. "anthropic/claude-sonnet-4"). */
  model?: string;
  /** Optional tool allowlist for the child. "bash" is appended for autonomous polling. */
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

export interface SpawnWorkerResult {
  ok: boolean;
  /** Present when ok; the child exited (or timed out). */
  result?: { pid: number; exitCode: number; stdout: string; stderr: string; usage?: WorkerUsage; timedOut: boolean };
  /** Present when the child could not be spawned. */
  error?: string;
}

export interface SpawnedWorker {
  pid: number;
}

/** Live workers by teammate name — lets the panel interrupt/stop a running worker. */
const workers = new Map<string, ReturnType<typeof spawn>>();

/**
 * Interrupt (SIGTERM) or stop (SIGKILL) the worker currently running as the
 * named teammate. Returns false when no live worker is registered for it.
 */
export function killWorker(name: string, signal: "SIGTERM" | "SIGKILL" = "SIGTERM"): boolean {
  const child = workers.get(name);
  if (!child || child.exitCode !== null) return false;
  try {
    return child.kill(signal);
  } catch {
    return false;
  }
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
  // Autonomous workers need bash to poll the shared state file (sleep + file
  // reads). Append it when a tool allowlist is configured without it.
  const tools = options.tools?.includes("bash") || !options.tools ? options.tools : [...options.tools, "bash"];
  if (tools && tools.length > 0) args.push("--tools", tools.join(","));

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
  if (options.workerName) workers.set(options.workerName, child);

  const stdoutChunks: string[] = [];
  const stderrChunks: string[] = [];
  let timedOut = false;
  let settled = false;
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
    settled = true;
    if (options.workerName) workers.delete(options.workerName);
    options.onError?.(error);
  });

  child.on("close", (code) => {
    if (timer) clearTimeout(timer);
    // A spawn failure already reported via onError (Node fires error then
    // close) — do not double-report through onExit, which would let a failed
    // spawn look like a successful 0-exit run.
    if (settled) return;
    if (options.workerName) workers.delete(options.workerName);
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

/**
 * Blocking variant: spawns a worker and resolves when the worker EXITS ON ITS
 * OWN (autonomous close, timeout, or spawn failure). Lets the parent await the
 * worker's own decision instead of polling.
 */
export function spawnPiWorkerBlocking(
  options: Omit<SpawnPiWorkerOptions, "onExit" | "onError">,
): Promise<SpawnWorkerResult> {
  return new Promise<SpawnWorkerResult>((resolve) => {
    spawnPiWorker({
      ...options,
      onExit: (result) => resolve({ ok: true, result }),
      onError: (error) => resolve({ ok: false, error: error.message }),
    });
  });
}
