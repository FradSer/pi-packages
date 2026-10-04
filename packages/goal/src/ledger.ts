/**
 * The goal ledger: an append-only JSONL record of every lifecycle transition.
 *
 * The record file holds current state and is replaceable; the ledger holds what
 * happened and is never rewritten. That split is what makes a goal survivable
 * across compaction and restart: state can always be rebuilt from the ledger
 * when a record is lost, and history can be read without loading state.
 *
 * Storage is pi-kit's `appendJsonlLine` and `readJsonlBatch`. pi-kit owns the
 * byte caps, the private directory and owner-only file modes, the offset cursor,
 * and the malformed-record diagnostics, so this module owns only the event
 * vocabulary and the projection onto it.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import {
  appendJsonlLine,
  readJsonlBatch,
  type JsonlBatch,
} from "@fradser/pi-kit";
import { ARCHIVED_GOALS_DIR, GOALS_DIR, safeGoalId } from "./paths.ts";
import type { GoalRecord, StopReason } from "./record.ts";

/**
 * Every event the ledger can hold. The union is the schema: a reader that does
 * not recognize a `type` is reading a ledger from a newer version, which the
 * store treats as unreadable rather than as empty.
 */
export type GoalLedgerEvent =
  | { type: "goal_created"; goalId: string; objective: string; autoContinue: boolean; at: string }
  | { type: "research_attached"; goalId: string; focus: string; tokens: number; at: string }
  | { type: "goal_focused"; goalId: string; reason: string; at: string }
  | { type: "goal_unfocused"; goalId: string | null; at: string }
  | { type: "goal_paused"; goalId: string; reason: string; stopReason: StopReason; at: string }
  | { type: "goal_resumed"; goalId: string; reason: string; at: string }
  | { type: "goal_claimed"; goalId: string; dispatchId: string; run: number; at: string }
  | { type: "goal_blocked"; goalId: string; reason: string; at: string }
  | { type: "goal_tweaked"; goalId: string; changeSummary: string; at: string }
  | { type: "goal_budget_warning"; goalId: string; remaining: number; at: string }
  | { type: "goal_budget_limited"; goalId: string; tokenBudget: number; at: string }
  | { type: "goal_cleared"; goalId: string; reason: string; at: string }
  | { type: "goal_archived"; goalId: string; archivePath: string; at: string }
  | { type: "completion_refused"; goalId: string; attempts: number; report: string; advice: string; at: string }
  | { type: "completion_requested"; goalId: string; summary?: string; at: string }
  | { type: "check_started"; goalId: string; model?: string; at: string }
  | { type: "check_result"; goalId: string; met: boolean; report: string; at: string }
  | { type: "check_deferred"; goalId: string; report: string; at: string }
  | { type: "check_skipped"; goalId: string; reason: string; at: string }
  | { type: "goal_completed"; goalId: string; archivePath: string; at: string };

export type GoalLedgerEventType = GoalLedgerEvent["type"];

/**
 * One goal's ledger. Reading is paged by byte offset, so a caller that only
 * wants the recent tail never materializes the whole history.
 *
 * `archived` matters: archiving moves the whole goal directory, history
 * included, so an append aimed at the open path afterwards would recreate an
 * empty directory beside the archive and split one goal's history in two.
 */
export function ledgerPath(projectRoot: string, goalId: string, archived = false): string {
  const base = archived ? ARCHIVED_GOALS_DIR : GOALS_DIR;
  return path.join(projectRoot, base, safeGoalId(goalId), "ledger.jsonl");
}

/**
 * Append one event.
 *
 * Appends happen after the authoritative record write, so a failed record write
 * leaves no event. A ledger append that fails after a successful write is
 * surfaced as a diagnostic rather than rolled back: the state transition is
 * real, and discarding it because history could not be written would be a worse
 * lie than a gap in history.
 */
export function appendGoalEvent(projectRoot: string, event: GoalLedgerEvent, archived = false): string | undefined {
  try {
    appendJsonlLine(ledgerPath(projectRoot, event.goalId ?? "pool", archived), event, { label: "Goal ledger event" });
    return undefined;
  } catch (error) {
    return `ledger append failed for ${event.type}: ${error instanceof Error ? error.message : String(error)}`;
  }
}

export function appendGoalEvents(projectRoot: string, events: GoalLedgerEvent[], archived = false): string[] {
  const diagnostics: string[] = [];
  for (const event of events) {
    const diagnostic = appendGoalEvent(projectRoot, event, archived);
    if (diagnostic) diagnostics.push(diagnostic);
  }
  return diagnostics;
}

/** One page of history plus where to resume. */
export interface GoalHistoryPage {
  events: GoalLedgerEvent[];
  /** Opaque continuation cursor, or undefined at the end. */
  cursor?: string;
  diagnostics: string[];
}

export function readGoalLedger(projectRoot: string, goalId: string, maxBytes?: number, archived = false): GoalLedgerEvent[] {
  const batch = maxBytes === undefined
    ? readJsonlBatch(ledgerPath(projectRoot, goalId, archived), 0)
    : readJsonlBatch(ledgerPath(projectRoot, goalId, archived), 0, Number.POSITIVE_INFINITY, maxBytes);
  return batch.records.filter(isGoalLedgerEvent);
}

/**
 * Read the next page after `cursor`.
 *
 * The cursor is the byte offset pi-kit already tracks. It is passed through
 * base64url because an offset is an implementation detail of the storage, and a
 * persisted or model-supplied cursor should not be able to address the file any
 * other way.
 */
export function readGoalHistoryPage(projectRoot: string, goalId: string, cursor?: string, maxBytes?: number, archived = false): GoalHistoryPage {
  const file = ledgerPath(projectRoot, goalId, archived);
  if (!fs.existsSync(file)) return { events: [], diagnostics: [] };
  const offset = decodeCursor(cursor);
  const batch: JsonlBatch = maxBytes === undefined
    ? readJsonlBatch(ledgerPath(projectRoot, goalId, archived), offset)
    : readJsonlBatch(ledgerPath(projectRoot, goalId, archived), offset, Number.POSITIVE_INFINITY, maxBytes);
  const events: GoalLedgerEvent[] = [];
  const rejected: string[] = [];
  for (const record of batch.records) {
    if (isGoalLedgerEvent(record)) events.push(record);
    // pi-kit reports records that are not valid JSON. A record that parses but
    // is not an event is a different failure — corruption, or a ledger written
    // by a newer version — and it is reported here so a reader never silently
    // loses an event it could not interpret.
    else rejected.push(`${goalId}: unrecognized ledger record was consumed`);
  }
  const page: GoalHistoryPage = {
    events,
    diagnostics: [...batch.diagnostics.map((diagnostic) => `${goalId}: ${diagnostic}`), ...rejected],
  };
  // The end of the file is offset + bytes read, which pi-kit reports as
  // `nextOffset`. Reaching it exactly means there is nothing left to page.
  const size = fs.statSync(file, { throwIfNoEntry: false })?.size ?? Number.POSITIVE_INFINITY;
  if (batch.nextOffset < size) page.cursor = encodeCursor(batch.nextOffset);
  return page;
}

export function encodeCursor(offset: number): string {
  return Buffer.from(String(offset), "utf-8").toString("base64url");
}

export function decodeCursor(cursor: string | undefined): number {
  if (!cursor) return 0;
  try {
    const offset = Number.parseInt(Buffer.from(cursor, "base64url").toString("utf-8"), 10);
    return Number.isSafeInteger(offset) && offset >= 0 ? offset : 0;
  } catch {
    return 0;
  }
}

const KNOWN_EVENT_TYPES = new Set<string>([
  "goal_created", "research_attached", "goal_focused", "goal_unfocused", "goal_paused", "goal_resumed", "goal_blocked",
  "goal_tweaked", "goal_budget_warning", "goal_budget_limited", "goal_cleared", "goal_archived",
  "goal_claimed",
  "completion_refused", "completion_requested", "check_started", "check_result", "check_deferred", "check_skipped", "goal_completed",
]);

/**
 * Whether a parsed line is an event this version understands.
 *
 * A line that is valid JSON but not an event is rejected rather than passed
 * through: the ledger is append-only, so an unrecognized record is either
 * corruption or a future version, and either way letting it into a projection
 * would invent state.
 */
export function isGoalLedgerEvent(value: unknown): value is GoalLedgerEvent {
  if (typeof value !== "object" || value === null) return false;
  const event = value as Record<string, unknown>;
  return typeof event.type === "string" && KNOWN_EVENT_TYPES.has(event.type) && typeof event.at === "string";
}

/** Rebuild the authoritative lifecycle state from the ledger alone. Used when a
 * record file is lost but its history survives. The last event for a field
 * wins, so replay is order-dependent and therefore explicit. */
export function rebuildGoalFromLedger(projectRoot: string, goalId: string, archived = false): Partial<GoalRecord> | undefined {
  const events = readGoalLedger(projectRoot, goalId, undefined, archived);
  if (events.length === 0) return undefined;
  const rebuilt: Partial<GoalRecord> = { id: goalId, revision: 0 };
  for (const event of events) {
    switch (event.type) {
      case "goal_created":
        rebuilt.objective = event.objective;
        rebuilt.autoContinue = event.autoContinue;
        rebuilt.status = "active";
        rebuilt.createdAt = event.at;
        break;
      case "goal_paused":
        rebuilt.status = "paused";
        rebuilt.autoContinue = false;
        rebuilt.pauseReason = event.reason;
        rebuilt.stopReason = event.stopReason;
        break;
      case "goal_blocked":
        rebuilt.status = "blocked";
        rebuilt.autoContinue = false;
        rebuilt.pauseReason = event.reason;
        break;
      case "goal_claimed":
        // A consumed run is history, not state: it records that a dispatch was
        // spent, which is what makes a goal that stops mid-run diagnosable.
        break;
      case "goal_resumed":
        rebuilt.status = "active";
        rebuilt.autoContinue = true;
        rebuilt.pauseReason = undefined;
        break;
      case "goal_budget_limited":
        rebuilt.status = "budget_limited";
        rebuilt.autoContinue = false;
        break;
      case "goal_tweaked":
        // The objective itself is not in the event: the store rewrites the
        // record file, and a ledger replay cannot recover user prose it was
        // never given. Recovery reports the goal as needing its objective.
        rebuilt.objective = undefined;
        break;
      case "goal_completed":
      case "goal_cleared":
      case "goal_archived":
        rebuilt.status = "complete";
        rebuilt.autoContinue = false;
        break;
    }
  }
  rebuilt.updatedAt = events[events.length - 1]!.at;
  return rebuilt;
}

/** Projection for prompts and the dashboard: the recent tail, newest last, plus
 * anything worth pinning regardless of recency (lifecycle and verification). */
export function projectHistory(projectRoot: string, goalId: string, limit = 12, archived = false): GoalLedgerEvent[] {
  const events = readGoalLedger(projectRoot, goalId, undefined, archived);
  return events.slice(-limit);
}