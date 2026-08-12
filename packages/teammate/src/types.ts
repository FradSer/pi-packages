import type { Static } from "typebox";
import { Type } from "typebox";

export const EmptyParams = Type.Object({}, { description: "No parameters required" });

// ── Agent / Teammate ─────────────────────────────────────────────

export const TeammateRole = Type.Union(
  [
    Type.Literal("team-leader"),
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
  model?: string;
  tools?: string[];
  /** Liveness: idle (registered, no active process) or running (worker spawned). */
  status: "idle" | "running";
  /** Task ID currently being executed by this teammate's spawned worker. */
  currentTaskId?: string;
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

// ── Task ──────────────────────────────────────────────────────────

export const TaskStatus = Type.Union(
  [
    Type.Literal("created"),
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
  assignee: string;
  assignedBy: string;
  status: TaskStatus;
  result?: string;
  errorMessage?: string;
  /** Task IDs this task blocks (they cannot start until this one completes). */
  blocks: string[];
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
}

// ── Tool parameter schemas (typebox) ──────────────────────────────

export const TeammateRegisterParams = Type.Object({
  name: Type.String({ description: "Unique name for this teammate" }),
  role: TeammateRole,
  description: Type.String({ description: "What this teammate is responsible for" }),
  model: Type.Optional(Type.String({ description: "Preferred model for this agent" })),
  tools: Type.Optional(Type.Array(Type.String(), { description: "Allowed tools" })),
});

export const TeammateSendParams = Type.Object({
  to: Type.String({ description: "Name of the recipient teammate" }),
  subject: Type.String({ description: "Message subject" }),
  body: Type.String({ description: "Message body content" }),
  taskId: Type.Optional(Type.String({ description: "Optional associated task ID" })),
});

export const TeammateReadMailboxParams = Type.Object({
  name: Type.Optional(
    Type.String({ description: "Teammate name to read mailbox for (default: the caller's context)" }),
  ),
  markRead: Type.Optional(Type.Boolean({ description: "Mark messages as read. Default: true.", default: true })),
  unreadOnly: Type.Optional(Type.Boolean({ description: "Only show unread messages. Default: true.", default: true })),
});

export const TeammateAssignTaskParams = Type.Object({
  assignee: Type.String({ description: "Teammate name to assign the task to" }),
  title: Type.String({ description: "Task title" }),
  description: Type.String({ description: "Detailed task description" }),
});

export const TeammateListTasksParams = Type.Object({
  status: Type.Optional(
    Type.Union(
      [
        Type.Literal("created"),
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

export const TeammateUpdateTaskParams = Type.Object({
  taskId: Type.String({ description: "ID of the task to update" }),
  status: Type.Union(
    [
      Type.Literal("in_progress"),
      Type.Literal("completed"),
      Type.Literal("failed"),
      Type.Literal("cancelled"),
    ],
    { description: "New status" },
  ),
  result: Type.Optional(Type.String({ description: "Result or output (for completed tasks)" })),
  errorMessage: Type.Optional(Type.String({ description: "Error message (for failed tasks)" })),
});

export const TeammateBroadcastParams = Type.Object({
  subject: Type.String({ description: "Broadcast message subject" }),
  body: Type.String({ description: "Broadcast message body" }),
  role: Type.Optional(
    Type.String({ description: "Only send to teammates with this role (e.g. 'worker')" }),
  ),
});

export const TeammateTaskDepsParams = Type.Object({
  taskId: Type.String({ description: "Task ID to update dependencies for" }),
  blocks: Type.Optional(Type.Array(Type.String(), { description: "Task IDs this task blocks" })),
  blockedBy: Type.Optional(Type.Array(Type.String(), { description: "Task IDs that block this task" })),
});

export const TeammateSpawnParams = Type.Object({
  name: Type.String({ description: "Name of the teammate to spawn as a worker" }),
  taskId: Type.String({ description: "Task ID to execute in the child process" }),
  isolation: Type.Optional(
    Type.Union(
      [Type.Literal("worktree"), Type.Literal("none")],
      { description: "Run the worker in a fresh git worktree (default: none)" },
    ),
  ),
  timeoutMs: Type.Optional(
    Type.Integer({
      minimum: 1,
      description: "Kill the worker after this many milliseconds (default: 1800000 = 30 min)",
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
}