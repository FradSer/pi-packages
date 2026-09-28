/**
 * Per-Work-Item context.
 *
 * A Work Item is durable, but the context behind it was not: reassignment handed
 * a successor prose concatenated by `buildSuccessorHandoff`, and a fork snapshot
 * existed only as a one-off helper. This module makes the context a first-class,
 * bounded part of the Work Item, so a successor receives a structured brief
 * instead of the entire history, and a long-lived Work Item cannot grow without
 * limit.
 *
 * Deliberately no session identifiers. Pi owns session storage and resolves it
 * from the working path, so a Work Item records the path it ran in and leaves
 * resolution to the execution layer. Keeping that boundary is what stops this
 * package from growing a dependency on processes.
 */

import type { BoardTask } from "./types.ts";

/** Default ceiling on one Work Item's retained context, in bytes. */
export const DEFAULT_CONTEXT_BUDGET_BYTES = 64 * 1024;

/** A structured successor brief. Replaces prose concatenation so a reassignment
 * carries the candidate that was checked, what changed, and what is unverified —
 * the fields a recheck actually needs. */
export interface WorkHandoff {
  /** The revision or scoped snapshot the outgoing attempt checked. */
  candidate?: string;
  /** What the outgoing attempt changed, in its own words. */
  delta?: string;
  /** Checks that ran and their outcomes. */
  verification?: string;
  /** Findings the successor must not lose. Prior review findings belong here,
   * outside the result that a reopen clears. */
  priorFindings?: string[];
  /** Work that is known unfinished or unverified. */
  outstanding?: string[];
}

/** A reference to context this Work Item builds on. */
export interface WorkContextRef {
  kind: "work" | "report" | "file";
  /** Work id, report id, or repository-relative path. */
  id: string;
  note?: string;
}

/** The context a Work Item carries, stored on the task record. */
export interface WorkContext {
  /** The Agent workspace this Work ran in. Pi resolves sessions from this path;
   * this package never stores a session id. */
  workspacePath?: string;
  /** Structured successor brief. */
  handoff?: WorkHandoff;
  /** Prior Work, reports, and files this Work builds on. */
  refs?: WorkContextRef[];
  /** Byte ceiling for the retained context. */
  budgetBytes?: number;
}

/** Measure the retained context of one Work Item, so a budget can be enforced
 * rather than merely declared. */
export function workContextBytes(task: Pick<BoardTask, "description" | "result" | "errorMessage"> & { context?: WorkContext }): number {
  const parts = [
    task.description ?? "",
    task.result ?? "",
    task.errorMessage ?? "",
    task.context?.handoff ? JSON.stringify(task.context.handoff) : "",
    ...(task.context?.refs ?? []).map((ref) => `${ref.kind}:${ref.id}${ref.note ?? ""}`),
  ];
  return parts.reduce((total, part) => total + Buffer.byteLength(part, "utf-8"), 0);
}

/** Whether a Work Item's retained context is within its budget. */
export function withinContextBudget(
  task: Pick<BoardTask, "description" | "result" | "errorMessage"> & { context?: WorkContext },
): boolean {
  return workContextBytes(task) <= (task.context?.budgetBytes ?? DEFAULT_CONTEXT_BUDGET_BYTES);
}

/** Clip one text field to a byte budget without splitting a UTF-8 sequence, and
 * say that it was clipped. A silently truncated brief is worse than a shorter one
 * that announces itself. */
export function clipToBytes(text: string, budgetBytes: number): { text: string; clipped: boolean } {
  if (Buffer.byteLength(text, "utf-8") <= budgetBytes) return { text, clipped: false };
  const marker = "\n[context clipped to budget]";
  const room = Math.max(0, budgetBytes - Buffer.byteLength(marker, "utf-8"));
  const buffer = Buffer.from(text, "utf-8").subarray(0, room);
  // A subarray can end mid-sequence; drop the incomplete tail rather than emit a
  // replacement character into a brief someone will read.
  let end = buffer.length;
  while (end > 0 && (buffer[end - 1] & 0xc0) === 0x80) end -= 1;
  if (end > 0 && end < buffer.length) end -= 1;
  return { text: buffer.subarray(0, end).toString("utf-8") + marker, clipped: true };
}

/**
 * Build the successor brief for a reassignment.
 *
 * Bounded on purpose: a successor needs the candidate, the delta, the checks that
 * ran, and what is still unverified — not the outgoing attempt's whole history.
 * Anything over budget is clipped and marked.
 */
export function buildWorkHandoff(input: {
  candidate?: string;
  delta?: string;
  verification?: string;
  priorFindings?: readonly string[];
  outstanding?: readonly string[];
  budgetBytes?: number;
}): { handoff: WorkHandoff; clipped: boolean } {
  const budget = input.budgetBytes ?? DEFAULT_CONTEXT_BUDGET_BYTES;
  const perField = Math.max(256, Math.floor(budget / 5));
  let clipped = false;
  const clip = (value: string | undefined): string | undefined => {
    if (value === undefined) return undefined;
    const result = clipToBytes(value, perField);
    clipped = clipped || result.clipped;
    return result.text;
  };
  const clipList = (values: readonly string[] | undefined): string[] | undefined => {
    if (!values || values.length === 0) return undefined;
    return values.map((value) => clip(value) ?? "");
  };
  const handoff: WorkHandoff = {};
  const candidate = clip(input.candidate);
  const delta = clip(input.delta);
  const verification = clip(input.verification);
  const priorFindings = clipList(input.priorFindings);
  const outstanding = clipList(input.outstanding);
  if (candidate !== undefined) handoff.candidate = candidate;
  if (delta !== undefined) handoff.delta = delta;
  if (verification !== undefined) handoff.verification = verification;
  if (priorFindings !== undefined) handoff.priorFindings = priorFindings;
  if (outstanding !== undefined) handoff.outstanding = outstanding;
  return { handoff, clipped };
}

/** Format a handoff as the text a successor receives. Kept here so the shape of a
 * brief has one definition instead of one per caller. */
export function formatWorkHandoff(handoff: WorkHandoff | undefined): string {
  if (!handoff) return "";
  const sections: string[] = [];
  if (handoff.candidate) sections.push(`=== CANDIDATE CHECKED ===\n${handoff.candidate}`);
  if (handoff.delta) sections.push(`=== CHANGE DELTA ===\n${handoff.delta}`);
  if (handoff.verification) sections.push(`=== VERIFICATION RUN ===\n${handoff.verification}`);
  if (handoff.priorFindings?.length) {
    sections.push(`=== PRIOR FINDINGS (do not lose these) ===\n${handoff.priorFindings.map((f) => `- ${f}`).join("\n")}`);
  }
  if (handoff.outstanding?.length) {
    sections.push(`=== OUTSTANDING / UNVERIFIED ===\n${handoff.outstanding.map((o) => `- ${o}`).join("\n")}`);
  }
  return sections.join("\n\n");
}

/** Normalize context refs: de-duplicate by kind and id, drop empties, and cap the
 * list so a long-lived Work Item cannot accumulate references without bound. */
export const MAX_CONTEXT_REFS = 64;

export function normalizeContextRefs(refs: readonly WorkContextRef[] | undefined): WorkContextRef[] {
  const seen = new Set<string>();
  const result: WorkContextRef[] = [];
  for (const ref of refs ?? []) {
    const id = ref.id.trim();
    if (!id) continue;
    const key = `${ref.kind}:${id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push({ kind: ref.kind, id, ...(ref.note?.trim() ? { note: ref.note.trim() } : {}) });
    if (result.length >= MAX_CONTEXT_REFS) break;
  }
  return result;
}
