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
 * Build the one-task execution prompt for a spawned worker.
 *
 * A worker executes one bounded task run. It reports to the leader throughout
 * the run and then exits; its idle teammate identity may be reused for later
 * current-session work. The parent independently drains the worker outbox.
 */
export function buildAutonomousPrompt(opts: {
  name: string;
  role: string;
  prompt: string;
  taskId?: string;
  stateFile: string;
  outboxFile: string;
  timeoutSec: number;
}): string {
  const taskLine = opts.taskId
    ? `\nAssigned node: [${opts.taskId}]\nUse teammate_report to report progress and the final result (status → completed/failed). Keep the result concise: outcome, files, verification, risks.`
    : "\nNo assigned node — your job is purely to watch and process the mailbox.";

  return `You are a FULLY AUTONOMOUS worker node named "${opts.name}" (agent: ${opts.role}) in a pi multi-agent team run.

=== ROLE PROMPT ===
${opts.prompt}

Shared state snapshot (READ ONLY — leader-owned): ${opts.stateFile}
Your append-only outbox (WRITE ONLY): ${opts.outboxFile}
Snapshot shape: { "runs": { "<runId>": { id, status, concurrency, worktree, nodes: { "<nodeId>": {id, agent, access, paths, status, ...} } } }, "mailboxes": { "<workerKey>": [...] } }${taskLine}

YOUR ONE-NODE RUN:
1. Read the state snapshot for your assigned node and relevant leader messages. MUST NOT write state.json or modify its in-memory shape.
2. Before substantive work, call teammate_message to:"agent" with a concise plan: approach, Paths, likely verification, and any dependency risk. The plan is recorded in the mailbox; it does not interrupt the leader.
3. Work only on the assigned node and recorded Paths. Call teammate_report with a concise in_progress update after material progress. Message agent for a blocker, changed material assumption, scope risk, or need for a decision; these messages remain in the mailbox until the leader reads them.
4. **Direct messaging**: use teammate_message with to:"agent" for plan, blocker, and decision request. Message same-run peers proactively (node id or runId:nodeId) when a handoff, shared assumption, or review finding would help them.
5. Call teammate_report exactly once with completed or failed. Its result must be the final summary: outcome, changed paths, verification, and risks. After the child closes, the parent harness delivers one authoritative terminal result to the main session. Do not wait for future work or claim nodes.
6. The hard wall-clock cap is ${opts.timeoutSec}s — notify agent of a blocker and report failure before it when blocked.

BOUND CAPABILITIES:
- teammate_message sends a leader-validated direct message (best-effort mailbox, no read receipts).
- teammate_inbox reads your own inbox from the snapshot; messages are not acknowledged.
- teammate_report updates only the node bound to this worker process.

Technical notes:
- Use Pi's read tool to inspect the snapshot at ${opts.stateFile}; use a Python one-liner only if the read tool is unavailable.
- Your outbox path is ${opts.outboxFile}; use the bound teammate tools instead of writing it with bash.
- MUST NOT write state.json, rewrite/truncate the outbox, claim nodes, or update another node's task.
- The leader rejects malformed events, events claiming another worker identity, and task updates for nodes other than your own assigned node.`;
}

export interface SpawnPiWorkerOptions {
  /** Worker identity — used to register the child so the panel can interrupt/stop it. */
  workerName?: string;
  /** Task description — the actual work the worker executes. */
  description: string;
  /** Optional model pattern for the child (e.g. "anthropic/claude-sonnet-4"). */
  model?: string;
  /** Optional execution-tool allowlist for the child. Capability tools are always appended. */
  tools?: string[];
  /** Environment additions bound to this worker process. */
  env?: Record<string, string | undefined>;
  /** Working directory for the child (defaults to the parent's cwd). */
  cwd?: string;
  /** Kill the worker after this many milliseconds (undefined = no timeout). */
  timeoutMs?: number;
  /** Output parsing mode. "json" (default) parses usage from JSONL output. */
  mode?: "json" | "text";
  /** Called whenever JSON-mode worker output reveals live model or tool activity. */
  onUpdate?: (update: WorkerProgressUpdate) => void;
  /** Called once with the captured output when the child exits. */
  onExit: (result: WorkerProcessResult) => void;
  /** Called when the child could not be spawned at all. */
  onError?: (error: Error) => void;
}

export interface WorkerProcessResult {
  pid: number;
  exitCode: number | null;
  signal: NodeJS.Signals | null;
  stdout: string;
  stderr: string;
  usage?: WorkerUsage;
  timedOut: boolean;
}

/** Live state extracted from a spawned worker's JSON-mode output. */
export interface WorkerProgressUpdate {
  text: string;
  activeTool?: string;
  turns: number;
  finalResponse?: boolean;
}

/** A worker only succeeds after a normal zero exit; signals are failures. */
export function isSuccessfulWorkerExit(result: Pick<WorkerProcessResult, "exitCode" | "signal" | "timedOut">): boolean {
  return result.exitCode === 0 && result.signal === null && !result.timedOut;
}

/** A reported completion remains successful when the harness then closes it with SIGTERM. */
export function isCompletedWorkerExit(
  result: Pick<WorkerProcessResult, "exitCode" | "signal" | "timedOut">,
  reportedCompleted = false,
): boolean {
  const sigtermExit = result.signal === "SIGTERM" || result.exitCode === 128 + 15;
  return isSuccessfulWorkerExit(result) || (reportedCompleted && sigtermExit && !result.timedOut);
}

export interface SpawnedWorker {
  pid: number;
}

/** Bounded grace period before a cancellation escalates from SIGTERM to SIGKILL. */
const CANCEL_GRACE_MS = 5_000;
/** Give a terminally reported worker a short chance to exit cleanly. */
export const POST_REPORT_GRACE_MS = 10_000;

/**
 * Defers a close finalizer while the leader confirms a cancellation request.
 * A run ID is unique to one child process, so an old close event cannot affect
 * a later task run.
 */
export class CancellationIntents {
  private readonly finalizers = new Map<string, Array<(cancelled: boolean) => void>>();

  begin(runId: string): boolean {
    if (this.finalizers.has(runId)) return false;
    this.finalizers.set(runId, []);
    return true;
  }

  has(runId: string): boolean {
    return this.finalizers.has(runId);
  }

  defer(runId: string, finalize: (cancelled: boolean) => void): boolean {
    const pending = this.finalizers.get(runId);
    if (!pending) return false;
    pending.push(finalize);
    return true;
  }

  resolve(runId: string, cancelled: boolean): boolean {
    const pending = this.finalizers.get(runId);
    if (!pending) return false;
    try {
      for (const finalize of pending) finalize(cancelled);
    } finally {
      this.finalizers.delete(runId);
    }
    return true;
  }
}

/** Live workers by teammate name — lets the panel interrupt/stop a running worker. */
const workers = new Map<string, ReturnType<typeof spawn>>();

function isChildRunning(child: ReturnType<typeof spawn>): boolean {
  return child.exitCode === null && child.signalCode === null;
}

function waitForClose(child: ReturnType<typeof spawn>, timeoutMs: number): Promise<boolean> {
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

/**
 * Request a graceful child shutdown, escalate to SIGKILL when it resists, and
 * resolve only after a bounded wait observes the child `close` event.
 */
export async function terminateChildProcess(child: ReturnType<typeof spawn>, graceMs = CANCEL_GRACE_MS): Promise<boolean> {
  if (!isChildRunning(child)) return false;

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
  if (!isChildRunning(child)) return false;

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

/**
 * Interrupt (SIGTERM) or stop (SIGKILL) the worker currently running as the
 * named teammate. Returns false when no live worker is registered for it.
 */
export function killWorker(name: string, signal: "SIGTERM" | "SIGKILL" = "SIGTERM"): boolean {
  const child = workers.get(name);
  if (!child || !isChildRunning(child)) return false;
  try {
    return child.kill(signal);
  } catch {
    return false;
  }
}

/** Terminate a live worker and wait until its child process has closed. */
export async function terminateWorker(name: string, graceMs = CANCEL_GRACE_MS): Promise<boolean> {
  const child = workers.get(name);
  if (!child) return false;
  return terminateChildProcess(child, graceMs);
}

/** Gracefully end a worker that has already reported a terminal task result. */
export async function finishReportedWorker(name: string, graceMs = POST_REPORT_GRACE_MS): Promise<boolean> {
  return terminateWorker(name, graceMs);
}

/** Stop every live child before the leader discards the current session board. */
export async function terminateAllWorkers(graceMs = CANCEL_GRACE_MS): Promise<void> {
  const children = [...workers.values()];
  await Promise.all(children.map((child) => (isChildRunning(child) ? terminateChildProcess(child, graceMs) : undefined)));
  workers.clear();
}

const TASK_ARG_LIMIT = 8000;
const OUTPUT_CAP = 16_000;

type JsonEvent = {
  type?: string;
  toolName?: string;
  assistantMessageEvent?: {
    type?: string;
    delta?: string;
  };
  message?: {
    role?: string;
    stopReason?: string;
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
  const state = createWorkerStreamState();
  for (const line of stdout.split("\n")) applyWorkerJsonLine(state, line);
  return { text: state.text.trim(), usage: state.usage };
}

interface WorkerStreamState {
  text: string;
  activeTool?: string;
  turns: number;
  finalResponse?: boolean;
  usage?: WorkerUsage;
}

function createWorkerStreamState(): WorkerStreamState {
  return { text: "", turns: 0 };
}

function applyWorkerJsonLine(state: WorkerStreamState, line: string): boolean {
  if (!line.trim()) return false;
  let event: JsonEvent;
  try {
    event = JSON.parse(line) as JsonEvent;
  } catch {
    return false;
  }
  if (event.type === "message_update" && event.assistantMessageEvent?.type === "text_delta") {
    state.text += event.assistantMessageEvent.delta ?? "";
    return true;
  }
  if (event.type === "tool_execution_start") {
    state.activeTool = event.toolName;
    return true;
  }
  if (event.type === "tool_execution_end") {
    state.activeTool = undefined;
    return true;
  }
  if (event.type !== "message_end" || event.message?.role !== "assistant") return false;
  state.turns++;
  if (event.message.stopReason === "stop") state.finalResponse = true;
  const parts = (event.message.content ?? [])
    .filter((part) => part.type === "text" && typeof part.text === "string")
    .map((part) => part.text as string)
    .join("");
  if (parts.trim()) state.text = parts;
  const u = event.message.usage;
  if (u) {
    state.usage = {
      input: u.input ?? 0,
      output: u.output ?? 0,
      cacheRead: u.cacheRead ?? 0,
      cacheWrite: u.cacheWrite ?? 0,
      totalTokens: u.totalTokens ?? 0,
      cost: u.cost?.total ?? 0,
    };
  }
  return true;
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
  // Capability tools cannot be removed; execution tools are selected by the
  // leader from the teammate's explicit configuration or role default.
  const capabilityTools = ["teammate_message", "teammate_inbox", "teammate_report"];
  const requestedTools = (options.tools ?? []).filter((tool) => !tool.startsWith("teammate_"));
  const tools = [...new Set([...requestedTools, ...capabilityTools])];
  args.push("--tools", tools.join(","));

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
      env: { ...process.env, ...options.env },
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) };
  }
  if (options.workerName) workers.set(options.workerName, child);

  const stdoutChunks: string[] = [];
  const stderrChunks: string[] = [];
  const streamState = createWorkerStreamState();
  let stdoutBuffer = "";
  let timedOut = false;
  let settled = false;
  const emitProgress = () => options.onUpdate?.({
    text: truncate(streamState.text, OUTPUT_CAP),
    activeTool: streamState.activeTool,
    turns: streamState.turns,
    finalResponse: streamState.finalResponse,
  });
  child.stdout.on("data", (chunk: Buffer) => {
    const text = chunk.toString();
    stdoutChunks.push(text);
    stdoutBuffer += text;
    const lines = stdoutBuffer.split("\n");
    stdoutBuffer = lines.pop() ?? "";
    let changed = false;
    for (const line of lines) changed = applyWorkerJsonLine(streamState, line) || changed;
    if (changed) emitProgress();
  });
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
    if (options.workerName && workers.get(options.workerName) === child) workers.delete(options.workerName);
    options.onError?.(error);
  });

  child.on("close", (code, signal) => {
    if (timer) clearTimeout(timer);
    // A spawn failure already reported via onError (Node fires error then
    // close) — do not double-report through onExit, which would let a failed
    // spawn look like a successful 0-exit run.
    if (settled) return;
    if (options.workerName && workers.get(options.workerName) === child) workers.delete(options.workerName);
    const rawStdout = stdoutChunks.join("");
    const parsed = (options.mode ?? "json") === "json"
      ? parseWorkerOutput(rawStdout)
      : { text: rawStdout.trim(), usage: undefined };
    const stdout = truncate(parsed.text, OUTPUT_CAP);
    const stderr = truncate(stderrChunks.join("").trim(), OUTPUT_CAP);
    options.onExit({ pid: child.pid ?? 0, exitCode: code, signal, stdout, stderr, usage: parsed.usage, timedOut });
  });

  return { pid: child.pid ?? 0 };
}

