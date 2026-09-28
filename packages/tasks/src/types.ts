/**
 * The Work Item data model.
 *
 * `TaskStatus` is a plain union rather than a TypeBox schema: the previous
 * TypeBox construction existed only to be converted straight back into a type
 * with `Static<>`, and no tool parameter ever used the runtime value. Dropping
 * it keeps this package free of a typebox peer.
 *
 * Nothing here imports coordination state. A Work Item is durable data with a
 * lifecycle; who executes it, and how they are reached, belongs to the packages
 * that own processes and messaging.
 */

/** Board lifecycle of a Task. The set is closed: every transition a caller may
 *  name lives here, so an unsupported value is a compile error rather than a
 *  silent no-op. `in_progress` replaces the older `claimed` because "in_progress"
 *  described an authority a caller had to be granted, and a Task has no declared
 *  owner — moving a Task into progress *is* taking it. */
export type TaskStatus = "pending" | "in_progress" | "completed" | "superseded";

/** One Task on the shared board. A Task records what must be done and under
 *  which completion requirements; it never records who must do it. `claimedBy`
 *  is written only by the runtime, from the identity of whoever took the Task,
 *  so it can never be set or spoofed by a caller. */
export interface BoardTask {
  id: string;
  subject: string;
  description?: string;
  /** Task ids that must complete before this Task may be taken. */
  dependsOn: string[];
  /** Completion gate: a review prompt a fresh one-shot reviewer answers with
   *  VERDICT: PASS or FAIL; overrides the agent-role default. */
  verify?: string;
  /** Mutating work must use stable resource tags such as `firmware/sub-node`.
   *  A resource conflicts with itself and any slash-prefixed descendant. */
  resources: string[];
  status: TaskStatus;
  /** The participant that took this Task, recorded by the runtime from the
   *  caller's own context. There is no parameter through which a caller could
   *  name somebody else. */
  claimedBy?: string;
  /** Replacement Work that made this Work obsolete. */
  supersededBy?: string;
  result?: string;
  /** Deferred mail archived when an accepted result closes its Work Item. */
  deferredMessages?: Array<{ from: string; subject: string; body: string; timestamp: number }>;
  errorMessage?: string;
  /** Failed or interrupted Work stays pending for inspection but cannot be
   * autonomously claimed until the leader deliberately authorizes recovery. */
  recoveryRequired?: boolean;
  /** Per-Work context: the workspace path it ran in, a structured successor
   *  brief, what it builds on, and its byte budget. See `./context.ts`. */
  context?: import("./context.ts").WorkContext;
  createdAt: number;
  updatedAt: number;
  completedAt?: number;
}

/** A claim or submission intent expressed by a worker through marker files.
 * Workers never write the board file itself. `status` applies to submissions. */
export interface TaskIntent {
  taskId: string;
  worker: string;
  spawnId: string;
  assignmentId?: string;
  status?: "completed" | "failed";
  result?: string;
  timestamp: number;
}

/** Version of the persisted board file. The value is inherited from the
 * pre-split `TEAM_RUNTIME_VERSION` so boards written before the extraction still
 * load; an incompatible version is rejected rather than silently migrated. */
export const WORK_RUNTIME_VERSION = 2;
