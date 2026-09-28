import { randomUUID } from "node:crypto";
import { canonicalDependencies, hasDependencyCycle, normalizeResources, taskIdFromSubject } from "./graph.ts";
import type { BoardTask, TaskIntent } from "./types.ts";

export interface WorkAssignment {
  id: string;
  kind: "direct" | "board";
  resources: string[];
  closed?: boolean;
}

export interface WorkHolder {
  name: string;
  spawnId?: string;
  status: string;
  assignment?: WorkAssignment;
  currentTaskId?: string;
}

export interface BoardStoreHooks {
  get(holder: string): WorkHolder | undefined;
  conflicting(resources: readonly string[], exceptHolder?: string): WorkHolder | undefined;
  sync(holder: string, assignment: WorkAssignment | undefined, taskId: string | undefined): void;
  changed(): void;
}

export const MAX_TASK_DEPENDENCIES = 32;

/** The main session's board identity: the process that owns the board when no
 *  agent is bound to it.
 *
 * It is exempt from the participant check below because that check exists to
 *  stop a *dead agent* from taking work, and the main session is not an agent —
 *  it cannot stop or be replaced. A single-session install has no roster at all,
 *  so without this exemption every take would be refused and the standalone
 *  board would be unusable. */
export const MAIN_SESSION = "main";

export const tasks: Record<string, BoardTask> = Object.create(null);

const NO_HOOKS: BoardStoreHooks = {
  get: () => undefined,
  conflicting: () => undefined,
  sync: () => {},
  changed: () => {},
};

export let hooks:
 BoardStoreHooks = NO_HOOKS;

/** True once a coordinator has published a roster and a conflict oracle.
 *
 * This is what separates a board with participants from a single-session board.
 * Without it, `hooks.get` returns undefined for everybody — including the main
 * session, which by definition is not on a roster of spawned agents — and every
 * take would be refused, making a standalone install unusable. */
let coordinated = false;

/** Whether a coordinator is present. Exported so a tool can report which mode
 *  it is in rather than guessing from an empty roster. */
export function isCoordinated(): boolean {
  return coordinated;
}

export function configureBoardStore(next: BoardStoreHooks): void {
  hooks = next;
  coordinated = true;
}

export function createTask(input: {
    id?: string;
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
      if (!tasks[taskId]) return { ok: false, error: `Task references unknown task "${taskId}".` };
    }
    const completedTarget = requestedSupersedes.find((taskId) => tasks[taskId]?.status === "completed");
    if (completedTarget) {
      return { ok: false, error: `Task cannot supersede completed task "${completedTarget}".` };
    }
    const dependsOn = canonicalDependencies(requestedDependencies, tasks);
    const supersedes = canonicalDependencies(requestedSupersedes, tasks);
    if (!dependsOn || !supersedes) return { ok: false, error: "Task dependency or supersession chain is invalid or cyclic." };
    const canonicalCompletedTarget = supersedes.find((taskId) => tasks[taskId]?.status === "completed");
    if (canonicalCompletedTarget) {
      return { ok: false, error: `Task cannot supersede completed task "${canonicalCompletedTarget}".` };
    }
    const selfReplacement = supersedes.find((taskId) => dependsOn.includes(taskId));
    if (selfReplacement) {
      return { ok: false, error: `Task cannot both depend on and supersede "${selfReplacement}".` };
    }

    const id = input.id ?? taskIdFromSubject(subject, new Set(Object.keys(tasks)));
    if (tasks[id]) return { ok: false, error: `Task id "${id}" already exists.` };
    const migrations = new Map<string, string[]>();
    for (const dependent of Object.values(tasks)) {
      if (dependent.status === "completed" || dependent.status === "superseded") continue;
      const migrated = dependent.dependsOn.map((dependency) => supersedes.includes(dependency) ? id : dependency);
      if (migrated.some((dependency, index) => dependency !== dependent.dependsOn[index])) {
        migrations.set(dependent.id, [...new Set(migrated)]);
      }
    }
    const prospectiveGraph = new Map<string, readonly string[]>();
    for (const existing of Object.values(tasks)) {
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
    tasks[id] = task;
    hooks.changed();
    const superseded: BoardTask[] = [];
    for (const oldId of supersedes) {
      const old = tasks[oldId];
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
      const dependent = tasks[dependentId];
      if (!dependent) continue;
      dependent.dependsOn = migratedDependencies;
      dependent.updatedAt = Date.now();
    }
    return { ok: true, task, superseded };
  }

export function getTask(taskId: string): BoardTask | undefined {
    return tasks[taskId];
  }

export function listTasks(): BoardTask[] {
    return Object.values(tasks).sort((a, b) => a.id.localeCompare(b.id));
  }

export function pendingTasks(): BoardTask[] {
    return listTasks().filter((task) => task.status === "pending");
  }

export function claimableTasks(): BoardTask[] {
    return pendingTasks().filter((task) => !task.recoveryRequired && taskDependenciesMet(task));
  }

export function taskDependenciesMet(task: BoardTask): boolean {
    return task.status === "pending" && task.dependsOn.every((dep) => tasks[dep]?.status === "completed");
  }

export function createDirectWork(input: {
    id: string;
    subject: string;
    description?: string;
    resources: string[];
    verify?: string;
    workerName: string;
    assignment: WorkAssignment;
  }): { ok: true; task: BoardTask } | { ok: false; error: string } {
    const created = createTask({
      id: input.id,
      subject: input.subject,
      description: input.description,
      resources: input.resources,
      verify: input.verify,
    });
    if (!created.ok) return created;
    const task = created.task;
    const worker = hooks.get(input.workerName);
    if (!worker || worker.assignment || hooks.conflicting(task.resources, input.workerName)) {
      // The Work is rolled back here, so its id would render as an unresolvable
      // handle: name the work a person can recognize instead.
      const reason = !worker
        ? `@${input.workerName} is not a registered agent`
        : worker.assignment
          ? `@${input.workerName} already owns ${worker.assignment.kind} assignment "${worker.assignment.id}"`
          : `its resources conflict with active Work`;
      delete tasks[task.id];
      return { ok: false, error: `Cannot bind direct Work "${input.subject}" to @${input.workerName}: ${reason}.` };
    }
    task.status = "in_progress";
    task.claimedBy = input.workerName;
    task.updatedAt = Date.now();
    hooks.changed();
    hooks.sync(input.workerName, input.assignment, task.id);
    return { ok: true, task };
  }

export function discardDirectWork(taskId: string, workerName: string): boolean {
    const task = tasks[taskId];
    if (!task || task.status !== "in_progress" || task.claimedBy !== workerName) return false;
    delete tasks[taskId];
    hooks.changed();
    return true;
  }

export function reclaimDirectWork(
    taskId: string,
    workerName: string,
    assignment: WorkAssignment,
    expectedState: "pending" | "completed" | "in_progress",
    allowActiveAssignment = false,
  ): { ok: true } | { ok: false; error: string } {
    const task = tasks[taskId];
    const worker = hooks.get(workerName);
    const retainsSupersededWork = worker?.currentTaskId !== undefined
      && tasks[worker.currentTaskId]?.status === "superseded";
    if (!task || task.status !== expectedState || !worker || retainsSupersededWork || (!allowActiveAssignment && worker.assignment && !worker.assignment.closed)) {
      return { ok: false, error: `Unable to reclaim direct Work Item "${taskId}".` };
    }
    const conflict = hooks.conflicting(task.resources, workerName);
    if (conflict) return { ok: false, error: `Resource conflict with @${conflict.name}'s active assignment.` };
    task.status = "in_progress";
    task.claimedBy = workerName;
    task.result = undefined;
    task.errorMessage = undefined;
    task.recoveryRequired = undefined;
    task.completedAt = undefined;
    task.updatedAt = Date.now();
    hooks.changed();
    hooks.sync(workerName, assignment, task.id);
    return { ok: true };
  }

/** The claim-intent path's take.
 *
 * Not exported: `takeTask` is the one public take, and a second exported take
 * under another name is how a caller ends up bypassing the recovery hold without
 * intending to. This one runs only after `applyClaimIntent` has already checked
 * the hold, the dependencies and the conflicts, so it needs no re-check. */
function setTaskClaimed(taskId: string, workerName: string): BoardTask | undefined {
    const task = tasks[taskId];
    const holder = hooks.get(workerName);
    if (!task || !holder || task.status !== "pending" || task.recoveryRequired || !taskDependenciesMet(task)) return undefined;
    if (holder.assignment) return undefined;
    if (hooks.conflicting(task.resources, workerName)) return undefined;
    task.status = "in_progress";
    task.claimedBy = workerName;
    task.updatedAt = Date.now();
    hooks.changed();
    hooks.sync(workerName, { id: `board:${randomUUID()}`, kind: "board", resources: task.resources }, task.id);
    return task;
  }

  /** Release a claimed task back to pending. A superseded holder instead
   * acknowledges cancellation: the task stays superseded but frees resources.
   * `recoveryRequired` marks an attempt that ran and did not succeed (failure,
   * crash, or stop), so it waits for a deliberate Leader assignment instead of
   * being re-offered. A harness start failure that happened before the attempt
   * reached the worker stays ordinarily claimable; a deliberate Leader release
   * passes `false` for the same reason. */
export function claimedDependents(workId: string): BoardTask[] {
    const reverse = new Map<string, string[]>();
    for (const task of Object.values(tasks)) {
      for (const dependency of task.dependsOn) {
        const dependents = reverse.get(dependency) ?? [];
        dependents.push(task.id);
        reverse.set(dependency, dependents);
      }
    }
    const visited = new Set<string>();
    const pending = [...(reverse.get(workId) ?? [])];
    const claimed: BoardTask[] = [];
    while (pending.length > 0) {
      const id = pending.shift()!;
      if (visited.has(id)) continue;
      visited.add(id);
      const task = tasks[id];
      if (!task) continue;
      if (task.status === "in_progress" || (task.status === "superseded" && task.claimedBy !== undefined)) claimed.push(task);
      pending.push(...(reverse.get(id) ?? []));
    }
    return claimed.sort((left, right) => left.id.localeCompare(right.id));
  }

export function reopenCompletedWork(workId: string): { ok: true; task: BoardTask } | { ok: false; error: string } {
    const task = tasks[workId];
    if (!task || task.status !== "completed") return { ok: false, error: `Work Item "${workId}" is not completed.` };
    const blockers = claimedDependents(workId);
    if (blockers.length > 0) return { ok: false, error: `Work Item "${workId}" has active dependent Work: ${blockers.map((blocker) => blocker.id).join(", ")}.` };
    task.status = "pending";
    task.claimedBy = undefined;
    task.result = undefined;
    task.deferredMessages = undefined;
    task.errorMessage = undefined;
    task.recoveryRequired = undefined;
    task.completedAt = undefined;
    task.updatedAt = Date.now();
    hooks.changed();
    return { ok: true, task };
  }

/** Undo a transition the runtime itself just started.
 *
 * This is not a work-lifecycle action and nothing in the tool surface reaches it.
 * It exists because starting work is several steps — spawn, readiness, session
 * reset — and any of them can fail after the task has been taken. Returning the
 * task to pending here is a *revert*, not a failure report, and that is why it
 * differs from a recorded failure in exactly one way: it sets no recovery hold.
 *
 * A hold would be wrong here. The hold exists so a failure nobody looked at is
 * not silently retried by whichever participant is idle; an attempt that never
 * began has no failure to look at, and holding it would park the task until
 * somebody explained a start that never happened.
 */
export function revertInFlightAttempt(taskId: string, reason: string): BoardTask | undefined {
  const task = tasks[taskId];
  if (!task || task.status !== "in_progress") return undefined;
  const holder = task.claimedBy;
  task.status = "pending";
  task.claimedBy = undefined;
  task.recoveryRequired = undefined;
  task.result = reason;
  task.updatedAt = Date.now();
  hooks.changed();
  if (holder) hooks.sync(holder, undefined, undefined);
  return task;
}

/** A holder releasing its resources while the task stays superseded.
 *
 * Distinct from a failure report because the task's *status* is not the holder's
 * to change: it was replaced, and the replacement stands. What the holder owns is
 * its resource lease, and acknowledging the cancellation gives that back.
 */
export function acknowledgeSupersession(taskId: string, holder: string, reason: string): BoardTask | undefined {
  const task = tasks[taskId];
  if (!task || task.status !== "superseded" || task.claimedBy !== holder) return undefined;
  task.claimedBy = undefined;
  task.recoveryRequired = undefined;
  task.result = reason;
  task.updatedAt = Date.now();
  hooks.changed();
  hooks.sync(holder, undefined, undefined);
  return task;
}

  /** Attach per-Work context. Additive: an existing field is only replaced when the
   * caller supplies a new value, so recording a workspace path cannot erase a
   * handoff written earlier. */
export function setTaskContext(
    taskId: string,
    context: NonNullable<BoardTask["context"]>,
  ): BoardTask | undefined {
    const task = tasks[taskId];
    if (!task) return undefined;
    task.context = { ...task.context, ...context };
    hooks.changed();
    return task;
  }

  /** Release every task held by a named agent (crash or shutdown).
   *
   * Recorded as a failure rather than a revert, because the attempt did run: a
   * crashed or stopping agent may have written anything, and the hold is what
   * stops the wreckage from being silently picked up by the next idle
   * participant. */
export function releaseTasksOf(workerName: string, reason: string): BoardTask[] {
  const released: BoardTask[] = [];
  for (const task of listTasks()) {
    if (task.status === "in_progress" && task.claimedBy === workerName) {
      completeTaskWithOutcome(task.id, workerName, "failed", reason);
      released.push(task);
    } else if (task.status === "superseded" && task.claimedBy === workerName) {
      // A superseded task stays superseded; only the lease comes back.
      acknowledgeSupersession(task.id, workerName, reason);
      released.push(task);
    }
  }
  return released;
}

  /** Apply a validated claim intent from a marker file. */
export function applyClaimIntent(intent: TaskIntent): { applied: boolean; reason?: string } {
    const task = tasks[intent.taskId];
    const holder = hooks.get(intent.worker);
    if (!task) return { applied: false, reason: `unknown task "${intent.taskId}"` };
    if (!holder || holder.spawnId !== intent.spawnId || holder.status === "stopped") {
      return { applied: false, reason: `worker "${intent.worker}" is not a living current incarnation` };
    }
    if (holder.assignment) {
      const state = holder.assignment.closed ? "closed pending leader reopen" : "active";
      return { applied: false, reason: `@${intent.worker} already owns ${state} ${holder.assignment.kind} assignment "${holder.assignment.id}"` };
    }
    if (task.status === "in_progress") return { applied: false, reason: `task "${intent.taskId}" is already in progress` };
    if (task.status === "completed" || task.status === "superseded") return { applied: false, reason: `task "${intent.taskId}" is ${task.status}` };
    if (task.recoveryRequired) return { applied: false, reason: `task "${intent.taskId}" requires explicit leader Work assignment after failure` };
    if (!taskDependenciesMet(task)) return { applied: false, reason: `task "${intent.taskId}" has unmet dependencies` };
    const conflict = hooks.conflicting(task.resources, intent.worker);
    if (conflict) return { applied: false, reason: `resource conflict with @${conflict.name}'s ${conflict.assignment?.kind} assignment "${conflict.assignment?.id}"` };
    if (!setTaskClaimed(intent.taskId, intent.worker)) return { applied: false, reason: `task "${intent.taskId}" could not be taken` };
    return { applied: true };
  }

  /** Validate and apply a submission intent; verify gating happens in the caller. */
export function applySubmissionIntent(intent: TaskIntent): { ok: boolean; error?: string } {
    if (intent.status !== "completed" && intent.status !== "failed") {
      return { ok: false, error: `task "${intent.taskId}" has invalid submission status` };
    }
    const holder = hooks.get(intent.worker);
    if (!holder || holder.spawnId !== intent.spawnId || holder.status === "stopped") {
      return { ok: false, error: `worker "${intent.worker}" is not a living current incarnation` };
    }
    const task = tasks[intent.taskId];
    if (!task) return { ok: false, error: `unknown task "${intent.taskId}"` };
    if (task.status !== "in_progress" && task.status !== "superseded") {
      return { ok: false, error: `task "${intent.taskId}" is not in progress` };
    }
    if (task.claimedBy !== intent.worker) {
      return { ok: false, error: `task "${intent.taskId}" is claimed by ${task.claimedBy ?? "someone else"}` };
    }
    if (task.status === "superseded" && intent.status !== "failed") {
      return { ok: false, error: `task "${intent.taskId}" was superseded by "${task.supersededBy ?? "a replacement"}"; submit failed to acknowledge cancellation` };
    }
    if (intent.status === "failed") {
      // A superseded task stays superseded: its replacement stands, and only the
      // holder's lease comes back. Anything else is a recorded failure, which
      // returns the task to pending under a recovery hold.
      if (task.status === "superseded") {
        acknowledgeSupersession(intent.taskId, intent.worker, intent.result?.trim() || "Cancellation acknowledged.");
      } else {
        completeTaskWithOutcome(intent.taskId, intent.worker, "failed", intent.result?.trim() || "Agent reported failure.");
      }
      return { ok: true };
    }
    completeTaskWithOutcome(intent.taskId, intent.worker, "success", intent.result?.trim() || undefined);
    return { ok: true };
  }

export function loadBoard(persisted: Record<string, BoardTask>): number {
    let reloaded = 0;
    for (const task of Object.values(persisted)) {
      const orphanedHolding = task.status === "in_progress" || task.status === "superseded";
      const restored: BoardTask = {
        ...task,
        resources: normalizeResources(task.resources),
        status: task.status === "in_progress" ? "pending" : task.status,
        recoveryRequired: task.status === "in_progress" ? true : task.recoveryRequired,
        // Runtime workers and assignments die with the session. Superseded work
        // remains visible for audit but cannot retain a dead holder/resource lock.
        claimedBy: orphanedHolding ? undefined : task.claimedBy,
        updatedAt: Date.now(),
      };
      tasks[restored.id] = restored;
      reloaded++;
    }
    if (reloaded > 0) {
      hooks.changed();
    }
    return reloaded;
  }
// ── Public task surface ──────────────────────────────────────────────────────
//
// The four actions a task board exposes to every process: create, list, update,
// complete, reopen. They are here rather than in a tool layer so the same
// transitions back a single-session board, a spawned agent, and a caller's
// direct use, and so no caller can reach a transition the tool does not name.
//
// Two properties are deliberate and load-bearing:
//
// **Ownership is derived, never declared.** There is no parameter anywhere in
// this section through which a caller could name who takes a task. The holder is
// the `holder` argument, which the tool layer fills from the caller's own
// runtime identity, so naming somebody else is not expressible rather than merely
// rejected. That is why `takeTask` takes a name while no action takes an
// assignee.
//
// **A task with no live holder is a fallback acceptance, not a takeover.**
// `completeTaskWithOutcome` refuses when someone else is actively holding it, so
// a leader cannot close work that a running agent is still doing, and cannot
// forge completion either.

/** Why a take was refused. A caller turns this into user-facing text. */
export type TakeRefusal =
  | "unknown"
  | "not-pending"
  | "held-by-other"
  | "unmet-dependencies"
  | "recovery-hold-needs-reason"
  | "resource-conflict"
  | "participant-unavailable";

/** Reason text for a refused take, naming the blocker where one exists. */
export function takeRefusalReason(taskId: string, refusal: TakeRefusal, detail?: string): string {
  switch (refusal) {
    case "unknown": return `Task "${taskId}" does not exist.`;
    case "not-pending": return `Task "${taskId}" is not pending.`;
    case "held-by-other": return `Task "${taskId}" is in progress${detail ? ` by @${detail}` : ""}.`;
    case "unmet-dependencies": return `Task "${taskId}" has unmet dependencies.`;
    case "recovery-hold-needs-reason": return `Task "${taskId}" failed its last attempt. Take it with a reason stating how the blocker was addressed.`;
    case "resource-conflict": return `Task "${taskId}" conflicts with active work${detail ? ` held by @${detail}` : ""}.`;
    case "participant-unavailable": return `Task "${taskId}" cannot be taken: no current participant.`;
  }
}

/**
 * Take a task, deriving the holder from the caller's own identity.
 *
 * Exactly one of two concurrent callers wins. The loser is told who holds the
 * task rather than receiving a second copy, so a race cannot produce two
 * participants both believing they own the same resources.
 *
 * `reason` is required only while a recovery hold is set. That is a stated
 * justification rather than a role check on purpose: a role check would put
 * participant identity back into the task, which is exactly what deriving the
 * holder removed.
 */
export function takeTask(
  taskId: string,
  holder: string,
  options: { reason?: string } = {},
): { ok: true; task: BoardTask } | { ok: false; refusal: TakeRefusal; detail?: string; reason: string } {
  const task = tasks[taskId];
  if (!task) return { ok: false, refusal: "unknown", reason: takeRefusalReason(taskId, "unknown") };
  if (task.status === "in_progress") {
    const other = task.claimedBy && task.claimedBy !== holder ? task.claimedBy : undefined;
    return { ok: false, refusal: "held-by-other", detail: other, reason: takeRefusalReason(taskId, "held-by-other", other) };
  }
  if (task.status !== "pending") {
    return { ok: false, refusal: "not-pending", reason: takeRefusalReason(taskId, "not-pending") };
  }
  if (!task.dependsOn.every((dep) => tasks[dep]?.status === "completed")) {
    return { ok: false, refusal: "unmet-dependencies", reason: takeRefusalReason(taskId, "unmet-dependencies") };
  }
  if (task.recoveryRequired && !options.reason?.trim()) {
    return { ok: false, refusal: "recovery-hold-needs-reason", reason: takeRefusalReason(taskId, "recovery-hold-needs-reason") };
  }
  // Only meaningful with a coordinator. Standalone, the single participant is
  // the caller by construction, so there is nothing to check them against.
  if (coordinated && holder !== MAIN_SESSION) {
    const participant = hooks.get(holder);
    if (!participant || participant.status === "stopped") {
      return { ok: false, refusal: "participant-unavailable", reason: takeRefusalReason(taskId, "participant-unavailable") };
    }
  }
  const conflict = coordinated ? hooks.conflicting(task.resources, holder) : undefined;
  if (conflict) {
    return { ok: false, refusal: "resource-conflict", detail: conflict.name, reason: takeRefusalReason(taskId, "resource-conflict", conflict.name) };
  }
  task.status = "in_progress";
  task.claimedBy = holder;
  task.recoveryRequired = undefined;
  if (options.reason?.trim()) task.recoveryNote = options.reason.trim();
  task.updatedAt = Date.now();
  hooks.changed();
  hooks.sync(holder, { id: `board:${randomUUID()}`, kind: "board", resources: task.resources }, task.id);
  return { ok: true, task };
}

/** Fields a caller may change on a task it is not taking. */
export interface TaskUpdate {
  description?: string;
  verify?: string;
  resources?: string[];
  context?: BoardTask["context"];
}

/**
 * Change a task's content without changing who holds it.
 *
 * Deliberately accepts no status: a status transition goes through `takeTask`,
 * `completeTaskWithOutcome`, or `reopenTask`, so every position in the lifecycle
 * is reachable by exactly one named operation. An open `status` field here would
 * let a caller bypass the preconditions those operations enforce, which is the
 * same reason `supersede` was folded into `create(supersedes)` rather than kept
 * as a verb.
 */
export function updateTask(taskId: string, patch: TaskUpdate): { ok: true; task: BoardTask } | { ok: false; reason: string } {
  const task = tasks[taskId];
  if (!task) return { ok: false, reason: `Task "${taskId}" does not exist.` };
  if (patch.description !== undefined) task.description = patch.description.trim() || undefined;
  if (patch.verify !== undefined) task.verify = patch.verify.trim() || undefined;
  if (patch.resources !== undefined) task.resources = normalizeResources(patch.resources);
  if (patch.context !== undefined) task.context = { ...(task.context ?? {}), ...patch.context };
  task.updatedAt = Date.now();
  hooks.changed();
  return { ok: true, task };
}

/**
 * Deliver a task's outcome. `failed` returns it to pending under a recovery hold
 * with the blocker retained as evidence.
 *
 * The holder check is the whole point. When somebody else holds the task the
 * call is refused, so a stale attempt, a different agent, or the leader cannot
 * report a result for work it is not doing. With no live holder any participant
 * may close the task, which is the fallback path when an agent died mid-task.
 */
export function completeTaskWithOutcome(
  taskId: string,
  holder: string,
  outcome: "success" | "failed",
  result?: string,
): { ok: true; task: BoardTask } | { ok: false; reason: string } {
  const task = tasks[taskId];
  if (!task) return { ok: false, reason: `Task "${taskId}" does not exist.` };
  if (outcome !== "success" && outcome !== "failed") {
    return { ok: false, reason: `Task "${taskId}" has invalid submission outcome` };
  }
  // Two statuses are refused before the holder check, because neither is
  // completable and the holder check cannot see the difference: a completed task
  // is already terminal, and a superseded one has been replaced — completing it
  // would leave the board claiming both the original and its replacement are
  // done, which is the one outcome a supersession exists to prevent.
  if (task.status === "completed") {
    return { ok: false, reason: `Task "${taskId}" is already completed.` };
  }
  if (task.status === "superseded") {
    return { ok: false, reason: `Task "${taskId}" was superseded by "${task.supersededBy ?? "a replacement"}"; deliver the outcome against the replacement.` };
  }
  if (task.claimedBy && task.claimedBy !== holder) {
    return { ok: false, reason: `Task "${taskId}" is in progress by @${task.claimedBy}; only its holder may deliver the outcome.` };
  }
  const previous = task.claimedBy;
  // Retained evidence round-trips byte-for-byte. Trimming decides only whether
  // there is evidence at all, so a whitespace-only result records nothing while a
  // real one keeps whatever the caller supplied, trailing newline included.
  task.result = result?.trim() ? result : undefined;
  if (outcome === "failed") {
    task.status = "pending";
    task.claimedBy = undefined;
    task.recoveryRequired = true;
    task.completedAt = undefined;
  } else {
    task.status = "completed";
    task.claimedBy = undefined;
    task.recoveryRequired = undefined;
    task.completedAt = Date.now();
  }
  task.updatedAt = Date.now();
  hooks.changed();
  if (previous) hooks.sync(previous, undefined, undefined);
  return { ok: true, task };
}

/**
 * Return a completed task to pending.
 *
 * Refused while a dependent is in progress, naming it, because reopening a task
 * its successor is already building against would silently invalidate that
 * successor's premise.
 */
export function reopenTask(taskId: string): { ok: true; task: BoardTask } | { ok: false; reason: string } {
  const task = tasks[taskId];
  if (!task) return { ok: false, reason: `Task "${taskId}" does not exist.` };
  if (task.status !== "completed") {
    return { ok: false, reason: `Task "${taskId}" is not completed.` };
  }
  const blockers = claimedDependents(taskId);
  if (blockers.length > 0) {
    return { ok: false, reason: `Task "${taskId}" has a dependent in progress: ${blockers.map((blocker) => blocker.id).join(", ")}.` };
  }
  task.status = "pending";
  task.claimedBy = undefined;
  task.result = undefined;
  task.deferredMessages = undefined;
  task.errorMessage = undefined;
  task.recoveryRequired = undefined;
  task.completedAt = undefined;
  task.updatedAt = Date.now();
  hooks.changed();
  return { ok: true, task };
}
