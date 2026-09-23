import type { Static, TSchema, TString, TObject, TUnion } from "typebox";
import { Type } from "typebox";
import { WORKER_BUILTIN_TOOLS } from "./worker-tools.ts";

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
  /** Deferred mail archived when an accepted result closes its Work Item. */
  deferredMessages?: Array<{ from: string; subject: string; body: string; timestamp: number }>;
  errorMessage?: string;
  /** Failed/interrupted Work stays pending for inspection but cannot be
   * autonomously claimed until the Leader deliberately authorizes recovery. */
  recoveryRequired?: boolean;
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
  /** Incarnation the sender addressed. A replacement resident of the same name
   *  must never consume mail written for its predecessor. */
  toSpawnId?: string;
  timestamp: number;
}

// ── Tool parameter schemas (typebox) ──────────────────────────────

export const InlineAgentDefinitionParams = Type.Object({
  description: Type.String({ minLength: 1, description: "Routing contract for the generated Agent" }),
  tools: Type.Optional(Type.Array(Type.String(), { description: `Explicit minimal tool grant. Canonical built-ins: ${WORKER_BUILTIN_TOOLS.join(", ")}. Omitted or [] means coordination-only (agent_event and work), with no file or shell access. No aliases or inherited leader extension tools.` })),
  model: Type.Optional(Type.String({ description: "Provider/model pin or inherit" })),
  verify: Type.Optional(Type.String({ description: "Default Work verification gate" })),
  worktree: Type.Optional(Type.Boolean({ description: "Dedicated Git worktree" })),
  prompt: Type.String({ minLength: 1, description: "Agent role prompt" }),
  persist: Type.Optional(Type.Boolean({ description: "Persist only when explicitly requested" })),
  persistScope: Type.Optional(Type.Union([Type.Literal("project"), Type.Literal("project-local")])),
}, { additionalProperties: false });

/** Some harnesses deliver object/array parameters as JSON strings and Pi
 * validates arguments exactly as delivered, before any handler runs. Accept the
 * string at the schema edge and parse it in the handler so a callable payload is
 * never rejected by validation. */
function stringTolerant<T extends TSchema>(schema: T): TUnion<[T, TString]> {
  return Type.Union([schema, Type.String()]);
}

/** Harnesses that stream tool parameters per name infer JSON parsing from the
 * root schema `properties`. A bare Type.Union exposes only `anyOf`, so object
 * and array parameters such as `definition`, `target`, or `dependsOn` reach
 * validation as unparsed JSON strings and every branch rejects the call before
 * the handler runs. Mirror every branch property onto the root as an optional
 * property (unioned when branches disagree) so callers parse structured values,
 * while each anyOf branch keeps its strict per-action contract. */
function alternativesOf(sub: any): any[] {
  return Array.isArray(sub.anyOf) ? sub.anyOf : [sub];
}

function mergeBranchSubSchemas(pool: any[]): any {
  if (pool.length === 1) return pool[0];
  const types = new Set(pool.map((entry) => entry.type));
  if (types.size === 1) {
    const [type] = [...types];
    // Same JSON type: collapse to the shared type so callers can still infer
    // parsing; literal branches keep an exact enum at the root.
    if (type === "string" && pool.every((entry) => entry.const !== undefined || Array.isArray(entry.enum))) {
      const values = pool.flatMap((entry) => (entry.const !== undefined ? [entry.const] : entry.enum));
      return { type, enum: [...new Set(values)] };
    }
    return { type };
  }
  return { anyOf: pool };
}

/** The root also declares `type: "object"`. A schema that carries `properties`
 * without an explicit object type is rejected by Google's GenerateContent API
 * ("parameters.properties: only allowed for OBJECT type"), which the Gemini
 * routes reach through their provider translators. */
function actionUnion<T extends TObject[]>(branches: [...T], options?: Record<string, unknown>): TUnion<T> {
  const pools: Record<string, any[]> = {};
  for (const branch of branches) {
    for (const [key, sub] of Object.entries((branch as { properties?: Record<string, any> }).properties ?? {})) {
      const pool = (pools[key] ??= []);
      for (const alt of alternativesOf(sub)) {
        const json = JSON.stringify(alt);
        if (!pool.some((entry) => JSON.stringify(entry) === json)) pool.push(alt);
      }
    }
  }
  const properties: Record<string, any> = {};
  for (const [key, pool] of Object.entries(pools)) properties[key] = mergeBranchSubSchemas(pool);
  return Type.Union(branches, { type: "object", ...options, properties } as never) as TUnion<T>;
}

/** Tolerate harnesses that deliver object or array parameters as JSON strings. */
export function parseJsonParam<T>(value: T): T {
  if (typeof value !== "string") return value;
  const text = value.trim();
  if (!text.startsWith("{") && !text.startsWith("[")) return value;
  try {
    return JSON.parse(text) as T;
  } catch {
    return value;
  }
}

/** Parse stringified structured parameters before handlers branch on them. */
export function normalizeCoordinationParams<T extends Record<string, unknown>>(params: T, keys: readonly string[]): T {
  const next: Record<string, unknown> = { ...params };
  for (const key of keys) {
    if (key in next) next[key] = parseJsonParam(next[key]);
  }
  return next as T;
}

/** Reject string parameters that could not be parsed back into structures. */
export function requireParsedParams<T extends Record<string, unknown>>(params: T, keys: readonly string[]): T {
  for (const key of keys) {
    if (typeof params[key] === "string") throw new Error(`Parameter "${key}" must be a JSON object or array, not a string.`);
  }
  return params;
}

/** Legacy overloaded Agent control; replaced by AgentActionParams at final cutover. */
export const AgentActionParams = actionUnion([
  Type.Object({ action: Type.Literal("delegate"), name: Type.String({ minLength: 1 }), prompt: Type.String({ minLength: 1 }), definition: Type.Optional(stringTolerant(InlineAgentDefinitionParams)), resources: Type.Optional(stringTolerant(Type.Array(Type.String({ minLength: 1 })))), verify: Type.Optional(Type.String()), model: Type.Optional(Type.String()), fork: Type.Optional(Type.Boolean()) }, { additionalProperties: false }),
  Type.Object({ action: Type.Literal("start"), name: Type.String({ minLength: 1 }), definition: Type.Optional(stringTolerant(InlineAgentDefinitionParams)), model: Type.Optional(Type.String()) }, { additionalProperties: false }),
  Type.Object({ action: Type.Literal("inspect"), name: Type.String({ minLength: 1 }), session: Type.String({ minLength: 1 }) }, { additionalProperties: false }),
  Type.Object({ action: Type.Literal("stop"), session: Type.String({ minLength: 1 }) }, { additionalProperties: false }),
], { description: "Delegate, start, inspect, or stop an Agent session" });

/** Shut down one living teammate. */
/** Create a board task (leader-only). */
/** First public Work interface slice. Work creation reuses the current
 * single-writer task record until every acquisition path shares one lifecycle. */
export const WorkToolParams = actionUnion([
  Type.Object({
    action: Type.Literal("create"),
    subject: Type.String({ minLength: 1, description: "Work title" }),
    description: Type.Optional(Type.String({ description: "Full Work description" })),
    dependsOn: Type.Optional(stringTolerant(Type.Array(Type.String({ minLength: 1 }), { description: "Work IDs that must complete first" }))),
    verify: Type.Optional(Type.String({ description: "Completion gate for this Work Item" })),
    resources: Type.Optional(stringTolerant(Type.Array(Type.String({ minLength: 1 }), { description: "Resource tags that cannot overlap active Work" }))),
  }, { additionalProperties: false }),
  Type.Object({ action: Type.Literal("list") }, { additionalProperties: false }),
  Type.Object({
    action: Type.Literal("assign"),
    id: Type.String({ minLength: 1, description: "Pending Work Item ID" }),
    target: stringTolerant(Type.Object({ session: Type.String({ minLength: 1, description: "Exact idle session route" }) }, { additionalProperties: false })),
  }, { additionalProperties: false }),
  Type.Object({
    action: Type.Literal("release"),
    id: Type.String({ minLength: 1, description: "Claimed Work Item ID" }),
    reason: Type.String({ minLength: 1, description: "Reason Work is returned to pending" }),
  }, { additionalProperties: false }),
  Type.Object({
    action: Type.Literal("reopen"),
    id: Type.String({ minLength: 1, description: "Completed Work Item ID" }),
    reason: Type.String({ minLength: 1, description: "Reason this completed Work is reopened" }),
  }, { additionalProperties: false }),
  Type.Object({
    action: Type.Literal("supersede"),
    subject: Type.String({ minLength: 1, description: "Replacement Work title" }),
    description: Type.Optional(Type.String({ description: "Full replacement Work description" })),
    dependsOn: Type.Optional(stringTolerant(Type.Array(Type.String({ minLength: 1 }), { description: "Replacement Work dependencies" }))),
    verify: Type.Optional(Type.String({ description: "Replacement completion gate" })),
    resources: Type.Optional(stringTolerant(Type.Array(Type.String({ minLength: 1 }), { description: "Replacement resource tags" }))),
    supersedes: stringTolerant(Type.Array(Type.String({ minLength: 1 }), { minItems: 1, description: "Obsolete Work IDs replaced atomically" })),
  }, { additionalProperties: false }),
], { description: "Create, list, assign, release, reopen, or supersede current Work Items" });

/** Shared leader/worker read-only board view. */
/** Shared communication event parameters across Leader, Worker, and Peers. */
export const AgentEventParams = Type.Object({
  message: Type.String({ description: "Message content" }),
  to: Type.Optional(Type.String({ minLength: 1, description: "Recipient Agent, leader, or exact session route" })),
  intent: Type.Optional(Type.Union([Type.Literal("inform"), Type.Literal("request")])),
}, { additionalProperties: false });

/** The reserved recipient name for reports to the team leader. */
export const LEADER_RECIPIENT = "leader";

/** The single messaging primitive: addressed peer mail and leader reports.
 * `status` is honored only for to="leader" terminal reports. */
/** Self-claim a pending board task. */
/** Worker-only Work claim operation. It queues an intent; the single-writer
 * harness remains the only authority that can grant ownership. */
export const WorkerWorkToolParams = actionUnion([
  Type.Object({ action: Type.Literal("list") }, { additionalProperties: false }),
  Type.Object({
    action: Type.Literal("claim"),
    id: Type.Optional(Type.String({ minLength: 1, description: "Specific claimable Work Item ID" })),
  }, { additionalProperties: false }),
  Type.Object({
    action: Type.Literal("release"),
    result: Type.Optional(Type.String({ description: "Reason owned Work is released" })),
  }, { additionalProperties: false }),
  Type.Object({
    action: Type.Literal("submit"),
    outcome: Type.Union([Type.Literal("success"), Type.Literal("failed")]),
    result: Type.Optional(Type.String({ description: "Result evidence for the owned Work Item" })),
  }, { additionalProperties: false }),
], { description: "Worker claim or submit operation for Work" });

/** Submit a claimed task outcome. Completion passes through the verify gate. */
// ── State snapshot for persistence ────────────────────────────────

export const TEAM_RUNTIME_VERSION = 2;

export interface TeamState {
  runtimeVersion: number;
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
  /** Harness-owned peer-delivery transition by message id. This records queueing,
   *  control-stream acceptance, or a drop aimed at a retired incarnation; it
   *  never asserts recipient processing. */
  peerDeliveryStates: Record<string, "queued" | "routed" | "dropped">;
}
