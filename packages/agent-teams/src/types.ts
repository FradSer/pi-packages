import type { Static } from "typebox";
import { Type } from "typebox";

// ── Run / Node ────────────────────────────────────────────────────

export const NodeStatus = Type.Union(
  [
    Type.Literal("pending"),
    Type.Literal("running"),
    Type.Literal("completed"),
    Type.Literal("failed"),
    Type.Literal("cancelled"),
  ],
  { description: "Current status of a run node" },
);
export type NodeStatus = Static<typeof NodeStatus>;

export const RunStatus = Type.Union(
  [
    Type.Literal("running"),
    Type.Literal("completed"),
    Type.Literal("failed"),
    Type.Literal("cancelled"),
  ],
  { description: "Current status of a run" },
);
export type RunStatus = Static<typeof RunStatus>;

/** One task in a dispatched run: a bounded child-process unit of work. */
export interface Node {
  /** User-chosen id, unique within the run. */
  id: string;
  /** Mailbox identity: `${runId}:${nodeId}`. */
  workerKey: string;
  /** Resolved agent definition name. */
  agent: string;
  /** The specific task text handed to the worker. */
  prompt: string;
  /** Repository-relative paths used to coordinate this node. */
  paths: string[];
  /** Read nodes may overlap; write nodes need shared-workspace conflict protection. */
  access: "read" | "write";
  /** Optional per-node model pin (provider/model). */
  model?: string;
  /** Optional per-node hard wall-clock cap before the worker is killed. */
  timeoutMs?: number;
  /** Node ids that must complete before this node may start. */
  dependsOn: string[];
  status: NodeStatus;
  result?: string;
  errorMessage?: string;
  /** Real child-process execution info when this node was spawned. */
  spawn?: SpawnInfo;
  createdAt: number;
  updatedAt: number;
  completedAt?: number;
}

/** A dispatched dependency-aware task graph. */
export interface Run {
  id: string;
  cwd: string;
  status: RunStatus;
  concurrency: number;
  /** Every node runs in its own git worktree when true. */
  worktree: boolean;
  /** background=true returns immediately; false gathers in the tool call. */
  background: boolean;
  /** Optional run-level hard wall-clock cap before the run fails. */
  timeoutMs?: number;
  /** Absolute deadline for timeoutMs, when set. */
  deadlineAt?: number;
  /** Run-level failure detail (e.g. run timeout). */
  errorMessage?: string;
  nodes: Record<string, Node>;
  createdAt: number;
  updatedAt: number;
  finishedAt?: number;
  /** True once the run-completion follow-up was delivered, or claimed by wait/foreground gather. */
  completionNotified?: boolean;
  /** True once the run-settled mailbox summary was sent (onRunSettled is idempotent). */
  settledMessageSent?: boolean;
  /** Synthesized final summary produced by the optional __summary node. */
  summary?: string;
}

// ── Spawn ─────────────────────────────────────────────────────────

/** Lifecycle of a spawned child Pi process running a node. */
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
  /** Live assistant text assembled from JSON-mode stream events. */
  liveText?: string;
  /** Current child tool name, if a tool is executing. */
  activeTool?: string;
  /** Live assistant reasoning streamed from the child (shown while no tool runs). */
  liveThinking?: string;
  /** Number of assistant turns observed from the child JSON stream. */
  turns?: number;
  /** The child emitted a final successful assistant response and should close promptly. */
  finalResponse?: boolean;
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
  /** Whether this spawn owns a dedicated Git worktree. */
  isolation?: "worktree" | "none";
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
  status?: "in_progress" | "completed" | "failed";
  taskId?: string;
}

export type WorkerEvent = WorkerMessageEvent;

// ── Tool parameter schemas (typebox) ──────────────────────────────

const NodeAccess = Type.Union(
  [Type.Literal("read"), Type.Literal("write")],
  { description: "read permits overlapping analysis; write protects overlapping shared-workspace changes. Default: read." },
);

/** One task inside teammate_run. */
export const RunTaskSpec = Type.Object({
  id: Type.String({ description: "Node id, unique within this run" }),
  agent: Type.String({ description: "Agent definition name (bundled, user, or project scope)" }),
  prompt: Type.String({ minLength: 1, description: "The specific task text handed to this worker" }),
  dependsOn: Type.Optional(Type.Array(Type.String(), { description: "Node ids that must complete before this node starts" })),
  paths: Type.Array(Type.String({ description: "Repository-relative path this node may inspect or modify" }), {
    minItems: 1,
    description: "Repository-relative paths used to coordinate this node",
  }),
  access: Type.Optional(NodeAccess),
  model: Type.Optional(Type.String({ description: "Optional per-node provider/model pin" })),
  timeoutMs: Type.Optional(Type.Integer({ minimum: 1, description: "Optional per-node hard wall-clock cap before the worker is killed (default: 30 minutes; do not set overly short timeouts for multi-file or reasoning tasks)" })),
});

/** Dispatch a dependency-aware task graph in one call. */
export const TeammateRunParams = Type.Object({
  tasks: Type.Array(RunTaskSpec, {
    minItems: 1,
    maxItems: 32,
    description: "Task graph to dispatch; dependsOn edges must form a DAG",
  }),
  concurrency: Type.Optional(Type.Integer({ minimum: 1, maximum: 32, description: "Max nodes running at once (default: 4)" })),
  worktree: Type.Optional(Type.Boolean({ description: "Run every node in its own git worktree (default: false)" })),
  background: Type.Optional(Type.Boolean({ default: true, description: "Return immediately and deliver one completion follow-up. Default: true — teammates always run in the background; collect via the completion follow-up or teammate_status." })),
  timeoutMs: Type.Optional(Type.Integer({ minimum: 1, description: "Run-level hard wall-clock cap; the run fails when exceeded (default: none, nodes have their own caps)" })),
  summarize: Type.Optional(Type.Boolean({ description: "Append a __summary node after all leaf nodes. Default: true when the run has more than one user task, false for a single task." })),
  summaryAgent: Type.Optional(Type.String({ description: "Agent used for the summary node when summarize is on (default: observer)" })),
  cwd: Type.Optional(Type.String({ description: "Working directory for this run (default: the session cwd)" })),
});

/** Query agents, runs, or one run's node detail. */
export const TeammateStatusParams = Type.Object({
  runId: Type.Optional(Type.String({ description: "Run id for node-level detail; omit for agents plus run overview" })),
});

/** Explicit cancel of a run or single node. */
export const TeammateCancelParams = Type.Object({
  runId: Type.String({ description: "Run id to cancel" }),
  nodeId: Type.Optional(Type.String({ description: "Cancel one node (and its not-yet-started dependents) instead of the whole run; the run continues" })),
});

/** Retry the failed/cancelled nodes of a settled run. */
export const TeammateRetryParams = Type.Object({
  runId: Type.String({ description: "Run id of a settled (failed/cancelled/completed) run" }),
  nodeIds: Type.Optional(Type.Array(Type.String(), { description: "Node ids to reset and re-run; defaults to all failed and cancelled nodes" })),
});

/** Send a direct message or final report. Leaders address a node key or broadcast; workers address team-leader (with optional status) or a same-run peer. */
export const TeammateMessageParams = Type.Object({
  to: Type.String({ description: "Recipient: team-leader (the main session), a same-run node id, or runId:nodeId. Leaders may also use all with runId." }),
  subject: Type.String({ description: "Concise message subject" }),
  body: Type.String({ description: "Message body (or full final deliverable when submitting status=completed/failed to team-leader)" }),
  status: Type.Optional(Type.Union([
    Type.Literal("in_progress"),
    Type.Literal("completed"),
    Type.Literal("failed"),
  ], { description: "Optional status update for the sender's node (use completed/failed when submitting the final deliverable to team-leader)" })),
  runId: Type.Optional(Type.String({ description: "Run id required when to is all (leader only)" })),
});

// ── State snapshot for persistence ────────────────────────────────

export interface TeammateState {
  runs: Record<string, Run>;
  mailboxes: Record<string, MailboxMessage[]>;
  messageCounter: number;
  runCounter: number;
  /** Byte offsets consumed by the parent from each worker's append-only outbox. */
  workerEventOffsets: Record<string, number>;
  /** Event IDs already applied by the parent, keyed to their worker spawn for compaction. */
  workerEventIds: Record<string, string>;
}
