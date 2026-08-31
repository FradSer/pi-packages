/**
 * Team state management for the current session only: the teammate roster,
 * the in-memory task board, and the single leader inbox. The leader process
 * is the sole writer of this snapshot and of board.json.
 */

import {
  messageTitle,
  type BoardTask,
  type WorkerAssignment,
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
/** Bounded forensic routing history; mailbox files retain the full peer transcript. */
export const MAX_PEER_DELIVERY_STATES = 4096;
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
    peerDeliveryStates: {},
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
export function assignTeammate(
  name: string,
  assignment: WorkerAssignment | undefined,
  currentTaskId?: string,
): Teammate | undefined {
  const teammate = getTeammate(name);
  if (!teammate) return undefined;
  const lastAssignment = assignment ?? teammate.assignment ?? teammate.lastAssignment;
  const lastTaskId = currentTaskId ?? teammate.currentTaskId ?? teammate.lastTaskId;
  return updateTeammate(name, { assignment, currentTaskId, lastAssignment, lastTaskId });
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
export function receiveWorkerMessage(event: WorkerReportEvent, options?: { archived?: boolean }): boolean {
  const sender = getTeammate(event.worker);
  if (!sender || sender.spawnId !== event.spawnId) return false;
  if (state.leaderMailbox.some((message) => message.id === event.id)) return false;
  state.leaderMailbox.push({
    id: event.id,
    from: event.worker,
    subject: messageTitle(event.body),
    body: event.body,
    status: event.status,
    archived: options?.archived,
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

/** Record only the harness-controlled routing transition, never recipient read. */
export function setPeerDeliveryState(messageId: string, routing: "queued" | "routed"): void {
  state.peerDeliveryStates ??= {};
  if (!(messageId in state.peerDeliveryStates)
    && Object.keys(state.peerDeliveryStates).length >= MAX_PEER_DELIVERY_STATES) {
    const oldest = Object.keys(state.peerDeliveryStates)[0];
    if (oldest) delete state.peerDeliveryStates[oldest];
  }
  state.peerDeliveryStates[messageId] = routing;
  markStateDirty();
}

export function getPeerDeliveryState(messageId: string): "queued" | "routed" | undefined {
  return state.peerDeliveryStates?.[messageId];
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

export function normalizeResources(resources: readonly string[] | undefined): string[] {
  return [...new Set((resources ?? [])
    .map((resource) => resource.trim().replace(/^\/+|\/+$/g, ""))
    .filter(Boolean))]
    .sort();
}

/** Follow an obsolete dependency to its latest replacement. An invalid persisted
 * chain is rejected rather than silently making a future task unclaimable. */
export function canonicalDependency(taskId: string, tasks: Record<string, BoardTask>): string | undefined {
  const seen = new Set<string>();
  let current = taskId;
  while (true) {
    if (seen.has(current)) return undefined;
    seen.add(current);
    const task = tasks[current];
    if (!task) return undefined;
    if (task.status !== "superseded") return current;
    if (!task.supersededBy) return undefined;
    current = task.supersededBy;
  }
}

function canonicalDependencies(
  dependencies: readonly string[],
  tasks: Record<string, BoardTask>,
): string[] | undefined {
  const canonical: string[] = [];
  for (const dependency of dependencies) {
    const resolved = canonicalDependency(dependency, tasks);
    if (!resolved) return undefined;
    if (!canonical.includes(resolved)) canonical.push(resolved);
  }
  return canonical;
}

function hasDependencyCycle(graph: Map<string, readonly string[]>): boolean {
  const visiting = new Set<string>();
  const visited = new Set<string>();
  const visit = (taskId: string): boolean => {
    if (visiting.has(taskId)) return true;
    if (visited.has(taskId)) return false;
    visiting.add(taskId);
    for (const dependency of graph.get(taskId) ?? []) {
      if (graph.has(dependency) && visit(dependency)) return true;
    }
    visiting.delete(taskId);
    visited.add(taskId);
    return false;
  };
  return [...graph.keys()].some(visit);
}

/** `firmware/sub-node` conflicts with itself and descendants such as
 * `firmware/sub-node/app`; unrelated siblings stay concurrently claimable. */
export function resourcesConflict(left: readonly string[], right: readonly string[]): boolean {
  return left.some((a) => right.some((b) => a === b || a.startsWith(`${b}/`) || b.startsWith(`${a}/`)));
}

export function activeAssignmentConflict(
  resources: readonly string[],
  exceptWorker?: string,
): Teammate | undefined {
  if (resources.length === 0) return undefined;
  return livingTeammates().find((teammate) => {
    if (teammate.name === exceptWorker) return false;
    const assignment = teammate.assignment;
    return assignment !== undefined && !assignment.closed && resourcesConflict(resources, assignment.resources);
  });
}

export function createTask(input: {
  subject: string;
  description?: string;
  dependsOn?: string[];
  verify?: string;
  resources?: string[];
  supersedes?: string[];
}): { ok: true; task: BoardTask; superseded: BoardTask[] } | { ok: false; error: string } {
  const subject = input.subject.trim();
  if (!subject) return { ok: false, error: "Task subject must not be empty." };
  const requestedDependencies = [...new Set(input.dependsOn ?? [])];
  const requestedSupersedes = [...new Set(input.supersedes ?? [])];
  if (requestedDependencies.length > MAX_TASK_DEPENDENCIES) {
    return { ok: false, error: `Task depends on more than ${MAX_TASK_DEPENDENCIES} tasks.` };
  }
  for (const taskId of [...requestedDependencies, ...requestedSupersedes]) {
    if (!state.tasks[taskId]) return { ok: false, error: `Task references unknown task "${taskId}".` };
  }
  const completedTarget = requestedSupersedes.find((taskId) => state.tasks[taskId]?.status === "completed");
  if (completedTarget) {
    return { ok: false, error: `Task cannot supersede completed task "${completedTarget}".` };
  }
  const dependsOn = canonicalDependencies(requestedDependencies, state.tasks);
  const supersedes = canonicalDependencies(requestedSupersedes, state.tasks);
  if (!dependsOn || !supersedes) return { ok: false, error: "Task dependency or supersession chain is invalid or cyclic." };
  const canonicalCompletedTarget = supersedes.find((taskId) => state.tasks[taskId]?.status === "completed");
  if (canonicalCompletedTarget) {
    return { ok: false, error: `Task cannot supersede completed task "${canonicalCompletedTarget}".` };
  }
  const selfReplacement = supersedes.find((taskId) => dependsOn.includes(taskId));
  if (selfReplacement) {
    return { ok: false, error: `Task cannot both depend on and supersede "${selfReplacement}".` };
  }

  const id = taskIdFromSubject(subject, new Set(Object.keys(state.tasks)));
  const migrations = new Map<string, string[]>();
  for (const dependent of Object.values(state.tasks)) {
    if (dependent.status === "completed" || dependent.status === "superseded") continue;
    const migrated = dependent.dependsOn.map((dependency) => supersedes.includes(dependency) ? id : dependency);
    if (migrated.some((dependency, index) => dependency !== dependent.dependsOn[index])) {
      migrations.set(dependent.id, [...new Set(migrated)]);
    }
  }
  const prospectiveGraph = new Map<string, readonly string[]>();
  for (const existing of Object.values(state.tasks)) {
    prospectiveGraph.set(existing.id, migrations.get(existing.id) ?? existing.dependsOn);
  }
  prospectiveGraph.set(id, dependsOn);
  if (hasDependencyCycle(prospectiveGraph)) {
    return { ok: false, error: "Task supersession would create a dependency cycle." };
  }

  const task: BoardTask = {
    id,
    subject,
    description: input.description?.trim() || undefined,
    dependsOn,
    verify: input.verify?.trim() || undefined,
    resources: normalizeResources(input.resources),
    status: "pending",
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
  state.tasks[id] = task;
  const superseded: BoardTask[] = [];
  for (const oldId of supersedes) {
    const old = state.tasks[oldId];
    if (!old || old.status === "completed" || old.status === "superseded") continue;
    old.status = "superseded";
    old.supersededBy = id;
    // A living holder keeps the claim and assignment until it acknowledges
    // cancellation or stops. Releasing its resource before it receives the
    // stop instruction would let replacement work race active file writes.
    old.updatedAt = Date.now();
    superseded.push(old);
  }
  for (const [dependentId, migratedDependencies] of migrations) {
    const dependent = state.tasks[dependentId];
    if (!dependent) continue;
    dependent.dependsOn = migratedDependencies;
    dependent.updatedAt = Date.now();
  }
  markStateDirty();
  return { ok: true, task, superseded };
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
  return task.status === "pending" && task.dependsOn.every((dep) => state.tasks[dep]?.status === "completed");
}

/** First claimable task, or undefined. */
export function firstClaimableTask(): BoardTask | undefined {
  return claimableTasks()[0];
}

export function setTaskClaimed(taskId: string, workerName: string): BoardTask | undefined {
  const task = state.tasks[taskId];
  const teammate = getTeammate(workerName);
  if (!task || !teammate || task.status !== "pending" || !taskDependenciesMet(task)) return undefined;
  if (teammate.assignment) return undefined;
  if (activeAssignmentConflict(task.resources, workerName)) return undefined;
  task.status = "claimed";
  task.claimedBy = workerName;
  task.updatedAt = Date.now();
  assignTeammate(workerName, { id: task.id, kind: "board", resources: task.resources }, task.id);
  markStateDirty();
  return task;
}

/** Release a claimed task back to pending. A superseded holder instead
 * acknowledges cancellation: the task stays superseded but frees resources. */
export function releaseTask(taskId: string, errorMessage?: string): BoardTask | undefined {
  const task = state.tasks[taskId];
  if (!task || (task.status !== "claimed" && task.status !== "superseded")) return undefined;
  const holder = task.claimedBy;
  if (task.status === "claimed") task.status = "pending";
  task.claimedBy = undefined;
  if (errorMessage !== undefined) task.errorMessage = errorMessage;
  task.updatedAt = Date.now();
  if (holder) assignTeammate(holder, undefined, undefined);
  markStateDirty();
  return task;
}

export function completeTask(taskId: string, result?: string): BoardTask | undefined {
  const task = state.tasks[taskId];
  if (!task || task.status !== "claimed") return undefined;
  const holder = task.claimedBy;
  task.status = "completed";
  task.result = result;
  task.errorMessage = undefined;
  task.completedAt = Date.now();
  task.updatedAt = Date.now();
  if (holder) assignTeammate(holder, undefined, undefined);
  markStateDirty();
  return task;
}

/** Release every task held by a named teammate (crash or shutdown). */
export function releaseTasksOf(workerName: string, reason: string): BoardTask[] {
  const released: BoardTask[] = [];
  for (const task of listTasks()) {
    if ((task.status === "claimed" || task.status === "superseded") && task.claimedBy === workerName) {
      releaseTask(task.id, reason);
      released.push(task);
    }
  }
  return released;
}

/** Apply a validated claim intent from a marker file. */
export function applyClaimIntent(intent: TaskIntent): { applied: boolean; reason?: string } {
  const task = state.tasks[intent.taskId];
  const teammate = getTeammate(intent.worker);
  if (!task) return { applied: false, reason: `unknown task "${intent.taskId}"` };
  if (!teammate || teammate.spawnId !== intent.spawnId || teammate.status === "stopped") {
    return { applied: false, reason: `worker "${intent.worker}" is not a living current incarnation` };
  }
  if (teammate.assignment) {
    const state = teammate.assignment.closed ? "closed pending leader reopen" : "active";
    return { applied: false, reason: `@${intent.worker} already owns ${state} ${teammate.assignment.kind} assignment "${teammate.assignment.id}"` };
  }
  if (task.status === "claimed") return { applied: false, reason: `task "${intent.taskId}" is already claimed` };
  if (task.status === "completed" || task.status === "superseded") return { applied: false, reason: `task "${intent.taskId}" is ${task.status}` };
  if (!taskDependenciesMet(task)) return { applied: false, reason: `task "${intent.taskId}" has unmet dependencies` };
  const conflict = activeAssignmentConflict(task.resources, intent.worker);
  if (conflict) return { applied: false, reason: `resource conflict with @${conflict.name}'s ${conflict.assignment?.kind} assignment "${conflict.assignment?.id}"` };
  if (!setTaskClaimed(intent.taskId, intent.worker)) return { applied: false, reason: `task "${intent.taskId}" could not be claimed` };
  return { applied: true };
}

/** Validate and apply a submission intent; verify gating happens in the caller. */
export function applySubmissionIntent(intent: TaskIntent): { ok: boolean; error?: string } {
  if (intent.status !== "completed" && intent.status !== "failed") {
    return { ok: false, error: `task "${intent.taskId}" has invalid submission status` };
  }
  const teammate = getTeammate(intent.worker);
  if (!teammate || teammate.spawnId !== intent.spawnId || teammate.status === "stopped") {
    return { ok: false, error: `worker "${intent.worker}" is not a living current incarnation` };
  }
  const task = state.tasks[intent.taskId];
  if (!task) return { ok: false, error: `unknown task "${intent.taskId}"` };
  if (task.status !== "claimed" && task.status !== "superseded") {
    return { ok: false, error: `task "${intent.taskId}" is not claimed` };
  }
  if (task.claimedBy !== intent.worker) {
    return { ok: false, error: `task "${intent.taskId}" is claimed by ${task.claimedBy ?? "someone else"}` };
  }
  if (task.status === "superseded" && intent.status !== "failed") {
    return { ok: false, error: `task "${intent.taskId}" was superseded by "${task.supersededBy ?? "a replacement"}"; submit failed to acknowledge cancellation` };
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
    const orphanedHolding = task.status === "claimed" || task.status === "superseded";
    const restored: BoardTask = {
      ...task,
      resources: normalizeResources(task.resources),
      status: task.status === "claimed" ? "pending" : task.status,
      // Runtime workers and assignments die with the session. Superseded work
      // remains visible for audit but cannot retain a dead holder/resource lock.
      claimedBy: orphanedHolding ? undefined : task.claimedBy,
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
  const counts = { pending: 0, claimed: 0, completed: 0, superseded: 0 };
  for (const task of listTasks()) {
    if (task.status in counts) counts[task.status as keyof typeof counts]++;
  }
  return `${alive.length} teammate(s) alive | board: ${counts.pending} pending / ${counts.claimed} claimed / ${counts.completed} completed / ${counts.superseded} superseded`;
}
