import {
  MAX_EVENT_TEXT,
  MAX_EVENTS_PER_SESSION,
  MAX_MESSAGE_BYTES,
  MAX_RESULT_BYTES,
  MAX_SESSION_EVENT_BYTES,
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

/** Kinds that carry a rendered body rather than a one-line summary. */
const BODY_KINDS = new Set(["result", "assistant"]);

/**
 * Apply the body bound without flattening or prefixing its Markdown. A tool
 * result and an assistant reply keep their line structure so the desk can
 * render them the way Pi does; summaries stay one bounded line.
 */
export function boundSessionEvent(event: SessionEvent): SessionEvent | null {
  if (!BODY_KINDS.has(event.kind)) {
    const text = boundEventText(event.text);
    return text ? { kind: event.kind, text } : null;
  }
  if (!event.text.trim()) return null;
  const maxBytes = event.kind === "assistant" ? MAX_MESSAGE_BYTES : MAX_RESULT_BYTES;
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
  const toolName = boundEventText(event.toolName);
  return { kind: event.kind, text, ...(toolName ? { toolName } : {}), ...(truncated ? { truncated: true } : {}) };
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

function baseName(value: string): string {
  const parts = value.split(/[/\\]/).filter((part) => part.length > 0);
  return parts.length > 0 ? (parts[parts.length - 1] ?? value) : value;
}

/** Name a tool call the way the desk reads it: a command, a file, or a query. */
export function summarizeToolCall(name: string, args: unknown): string {
  const parsed = readArguments(args);
  const asText = (value: unknown): string => (typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "");
  const command = asText(parsed.command);
  if (command) return `bash: ${command}`;
  const file = asText(parsed.path);
  if (file) return `${name}: ${baseName(file)}`;
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
    });
    return event ? [event] : [];
  }
  const events: SessionEvent[] = [];
  for (const part of parts) {
    if (view.role === "user" && isText(part)) {
      const text = boundEventText(part.text);
      if (text) events.push({ kind: "user", text });
      continue;
    }
    if (view.role === "assistant" && isThinking(part)) {
      const text = boundEventText(part.thinking);
      if (text) events.push({ kind: "thinking", text });
      continue;
    }
    if (view.role === "assistant" && isToolCall(part)) {
      const text = boundEventText(summarizeToolCall(part.name, part.arguments));
      if (text) events.push({ kind: "tool", text });
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
