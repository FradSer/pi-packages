/**
 * Team state management for the current session only: the teammate roster,
 * the in-memory task board, and the single leader inbox. The leader process
 * is the sole writer of this snapshot and of board.json.
 */

import {
  messageTitle,
  TEAM_RUNTIME_VERSION,
  type WorkerAssignment,
  type MailboxMessage,
  type Teammate,
  type TeamState,
  type WorkerReportEvent,
  type WorkerUsage,
} from "./types.ts";
import { nonEmpty } from "@fradser/pi-kit";
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
    teammates: {},
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
  state = emptyState();
  rosterRevisionCounter++;
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
let rosterRevisionCounter = 0;
let boardRevisionCounter = 0;
let progressRevisionCounter = 0;

/** Revision of the whole snapshot: roster, board, mailbox, and offsets. */
export function stateRevision(): number {
  return stateRevisionCounter;
}

/** Revision of the worker-readable roster. */
export function rosterRevision(): number {
  return rosterRevisionCounter;
}

/** Revision of the persisted board. */
export function boardRevision(): number {
  return boardRevisionCounter;
}

/** Revision of streamed progress only; never persisted on its own. */
export function progressRevision(): number {
  return progressRevisionCounter;
}

/** Record a board change made outside this module's task mutators. */
export function markBoardChanged(): void {
  boardRevisionCounter++;
  stateRevisionCounter++;
}

// ── Team default model ──────────────────────────────────────

/** The unified teammate model for this session, or undefined when Pi picks. */
export function getTeamDefaultModel(): string | undefined {
  return state.defaultModel;
}

/** Set (or clear with undefined) the unified teammate model for later spawns. */
export function setTeamDefaultModel(ref: string | undefined): void {
  state.defaultModel = nonEmpty(ref);
  stateRevisionCounter++;
}

// ── Roster queries ────────────────────────────────────────────────

const NAME_PATTERN = /^[a-z][a-z0-9._-]{0,63}$/i;

export function isValidTeammateName(name: string): boolean {
  return NAME_PATTERN.test(name);
}

export function getTeammate(name: string): Teammate | undefined {
  return state.teammates[name];
}

export function listTeammates(): Teammate[] {
  return Object.values(state.teammates).sort((a, b) => a.createdAt - b.createdAt);
}

export function livingTeammates(): Teammate[] {
  return listTeammates().filter((t) => t.status !== "stopped");
}

export function idleTeammates(): Teammate[] {
  return livingTeammates().filter((t) => t.status === "idle");
}

export function registerTeammate(teammate: Teammate): { ok: true } | { ok: false; error: string } {
  if (!isValidTeammateName(teammate.name)) {
    return { ok: false, error: `Invalid teammate name "${teammate.name}". Use letters, digits, dots, dashes, underscores.` };
  }
  if (livingTeammates().some((t) => t.name === teammate.name)) {
    return { ok: false, error: `A living teammate named "${teammate.name}" already exists.` };
  }
  state.teammates[teammate.name] = teammate;
  rosterRevisionCounter++;
  stateRevisionCounter++;
  return { ok: true };
}

/** Fields whose change is stream progress rather than persisted state. A
 *  progress tick must not republish the roster or the board. */
const VOLATILE_TEAMMATE_FIELDS = new Set<string>([
  "liveText",
  "liveThinking",
  "activeTool",
  "turns",
  "sequenceEnded",
  "modelOutputSeen",
  "usage",
  "lastOutputAt",
  "updatedAt",
  "lastNoticeAt",
  "noticedTaskIds",
]);

export function updateTeammate(name: string, patch: Partial<Teammate>): Teammate | undefined {
  const teammate = state.teammates[name];
  if (!teammate) return undefined;
  const changed = (Object.keys(patch) as Array<keyof Teammate>)
    .filter((field) => !Object.is(teammate[field], patch[field]));
  Object.assign(teammate, patch, { updatedAt: Date.now() });
  if (patch.status === "stopped") teammate.stoppedAt = Date.now();
  // Republishing a roster that only streamed progress is pure write churn.
  if (changed.some((field) => !VOLATILE_TEAMMATE_FIELDS.has(field as string))) {
    rosterRevisionCounter++;
    stateRevisionCounter++;
  } else if (changed.length > 0) {
    progressRevisionCounter++;
  }
  return teammate;
}

/** Merge streaming child-process progress into a living teammate. */
export function assignTeammate(
  name: string,
  assignment: WorkerAssignment | undefined,
  currentTaskId?: string,
): Teammate | undefined {
  const teammate = getTeammate(name);
  if (!teammate) return undefined;
  const lastAssignment = assignment ?? teammate.assignment ?? teammate.lastAssignment;
  const lastTaskId = currentTaskId ?? teammate.currentTaskId ?? teammate.lastTaskId;
  return updateTeammate(name, { assignment, currentTaskId, lastAssignment, lastTaskId,
    ...(assignment && assignment.id !== teammate.assignment?.id ? { reportSequenceEnded: false } : {}),
  });
}

export function updateTeammateProgress(
  name: string,
  spawnId: string,
  progress: Pick<Teammate, "liveText" | "activeTool" | "liveThinking" | "turns"> & {
    sequenceEnded?: boolean;
    modelOutputSeen?: boolean;
    usage?: WorkerUsage;
  },
): boolean {
  const teammate = state.teammates[name];
  if (!teammate || teammate.spawnId !== spawnId) return false;
  const changed = teammate.liveText !== progress.liveText
    || teammate.activeTool !== progress.activeTool
    || teammate.liveThinking !== progress.liveThinking
    || teammate.turns !== progress.turns
    || (progress.sequenceEnded !== undefined && teammate.sequenceEnded !== progress.sequenceEnded)
    || (progress.modelOutputSeen === true && teammate.modelOutputSeen !== true);
  teammate.liveText = progress.liveText;
  teammate.activeTool = progress.activeTool;
  teammate.liveThinking = progress.liveThinking;
  teammate.turns = progress.turns;
  if (progress.sequenceEnded !== undefined) teammate.sequenceEnded = progress.sequenceEnded;
  if (progress.modelOutputSeen) teammate.modelOutputSeen = true;
  if (progress.usage) teammate.usage = progress.usage;
  if (teammate.status === "starting") {
    teammate.status = progress.sequenceEnded ? "idle" : "working";
    // A status transition is roster state, not stream noise.
    rosterRevisionCounter++;
    stateRevisionCounter++;
  }
  teammate.updatedAt = Date.now();
  if (changed) progressRevisionCounter++;
  return true;
}

/** Drop per-spawn replay metadata once its final snapshot was persisted. */
export function clearWorkerRunEvents(workerName: string, spawnId: string): void {
  const outboxKey = `${workerName}:${spawnId}`;
  delete state.workerEventOffsets[outboxKey];
  for (const id of Object.keys(state.workerEventIds)) {
    if (id.startsWith(`${spawnId}:`)) delete state.workerEventIds[id];
  }
}

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
export {
  createTask, getTask, listTasks, pendingTasks, claimableTasks, taskDependenciesMet,
  createDirectWork, discardDirectWork, reclaimDirectWork, setTaskClaimed, claimedDependents,
  reopenCompletedWork, releaseTask, completeTask, releaseTasksOf, applyClaimIntent,
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
