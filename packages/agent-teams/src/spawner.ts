/**
 * Teammate spawner — spawns named resident child Pi processes in RPC mode.
 *
 * A teammate is a long-lived worker: it receives prompts on its control
 * stream (stdin), streams JSON events on stdout, and suspends between wake
 * ups without consuming tokens. The harness delivers new prompts via
 * deliverPrompt (idle wake-up) and steering lines via sendWorkerSteer
 * (mid-turn delivery). Wake-up sequences are uncapped: no turn-count or
 * wall-clock limit terminates a working teammate; anomalies surface as
 * leader notifications instead.
 */

import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import {
  DEFAULT_TERMINATION_GRACE_MS,
  extractTextContent,
  resolvePiCli,
  spawnPiChild,
  terminateChildProcess,
} from "@fradser/pi-kit";
import type { ChildProcess } from "node:child_process";
import type { WorkerUsage } from "./types.ts";

const OUTPUT_CAP = 16_000;

export interface WorkerProcessResult {
  pid: number;
  exitCode: number | null;
  signal: NodeJS.Signals | null;
  stdout: string;
  stderr: string;
  usage?: WorkerUsage;
}

/** Live state extracted from a teammate's RPC output stream. */
export interface WorkerProgressUpdate {
  text: string;
  activeTool?: string;
  liveThinking?: string;
  /** Assistant turns observed in the current wake-up sequence. */
  turns: number;
  /** True after the current sequence's final response. */
  finalResponse?: boolean;
  /** True once the stream delivered recognized model activity (text, thinking,
   *  tool-call, or tool execution events). Independent of usage totals so
   *  providers that omit usage are not misclassified as silent. */
  modelOutputSeen?: boolean;
  /** Lifetime accumulated usage parsed from message_end events. */
  usage?: WorkerUsage;
}

/** A crashed teammate is one that closed without a normal zero exit. */
export function isCleanExit(result: Pick<WorkerProcessResult, "exitCode" | "signal">): boolean {
  return result.exitCode === 0 && result.signal === null;
}

/** Tools every teammate receives regardless of its role definition. */
export const WORKER_CAPABILITY_TOOLS: readonly string[] = [
  "send_message",
  "task_list",
  "task_claim",
  "task_submit",
];

/** Effective tool allowlist for one teammate: the role's requested tools plus
 *  the capability set, deduplicated in request order. Roles without a tools
 *  field get exactly the capability set — leaders should see that narrow
 *  grant before the first wake so missing read/bash is obvious at spawn time. */
export function resolveWorkerTools(requested?: string[]): string[] {
  const requestedOnly = (requested ?? []).filter((tool) => !WORKER_CAPABILITY_TOOLS.includes(tool));
  return [...new Set([...requestedOnly, ...WORKER_CAPABILITY_TOOLS])];
}

// ── Process registry ──────────────────────────────────────────────

/** Live children by teammate name — powers steering, prompting, and shutdown. */
const workers = new Map<string, ChildProcess>();
const closedWorkers = new WeakSet<ChildProcess>();

function observeWorkerClose(name: string, child: ChildProcess): void {
  child.once("close", () => {
    closedWorkers.add(child);
    if (workers.get(name) === child) workers.delete(name);
  });
}

/** True only after Node has emitted the child process close event. */
export function isWorkerCloseObserved(name: string): boolean {
  const child = workers.get(name);
  if (child) return closedWorkers.has(child);
  // Not registered anymore: either never spawned or already unregistered by close.
  return true;
}

export { terminateChildProcess };

/** Terminate a living teammate and wait until its child process has closed. */
export async function terminateTeammate(name: string, graceMs = DEFAULT_TERMINATION_GRACE_MS): Promise<boolean> {
  const child = workers.get(name);
  if (!child) return false;
  return terminateChildProcess(child, graceMs);
}

export async function terminateAllTeammates(graceMs = DEFAULT_TERMINATION_GRACE_MS): Promise<Array<{ name: string; confirmedClosed: boolean }>> {
  const entries = [...workers.entries()];
  return Promise.all(entries.map(async ([name, child]) => ({
    name,
    confirmedClosed: closedWorkers.has(child) || await terminateChildProcess(child, graceMs),
  })));
}

// ── Control stream ────────────────────────────────────────────────

function writeToControlStream(child: ChildProcess, line: unknown): boolean {
  if (!child.stdin || child.stdin.destroyed || !child.stdin.writable) return false;
  child.stdin.write(`${JSON.stringify(line)}\n`);
  return true;
}

/**
 * Deliver a new wake-up prompt to an idle teammate's control stream.
 * This starts a fresh assistant sequence in the child process.
 */
export function deliverPrompt(name: string, message: string): boolean {
  const child = workers.get(name);
  if (!child) return false;
  const sent = writeToControlStream(child, { type: "prompt", id: randomUUID(), message });
  if (sent) beginSequence(name);
  return sent;
}

/** Per-name stream states so prompt delivery can reset sequence boundaries. */
const streamStates = new Map<string, StreamState>();

function beginSequence(name: string): void {
  const state = streamStates.get(name);
  if (state) {
    state.finalResponse = false;
    state.text = "";
    state.thinking = "";
    clearActiveTools(state);
  }
  baselines.set(name, streamTurns.get(name) ?? 0);
}

/** Send a mid-turn steer to a working teammate; no peer mailbox is involved. */
export function sendWorkerSteer(name: string, message: string): boolean {
  const child = workers.get(name);
  return child ? writeToControlStream(child, { type: "steer", message }) : false;
}

// ── Stream parsing ────────────────────────────────────────────────

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

interface StreamState {
  text: string;
  thinking: string;
  toolcallArgs: string;
  activeTool?: string;
  activeTools: Map<string, string>;
  /** Lifetime count of completed assistant messages. */
  turns: number;
  finalResponse?: boolean;
  /** Set by any recognized model/stream activity; never by a bare empty
   *  message_end artifact. The stall classifier uses this, not usage. */
  modelOutputSeen?: boolean;
  usage?: WorkerUsage;
}

function createStreamState(): StreamState {
  return { text: "", thinking: "", toolcallArgs: "", activeTools: new Map(), turns: 0 };
}

function clearActiveTools(state: StreamState): void {
  state.toolcallArgs = "";
  state.activeTool = undefined;
  state.activeTools.clear();
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
    if (typeof command === "string" && command.trim()) return `bash: ${normalizeInline(command)}`;
    const filePath = args.path;
    if (typeof filePath === "string" && filePath.trim()) return `file: ${normalizeInline(path.basename(filePath.trim()))}`;
    const subject = args.subject;
    if (typeof subject === "string" && subject.trim()) return `message: ${normalizeInline(subject)}`;
    const query = args.query;
    if (typeof query === "string" && query.trim()) return `search: ${normalizeInline(query)}`;
    const to = args.to;
    if (typeof to === "string" && to.trim() && typeof args.subject === "string") return `send: ${normalizeInline(args.subject)}`;
  } catch {
    // Incomplete JSON mid-stream — retry on the next delta.
  }
  return undefined;
}

function normalizeInline(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function applyStreamLine(state: StreamState, line: string): boolean {
  if (!line.trim()) return false;
  let event: JsonEvent;
  try {
    event = JSON.parse(line) as JsonEvent;
  } catch {
    return false;
  }
  if (event.type === "tool_execution_start") {
    state.modelOutputSeen = true;
    state.activeTools.set(event.toolCallId ?? `tool-${state.activeTools.size}`, toolExecutionLabel(event.toolName, event.args));
    state.activeTool = [...state.activeTools.values()].at(-1);
    return true;
  }
  if (event.type === "tool_execution_end") {
    state.modelOutputSeen = true;
    if (event.toolCallId) state.activeTools.delete(event.toolCallId);
    else state.activeTools.clear();
    state.activeTool = [...state.activeTools.values()].at(-1);
    return true;
  }
  if (event.type !== "message_update") {
    if (event.type !== "message_end" || event.message?.role !== "assistant") return false;
    state.turns++;
    clearActiveTools(state);
    state.thinking = "";
    if (event.message.stopReason === "stop") state.finalResponse = true;
    const parts = extractTextContent(event.message.content, "");
    if (parts.trim()) state.text = parts;
    const u = event.message.usage;
    // A bare empty message_end (RPC startup artifact) must not count as model
    // output; real content or usage does.
    if (parts.trim() || (u && (u.totalTokens ?? 0) > 0)) state.modelOutputSeen = true;
    if (u) {
      state.usage = {
        input: (state.usage?.input ?? 0) + (u.input ?? 0),
        output: (state.usage?.output ?? 0) + (u.output ?? 0),
        cacheRead: (state.usage?.cacheRead ?? 0) + (u.cacheRead ?? 0),
        cacheWrite: (state.usage?.cacheWrite ?? 0) + (u.cacheWrite ?? 0),
        totalTokens: (state.usage?.totalTokens ?? 0) + (u.totalTokens ?? 0),
        cost: (state.usage?.cost ?? 0) + (u.cost?.total ?? 0),
      };
    }
    return true;
  }
  const sub = event.assistantMessageEvent;
  if (!sub) return false;
  switch (sub.type) {
    case "text_delta":
      state.modelOutputSeen = true;
      state.activeTool = undefined;
      state.text += sub.delta ?? "";
      return true;
    case "thinking_delta":
      state.modelOutputSeen = true;
      state.activeTool = undefined;
      state.thinking += sub.delta ?? "";
      return true;
    case "toolcall_start":
      state.modelOutputSeen = true;
      clearActiveTools(state);
      return true;
    case "toolcall_delta": {
      state.modelOutputSeen = true;
      state.toolcallArgs += sub.delta ?? "";
      const label = toolcallLabel(state.toolcallArgs);
      if (label) state.activeTool = label;
      return true;
    }
    case "toolcall_end":
      state.modelOutputSeen = true;
      // Execution events own the activity label until the result arrives.
      clearActiveTools(state);
      return true;
    default:
      return false;
  }
}

/** Parse the final assistant text and accumulated usage from captured stdout. */
export function parseTeammateOutput(stdout: string): { text: string; usage?: WorkerUsage } {
  const state = createStreamState();
  for (const line of stdout.split("\n")) applyStreamLine(state, line);
  return { text: state.text.trim(), usage: state.usage };
}

function truncate(text: string, cap: number): string {
  if (text.length <= cap) return text;
  return `${text.slice(0, cap)}\n... [truncated ${text.length - cap} chars]`;
}

// ── Resident spawn ────────────────────────────────────────────────

/** Turn-count baseline per teammate at its most recent delivered prompt. */
const baselines = new Map<string, number>();
const streamTurns = new Map<string, number>();

export interface ResidentSpawnOptions {
  /** Teammate name — the registry key for steering, prompting, and shutdown. */
  workerName: string;
  /** Optional kickoff prompt; omit to let the teammate idle immediately. */
  description?: string;
  model?: string;
  /** Execution-tool allowlist; capability tools are always appended. */
  tools?: string[];
  env?: Record<string, string | undefined>;
  cwd?: string;
  onUpdate?: (update: WorkerProgressUpdate) => void;
  onExit: (result: WorkerProcessResult) => void;
  onError?: (error: Error) => void;
}

export interface SpawnedResident {
  pid: number;
}

const WORKER_EXTENSION = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "index.ts");

/**
 * Spawn one resident child Pi process in RPC mode. Returns immediately with
 * the child pid; outcomes arrive via onExit / onError. An empty description
 * spawns an idle teammate that waits for its first delivered prompt.
 */
export function spawnResident(options: ResidentSpawnOptions): SpawnedResident | { error: string } {
  const cli = resolvePiCli();
  const args: string[] = [
    ...cli.args,
    "--mode", "rpc",
    "--no-session",
    "--no-extensions",
    "--extension", WORKER_EXTENSION,
  ];
  if (options.model) args.push("--model", options.model);
  args.push("--tools", resolveWorkerTools(options.tools).join(","));

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

  let child: ChildProcess;
  try {
    child = spawnPiChild(cli.command, args, {
      cwd: options.cwd,
      env: { ...process.env, ...options.env },
      stdio: ["pipe", "pipe", "pipe"],
    });
  } catch (error) {
    cleanupTempDir();
    return { error: error instanceof Error ? error.message : String(error) };
  }
  if (options.description && options.description.trim()) {
    writeToControlStream(child, { type: "prompt", id: randomUUID(), message: options.description });
    baselines.set(options.workerName, 0);
  }
  observeWorkerClose(options.workerName, child);
  workers.set(options.workerName, child);

  const stdoutChunks: string[] = [];
  const stderrChunks: string[] = [];
  const streamState = createStreamState();
  streamStates.set(options.workerName, streamState);
  let stdoutBuffer = "";
  let settled = false;

  const emitProgress = () => options.onUpdate?.({
    text: truncate(streamState.text, OUTPUT_CAP),
    activeTool: streamState.activeTool,
    liveThinking: truncate(streamState.thinking, OUTPUT_CAP),
    turns: Math.max(0, streamState.turns - (baselines.get(options.workerName) ?? 0)),
    finalResponse: streamState.finalResponse,
    modelOutputSeen: streamState.modelOutputSeen,
    usage: streamState.usage,
  });

  child.stdout?.on("data", (chunk: Buffer) => {
    const text = chunk.toString();
    appendCapped(stdoutChunks, text, OUTPUT_CAP * 4);
    stdoutBuffer += text;
    const lines = stdoutBuffer.split("\n");
    stdoutBuffer = lines.pop() ?? "";
    let changed = false;
    for (const line of lines) {
      changed = applyStreamLine(streamState, line) || changed;
    }
    streamTurns.set(options.workerName, streamState.turns);
    if (changed) emitProgress();
  });
  child.stderr?.on("data", (chunk: Buffer) => appendCapped(stderrChunks, chunk.toString(), OUTPUT_CAP * 2));

  child.on("error", (error) => {
    cleanupTempDir();
    settled = true;
    // Keep the registry entry until close is observed so shutdown diagnostics
    // can distinguish an error/exit code from a confirmed close event.
    options.onError?.(error);
  });

  child.on("close", (code, signal) => {
    cleanupTempDir();
    if (workers.get(options.workerName) === child) workers.delete(options.workerName);
    streamStates.delete(options.workerName);
    baselines.delete(options.workerName);
    streamTurns.delete(options.workerName);
    // A spawn failure was already reported via onError (Node fires error then
    // close) — do not double-report through onExit.
    if (settled) return;
    const parsed = parseTeammateOutput(stdoutChunks.join(""));
    options.onExit({
      pid: child.pid ?? 0,
      exitCode: code,
      signal,
      stdout: truncate(parsed.text, OUTPUT_CAP),
      stderr: truncate(stderrChunks.join("").trim(), OUTPUT_CAP),
      usage: parsed.usage,
    });
  });

  return { pid: child.pid ?? 0 };
}

function appendCapped(chunks: string[], chunk: string, cap: number): void {
  chunks.push(chunk);
  let total = chunks.reduce((sum, value) => sum + value.length, 0);
  while (total > cap && chunks.length > 1) {
    total -= chunks.shift()?.length ?? 0;
  }
  if (total > cap && chunks.length === 1) chunks[0] = chunks[0].slice(-cap);
}
