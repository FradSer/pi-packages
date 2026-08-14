import type { Static } from "typebox";
import { Type } from "typebox";

export const EmptyParams = Type.Object({}, { description: "No parameters required" });

// ── Agent / Teammate ─────────────────────────────────────────────

export const TeammateRole = Type.Union(
  [
    Type.Literal("worker"),
    Type.Literal("reviewer"),
    Type.Literal("specialist"),
    Type.Literal("observer"),
  ],
  { description: "Role of the teammate" },
);
export type TeammateRole = Static<typeof TeammateRole>;

export interface Teammate {
  name: string;
  role: TeammateRole;
  description: string;
  /** Reusable worker prompt: role, method, boundaries, and completion criteria. */
  prompt: string;
  model?: string;
  tools?: string[];
  /** Liveness: idle (registered, no active process) or running (worker spawned). */
  status: "idle" | "running";
  /** Task ID currently being executed by this teammate's spawned worker. */
  currentTaskId?: string;
  /** Per-spawn identity that prevents old worker events affecting a later run. */
  currentRunId?: string;
  /** Last time the teammate transitioned idle/running (milliseconds). */
  lastActiveAt?: number;
  registeredAt: number;
}

// ── Mailbox ───────────────────────────────────────────────────────

export interface MailboxMessage {
  id: string;
  from: string;
  to: string;
  subject: string;
  body: string;
  taskId?: string;
  timestamp: number;
  read: boolean;
}

/** Append-only event emitted by a worker and applied by the team leader. */
export interface WorkerMessageEvent {
  id: string;
  type: "message";
  worker: string;
  runId: string;
  to: string;
  subject: string;
  body: string;
  taskId?: string;
}

export interface WorkerMessageReadEvent {
  id: string;
  type: "message_read";
  worker: string;
  runId: string;
  messageId: string;
}

export interface WorkerTaskUpdateEvent {
  id: string;
  type: "task_update";
  worker: string;
  runId: string;
  taskId: string;
  status: "in_progress" | "completed" | "failed";
  result?: string;
  errorMessage?: string;
}

export type WorkerEvent = WorkerMessageEvent | WorkerMessageReadEvent | WorkerTaskUpdateEvent;

// ── Task ──────────────────────────────────────────────────────────

export const TaskStatus = Type.Union(
  [
    Type.Literal("assigned"),
    Type.Literal("in_progress"),
    Type.Literal("completed"),
    Type.Literal("failed"),
    Type.Literal("cancelled"),
  ],
  { description: "Current status of the task" },
);
export type TaskStatus = Static<typeof TaskStatus>;

export interface Task {
  id: string;
  title: string;
  description: string;
  /** Repository-relative paths used to coordinate this task. */
  paths: string[];
  /** Read tasks may overlap; write tasks need shared-workspace conflict protection. */
  access: "read" | "write";
  assignee: string;
  assignedBy: string;
  status: TaskStatus;
  result?: string;
  errorMessage?: string;
  /** Task IDs this task blocks (they cannot start until this one completes). */
  blocks: string[];
  /** Downstream task IDs already notified after process-confirmed completion. */
  unblockedNotificationTaskIds?: string[];
  /** Task IDs that block this task (all must be completed before it can start). */
  blockedBy: string[];
  /** Real child-process execution info when this task was spawned to a worker. */
  spawn?: SpawnInfo;
  createdAt: number;
  updatedAt: number;
  completedAt?: number;
}

// ── Spawn ────────────────────────────────────────────────────────

/** Lifecycle of a spawned child Pi process running a task. */
export type SpawnStatus = "running" | "completed" | "failed";

/** Token/cost usage reported by a finished worker (from JSON-mode output). */
export interface WorkerUsage {
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
  totalTokens: number;
  cost: number;
}

export interface SpawnInfo {
  /** Per-spawn capability identity, regenerated for every worker process. */
  runId: string;
  pid: number;
  status: SpawnStatus;
  startedAt: number;
  finishedAt?: number;
  exitCode?: number;
  /** Truncated stdout of the child process. */
  stdout?: string;
  /** Truncated stderr of the child process. */
  stderr?: string;
  /** Spawn-level error (e.g. CLI resolution failure). */
  error?: string;
  /** Token/cost usage reported by the worker, when available. */
  usage?: WorkerUsage;
  /** True when the worker was killed by the spawn timeout. */
  timedOut?: boolean;
  /** Whether this run owns a dedicated Git worktree. */
  isolation?: "worktree" | "none";
}

// ── Tool parameter schemas (typebox) ──────────────────────────────

export const TeammateRegisterParams = Type.Object({
  name: Type.String({ description: "Unique name for this teammate" }),
  role: TeammateRole,
  description: Type.String({ description: "Short responsibility summary" }),
  prompt: Type.String({
    minLength: 1,
    description: "Reusable role prompt: goal, context, procedure, deliverable, boundaries, and completion criteria",
  }),
  model: Type.Optional(Type.String({ description: "Preferred model for this agent" })),
  tools: Type.Optional(Type.Array(Type.String(), { description: "Allowed tools" })),
});

/** Send a direct message. Leaders may address a teammate; workers may address
 * a teammate or `agent` (the main session). */
export const TeammateMessageParams = Type.Object({
  to: Type.String({ description: "Recipient teammate name, or agent when called by a worker" }),
  subject: Type.String({ description: "Concise message subject" }),
  body: Type.String({ description: "Message body" }),
  taskId: Type.Optional(Type.String({ description: "Optional associated task ID (leader only)" })),
  role: Type.Optional(Type.String({ description: "Leader-only role filter when to is all" })),
});

/** Read the caller's inbox. Workers may also acknowledge a consumed message. */
export const TeammateInboxParams = Type.Object({
  unreadOnly: Type.Optional(Type.Boolean({ description: "Only return unread messages. Default: true.", default: true })),
  markRead: Type.Optional(Type.Boolean({ description: "Mark returned messages read. Default: true.", default: true })),
});

/** Worker-only: report progress or a final outcome for the bound task run. */
export const TeammateReportParams = Type.Object({
  status: Type.Union([Type.Literal("in_progress"), Type.Literal("completed"), Type.Literal("failed")]),
  result: Type.Optional(Type.String({ description: "Final result when completed" })),
  errorMessage: Type.Optional(Type.String({ description: "Failure detail when failed" })),
});

export const TeammateConfigureParams = Type.Object({
  name: Type.String({ description: "Teammate name to configure" }),
  description: Type.Optional(Type.String({ description: "Updated responsibility summary" })),
  prompt: Type.Optional(Type.String({ description: "Updated role prompt" })),
  model: Type.Optional(Type.String({ description: "Updated model pattern" })),
  tools: Type.Optional(Type.Array(Type.String(), { description: "Updated allowed tools" })),
});

export const TeammateCreateTaskParams = Type.Object({
  assignee: Type.String({ description: "Teammate name to assign the task to" }),
  title: Type.String({ description: "Task title" }),
  description: Type.String({ description: "Detailed task description" }),
  paths: Type.Array(Type.String({ description: "Repository-relative path this task may inspect or modify" }), {
    minItems: 1,
    description: "Repository-relative paths used to coordinate this task",
  }),
  access: Type.Optional(Type.Union([Type.Literal("read"), Type.Literal("write")], {
    default: "write",
    description: "read permits overlapping analysis; write protects overlapping shared-workspace changes. Default: write.",
  })),
  blockedBy: Type.Optional(Type.Array(Type.String(), { description: "Task IDs that block this task" })),
});

export const TeammateStartTaskParams = Type.Object({
  taskId: Type.String({ description: "Task ID to start" }),
  retry: Type.Optional(
    Type.Boolean({ description: "Explicitly retry a failed task with the same idle teammate. Default: false.", default: false }),
  ),
  isolation: Type.Optional(
    Type.Union(
      [Type.Literal("worktree"), Type.Literal("none")],
      { description: "Run the worker in a fresh git worktree (default: none)" },
    ),
  ),
  timeoutMs: Type.Optional(
    Type.Integer({
      minimum: 1,
      description: "Hard wall-clock cap before the worker is killed (default: 1800000 = 30 min)",
    }),
  ),
});

export const TeammateCancelTaskParams = Type.Object({
  taskId: Type.String({ description: "Task ID to cancel" }),
});

export const TeammateRemoveParams = Type.Object({
  name: Type.String({ description: "Teammate name to unregister" }),
});

export const TeammateListTasksParams = Type.Object({
  status: Type.Optional(
    Type.Union(
      [
        Type.Literal("assigned"),
        Type.Literal("in_progress"),
        Type.Literal("completed"),
        Type.Literal("failed"),
        Type.Literal("cancelled"),
      ],
      { description: "Filter by status" },
    ),
  ),
  assignee: Type.Optional(Type.String({ description: "Filter by assignee name" })),
});

export const TeammateWaitParams = Type.Object({
  taskIds: Type.Array(Type.String(), {
    minItems: 1,
    description: "Task IDs of parallel workers to wait for",
  }),
  timeoutMs: Type.Optional(
    Type.Integer({
      minimum: 1,
      description: "Maximum time to wait in milliseconds (default: 300000 = 5 min)",
    }),
  ),
});

// ── State snapshot for persistence ────────────────────────────────

export interface TeammateState {
  teammates: Record<string, Teammate>;
  mailboxes: Record<string, MailboxMessage[]>;
  tasks: Record<string, Task>;
  messageCounter: number;
  taskCounter: number;
  /** Byte offsets consumed by the parent from each worker's append-only outbox. */
  workerEventOffsets: Record<string, number>;
  /** Event IDs already applied by the parent, keyed to their worker run for compaction. */
  workerEventIds: Record<string, string>;
}