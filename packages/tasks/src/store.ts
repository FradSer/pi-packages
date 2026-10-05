/**
 * Task storage: one container and one closed set of transitions over Tasks,
 * the participant holding each, and the resources that holding leases.
 *
 * The task store states what must be done. It does not dispatch work to a named
 * participant, and it knows nothing about how participants are reached: the
 * participant registry published by a process layer is read through the seam
 * below, and everything the task store needs to know about a participant arrives
 * through that one channel.
 */

import { randomUUID } from "node:crypto";
import type { Participant, ParticipantAssignment, ParticipantRegistry } from "@fradser/pi-kit";
import { resolveParticipantRegistry } from "@fradser/pi-kit";
import {
  DEFAULT_CONTEXT_BUDGET_BYTES,
  contextCarriesValue,
  mergeTaskContext,
  normalizeTaskContext,
  withinContextBudget,
} from "./context.ts";
import { canonicalDependencies, hasDependencyCycle, normalizeResources, resourcesConflict, taskIdFromSubject } from "./graph.ts";
import { isTaskStatus, resolveRecordKind, type CompletionVerdict, type Task, type TaskIntent, type TaskStatus } from "./types.ts";

/** A holder's lease on the Task it holds. The participant registry publishes this
 *  same record, so the two sides mirror one shape rather than translating. */
export type WorkAssignment = ParticipantAssignment;

/** A participant as the tasks sees it: which one, which incarnation, and what it
 *  currently holds. A projection published by the registry, never the registry's
 *  own entry. */
export type WorkHolder = Participant;

/**
 * The tasks's one channel to whatever publishes participants.
 *
 * `current` is a question rather than a comparison the tasks performs itself: a
 * retired incarnation and a replaced one are the same fact, and the layer that
 * mints incarnations is the only one that can answer it.
 */
export interface TaskStoreHooks {
  get(holder: string): WorkHolder | undefined;
  /** Whether `holder` can hold a Task now, and whether `incarnation` is its
   *  current one. Omitting `incarnation` asks only about the holder. */
  current(holder: string, incarnation?: string): boolean;
  conflicting(resources: readonly string[], exceptHolder?: string): WorkHolder | undefined;
  sync(holder: string, assignment: WorkAssignment | undefined, taskId: string | undefined): void;
  changed(): void;
}

export const MAX_TASK_DEPENDENCIES = 32;

/** Ceiling on one Task's resource tags.
 *
 *  Present because every other model-supplied list on a Task has one, and
 *  without it the tags are the one field a caller can grow without limit: they
 *  are re-serialized into the tasks file on every change, and the conflict check
 *  is linear in them, so the file is where the cost lands. */
export const MAX_TASK_RESOURCES = 32;

/** The main session's tasks identity: the process that owns the tasks when no
 *  participant is bound to it.
 *
 * It is exempt from the reachability check below because that check exists to
 * stop a *departed* participant from taking work, and the main session is not a
 * participant — it cannot depart or be replaced. A single-participant install has
 * no registry at all, so without this exemption every take would be refused and
 * the standalone tasks would be unusable. */
export const MAIN_SESSION = "main";

export const tasks: Record<string, Task> = Object.create(null);

/**
 * The default store: the tasks alone, extended by whichever layer published a
 * participant registry beside it.
 *
 * Consulted at use time rather than configured at load time, so a task set
 * integrates with a registry by the two being installed together and installation
 * order stops mattering. Every piece of policy stays on this side — the registry
 * supplies participants, `resourcesConflict` decides — so a publisher never owns
 * a rule the tasks then has to agree with.
 */
const SINGLE_PARTICIPANT: TaskStoreHooks = {
  get: (holder) => publishedRegistry()?.get(holder),
  current: () => true,
  conflicting: (resources, exceptHolder) => {
    for (const holder of publishedRegistry()?.list() ?? []) {
      if (holder.name === exceptHolder) continue;
      const assignment = holder.assignment;
      if (assignment && !assignment.closed && resourcesConflict(resources, assignment.resources)) {
        return holder;
      }
    }
    return undefined;
  },
  sync: (holder, assignment, taskId) => {
    publishedRegistry()?.sync(holder, assignment, taskId);
  },
  // A registry has no snapshot writer, so there is nothing to mark.
  changed: () => {},
};

let hooks: TaskStoreHooks = SINGLE_PARTICIPANT;

/** True once a layer has claimed this task set's store outright. */
let coordinated = false;

/** Notified after every recorded change, so a layer that owns the durable file
 *  can write it. Separate from `hooks.changed` because a registry publishes no
 *  snapshot writer of its own. */
let onChange: (() => void) | undefined;

/** A task set-level notice a caller should see: a durable file that was present but
 *  could not be read, for instance. Never set for a merely absent file, which is
 *  a fresh tasks rather than a problem. */
let diagnostic: string | undefined;

/**
 * Whether this task set has participants beyond the main session.
 *
 * A coordinator claims the tasks; otherwise a published participant registry
 * counts, because that is what separates a task set with participants from a
 * single-participant tasks. Without it, `hooks.get` returns undefined for
 * everybody — including the main session, which by definition is not a published
 * participant — and every take would be refused, making a standalone install
 * unusable.
 *
 * This is a question about participants, not about who writes the durable file:
 * a published participant registry makes a take check somebody else's lease,
 * while claiming nothing about the store. `isTaskStoreClaimed` is the other
 * question.
 *
 * Exported so a tool can report which mode it is in rather than guessing from an
 * empty participant set.
 */
export function isCoordinated(): boolean {
  return coordinated || Boolean(publishedRegistry());
}

/**
 * Whether a layer has claimed this task set's store outright, and with it the duty
 * of writing the durable file.
 *
 * Narrower than `isCoordinated()` on purpose. A published participant registry
 * makes this task set aware of other holders; the default store's own `changed` hook
 * is a no-op, so nobody is writing the file on the task set's behalf. Answering
 * "somebody is coordinated" to the question of who owns the file stood this
 * package down on a task set nobody else was writing: the tasks were recorded, no
 * file appeared, and nothing reported it.
 */
export function isTaskStoreClaimed(): boolean {
  return coordinated;
}

/** Replace the store's participant source. Claims the tasks outright. */
export function configureTaskStore(next: TaskStoreHooks): void {
  hooks = next;
  coordinated = true;
}

/**
 * Publish the participant registry this task set reads.
 *
 * Taken here rather than imported because this package owns no process concept:
 * the layer that publishes a registry knows about participants, and a task set that
 * imported it would put that knowledge in the wrong package. Registered through
 * the shared runtime so both sides name one declared contract instead of
 * agreeing on a string key by convention.
 */
function publishedRegistry(): ParticipantRegistry | undefined {
  const registry = resolveParticipantRegistry();
  // Shape-checked rather than trusted: a stale registry from an older install, or
  // anything else on this key, has to degrade to a single-participant tasks
  // rather than throw in the middle of a take.
  return registry && typeof registry.get === "function" && typeof registry.list === "function"
    && typeof registry.sync === "function" && typeof registry.current === "function"
    ? registry
    : undefined;
}

/** Record a change: tell whoever owns the store, then whoever owns the file. */
function markChanged(): void {
  hooks.changed();
  onChange?.();
}

/** Write the tasks to durable storage after every recorded change. Idempotent.
 *
 *  Passing nothing releases the writer, which is what a session switch needs
 *  before it decides whether to attach a new one. A writer left over from the
 *  session that was just left would put the new session's work in the old
 *  session's file: two task sets, one writer, and neither holding what it claims. */
export function onTasksChanged(write: (() => void) | undefined): void {
  onChange = write;
}

/** A notice a caller should surface, or undefined when the task store is healthy. */
export function storeNotice(): string | undefined {
  return diagnostic;
}

export function setStoreNotice(notice: string | undefined): void {
  diagnostic = notice;
}

/** Drop every Task. The runtime's own reset between fixtures and sessions. */
export function clearTasks(): void {
  for (const id of Object.keys(tasks)) delete tasks[id];
  diagnostic = undefined;
}

// ── Reading ────────────────────────────────────────────────────────────────

export function getTask(taskId: string): Task | undefined {
  return tasks[taskId];
}

export function listTasks(): Task[] {
  return Object.values(tasks).sort((a, b) => a.id.localeCompare(b.id));
}

export function pendingTasks(): Task[] {
  return listTasks().filter((task) => task.status === "pending");
}

/** Tasks a caller may take right now.
 *
 *  The one definition of the answer. `list_tasks` and the reminder before
 *  settlement read this rather than keeping their own copy: a copy that drifts
 *  reports less available work than `takeTask` accepts, so a pending task the
 *  take path would hand over disappears from the two places a caller looks for
 *  it, and nothing reports the disagreement. */
export function claimableTasks(): Task[] {
  return pendingTasks().filter((task) => task.recordKind !== "execution" && taskDependenciesMet(task));
}

/** The declared dependencies that are not completed, in declaration order.
 *
 *  `dependsOn` says what the edges are; this says which of them are unfinished,
 *  which is the comparison a caller would otherwise make by hand against a list.
 *  A task with no dependencies is never blocked, and one whose dependencies have
 *  all completed names nothing. */
export function blockedDependencies(task: Task): string[] {
  return task.dependsOn.filter((id) => tasks[id]?.status !== "completed");
}

/** Tasks that could be completed right now.
 *
 *  The read side of the completion checks. Two conditions, both about state the
 *  store already holds: an attempt has to be on the record — the task is in
 *  progress, or it is pending under a recovery hold a dead holder left — and every
 *  declared dependency has to be completed.
 *
 *  Paired with `claimableTasks` on purpose. That answers "what can I start", and a
 *  model that has just finished one of n tasks needs the other question: which of
 *  the rest can I mark done, so the batch does not have to be discovered one
 *  refused completion at a time. */
export function completableTasks(): Task[] {
  return listTasks().filter((task) => task.recordKind !== "execution" && (
    task.status === "in_progress" || task.status === "recovery_hold"
  ) && blockedDependencies(task).length === 0);
}

export function taskDependenciesMet(task: Task): boolean {
  return task.status === "pending" && task.dependsOn.every((dep) => tasks[dep]?.status === "completed");
}

/** Every Task transitively depending on `taskId` that `select` accepts.
 *
 *  One walk, two questions. Reopening asks about dependents that are *held* —
 *  they are building against a premise that is about to move. It also asks about
 *  dependents that are *completed*, because a conclusion drawn on a withdrawn
 *  premise has to be pulled back with it. Two predicates over one traversal, so
 *  the reverse graph is built and bounded in exactly one place. */
function transitiveDependents(taskId: string, select: (task: Task) => boolean): Task[] {
  const reverse = new Map<string, string[]>();
  for (const task of Object.values(tasks)) {
    for (const dependency of task.dependsOn) {
      const dependents = reverse.get(dependency) ?? [];
      dependents.push(task.id);
      reverse.set(dependency, dependents);
    }
  }
  const visited = new Set<string>();
  const pending = [...(reverse.get(taskId) ?? [])];
  const found: Task[] = [];
  // Bounded by `visited`: the graph is acyclic by construction, and the visited
  // set makes that a guarantee rather than an assumption.
  while (pending.length > 0) {
    const id = pending.shift()!;
    if (visited.has(id)) continue;
    visited.add(id);
    const task = tasks[id];
    if (!task) continue;
    if (select(task)) found.push(task);
    pending.push(...(reverse.get(id) ?? []));
  }
  return found.sort((left, right) => left.id.localeCompare(right.id));
}

/** Every Task transitively depending on `taskId` that is currently being held. */
export function claimedDependents(taskId: string): Task[] {
  return transitiveDependents(
    taskId,
    (task) => task.status === "in_progress" || (task.status === "superseded" && task.claimedBy !== undefined),
  );
}

/** Every Task transitively depending on `taskId` that is already completed. */
export function completedDependents(taskId: string): Task[] {
  return transitiveDependents(taskId, (task) => task.status === "completed");
}

// ── Recording ──────────────────────────────────────────────────────────────

export function createTask(input: {
    id?: string;
    recordKind?: "task" | "execution";
    subject: string;
    description?: string;
    dependsOn?: string[];
    verify?: string;
    resources?: string[];
    supersedes?: string[];
  }): { ok: true; task: Task; superseded: Task[] } | TaskRefusalResult {
    const subject = input.subject.trim();
    if (!subject) return refuse("invalid-content", "Task subject must not be empty.");
    const requestedDependencies = [...new Set(input.dependsOn ?? [])];
    const requestedSupersedes = [...new Set(input.supersedes ?? [])];
    if (requestedDependencies.length > MAX_TASK_DEPENDENCIES) {
      return refuse("resource-limit", `Task depends on more than ${MAX_TASK_DEPENDENCIES} tasks.`);
    }
    const resources = normalizeResources(input.resources);
    if (resources.length > MAX_TASK_RESOURCES) {
      return refuse("resource-limit", `Task declares more than ${MAX_TASK_RESOURCES} resources.`);
    }
    for (const taskId of [...requestedDependencies, ...requestedSupersedes]) {
      if (!tasks[taskId]) return refuse("unknown-task", `Task references unknown task "${taskId}".`, taskId);
    }
    const completedTarget = requestedSupersedes.find((taskId) => tasks[taskId]?.status === "completed");
    if (completedTarget) {
      return refuse("invalid-supersession", `Task cannot supersede completed task "${completedTarget}".`, completedTarget);
    }
    const dependsOn = canonicalDependencies(requestedDependencies, tasks);
    const supersedes = canonicalDependencies(requestedSupersedes, tasks);
    if (!dependsOn || !supersedes) return refuse("invalid-dependency", "Task dependency or supersession chain is invalid or cyclic.");
    const canonicalCompletedTarget = supersedes.find((taskId) => tasks[taskId]?.status === "completed");
    if (canonicalCompletedTarget) {
      return refuse("invalid-supersession", `Task cannot supersede completed task "${canonicalCompletedTarget}".`, canonicalCompletedTarget);
    }
    const selfReplacement = supersedes.find((taskId) => dependsOn.includes(taskId));
    if (selfReplacement) {
      return refuse("invalid-supersession", `Task cannot both depend on and supersede "${selfReplacement}".`, selfReplacement);
    }

    const id = input.id ?? taskIdFromSubject(subject, new Set(Object.keys(tasks)));
    if (tasks[id]) return refuse("already-exists", `Task id "${id}" already exists.`, id);
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
      return refuse("invalid-dependency", "Task supersession would create a dependency cycle.");
    }

    const task: Task = {
      id,
      ...(input.recordKind ? { recordKind: input.recordKind } : {}),
      subject,
      description: input.description?.trim() || undefined,
      dependsOn,
      verify: input.verify?.trim() || undefined,
      resources,
      status: "pending",
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    // A creation is a write like any other, and everything it retains is free
    // text a model wrote. Budgeting only on update would let the first write past
    // a ceiling every later one is held to. Named by its derived id rather than
    // quoted back: the refusal is model-facing text, and a 70 KB subject would
    // otherwise be answered with 70 KB of it.
    if (!withinContextBudget(task)) {
      return refuse("budget-exceeded", `Task "${id}" exceeds the byte budget its own content allows.`, id);
    }
    tasks[id] = task;
    const superseded: Task[] = [];
    for (const oldId of supersedes) {
      const old = tasks[oldId];
      if (!old || old.status === "completed" || old.status === "superseded") continue;
      old.status = "superseded";
      old.supersededBy = id;
      // A living holder keeps the claim and lease until it acknowledges
      // cancellation or stops. Releasing its resources before it receives the
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
    // Marked once, after every mutation this call makes — not between them. A
    // supersession rewrites the obsolete task and every dependent's edges, and a
    // mark placed before those loops persisted a task set saying the obsolete task
    // was still pending and its dependents still pointed at it. Nothing marked it
    // again, so a session whose last change was a supersession wrote a task set file
    // that disagreed with the tasks it had just changed, and a restart loaded
    // that disagreement.
    markChanged();
    return { ok: true, task, superseded };
  }

/**
 * Attach per-Task context. Additive at every level: a brief a successor reads is
 * folded into the one already there rather than replacing it, and refs pass
 * through the normalization that caps them. Refused when the result would exceed
 * the Task's byte budget, because a context nothing can outgrow is not a bound.
 */
export function setTaskContext(
    taskId: string,
    context: NonNullable<Task["context"]>,
  ): { ok: true; task: Task } | TaskRefusalResult {
    const task = tasks[taskId];
    if (!task) return refuse("unknown-task", `Task "${taskId}" does not exist.`, taskId);
    const read = normalizeTaskContext(context);
    if (!read.ok) return refuse("context-unreadable", `Task "${taskId}" ${read.error}`, taskId);
    // A context whose every value was blank normalizes to nothing, and recording
    // nothing while reporting success is the one outcome this reader exists to
    // prevent. A blank field *beside* a real one is still fine.
    if (!contextCarriesValue(read.value)) {
      return refuse("context-empty", `Task "${taskId}" context carries no value to record; nothing was written.`, taskId);
    }
    const next = mergeTaskContext(task.context, read.value);
    if (!withinContextBudget({ ...task, context: next })) {
      return refuse("budget-exceeded", `Task "${taskId}" context exceeds its byte budget.`, taskId);
    }
    task.context = next;
    task.updatedAt = Date.now();
    markChanged();
    return { ok: true, task };
  }

/**
 * Restore a persisted tasks.
 *
 * An in-progress Task comes back pending under a recovery hold: the participant
 * that held it is not in this task set, so continuing to call it in progress would
 * show work nobody is doing, and handing it straight back to the take path would
 * retry an attempt whose outcome is unknown.
 */
export function loadTasks(persisted: Record<string, Task>): number {
  let reloaded = 0;
  // What a hand-edited, truncated, or older-build tasks file cost this session.
  // Reported rather than swallowed: dropping a field silently is how a restored
  // task state disagrees with the persisted data.
  const notices: string[] = [];
  for (const [persistedId, task] of Object.entries(persisted)) {
    const repairedIdentity = typeof task.id !== "string" || task.id.trim() === "";
    // The persisted map key preserves the identity when the record's id is
    // absent or invalid. Keep the repaired task under a hold for inspection.
    const id = repairedIdentity ? persistedId : task.id;
    if (repairedIdentity) {
      notices.push(`task "${persistedId}" had no valid id; its persisted key was used under a recovery hold`);
    }
    // Every field the rest of the task store reads is read back through the same
    // checks the write path applies, because this is the other route into the
    // store. Validating only on write left a restored `budgetBytes` unclamped, a
    // context spread straight from the file, and a `dependsOn` holding something
    // other than task ids — all reachable by editing one line of JSON.
    const rawRecordKind: unknown = task.recordKind;
    const invalidRecordKind = rawRecordKind !== undefined && rawRecordKind !== "task" && rawRecordKind !== "execution";
    const recordKind = resolveRecordKind(rawRecordKind, id);
    if (invalidRecordKind) notices.push(`task "${id}" has invalid recordKind; it remains a task under a recovery hold`);
    const rawStatus: unknown = task.status;
    const knownStatus = isTaskStatus(rawStatus);
    if (!knownStatus) {
      notices.push(`task "${task.id}" has status ${JSON.stringify(rawStatus)}, which this task set does not define`);
    }
    const orphanedHolding = rawStatus === "in_progress" || rawStatus === "superseded";
    const rawContext = task.context as { budgetBytes?: unknown } | undefined;
    const readContext = task.context === undefined ? undefined : normalizeTaskContext(task.context);
    const context = readContext?.ok ? readContext.value : undefined;
    if (task.context !== undefined && !readContext?.ok) {
      notices.push(`task "${task.id}" has a context this task set cannot read (${readContext?.error ?? "unreadable"}); it was dropped`);
    }
    // The clamp itself belongs to the reader, so it is applied once. What is
    // reported here is that the file said something else: the next tasks write
    // persists the clamped value, so a budget that named a gigabyte is a fact
    // worth surfacing rather than a silent repair.
    if (typeof rawContext?.budgetBytes === "number" && rawContext.budgetBytes > DEFAULT_CONTEXT_BUDGET_BYTES) {
      notices.push(`task "${task.id}" named a budget above the task set's default; it was clamped`);
    }
    const rawDependencies = Array.isArray(task.dependsOn) ? task.dependsOn : [];
    const dependsOn = rawDependencies.filter((id): id is string => typeof id === "string" && id.trim() !== "");
    if (dependsOn.length !== rawDependencies.length) {
      notices.push(`task "${task.id}" listed a dependency that is not a task id; those entries were dropped`);
    }
    // A file written before `recovery_hold` was a status carried the state as a
    // flag beside `pending`. The two spellings mean the same thing, so the flag
    // is read here once and never written back; the status is now the only one.
    // A `pending` record that still names a claimant says the same thing, since
    // a take is what writes that field and every transition that undoes one
    // clears it.
    const legacy = task as Task & { recoveryRequired?: unknown };
    const legacyHold = legacy.recoveryRequired === true;
    const { recoveryRequired: _legacyHold, ...carried } = legacy;
    const attempted = rawStatus === "pending" && (legacyHold || task.claimedBy !== undefined);
    // A status this task set cannot read is a state it cannot describe, so it is
    // treated like work whose attempt did not stand: kept and held. Dropping the
    // Task would discard real work; trusting the value would put the tasks in a
    // state the store never enters, and every projection of it would then fail
    // the declared result schema.
    const unrestorable = !knownStatus || repairedIdentity || invalidRecordKind;
    const restoredStatus: TaskStatus = unrestorable || attempted || rawStatus === "in_progress"
      ? "recovery_hold"
      : rawStatus as TaskStatus;
    const restored: Task = {
      ...carried,
      id,
      // Earlier generated direct-input ids use this reserved UUID namespace.
      // Explicit record metadata wins; ordinary user task ids are unchanged.
      recordKind,
      resources: normalizeResources(task.resources),
      dependsOn,
      context,
      status: restoredStatus,
      // Restored task state has no participants, so a held Task cannot keep naming
      // one. Superseded work stays visible for audit but retains no dead lease.
      claimedBy: orphanedHolding || repairedIdentity ? undefined : task.claimedBy,
      updatedAt: Date.now(),
    };
    tasks[restored.id] = restored;
    reloaded++;
  }
  if (notices.length > 0) {
    setStoreNotice(
      [diagnostic, `The restored task storage needed repair: ${notices.join("; ")}.`].filter(Boolean).join(" "),
    );
  }
  if (reloaded > 0) {
    markChanged();
  }
  return reloaded;
}

// ── The task surface ───────────────────────────────────────────────────────
//
// The four actions a task set exposes to every participant: create, list, update,
// complete, reopen. They are here rather than in a tool layer so the same
// transitions back a standalone tasks, a participant's tasks, and a caller's
// direct use, and so no caller can reach a transition the tool does not name.
//
// Two properties are deliberate and load-bearing:
//
// **Ownership is derived, never declared.** There is no parameter anywhere in
// this section through which a caller could name who takes a task. The holder is
// the `holder` argument, which the tool layer fills from the caller's own
// runtime identity, so naming somebody else is not expressible rather than
// merely rejected. That is why `takeTask` takes a name while no action takes an
// assignee.
//
// **A task with no live holder is a fallback acceptance, not a takeover.**
// `completeTaskWithOutcome` refuses when someone else is actively holding it, so
// a stale attempt, a different participant, or the main session cannot close work
// that is still being done, and cannot forge completion either.

/** Every refusal the task store returns, as one closed set of machine codes.
 *
 *  A caller that wanted to branch on *why* could only do it for a take: the
 *  other refusals arrived as free text under two different field names, so the
 *  branch existed or did not exist depending on which operation produced it.
 *  One set means one exhaustive switch, and a refusal added to the store joins a
 *  list every caller already has to handle. */
export type TaskRefusal =
  | TakeRefusal
  | CompletionRefusal
  | "unknown-task"
  | "already-exists"
  | "invalid-content"
  | "invalid-dependency"
  | "invalid-supersession"
  | "resource-limit"
  | "budget-exceeded"
  | "context-unreadable"
  | "context-empty"
  | "invalid-outcome"
  | "already-completed"
  | "superseded"
  | "not-completed"
  | "not-in-progress"
  | "lease-held"
  | "bind-not-allowed";

/** The refusal itself, with no success flag.
 *
 *  `refusal` is the machine code, `reason` is the sentence a caller or a model
 *  reads, and `detail` names what the refusal is about when it is about
 *  something: a task id, a holder, a prerequisite. The success flag is not part
 *  of it, because an operation keeps the answer its own domain calls it — `ok`
 *  for a task write, `applied` for a claim marker. The payload has one shape and
 *  each path adds only its own flag. */
export interface TaskRefusalPayload {
  refusal: TaskRefusal;
  detail?: string;
  reason: string;
}

/** A refusal carrying the `ok` flag a task write, a take, and a submission use. */
export type TaskRefusalResult = TaskRefusalPayload & { ok: false };

/** The claim marker's answer. `applied` is this path's word for success, and its
 *  failure is the store's one refusal, unchanged. */
export interface TaskClaimOutcome {
  applied: boolean;
  refusal?: TaskRefusal;
  detail?: string;
  reason?: string;
}

/** The submission marker's answer. Same refusal as every other refusal here;
 *  only the success word differs, because a submission reports whether it stuck. */
export interface TaskSubmissionOutcome {
  ok: boolean;
  refusal?: TaskRefusal;
  detail?: string;
  reason?: string;
}

/** The one place a refusal payload is built, which is what keeps the shape from
 *  drifting back into five forms. */
function refusalPayload(refusal: TaskRefusal, reason: string, detail?: string): TaskRefusalPayload {
  return { refusal, reason, ...(detail ? { detail } : {}) };
}

/** Refuse a task write, a take, or a submission. */
export function refuse(refusal: TaskRefusal, reason: string, detail?: string): TaskRefusalResult {
  return { ok: false, ...refusalPayload(refusal, reason, detail) };
}

/** Refuse a claim marker. Same payload, the flag this path's own domain uses. */
export function refuseClaim(refusal: TaskRefusal, reason: string, detail?: string): TaskClaimOutcome {
  return { applied: false, ...refusalPayload(refusal, reason, detail) };
}

/** Why a take was refused. A caller turns this into user-facing text. */
export type TakeRefusal =
  | "unknown-task"
  | "not-pending"
  | "held-by-other"
  | "unmet-dependencies"
  | "recovery-hold-needs-reason"
  | "resource-conflict"
  | "participant-unavailable";

/** Reason text for a refused take, naming the blocker where one exists. */
export function takeRefusalReason(taskId: string, refusal: TakeRefusal, detail?: string): string {
  switch (refusal) {
    case "unknown-task": return `Task "${taskId}" does not exist.`;
    case "not-pending": return `Task "${taskId}" is not pending.`;
    case "held-by-other": return `Task "${taskId}" is in progress${detail ? ` by @${detail}` : ""}.`;
    case "unmet-dependencies":
      return `Task "${taskId}" depends on ${detail ? detail.split(", ").map((id) => `"${id}"`).join(", ") : "a task"}, which is not completed.`;
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
): { ok: true; task: Task } | TaskRefusalResult {
  const task = tasks[taskId];
  if (!task) return refuse("unknown-task", takeRefusalReason(taskId, "unknown-task"), taskId);
  if (task.status === "in_progress") {
    const other = task.claimedBy && task.claimedBy !== holder ? task.claimedBy : undefined;
    return refuse("held-by-other", takeRefusalReason(taskId, "held-by-other", other), other);
  }
  if (task.status !== "pending" && task.status !== "recovery_hold") {
    return refuse("not-pending", takeRefusalReason(taskId, "not-pending"), taskId);
  }
  const unfinished = blockedDependencies(task);
  if (unfinished.length > 0) {
    // Named, because a task with several dependencies and one refusal telling the
    // caller only that some are unmet leaves it with nothing to act on. Every other
    // refusal here names its blocker; this one had been the exception.
    return refuse("unmet-dependencies", takeRefusalReason(taskId, "unmet-dependencies", unfinished.join(", ")), unfinished.join(", "));
  }
  if (task.status === "recovery_hold" && !options.reason?.trim()) {
    return refuse("recovery-hold-needs-reason", takeRefusalReason(taskId, "recovery-hold-needs-reason"), taskId);
  }
  // Only meaningful with a registry. Standalone, the single participant is the
  // caller by construction, so there is nothing to check them against.
  if (isCoordinated() && holder !== MAIN_SESSION && !hooks.current(holder)) {
    return refuse("participant-unavailable", takeRefusalReason(taskId, "participant-unavailable"), holder);
  }
  const conflict = isCoordinated() ? hooks.conflicting(task.resources, holder) : undefined;
  if (conflict) {
    return refuse("resource-conflict", takeRefusalReason(taskId, "resource-conflict", conflict.name), conflict.name);
  }
  return recordTake(task, holder, {
    ...(options.reason?.trim() ? { recoveryNote: options.reason.trim() } : {}),
  });
}

/** Fields a caller may change on a task it is not taking. */
export interface update_task {
  subject?: string;
  description?: string;
  dependsOn?: string[];
  verify?: string;
  resources?: string[];
  context?: Task["context"];
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
export function updateTask(taskId: string, patch: update_task): { ok: true; task: Task } | TaskRefusalResult {
  const task = tasks[taskId];
  if (!task) return refuse("unknown-task", `Task "${taskId}" does not exist.`, taskId);
  const nextSubject = patch.subject === undefined ? task.subject : patch.subject.trim();
  if (!nextSubject) return refuse("invalid-content", "Task subject must not be empty.");
  let nextDependencies = task.dependsOn;
  if (patch.dependsOn !== undefined) {
    const requested = [...new Set(patch.dependsOn)];
    if (requested.length > MAX_TASK_DEPENDENCIES) {
      return refuse("resource-limit", `Task depends on more than ${MAX_TASK_DEPENDENCIES} tasks.`, taskId);
    }
    const unknown = requested.find(id => !tasks[id]);
    if (unknown) return refuse("unknown-task", `Task references unknown task "${unknown}".`, unknown);
    if (requested.includes(taskId)) return refuse("invalid-dependency", "A task cannot depend on itself.", taskId);
    const canonical = canonicalDependencies(requested, tasks);
    if (!canonical) return refuse("invalid-dependency", "Task dependency chain is invalid or cyclic.", taskId);
    if (canonical.includes(taskId)) return refuse("invalid-dependency", "A task cannot depend on itself.", taskId);
    const graph = new Map(Object.values(tasks).map(existing => [
      existing.id, existing.id === taskId ? canonical : existing.dependsOn,
    ]));
    if (hasDependencyCycle(graph)) return refuse("invalid-dependency", "The edit would create a dependency cycle.", taskId);
    if ((task.status === "in_progress" || task.status === "completed")
      && canonical.some(id => tasks[id]?.status !== "completed")) {
      return refuse("unmet-dependencies", "Finish the prerequisites before this edit, or reopen a completed task first.", taskId);
    }
    nextDependencies = canonical;
  }
  // Read, not trusted: a caller that reached the store directly gets the same
  // answer a model does. A top-level check was not enough — a misspelled field
  // inside a handoff was dropped and the caller told its brief was recorded.
  const read = patch.context === undefined ? undefined : normalizeTaskContext(patch.context);
  if (read && !read.ok) return refuse("context-unreadable", `Task "${taskId}" ${read.error}`, taskId);
  if (read?.ok && !contextCarriesValue(read.value)) {
    return refuse("context-empty", `Task "${taskId}" context carries no value to record; nothing was written.`, taskId);
  }
  const nextResources = patch.resources === undefined ? task.resources : normalizeResources(patch.resources);
  if (nextResources.length > MAX_TASK_RESOURCES) {
    return refuse("resource-limit", `Task "${taskId}" declares more than ${MAX_TASK_RESOURCES} resources.`, taskId);
  }
  const nextDescription = patch.description !== undefined ? patch.description.trim() || undefined : task.description;
  const nextVerify = patch.verify !== undefined ? patch.verify.trim() || undefined : task.verify;
  // Folded rather than replaced: recording a workspace path must not erase a
  // handoff, and a successor supplying only its own delta must not drop the
  // findings the outgoing attempt recorded.
  const nextContext = patch.context === undefined ? task.context : mergeTaskContext(task.context, read!.value);
  if (!withinContextBudget({ ...task, subject: nextSubject, description: nextDescription, verify: nextVerify, resources: nextResources, context: nextContext })) {
    return refuse("budget-exceeded", `Task "${taskId}" content exceeds its byte budget.`, taskId);
  }
  if (patch.subject !== undefined) task.subject = nextSubject;
  if (patch.description !== undefined) task.description = nextDescription;
  if (patch.dependsOn !== undefined) task.dependsOn = nextDependencies;
  if (patch.verify !== undefined) task.verify = nextVerify;
  if (patch.resources !== undefined) task.resources = nextResources;
  if (patch.context !== undefined) task.context = nextContext;
  task.updatedAt = Date.now();
  markChanged();
  return { ok: true, task };
}

/**
 * What the task store checks about a completion, and what it refuses without.
 *
 * Every check here is a fact the tasks already holds. None of them runs
 * anything: a declared gate is a prompt, and a task set that evaluates a prompt is a
 * tasks that runs agents. What the task store can do is refuse a completion its own
 * record does not support — a task marked done whose dependency is not done, that
 * nobody ever worked on, that carries no evidence, or whose declared gate was
 * never answered.
 *
 * Off unless a caller asks, because a coordinator that already verifies a
 * submission by other means would otherwise be refused for work it has already
 * checked. A caller that wants the guarantees asks for them by name.
 */
export interface CompletionChecks {
  /** Every declared dependency must be completed. */
  requireDependenciesCompleted?: boolean;
  /** A success must record a result. */
  requireEvidence?: boolean;
  /** Only the holder, or a holder demonstrably gone, may deliver: a task nobody
   *  ever took has no attempt to accept. */
  requirePriorHold?: boolean;
  /** A declared gate must be answered with a verdict. */
  requireGateVerdict?: boolean;
}

/** Every check, as one value. What the model-facing tool asks for. */
export const ALL_COMPLETION_CHECKS: CompletionChecks = {
  requireDependenciesCompleted: true,
  requireEvidence: true,
  requirePriorHold: true,
  requireGateVerdict: true,
};

/** What a caller may say about a completion beyond the outcome. */
export interface CompletionOptions {
  checks?: CompletionChecks;
  /** The answer to the task's declared gate, when it has one. */
  verdict?: CompletionVerdict;
  /** The evidence this completion would record.
   *
   *  Carried rather than read off the task because the check runs *before* the
   *  evidence is written: a caller reading the task at that point sees the
   *  absence and would refuse every completion that supplies exactly what the
   *  rule asks for. */
  result?: string;
}

/** Why a completion was refused, by which check. Named so a caller can tell a
 *  missing verdict from a missing dependency, and a test can pin one rule
 *  without the other three. */
export type CompletionRefusal =
  | "unfinished-dependency"
  | "no-evidence"
  | "never-taken"
  | "ungated-verdict"
  | "gate-failed";

/**
 * Check a completion against the task set's own facts.
 *
 * Exported because a caller coordinating a submission runs this before it
 * decides to record one, and a refusal it can name is more useful than a
 * completion it has to walk back.
 */
export function checkCompletion(
  task: Task,
  outcome: "success" | "failed",
  options: CompletionOptions = {},
): CompletionRefusal | undefined {
  const checks = options.checks;
  if (!checks) return undefined;
  if (checks.requireDependenciesCompleted) {
    const unfinished = task.dependsOn.find((id) => tasks[id]?.status !== "completed");
    if (unfinished) return "unfinished-dependency";
  }
  if (checks.requirePriorHold) {
    // A holder that reported a failure is on the record as a recovery hold, and
    // that is what makes an unheld task accept-able. Never taken is not the same
    // thing, and conflating them is how a task set ends up accepting work that was
    // never attempted.
    if (task.claimedBy === undefined && task.status !== "recovery_hold") return "never-taken";
  }
  if (outcome !== "success") return undefined;
  const evidence = options.result !== undefined ? options.result : task.result;
  if (checks.requireEvidence && !evidence?.trim()) return "no-evidence";
  if (checks.requireGateVerdict) {
    if (task.verify?.trim() && options.verdict === undefined) return "ungated-verdict";
    if (options.verdict === "fail") return "gate-failed";
  }
  return undefined;
}

/** Why a completion was refused, in text a caller can act on. Every one names
 *  the task and what would satisfy it. */
export function completionRefusalReason(
  taskId: string,
  refusal: CompletionRefusal,
  detail?: { dependency?: string; verify?: string },
): string {
  switch (refusal) {
    case "unfinished-dependency":
      return `Task "${taskId}" depends on "${detail?.dependency}", which is not completed. Complete it, or record the dependency as the work it is.`;
    case "no-evidence":
      return `Task "${taskId}" cannot be completed with no result recorded. A success is a judgement against the task's requirements, so it carries the evidence for that judgement.`;
    case "never-taken":
      return `Task "${taskId}" was never taken, so there is no attempt to accept. Take it, or record a failure first if the work could not be started.`;
    case "ungated-verdict":
      return `Task "${taskId}" declares a completion gate ("${detail?.verify ?? ""}"), so completing it needs a verdict for that gate: pass or fail.`;
    case "gate-failed":
      return `Task "${taskId}" declares a completion gate and its verdict was fail, so the task is not complete. Address the gate or supersede the task.`;
  }
}

/**
 * Deliver a task's outcome. `failed` returns it to pending under a recovery hold
 * with the blocker retained as evidence.
 *
 * The holder check is the whole point. When somebody else holds the task the
 * call is refused, so a stale attempt, a different participant, or the main
 * session cannot report a result for work it is not doing. With no live holder
 * any participant may close the task, which is the fallback path when a holder
 * left mid-task — a state the task store can tell apart from work nobody started,
 * because a holder that died leaves a recovery hold behind. The check applies only
 * while the task is actually held (`status === "in_progress"`): a pending task is
 * unheld whatever `claimedBy` still records, so a restored pending task naming a
 * departed holder takes the fallback path, exactly as `takeTask` accepts it.
 *
 * `options.checks` adds the task set's own facts to that: see `checkCompletion`.
 */
export function completeTaskWithOutcome(
  taskId: string,
  holder: string,
  outcome: "success" | "failed",
  result?: string,
  options: CompletionOptions = {},
): { ok: true; task: Task } | TaskRefusalResult {
  const task = tasks[taskId];
  if (!task) return refuse("unknown-task", `Task "${taskId}" does not exist.`, taskId);
  if (outcome !== "success" && outcome !== "failed") {
    return refuse("invalid-outcome", `Task "${taskId}" has invalid submission outcome`, taskId);
  }
  // Two statuses are refused before the holder check, because neither is
  // completable and the holder check cannot see the difference: a completed task
  // is already terminal, and a superseded one has been replaced — completing it
  // would leave the tasks claiming both the original and its replacement are
  // done, which is the one outcome a supersession exists to prevent.
  if (task.status === "completed") {
    return refuse("already-completed", `Task "${taskId}" is already completed.`, taskId);
  }
  if (task.status === "superseded") {
    return refuse("superseded", `Task "${taskId}" was superseded by "${task.supersededBy ?? "a replacement"}"; deliver the outcome against the replacement.`, taskId);
  }
  if (task.status === "in_progress" && task.claimedBy && task.claimedBy !== holder) {
    return refuse("held-by-other", `Task "${taskId}" is in progress by @${task.claimedBy}; only its holder may deliver the outcome.`, task.claimedBy);
  }
  // Checked before anything is written, so a refusal leaves no partial state —
  // and with the evidence this call would record, so the rule reads what the
  // caller is offering rather than what the task happened to hold.
  const refusal = checkCompletion(task, outcome, { ...options, result });
  if (refusal) {
    const dependency = refusal === "unfinished-dependency"
      ? task.dependsOn.find((id) => tasks[id]?.status !== "completed")
      : undefined;
    return refuse(
      refusal,
      completionRefusalReason(taskId, refusal, {
        ...(dependency ? { dependency } : {}),
        ...(task.verify ? { verify: task.verify } : {}),
      }),
      dependency,
    );
  }
  const previous = task.claimedBy;
  // Retained evidence round-trips byte-for-byte. Trimming decides only whether
  // there is evidence at all, so a whitespace-only result records nothing while a
  // real one keeps whatever the caller supplied, trailing newline included.
  task.result = result?.trim() ? result : undefined;
  if (outcome === "failed") {
    // A failed attempt answered no gate, so both gate fields go with it: a
    // verdict and gate left by an earlier attempt would read as this attempt's
    // answer to every later reader.
    task.completionVerdict = undefined;
    task.completionGate = undefined;
    task.status = "recovery_hold";
    task.claimedBy = undefined;
    task.completedAt = undefined;
  } else {
    if (options.verdict) task.completionVerdict = options.verdict;
    if (task.verify?.trim()) task.completionGate = task.verify;
    task.status = "completed";
    task.claimedBy = undefined;
    task.completedAt = Date.now();
  }
  task.updatedAt = Date.now();
  markChanged();
  if (previous) hooks.sync(previous, undefined, undefined);
  return { ok: true, task };
}

/**
 * Return a completed task to pending.
 *
 * Refused while a dependent is being held, naming it, because reopening a task
 * its successor is already building against would silently invalidate that
 * successor's premise.
 */
export function reopenTask(
  taskId: string,
): { ok: true; task: Task; invalidated: Task[] } | TaskRefusalResult {
  const task = tasks[taskId];
  if (!task) return refuse("unknown-task", `Task "${taskId}" does not exist.`, taskId);
  if (task.status !== "completed") {
    return refuse("not-completed", `Task "${taskId}" is not completed.`, taskId);
  }
  // Reopen is always available. It is the only way back from a completed task, so
  // refusing it would strand the work for everyone who ever depended on it — and
  // refusing it only while somebody happened to be working on a dependent would
  // make the answer depend on timing rather than on the task.
  //
  // So the premise moves and everything standing on it moves with it. A dependent
  // that is completed had a conclusion withdrawn; one that is being worked on had
  // an attempt invalidated. Both go back to pending under a recovery hold naming
  // what withdrew them, and both keep their evidence: it is what the next attempt
  // has to answer.
  const invalidated = [...completedDependents(taskId), ...claimedDependents(taskId)]
    .filter((dependent, index, all) => all.findIndex((entry) => entry.id === dependent.id) === index);
  task.status = "pending";
  task.claimedBy = undefined;
  task.result = undefined;
  task.completedAt = undefined;
  task.updatedAt = Date.now();
  for (const dependent of invalidated) {
    const wasHeld = dependent.claimedBy;
    dependent.status = "recovery_hold";
    dependent.claimedBy = undefined;
    dependent.completedAt = undefined;
    dependent.invalidatedBy = taskId;
    dependent.recoveryNote = `Its premise "${taskId}" was reopened, so this ${wasHeld ? "attempt" : "completion"} no longer stands against it.`;
    // The verdict described work whose premise is gone. It is withdrawn rather
    // than left standing, because a `pass` on a task that is no longer complete
    // is the one reading this task set cannot afford.
    dependent.completionVerdict = undefined;
    dependent.completionGate = undefined;
    // The evidence stays: it is what the next attempt has to answer, and what a
    // reviewer reads before deciding whether the work still holds.
    dependent.updatedAt = Date.now();
    // The lease goes with the hold. Left open, the resources stay locked by a
    // participant who is no longer working on anything.
    if (wasHeld) hooks.sync(wasHeld, undefined, undefined);
  }
  markChanged();
  return { ok: true, task, invalidated };
}

// ── Runtime-driven transitions ─────────────────────────────────────────────
//
// Not a work-lifecycle surface and nothing in the tool reaches these. They exist
// because a task reaches `in_progress` through several steps, and any of them
// can fail after the take, or because a holder left without delivering. Each is
// named for what happened rather than offering one verb that could take any task
// from anybody, which is the same reason the tool surface has no `release`.

/**
 * Undo a take whose attempt never began.
 *
 * This is a *revert*, not a failure report, and that is why it differs from a
 * recorded failure in exactly one way: it sets no recovery hold. A hold would be
 * wrong here. The hold exists so a failure nobody looked at is not silently
 * retried by whichever participant is idle; an attempt that never began has no
 * failure to look at, and holding it would park the task until somebody explained
 * a start that never happened.
 */
export function revertUndeliveredTake(taskId: string, holder: string, reason: string): Task | undefined {
  const task = tasks[taskId];
  if (!task || task.status !== "in_progress" || task.claimedBy !== holder) return undefined;
  task.status = "pending";
  task.claimedBy = undefined;
  task.result = reason;
  task.updatedAt = Date.now();
  markChanged();
  hooks.sync(holder, undefined, undefined);
  return task;
}

/**
 * A holder releasing its resources while the task stays superseded.
 *
 * Distinct from a failure report because the task's *status* is not the holder's
 * to change: it was replaced, and the replacement stands. What the holder owns is
 * its resource lease, and acknowledging the cancellation gives that back.
 */
export function acknowledgeSupersession(taskId: string, holder: string, reason: string): Task | undefined {
  const task = tasks[taskId];
  if (!task || task.status !== "superseded" || task.claimedBy !== holder) return undefined;
  task.claimedBy = undefined;
  task.result = reason;
  task.updatedAt = Date.now();
  markChanged();
  hooks.sync(holder, undefined, undefined);
  return task;
}

/**
 * Record a failure for every task a holder was working on.
 *
 * A failure rather than a revert, because the attempt did run: a participant that
 * stopped or crashed may have changed anything, and the hold is what stops the
 * wreckage from being silently picked up by the next idle participant.
 */
export function failTasksHeldBy(holder: string, reason: string): Task[] {
  const released: Task[] = [];
  for (const task of listTasks()) {
    if (task.status === "in_progress" && task.claimedBy === holder) {
      completeTaskWithOutcome(task.id, holder, "failed", reason);
      released.push(task);
    } else if (task.status === "superseded" && task.claimedBy === holder) {
      // A superseded task stays superseded; only the lease comes back.
      const acknowledged = acknowledgeSupersession(task.id, holder, reason);
      if (acknowledged) released.push(acknowledged);
    }
  }
  return released;
}

/**
 * Bind a task to a participant the caller has already decided on, under a lease
 * the caller minted.
 *
 * The counterpart to `takeTask`, not a replacement for it: a participant taking
 * its own work is subject to the recovery hold, while this path is the authority
 * that clears one. It therefore says which prior statuses it may take from, and
 * may be told to bind a participant that still holds an earlier lease — the case
 * where the previous holder is gone and its lease has not been given back.
 */
export function bindTask(
  taskId: string,
  holder: string,
  lease: WorkAssignment,
  options: { from?: TaskStatus[]; allowHeldLease?: boolean } = {},
): { ok: true; task: Task } | TaskRefusalResult {
  const task = tasks[taskId];
  const from = options.from ?? ["pending"];
  if (!task) return refuse("unknown-task", `Task "${taskId}" does not exist.`, taskId);
  if (!from.includes(task.status)) {
    return refuse("bind-not-allowed", `Task "${taskId}" is ${task.status}; it cannot be bound from that state.`, taskId);
  }
  const participant = hooks.get(holder);
  // Every refusal names the work by its subject, not by its id. An id a caller
  // has to look up is the one thing a caller in the middle of a dispatch cannot
  // do, and a creation that rolled back leaves no record to look up at all.
  const named = `Task "${task.subject}"`;
  if (!participant) return refuse("participant-unavailable", `Cannot bind ${named} to @${holder}: it is not a current participant.`, holder);
  if (participant.currentTaskId !== undefined && task.status === "superseded") {
    return refuse("bind-not-allowed", `Cannot bind ${named} to @${holder}: it still holds superseded work and must acknowledge that first.`, holder);
  }
  if (!options.allowHeldLease && participant.assignment && !participant.assignment.closed) {
    return refuse("lease-held", `Cannot bind ${named} to @${holder}: it already holds an open lease on "${participant.assignment.id}".`, participant.assignment.id);
  }
  const conflict = hooks.conflicting(task.resources, holder);
  if (conflict) {
    return refuse("resource-conflict", `Cannot bind ${named} to @${holder}: its resources conflict with @${conflict.name}'s active work.`, conflict.name);
  }
  return recordTake(task, holder, { assignment: lease });
}

/**
 * Remove a task no attempt ever began.
 *
 * The one deletion the task store offers, and refused unless the task is either
 * unheld or held by the named participant who never started it. A task carrying
 * a result, a dependency, or a completed attempt is real work, and real work is
 * returned to pending rather than erased.
 */
export function discardTask(taskId: string, holder: string): boolean {
  const task = tasks[taskId];
  if (!task) return false;
  if (task.status === "pending" && task.claimedBy === undefined && task.result === undefined) {
    delete tasks[taskId];
    markChanged();
    return true;
  }
  if (task.status !== "in_progress" || task.claimedBy !== holder || task.result !== undefined) return false;
  delete tasks[taskId];
  markChanged();
  hooks.sync(holder, undefined, undefined);
  return true;
}

/** The one write that moves a task into `in_progress`, shared by every path
 *  that does it: a self-serve take and a caller-decided bind. Two writers of the
 *  same transition is how the two drift apart on what a take requires. */
function recordTake(
  task: Task,
  holder: string,
  options: { recoveryNote?: string; assignment?: WorkAssignment } = {},
): { ok: true; task: Task } {
  task.status = "in_progress";
  task.claimedBy = holder;
  if (options.recoveryNote) task.recoveryNote = options.recoveryNote;
  task.updatedAt = Date.now();
  markChanged();
  hooks.sync(holder, options.assignment ?? { id: `task:${randomUUID()}`, kind: "task", resources: task.resources }, task.id);
  return { ok: true, task };
}

// ── Marker-file intents ─────────────────────────────────────────────────────
//
// A participant never writes the tasks file; it expresses intent through an
// exclusive-create marker so exactly one racer wins a contested claim. Applying
// one is a task set transition like any other — the preconditions are the same ones
// `takeTask` enforces, which is why they are checked here once and then reuse the
// single take rather than a second one that could drift.

/** Apply a validated claim intent from a marker file.
 *
 *  `applied` rather than `ok`: the domain word here is "did the marker take
 *  effect", and the refusal it carries is the same one every other refusal in
 *  this store carries. */
export function applyClaimIntent(intent: TaskIntent): TaskClaimOutcome {
  const task = tasks[intent.taskId];
  if (!task) return refuseClaim("unknown-task", `unknown task "${intent.taskId}"`, intent.taskId);
  if (!hooks.current(intent.participant, intent.spawnId)) {
    return refuseClaim("participant-unavailable", `"${intent.participant}" is not a living current participant`, intent.participant);
  }
  const participant = hooks.get(intent.participant);
  if (participant?.assignment) {
    const state = participant.assignment.closed ? "closed, pending a reopen" : "open";
    return refuseClaim("lease-held", `"${intent.participant}" already holds a ${state} lease on "${participant.assignment.id}"`, participant.assignment.id);
  }
  // A hold is refused outright rather than cleared: a marker carries no reason,
  // and a participant that failed its last attempt needs a deliberate statement
  // of what changed before its work is offered again.
  if (task.status === "recovery_hold") {
    return refuseClaim("recovery-hold-needs-reason", `task "${intent.taskId}" requires a deliberate assignment after a failed attempt`, intent.taskId);
  }
  const taken = takeTask(intent.taskId, intent.participant);
  return taken.ok
    ? { applied: true }
    : refuseClaim(taken.refusal, taken.reason, taken.detail);
}

/** Apply a validated submission intent; verify gating happens in the caller. */
export function applySubmissionIntent(
  intent: TaskIntent,
  options: CompletionOptions = {},
): TaskSubmissionOutcome {
  if (intent.status !== "completed" && intent.status !== "failed") {
    return refuse("invalid-outcome", `task "${intent.taskId}" has invalid submission status`, intent.taskId);
  }
  if (!hooks.current(intent.participant, intent.spawnId)) {
    return refuse("participant-unavailable", `"${intent.participant}" is not a living current participant`, intent.participant);
  }
  const task = tasks[intent.taskId];
  if (!task) return refuse("unknown-task", `unknown task "${intent.taskId}"`, intent.taskId);
  if (task.status !== "in_progress" && task.status !== "superseded") {
    return refuse("not-in-progress", `task "${intent.taskId}" is not in progress`, intent.taskId);
  }
  if (task.claimedBy !== intent.participant) {
    return refuse("held-by-other", `task "${intent.taskId}" is held by @${task.claimedBy ?? "someone else"}`, task.claimedBy);
  }
  if (task.status === "superseded" && intent.status !== "failed") {
    return refuse("superseded", `task "${intent.taskId}" was superseded by "${task.supersededBy ?? "a replacement"}"; a submission must acknowledge cancellation instead`, intent.taskId);
  }
  if (intent.status === "failed") {
    // A superseded task stays superseded: its replacement stands, and only the
    // holder's lease comes back. Anything else is a recorded failure, which
    // returns the task to pending under a recovery hold.
    if (task.status === "superseded") {
      const acknowledged = acknowledgeSupersession(intent.taskId, intent.participant, intent.result?.trim() || "Cancellation acknowledged.");
      return acknowledged ? { ok: true } : refuse("superseded", `could not acknowledge cancellation of task "${intent.taskId}"`, intent.taskId);
    }
    return completeTaskWithOutcome(intent.taskId, intent.participant, "failed", intent.result?.trim() || "Attempt reported failure.");
  }
  // The marker path is a second way into the same completion, so it carries the
  // same checks and the same verdict. A participant that could skip them by
  // writing a file instead of calling a tool would make every rule in
  // `CompletionChecks` advisory.
  const completed = completeTaskWithOutcome(
    intent.taskId,
    intent.participant,
    "success",
    intent.result?.trim() || undefined,
    { ...options, ...(intent.verdict ? { verdict: intent.verdict } : {}) },
  );
  // The refusal has to survive the crossing. `completeTaskWithOutcome` returns
  // the store's one refusal shape, and handing that object straight back is what
  // keeps the code, the detail, and the only sentence that says why.
  return completed.ok ? { ok: true } : refuse(completed.refusal, completed.reason, completed.detail);
}

/** Re-exported so a caller narrowing the registry does not repeat the import. */
export type { Participant, ParticipantAssignment, ParticipantRegistry };
