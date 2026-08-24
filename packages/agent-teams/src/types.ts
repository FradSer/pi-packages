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

/** A named, long-lived child Pi process on the team roster. */
export interface Teammate {
  /** Unique among living teammates; also the mailbox and roster key. */
  name: string;
  /** Resolved agent definition name. */
  agent: string;
  /** Per-spawn capability identity, regenerated for every process. */
  spawnId: string;
  pid: number;
  status: TeammateStatus;
  /** Working directory (the worktree root when isolated). */
  cwd?: string;
  /** Whether this teammate owns a dedicated Git worktree. */
  isolation: "worktree" | "none";
  /** Board task currently claimed by this teammate, if any. */
  currentTaskId?: string;
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
  /** When the harness last sent a claimable-task notice to this teammate. */
  lastNoticeAt?: number;
  /** Claimable task ids already announced to this teammate; one notice per id until it re-arms. */
  noticedTaskIds?: string[];
  usage?: WorkerUsage;
  error?: string;
  createdAt: number;
  updatedAt: number;
  stoppedAt?: number;
  /** Last wall-clock time output was observed (any stream event or prompt delivery). */
  lastOutputAt?: number;
  /** When the current stall episode notice was sent (one per episode). */
  stallNoticeSentAt?: number;
}

// ── Task board ────────────────────────────────────────────────────

export const TaskStatus = Type.Union(
  [
    Type.Literal("pending"),
    Type.Literal("claimed"),
    Type.Literal("completed"),
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
  status: TaskStatus;
  claimedBy?: string;
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
  from: string;
  subject: string;
  body: string;
  status?: "in_progress" | "completed" | "failed";
  timestamp: number;
}

/** Append-only report event emitted by a teammate to the leader. The title
 * is derived by the harness from the first line of the body. */
export interface WorkerReportEvent {
  id: string;
  type: "message";
  worker: string;
  spawnId: string;
  body: string;
  status?: "in_progress" | "completed" | "failed";
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
    && (event.status === undefined || ["in_progress", "completed", "failed"].includes(event.status));
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

/** Spawn one named resident teammate. */
export const TeammateSpawnParams = Type.Object({
  name: Type.String({ minLength: 1, description: "Teammate name, unique among living teammates; used for messaging and claiming" }),
  agent: Type.String({ description: "Agent definition name; an inline definition may create this role in memory for the current session" }),
  prompt: Type.Optional(Type.String({ description: "Optional kickoff prompt delivered as the teammate's first turn; omit to let it wait for messages or board claims" })),
  definition: Type.Optional(Type.Object({
    description: Type.String({ description: "Routing contract for the generated role" }),
    tools: Type.Optional(Type.Array(Type.String(), { description: "Pi tool ids for the generated role" })),
    model: Type.Optional(Type.String({ description: 'Optional provider/model pin, or "inherit" to run on the leader\'s current model' })),
    verify: Type.Optional(Type.String({ description: "Role-default completion gate: a review prompt a fresh reviewer answers with VERDICT: PASS or FAIL" })),
    worktree: Type.Optional(Type.Boolean({ description: "Whether this role receives a dedicated Git worktree" })),
    prompt: Type.String({ minLength: 1, description: "Role prompt for this generated teammate" }),
    persist: Type.Optional(Type.Boolean({ description: "Persist only when the user explicitly asks to keep this role for future sessions" })),
    persistScope: Type.Optional(Type.Union([
      Type.Literal("project"),
      Type.Literal("project-local"),
    ], { description: "Persistence scope; defaults to project-local when persist is true" })),
  }, { description: "Optional generated role definition; kept in memory unless explicitly persisted" })),
});

/** Shut down one living teammate. */
export const TeammateShutdownParams = Type.Object({
  name: Type.String({ description: "Teammate name on the roster" }),
});

/** Create a board task (leader-only). */
export const TaskCreateParams = Type.Object({
  subject: Type.String({ minLength: 1, description: "Short task title shown on the board" }),
  description: Type.Optional(Type.String({ description: "Full task description for the claiming teammate" }),
  ),
  dependsOn: Type.Optional(Type.Array(Type.String(), { description: "Task ids that must complete before this task is claimable" })),
  verify: Type.Optional(Type.String({ description: "Completion gate: a review prompt a fresh reviewer answers with VERDICT: PASS or FAIL. Overrides any agent-role default verify." })),
});

/** Shared leader/worker read-only board view. */
export const TaskListParams = Type.Object({});

/** The reserved recipient name for reports to the team leader. */
export const LEADER_RECIPIENT = "leader";

/** The single messaging primitive: addressed peer mail and leader reports.
 * `status` is honored only for to="leader" terminal reports. */
export const SendMessageParams = Type.Object({
  to: Type.String({ minLength: 1, description: 'Recipient: a teammate name on the roster, or "leader" to report to the team leader' }),
  message: Type.String({ description: "Message content; the first line becomes the title shown in the console" }),
  status: Type.Optional(Type.Union([
    Type.Literal("in_progress"),
    Type.Literal("completed"),
    Type.Literal("failed"),
  ], { description: 'Only for to="leader": completed or failed ends the current assignment and triggers immediate follow-up delivery' })),
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
}
