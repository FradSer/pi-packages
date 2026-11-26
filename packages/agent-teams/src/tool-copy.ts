/**
 * Human-facing transcript copy for the coordination tools.
 *
 * The model keeps the exact handles it needs — `session:<name>:<spawn>`,
 * `work:<uuid>`, `direct:<uuid>` — in tool content. A person reading the
 * transcript should instead see the Agent name, the text they passed, the Work
 * subject, and a plain state word. `plainText` is the safety net for free-form
 * strings (errors, harness events) whose identifiers cannot be re-derived.
 */

import { contentDetailLines, detailField, displayText, fieldLine, safeDisplayText, scrubHandles } from "@fradser/pi-kit";
import { getTask } from "./state.ts";

/** One rendered lifecycle row: the collapsed line plus its expanded body. */
export interface CoordinationRow {
  subject: string;
  /** Replace the collapsed subject inline, retaining its semantic line breaks. */
  expandedSubject?: string;
  body: string[];
}

/** Package resolver: a known Work handle becomes its subject. Only prefixed
 * handles are machine identifiers; a bare UUID can be a person's own text
 * (a commit, an id under review) and survives verbatim inside kit. */
function workHandle(handle: string): string | undefined {
  return getTask(handle)?.subject;
}

/** Scalar model text only: a renderer must not stringify an object argument
 * into the transcript, and identifiers become the words a person expects. */
export function plainText(value: unknown): string {
  return scrubHandles(value, workHandle)
    .replace(/"\s*"/g, "")
    .replace(/[ \t]+([.,;:!?])/g, "$1");
}

function collapse(value: unknown): string {
  return displayText(value).replace(/\s+/g, " ").trim();
}

function oneLine(value: unknown): string {
  return collapse(plainText(value));
}

function clipLines(value: unknown): string {
  return displayText(value).split("\n").map((line) => plainText(line)).join("\n");
}

/** The first non-empty line, on one line: a title. The row's own width fit
 * bounds it and expansion reveals the whole value, so no character cap here. */
function headline(value: unknown): string {
  const text = displayText(value);
  const firstLine = text.split("\n").map((l) => plainText(l).trim()).find(Boolean) ?? "";
  return collapse(firstLine);
}

function labeled(label: string, value: unknown): string {
  return fieldLine(label, oneLine(value));
}

function bodyLines(value: unknown): string[] {
  return contentDetailLines({ content: [{ type: "text", text: clipLines(value) }] })
    .map((line) => dedupeSegments(collapse(line)))
    .filter(Boolean);
}

/** Scrubbing a Work id into its subject can repeat what the line already says. */
function dedupeSegments(line: string): string {
  const parts = line.split(" · ");
  return parts.filter((part, index) => parts.indexOf(part) === index).join(" · ");
}

const STATUS_WORDS: Record<string, string> = {
  starting: "starting",
  working: "working",
  idle: "idle",
  stopped: "stopped",
  pending: "pending",
  in_progress: "in progress",
  completed: "completed",
  superseded: "superseded",
  sent: "sent",
  routed: "delivered",
  queued: "queued",
  "not-sent": "not delivered",
  "fresh-session-pending": "waiting for a fresh session",
  created: "created",
  assigned: "assigned",
  released: "released",
  reopened: "reopened",
  listed: "listed",
};

function stateWord(value: unknown): string {
  const key = oneLine(value);
  return STATUS_WORDS[key] ?? key.replace(/[_-]+/g, " ");
}

// ── agent_event ───────────────────────────────────────────────────

/** One `agent_event` row: who receives it and what was actually said. */
export function messageRow(
  args: { to?: string; body?: string; kind?: string },
  details: unknown,
  options: { isError?: boolean } = {},
): CoordinationRow {
  const to = oneLine(detailField<string>(details, "to") ?? args.to ?? "leader").replace(/^@+/, "");
  const outcome = detailField<string>(details, "outcome");
  // Messages are literal readbacks, not prose to clean up. Only terminal
  // controls and runtime handles change; the shared renderer owns truncation.
  const message = scrubHandles(safeDisplayText(displayText(args.body)), workHandle);
  const prefix = [`to @${to}`, options.isError ? "failed" : outcome ? stateWord(outcome) : undefined]
    .filter(Boolean).join(" · ");
  return {
    subject: [prefix, collapse(message)].filter(Boolean).join(" · "),
    expandedSubject: [prefix, message].filter(Boolean).join(" · "),
    body: detailField<string>(details, "terminalReport") ? [labeled("note", "terminal report recorded for this Work")] : [],
  };
}

// ── worker surfaces ───────────────────────────────────────────────

/** One worker `work` row: the task subject leads, never the task id. */
export function workerWorkRow(
  args: { action?: string; id?: string },
  details: unknown,
  content: string,
  flags: { isError?: boolean } = {},
): CoordinationRow {
  const action = String(args.action ?? detailField<string>(details, "action") ?? "work");
  const owned = detailField<string>(details, "taskId") ?? detailField<string>(details, "id");
  const subject = detailField<string>(details, "subject") ?? (owned ? getTask(owned)?.subject : undefined);
  const outcome = detailField<string>(details, "outcome") ?? detailField<string>(details, "status");
  const leads = action === "claim" && !args.id
    ? "next claimable Work"
    : action === "list" || action === "submit" || action === "release"
      ? "current Work"
      : undefined;
  return {
    subject: `${headline(subject ?? leads ?? "Work")} · ${flags.isError ? "failed" : workerStateWord(action, outcome)}`,
    body: bodyLines(content).slice(1),
  };
}

const WORKER_QUEUE_WORDS: Record<string, string> = {
  claim: "claim queued",
  submit: "submission queued",
  release: "released",
  list: "listed",
};

function workerStateWord(action: string, outcome: string | undefined): string {
  if (outcome === "queued") return WORKER_QUEUE_WORDS[action] ?? "queued";
  return stateWord(outcome ?? action);
}

/** Render-ready body for a failed call, whose details never reach the renderer. */
export function failureBody(result: { content: Array<{ type: string; text?: string }> }): string[] {
  return bodyLines(result.content.find((part) => part.type === "text")?.text ?? "");
}
