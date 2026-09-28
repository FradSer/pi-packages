/**
 * Team state management for the current session only: the teammate roster,
 * the in-memory task board, and the single leader inbox. The leader process
 * is the sole writer of this snapshot and of board.json.
 */

import { nonEmpty } from "@fradser/pi-kit";
import {
  messageTitle,
  TEAM_RUNTIME_VERSION,
  type MailboxMessage,
  type TeamState,
  type WorkerReportEvent,
} from "./types.ts";
// The roster — one child process per entry, its lifecycle, and the revisions that
// say when it changed — is an execution fact, so it lives in @fradser/pi-subagents
// with the spawner that creates those processes. This module keeps the snapshot,
// the leader inbox, and the board callback, and points `teammates` at the roster's
// own map by identity so no snapshot schema changes and no version bump is needed.
import {
  assignTeammate,
  getTeammate,
  livingTeammates,
  teammates as roster,
  progressRevision as rosterProgressRevision,
  resetRoster,
  rosterRevision as currentRosterRevision,
  type Teammate,
} from "@fradser/pi-subagents";
// The Work Item graph and resource rules are pure and live in @fradser/pi-tasks, so the
// leader, the worker, and any board-only consumer share one implementation.
// `activeAssignmentConflict` below is the roster-backed policy on top of
// `resourcesConflict`, and stays here because it reads the roster.
import {
  configureBoardStore,
  resourcesConflict,
  tasks as boardTasks,
} from "@fradser/pi-tasks";

export const MAX_LEADER_MAILBOX_MESSAGES = 4096;
/** Total mailbox body bytes retained for forensics. A count cap alone lets a few
 *  long reports blow the snapshot up: this keeps the debug artifact bounded. */
export const MAX_LEADER_MAILBOX_BYTES = 8 * 1024 * 1024;
/** FIFO cap of remembered peer message ids per inbox (dedup guard). */
export const MAX_PEER_DELIVERED_IDS = 512;
/** Bounded forensic routing history; mailbox files retain the full peer transcript. */
export const MAX_PEER_DELIVERY_STATES = 4096;
export const MAX_TASK_DEPENDENCIES = 32;

function emptyState(): TeamState {
  return {
    runtimeVersion: TEAM_RUNTIME_VERSION,
    teammates: roster,
    tasks: boardTasks,
    leaderMailbox: [],
    messageCounter: 0,
    workerEventOffsets: {},
    workerEventIds: {},
    peerInboxOffsets: {},
    peerDeliveredIds: {},
    peerDeliveryStates: {},
  };
}

let state = emptyState();

function nextMessageId(): string {
  return `msg_${++state.messageCounter}`;
}

export function resetState(): void {
  for (const id of Object.keys(boardTasks)) delete boardTasks[id];
  resetRoster();
  state = emptyState();
  boardRevisionCounter++;
  stateRevisionCounter++;
}

// ── Persistence revisions ────────────────────────────────────────
// state.ts owns every in-memory mutation, so it is the one place that can say
// exactly which artifact changed. Stream progress is counted separately: a
// running teammate must not force the roster, the board, or the debug snapshot
// to be rewritten on every token. Every persisted mutation in this module bumps
// one of these counters, so a mutation that forgets to bump would not be written
// until something else changed — add the bump with any new mutator.
let stateRevisionCounter = 0;
let boardRevisionCounter = 0;

/** Revision of the whole snapshot: roster, board, mailbox, and offsets.
 *
 * Composed rather than single-sourced, because the roster now has its own counter
 * in another package. Every input is monotonic, so the sum changes whenever any
 * of them does, which is the only property the snapshot writer relies on: it
 * compares against the last written value and rewrites on inequality. */
export function stateRevision(): number {
  return stateRevisionCounter + currentRosterRevision() + boardRevisionCounter;
}

/** Revision of the worker-readable roster, owned by @fradser/pi-subagents. */
export { currentRosterRevision as rosterRevision };

/** Revision of the persisted board. */
export function boardRevision(): number {
  return boardRevisionCounter;
}

/** Revision of streamed progress only; never persisted on its own. */
export { rosterProgressRevision as progressRevision };

/** Record a board change made outside this module's task mutators. */
export function markBoardChanged(): void {
  boardRevisionCounter++;
  stateRevisionCounter++;
}

/** Drop per-spawn replay metadata once its final snapshot was persisted.
 *  Snapshot bookkeeping rather than roster state, so it stays here even though
 *  the roster itself moved. */
export function clearWorkerRunEvents(workerName: string, spawnId: string): void {
  const outboxKey = `${workerName}:${spawnId}`;
  delete state.workerEventOffsets[outboxKey];
  for (const id of Object.keys(state.workerEventIds)) {
    if (id.startsWith(`${spawnId}:`)) delete state.workerEventIds[id];
  }
}

// ── Session settings ─────────────────────────────────────────────

/** The unified model for later spawns, or undefined when Pi picks.
 *
 * Deliberately session state rather than roster state: it is a setting the
 * snapshot persists for forensics and resume, so moving it with the roster would
 * have given the roster a second source of truth that no snapshot records. The
 * spawner reads it through the re-export below. */
export function getTeamDefaultModel(): string | undefined {
  return state.defaultModel;
}

/** Set (or clear with undefined) the unified model for later spawns. */
export function setTeamDefaultModel(ref: string | undefined): void {
  state.defaultModel = nonEmpty(ref);
  stateRevisionCounter++;
}

// ── Roster (owned by @fradser/pi-subagents) ───────────────────────
//
// A child process is an execution fact, so the roster lives with the spawner.
// Re-exported here because the coordination vocabulary reads this module as its
// entry point, and every existing consumer imports it from here.

export {
  assignTeammate,
  getTeammate,
  idleTeammates,
  isValidTeammateName,
  listTeammates,
  livingTeammates,
  registerTeammate,
  updateTeammate,
  updateTeammateProgress,
  teammates,
} from "@fradser/pi-subagents";

/** Drop the oldest mailbox entries until both the count and byte caps hold. */
function trimLeaderMailbox(): void {
  if (state.leaderMailbox.length > MAX_LEADER_MAILBOX_MESSAGES) {
    state.leaderMailbox.splice(0, state.leaderMailbox.length - MAX_LEADER_MAILBOX_MESSAGES);
  }
  let bytes = 0;
  for (const message of state.leaderMailbox) bytes += message.body.length + message.subject.length + 64;
  while (bytes > MAX_LEADER_MAILBOX_BYTES && state.leaderMailbox.length > 1) {
    const dropped = state.leaderMailbox.shift()!;
    bytes -= dropped.body.length + dropped.subject.length + 64;
  }
}

// ── Leader inbox ──────────────────────────────────────────────────

export function deliverToLeader(msg: Omit<MailboxMessage, "id" | "timestamp">): MailboxMessage {
  const full: MailboxMessage = { ...msg, id: nextMessageId(), timestamp: Date.now() };
  state.leaderMailbox.push(full);
  trimLeaderMailbox();
  stateRevisionCounter++;
  return full;
}

/** Apply a validated report event exactly once by event id. */
export function receiveWorkerMessage(event: WorkerReportEvent, options?: { archived?: boolean }): boolean {
  const sender = getTeammate(event.worker);
  if (!sender || sender.spawnId !== event.spawnId) return false;
  if (state.leaderMailbox.some((message) => message.id === event.id)) return false;
  state.leaderMailbox.push({
    id: event.id,
    from: event.worker,
    assignmentId: event.assignmentId,
    spawnId: event.spawnId,
    subject: messageTitle(event.body),
    body: event.body,
    status: event.status,
    archived: options?.archived,
    // Keep the authored-at moment so console ordering reflects when the
    // teammate spoke, not when the leader happened to drain the outbox.
    timestamp: event.timestamp ?? Date.now(),
  });
  trimLeaderMailbox();
  stateRevisionCounter++;
  return true;
}

/** True when this peer message id was already delivered to that inbox. */
export function isPeerDelivered(inboxName: string, messageId: string): boolean {
  return (state.peerDeliveredIds[inboxName] ?? []).includes(messageId);
}

/** Remember a delivered peer message id with a bounded FIFO per inbox. */
export function markPeerDelivered(inboxName: string, messageId: string): void {
  const ids = state.peerDeliveredIds[inboxName] ?? [];
  ids.push(messageId);
  while (ids.length > MAX_PEER_DELIVERED_IDS) ids.shift();
  state.peerDeliveredIds[inboxName] = ids;
  stateRevisionCounter++;
}

export function getPeerInboxOffset(inboxName: string): number {
  return state.peerInboxOffsets[inboxName] ?? 0;
}

export function setPeerInboxOffset(inboxName: string, offset: number): void {
  state.peerInboxOffsets[inboxName] = offset;
  stateRevisionCounter++;
}

/** Record only the harness-controlled routing transition, never recipient read. */
export function setPeerDeliveryState(messageId: string, routing: "queued" | "routed" | "dropped"): void {
  state.peerDeliveryStates ??= {};
  if (!(messageId in state.peerDeliveryStates)
    && Object.keys(state.peerDeliveryStates).length >= MAX_PEER_DELIVERY_STATES) {
    const oldest = Object.keys(state.peerDeliveryStates)[0];
    if (oldest) delete state.peerDeliveryStates[oldest];
  }
  state.peerDeliveryStates[messageId] = routing;
  stateRevisionCounter++;
}

export function getPeerDeliveryState(messageId: string): "queued" | "routed" | "dropped" | undefined {
  return state.peerDeliveryStates?.[messageId];
}

// ── Board: creation and queries ───────────────────────────────────

/** Maximum characters in a generated slug task id (suffix included). */
export function activeAssignmentConflict(
  resources: readonly string[],
  exceptWorker?: string,
): Teammate | undefined {
  if (resources.length === 0) return undefined;
  return livingTeammates().find((teammate) => {
    if (teammate.name === exceptWorker) return false;
    const assignment = teammate.assignment;
    const retainsWorkAuthority = teammate.currentTaskId !== undefined
      && ["in_progress", "superseded"].includes(state.tasks[teammate.currentTaskId]?.status ?? "");
    return assignment !== undefined
      && (!assignment.closed || retainsWorkAuthority)
      && resourcesConflict(resources, assignment.resources);
  });
}

// ── Board (delegated to pi-tasks) ────────────────────────────────
//
// There is deliberately no `release` here. A lease is given back on completion,
// on process exit, and on stop; the runtime's own half-start reverts go through
// `revertInFlightAttempt`, and a holder that must free a lease it is not giving
// up uses `acknowledgeSupersession`. Those name what happened instead of offering
// one verb that can take any task from anyone.
export {
  createTask, getTask, listTasks, pendingTasks, claimableTasks, taskDependenciesMet,
  createDirectWork, discardDirectWork, reclaimDirectWork, takeTask, claimedDependents,
  reopenCompletedWork, releaseTasksOf, applyClaimIntent, revertInFlightAttempt,
  acknowledgeSupersession, completeTaskWithOutcome,
  applySubmissionIntent, loadBoard, setTaskContext,
} from "@fradser/pi-tasks";
export type { WorkAssignment as WorkerAssignment } from "@fradser/pi-tasks";

// ── State inspection ──────────────────────────────────────────────

export function getState(): TeamState {
  return state;
}

configureBoardStore({
  get: (name) => {
    const t = getTeammate(name);
    return t ? { name: t.name, spawnId: t.spawnId, status: t.status,
                assignment: t.assignment, currentTaskId: t.currentTaskId } : undefined;
  },
  conflicting: (resources, except) => activeAssignmentConflict(resources, except),
  sync: (name, assignment, taskId) => { assignTeammate(name, assignment, taskId); },
  changed: () => { boardRevisionCounter++; stateRevisionCounter++; },
});
