/**
 * Teammate spawner — spawns real child Pi processes as workers.
 *
 * A teammate becomes "real" by running its assigned task in a fresh,
 * non-interactive Pi CLI process (`--print`), with its own model and tool
 * scope. stdout/stderr are captured and reported back through the callback
 * so the board can record the outcome on the task.
 */

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { extractTextContent, resolvePiCli } from "@fradser/pi-kit";
import type { WorkerUsage } from "./types";

/** High default safety cap; explicit task budgets can still be lower. */
export const DEFAULT_TURN_BUDGET = 100;

/**
 * Build the one-task execution prompt for a spawned worker.
 *
 * A worker executes one bounded task run. It reports to the leader throughout
 * the run and then exits. The parent independently drains the worker outbox.
 */
export function buildAutonomousPrompt(opts: {
  name: string;
  role: string;
  prompt: string;
  taskId?: string;
  turnBudget?: number;
}): string {
  const taskLine = `\nAssigned task: [${opts.taskId}].\nWhen finished, you MUST call teammate_message with status="completed" to submit your FULL final deliverable.`;
  const budgetLine = opts.turnBudget
    ? `4. You have a maximum of ${opts.turnBudget} assistant turn(s) — manage your turn budget, avoid unnecessary exploration, and deliver your final message before the budget is exhausted.`
    : `4. There is no turn budget — work until the task is complete. Do not rush or truncate your work.`;

  return `You are a FULLY AUTONOMOUS teammate named "${opts.name}" (agent: ${opts.role}) in a pi multi-agent team run.

=== ROLE PROMPT ===
${opts.prompt}
${taskLine}

YOUR ROLE IN THIS RUN:
1. Work directly on your assigned scope and declared paths. DAG upstream results are ALREADY injected into this prompt below; do not poll for them.
2. Report plans, progress, and blockers with teammate_message. When finished, call teammate_message with status="completed" and put your FULL deliverable in the body. If blocked or failed, use status="failed" and explain the error.
3. There is no peer or leader-to-worker message channel. Make decisions within the assigned task and report blockers instead of waiting for a reply.
${budgetLine}

BOUND CAPABILITIES:
- teammate_message reports progress or a final deliverable to the team leader.`;
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
  /** Maximum assistant turns for this worker (defaults to DEFAULT_TURN_BUDGET). */
  turnBudget?: number;
  /** Output parsing mode. RPC keeps stdin available for runtime steering. */
  mode?: "json" | "rpc" | "text";
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
  turnBudgetExceeded?: boolean;
}

/** Live state extracted from a spawned worker's JSON-mode output. */
export interface WorkerProgressUpdate {
  text: string;
  activeTool?: string;
  liveThinking?: string;
  turns: number;
  finalResponse?: boolean;
}

/** A worker only succeeds after a normal zero exit; signals are failures. */
export function isSuccessfulWorkerExit(result: Pick<WorkerProcessResult, "exitCode" | "signal">): boolean {
  return result.exitCode === 0 && result.signal === null;
}

/** A reported completion remains successful when the harness closes it or teardown observes a signal. */
export function isCompletedWorkerExit(
  result: Pick<WorkerProcessResult, "exitCode" | "signal">,
  reportedCompleted = false,
): boolean {
  return isSuccessfulWorkerExit(result) || reportedCompleted;
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

  begin(spawnId: string): boolean {
    if (this.finalizers.has(spawnId)) return false;
    this.finalizers.set(spawnId, []);
    return true;
  }

  has(spawnId: string): boolean {
    return this.finalizers.has(spawnId);
  }

  defer(spawnId: string, finalize: (cancelled: boolean) => void): boolean {
    const pending = this.finalizers.get(spawnId);
    if (!pending) return false;
    pending.push(finalize);
    return true;
  }

  resolve(spawnId: string, cancelled: boolean): boolean {
    const pending = this.finalizers.get(spawnId);
    if (!pending) return false;
    try {
      for (const finalize of pending) finalize(cancelled);
    } finally {
      this.finalizers.delete(spawnId);
    }
    return true;
  }
}

/** Live workers by teammate name — lets the panel interrupt/stop a running worker. */
const workers = new Map<string, ReturnType<typeof spawn>>();

/** Send a steering message to an RPC worker without adding a peer mailbox. */
export function sendWorkerSteer(name: string, message: string): boolean {
  const child = workers.get(name);
  if (!child?.stdin || child.stdin.destroyed || !child.stdin.writable) return false;
  child.stdin.write(`${JSON.stringify({ type: "steer", message })}\n`);
  return true;
}

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

function appendCapped(chunks: string[], chunk: string, cap: number): void {
  chunks.push(chunk);
  let total = chunks.reduce((sum, value) => sum + value.length, 0);
  while (total > cap && chunks.length > 1) {
    total -= chunks.shift()?.length ?? 0;
  }
  if (total > cap && chunks.length === 1) chunks[0] = chunks[0].slice(-cap);
}

type JsonEvent = {
  type?: string;
  toolCallId?: string;
  toolName?: string;
  args?: unknown;
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

/** Parse the latest live progress state from a worker JSON stream. */
export function parseWorkerProgress(stdout: string): WorkerProgressUpdate {
  const state = createWorkerStreamState();
  for (const line of stdout.split("\n")) applyWorkerJsonLine(state, line);
  return {
    text: truncate(state.text, OUTPUT_CAP),
    activeTool: state.activeTool,
    liveThinking: truncate(state.thinking, OUTPUT_CAP),
    turns: state.turns,
    finalResponse: state.finalResponse,
  };
}

interface WorkerStreamState {
  text: string;
  thinking: string;
  toolcallArgs: string;
  activeTool?: string;
  activeToolCallId?: string;
  activeTools: Map<string, string>;
  turns: number;
  finalResponse?: boolean;
  usage?: WorkerUsage;
}

function createWorkerStreamState(): WorkerStreamState {
  return { text: "", thinking: "", toolcallArgs: "", activeTools: new Map(), turns: 0 };
}

function setActiveTool(state: WorkerStreamState, toolCallId: string | undefined, label: string): void {
  const key = toolCallId ?? `tool-${state.activeTools.size}`;
  state.activeTools.set(key, label);
  state.activeToolCallId = key;
  state.activeTool = label;
}

function clearActiveTool(state: WorkerStreamState, toolCallId: string | undefined): void {
  if (toolCallId) state.activeTools.delete(toolCallId);
  else state.activeTools.clear();
  const next = [...state.activeTools.entries()].at(-1);
  state.activeToolCallId = next?.[0];
  state.activeTool = next?.[1];
}

function toolExecutionLabel(toolName: string | undefined, args: unknown): string {
  const serialized = typeof args === "string" ? args : JSON.stringify(args ?? {});
  return toolcallLabel(serialized) ?? toolName ?? "tool";
}

/** Human-readable label from a partially streamed tool-call argument JSON. */
function toolcallLabel(rawArgs: string): string | undefined {
  const trimmed = rawArgs.trim();
  if (!trimmed.startsWith("{")) return undefined;
  try {
    const args = JSON.parse(trimmed) as Record<string, unknown>;
    const command = args.command;
    if (typeof command === "string" && command.trim()) return `bash: ${truncateInline(command, 40)}`;
    const filePath = args.path;
    if (typeof filePath === "string" && filePath.trim()) return `file: ${path.basename(filePath.trim())}`;
    const subject = args.subject;
    if (typeof subject === "string" && subject.trim()) return `message: ${truncateInline(subject, 40)}`;
    const query = args.query;
    if (typeof query === "string" && query.trim()) return `search: ${truncateInline(query, 40)}`;
  } catch {
    // Incomplete JSON mid-stream — retry on the next delta.
  }
  return undefined;
}

function applyWorkerJsonLine(state: WorkerStreamState, line: string): boolean {
  if (!line.trim()) return false;
  let event: JsonEvent;
  try {
    event = JSON.parse(line) as JsonEvent;
  } catch {
    return false;
  }
  if (event.type === "message_start" && event.message?.role === "assistant") {
    state.thinking = "";
    state.activeTool = undefined;
    state.activeToolCallId = undefined;
    state.activeTools.clear();
    return true;
  }
  if (event.type === "tool_execution_start") {
    setActiveTool(state, event.toolCallId, toolExecutionLabel(event.toolName, event.args));
    return true;
  }
  if (event.type === "tool_execution_end") {
    if (!event.toolCallId || state.activeTools.has(event.toolCallId)) {
      clearActiveTool(state, event.toolCallId);
      return true;
    }
    return false;
  }
  if (event.type !== "message_update") {
    if (event.type !== "message_end" || event.message?.role !== "assistant") return false;
    state.turns++;
    state.activeTool = undefined;
    state.activeToolCallId = undefined;
    state.activeTools.clear();
    state.thinking = "";
    if (event.message.stopReason === "stop") state.finalResponse = true;
    const parts = extractTextContent(event.message.content, "");
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
  const sub = event.assistantMessageEvent;
  if (!sub) return false;
  switch (sub.type) {
    case "text_delta":
      state.activeTool = undefined;
      state.text += sub.delta ?? "";
      return true;
    case "thinking_delta":
      state.activeTool = undefined;
      state.thinking += sub.delta ?? "";
      return true;
    case "toolcall_start":
      state.toolcallArgs = "";
      state.activeTool = undefined;
      state.activeToolCallId = undefined;
      state.activeTools.clear();
      return true;
    case "toolcall_delta": {
      state.toolcallArgs += sub.delta ?? "";
      const label = toolcallLabel(state.toolcallArgs);
      if (label) state.activeTool = label;
      return true;
    }
    case "toolcall_end":
      // The tool call has been emitted; execution events now own the current
      // activity label until the tool result arrives.
      state.toolcallArgs = "";
      state.activeTool = undefined;
      state.activeToolCallId = undefined;
      state.activeTools.clear();
      return true;
    default:
      return false;
  }
}

function truncateInline(text: string, cap: number): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  if (oneLine.length <= cap) return oneLine;
  return `${oneLine.slice(0, cap).trimEnd()} ...`;
}

function truncate(text: string, cap: number): string {
  if (text.length <= cap) return text;
  return `${text.slice(0, cap)}\n... [truncated ${text.length - cap} chars]`;
}

/**
 * Resolve how to launch a Pi CLI process.
 * Re-exported from pi-kit for backward compatibility.
 */
export { resolvePiCli } from "@fradser/pi-kit";

/**
 * Spawn a child Pi process that executes the task description in
 * non-interactive mode. Returns immediately with the child pid; the outcome
 * is delivered via `onExit` / `onError`.
 */
export function spawnPiWorker(options: SpawnPiWorkerOptions): SpawnedWorker | { error: string } {
  // resolvePiCli always resolves (worst case a "pi" binary on PATH); a missing
  // binary surfaces later as a child "error" event through onError.
  const cli = resolvePiCli();
  const workerExtension = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "index.ts");
  const mode = options.mode ?? "json";
  const args: string[] = [
    ...cli.args,
    ...(mode === "rpc" ? ["--mode", "rpc"] : ["--print", "--mode", mode]),
    "--no-session",
    "--no-extensions",
    "--extension",
    workerExtension,
  ];
  if (options.model) args.push("--model", options.model);
  // Capability tools cannot be removed; execution tools are selected by the
  // leader from the teammate's explicit configuration or role default.
  const capabilityTools = ["teammate_message"];
  const requestedTools = (options.tools ?? []).filter((tool) => !tool.startsWith("teammate_"));
  const tools = [...new Set([...requestedTools, ...capabilityTools])];
  args.push("--tools", tools.join(","));

  let tempDir: string | undefined;
  const cleanupTempDir = () => {
    if (!tempDir) return;
    try {
      fs.rmSync(tempDir, { recursive: true, force: true });
    } catch {
      // Temporary cleanup must not mask the worker outcome.
    } finally {
      tempDir = undefined;
    }
  };
  const setupError = (error: unknown): { error: string } => ({
    error: error instanceof Error ? error.message : String(error),
  });

  let taskText = `Task: ${options.description}`;
  try {
    if (mode !== "rpc" && taskText.length > TASK_ARG_LIMIT) {
      tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "teammate-"));
      const taskFile = path.join(tempDir, "task.md");
      fs.writeFileSync(taskFile, taskText, { mode: 0o600 });
      args.push(`@${taskFile}`);
    } else if (mode !== "rpc") {
      args.push(taskText);
    }
  } catch (error) {
    cleanupTempDir();
    return setupError(error);
  }

  let child;
  try {
    child = spawn(cli.command, args, {
      cwd: options.cwd,
      env: { ...process.env, ...options.env },
      stdio: [mode === "rpc" ? "pipe" : "ignore", "pipe", "pipe"],
    });
  } catch (error) {
    cleanupTempDir();
    return setupError(error);
  }
  if (options.workerName) workers.set(options.workerName, child);

  if (mode === "rpc") {
    child.stdin?.write(`${JSON.stringify({ type: "prompt", id: randomUUID(), message: taskText })}\n`);
  }

  const stdoutChunks: string[] = [];
  const stderrChunks: string[] = [];
  const streamState = createWorkerStreamState();
  let stdoutBuffer = "";
  let settled = false;
  let turnBudgetExceeded = false;
  const emitProgress = () => options.onUpdate?.({
    text: truncate(streamState.text, OUTPUT_CAP),
    activeTool: streamState.activeTool,
    liveThinking: truncate(streamState.thinking, OUTPUT_CAP),
    turns: streamState.turns,
    finalResponse: streamState.finalResponse,
  });
  child.stdout?.on("data", (chunk: Buffer) => {
    const text = chunk.toString();
    appendCapped(stdoutChunks, text, OUTPUT_CAP * 2);
    stdoutBuffer += text;
    const lines = stdoutBuffer.split("\n");
    stdoutBuffer = lines.pop() ?? "";
    let changed = false;
    for (const line of lines) {
      changed = applyWorkerJsonLine(streamState, line) || changed;
      if (options.turnBudget && streamState.turns >= options.turnBudget && !streamState.finalResponse && !turnBudgetExceeded) {
        turnBudgetExceeded = true;
        void terminateChildProcess(child);
      }
    }
    if (changed) emitProgress();
  });
  child.stderr?.on("data", (chunk: Buffer) => appendCapped(stderrChunks, chunk.toString(), OUTPUT_CAP * 2));

  child.on("error", (error) => {
    cleanupTempDir();
    settled = true;
    if (options.workerName && workers.get(options.workerName) === child) workers.delete(options.workerName);
    options.onError?.(error);
  });

  child.on("close", (code, signal) => {
    cleanupTempDir();
    // A spawn failure already reported via onError (Node fires error then
    // close) — do not double-report through onExit, which would let a failed
    // spawn look like a successful 0-exit run.
    if (settled) return;
    if (options.workerName && workers.get(options.workerName) === child) workers.delete(options.workerName);
    const rawStdout = stdoutChunks.join("");
    const parsed = mode === "text"
      ? { text: rawStdout.trim(), usage: undefined }
      : parseWorkerOutput(rawStdout);
    const stdout = truncate(parsed.text, OUTPUT_CAP);
    const stderr = truncate(stderrChunks.join("").trim(), OUTPUT_CAP);
    options.onExit({ pid: child.pid ?? 0, exitCode: code, signal, stdout, stderr, usage: parsed.usage, turnBudgetExceeded });
  });

  return { pid: child.pid ?? 0 };
}

