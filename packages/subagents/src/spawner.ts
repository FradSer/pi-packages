/**
 * Agent spawner — spawns named resident child Pi processes in RPC mode.
 *
 * An Agent is a long-lived process: it receives prompts on its control
 * stream (stdin), streams JSON events on stdout, and suspends between wake
 * ups without consuming tokens. The harness delivers new prompts via
 * deliverPrompt (idle wake-up) and steering lines via sendAgentSteer
 * (mid-turn delivery). Wake-up sequences are uncapped: no turn-count or
 * wall-clock limit terminates a working agent; anomalies surface as
 * leader notifications instead.
 */

import { randomUUID } from "node:crypto";
import { StringDecoder } from "node:string_decoder";
import { AGENT_BUILTIN_TOOLS } from "./agent-tools.ts";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  classifyToolActivity,
  DEFAULT_TERMINATION_GRACE_MS,
  extractTextContent,
  inlineToolActivity,
  resolvePiCli,
  spawnPiChild,
  terminateChildProcess,
} from "@fradser/pi-kit";
import type { ChildProcess } from "node:child_process";
import { diagnosticOf, resolveChildEnv, type ChildEnvDiagnostic } from "./child-env.ts";
import type { AgentUsage } from "./types.ts";
import { createForkContextCommand, FORK_CONTEXT_EXTENSION_PATH, parseForkContextAck, writeWorkContext, type ForkContextCommand } from "./work-context.ts";
import { assertPrivateSessionFiles } from "./workspace.ts";
import { boundedFinalDiagnostic, normalizeFinalStopReason } from "./session-result.ts";
import type { SessionContext } from "@earendil-works/pi-coding-agent";
import { PARENT_MESSAGE_TOOL_NAME, parseParentMessageResult, type ParentMessagePayload } from "./parent-message.ts";

const OUTPUT_CAP = 16_000;
/** A single JSONL record and an unterminated record may not exceed this many bytes. */
export const MAX_JSONL_LINE_BYTES = 8 * 1024 * 1024;
/** Live text, thinking, or tool arguments are bounded per assistant message. */
export const MAX_TURN_OUTPUT_BYTES = 16 * 1024 * 1024;
/** Diagnostic tail only; this is not a resident-process lifetime quota. */
const DIAGNOSTIC_TAIL_BYTES = 64 * 1024;

export interface AgentProcessResult {
  pid: number;
  exitCode: number | null;
  signal: NodeJS.Signals | null;
  stdout: string;
  stderr: string;
  usage?: AgentUsage;
}

/** Live state extracted from an agent's RPC output stream. */
export interface AgentProgressUpdate {
  text: string;
  activeTool?: string;
  liveThinking?: string;
  /** Assistant turns observed in the current wake-up sequence. */
  turns: number;
  /** True after the current sequence's final response. */
  finalResponse?: boolean;
  /** The settled sequence includes an authoritative completed assistant message. */
  answerComplete?: boolean;
  /** Final-message evidence; retained only for the current native sequence. */
  stopReason?: string;
  errorMessage?: string;
  hasToolCalls?: boolean;
  /** True only when a real started sequence settled without message_end. */
  missingFinal?: boolean;
  /** True once the stream delivered recognized model activity (text, thinking,
   *  tool-call, or tool execution events). Independent of usage totals so
   *  providers that omit usage are not misclassified as silent. */
  modelOutputSeen?: boolean;
  /** A prompt-less child acknowledged native startup readiness. */
  ready?: boolean;
  /** Lifetime accumulated usage parsed from message_end events. */
  usage?: AgentUsage;
  controlError?: string;
}

/** A crashed agent is one that closed without a normal zero exit. */
export function isCleanExit(result: Pick<AgentProcessResult, "exitCode" | "signal">): boolean {
  return result.exitCode === 0 && result.signal === null;
}

/** Pi built-in tool ids a bare agent process registers. The child runs
 *  --no-extensions, so this list plus the capability tools contributed by the
 *  loaded Agent extensions is the complete grantable universe; anything else is
 *  silently dropped by the child's --tools allowlist filter.
 *  Canonical IDs are shared with public schema and guidance in agent-tools.ts. */

/** Effective tool allowlist for one agent: the role's requested tools plus
 *  the capability tools contributed by the Agent extensions this spawn loads,
 *  deduplicated in request order. Roles without a tools field get exactly the
 *  capability set — leaders should see that narrow grant before the first wake
 *  so missing read/bash is obvious at spawn time.
 *
 *  `capabilityTools` is required and has no default: a spawner that assumed a
 *  coordination pair would advertise tools belonging to whichever package
 *  happens to register them, and a consumer loading only its own Agent
 *  extension would grant ids nothing implements. */
export function resolveAgentTools(requested: string[] | undefined, capabilityTools: readonly string[]): string[] {
  const capabilities = [...capabilityTools];
  const requestedOnly = (requested ?? []).filter((tool) => !capabilities.includes(tool));
  return [...new Set([...requestedOnly, ...capabilities])];
}

/** Every tool id an agent can actually receive: pi built-ins plus the
 *  capability tools contributed by the loaded Agent extensions. */
export function agentToolUniverse(capabilityTools: readonly string[]): readonly string[] {
  return [...AGENT_BUILTIN_TOOLS, ...capabilityTools];
}

/** Requested tool ids outside the agent universe — exactly the ones the
 *  child's --tools allowlist would silently drop. */
export function unknownAgentTools(requested: string[] | undefined, capabilityTools: readonly string[]): string[] {
  const universe = agentToolUniverse(capabilityTools);
  return [...new Set((requested ?? []).filter((tool) => !universe.includes(tool)))];
}

/** Spawn failure for a requested tool id outside the child's universe.
 *
 *  Owned here beside `unknownAgentTools` because both spawn paths need it: a
 *  receipt that names a grant the child's own allowlist filter will drop is a
 *  receipt about a child nobody launched. The message names the id, the
 *  universe, and the one place that work can be done, because "unknown tool" on
 *  its own sends the caller looking for a typo that is not there. */
export function unknownAgentToolsError(unknown: readonly string[], capabilityTools: readonly string[] = []): string {
  return [
    `Unknown tool id${unknown.length === 1 ? "" : "s"} for a child: ${unknown.join(", ")}.`,
    "A child runs a bare pi process (--no-extensions), so only pi built-in tools plus the capability tools an Agent extension registers can be granted.",
    `Valid ids: ${agentToolUniverse(capabilityTools).join(", ")}.`,
    "MCP or project-extension tools cannot reach a child; perform that work in the leader session instead.",
  ].join(" ");
}

// ── Process registry ──────────────────────────────────────────────

/** Live children by agent name — powers steering, prompting, and shutdown. */
const PROCESS_STATE_KEY = Symbol.for("fradser.pi-subagents.process-state");
interface SharedProcessState {
  processes: Map<string, ChildProcess>;
  closed: WeakSet<ChildProcess>;
  controls: Map<string, PendingControlResponse>;
  fresh: Map<string, PendingFreshAssignment>;
  streams: Map<string, StreamState>;
  baselines: Map<string, number>;
  turns: Map<string, number>;
  readiness: Map<string, { child: ChildProcess; promise: Promise<boolean> }>;
}
const processCarrier = globalThis as { [PROCESS_STATE_KEY]?: SharedProcessState };
const shared = processCarrier[PROCESS_STATE_KEY] ?? (processCarrier[PROCESS_STATE_KEY] = {
  processes: new Map(), closed: new WeakSet(), controls: new Map(), fresh: new Map(),
  streams: new Map(), baselines: new Map(), turns: new Map(), readiness: new Map(),
});
const processes = shared.processes;
const closedProcesses = shared.closed;

function observeProcessClose(name: string, child: ChildProcess): void {
  child.once("close", () => {
    closedProcesses.add(child);
    if (processes.get(name) === child) processes.delete(name);
  });
}

/** True only after Node has emitted the child process close event. */
export function isProcessCloseObserved(name: string): boolean {
  const child = processes.get(name);
  if (child) return closedProcesses.has(child);
  // Not registered anymore: either never spawned or already unregistered by close.
  return true;
}

export { terminateChildProcess };

/** Terminate a living agent and wait until its child process has closed. */
export type AgentTermination = { outcome: "missing" } | { outcome: "closed" } | { outcome: "unconfirmed" };

export async function terminateAgent(name: string, graceMs = DEFAULT_TERMINATION_GRACE_MS): Promise<AgentTermination> {
  const child = processes.get(name);
  if (!child) return { outcome: "missing" };
  const closed = closedProcesses.has(child) || await terminateChildProcess(child, graceMs);
  return { outcome: closed ? "closed" : "unconfirmed" };
}

export async function terminateAllAgents(graceMs = DEFAULT_TERMINATION_GRACE_MS): Promise<Array<{ name: string; confirmedClosed: boolean }>> {
  const entries = [...processes.entries()];
  return Promise.all(entries.map(async ([name, child]) => ({
    name,
    confirmedClosed: closedProcesses.has(child) || await terminateChildProcess(child, graceMs),
  })));
}

// ── Control stream ────────────────────────────────────────────────

interface PendingControlResponse {
  child: ChildProcess;
  command: string;
  timeout: ReturnType<typeof setTimeout>;
  resolve: (success: boolean) => void;
}

type PendingFreshDelivery = {
  message: string;
  streamingBehavior: "steer" | "followUp";
};

interface PendingFreshAssignment {
  child: ChildProcess;
  message: string;
  resetId?: string;
  queued: PendingFreshDelivery[];
  resolve: (success: boolean) => void;
}

const CONTROL_RESPONSE_TIMEOUT_MS = 5_000;
// The first RPC reply includes loading Pi and its explicit extensions. Once the
// child is running, ordinary input controls retain their shorter deadline.
const STARTUP_RESPONSE_TIMEOUT_MS = 30_000;
const pendingControlResponses = shared.controls;
const pendingFreshAssignments = shared.fresh;

function writeToControlStream(child: ChildProcess, line: unknown): boolean {
  if (!child.stdin || child.stdin.destroyed || !child.stdin.writable) return false;
  try { child.stdin.write(`${JSON.stringify(line)}\n`); return true; }
  catch { return false; }
}

/**
 * Deliver a new wake-up prompt to an idle agent's control stream.
 * This starts a fresh assistant sequence in the child process.
 */
export function deliverPrompt(name: string, message: string): boolean {
  const child = processes.get(name);
  if (!child) return false;
  const sent = writeToControlStream(child, { type: "prompt", id: randomUUID(), message, streamingBehavior: "followUp" });
  if (sent) beginSequence(name);
  return sent;
}

/** Reuse the prompt-less native startup handshake; no extra control request. */
export function waitForResidentReady(name: string): Promise<boolean> {
  const ready = shared.readiness.get(name);
  return ready && processes.get(name) === ready.child ? ready.promise : Promise.resolve(false);
}

/** A writable pipe is not proof Pi accepted input. Correlate its RPC response. */
export function deliverResidentPrompt(name: string, message: string): Promise<boolean> {
  return deliverAcknowledgedResidentInput(name, message, "followUp", true);
}

/** Public mid-turn steering retains the existing stream/turn baseline and
 * reports only native correlated acceptance, not a successful pipe write. */
export function deliverResidentSteer(name: string, message: string): Promise<boolean> {
  return deliverAcknowledgedResidentInput(name, message, "steer", false);
}

function deliverAcknowledgedResidentInput(
  name: string, message: string, streamingBehavior: "followUp" | "steer", newSequence: boolean,
  timeoutMs = CONTROL_RESPONSE_TIMEOUT_MS,
): Promise<boolean> {
  const child = processes.get(name);
  if (!child || !child.stdin?.writable || child.stdin.destroyed) return Promise.resolve(false);
  const id = randomUUID();
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      pendingControlResponses.delete(id);
      reject(new Error("Prompt acknowledgement timed out; execution may already have started. Inspect or stop before retrying."));
    }, timeoutMs);
    pendingControlResponses.set(id, { child, command: "prompt", timeout, resolve });
    // Arm the sequence before writing: a response and answer can arrive in write().
    if (newSequence) beginSequence(name);
    if (!writeToControlStream(child, { type: "prompt", id, message, streamingBehavior })) {
      clearTimeout(timeout);
      pendingControlResponses.delete(id);
      resolve(false);
    }
  });
}

/** Per-name stream states so prompt delivery can reset sequence boundaries. */
const streamStates = shared.streams;

function beginSequence(name: string): void {
  const state = streamStates.get(name);
  if (state) {
    state.finalResponse = false;
    state.text = "";
    state.thinking = "";
    clearActiveTools(state);
    state.turnBytes = 0;
    state.outputLimitError = undefined;
    state.answerComplete = false;
    state.stopReason = undefined;
    state.errorMessage = undefined;
    state.hasToolCalls = undefined;
    state.sequenceStarted = true;
  }
  baselines.set(name, streamTurns.get(name) ?? 0);
}

function sendOrQueueDuringFreshReset(
  name: string,
  message: string,
  streamingBehavior: PendingFreshDelivery["streamingBehavior"],
): boolean {
  const child = processes.get(name);
  if (!child) return false;
  const pending = pendingFreshAssignments.get(name);
  if (pending?.child === child) {
    pending.queued.push({ message, streamingBehavior });
    return true;
  }
  return writeToControlStream(child, { type: "prompt", id: randomUUID(), message, streamingBehavior });
}

/** Send a mid-turn steer to a working agent; no peer mailbox is involved. */
export function sendAgentSteer(name: string, message: string): boolean {
  return sendOrQueueDuringFreshReset(name, message, "steer");
}

/** Peer traffic yields to leader steering without depending on roster freshness. */
export function sendAgentFollowUp(name: string, message: string): boolean {
  return sendOrQueueDuringFreshReset(name, message, "followUp");
}

function settleFreshAssignment(name: string, success: boolean): void {
  const pending = pendingFreshAssignments.get(name);
  if (!pending) return;
  pendingFreshAssignments.delete(name);
  if (pending.resetId) {
    const control = pendingControlResponses.get(pending.resetId);
    if (control) clearTimeout(control.timeout);
    pendingControlResponses.delete(pending.resetId);
  }
  pending.resolve(success);
}

function deliverFreshPrompts(name: string, pending: PendingFreshAssignment): boolean {
  if (!writeToControlStream(pending.child, {
    type: "prompt",
    id: randomUUID(),
    message: pending.message,
    streamingBehavior: "followUp",
  })) return false;
  beginSequence(name);
  for (const delivery of pending.queued) {
    if (!writeToControlStream(pending.child, {
      type: "prompt",
      id: randomUUID(),
      message: delivery.message,
      streamingBehavior: delivery.streamingBehavior,
    })) break;
  }
  return true;
}

function startFreshAssignmentReset(name: string): void {
  const pending = pendingFreshAssignments.get(name);
  const state = streamStates.get(name);
  if (!pending || pending.resetId || state?.finalResponse !== true || processes.get(name) !== pending.child) return;
  const id = randomUUID();
  pending.resetId = id;
  const timeout = setTimeout(() => settleFreshAssignment(name, false), CONTROL_RESPONSE_TIMEOUT_MS);
  timeout.unref?.();
  pendingControlResponses.set(id, {
    child: pending.child,
    command: "new_session",
    timeout,
    resolve: (reset: boolean) => {
      const current = pendingFreshAssignments.get(name);
      if (current !== pending || !reset || processes.get(name) !== pending.child) {
        settleFreshAssignment(name, false);
        return;
      }
      settleFreshAssignment(name, deliverFreshPrompts(name, pending));
    },
  });
  if (!writeToControlStream(pending.child, { type: "new_session", id })) {
    settleFreshAssignment(name, false);
  }
}

/** True while a new Assignment Attempt is waiting for reset or prompt delivery. */
export function isFreshAssignmentPending(name: string): boolean {
  return pendingFreshAssignments.has(name);
}

/** Queue a fresh Pi session and deliver a new Assignment Attempt after settlement. */
export function deliverFreshAssignment(name: string, message: string): Promise<boolean> {
  const child = processes.get(name);
  if (!child || pendingFreshAssignments.has(name)) return Promise.resolve(false);
  return new Promise((resolve) => {
    pendingFreshAssignments.set(name, { child, message, queued: [], resolve });
    startFreshAssignmentReset(name);
  });
}

// ── Stream parsing ────────────────────────────────────────────────

type JsonEvent = {
  id?: string;
  type?: string;
  command?: string;
  success?: boolean;
  error?: string;
  data?: { cancelled?: boolean; isStreaming?: boolean; isCompacting?: boolean; pendingMessageCount?: number; disposition?: string };
  toolCallId?: string;
  toolName?: string;
  args?: unknown;
  isError?: boolean;
  result?: unknown;
  assistantMessageEvent?: {
    type?: string;
    delta?: string;
  };
  message?: {
    role?: string;
    stopReason?: string;
    errorMessage?: string;
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
  /** Last authoritative message survives new runs and diagnostic-tail eviction. */
  lastAnswer?: string;
  answerComplete?: boolean;
  stopReason?: string;
  errorMessage?: string;
  hasToolCalls?: boolean;
  sequenceStarted?: boolean;
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
  usage?: AgentUsage;
  controlError?: string;
  turnBytes: number;
  outputLimitError?: string;
}

function createStreamState(): StreamState {
  return { text: "", thinking: "", toolcallArgs: "", activeTools: new Map(), turns: 0, turnBytes: 0 };
}

function clearActiveTools(state: StreamState): void {
  state.toolcallArgs = "";
  state.activeTool = undefined;
  state.activeTools.clear();
}

/** Final evidence belongs to one assistant message, not the whole sequence.
 * Keep lastAnswer for close diagnostics but never reuse it for a newer draft. */
function startAssistantMessage(state: StreamState): void {
  state.finalResponse = false;
  state.sequenceStarted = true;
  state.text = "";
  state.thinking = "";
  clearActiveTools(state);
  state.turnBytes = 0;
  state.outputLimitError = undefined;
  state.answerComplete = false;
  state.stopReason = undefined;
  state.errorMessage = undefined;
  state.hasToolCalls = undefined;
}

function toolExecutionLabel(toolName: string | undefined, args: unknown): string {
  const serialized = typeof args === "string" ? args : JSON.stringify(args ?? {});
  return truncate(toolcallLabel(serialized) ?? toolName ?? "tool", OUTPUT_CAP);
}

/** Human-readable label from a partially streamed tool-call argument JSON. */
function toolcallLabel(rawArgs: string): string | undefined {
  const activity = classifyToolActivity(rawArgs);
  if (!activity) return undefined;
  switch (activity.kind) {
    case "command": return `bash: ${inlineToolActivity(activity.value)}`;
    case "search": return `search: ${inlineToolActivity(activity.value)}`;
    case "file": return `file: ${inlineToolActivity(path.basename(activity.value))}`;
    case "message": return `message: ${inlineToolActivity(activity.value)}`;
    case "target": return `send: ${inlineToolActivity(activity.value)}`;
  }
}

function appendTurnText(state: StreamState, field: "text" | "thinking" | "toolcallArgs", delta: string): boolean {
  const nextBytes = state.turnBytes + Buffer.byteLength(delta, "utf8");
  if (nextBytes > MAX_TURN_OUTPUT_BYTES) {
    state.outputLimitError = `Resident Agent ${field} exceeded ${MAX_TURN_OUTPUT_BYTES} bytes in one turn.`;
    return false;
  }
  state.turnBytes = nextBytes;
  state[field] += delta;
  return true;
}

function applyStreamLine(state: StreamState, line: string, child?: ChildProcess): boolean {
  if (!line.trim()) return false;
  let event: JsonEvent;
  try {
    event = JSON.parse(line) as JsonEvent;
  } catch {
    return false;
  }
  if (event.type === "response" && event.id) {
    const pending = pendingControlResponses.get(event.id);
    if (pending && child === pending.child && pending.command === event.command) {
      clearTimeout(pending.timeout);
      pendingControlResponses.delete(event.id);
      pending.resolve(event.success === true && event.data?.cancelled !== true
        && (pending.command !== "prompt" || event.data?.disposition !== "handled")
        && (pending.command !== "get_state" || (event.data?.isStreaming === false
          && event.data?.isCompacting !== true && (event.data?.pendingMessageCount ?? 0) === 0)));
    }
  }
  if (event.type === "response" && event.success === false) {
    state.controlError = truncate(`RPC ${event.command ?? "command"} rejected: ${event.error ?? "unknown error"}`, 1000);
    return true;
  }
  if (event.type === "agent_settled") {
    state.finalResponse = true;
    clearActiveTools(state);
    return true;
  }
  if (event.type === "agent_start") {
    state.finalResponse = false;
    state.text = "";
    state.thinking = "";
    clearActiveTools(state);
    state.turnBytes = 0;
    state.outputLimitError = undefined;
    state.answerComplete = false;
    state.stopReason = undefined;
    state.errorMessage = undefined;
    state.hasToolCalls = undefined;
    state.sequenceStarted = true;
    return true;
  }
  if (event.type === "message_start" && event.message?.role === "assistant") {
    startAssistantMessage(state);
    return true;
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
    const parts = extractTextContent(event.message.content, "");
    if (Buffer.byteLength(parts, "utf8") > MAX_TURN_OUTPUT_BYTES) {
      state.outputLimitError = `Resident Agent message exceeded ${MAX_TURN_OUTPUT_BYTES} bytes.`;
      return true;
    }
    state.text = parts;
    state.lastAnswer = parts;
    state.answerComplete = true;
    state.stopReason = normalizeFinalStopReason(event.message.stopReason);
    state.errorMessage = boundedFinalDiagnostic(event.message.errorMessage);
    state.hasToolCalls = event.message.content?.some(part => part.type === "toolCall") ?? false;
    state.turnBytes = 0;
    // Usage stays diagnostics: only streamed content counts as model output,
    // so input-only or failed responses cannot bypass the zero-output tier.
    const u = event.message.usage;
    if (parts.trim()) state.modelOutputSeen = true;
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
  // Some transports omit message_start. The first content event after a
  // completed message is still a new message; later blocks are not.
  if (state.answerComplete && ["text_start", "thinking_start", "toolcall_start", "text_delta", "thinking_delta", "toolcall_delta"].includes(sub.type ?? "")) {
    startAssistantMessage(state);
  }
  switch (sub.type) {
    case "text_start":
    case "thinking_start":
      state.modelOutputSeen = true;
      return true;
    case "text_delta":
      state.modelOutputSeen = true;
      state.activeTool = undefined;
      appendTurnText(state, "text", sub.delta ?? "");
      return true;
    case "thinking_delta":
      state.modelOutputSeen = true;
      state.activeTool = undefined;
      appendTurnText(state, "thinking", sub.delta ?? "");
      return true;
    case "toolcall_start":
      state.modelOutputSeen = true;
      clearActiveTools(state);
      return true;
    case "toolcall_delta": {
      state.modelOutputSeen = true;
      appendTurnText(state, "toolcallArgs", sub.delta ?? "");
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
export function parseAgentOutput(stdout: string): { text: string; usage?: AgentUsage } {
  const state = createStreamState();
  for (const line of stdout.split("\n")) applyStreamLine(state, line);
  return { text: state.text, usage: state.usage };
}

function truncate(text: string, cap: number): string {
  if (text.length <= cap) return text;
  return `${text.slice(0, cap)}\n... [truncated ${text.length - cap} chars]`;
}

// ── Resident spawn ────────────────────────────────────────────────

/** Turn-count baseline per agent at its most recent delivered prompt. */
const baselines = shared.baselines;
const streamTurns = shared.turns;

export interface ResidentSpawnOptions {
  /** Agent name — the registry key for steering, prompting, and shutdown. */
  agentName: string;
  /** Optional kickoff prompt; omit to let the agent idle immediately. */
  description?: string;
  model?: string;
  /** Execution-tool allowlist; the contributed capability tools are appended. */
  tools?: string[];
  /** Agent extension paths loaded into the child with `-e`. `--no-extensions`
   *  still loads explicit paths, so each contributing package passes its own
   *  Agent extension and the spawner hardcodes none. Defaults to none, which
   *  spawns a bare child holding only pi built-ins. */
  extensions?: readonly string[];
  /** Tool ids registered by those extensions. Appended to the role's grant and
   *  admitted into the grantable universe, so a consumer never advertises a tool
   *  nothing implements. Declaring these with no extension is rejected. */
  capabilityTools?: readonly string[];
  /** Leader session's thinking level, forwarded as the child's default. */
  thinking?: string;
  /** Detached active-context snapshot; undefined starts with fresh history. */
  context?: SessionContext["messages"];
  /** Session policy for the child.
   *
   *  - `none` (default) passes `--no-session`. Required when the child
   *    shares the leader's working directory, otherwise its turns would land in
   *    the user's own session group.
   *  - `persist` passes no session flag, so Pi stores the session under the
   *    child's own working path. A durable workspace is what makes this the
   *    Agent's working memory rather than an orphan.
   *  - `resume` passes `--continue`, reopening the most recent session for that
   *    working path. Supply it only for a reused workspace; `--continue` with no
   *    prior session is not a state this spawner should create.
   *
   *  A durable fork context creates new history in its explicit private directory.
   *  A no-session fork transfers structured context through the control pipe and
   *  native context extension; it never materializes a history file. */
  session?: "none" | "persist" | "resume";
  /** Private storage for a persisted Agent, independent of its working directory. */
  sessionDir?: string;
  /** Pass `-a`/`--approve` so the child trusts project-local configuration.
   *
   *  Required for a workspace this harness created. Pi's `defaultProjectTrust`
   *  is `"ask"`, and a freshly created directory is an untrusted project, so a
   *  child started there blocks forever waiting for a trust decision that RPC
   *  mode has no UI to make. Approving is correct in that case and only in that
   *  case: the workspace is a linked checkout of a repository the leader session
   *  already trusts. A child sharing the caller's directory inherits that
   *  directory's existing trust record and must not be force-approved. */
  approveProjectTrust?: boolean;
  env?: Record<string, string | undefined>;
  cwd?: string;
  onUpdate?: (update: AgentProgressUpdate) => void;
  /** Receives only successful, bounded agent_message tool results from this exact child. */
  onParentMessage?: (payload: ParentMessagePayload, sequence: number) => void;
  onExit: (result: AgentProcessResult) => void;
  onError?: (error: Error) => void;
}

export interface SpawnedResident {
  pid: number;
  /** Native idle startup handshake, supplied for prompt-less launches. */
  readiness?: Promise<boolean>;
  /** First prompt RPC acknowledgement; completion still arrives as events. */
  accepted?: Promise<boolean>;
  /** What the environment policy withheld from this child. Passive operator
   *  telemetry: ADR-0002 keeps observation in the console, so this never wakes
   *  the leader on its own. */
  envPolicy?: ChildEnvDiagnostic;
}

/**
 * Spawn one resident child Pi process in RPC mode. Returns immediately with
 * the child pid; outcomes arrive via onExit / onError. An empty description
 * spawns an idle agent that waits for its first delivered prompt.
 */
export function spawnResident(options: ResidentSpawnOptions): SpawnedResident | { error: string } {
  const extensions = options.extensions ?? [];
  const capabilityTools = options.capabilityTools ?? [];
  // The contradiction worth refusing: capability tools with no extension to
  // register them would grant ids the child's --tools filter silently drops, so
  // an agent would be told it can coordinate and then find no such tool.
  if (capabilityTools.length > 0 && extensions.length === 0) {
    return {
      error: `Capability tools ${capabilityTools.join(", ")} were declared but no Agent extension was supplied to register them.`,
    };
  }
  const memoryFork = options.context !== undefined && options.session !== "persist" && options.session !== "resume";
  let forkCommand: ForkContextCommand | undefined;
  try {
    if (memoryFork) forkCommand = createForkContextCommand(randomUUID(), options.context!);
  } catch (error) { return { error: error instanceof Error ? error.message : String(error) }; }
  const childExtensions = memoryFork
    ? [...new Set([...extensions, FORK_CONTEXT_EXTENSION_PATH])] : extensions;
  const cli = resolvePiCli();
  const args: string[] = [
    ...cli.args,
    "--mode", "rpc",
    "--no-extensions",
  ];
  for (const extension of childExtensions) args.push("--extension", extension);
  if (options.approveProjectTrust) args.push("--approve");
  if (options.model) args.push("--model", options.model);
  if (options.thinking) args.push("--thinking", options.thinking);
  args.push("--tools", resolveAgentTools(options.tools, capabilityTools).join(","));

  let child: ChildProcess;
  // The child receives an explicit non-secret environment, never the leader's
  // complete one. See child-env.ts for why this is leakage defense rather than
  // containment, and what a child still needs the config directory for.
  const childEnv = resolveChildEnv({ overrides: options.env });
  try {
    if (options.sessionDir && options.session !== "none") assertPrivateSessionFiles(options.sessionDir);
    if (memoryFork) {
      args.push("--no-session");
    } else if (options.context !== undefined) {
      if (!options.sessionDir) throw new Error("A durable fork requires an explicit private session directory.");
      fs.mkdirSync(options.sessionDir, { recursive: true, mode: 0o700 });
      args.push("--session", writeWorkContext(options.cwd ?? process.cwd(), options.sessionDir, options.context));
    } else if (options.session === "resume") {
      args.push("--continue");
    } else if (options.session !== "persist") {
      args.push("--no-session");
    }
    if (options.sessionDir && options.session !== "none") {
      fs.mkdirSync(options.sessionDir, { recursive: true, mode: 0o700 });
      args.push("--session-dir", options.sessionDir);
    }
    child = spawnPiChild(cli.command, args, {
      cwd: options.cwd,
      env: childEnv.env,
      stdio: ["pipe", "pipe", "pipe"],
    });
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) };
  }
  observeProcessClose(options.agentName, child);
  processes.set(options.agentName, child);
  // A same-name successor may be spawned reentrantly from the predecessor's
  // final onUpdate during close. Its lifetime turn count starts at zero; the
  // predecessor's count must never become its baseline.
  streamTurns.set(options.agentName, 0);
  baselines.delete(options.agentName);

  const stdoutChunks: string[] = [];
  const stderrChunks: string[] = [];
  const streamState = createStreamState();
  streamStates.set(options.agentName, streamState);
  let stdoutBuffer = "";
  const decoder = new StringDecoder("utf8");
  let failureReason: string | undefined;
  let settled = false;
  let completeForkSetup: ((accepted: boolean) => void) | undefined;
  let parentMessageSequence = 0;

  const emitProgress = () => options.onUpdate?.({
    text: streamState.finalResponse === true ? streamState.text : truncate(streamState.text, OUTPUT_CAP),
    activeTool: streamState.activeTool,
    liveThinking: truncate(streamState.thinking, OUTPUT_CAP),
    turns: Math.max(0, streamState.turns - (baselines.get(options.agentName) ?? 0)),
    finalResponse: streamState.finalResponse,
    answerComplete: streamState.finalResponse === true && streamState.answerComplete === true,
    stopReason: streamState.stopReason,
    errorMessage: streamState.errorMessage,
    hasToolCalls: streamState.hasToolCalls,
    missingFinal: streamState.finalResponse === true && streamState.sequenceStarted === true && streamState.answerComplete !== true,
    modelOutputSeen: streamState.modelOutputSeen,
    usage: streamState.usage,
    controlError: streamState.controlError,
  });

  let termination: Promise<boolean> | undefined;
  const failAgent = (reason: string) => {
    failureReason ??= reason;
    completeForkSetup?.(false);
    stdoutBuffer = "";
    streamState.outputLimitError ??= reason;
    streamState.controlError = reason;
    emitProgress();
    termination ??= terminateChildProcess(child);
  };

  const consumeStdoutLines = (lines: string[], closing = false): void => {
    const ownsStream = () => streamStates.get(options.agentName) === streamState
      && (closing || processes.get(options.agentName) === child);
    if (failureReason || !ownsStream()) return;
    const routeParentMessage = (line: string): void => {
      if (!options.onParentMessage) return;
      let event: JsonEvent;
      try { event = JSON.parse(line) as JsonEvent; }
      catch { return; }
      if (event.type !== "tool_execution_end" || event.toolName !== PARENT_MESSAGE_TOOL_NAME || event.isError !== false) return;
      const payload = parseParentMessageResult(event.toolCallId, event.result);
      if (!payload || !ownsStream()) return;
      parentMessageSequence += 1;
      // The spawner owns transport identity and ordering. The surface adds
      // session/input ownership and creates its own notice from this payload.
      try { options.onParentMessage(payload, parentMessageSequence); }
      catch (error) { options.onError?.(error instanceof Error ? error : new Error(String(error))); }
    };
    let changed = false;
    // A settle is an event, and a consumer that waits for one to decide what
    // to do must not miss it because the same chunk also carried the next turn's
    // start. Coalescing to one frame per chunk would turn "the child answered,
    // then started a new turn" into "the child started a new turn", and the
    // answer would never be reported. The edge is therefore emitted as it
    // happens, not after the chunk is read.
    let settledBefore = streamState.finalResponse;
    for (const line of lines) {
      if (Buffer.byteLength(line, "utf8") > MAX_JSONL_LINE_BYTES) {
        failAgent(`Resident Agent JSONL line exceeded ${MAX_JSONL_LINE_BYTES} bytes.`);
        return;
      }
      if (forkCommand && completeForkSetup) {
        try {
          const event: unknown = JSON.parse(line);
          const ack = parseForkContextAck(event, forkCommand.id);
          if (ack) completeForkSetup(ack.success);
          else if (typeof event === "object" && event !== null && "type" in event && event.type === "response"
            && "id" in event && event.id === forkCommand.id && "command" in event && event.command === "prompt"
            && "success" in event && event.success === false) completeForkSetup(false);
        } catch { /* Generic handled/invalid records cannot acknowledge setup. */ }
      }
      changed = applyStreamLine(streamState, line, child) || changed;
      routeParentMessage(line);
      if (!streamState.finalResponse && settledBefore) {
        // The sequence-start edge must survive a coalesced read as well as settle.
        emitProgress();
        changed = false;
      }
      if (streamState.finalResponse) startFreshAssignmentReset(options.agentName);
      if (streamState.finalResponse && !settledBefore) {
        emitProgress();
        if (ownsStream()) streamTurns.set(options.agentName, streamState.turns);
        changed = false;
      }
      settledBefore = streamState.finalResponse;
      if (streamState.outputLimitError) {
        failAgent(streamState.outputLimitError);
        return;
      }
    }
    if (Buffer.byteLength(stdoutBuffer, "utf8") > MAX_JSONL_LINE_BYTES) {
      failAgent(`Resident Agent JSONL line exceeded ${MAX_JSONL_LINE_BYTES} bytes.`);
      return;
    }
    if (changed) emitProgress();
    if (ownsStream()) streamTurns.set(options.agentName, streamState.turns);
    if (!failureReason) streamState.controlError = undefined;
  };
  child.stdout?.on("data", (chunk: Buffer) => {
    if (failureReason || processes.get(options.agentName) !== child) return;
    const text = decoder.write(chunk);
    stdoutBuffer += text;
    const lines = stdoutBuffer.split("\n");
    stdoutBuffer = lines.pop() ?? "";
    consumeStdoutLines(lines);
    appendCapped(stdoutChunks, text, DIAGNOSTIC_TAIL_BYTES);
  });
  child.stderr?.on("data", (chunk: Buffer) => {
    if (failureReason) return;
    appendCapped(stderrChunks, chunk.toString(), DIAGNOSTIC_TAIL_BYTES);
  });

  child.on("error", (error) => {
    completeForkSetup?.(false);
    if (child.pid === undefined) settled = true;
    // Keep the registry entry until close is observed so shutdown diagnostics
    // can distinguish an error/exit code from a confirmed close event.
    options.onError?.(error);
  });

  child.on("close", (code, signal) => {
    // A producer may close after its final JSON record without writing LF.
    // Flush StringDecoder so a split trailing UTF-8 code point and that final
    // record are both observed before onExit snapshots authoritative output.
    if (!failureReason && streamStates.get(options.agentName) === streamState) {
      stdoutBuffer += decoder.end();
      if (stdoutBuffer) {
        const trailing = stdoutBuffer;
        stdoutBuffer = "";
        consumeStdoutLines([trailing], true);
      }
    }
    completeForkSetup?.(false);
    if (processes.get(options.agentName) === child) processes.delete(options.agentName);
    if (streamStates.get(options.agentName) === streamState) {
      streamStates.delete(options.agentName);
      baselines.delete(options.agentName);
      streamTurns.delete(options.agentName);
    }
    if (shared.readiness.get(options.agentName)?.child === child) shared.readiness.delete(options.agentName);
    const fresh = pendingFreshAssignments.get(options.agentName);
    if (fresh?.child === child) settleFreshAssignment(options.agentName, false);
    for (const [id, pending] of pendingControlResponses) {
      if (pending.child !== child) continue;
      clearTimeout(pending.timeout);
      pendingControlResponses.delete(id);
      pending.resolve(false);
    }
    // A spawn failure was already reported via onError (Node fires error then
    // close) — do not double-report through onExit.
    if (settled) return;
    const failed = failureReason !== undefined;
    const parsed = failed ? { text: "", usage: undefined }
      : { text: streamState.lastAnswer ?? streamState.text, usage: streamState.usage };
    options.onExit({
      pid: child.pid ?? 0,
      exitCode: code === 0 && failed ? 1 : code,
      signal,
      stdout: failed ? "" : parsed.text,
      stderr: truncate([failureReason, stderrChunks.join("").trim()].filter(Boolean).join("\n"), OUTPUT_CAP),
      usage: parsed.usage,
    });
  });

  const forkInitialized = forkCommand ? new Promise<boolean>(resolve => {
    const timeout = setTimeout(() => completeForkSetup?.(false), STARTUP_RESPONSE_TIMEOUT_MS);
    // Register before write: native setup can acknowledge inside stdin.write().
    completeForkSetup = (accepted) => {
      clearTimeout(timeout);
      completeForkSetup = undefined;
      const current = accepted && processes.get(options.agentName) === child && !closedProcesses.has(child);
      if (!current && processes.get(options.agentName) === child) {
        streamState.controlError = "In-memory fork context setup was not acknowledged; no input was sent.";
        emitProgress();
      }
      resolve(current);
    };
    if (!writeToControlStream(child, forkCommand!)) completeForkSetup(false);
  }) : undefined;
  const accepted = options.description?.trim()
    ? forkInitialized
      ? forkInitialized.then(ready => ready && processes.get(options.agentName) === child
          ? deliverResidentPrompt(options.agentName, options.description!) : false)
      : deliverAcknowledgedResidentInput(options.agentName, options.description, "followUp", true, STARTUP_RESPONSE_TIMEOUT_MS)
    : undefined;
  let readiness: Promise<boolean> | undefined;
  if (!options.description?.trim()) {
    let resolveReady!: (ready: boolean) => void;
    readiness = new Promise<boolean>(resolve => { resolveReady = resolve; });
    shared.readiness.set(options.agentName, { child, promise: readiness });
    const requestIdleReadiness = () => {
      if (processes.get(options.agentName) !== child || closedProcesses.has(child)) { resolveReady(false); return; }
      const id = randomUUID();
      const timeout = setTimeout(() => {
        pendingControlResponses.delete(id);
        streamState.controlError = "Resident startup readiness was not acknowledged.";
        emitProgress();
        resolveReady(false);
      }, STARTUP_RESPONSE_TIMEOUT_MS);
      timeout.unref?.();
      pendingControlResponses.set(id, {
        child,
        command: "get_state",
        timeout,
        resolve: (ready: boolean) => {
          resolveReady(ready && processes.get(options.agentName) === child);
          if (processes.get(options.agentName) !== child) return;
          if (!ready) {
            streamState.controlError = "Resident startup readiness acknowledgement was rejected or not idle.";
            emitProgress();
            return;
          }
          streamState.finalResponse = true;
          options.onUpdate?.({ text: "", turns: 0, finalResponse: true, ready: true });
          startFreshAssignmentReset(options.agentName);
        },
      });
      if (!writeToControlStream(child, { type: "get_state", id })) {
        clearTimeout(timeout);
        pendingControlResponses.delete(id);
        resolveReady(false);
        options.onError?.(new Error("Cannot request resident startup readiness."));
      }
    };
    if (forkInitialized) void forkInitialized.then(ready => ready ? requestIdleReadiness() : resolveReady(false));
    else requestIdleReadiness();
  }
  return { pid: child.pid ?? 0, envPolicy: diagnosticOf(childEnv), ...(readiness ? { readiness } : {}), ...(accepted ? { accepted } : {}) };
}

function appendCapped(chunks: string[], chunk: string, cap: number): void {
  chunks.push(chunk);
  let total = chunks.reduce((sum, value) => sum + Buffer.byteLength(value, "utf8"), 0);
  while (total > cap && chunks.length > 1) {
    total -= Buffer.byteLength(chunks.shift() ?? "", "utf8");
  }
  if (total > cap && chunks.length === 1) {
    chunks[0] = Buffer.from(chunks[0], "utf8").subarray(-cap).toString("utf8");
  }
}
