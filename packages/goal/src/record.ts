/**
 * The Goal record: what a durable objective is, and how it changes.
 *
 * Nothing here reads or writes storage. This module owns the shape and the
 * normalization a persisted record needs before it can be trusted. Storage
 * belongs to ./store.ts and the append-only history to ./ledger.ts.
 *
 * There is deliberately no task tree. A goal is one objective plus one exit
 * condition, and a second opinion about that exit condition — a list the agent
 * ticks off — can contradict the first and leaves the model deciding which one to
 * believe. What remains here is the objective, its optional completion contract,
 * what has been spent, and whether it is still running.
 */

/** Goal lifecycle. `budget_limited` is distinct from `paused` because reaching
 * the spending cap stops work permanently, while a pause is a suspension the
 * user can lift. */
export type GoalStatus = "active" | "paused" | "blocked" | "budget_limited" | "complete";

/** Why a goal stopped. Lets the dashboard and the ledger distinguish "the model
 * gave up" from "the user stopped it". */
export type StopReason = "user" | "agent";

/**
 * Persisted scheduling state.
 *
 * Every field here is durable on purpose. A decision that authorizes another
 * automatic run has to survive a restart, because a goal that survives but its
 * authorization does not is either stuck or, worse, keeps running on memory the
 * process has lost.
 */
export interface GoalSchedulerState {
  /** Session that owns scheduling. Another session cannot claim or pause this
   * goal; it has to be resumed explicitly, so two open sessions cannot silently
   * end each other's work. */
  owner: string;
  /** `interrupted` is a crash marker: a previous run was claimed or running when
   * its session ended, so the goal is paused rather than resumed, because the
   * dispatch that would have finished it never will. */
  phase: "idle" | "ready" | "claimed" | "running" | "interrupted";
  /** What the model said comes next. Recorded so the following turn starts from
   * the model's own answer rather than from nothing. It does not authorize
   * anything: the loop continues either way. */
  nextAction?: string;
  /** Automatic runs consumed in the current period. Only creation or an explicit
   * resume resets it. */
  used: number;
  /** Consecutive settled runs without completed work. */
  idleRuns?: number;
  /** Rotates on every authorization change, so a claim computed for an older
   * decision cannot be replayed against a newer one. */
  generation: string;
  /** The claim that was authorized, spent exactly once. */
  dispatch?: { id: string; claimedAt: number };
}

export interface GoalUsage {
  /** Lifetime tokens attributed to this goal. Not context occupancy. */
  tokensUsed: number;
  /** Wall-clock seconds the goal has been worked on. The only progress figure
   * the surface reports: a goal has no steps to be partway through. */
  activeSeconds: number;
}

export interface GoalRecord {
  id: string;
  /** Thread that created the goal. Absent only on legacy records. */
  threadId?: string;
  objective: string;
  status: GoalStatus;
  autoContinue: boolean;
  usage: GoalUsage;
  createdAt: string;
  updatedAt: string;
  /** Monotonic mutation counter, compared under the write lock so a stale
   * writer is refused instead of overwriting a newer record. */
  revision: number;
  activePath?: string;
  archivedPath?: string;
  stopReason?: StopReason;
  pauseReason?: string;
  /** Lifetime spending cap in whole tokens. */
  tokenBudget?: number;
  /** What evidence must exist before this goal may be considered met. The
   * completion check is told about it and nothing else is. */
  verificationContract?: string;
  /** What the model said it had done when it asked to close the goal. Retained
   * so a rejection can be read against what was claimed, never as evidence. */
  completionClaim?: string;
  /** Observations before the latest requirement revision are excluded. */
  evidenceSince?: string;
  /** Consecutive valid explicit completion refusals for these requirements. */
  completionFailures?: number;
  scheduler?: GoalSchedulerState;
}

/** Version of the persisted record file. A record written by an earlier version
 * is normalized forward; one from a newer version is refused rather than read on
 * its known fields, because its extra fields may carry the state the missing
 * ones would have. */
export const GOAL_RECORD_VERSION = 1;

export const MAX_OBJECTIVE_CHARS = 4000;

export function nowIso(): string {
  return new Date().toISOString();
}

/** A short token that cannot collide with a value read back from disk. */
export function randomToken(): string {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function asWholeNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : undefined;
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[]): T | undefined {
  return typeof value === "string" && (allowed as readonly string[]).includes(value) ? (value as T) : undefined;
}

export function normalizeGoalRecord(raw: unknown): GoalRecord | undefined {
  const record = asRecord(raw);
  if (!record) return undefined;
  const id = asString(record.id);
  const objective = asString(record.objective);
  if (!id || !objective) return undefined;
  const goal: GoalRecord = {
    id,
    objective: objective.slice(0, MAX_OBJECTIVE_CHARS),
    status: oneOf(record.status, ["active", "paused", "blocked", "budget_limited", "complete"] as const) ?? "paused",
    autoContinue: record.autoContinue === true,
    usage: {
      tokensUsed: asWholeNumber(asRecord(record.usage)?.tokensUsed) ?? 0,
      activeSeconds: asWholeNumber(asRecord(record.usage)?.activeSeconds) ?? 0,
    },
    createdAt: asString(record.createdAt) ?? nowIso(),
    updatedAt: asString(record.updatedAt) ?? nowIso(),
    // A record written before revisions existed normalizes to zero, which is a
    // real revision: the first mutation after the upgrade produces one.
    revision: asWholeNumber(record.revision) ?? 0,
  };
  if (asString(record.threadId)) goal.threadId = String(record.threadId);
  if (asString(record.activePath)) goal.activePath = String(record.activePath);
  if (asString(record.archivedPath)) goal.archivedPath = String(record.archivedPath);
  const stopReason = oneOf(record.stopReason, ["user", "agent"] as const);
  if (stopReason) goal.stopReason = stopReason;
  if (asString(record.pauseReason)) goal.pauseReason = String(record.pauseReason);
  const budget = asWholeNumber(record.tokenBudget);
  if (budget !== undefined && budget > 0) goal.tokenBudget = budget;
  if (asString(record.verificationContract)) goal.verificationContract = String(record.verificationContract);
  if (asString(record.completionClaim)) goal.completionClaim = String(record.completionClaim);
  if (asString(record.evidenceSince)) goal.evidenceSince = String(record.evidenceSince);
  goal.completionFailures = asWholeNumber(record.completionFailures) ?? 0;
  const scheduler = normalizeScheduler(asRecord(record.scheduler));
  if (scheduler) goal.scheduler = scheduler;
  return goal;
}

function normalizeScheduler(raw: Record<string, unknown> | undefined): GoalSchedulerState | undefined {
  const owner = asString(raw?.owner);
  if (!owner) return undefined;
  const scheduler: GoalSchedulerState = {
    owner,
    // A record from a version whose phase this one does not know reads as
    // `idle`, which is the safe reading: it authorizes no run on its own, and a
    // fresh decision has to be armed before anything may claim it.
    phase: oneOf(raw?.phase, ["idle", "ready", "claimed", "running", "interrupted"] as const) ?? "idle",
    used: asWholeNumber(raw?.used) ?? 0,
    idleRuns: asWholeNumber(raw?.idleRuns) ?? 0,
    generation: asString(raw?.generation) ?? "unknown",
  };
  const nextAction = asString(raw?.nextAction);
  if (nextAction) scheduler.nextAction = nextAction;
  const dispatch = asRecord(raw?.dispatch);
  const dispatchId = asString(dispatch?.id);
  const claimedAt = asWholeNumber(dispatch?.claimedAt);
  if (dispatchId && claimedAt !== undefined) scheduler.dispatch = { id: dispatchId, claimedAt };
  return scheduler;
}

/** Deep copy. Every mutation runs on a clone, so a rejected write cannot leave a
 * half-applied change in the caller's live object. */
export function cloneGoal(goal: GoalRecord): GoalRecord {
  return {
    ...goal,
    usage: { ...goal.usage },
    scheduler: goal.scheduler
      ? { ...goal.scheduler, dispatch: goal.scheduler.dispatch ? { ...goal.scheduler.dispatch } : undefined }
      : undefined,
  };
}

/** Whether the lifetime token cap has been reached. */
export function budgetReached(goal: GoalRecord): boolean {
  return goal.tokenBudget !== undefined && goal.usage.tokensUsed >= goal.tokenBudget;
}

export function remainingBudget(goal: GoalRecord): number | undefined {
  if (goal.tokenBudget === undefined) return undefined;
  return Math.max(0, goal.tokenBudget - goal.usage.tokensUsed);
}

export function newGoalScheduler(owner: string, generation: string): GoalSchedulerState {
  return { owner, phase: "idle", used: 0, generation };
}

/** Elapsed time, the one progress figure a goal has. A goal is not partway
 * through a list, so "how long has this been going" is the only honest answer to
 * "how is it doing".
 *
 * The figure scales with the run. A goal can last minutes, hours or days, and
 * total minutes stop being readable past an hour: "107m" is not what a person
 * reads a two-hour run as. Two units are shown, the larger one first, and the
 * smaller one only while it carries information. */
export function formatElapsed(seconds: number): string {
  const minutes = Math.max(0, Math.floor(seconds / 60));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ${minutes % 60}m`;
  const days = Math.floor(hours / 24);
  return `${days}d ${hours % 24}h`;
}