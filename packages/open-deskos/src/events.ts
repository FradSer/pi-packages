import {
  MAX_EVENT_TEXT,
  MAX_EVENTS_PER_SESSION,
  MAX_MESSAGE_BYTES,
  MAX_RESULT_BYTES,
  MAX_SESSION_EVENT_BYTES,
  MAX_THINKING_BYTES,
  MAX_TOOL_BYTES,
  MAX_USER_BYTES,
  type SessionEvent,
  type ThinkingPart,
  type ToolCallPart,
  type TextPart,
} from "./types.ts";

/** Collapse a value to the first non-empty line, bounded to one short line. */
export function boundEventText(value: unknown, max = MAX_EVENT_TEXT): string {
  if (typeof value !== "string") return "";
  for (const raw of value.split(/\r?\n/)) {
    const line = raw.replace(/\s+/g, " ").trim();
    if (line.length === 0) continue;
    return line.length > max ? `${line.slice(0, max - 1)}…` : line;
  }
  return "";
}

/** The bound each kind's body is held to. */
const BODY_BYTES: Record<SessionEvent["kind"], number> = {
  result: MAX_RESULT_BYTES,
  assistant: MAX_MESSAGE_BYTES,
  user: MAX_USER_BYTES,
  thinking: MAX_THINKING_BYTES,
  tool: MAX_TOOL_BYTES,
};

/**
 * Apply the body bound without flattening or prefixing its Markdown. Every kind
 * keeps its line structure so the desk can render it the way Pi does: a bash
 * command, a prompt, a thought, a reply, and a result are content, and only
 * their own byte limit shortens them.
 */
export function boundSessionEvent(event: SessionEvent): SessionEvent | null {
  if (!event.text.trim()) return null;
  const maxBytes = BODY_BYTES[event.kind] ?? MAX_RESULT_BYTES;
  const bytes = Buffer.from(event.text, "utf8");
  let text = event.text;
  let truncated = event.truncated === true;
  if (bytes.length > maxBytes) {
    let end = maxBytes;
    // A byte limit must never bisect a UTF-8 code point.
    while (end > 0 && (bytes[end]! & 0xc0) === 0x80) end -= 1;
    text = bytes.subarray(0, end).toString("utf8");
    truncated = true;
  }
  const toolName = event.kind === "result" ? boundEventText(event.toolName) : "";
  // A call identity is an opaque short line, never a body, so it is bounded as one.
  const toolCallId = event.kind === "result" || event.kind === "tool" ? boundEventText(event.toolCallId) : "";
  return {
    kind: event.kind,
    text,
    ...(toolName ? { toolName } : {}),
    ...(toolCallId ? { toolCallId } : {}),
    ...(event.kind === "result" && event.isError === true ? { isError: true } : {}),
    ...(truncated ? { truncated: true } : {}),
  };
}

/** Keep a contiguous newest tail within both the event-count and UTF-8 budgets. */
export function retainEvents(events: readonly SessionEvent[]): SessionEvent[] {
  const retained: SessionEvent[] = [];
  let bytes = 0;
  for (let index = events.length - 1; index >= 0 && retained.length < MAX_EVENTS_PER_SESSION; index -= 1) {
    const event = events[index]!;
    const size = Buffer.byteLength(event.text) + Buffer.byteLength(event.toolName ?? "");
    if (bytes + size > MAX_SESSION_EVENT_BYTES) break;
    retained.push(event);
    bytes += size;
  }
  return retained.reverse();
}

function readArguments(args: unknown): Record<string, unknown> {
  if (typeof args === "string") {
    try {
      const parsed: unknown = JSON.parse(args);
      return typeof parsed === "object" && parsed !== null ? (parsed as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  }
  return typeof args === "object" && args !== null ? (args as Record<string, unknown>) : {};
}

/** The command, file, or query a tool call names, as Pi issued it. */
export function summarizeToolCall(name: string, args: unknown): string {
  const parsed = readArguments(args);
  const asText = (value: unknown): string => (typeof value === "string" ? value.trim() : "");
  const command = asText(parsed.command);
  if (command) return `bash: ${command}`;
  const file = asText(parsed.path);
  if (file) return `${name}: ${file}`;
  const query = asText(parsed.query);
  if (query) return `search: ${query}`;
  const subject = asText(parsed.subject);
  if (subject) return `${name}: ${subject}`;
  return name;
}

function isText(part: unknown): part is TextPart {
  return typeof part === "object" && part !== null && (part as TextPart).type === "text" && typeof (part as TextPart).text === "string";
}

function isThinking(part: unknown): part is ThinkingPart {
  return typeof part === "object" && part !== null && (part as ThinkingPart).type === "thinking" && typeof (part as ThinkingPart).thinking === "string";
}

function isToolCall(part: unknown): part is ToolCallPart {
  return typeof part === "object" && part !== null && (part as ToolCallPart).type === "toolCall" && typeof (part as ToolCallPart).name === "string";
}

interface MessageView {
  role?: string;
  toolName?: string;
  toolCallId?: string;
  isError?: boolean;
  content?: unknown;
}

function asMessage(value: unknown): MessageView | null {
  if (typeof value !== "object" || value === null) return null;
  const message = value as MessageView;
  return typeof message.role === "string" ? message : null;
}

/** The user prompt carried by a message, used as the session's stated goal. */
export function promptFromMessage(message: unknown): string {
  const view = asMessage(message);
  if (!view || view.role !== "user") return "";
  if (typeof view.content === "string") return boundEventText(view.content);
  const parts = Array.isArray(view.content) ? view.content : [];
  for (const part of parts) if (isText(part)) return boundEventText(part.text);
  return "";
}

/**
 * The Session Events one finalized message contributes. A tool result joins
 * all text parts into one bounded Markdown body; other events stay summaries.
 */
export function eventsFromMessage(message: unknown): SessionEvent[] {
  const view = asMessage(message);
  if (!view) return [];
  // A user message may carry plain text rather than parts.
  if (typeof view.content === "string") {
    const text = boundEventText(view.content);
    return text.length > 0 && view.role === "user" ? [{ kind: "user", text }] : [];
  }
  const parts = Array.isArray(view.content) ? view.content : [];
  if (view.role === "toolResult") {
    const event = boundSessionEvent({
      kind: "result",
      text: parts.filter(isText).map((part) => part.text).join("\n\n"),
      ...(typeof view.toolName === "string" ? { toolName: view.toolName } : {}),
      // The call this result answers, and whether Pi recorded it as an error:
      // a desk reads the outcome from this record instead of guessing one.
      ...(typeof view.toolCallId === "string" ? { toolCallId: view.toolCallId } : {}),
      ...(view.isError === true ? { isError: true } : {}),
    });
    return event ? [event] : [];
  }
  const events: SessionEvent[] = [];
  for (const part of parts) {
    if (view.role === "user" && isText(part)) {
      if (part.text.trim()) events.push({ kind: "user", text: part.text.trim() });
      continue;
    }
    if (view.role === "assistant" && isThinking(part)) {
      if (part.thinking.trim()) events.push({ kind: "thinking", text: part.thinking.trim() });
      continue;
    }
    if (view.role === "assistant" && isToolCall(part)) {
      // The call is kept as Pi issued it: a multi-line command or a heredoc is
      // content. The one-line activity summary is made separately, in the
      // reporter, and never replaces this body.
      const text = summarizeToolCall(part.name, part.arguments).trim();
      if (text) events.push({ kind: "tool", text, ...(typeof part.id === "string" && part.id ? { toolCallId: part.id } : {}) });
      continue;
    }
    // The reply body is added once, after its thinking and tool calls.
  }
  if (view.role === "assistant") {
    // One reply may stream as several text parts; Pi reads them as one body.
    const said = parts.filter((part): part is TextPart => isText(part) && part.text.trim().length > 0);
    if (said.length > 0) events.push({ kind: "assistant", text: said.map((part) => part.text).join("\n\n") });
  }
  return events;
}
