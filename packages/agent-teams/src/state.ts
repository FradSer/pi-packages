/**
 * Team state management for the current session only: the teammate roster,
 * the in-memory task storage, and the single leader inbox. The leader process
 * is the sole writer of this snapshot and of tasks.json.
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
// the leader inbox, and the tasks callback, and points `agents` at the roster's
// own map by identity so no snapshot schema changes and no version bump is needed.
import {
  assignAgent,
  getAgent,
  livingAgents,
  agents as roster,
  progressRevision as rosterProgressRevision,
  resetRoster,
  rosterRevision as currentRosterRevision,
  type Agent,
} from "@fradser/pi-subagents";
// The Work Item graph and resource rules are pure and live in @fradser/pi-tasks, so the
// leader, the worker, and any tasks-only consumer share one implementation.
// `activeAssignmentConflict` below is the roster-backed policy on top of
// `resourcesConflict`, and stays here because it reads the roster.
import {
  bindTask,
  configureTaskStore,
  createTask,
  discardTask,
  resourcesConflict,
  tasks as storedTasks,
  type WorkAssignment as WorkerAssignment,
} from "@fradser/pi-tasks";

export const MAX_LEADER_MAILBOX_MESSAGES = 4096;
/** Total mailbox body bytes retained for forensics. A count cap alone lets a few
 *  long reports blow the snapshot up: this keeps the debug artifact bounded. */
export const MAX_LEADER_MAILBOX_BYTES = 8 * 1024 * 1024;
/** FIFO cap of remembered peer message ids per inbox (dedup guard). */
export const MAX_PEER_DELIVERED_IDS = 512;
/** Bounded forensic routing history; mailbox files retain the full peer transcript. */
export const MAX_PEER_DELIVERY_STATES = 4096;

function emptyState(): TeamState {
  return {
    runtimeVersion: TEAM_RUNTIME_VERSION,
    agents: roster,
    tasks: storedTasks,
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
  for (const id of Object.keys(storedTasks)) delete storedTasks[id];
  resetRoster();
  state = emptyState();
  tasksRevisionCounter++;
  stateRevisionCounter++;
}

// ── Persistence revisions ────────────────────────────────────────
// state.ts owns every in-memory mutation, so it is the one place that can say
// exactly which artifact changed. Stream progress is counted separately: a
// running teammate must not force the roster, the tasks, or the debug snapshot
// to be rewritten on every token. Every persisted mutation in this module bumps
// one of these counters, so a mutation that forgets to bump would not be written
// until something else changed — add the bump with any new mutator.
let stateRevisionCounter = 0;
let tasksRevisionCounter = 0;

/** Revision of the whole snapshot: roster, tasks, mailbox, and offsets.
 *
 * Composed rather than single-sourced, because the roster now has its own counter
 * in another package. Every input is monotonic, so the sum changes whenever any
 * of them does, which is the only property the snapshot writer relies on: it
 * compares against the last written value and rewrites on inequality. */
export function stateRevision(): number {
  return stateRevisionCounter + currentRosterRevision() + tasksRevisionCounter;
}

/** Revision of the worker-readable roster, owned by @fradser/pi-subagents. */
export { currentRosterRevision as rosterRevision };

/** Revision of the persisted tasks. */
export function tasksRevision(): number {
  return tasksRevisionCounter;
}

/** Revision of streamed progress only; never persisted on its own. */
export { rosterProgressRevision as progressRevision };

/** Record a task set change made outside this module's task mutators. */
export function markTasksChanged(): void {
  tasksRevisionCounter++;
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
  assignAgent,
  getAgent,
  idleAgents,
  isValidAgentName,
  listAgents,
  livingAgents,
  registerAgent,
  updateAgent,
  updateAgentProgress,
  agents,
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
  const sender = getAgent(event.worker);
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

// ── Tasks: creation and queries ───────────────────────────────────

/** Maximum characters in a generated slug task id (suffix included). */
export function activeAssignmentConflict(
  resources: readonly string[],
  exceptWorker?: string,
): Agent | undefined {
  if (resources.length === 0) return undefined;
  return livingAgents().find((teammate) => {
    if (teammate.name === exceptWorker) return false;
    const assignment = teammate.assignment;
    const retainsWorkAuthority = teammate.currentTaskId !== undefined
      && ["in_progress", "superseded"].includes(state.tasks[teammate.currentTaskId]?.status ?? "");
    return assignment !== undefined
      && (!assignment.closed || retainsWorkAuthority)
      && resourcesConflict(resources, assignment.resources);
  });
}

// ── Tasks (delegated to pi-tasks) ────────────────────────────────
//
// There is deliberately no `release` here. A lease is given back on completion,
// on process exit, and on stop; the runtime's own half-start reverts go through
// `revertUndeliveredTake`, and a holder that must free a lease it is not giving
// up uses `acknowledgeSupersession`. Those name what happened instead of offering
// one verb that can take any task from anyone.
export {
  createTask, getTask, listTasks, pendingTasks, claimableTasks, taskDependenciesMet,
  takeTask, claimedDependents, reopenTask, failTasksHeldBy,
  applyClaimIntent, revertUndeliveredTake, bindTask, discardTask,
  acknowledgeSupersession, completeTaskWithOutcome,
  applySubmissionIntent, loadTasks, setTaskContext,
} from "@fradser/pi-tasks";
export type { WorkAssignment as WorkerAssignment } from "@fradser/pi-tasks";

/**
 * Create a Task and bind it to a named holder in one step, rolling the creation
 * back if the bind is refused.
 *
 * Composed here rather than offered by the tasks, because it is a coordinator's
 * move: the task store states what must be done and takes only what a holder chose to
 * take, while this names a holder and mints its lease. The rollback matters —
 * without it a refusal would leave a Task whose id resolves to nothing.
 */
export function createBoundWork(input: {
    id: string;
    subject: string;
    description?: string;
    resources?: string[];
    verify?: string;
    holder: string;
    assignment: WorkerAssignment;
  }): { ok: true; task: import("@fradser/pi-tasks").Task } | { ok: false; reason: string } {
    const created = createTask({
      id: input.id,
      recordKind: "execution",
      subject: input.subject,
      ...(input.description ? { description: input.description } : {}),
      ...(input.resources ? { resources: input.resources } : {}),
      ...(input.verify ? { verify: input.verify } : {}),
    });
    if (!created.ok) return { ok: false, reason: created.reason };
    const bound = bindTask(input.id, input.holder, input.assignment, { from: ["pending"] });
    if (!bound.ok) {
      discardTask(input.id, input.holder);
      return { ok: false, reason: bound.reason };
    }
    return { ok: true, task: bound.task };
  }

// ── State inspection ──────────────────────────────────────────────

export function getState(): TeamState {
  return state;
}

configureTaskStore({
  get: (name) => {
    const t = getAgent(name);
    return t ? { name: t.name, spawnId: t.spawnId, status: t.status,
                assignment: t.assignment, currentTaskId: t.currentTaskId } : undefined;
  },
  // A stopped agent holds nothing, and a replaced one is not the incarnation that
  // published the intent. Only the roster knows either, which is why the tasks
  // asks rather than comparing spawn ids itself.
  current: (name, incarnation) => {
    const t = getAgent(name);
    if (!t || t.status === "stopped") return false;
    return incarnation === undefined || t.spawnId === incarnation;
  },
  conflicting: (resources, except) => activeAssignmentConflict(resources, except),
  sync: (name, assignment, taskId) => { assignAgent(name, assignment, taskId); },
  changed: () => { tasksRevisionCounter++; stateRevisionCounter++; },
});
