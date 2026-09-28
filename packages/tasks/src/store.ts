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

export const tasks: Record<string, BoardTask> = Object.create(null);

const NO_HOOKS: BoardStoreHooks = {
  get: () => undefined,
  conflicting: () => undefined,
  sync: () => {},
  changed: () => {},
};

export let hooks:
 BoardStoreHooks = NO_HOOKS;

export function configureBoardStore(next: BoardStoreHooks): void {
  hooks = next;
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

export function setTaskClaimed(taskId: string, workerName: string): BoardTask | undefined {
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

export function releaseTask(taskId: string, errorMessage: string | undefined, recoveryRequired: boolean): BoardTask | undefined {
    const task = tasks[taskId];
    if (!task || (task.status !== "in_progress" && task.status !== "superseded")) return undefined;
    const holder = task.claimedBy;
    if (task.status === "in_progress") task.status = "pending";
    task.claimedBy = undefined;
    task.recoveryRequired = task.status === "pending" && recoveryRequired ? true : undefined;
    if (errorMessage !== undefined) task.errorMessage = errorMessage;
    task.updatedAt = Date.now();
    hooks.changed();
    if (holder) hooks.sync(holder, undefined, undefined);
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

export function completeTask(taskId: string, result?: string): BoardTask | undefined {
    const task = tasks[taskId];
    if (!task || task.status !== "in_progress") return undefined;
    const holder = task.claimedBy;
    task.status = "completed";
    task.claimedBy = undefined;
    task.result = result;
    task.errorMessage = undefined;
    task.recoveryRequired = undefined;
    task.completedAt = Date.now();
    task.updatedAt = Date.now();
    hooks.changed();
    if (holder) hooks.sync(holder, undefined, undefined);
    return task;
  }

  /** Release every task held by a named agent (crash or shutdown). */
export function releaseTasksOf(workerName: string, reason: string): BoardTask[] {
    const released: BoardTask[] = [];
    for (const task of listTasks()) {
      if ((task.status === "in_progress" || task.status === "superseded") && task.claimedBy === workerName) {
        releaseTask(task.id, reason, true);
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
      releaseTask(intent.taskId, intent.result?.trim() || "Agent reported failure.", true);
      return { ok: true };
    }
    completeTask(intent.taskId, intent.result?.trim() || undefined);
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