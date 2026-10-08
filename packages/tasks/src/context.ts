/**
 * Per-Task context.
 *
 * A Task is durable, but the context behind it was not: reassignment handed a
 * successor prose concatenated by a caller, and a fork snapshot existed only as
 * a one-off helper. This module makes the context a first-class, bounded part of
 * the Task, so a successor receives a structured brief instead of the entire
 * history, and a long-lived Task cannot grow without limit.
 *
 * Deliberately no session identifiers. Pi owns session storage and resolves it
 * from the working path, so a Task records the path it ran in and leaves
 * resolution to the execution layer. Keeping that boundary is what stops this
 * package from growing a dependency on processes.
 */

import type { Task } from "./types.ts";

/** Default ceiling on one Task's retained context, in bytes. */
export const DEFAULT_CONTEXT_BUDGET_BYTES = 64 * 1024;

/** A structured successor brief. Replaces prose concatenation so a reassignment
 *  carries the candidate that was checked, what changed, and what is unverified —
 *  the fields a recheck actually needs. */
export interface TaskHandoff {
  /** The revision or scoped snapshot the outgoing attempt checked. */
  candidate?: string;
  /** What the outgoing attempt changed, in its own words. */
  delta?: string;
  /** Checks that ran and their outcomes. */
  verification?: string;
  /** Findings the successor must not lose. Prior review findings belong here,
   *  outside the result that a reopen clears. */
  priorFindings?: string[];
  /** Work that is known unfinished or unverified. */
  outstanding?: string[];
}

/** A reference to context this Task builds on. */
export interface TaskContextRef {
  kind: "work" | "report" | "file";
  /** Task id, report id, or repository-relative path. */
  id: string;
  note?: string;
}

/** The context a Task carries, stored on the task record. */
export interface TaskContext {
  /** The Agent workspace this Task ran in. Pi resolves sessions from this path;
   *  this package never stores a session id. */
  workspacePath?: string;
  /** Structured successor brief. */
  handoff?: TaskHandoff;
  /** Prior Tasks, reports, and files this Task builds on. */
  refs?: TaskContextRef[];
  /** Byte ceiling for the retained context. */
  budgetBytes?: number;
}

/** Measure the retained context of one Task, so a budget can be enforced
 *  rather than merely declared.
 *
 *  The retained value is what gets measured, not the fields this module happens
 *  to read by name. A budget that counts only the fields it understands is not a
 *  bound: one field it does not understand and the Task is unbounded again while
 *  measuring as empty. That is why the free-text fields a Task keeps beside its
 *  context are measured here too — `verify` is a completion gate a model writes
 *  in its own words, and the tasks file is re-serialized on every change, so an
 *  unmeasured one is paid for on every write as well.
 *
 *  `subject` and `verify` are optional in the shape so a caller measuring a
 *  partial Task is not asked to invent them. */
export function taskContextBytes(
  task: Partial<Pick<Task, "subject" | "description" | "verify" | "result" | "blockedReason" | "failureEvidence">> & {
    context?: TaskContext;
    resources?: readonly string[];
  },
): number {
  const parts = [
    task.subject ?? "",
    task.description ?? "",
    task.verify ?? "",
    task.result ?? "",
    task.blockedReason ?? "",
    task.failureEvidence ?? "",
    // Resource tags are model-supplied free text and are re-serialized into the
    // tasks file on every change, so they are measured with the rest of what a
    // Task retains rather than being the one field a caller can grow for free.
    task.resources === undefined ? "" : JSON.stringify(task.resources),
    task.context === undefined ? "" : JSON.stringify(task.context),
  ];
  return parts.reduce((total, part) => total + Buffer.byteLength(part, "utf-8"), 0);
}

/** Whether a Task's retained context is within its budget. */
export function withinContextBudget(
  task: Partial<Pick<Task, "subject" | "description" | "verify" | "result" | "blockedReason" | "failureEvidence">> & {
    context?: TaskContext;
    resources?: readonly string[];
  },
): boolean {
  return taskContextBytes(task) <= (task.context?.budgetBytes ?? DEFAULT_CONTEXT_BUDGET_BYTES);
}

/** Clip one text field to a byte budget without splitting a UTF-8 sequence, and
 *  say that it was clipped. A silently truncated brief is worse than a shorter one
 *  that announces itself. */
export function clipToBytes(text: string, budgetBytes: number): { text: string; clipped: boolean } {
  if (Buffer.byteLength(text, "utf-8") <= budgetBytes) return { text, clipped: false };
  const marker = "\n[context clipped to budget]";
  const markerBytes = Buffer.byteLength(marker, "utf-8");
  // The clipped flag reports truncation when the notice cannot fit.
  if (budgetBytes < markerBytes) return { text: "", clipped: true };
  const buffer = Buffer.from(text, "utf-8");
  let end = budgetBytes - markerBytes;
  // Inspect the first excluded byte. A continuation byte means the cut splits
  // a character; a leading byte means the preceding character is complete.
  while (end > 0 && (buffer[end] & 0xc0) === 0x80) end -= 1;
  return { text: buffer.subarray(0, end).toString("utf-8") + marker, clipped: true };
}

/**
 * Build the successor brief for a reassignment.
 *
 * Bounded on purpose: a successor needs the candidate, the delta, the checks that
 * ran, and what is still unverified — not the outgoing attempt's whole history.
 * Anything over budget is clipped and marked.
 */
export function buildTaskHandoff(input: {
  candidate?: string;
  delta?: string;
  verification?: string;
  priorFindings?: readonly string[];
  outstanding?: readonly string[];
  budgetBytes?: number;
}): { handoff: TaskHandoff; clipped: boolean } {
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
  const handoff: TaskHandoff = {};
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
 *  brief has one definition instead of one per caller. */
export function formatTaskHandoff(handoff: TaskHandoff | undefined): string {
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
 *  list so a long-lived Task cannot accumulate references without bound. */
export const MAX_CONTEXT_REFS = 64;

export function normalizeContextRefs(refs: readonly TaskContextRef[] | undefined): TaskContextRef[] {
  const seen = new Map<string, TaskContextRef>();
  for (const ref of refs ?? []) {
    const id = ref.id.trim();
    if (!id) continue;
    const key = `${ref.kind}:${id}`;
    const note = ref.note?.trim();
    // First position wins, so a merge keeps the order the Task was built up in.
    // The note is the exception: it is the one field a later write exists to
    // correct, so the most recent non-empty one is kept. Keeping the first note
    // instead would make a corrected note unrecordable for the life of the Task.
    const existing = seen.get(key);
    seen.set(key, existing
      ? { ...existing, ...(note ? { note } : {}) }
      : { kind: ref.kind, id, ...(note ? { note } : {}) });
    if (seen.size >= MAX_CONTEXT_REFS) break;
  }
  return [...seen.values()];
}

const CONTEXT_REF_KINDS = ["work", "report", "file"] as const;

/** The fields a handoff may carry. Closed, because a brief a successor cannot
 *  read is not a brief. */
const HANDOFF_FIELDS = ["candidate", "delta", "verification", "priorFindings", "outstanding"] as const;

/** The fields a context may carry. */
const CONTEXT_FIELDS = ["workspacePath", "handoff", "refs", "budgetBytes"] as const;

/** The outcome of reading a context somebody else wrote. */
export type ContextRead =
  | { ok: true; value: TaskContext }
  | { ok: false; error: string };

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function unknownFields(value: Record<string, unknown>, known: readonly string[]): string[] {
  return Object.keys(value).filter((key) => !known.includes(key));
}

function readString(value: unknown, label: string): { ok: true; value?: string } | { ok: false; error: string } {
  if (value === undefined) return { ok: true };
  if (typeof value !== "string") return { ok: false, error: `${label} must be a string.` };
  const trimmed = value.trim();
  return trimmed ? { ok: true, value: trimmed } : { ok: true };
}

function readStringList(value: unknown, label: string): { ok: true; value?: string[] } | { ok: false; error: string } {
  if (value === undefined) return { ok: true };
  if (!Array.isArray(value)) return { ok: false, error: `${label} must be an array of strings.` };
  // A Set, because this list is merged on every update and `includes` over a
  // list that can hold thousands of findings makes each merge quadratic on the
  // interactive tool path.
  const seen = new Set<string>();
  const list: string[] = [];
  for (const entry of value) {
    if (typeof entry !== "string" || !entry.trim()) {
      return { ok: false, error: `${label} must contain non-empty strings.` };
    }
    const trimmed = entry.trim();
    if (seen.has(trimmed)) continue;
    seen.add(trimmed);
    list.push(trimmed);
  }
  return { ok: true, value: list };
}

/**
 * Read a context written by somebody else — a model, above all.
 *
 * The tool hands its `context` parameter straight to the store, so this is the
 * one place that decides what shape of context the task store can hold. Two things
 * follow from that, and both are refusals rather than repairs:
 *
 * **A field the task store has no definition for is refused.** Repairing it by
 * dropping it would leave the caller believing a brief was recorded when nothing
 * was, and storing it would leave a field in the Task that no reader, no budget,
 * and no successor brief knows how to interpret. The refusal names the field and
 * says where the handoff fields belong, because the one mistake this sees most
 * is a handoff written one level too high.
 *
 * **A handoff field written at the context level is moved, not refused.** The
 * field names are unique to the handoff, so the caller meant the handoff and
 * said it one level too high. Refusing it cost a round trip and taught nothing:
 * the recorded session lost a whole evidence body to this, twice.
 *
 * **A field of the wrong type is refused for the same reason.** The budget is
 * measured in bytes precisely so a value cannot be wrong *and* unmeasured, but a
 * caller that spelled a handoff `handOff` deserves to be told so rather than
 * having its context quietly measure as empty.
 *
 * Refs are the one exception: they are normalized rather than refused, because
 * de-duplication and the cap are what make the list safe to accept at all.
 *
 * The store calls this too, on its own account, for a caller that reached it
 * directly. Checking the top level of a context there was not enough: a
 * misspelled field *inside* a handoff was dropped, and the caller was told its
 * brief had been recorded.
 */
export function normalizeTaskContext(value: unknown): ContextRead {
  if (!isPlainObject(value)) return { ok: false, error: "context must be an object." };
  const misplaced = HANDOFF_FIELDS.filter((field) => value[field] !== undefined);
  const unknown = unknownFields(value, [...CONTEXT_FIELDS, ...HANDOFF_FIELDS]);
  if (unknown.length > 0) {
    return {
      ok: false,
      error: `context has no field named ${unknown.sort().join(", ")}; it carries ${CONTEXT_FIELDS.join(", ")}, and ${HANDOFF_FIELDS.join(", ")} belong inside context.handoff.`,
    };
  }
  const context: TaskContext = {};

  const workspacePath = readString(value.workspacePath, "context.workspacePath");
  if (!workspacePath.ok) return workspacePath;
  if (workspacePath.value) context.workspacePath = workspacePath.value;

  // One source for the handoff, so a field cannot end up in both places. The
  // explicit `handoff` object wins a field the two spell differently, because a
  // caller that wrote both meant the nested one.
  const handoffSource: Record<string, unknown> = {};
  if (value.handoff !== undefined) {
    if (!isPlainObject(value.handoff)) return { ok: false, error: "context.handoff must be an object." };
    Object.assign(handoffSource, value.handoff);
  }
  for (const field of misplaced) {
    if (handoffSource[field] === undefined) handoffSource[field] = value[field];
  }
  if (Object.keys(handoffSource).length > 0) {
    const unknownHandoff = unknownFields(handoffSource, HANDOFF_FIELDS);
    if (unknownHandoff.length > 0) {
      return {
        ok: false,
        error: `context.handoff has no field named ${unknownHandoff.sort().join(", ")}; it carries ${HANDOFF_FIELDS.join(", ")}.`,
      };
    }
    const handoff: TaskHandoff = {};
    for (const field of ["candidate", "delta", "verification"] as const) {
      const read = readString(handoffSource[field], `context.handoff.${field}`);
      if (!read.ok) return read;
      if (read.value) handoff[field] = read.value;
    }
    for (const field of ["priorFindings", "outstanding"] as const) {
      const read = readStringList(handoffSource[field], `context.handoff.${field}`);
      if (!read.ok) return read;
      if (read.value?.length) handoff[field] = read.value;
    }
    context.handoff = handoff;
  }

  if (value.refs !== undefined) {
    if (!Array.isArray(value.refs)) return { ok: false, error: "context.refs must be an array." };
    const refs: TaskContextRef[] = [];
    for (const entry of value.refs) {
      if (!isPlainObject(entry)) return { ok: false, error: "Each context.refs entry must be an object." };
      const unknownRef = unknownFields(entry, ["kind", "id", "note"]);
      if (unknownRef.length > 0) {
        return { ok: false, error: `A context.refs entry has no field named ${unknownRef.sort().join(", ")}.` };
      }
      if (!CONTEXT_REF_KINDS.includes(entry.kind as (typeof CONTEXT_REF_KINDS)[number])) {
        return { ok: false, error: `context.refs kind must be one of ${CONTEXT_REF_KINDS.join(", ")}.` };
      }
      const id = typeof entry.id === "string" ? entry.id : undefined;
      if (id === undefined) return { ok: false, error: "Each context.refs entry needs a string id." };
      const note = readString(entry.note, "context.refs note");
      if (!note.ok) return note;
      refs.push({ kind: entry.kind as TaskContextRef["kind"], id, ...(note.value ? { note: note.value } : {}) });
    }
    context.refs = normalizeContextRefs(refs);
  }

  if (value.budgetBytes !== undefined) {
    // Floored before the guard, not after: `0.5` is not a budget, and flooring it
    // to 0 would leave a Task whose every later update is refused for exceeding
    // a budget of nothing.
    if (typeof value.budgetBytes !== "number" || !Number.isFinite(value.budgetBytes)) {
      return { ok: false, error: "context.budgetBytes must be a positive number of bytes." };
    }
    const bytes = Math.floor(value.budgetBytes);
    if (bytes < 1) return { ok: false, error: "context.budgetBytes must be a positive number of bytes." };
    // Capped at the task set's own default, and that is the whole point of the cap:
    // the budget is the only thing bounding a brief, so a caller able to raise it
    // removes the bound. A Task may be held to a tighter budget than the default
    // and never to a looser one.
    context.budgetBytes = Math.min(bytes, DEFAULT_CONTEXT_BUDGET_BYTES);
  }

  return { ok: true, value: context };
}

/** Whether a normalized context actually carries something.
 *
 *  Key count is not enough: `handoff: {}` has a key and no content, which is the
 *  shape a context collapses to when every value it was given was blank. This is
 *  what the store asks before recording, so that "your brief was recorded" is
 *  never said about a brief that was not.
 */
export function contextCarriesValue(context: TaskContext): boolean {
  if (context.workspacePath !== undefined && context.workspacePath !== "") return true;
  if (context.budgetBytes !== undefined) return true;
  if ((context.refs ?? []).length > 0) return true;
  const handoff = context.handoff;
  if (!handoff) return false;
  return [handoff.candidate, handoff.delta, handoff.verification].some((value) => value !== undefined && value !== "")
    || (handoff.priorFindings?.length ?? 0) > 0
    || (handoff.outstanding?.length ?? 0) > 0;
}

/** Union two finding lists, keeping the order they were recorded in. Absent on
 *  both sides means the field stays absent, so an empty brief has no empty
 *  section.
 *
 *  Linear, and deliberately uncapped: this runs on every update against a list
 *  that can hold thousands of entries, and a count cap here would drop findings —
 *  the one thing the brief exists to carry to a successor. The byte budget is
 *  what bounds the list, and it is enforced on the write that grows it. */
function unionFindings(
  left: readonly string[] | undefined,
  right: readonly string[] | undefined,
): string[] | undefined {
  if (left === undefined && right === undefined) return undefined;
  const seen = new Set<string>();
  const union: string[] = [];
  for (const entry of [...(left ?? []), ...(right ?? [])]) {
    if (seen.has(entry)) continue;
    seen.add(entry);
    union.push(entry);
  }
  return union;
}

/**
 * Fold a newly recorded context into the one a Task already carries.
 *
 * Additive at every level, because the alternative loses what a brief exists to
 * carry. A shallow merge replaces the whole `handoff` when a caller supplies one
 * field of it, so a successor recording its own delta silently dropped the
 * outgoing attempt's `priorFindings` — the one field the brief marks as not to be
 * lost. Findings and outstanding work are therefore unioned, and refs are unioned
 * through the same normalization that caps them.
 *
 * Fields are assigned one at a time rather than spread, so an explicitly
 * undefined value on either side leaves the other side's value alone instead of
 * erasing it.
 */
export function mergeTaskContext(base: TaskContext | undefined, patch: TaskContext): TaskContext {
  const merged: TaskContext = {};
  const workspacePath = patch.workspacePath ?? base?.workspacePath;
  if (workspacePath) merged.workspacePath = workspacePath;
  const budgetBytes = patch.budgetBytes ?? base?.budgetBytes;
  if (budgetBytes !== undefined) merged.budgetBytes = budgetBytes;
  const handoff = mergeTaskHandoff(base?.handoff, patch.handoff);
  if (handoff) merged.handoff = handoff;
  if (base?.refs !== undefined || patch.refs !== undefined) {
    merged.refs = normalizeContextRefs([...(base?.refs ?? []), ...(patch.refs ?? [])]);
  }
  return merged;
}

/** The handoff half of `mergeTaskContext`, with the same additive rule. */
export function mergeTaskHandoff(base: TaskHandoff | undefined, patch: TaskHandoff | undefined): TaskHandoff | undefined {
  if (!base && !patch) return undefined;
  const merged: TaskHandoff = {};
  for (const field of ["candidate", "delta", "verification"] as const) {
    const value = patch?.[field] ?? base?.[field];
    if (value) merged[field] = value;
  }
  const priorFindings = unionFindings(base?.priorFindings, patch?.priorFindings);
  if (priorFindings) merged.priorFindings = priorFindings;
  const outstanding = unionFindings(base?.outstanding, patch?.outstanding);
  if (outstanding) merged.outstanding = outstanding;
  return merged;
}
