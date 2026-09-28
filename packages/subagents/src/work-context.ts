import { randomUUID } from "node:crypto";
import { writeFileSync } from "node:fs";
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

function withoutRuntimeState(message: AgentMessage): AgentMessage {
  if (message.role === "custom") {
    const { details: _details, ...history } = message;
    return history;
  }
  if (message.role === "toolResult") {
    const { details: _details, addedToolNames: _tools, ...history } = message;
    return history;
  }
  return message;
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

/** Snapshot the active Pi context without moving the parent's branch or replaying pending tools. */
export function snapshotWorkContext(sessionManager: ContextReader | undefined): AgentMessage[] {
  if (!sessionManager || typeof sessionManager.getBranch !== "function" || typeof sessionManager.getLeafId !== "function") {
    throw new Error("Fork context unavailable: leader session manager is unavailable.");
  }
  const messages = buildSessionContext(sessionManager.getBranch(), sessionManager.getLeafId()).messages;
  const completed = completedExchanges(messages);
  const history: AgentMessage[] = [];
  for (const message of messages) {
    if (message.role === "toolResult" && !completed.results.has(message)) continue;
    if (message.role !== "assistant") {
      history.push(withoutRuntimeState(message));
      continue;
    }
    const content = message.content.filter((block) => block.type !== "toolCall" || completed.calls.has(block));
    if (content.length === 0 && message.content.length > 0) continue;
    const hasTools = content.some((block) => block.type === "toolCall");
    const stopReason = message.stopReason === "toolUse" && !hasTools ? "stop" : message.stopReason;
    history.push({ ...message, content, stopReason });
  }
  return structuredClone(history);
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
