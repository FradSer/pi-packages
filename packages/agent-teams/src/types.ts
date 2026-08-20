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
  /** Stable node identity: `${runId}:${nodeId}`. */
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
  /** RPC mode keeps stdin available for runtime steering. */
  mode?: "json" | "rpc";
  /** Optional maximum number of assistant turns before the worker is stopped. */
  turnBudget?: number;
  /** Node ids that must complete before this node may start. */
  dependsOn: string[];
  /** Named upstream node ids whose results are included as fork context. */
  forkContext?: string[];
  /** Named input bindings using `nodeId#/json/pointer` sources. */
  inputBindings?: Record<string, string>;
  status: NodeStatus;
  result?: string;
  /** Named structured outputs emitted through teammate_message. */
  namedOutputs?: Record<string, string>;
  /** Bounded JSON output emitted through teammate_message for downstream data flow. */
  structuredOutput?: unknown;
  errorMessage?: string;
  /** True once the terminal node follow-up has been delivered. */
  nodeFollowUpSent?: boolean;
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
  /** Run-level failure detail. */
  errorMessage?: string;
  nodes: Record<string, Node>;
  createdAt: number;
  updatedAt: number;
  finishedAt?: number;
  /** True once the run-completion follow-up was delivered, or claimed by wait/foreground gather. */
  completionNotified?: boolean;
  /** True once the run-settled leader summary was sent (onRunSettled is idempotent). */
  settledMessageSent?: boolean;
  /** Synthesized final summary produced by the optional __summary node. */
  summary?: string;
  /** True once run cancellation has been requested; it wins over node outcomes. */
  cancelRequested?: boolean;
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
  spawnId: string;
  mode?: "json" | "rpc";
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
  timedOut?: boolean;
  /** Whether this spawn owns a dedicated Git worktree. */
  isolation?: "worktree" | "none";
  /** Terminal report accepted from the worker before process close. */
  logicalTerminalReport?: "completed" | "failed";
  /** True after the first terminal report for this spawn is accepted. */
  terminalReportAccepted?: boolean;
  /** True only after the child process close event has been observed. */
  processClosed: boolean;
  /** True after the harness emits the canonical terminal result. */
  terminalResultEmitted?: boolean;
}

// ── Mailbox ───────────────────────────────────────────────────────

export interface MailboxMessage {
  id: string;
  from: string;
  subject: string;
  body: string;
  runId?: string;
  timestamp: number;
}

/** Append-only event emitted by a worker and applied by the team leader. */
export interface WorkerMessageEvent {
  id: string;
  type: "message";
  worker: string;
  spawnId: string;
  subject: string;
  body: string;
  status?: "in_progress" | "completed" | "failed";
  data?: {
    kind?: "named_output" | "output";
    name?: string;
    value?: string;
    output?: unknown;
    message?: string;
  };
}

export type WorkerEvent = WorkerMessageEvent;

// ── Tool parameter schemas (typebox) ──────────────────────────────

const NodeAccess = Type.Union(
  [Type.Literal("read"), Type.Literal("write")],
  { description: "Scheduling and prompt metadata only: read/write intent guides advisory shared-workspace write/write coordination; it does not enforce filesystem permissions or provide an OS/container sandbox. Default: read." },
);

/** One task inside teammate_run. */
export const RunTaskSpec = Type.Object({
  id: Type.String({ description: "Node id, unique within this run" }),
  agent: Type.String({ description: "Agent definition name (bundled, user, or project scope)" }),
  prompt: Type.String({ minLength: 1, description: "The specific task text handed to this worker" }),
  dependsOn: Type.Optional(Type.Array(Type.String(), { description: "Node ids that must complete before this node starts" })),
  paths: Type.Array(Type.String({ description: "Repository-relative path included in scheduling overlap checks and the worker prompt; not a permission boundary" }), {
    minItems: 1,
    description: "Scheduling and prompt metadata only for advisory shared-workspace write/write coordination; paths do not enforce read/write access or provide an OS/container sandbox",
  }),
  access: Type.Optional(NodeAccess),
  model: Type.Optional(Type.String({ description: "Optional per-node provider/model pin" })),
  mode: Type.Optional(Type.Union([Type.Literal("json"), Type.Literal("rpc")], { description: "Worker process mode; rpc enables runtime steering" })),
  turnBudget: Type.Optional(Type.Integer({ minimum: 1, description: "Optional maximum assistant turns before the worker is stopped (default: 100; high safety cap for edge cases)" })),
  forkContext: Type.Optional(Type.Array(Type.String(), { description: "Named upstream node ids whose results are included as fork context" })),
  inputBindings: Type.Optional(Type.Record(Type.String(), Type.String(), { description: "Named inputs bound from dependency outputs using nodeId#/json/pointer" })),
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
  background: Type.Optional(Type.Boolean({ default: true, description: "Return immediately and deliver one completion follow-up. Default: true — teammates always run in the background; workers message team-leader with deliverables upon completion." })),
  summarize: Type.Optional(Type.Boolean({ description: "Append a __summary node after all leaf nodes. Default: true when the run has more than one user task, false for a single task." })),
  summaryAgent: Type.Optional(Type.String({ description: "Agent used for the summary node when summarize is on (default: observer)" })),
  cwd: Type.Optional(Type.String({ description: "Working directory for this run (default: the session cwd)" })),
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

/** Worker progress message or final report to the team leader. */
export const TeammateMessageParams = Type.Object({
  subject: Type.String({ description: "Concise report subject" }),
  body: Type.String({ description: "Progress note or full final deliverable for the team leader" }),
  status: Type.Optional(Type.Union([
    Type.Literal("in_progress"),
    Type.Literal("completed"),
    Type.Literal("failed"),
  ], { description: "Optional worker status; use completed or failed for the final deliverable" })),
  data: Type.Optional(Type.Record(Type.String(), Type.Unknown(), { description: "Structured teammate data: named_output or output" })),
});

/** Leader-only operation that fans out a completed node's structured array output. */
export const TeammateFanoutParams = Type.Object({
  runId: Type.String({ description: "Source run id" }),
  nodeId: Type.String({ description: "Completed source node whose structured output is an array" }),
  agent: Type.String({ description: "Agent to run for each item" }),
  prompt: Type.String({ minLength: 1, description: "Task prompt; each item is appended as JSON" }),
  paths: Type.Array(Type.String({ description: "Scheduling and prompt metadata only: repository-relative paths guide advisory shared-workspace write/write coordination; they do not enforce filesystem permissions or provide an OS/container sandbox" }), { minItems: 1, description: "Scheduling and prompt metadata only for each child run; paths do not enforce read/write access or provide an OS/container sandbox" }),
  access: Type.Optional(NodeAccess),
  model: Type.Optional(Type.String()),
  turnBudget: Type.Optional(Type.Integer({ minimum: 1 })),
  concurrency: Type.Optional(Type.Integer({ minimum: 1, maximum: 32 })),
  background: Type.Optional(Type.Boolean({ default: true })),
});

/** Leader-only runtime steer sent through the existing teammate_message name. */
export const TeammateLeaderMessageParams = Type.Object({
  target: Type.String({ description: "Run-qualified worker key, for example run_1:inspect" }),
  body: Type.String({ minLength: 1, description: "Steering message for the running RPC worker" }),
});

// ── State snapshot for persistence ────────────────────────────────

export interface TeammateState {
  runs: Record<string, Run>;
  /** Single leader inbox for worker terminal reports and leader-bound messages. */
  leaderMailbox: MailboxMessage[];
  messageCounter: number;
  runCounter: number;
  /** Byte offsets consumed by the parent from each worker's append-only outbox. */
  workerEventOffsets: Record<string, number>;
  /** Event IDs already applied by the parent, keyed to their worker spawn for compaction. */
  workerEventIds: Record<string, string>;
}
