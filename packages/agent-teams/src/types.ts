import type { Static } from "typebox";
import { Type } from "typebox";

// ── Teammate ──────────────────────────────────────────────────────

export const TeammateStatus = Type.Union(
  [
    Type.Literal("starting"),
    Type.Literal("idle"),
    Type.Literal("working"),
    Type.Literal("stopped"),
  ],
  { description: "Lifecycle of a resident teammate" },
);
export type TeammateStatus = Static<typeof TeammateStatus>;

export interface WorkerAssignment {
  id: string;
  kind: "direct" | "board";
  /** Resource tags prevent concurrent mutating assignments from overlapping. */
  resources: string[];
  /** A terminal direct assignment is closed until the leader explicitly reopens it. */
  closed?: boolean;
}

/** A named, long-lived child Pi process on the team roster. */
export interface Teammate {
  /** Unique among living teammates; also the mailbox and roster key. */
  name: string;
  /** Resolved agent definition name. */
  agent: string;
  /** Per-spawn capability identity, regenerated for every process. */
  spawnId: string;
  /** Stable Work Item selected by agent; each reopen creates a new assignment attempt. */
  workId?: string;
  context?: "fresh" | "fork";
  pid: number;
  status: TeammateStatus;
  /** Working directory (the worktree root when isolated). */
  cwd?: string;
  /** Whether this teammate owns a dedicated Git worktree. */
  isolation: "worktree" | "none";
  /** Board task currently claimed by this teammate, if any. */
  currentTaskId?: string;
  /** The one assignment this worker is allowed to execute. Direct assignments
   * and board claims are mutually exclusive until the leader opens another. */
  assignment?: WorkerAssignment;
  /** Most recent assignment retained for successor handoff after release or shutdown. */
  lastAssignment?: WorkerAssignment;
  lastTaskId?: string;
  /** Effective launch model reference ("provider/model"); absent when Pi picks its default. */
  model?: string;
  /** Live assistant text assembled from the RPC stream. */
  liveText?: string;
  /** Current child tool name, if a tool is executing. */
  activeTool?: string;
  /** Live assistant reasoning streamed while no tool runs. */
  liveThinking?: string;
  /** Assistant turns observed in the current wake-up sequence. */
  turns?: number;
  /** The child finished its current sequence and awaits the next prompt. */
  sequenceEnded?: boolean;
  /** Leader reports are closed until a new prompt starts after a terminal report. */
  reportSequenceEnded?: boolean;
  /** When the harness last sent a claimable-task notice to this teammate. */
  lastNoticeAt?: number;
  /** Claimable task ids already announced to this teammate; one notice per id until it re-arms. */
  noticedTaskIds?: string[];
  usage?: WorkerUsage;
  error?: string;
  /** Effective tool allowlist granted to the child process (role tools plus
   *  the capability set). Absent only for legacy snapshots. */
  tools?: string[];
  /** True once recognized model/stream activity was observed for this
   * incarnation; console telemetry only, never a leader notification. */
  modelOutputSeen?: boolean;
  createdAt: number;
  updatedAt: number;
  stoppedAt?: number;
  /** Last wall-clock time output was observed (any stream event or prompt delivery). */
  lastOutputAt?: number;
}

// ── Task board ────────────────────────────────────────────────────

export const TaskStatus = Type.Union(
  [
    Type.Literal("pending"),
    Type.Literal("claimed"),
    Type.Literal("completed"),
    Type.Literal("superseded"),
  ],
  { description: "Board lifecycle of a task" },
);
export type TaskStatus = Static<typeof TaskStatus>;

/** One task on the shared board. Only the leader process writes board state. */
export interface BoardTask {
  id: string;
  subject: string;
  description?: string;
  /** Task ids that must complete before this task is claimable. */
  dependsOn: string[];
  /** Completion gate: a review prompt a fresh one-shot reviewer answers with
   *  VERDICT: PASS or FAIL; overrides the agent-role default. */
  verify?: string;
  /** Mutating work must use stable resource tags such as `firmware/sub-node`.
   *  A resource conflicts with itself and any slash-prefixed descendant. */
  resources: string[];
  status: TaskStatus;
  claimedBy?: string;
  /** Replacement task that made this task obsolete. */
  supersededBy?: string;
  result?: string;
  errorMessage?: string;
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
  status?: "completed" | "failed";
  result?: string;
  timestamp: number;
}

// ── Spawn ─────────────────────────────────────────────────────────

/** Token/cost usage reported by a teammate (accumulated across sequences). */
export interface WorkerUsage {
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
  totalTokens: number;
  cost: number;
}

// ── Mailbox ───────────────────────────────────────────────────────

export interface MailboxMessage {
  id: string;
  assignmentId?: string;
  spawnId?: string;
  from: string;
  subject: string;
  body: string;
  status?: "in_progress" | "completed" | "failed" | "inform" | "request" | "handoff";
  /** The harness retained this report for console inspection after shutdown;
   * it never initiated a leader follow-up. */
  archived?: boolean;
  timestamp: number;
}

/** Append-only report event emitted by a teammate to the leader. The title
 * is derived by the harness from the first line of the body. */
export interface WorkerReportEvent {
  id: string;
  assignmentId?: string;
  type: "message";
  worker: string;
  spawnId: string;
  body: string;
  status?: "in_progress" | "completed" | "failed" | "inform" | "request" | "handoff";
  /** Wall-clock time the teammate wrote the event. */
  timestamp?: number;
}

export type WorkerEvent = WorkerReportEvent;

/** Structural guard applied to every outbox record before it is trusted. */
export function isWorkerEvent(value: unknown): value is WorkerReportEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Partial<WorkerReportEvent>;
  return typeof event.id === "string"
    && event.type === "message"
    && typeof event.worker === "string"
    && typeof event.spawnId === "string"
    && typeof event.body === "string"
    && (event.assignmentId === undefined || typeof event.assignmentId === "string")
    && (event.status === undefined || ["in_progress", "completed", "failed", "inform", "request", "handoff"].includes(event.status))
    && (event.timestamp === undefined || (typeof event.timestamp === "number" && Number.isFinite(event.timestamp)));
}

/** Derive a display title from the first non-empty line of a message. */
export function messageTitle(body: string): string {
  for (const line of body.split("\n")) {
    const trimmed = line.replace(/\s+/g, " ").trim();
    if (trimmed) return trimmed.slice(0, 120);
  }
  return "(no content)";
}

/** One message in a teammate inbox (peer-to-peer or harness feedback). */
export interface InboxMessage {
  id: string;
  from: string;
  subject: string;
  body: string;
  timestamp: number;
}

// ── Tool parameter schemas (typebox) ──────────────────────────────

/** The single minimal delegation and work control tool (leader-only). */
export const AgentToolParams = Type.Object({
  name: Type.String({ minLength: 1, description: "Persistent or temporary Agent name" }),
  prompt: Type.Optional(Type.String({ description: "New work without work ID; guidance to selected work with an ID. Omit only for deliberate presence diagnosis, never to poll progress or completion." })),
  work: Type.Optional(Type.String({ description: "Specific Work Item ID to steer or reopen" })),
  model: Type.Optional(Type.String({ description: "Optional model override for new work (e.g. 'provider/model'). Defaults to current session model." })),
  fork: Type.Optional(Type.Boolean({ description: "Copy the current leader conversation into new work. Defaults to false (fresh context); invalid with work or without prompt." })),
});

/** Spawn one named resident teammate or sub-agent. */
export const TeammateSpawnParams = Type.Object({
  name: Type.String({ minLength: 1, description: "Unique teammate name" }),
  agent: Type.String({ description: "Role id; inline definition may create the role for this session" }),
  prompt: Type.Optional(Type.String({ description: "Kickoff prompt; omit to let it wait for messages or board claims" })),
  resources: Type.Optional(Type.Array(Type.String({ minLength: 1 }), { description: "Resource tags for this direct assignment; overlapping active claims are rejected" })),
  handoffFrom: Type.Optional(Type.String({ minLength: 1, description: "Stopped teammate whose assignment and reports feed this successor kickoff" })),
  definition: Type.Optional(Type.Object({
    description: Type.String({ description: "Routing contract for the generated role" }),
    tools: Type.Optional(Type.Array(Type.String(), { description: "Pi tool ids for the role; built-ins only, no extension ids" })),
    model: Type.Optional(Type.String({ description: 'Provider/model pin, or "inherit" for the leader\'s current model' })),
    verify: Type.Optional(Type.String({ description: "Review prompt a fresh reviewer answers with VERDICT: PASS or FAIL" })),
    worktree: Type.Optional(Type.Boolean({ description: "Dedicated Git worktree for this role" })),
    prompt: Type.String({ minLength: 1, description: "Role prompt" }),
    persist: Type.Optional(Type.Boolean({ description: "Persist only when the user explicitly asks" })),
    persistScope: Type.Optional(Type.Union([
      Type.Literal("project"),
      Type.Literal("project-local"),
    ], { description: "Scope; defaults to project-local when persist is true" })),
  }, { description: "Generated role definition; in-memory unless persisted" })),
});

/** Shut down one living teammate. */
export const TeammateShutdownParams = Type.Object({
  name: Type.String({ description: "Teammate name on the roster" }),
});

/** Create a board task (leader-only). */
export const TaskCreateParams = Type.Object({
  subject: Type.String({ minLength: 1, description: "Task title shown on the board" }),
  description: Type.Optional(Type.String({ description: "Full task description for the claiming teammate" }),
  ),
  dependsOn: Type.Optional(Type.Array(Type.String(), { description: "Task ids that must complete first" })),
  verify: Type.Optional(Type.String({ description: "Completion gate: a fresh reviewer judges acceptance; PASS completes, FAIL returns the task" })),
  resources: Type.Optional(Type.Array(Type.String({ minLength: 1 }), { description: "Resource tags this task mutates; overlapping active claims are rejected" })),
  supersedes: Type.Optional(Type.Array(Type.String({ minLength: 1 }), { description: "Obsolete task ids this replaces" })),
});

/** Shared leader/worker read-only board view. */
export const TaskListParams = Type.Object({});

/** Shared communication event parameters across Leader, Worker, and Peers. */
export const AgentEventParams = Type.Object({
  message: Type.String({ description: "Message content or report" }),
  to: Type.Optional(Type.String({ minLength: 1, description: "Recipient Agent name, leader, or precise reply route" })),
  status: Type.Optional(Type.Union([
    Type.Literal("inform"),
    Type.Literal("request"),
    Type.Literal("handoff"),
    Type.Literal("in_progress"),
    Type.Literal("completed"),
    Type.Literal("failed"),
  ], { description: "Allowed message intent or terminal transition" })),
});

/** The reserved recipient name for reports to the team leader. */
export const LEADER_RECIPIENT = "leader";

/** The single messaging primitive: addressed peer mail and leader reports.
 * `status` is honored only for to="leader" terminal reports. */
export const SendMessageParams = Type.Object({
  to: Type.String({ minLength: 1, description: 'Teammate name, or "leader" to report' }),
  message: Type.String({ description: "Message content; first line becomes the console title" }),
  reopen: Type.Optional(Type.Boolean({ description: "Leader only: start a new assignment after completion" })),
  resources: Type.Optional(Type.Array(Type.String({ minLength: 1 }), { description: "Leader only: resource tags for a reopened assignment" })),
  status: Type.Optional(Type.Union([
    Type.Literal("in_progress"),
    Type.Literal("completed"),
    Type.Literal("failed"),
  ], { description: 'Only for to="leader": completed or failed ends reporting; in_progress keeps the assignment open' })),
});

/** Self-claim a pending board task. */
export const TaskClaimParams = Type.Object({
  taskId: Type.Optional(Type.String({ description: "Specific task id to claim; omit to claim the first claimable task" })),
});

/** Submit a claimed task outcome. Completion passes through the verify gate. */
export const TaskSubmitParams = Type.Object({
  taskId: Type.String({ description: "The claimed task id" }),
  status: Type.Union([Type.Literal("completed"), Type.Literal("failed")], { description: "Outcome of the claimed task" }),
  result: Type.Optional(Type.String({ description: "Result summary recorded on the board when completed" })),
});

// ── State snapshot for persistence ────────────────────────────────

export interface TeamState {
  teammates: Record<string, Teammate>;
  tasks: Record<string, BoardTask>;
  /** Unified teammate model for this session; spawns without a role pin use it. */
  defaultModel?: string;
  /** Single leader inbox for teammate reports and harness diagnostics. */
  leaderMailbox: MailboxMessage[];
  messageCounter: number;
  /** Byte offsets consumed by the parent from each teammate's outbox. */
  workerEventOffsets: Record<string, number>;
  /** Report event ids already applied, keyed by teammate spawn. */
  workerEventIds: Record<string, string>;
  /** Consumed byte offsets per peer inbox file. */
  peerInboxOffsets: Record<string, number>;
  /** Delivered peer message ids per inbox, capped FIFO for deduplication. */
  peerDeliveredIds: Record<string, string[]>;
  /** Harness-owned peer-delivery transition by message id. This records queueing
   * or control-stream acceptance only; it never asserts recipient processing. */
  peerDeliveryStates: Record<string, "queued" | "routed">;
}
