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

import type { ToolLifecycleSpec } from "@fradser/pi-kit";
import type { WorkerUsage } from "./types.ts";

/** Custom message type carrying one delivered Session Result. */
export const SESSION_RESULT_MESSAGE_TYPE = "subagents-session-result";

/** Custom message type announcing a Work Session that ended without one. */
export const SESSION_ENDED_MESSAGE_TYPE = "subagents-session-ended";

/** One Work Session's settled output, for one turn of one incarnation. */
export interface SessionResultNotice {
  kind: "result";
  name: string;
  /** The exact incarnation that produced it, so a stale result is attributable. */
  session: string;
  /** 1-based count of settled turns this incarnation has reported. */
  turn: number;
  /** The child's final answer, verbatim. */
  text: string;
  usage?: WorkerUsage;
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

export type SessionNotice = SessionResultNotice | SessionEndedNotice;

/** What the loaded entry hands the library: send one notice to the session. */
export type SessionNoticeSender = (notice: SessionNotice) => void;

function escapeAttribute(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function timestampAttribute(value: number): string {
  return Number.isFinite(value) ? ` at="${new Date(value).toISOString()}"` : "";
}

/**
 * The text a model reads. The child's own words are the body; the envelope only
 * says which Agent and incarnation produced them. Nothing summarises, annotates,
 * or reorders what the child wrote.
 *
 * Verbatim means verbatim: a child's text containing a closing envelope tag
 * ends the envelope early. Fencing that would rewrite the child's words, which
 * is the one thing this delivery must not do, so the risk is recorded here
 * instead of papered over.
 */
export function formatSessionResult(notice: SessionResultNotice): string {
  return [
    `<agent-result from="${escapeAttribute(notice.name)}" session="${escapeAttribute(notice.session)}" turn="${notice.turn}"${timestampAttribute(notice.deliveredAt)}>`,
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

/** Content of one notice, whichever kind it is. */
export function formatSessionNotice(notice: SessionNotice): string {
  return notice.kind === "result" ? formatSessionResult(notice) : formatSessionEnded(notice);
}

export function sessionNoticeMessageType(notice: SessionNotice): string {
  return notice.kind === "result" ? SESSION_RESULT_MESSAGE_TYPE : SESSION_ENDED_MESSAGE_TYPE;
}

/** The first line of a result: what a person reads before expanding anything. */
function headline(text: string): string {
  const line = text.trim().split("\n").find((entry) => entry.trim()) ?? "";
  return line.length > 200 ? `${line.slice(0, 197)}…` : line;
}

/**
 * The row one notice paints.
 *
 * A result leads with what the child said, because that is the reason the
 * message exists; its provenance is in the envelope and the details, never in
 * the headline. An ended Work Session is painted on the error band: it is a
 * failure a person must be able to spot while scrolling.
 */
export function sessionNoticeSpec(notice: SessionNotice): ToolLifecycleSpec {
  if (notice.kind === "ended") {
    return {
      kind: "event",
      tool: "agent",
      subject: `@${notice.name}`,
      label: "ended",
      summary: [notice.reason],
      details: ["note · no Session Result was produced; list the children for the exit detail"],
      bgToken: "toolErrorBg",
    };
  }
  return {
    kind: "event",
    tool: "agent",
    subject: `@${notice.name}`,
    label: "reported",
    summary: [headline(notice.text)],
    // Expansion reveals the whole answer: the collapsed row shows what the child
    // concluded, and a reader who needs the reasoning gets all of it.
    details: notice.text.trim().split("\n").slice(1),
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
  if (kind !== "result" && kind !== "ended") return undefined;
  if (typeof value.name !== "string" || typeof value.session !== "string") return undefined;
  const deliveredAt = typeof value.deliveredAt === "number" ? value.deliveredAt : Date.now();
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
  return {
    kind: "result",
    name: value.name,
    session: value.session,
    turn: typeof value.turn === "number" ? value.turn : 1,
    text: value.text,
    ...(value.usage && typeof value.usage === "object" ? { usage: value.usage as WorkerUsage } : {}),
    deliveredAt,
  };
}
