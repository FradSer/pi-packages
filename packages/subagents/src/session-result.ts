/**
 * Session Result: the settled output one Work Session turn produced, handed back
 * to the Leader's session.
 *
 * A child answers inside its own process, so that answer has to be carried out
 * deliberately or it is lost at the moment it exists. The spawner already knows
 * when a turn settled; this module owns what a settle *means* to the Leader's
 * session — the message shape, its content, and the row a person reads — so the
 * decision of whether a given frame is a delivery stays with the caller that
 * owns the Work Session.
 *
 * **Why the execution layer delivers at all.** `@fradser/pi-agent-teams` can
 * deliver reports, and does when it owns the spawn. Installing this package
 * alone is the configuration its manifest advertises and its README documents,
 * and there a child's work would otherwise leave the session at the moment the
 * `agent` tool's description promised it would arrive. See ADR-0007.
 *
 * TUI-free by construction: the rows are pi-kit lifecycle *specs*, and the
 * geometry that paints one is bound by whoever is painting. The sender is
 * injected, because a tool's execution context has no `sendMessage` and the
 * loaded extension entry is the only layer holding the session API.
 */

import { safeDisplayText, type ToolLifecycleSpec } from "@fradser/pi-kit";
import type { AgentUsage } from "./types.ts";

/** Custom message type carrying one delivered Session Result. */
export const SESSION_RESULT_MESSAGE_TYPE = "subagents-session-result";

/** Custom message type announcing a Work Session that ended without one. */
export const SESSION_ENDED_MESSAGE_TYPE = "subagents-session-ended";

/** A settled sequence has no usable complete final answer; the process may remain IDLE. */
export const SESSION_UNANSWERED_MESSAGE_TYPE = "subagents-session-unanswered";
export const INPUT_CANCELLED_MESSAGE_TYPE = "subagents-input-cancelled";
export type UnansweredReason = "empty" | "error" | "aborted" | "length" | "incomplete" | "missing-final";
export type FinalStopReason = "pending" | "stop" | "length" | "toolUse" | "error" | "aborted" | "deferred" | "unknown";
const FINAL_STOP_REASONS: readonly FinalStopReason[] = ["pending", "stop", "length", "toolUse", "error", "aborted", "deferred", "unknown"];

/** Stop reasons are protocol tokens, never arbitrary provider diagnostic text. */
export function normalizeFinalStopReason(value: unknown): FinalStopReason | undefined {
  if (value === undefined) return undefined;
  return FINAL_STOP_REASONS.find(reason => reason === value) ?? "unknown";
}

export interface FinalAnswerEvidence {
  text: string;
  stopReason?: string;
  errorMessage?: string;
  hasToolCalls?: boolean;
  missingFinal?: boolean;
}

/** Syntactic execution outcome only, never semantic review/acceptance judgment. */
export function unansweredReason(evidence: FinalAnswerEvidence): UnansweredReason | undefined {
  const stopReason = normalizeFinalStopReason(evidence.stopReason);
  if (stopReason === "error" || stopReason === "aborted" || stopReason === "length") return stopReason;
  if (evidence.missingFinal) return "missing-final";
  if (evidence.hasToolCalls || (stopReason !== undefined && stopReason !== "stop")) return "incomplete";
  return evidence.text.trim() ? undefined : "empty";
}

/** Provider diagnostics are not final-answer bytes; keep their UI/context budget explicit. */
export function boundedFinalDiagnostic(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const safe = safeDisplayText(value);
  if (safe.length <= 1000) return safe;
  // `String#slice` counts UTF-16 code units. Keep a surrogate pair together at
  // the diagnostic boundary so a provider error cannot become malformed text
  // when it is read back or rendered.
  const end = safe.length > 1000
    && safe.charCodeAt(999) >= 0xd800 && safe.charCodeAt(999) <= 0xdbff
    && safe.charCodeAt(1000) >= 0xdc00 && safe.charCodeAt(1000) <= 0xdfff
    ? 999
    : 1000;
  return `${safe.slice(0, end)}… [diagnostic truncated]`;
}

export interface SessionUnansweredNotice {
  kind: "unanswered";
  inputId?: string;
  name: string;
  session: string;
  turn: number;
  reason: UnansweredReason;
  /** Original output, including whitespace or partial text, never shortened. */
  text: string;
  stopReason?: string;
  errorMessage?: string;
  usage?: AgentUsage;
  deliveredAt: number;
}

export function unansweredSummary(notice: Pick<SessionUnansweredNotice, "reason" | "stopReason">): string {
  const explanation: Record<UnansweredReason, string> = {
    empty: "The completed assistant message contained no final text.",
    error: "The provider failed before producing a complete final answer.",
    aborted: "Execution was aborted before a complete final answer.",
    length: "The response reached its length limit; any text is partial evidence.",
    incomplete: "Execution settled with an unfinished response or tool call.",
    "missing-final": "Execution settled without a completed assistant message.",
  };
  const stopReason = normalizeFinalStopReason(notice.stopReason);
  return `No usable final answer. ${explanation[notice.reason]}${stopReason ? ` Stop reason: ${stopReason}.` : ""}`;
}

/** One Work Session's settled output, for one turn of one incarnation. */
export interface SessionResultNotice {
  kind: "result";
  inputId?: string;
  name: string;
  /** The exact incarnation that produced it, so a stale result is attributable. */
  session: string;
  /** 1-based count of settled turns this incarnation has reported. */
  turn: number;
  /** The child's final answer, verbatim. */
  text: string;
  usage?: AgentUsage;
  deliveredAt: number;
}

/** A Work Session that ended without ever producing a Session Result. */
export interface SessionEndedNotice {
  kind: "ended";
  name: string;
  session: string;
  /** What ended it, in one line: signal, exit code, or the spawn error. */
  reason: string;
  deliveredAt: number;
}

export interface InputCancelledNotice {
  kind: "input-cancelled";
  name: string;
  session: string;
  inputId: string;
  reason: string;
  deliveredAt: number;
}
export type SessionNotice = SessionResultNotice | SessionUnansweredNotice | SessionEndedNotice | InputCancelledNotice;

/** What the loaded entry hands the library: send one notice to the session. */
export type SessionNoticeSender = (notice: SessionNotice) => void;

function escapeAttribute(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function inputAttribute(notice: { inputId?: string }): string {
  return notice.inputId ? ` input="${escapeAttribute(notice.inputId)}"` : "";
}

function timestampAttribute(value: number): string {
  return validTimestamp(value) ? ` at="${new Date(value).toISOString()}"` : "";
}

// Date#toISOString throws outside ECMAScript's representable time range even
// when the input is finite. Delivered notice metadata is untrusted, so reject
// those values before a renderer turns a readback into an exception.
const MAX_DATE_MILLISECONDS = 8_640_000_000_000_000;

function validTimestamp(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value)
    && Math.abs(value) <= MAX_DATE_MILLISECONDS;
}

/**
 * The text a model reads. The child's own words are the body; the envelope only
 * says which Agent and incarnation produced them. Nothing summarises, annotates,
 * or reorders what the child wrote.
 *
 * The envelope opens with one fact the child's words cannot carry: that it is
 * still IDLE and addressable. A settled turn is not a closed process, and the
 * Leader is the only actor that can act on it — without this line the cheapest
 * reading of a result is that the work is over and the next step needs a new
 * child, which is one whole process spent on an incarnation that was still up.
 * It stays inside the envelope, ahead of the body, so the child's bytes remain
 * the tail of the message and the two live delivery tests that assert exactly
 * that keep holding.
 *
 * Verbatim means verbatim: a child's text containing a closing envelope tag
 * ends the envelope early. Fencing that would rewrite the child's words, which
 * is the one thing this delivery must not do, so the risk is recorded here
 * instead of papered over.
 */
export function formatSessionResult(notice: SessionResultNotice): string {
  return [
    `<agent-result from="${escapeAttribute(notice.name)}" session="${escapeAttribute(notice.session)}" turn="${notice.turn}"${inputAttribute(notice)}${timestampAttribute(notice.deliveredAt)}>`,
    "This child is still IDLE at the session above: continue dependent work with agent_input on that exact session. This result is execution evidence, not acceptance.",
    notice.text,
    "</agent-result>",
  ].join("\n");
}

/** The text behind an ended notice. Never delivered with a triggered turn, so
 *  this is written for a person reading the transcript, not for a model. */
export function formatSessionEnded(notice: SessionEndedNotice): string {
  return [
    `<agent-result-ended from="${escapeAttribute(notice.name)}" session="${escapeAttribute(notice.session)}"${timestampAttribute(notice.deliveredAt)}>`,
    `The Work Session ended without producing a Session Result. ${notice.reason}`,
    "Its error detail is on the roster: list the children to read it.",
    "</agent-result-ended>",
  ].join("\n");
}

/** Nonempty transport failure report, without inventing or rewriting a child verdict. */
export function formatSessionUnanswered(notice: SessionUnansweredNotice): string {
  const stopReason = normalizeFinalStopReason(notice.stopReason);
  return [
    `<agent-result-unanswered from="${escapeAttribute(notice.name)}" session="${escapeAttribute(notice.session)}" turn="${notice.turn}"${inputAttribute(notice)} reason="${notice.reason}"${stopReason ? ` stop-reason="${stopReason}"` : ""}${timestampAttribute(notice.deliveredAt)}>`,
    unansweredSummary(notice),
    ...(notice.errorMessage ? [`Diagnostic: ${boundedFinalDiagnostic(notice.errorMessage)}`] : []),
    "This is not a review verdict or acceptance. The resident can receive explicit input; no new task input or replacement was launched after settlement.",
    "Original output follows verbatim:",
    notice.text,
    "</agent-result-unanswered>",
  ].join("\n");
}

/** Content of one notice, whichever kind it is. */
export function formatSessionNotice(notice: SessionNotice): string {
  if (notice.kind === "result") return formatSessionResult(notice);
  if (notice.kind === "input-cancelled") return `<agent-input-cancelled from="${escapeAttribute(notice.name)}" session="${escapeAttribute(notice.session)}"${inputAttribute(notice)}>\n${boundedFinalDiagnostic(notice.reason) ?? "The queued input was cancelled."}\n</agent-input-cancelled>`;
  return notice.kind === "unanswered" ? formatSessionUnanswered(notice) : formatSessionEnded(notice);
}

export function sessionNoticeMessageType(notice: SessionNotice): string {
  if (notice.kind === "result") return SESSION_RESULT_MESSAGE_TYPE;
  return notice.kind === "input-cancelled" ? INPUT_CANCELLED_MESSAGE_TYPE
    : notice.kind === "unanswered" ? SESSION_UNANSWERED_MESSAGE_TYPE : SESSION_ENDED_MESSAGE_TYPE;
}

/**
 * The row one notice paints.
 *
 * A result leads with what the child said, because that is the reason the
 * message exists; its provenance stays in the envelope and machine details,
 * not in a duplicated display body. An ended Work Session is painted on the error band: it is a
 * failure a person must be able to spot while scrolling.
 */
export function sessionNoticeSpec(notice: SessionNotice): ToolLifecycleSpec {
  // One rule for every child notice: the collapsed row says who reported and what
  // happened, and the payload waits for expansion. A result row that prints its
  // own answer spends the reader's line on text they did not ask for, and the
  // rest of the surface would then look inconsistent beside it.
  if (notice.kind === "input-cancelled") return {
    kind: "event", tool: "agent", subject: `@${notice.name}`, label: "input cancelled",
    summary: [],
    details: [notice.reason, `input · ${notice.inputId}`], bgToken: "toolErrorBg",
  };
  if (notice.kind === "ended") {
    return {
      kind: "event",
      tool: "agent",
      subject: `@${notice.name}`,
      label: "ended",
      summary: [],
      details: [notice.reason, "note · no Session Result was produced; list the children for the exit detail"],
      bgToken: "toolErrorBg",
    };
  }
  if (notice.kind === "unanswered") {
    return {
      kind: "event", tool: "agent", subject: `@${notice.name}`, label: "unanswered",
      summary: [],
      details: [unansweredSummary(notice), `unanswered execution · turn ${notice.turn}`,
        ...(notice.errorMessage ? [`diagnostic · ${boundedFinalDiagnostic(notice.errorMessage)}`] : []),
        "no review verdict or acceptance was produced.", ...notice.text.split("\n")],
      bgToken: "toolErrorBg",
    };
  }
  return {
    kind: "event",
    tool: "agent",
    subject: `@${notice.name}`,
    label: "reported",
    // The authored answer is the payload and stays Markdown, but the collapsed row
    // is the headline alone: the head identifies the child, and the reader who
    // wants the verdict opens the row. Turn and session stay machine metadata.
    summary: [notice.text],
    summaryFormat: "markdown",
    expandedSummary: true,
    details: [],
  };
}

/**
 * The row for a message that carries no readable notice.
 *
 * Distinct from a notice on purpose: a fallback that pretends to be an ended
 * Work Session would say a child died when in fact a host handed us something
 * we cannot read. It says only what is true.
 */
export function unreadableSessionNoticeSpec(): ToolLifecycleSpec {
  return {
    kind: "event",
    tool: "agent",
    subject: "a delivered message",
    label: "unreadable",
    summary: ["It carried no Session Result details."],
  };
}

/** Extract the notice from a delivered message's details, or undefined when the
 *  message is not one of ours. The renderer is handed untyped details, so every
 *  field is checked rather than assumed. */
export function readSessionNotice(details: unknown): SessionNotice | undefined {
  const value = details as Record<string, unknown> | undefined;
  if (!value || typeof value !== "object") return undefined;
  const kind = value.kind;
  if (kind !== "result" && kind !== "unanswered" && kind !== "ended" && kind !== "input-cancelled") return undefined;
  if (typeof value.name !== "string" || typeof value.session !== "string") return undefined;
  if (value.deliveredAt !== undefined && !validTimestamp(value.deliveredAt)) return undefined;
  const deliveredAt = typeof value.deliveredAt === "number" ? value.deliveredAt : Date.now();
  if (kind === "input-cancelled") return typeof value.inputId === "string" && typeof value.reason === "string"
    ? { kind, name: value.name, session: value.session, inputId: value.inputId, reason: value.reason, deliveredAt } : undefined;
  if (kind === "ended") {
    return {
      kind: "ended",
      name: value.name,
      session: value.session,
      reason: typeof value.reason === "string" ? value.reason : "The Work Session ended.",
      deliveredAt,
    };
  }
  if (typeof value.text !== "string") return undefined;
  if (value.turn !== undefined && (typeof value.turn !== "number" || !Number.isSafeInteger(value.turn) || value.turn < 1)) return undefined;
  if (kind === "unanswered") {
    const reasons: readonly UnansweredReason[] = ["empty", "error", "aborted", "length", "incomplete", "missing-final"];
    const reason = reasons.find(reason => reason === value.reason);
    if (!reason) return undefined;
    return { kind, name: value.name, session: value.session, reason,
      turn: typeof value.turn === "number" ? value.turn : 1, text: value.text,
      ...(typeof value.inputId === "string" ? { inputId: value.inputId } : {}),
      ...(value.stopReason !== undefined ? { stopReason: normalizeFinalStopReason(value.stopReason) } : {}),
      ...(typeof value.errorMessage === "string" ? { errorMessage: boundedFinalDiagnostic(value.errorMessage) } : {}),
      ...(value.usage && typeof value.usage === "object" ? { usage: value.usage as AgentUsage } : {}), deliveredAt };
  }
  return {
    kind: "result",
    name: value.name,
    session: value.session,
    turn: typeof value.turn === "number" ? value.turn : 1,
    text: value.text,
    ...(typeof value.inputId === "string" ? { inputId: value.inputId } : {}),
    ...(value.usage && typeof value.usage === "object" ? { usage: value.usage as AgentUsage } : {}),
    deliveredAt,
  };
}
