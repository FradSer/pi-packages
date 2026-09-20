/**
 * The Desk Link wire contract, version 1.
 *
 * A Desk Link carries one Reporting Machine's Reported Sessions to one
 * Open DeskOS runtime. Records are newline-delimited JSON over one connection
 * the package opens; Open DeskOS never reaches back to this machine.
 */

export const DESK_LINK_PROTOCOL = 1;

/** Event bounds, identical to the runtime's local session collector. */
export const MAX_EVENTS_PER_SESSION = 300;
export const MAX_EVENT_TEXT = 200;
/** Every event keeps the body Pi produced, bounded per kind. */
export const MAX_RESULT_BYTES = 65536;
export const MAX_MESSAGE_BYTES = 16384;
export const MAX_USER_BYTES = 8192;
export const MAX_THINKING_BYTES = 4096;
export const MAX_TOOL_BYTES = 4096;
export const MAX_SESSION_EVENT_BYTES = 1048576;

export type SessionStatus = "running" | "settled" | "exited";

export type SessionEventKind = "user" | "thinking" | "tool" | "result" | "assistant";

/** A short activity summary, or a bounded multiline Markdown result body. */
export interface SessionEvent {
  kind: SessionEventKind;
  text: string;
  /** Result-only label, kept outside the Markdown body. */
  toolName?: string;
  /** Present only when a result or assistant body was shortened. */
  /** Present only when the event body was shortened by its kind's limit. */
  truncated?: true;
}

/** One session as the Reporting Machine describes it. */
export interface ReportedSession {
  sessionId: string;
  /** Inventory provenance; an active direct reporter takes precedence. */
  discovered?: true;
  name?: string;
  cwd: string;
  workspaceName: string;
  status: SessionStatus;
  startedAt: number;
  updatedAt: number;
  latestGoal?: string;
  activity?: string;
}

export interface DeskLinkConfig {
  /** Reporting machine identity, as shown on the desk. */
  machine: string;
  host: string;
  port: number;
  token: string;
  /** Independent Control Credential. It is used only as an HMAC key. */
  controlToken?: string;
}

export type HostedPiStatus = "pending" | "running" | "settled" | "finished" | "failed" | "cancelled" | "interrupted";
export type HostedPiLifecycle = "launching" | "live" | "ended" | "interrupted";
export type HostedPiTurnOutcome = "finished" | "failed" | "cancelled" | "interrupted";

export interface HostedPiSession {
  sessionId: string;
  status: HostedPiStatus;
  lifecycle?: HostedPiLifecycle;
  activityState?: "working" | "idle";
  turnOutcome?: HostedPiTurnOutcome;
  project?: string;
  cwd?: string;
  workspaceName?: string;
  goal?: string;
  latestGoal?: string;
  activity?: string;
  startedAt?: number;
  updatedAt?: number;
}

export interface PositionedSessionEvent {
  position: number;
  /** Every Session Event derived from one complete Pi session-log entry. */
  events: SessionEvent[];
}

export interface HistoryPage {
  sessionId?: string;
  entries: PositionedSessionEvent[];
  nextPosition: number | null;
  boundary?: number;
  oversized?: boolean;
}

export interface HelloRecord {
  v: typeof DESK_LINK_PROTOCOL;
  type: "hello";
  machine: string;
  token: string;
}

export interface SessionsRecord {
  v: typeof DESK_LINK_PROTOCOL;
  type: "sessions";
  machine: string;
  sessions: ReportedSession[];
}

/** Append-only events; a new connection replays the bounded retained tail. */
export interface EventsRecord {
  v: typeof DESK_LINK_PROTOCOL;
  type: "events";
  machine: string;
  sessionId: string;
  events: SessionEvent[];
}

export interface ByeRecord {
  v: typeof DESK_LINK_PROTOCOL;
  type: "bye";
  machine: string;
}

export type DeskLinkRecord = HelloRecord | SessionsRecord | EventsRecord | ByeRecord;

/**
 * The message parts this package reads. Pi streams these shapes for user,
 * assistant, and tool-result messages; the reporter only needs the parts it
 * turns into Session Events.
 */
export interface TextPart {
  type: "text";
  text: string;
}

export interface ThinkingPart {
  type: "thinking";
  thinking: string;
}

export interface ToolCallPart {
  type: "toolCall";
  name: string;
  arguments: unknown;
}
