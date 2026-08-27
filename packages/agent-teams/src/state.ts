/**
 * Team state management for the current session only: the teammate roster,
 * the in-memory task board, and the single leader inbox. The leader process
 * is the sole writer of this snapshot and of board.json.
 */

import {
  messageTitle,
  type BoardTask,
  type MailboxMessage,
  type TaskIntent,
  type Teammate,
  type TeamState,
  type WorkerReportEvent,
  type WorkerUsage,
} from "./types.ts";
import { nonEmpty } from "@fradser/pi-kit";

export const MAX_LEADER_MAILBOX_MESSAGES = 4096;
/** FIFO cap of remembered peer message ids per inbox (dedup guard). */
export const MAX_PEER_DELIVERED_IDS = 512;
export const MAX_TASK_DEPENDENCIES = 32;

function emptyState(): TeamState {
  return {
    teammates: {},
    tasks: emptyTaskMap(),
    leaderMailbox: [],
    messageCounter: 0,
    workerEventOffsets: {},
    workerEventIds: {},
    peerInboxOffsets: {},
    peerDeliveredIds: {},
  };
}

let state = emptyState();
let stateDirty = false;

export function markStateDirty(): void {
  stateDirty = true;
}

export function isStateDirty(): boolean {
  return stateDirty;
}

export function clearStateDirty(): void {
  stateDirty = false;
}

export function consumeStateDirty(): boolean {
  const dirty = stateDirty;
  clearStateDirty();
  return dirty;
}

function nextMessageId(): string {
  return `msg_${++state.messageCounter}`;
}

/** Task maps must not inherit Object.prototype: slug ids like "constructor"
 *  are legal task ids and must never alias inherited properties. */
function emptyTaskMap(): Record<string, BoardTask> {
  return Object.create(null);
}

export function resetState(): void {
  state = emptyState();
  markStateDirty();
}

// ── Team default model ──────────────────────────────────────

/** The unified teammate model for this session, or undefined when Pi picks. */
export function getTeamDefaultModel(): string | undefined {
  return state.defaultModel;
}

/** Set (or clear with undefined) the unified teammate model for later spawns. */
export function setTeamDefaultModel(ref: string | undefined): void {
  state.defaultModel = nonEmpty(ref);
  markStateDirty();
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

export function workingTeammates(): Teammate[] {
  return livingTeammates().filter((t) => t.status === "working" || t.status === "starting");
}

export function findTeammateBySpawn(spawnId: string): Teammate | undefined {
  return listTeammates().find((t) => t.spawnId === spawnId && t.status !== "stopped");
}

export function registerTeammate(teammate: Teammate): { ok: true } | { ok: false; error: string } {
  if (!isValidTeammateName(teammate.name)) {
    return { ok: false, error: `Invalid teammate name "${teammate.name}". Use letters, digits, dots, dashes, underscores.` };
  }
  if (livingTeammates().some((t) => t.name === teammate.name)) {
    return { ok: false, error: `A living teammate named "${teammate.name}" already exists.` };
  }
  state.teammates[teammate.name] = teammate;
  markStateDirty();
  return { ok: true };
}

export function updateTeammate(name: string, patch: Partial<Teammate>): Teammate | undefined {
  const teammate = state.teammates[name];
  if (!teammate) return undefined;
  Object.assign(teammate, patch, { updatedAt: Date.now() });
  if (patch.status === "stopped") teammate.stoppedAt = Date.now();
  markStateDirty();
  return teammate;
}

/** Merge streaming child-process progress into a living teammate. */
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
  teammate.liveText = progress.liveText;
  teammate.activeTool = progress.activeTool;
  teammate.liveThinking = progress.liveThinking;
  teammate.turns = progress.turns;
  if (progress.sequenceEnded !== undefined) teammate.sequenceEnded = progress.sequenceEnded;
  if (progress.modelOutputSeen) teammate.modelOutputSeen = true;
  if (progress.usage) teammate.usage = progress.usage;
  if (teammate.status === "starting") {
    teammate.status = progress.sequenceEnded ? "idle" : "working";
  }
  teammate.updatedAt = Date.now();
  markStateDirty();
  return true;
}

/** Drop per-spawn replay metadata once its final snapshot was persisted. */
export function clearWorkerRunEvents(workerName: string, spawnId: string): void {
  const outboxKey = `${workerName}:${spawnId}`;
  delete state.workerEventOffsets[outboxKey];
  for (const id of Object.keys(state.workerEventIds)) {
    if (id.startsWith(`${spawnId}:`)) delete state.workerEventIds[id];
  }
  markStateDirty();
}

// ── Leader inbox ──────────────────────────────────────────────────

export function deliverToLeader(msg: Omit<MailboxMessage, "id" | "timestamp">): MailboxMessage {
  const full: MailboxMessage = { ...msg, id: nextMessageId(), timestamp: Date.now() };
  state.leaderMailbox.push(full);
  if (state.leaderMailbox.length > MAX_LEADER_MAILBOX_MESSAGES) {
    state.leaderMailbox.splice(0, state.leaderMailbox.length - MAX_LEADER_MAILBOX_MESSAGES);
  }
  markStateDirty();
  return full;
}

/** Apply a validated report event exactly once by event id. */
export function receiveWorkerMessage(event: WorkerReportEvent): boolean {
  const sender = getTeammate(event.worker);
  if (!sender || sender.spawnId !== event.spawnId) return false;
  if (state.leaderMailbox.some((message) => message.id === event.id)) return false;
  state.leaderMailbox.push({
    id: event.id,
    from: event.worker,
    subject: messageTitle(event.body),
    body: event.body,
    status: event.status,
    // Keep the authored-at moment so console ordering reflects when the
    // teammate spoke, not when the leader happened to drain the outbox.
    timestamp: event.timestamp ?? Date.now(),
  });
  if (state.leaderMailbox.length > MAX_LEADER_MAILBOX_MESSAGES) {
    state.leaderMailbox.splice(0, state.leaderMailbox.length - MAX_LEADER_MAILBOX_MESSAGES);
  }
  markStateDirty();
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
  markStateDirty();
}

export function getPeerInboxOffset(inboxName: string): number {
  return state.peerInboxOffsets[inboxName] ?? 0;
}

export function setPeerInboxOffset(inboxName: string, offset: number): void {
  state.peerInboxOffsets[inboxName] = offset;
  markStateDirty();
}

// ── Board: creation and queries ───────────────────────────────────

/** Maximum characters in a generated slug task id (suffix included). */
const MAX_TASK_ID_LENGTH = 48;

/** A readable, filesystem-safe id derived from the subject:
 *  "Polish login flow" -> "polish-login-flow"; duplicates get -2, -3, ... */
export function taskIdFromSubject(subject: string, taken: ReadonlySet<string>): string {
  const base = subject
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, MAX_TASK_ID_LENGTH)
    .replace(/-+$/g, "") || "task";
  let id = base;
  for (let n = 2; taken.has(id); n++) {
    const suffix = `-${n}`;
    id = base.slice(0, Math.max(1, MAX_TASK_ID_LENGTH - suffix.length)).replace(/-+$/g, "") + suffix;
  }
  return id;
}

export function createTask(input: {
  subject: string;
  description?: string;
  dependsOn?: string[];
  verify?: string;
}): { ok: true; task: BoardTask } | { ok: false; error: string } {
  const subject = input.subject.trim();
  if (!subject) return { ok: false, error: "Task subject must not be empty." };
  const dependsOn = [...new Set(input.dependsOn ?? [])];
  if (dependsOn.length > MAX_TASK_DEPENDENCIES) {
    return { ok: false, error: `Task depends on more than ${MAX_TASK_DEPENDENCIES} tasks.` };
  }
  for (const dep of dependsOn) {
    if (!state.tasks[dep]) return { ok: false, error: `Task depends on unknown task "${dep}".` };
  }
  const id = taskIdFromSubject(subject, new Set(Object.keys(state.tasks)));
  const task: BoardTask = {
    id,
    subject,
    description: input.description?.trim() || undefined,
    dependsOn,
    verify: input.verify?.trim() || undefined,
    status: "pending",
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
  state.tasks[id] = task;
  markStateDirty();
  return { ok: true, task };
}

export function getTask(taskId: string): BoardTask | undefined {
  return state.tasks[taskId];
}

export function listTasks(): BoardTask[] {
  return Object.values(state.tasks).sort((a, b) => a.id.localeCompare(b.id));
}

export function pendingTasks(): BoardTask[] {
  return listTasks().filter((task) => task.status === "pending");
}

export function claimableTasks(): BoardTask[] {
  return pendingTasks().filter(taskDependenciesMet);
}

export function taskDependenciesMet(task: BoardTask): boolean {
  return task.dependsOn.every((dep) => state.tasks[dep]?.status === "completed");
}

/** First claimable task, or undefined. */
export function firstClaimableTask(): BoardTask | undefined {
  return claimableTasks()[0];
}

export function setTaskClaimed(taskId: string, workerName: string): BoardTask | undefined {
  const task = state.tasks[taskId];
  if (!task || task.status !== "pending" || !taskDependenciesMet(task)) return undefined;
  task.status = "claimed";
  task.claimedBy = workerName;
  task.updatedAt = Date.now();
  markStateDirty();
  return task;
}

/** Release a claimed task back to pending (holder stopped or failed). */
export function releaseTask(taskId: string, errorMessage?: string): BoardTask | undefined {
  const task = state.tasks[taskId];
  if (!task || task.status !== "claimed") return undefined;
  task.status = "pending";
  task.claimedBy = undefined;
  if (errorMessage !== undefined) task.errorMessage = errorMessage;
  task.updatedAt = Date.now();
  markStateDirty();
  return task;
}

export function completeTask(taskId: string, result?: string): BoardTask | undefined {
  const task = state.tasks[taskId];
  if (!task || task.status !== "claimed") return undefined;
  task.status = "completed";
  task.result = result;
  task.errorMessage = undefined;
  task.completedAt = Date.now();
  task.updatedAt = Date.now();
  markStateDirty();
  return task;
}

/** Release every task held by a named teammate (crash or shutdown). */
export function releaseTasksOf(workerName: string, reason: string): BoardTask[] {
  const released: BoardTask[] = [];
  for (const task of listTasks()) {
    if (task.status === "claimed" && task.claimedBy === workerName) {
      releaseTask(task.id, reason);
      released.push(task);
    }
  }
  return released;
}

/** Apply a validated claim intent from a marker file. */
export function applyClaimIntent(intent: TaskIntent): { applied: boolean; reason?: string } {
  const task = state.tasks[intent.taskId];
  if (!task) return { applied: false, reason: `unknown task "${intent.taskId}"` };
  if (task.status === "claimed") return { applied: false, reason: `task "${intent.taskId}" is already claimed` };
  if (task.status === "completed") return { applied: false, reason: `task "${intent.taskId}" is completed` };
  if (!taskDependenciesMet(task)) return { applied: false, reason: `task "${intent.taskId}" has unmet dependencies` };
  setTaskClaimed(intent.taskId, intent.worker);
  return { applied: true };
}

/** Validate and apply a submission intent; verify gating happens in the caller. */
export function applySubmissionIntent(intent: TaskIntent): { ok: boolean; error?: string } {
  const task = state.tasks[intent.taskId];
  if (!task) return { ok: false, error: `unknown task "${intent.taskId}"` };
  if (task.status !== "claimed") return { ok: false, error: `task "${intent.taskId}" is not claimed` };
  if (task.claimedBy !== intent.worker) {
    return { ok: false, error: `task "${intent.taskId}" is claimed by ${task.claimedBy ?? "someone else"}` };
  }
  if (intent.status === "failed") {
    releaseTask(intent.taskId, intent.result?.trim() || "Teammate reported failure.");
    return { ok: true };
  }
  completeTask(intent.taskId, intent.result?.trim() || undefined);
  return { ok: true };
}

// ── State inspection ──────────────────────────────────────────────

export function getState(): TeamState {
  return state;
}

/** Load a persisted board into memory on resume; claims die with their holders. */
export function loadBoard(tasks: Record<string, BoardTask>): number {
  let reloaded = 0;
  for (const task of Object.values(tasks)) {
    const restored: BoardTask = {
      ...task,
      status: task.status === "claimed" ? "pending" : task.status,
      claimedBy: task.status === "claimed" ? undefined : task.claimedBy,
      updatedAt: Date.now(),
    };
    state.tasks[restored.id] = restored;
    reloaded++;
  }
  if (reloaded > 0) markStateDirty();
  return reloaded;
}

export function getSummary(): string | undefined {
  const alive = livingTeammates();
  if (alive.length === 0 && listTasks().length === 0) return undefined;
  const counts = { pending: 0, claimed: 0, completed: 0 };
  for (const task of listTasks()) {
    if (task.status in counts) counts[task.status as keyof typeof counts]++;
  }
  return `${alive.length} teammate(s) alive | board: ${counts.pending} pending / ${counts.claimed} claimed / ${counts.completed} completed`;
}
