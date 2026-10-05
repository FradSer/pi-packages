import { randomUUID } from "node:crypto";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  buildSessionContext,
  SessionManager,
  type ExtensionContext,
  type SessionContext,
  type SessionMessageEntry,
} from "@earendil-works/pi-coding-agent";

type AgentMessage = SessionContext["messages"][number];
type ContextReader = Pick<ExtensionContext["sessionManager"], "getBranch" | "getLeafId">;
type AssistantMessage = Extract<AgentMessage, { role: "assistant" }>;
type ToolResultMessage = Extract<AgentMessage, { role: "toolResult" }>;
type ToolCall = Extract<AssistantMessage["content"][number], { type: "toolCall" }>;

/** The child loads only this explicit contribution, never the parent's extensions. */
export const FORK_CONTEXT_EXTENSION_PATH = fileURLToPath(new URL("./fork-extension.ts", import.meta.url));
export const FORK_CONTEXT_COMMAND = "subagents-context";
export const FORK_CONTEXT_ACK_STATUS = "subagents-context-ack";
/** Includes base64, the command envelope and JSONL framing; matches the transport's 8 MiB limit. */
export const MAX_FORK_CONTEXT_COMMAND_BYTES = 8 * 1024 * 1024;
const REQUEST_ID = /^[A-Za-z0-9_-]{1,128}$/;

export interface ForkContextCommand {
  type: "prompt";
  id: string;
  message: string;
}

export type ForkContextAck = {
  version: 1;
  requestId: string;
  success: true;
  messageCount: number;
} | {
  version: 1;
  requestId: string;
  success: false;
  error: string;
};

/** Explicit field projection prevents future/legacy metadata from transferring authority. */
function fields<T, K extends keyof T>(value: T, keys: readonly K[]): Pick<T, K> {
  return Object.fromEntries(keys.filter(key => value[key] !== undefined).map(key => [key, value[key]])) as Pick<T, K>;
}

function historyUsage(usage: AssistantMessage["usage"]): AssistantMessage["usage"] {
  return {
    ...fields(usage, ["input", "output", "cacheRead", "cacheWrite", "cacheWrite1h", "reasoning", "totalTokens"]),
    cost: fields(usage.cost, ["input", "output", "cacheRead", "cacheWrite", "total"]),
  };
}

function historyBlock(block: AssistantMessage["content"][number]): AssistantMessage["content"][number];
function historyBlock(block: ToolResultMessage["content"][number]): ToolResultMessage["content"][number];
function historyBlock(block: AssistantMessage["content"][number] | ToolResultMessage["content"][number]) {
  switch (block.type) {
    case "text": return fields(block, ["type", "text", "textSignature"]);
    case "image": return fields(block, ["type", "data", "mimeType"]);
    case "thinking": return fields(block, ["type", "thinking", "thinkingSignature", "redacted"]);
    case "toolCall": return fields(block, ["type", "id", "name", "arguments", "thoughtSignature", "namespace"]);
  }
}

function withoutRuntimeState(message: AgentMessage): AgentMessage | undefined {
  switch (message.role) {
    // Pi 1.0.0 system messages carry the parent's prompt AND tool loadout.
    case "system": return undefined;
    case "user": return { ...fields(message, ["role", "timestamp"]),
      content: typeof message.content === "string" ? message.content : message.content.map(historyBlock) };
    case "assistant": return {
      ...fields(message, ["role", "api", "provider", "model", "responseModel", "providerThinkingLevel", "thinkingLevel",
        "stopReason", "errorMessage", "rawStopReason", "endTurn", "timestamp"]),
      content: message.content.map(block => historyBlock(block)), usage: historyUsage(message.usage),
      // Deferred provider operations belong to the parent, not to its history fork.
      stopReason: message.stopReason === "deferred" ? "stop" : message.stopReason,
    };
    case "toolResult": return {
      ...fields(message, ["role", "toolCallId", "toolName", "isError", "timestamp"]),
      content: message.content.map(historyBlock), ...(message.usage ? { usage: historyUsage(message.usage) } : {}),
    };
    case "custom": return { ...fields(message, ["role", "customType", "display", "timestamp"]),
      content: typeof message.content === "string" ? message.content : message.content.map(historyBlock) };
    case "bashExecution": return fields(message, ["role", "command", "output", "exitCode", "cancelled", "truncated",
      "fullOutputPath", "excludeFromContext", "timestamp"]);
    case "branchSummary": return fields(message, ["role", "summary", "fromId", "timestamp"]);
    case "compactionSummary": return fields(message, ["role", "summary", "tokensBefore", "timestamp"]);
  }
}

function completedExchanges(messages: AgentMessage[]): { calls: Set<ToolCall>; results: Set<ToolResultMessage> } {
  const pending = new Map<string, ToolCall>();
  const calls = new Set<ToolCall>();
  const results = new Set<ToolResultMessage>();
  for (const message of messages) {
    if (message.role === "user" || message.role === "assistant") pending.clear();
    if (message.role === "assistant") {
      for (const block of message.content) {
        if (block.type === "toolCall" && !pending.has(block.id)) pending.set(block.id, block);
      }
    } else if (message.role === "toolResult") {
      const call = pending.get(message.toolCallId);
      if (!call || call.name !== message.toolName) continue;
      calls.add(call);
      results.add(message);
      pending.delete(call.id);
    }
  }
  return { calls, results };
}

/** Project native conversation evidence; neither system/tool authority nor unfinished exchanges survive. */
export function sanitizeWorkContext(messages: readonly AgentMessage[]): AgentMessage[] {
  const completed = completedExchanges([...messages]);
  const history: AgentMessage[] = [];
  for (const message of messages) {
    if (message.role === "toolResult" && !completed.results.has(message)) continue;
    if (message.role !== "assistant") {
      const conversation = withoutRuntimeState(message);
      if (conversation) history.push(conversation);
      continue;
    }
    const content = message.content.filter((block) => block.type !== "toolCall" || completed.calls.has(block));
    if (content.length === 0 && message.content.length > 0) continue;
    const hasTools = content.some((block) => block.type === "toolCall");
    const stopReason = message.stopReason === "toolUse" && !hasTools ? "stop" : message.stopReason;
    const conversation = withoutRuntimeState({ ...message, content, stopReason });
    if (conversation) history.push(conversation);
  }
  return structuredClone(history);
}

/** Snapshot the active Pi context without moving the parent's branch or replaying pending tools. */
export function snapshotWorkContext(sessionManager: ContextReader | undefined): AgentMessage[] {
  if (!sessionManager || typeof sessionManager.getBranch !== "function" || typeof sessionManager.getLeafId !== "function") {
    throw new Error("Fork context unavailable: leader session manager is unavailable.");
  }
  return sanitizeWorkContext(buildSessionContext(sessionManager.getBranch(), sessionManager.getLeafId()).messages);
}

/**
 * Setup is a control command, not a user-history message. Wait for parseForkContextAck
 * to return success before sending ANY kickoff/readiness receipt. Pi's generic
 * prompt disposition "handled" is not evidence of successful extension setup.
 */
export function createForkContextCommand(requestId: string, messages: readonly AgentMessage[]): ForkContextCommand {
  if (!REQUEST_ID.test(requestId)) throw new Error("Fork context request id is invalid.");
  const payload = Buffer.from(JSON.stringify({ version: 1, messages: sanitizeWorkContext(messages) }), "utf8").toString("base64");
  const command: ForkContextCommand = { type: "prompt", id: requestId, message: `/${FORK_CONTEXT_COMMAND} ${requestId} ${payload}` };
  if (Buffer.byteLength(JSON.stringify(command) + "\n", "utf8") > MAX_FORK_CONTEXT_COMMAND_BYTES) {
    throw new Error(`Fork context command exceeds the ${MAX_FORK_CONTEXT_COMMAND_BYTES} byte transport limit.`);
  }
  return command;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function optionalFields(value: Record<string, unknown>, type: "string" | "boolean" | "number", keys: readonly string[]): boolean {
  return keys.every(key => value[key] === undefined || (typeof value[key] === type
    && (type !== "number" || Number.isFinite(value[key]))));
}

function validUsage(value: unknown): boolean {
  if (!record(value) || !record(value.cost)) return false;
  const cost = value.cost;
  return ["input", "output", "cacheRead", "cacheWrite", "totalTokens"].every(key => typeof value[key] === "number" && Number.isFinite(value[key]))
    && optionalFields(value, "number", ["cacheWrite1h", "reasoning"])
    && ["input", "output", "cacheRead", "cacheWrite", "total"].every(key => typeof cost[key] === "number" && Number.isFinite(cost[key]));
}

function validContent(value: unknown, assistant = false): boolean {
  if (typeof value === "string") return !assistant;
  if (!Array.isArray(value)) return false;
  return value.every(block => {
    if (!record(block)) return false;
    switch (block.type) {
      case "text": return typeof block.text === "string" && optionalFields(block, "string", ["textSignature"]);
      case "image": return !assistant && typeof block.data === "string" && typeof block.mimeType === "string";
      case "thinking": return assistant && typeof block.thinking === "string"
        && optionalFields(block, "string", ["thinkingSignature"]) && optionalFields(block, "boolean", ["redacted"]);
      case "toolCall": return assistant && typeof block.id === "string" && typeof block.name === "string" && record(block.arguments)
        && optionalFields(block, "string", ["thoughtSignature", "namespace"]);
      default: return false;
    }
  });
}

function validMessage(value: unknown): value is AgentMessage {
  if (!record(value) || typeof value.timestamp !== "number" || !Number.isFinite(value.timestamp)) return false;
  switch (value.role) {
    case "system": return true; // Always discarded, including its untrusted fields.
    case "user": return validContent(value.content);
    case "custom": return validContent(value.content) && typeof value.customType === "string" && typeof value.display === "boolean";
    case "assistant": return validContent(value.content, true) && validUsage(value.usage)
      && ["api", "provider", "model"].every(key => typeof value[key] === "string")
      && optionalFields(value, "string", ["responseModel", "providerThinkingLevel", "thinkingLevel", "errorMessage", "rawStopReason"])
      && optionalFields(value, "boolean", ["endTurn"])
      && ["stop", "length", "toolUse", "error", "aborted", "deferred"].includes(String(value.stopReason));
    case "toolResult": return Array.isArray(value.content) && validContent(value.content)
      && typeof value.toolCallId === "string" && typeof value.toolName === "string" && typeof value.isError === "boolean"
      && (value.usage === undefined || validUsage(value.usage));
    case "branchSummary": return typeof value.summary === "string" && (value.fromId === null || typeof value.fromId === "string");
    case "compactionSummary": return typeof value.summary === "string" && typeof value.tokensBefore === "number" && Number.isFinite(value.tokensBefore);
    case "bashExecution": return typeof value.command === "string" && typeof value.output === "string"
      && typeof value.cancelled === "boolean" && typeof value.truncated === "boolean"
      && optionalFields(value, "number", ["exitCode"]) && optionalFields(value, "string", ["fullOutputPath"])
      && optionalFields(value, "boolean", ["excludeFromContext"]);
    default: return false;
  }
}

/** Validate a versioned wire payload and defensively repeat the authority projection in the child. */
export function decodeForkContext(payload: string): AgentMessage[] {
  if (payload.length > MAX_FORK_CONTEXT_COMMAND_BYTES || payload.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(payload)) {
    throw new Error("Fork context payload is invalid or exceeds the transport limit.");
  }
  let parsed: unknown;
  try {
    const bytes = Buffer.from(payload, "base64");
    if (bytes.toString("base64") !== payload) throw new Error("Non-canonical base64.");
    parsed = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch { throw new Error("Fork context payload is not valid UTF-8 JSON."); }
  if (!record(parsed) || parsed.version !== 1 || Object.keys(parsed).some(key => key !== "version" && key !== "messages")
    || !Array.isArray(parsed.messages) || !parsed.messages.every(validMessage)) {
    throw new Error("Fork context payload version or native messages are invalid.");
  }
  return sanitizeWorkContext(parsed.messages);
}

/** Only this correlated native RPC notification acknowledges setup; generic prompt responses do not. */
export function parseForkContextAck(event: unknown, requestId: string): ForkContextAck | undefined {
  if (!record(event) || event.type !== "extension_ui_request" || event.method !== "setStatus"
    || event.statusKey !== FORK_CONTEXT_ACK_STATUS || typeof event.statusText !== "string" || event.statusText.length > 1024) return;
  let ack: unknown;
  try { ack = JSON.parse(event.statusText); } catch { return; }
  if (!record(ack) || ack.version !== 1 || ack.requestId !== requestId) return;
  if (ack.success === true && typeof ack.messageCount === "number" && Number.isSafeInteger(ack.messageCount) && ack.messageCount >= 0) {
    return { version: 1, requestId, success: true, messageCount: ack.messageCount };
  }
  if (ack.success === false && typeof ack.error === "string" && ack.error.length <= 512) {
    return { version: 1, requestId, success: false, error: ack.error };
  }
}

/** Materialize already-rebuilt context; appendMessage cannot represent Pi summary roles. */
export function writeWorkContext(cwd: string, directory: string, messages: AgentMessage[]): string {
  const session = SessionManager.create(cwd, directory);
  const file = session.getSessionFile()!;
  let parentId: string | null = null;
  const entries = messages.map((message): SessionMessageEntry => {
    const entry: SessionMessageEntry = {
      type: "message", id: randomUUID(), parentId, timestamp: new Date().toISOString(), message,
    };
    parentId = entry.id;
    return entry;
  });
  const content = [session.getHeader(), ...entries].map((entry) => JSON.stringify(entry)).join("\n");
  writeFileSync(file, `${content}\n`, { mode: 0o600, flag: "wx" });
  return file;
}
