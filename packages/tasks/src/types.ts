/**
 * The Task data model.
 *
 * `TaskStatus` is a plain union rather than a TypeBox schema: the previous
 * TypeBox construction existed only to be converted straight back into a type
 * with `Static<>`, and no tool parameter ever used the runtime value. Dropping
 * it keeps this package free of a typebox peer.
 *
 * Nothing here imports coordination state. A Task is durable data with a
 * lifecycle; who executes it, and how they are reached, belongs to the packages
 * that own processes and messaging.
 */

/** Tasks lifecycle of a Task, in the order the tasks moves through it.
 *
 *  `recovery_hold` sits beside `in_progress` rather than under `pending`,
 *  because it is a state of its own: the work was attempted and the attempt did
 *  not stand. `pending` now means never attempted, and only that. Taking from
 *  `recovery_hold` needs a stated reason.
 *
 *  The runtime list, not a bare union, so the two cannot drift: `loadTasks`
 *  validates a restored status against it, the tool declares it in a schema, and
 *  a status added here reaches all three. A `TaskStatus` written out as a union
 *  of literals instead would erase at runtime and leave each of those places
 *  holding its own private copy. */
export const TASK_STATUSES = ["pending", "in_progress", "recovery_hold", "completed", "superseded"] as const;

/** Tasks lifecycle of a Task. The set is closed: every transition a caller may
 *  name lives here, so an unsupported value is a compile error rather than a
 *  silent no-op. `in_progress` replaces the older `claimed` because "in_progress"
 *  described an authority a caller had to be granted, and a Task has no declared
 *  owner — moving a Task into progress *is* taking it. */
export type TaskStatus = (typeof TASK_STATUSES)[number];

/** The answer a task's declared completion gate was given. `pass` and `fail` are
 *  the two answers a gate can have; a gate that produced nothing has not answered,
 *  and an unanswered gate is the one state that never completes a task. */
export type CompletionVerdict = "pass" | "fail";

/** Whether a value is a status this task set knows. */
export function isTaskStatus(value: unknown): value is TaskStatus {
  return typeof value === "string" && (TASK_STATUSES as readonly string[]).includes(value);
}

/** Whether an id was minted by the runtime rather than derived from a subject.
 *
 *  A task id is a slug of its subject, so an id of this shape was never derived:
 *  earlier builds reserved the `work:<UUID>` namespace for a record created when
 *  the user entered work directly, and files written by those builds still carry
 *  those ids. Named here beside the persisted-file version rather than spelled
 *  inline in the restore path, because it is file-format history and not a rule
 *  about tasks. */
export function isGeneratedRecordId(id: string): boolean {
  return /^work:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
}

/** The classification a restored record carries, and the reason the order matters.
 *
 *  Explicit metadata wins, because a caller that recorded what a record is knows
 *  more about it than its id does. A value that is present but is not one this
 *  set defines is repaired to `task` and never inferred, including a `null`: the
 *  record is real work whose classification was lost, and inferring from the id
 *  would call user work execution history on the strength of a spelling. Only an
 *  absent value is inferred, and only from the reserved generated-id namespace. */
export function resolveRecordKind(recordKind: unknown, id: string): "task" | "execution" {
  if (recordKind === undefined) return isGeneratedRecordId(id) ? "execution" : "task";
  return recordKind === "execution" ? "execution" : "task";
}

/** One Task on the shared tasks. A Task records what must be done and under
 *  which completion requirements; it never records who must do it. `claimedBy`
 *  is written only by the runtime, from the identity of whoever took the Task,
 *  so it can never be set or spoofed by a caller. */
export interface Task {
  /** Internal execution history is readable but is not a user task reminder. */
  recordKind?: "task" | "execution";
  id: string;
  subject: string;
  description?: string;
  /** Task ids that must complete before this Task may be taken. */
  dependsOn: string[];
  /** Completion gate: a review prompt a fresh one-shot reviewer answers with
   *  VERDICT: PASS or FAIL; overrides the participant-role default. */
  verify?: string;
  /** Mutating work must use stable resource tags such as `firmware/sub-node`.
   *  A resource conflicts with itself and any slash-prefixed descendant. */
  resources: string[];
  status: TaskStatus;
  /** The participant that took this Task, recorded by the runtime from the
   *  caller's own context. There is no parameter through which a caller could
   *  name somebody else. */
  claimedBy?: string;
  /** The participant that recorded this Task, written by the runtime from the
   *  caller's own context. A creator may deliver the outcome of work it did
   *  itself without a separate take, so the accountable party is recoverable
   *  from the record instead of demanding a call that records nothing new. */
  createdBy?: string;
  /** Replacement Work that made this Work obsolete. */
  supersededBy?: string;
  /** The evidence recorded for the current or last attempt. Retained verbatim:
   *  trimming decides only whether there is evidence at all, so a real result
   *  keeps whatever the caller supplied. */
  result?: string;
  /** The answer to this task's declared completion gate, for the *current*
   *  attempt. `undefined` means the task declared no gate, or a recorded answer
   *  was withdrawn because the premise under it was reopened — never that a gate
   *  passed. A completed task always holds the verdict it was completed with. */
  completionVerdict?: CompletionVerdict;
  /** The gate this verdict answered, copied at completion so a later reader can
   *  see which acceptance criteria were actually applied. */
  completionGate?: string;
  /** The task whose reopening withdrew the premise this task's completion was
   *  drawn on. Set on a task that was completed and is back in pending, which is
   *  what separates a withdrawn conclusion from one never reached. */
  invalidatedBy?: string;
  /** Why a recovery hold was cleared, kept so an operator can see what was
   *  done about the failure rather than only that it was dismissed. */
  recoveryNote?: string;
  /** Per-Task context: the workspace path it ran in, a structured successor
   *  brief, what it builds on, and its byte budget. See `./context.ts`. */
  context?: import("./context.ts").TaskContext;
  createdAt: number;
  updatedAt: number;
  completedAt?: number;
}

/** A claim or submission intent expressed by a participant through a marker file.
 *  A participant never writes the tasks file itself. `status` applies to
 *  submissions. */
export interface TaskIntent {
  taskId: string;
  /** The participant that published the intent. */
  participant: string;
  /** The publishing incarnation. A retired incarnation's intent is refused, so a
   *  replaced participant cannot take or deliver Task it no longer holds. */
  spawnId: string;
  /** The assignment this intent was published under, when it published one. */
  assignmentId?: string;
  status?: "completed" | "failed";
  result?: string;
  /** The answer to the task's declared completion gate, when the participant has
   *  one. Carried here so the marker path is subject to the same gate check as a
   *  direct call rather than being a way around it. */
  verdict?: CompletionVerdict;
  timestamp: number;
}

/** Version of the persisted tasks file. The value is inherited from the
 *  pre-split `TEAM_RUNTIME_VERSION` so task sets written before the extraction still
 *  load; an incompatible version is rejected rather than silently migrated. */
export const TASKS_FILE_VERSION = 2;
