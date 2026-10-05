/**
 * Team machine — resident teammate lifecycle, peer mail routing, task-intent
 * processing, verify gating, and the harness poll loop that wakes idle
 * agents. The leader model never polls; this loop is the coordination
 * engine described by the BDD contract.
 */

import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { getAgentDir } from "@earendil-works/pi-coding-agent";

/** pi thinking levels, mirrored from @earendil-works/pi-agent-core. */
type LeaderThinkingLevel = NonNullable<ExtensionContext["thinkingLevel"]>;
const THINKING_LEVELS: readonly LeaderThinkingLevel[] = ["off", "minimal", "low", "medium", "high", "xhigh", "max"];
import { modelLabel, runPiWorker, type RunPiWorkerOptions } from "@fradser/pi-kit";
import { MODEL_INHERIT_ALIAS, discoverAgents, registerSessionAgent, resolveAgent, type AgentDefinition, type AgentDefinitionInput } from "@fradser/pi-subagents";
import {
  activeAssignmentConflict,
  acknowledgeSupersession,
  applyClaimIntent,
  assignAgent,
  bindTask,
  completeTaskWithOutcome,
  createBoundWork,
  tasksRevision,
  claimableTasks,
  clearWorkerRunEvents,
  createTask,
  deliverToLeader,
  discardTask,
  getPeerInboxOffset,
  getState,
  getAgent,
  getTeamDefaultModel,
  idleAgents,
  isPeerDelivered,
  isValidAgentName,
  listAgents,
  livingAgents,
  loadTasks,
  markTasksChanged,
  markPeerDelivered,
  getTask,
  progressRevision,
  registerAgent,
  failTasksHeldBy,
  revertUndeliveredTake,
  taskDependenciesMet,
  receiveWorkerMessage,
  reopenTask,
  setTaskContext,
  setPeerInboxOffset,
  rosterRevision,
  setPeerDeliveryState,
  stateRevision,
  updateAgent,
  updateAgentProgress,
} from "./state.ts";
import {
  tasksFilePath,
  buildTaskHandoff,
  claimsDir,
  createTaskIntent,
  formatTaskHandoff,
  normalizeResources,
  readTasksFile,
  submissionsDir,
  takeTaskIntent,
  writeTasksFile,
  TASK_HOLDER_ENV,
  type Task,
  type TaskRefusalResult,
} from "@fradser/pi-tasks";
import {
  appendInboxMessage,
  inboxPath,
  readJsonlBatch,
  removeSessionStateDir,
  removeWorkerOutbox,
  rosterPath,
  stateFilePath,
  writeRoster,
  writeStateFile,
  workerOutboxPath,
} from "./statefile.ts";
import { isWorkerEvent } from "./types.ts";
import {
  deliverFreshAssignment,
  deliverPrompt,
  deliverResidentPrompt,
  deliverResidentSteer,
  isCleanExit,
  isFreshAssignmentPending,
  resolveAgentTools,
  sendAgentSteer,
  sendAgentFollowUp,
  spawnResident,
  terminateAllAgents,
  terminateAgent,
  unknownAgentTools,
  type AgentProcessResult,
  type ResidentSpawnOptions,
} from "@fradser/pi-subagents";
import { WORKER_CAPABILITY_TOOLS, WORKER_EXTENSION_PATH } from "./capability-tools.ts";
import {
  assertPrivateSessionFiles,
  ensureAgentWorkspace,
  inlineDefinitionApplies,
  AGENT_MEMORY_CAPABILITY_TOOLS,
  SUBAGENT_ROLE_ENV,
  SUBAGENT_TOOLS_ENV,
  SUBAGENT_DEFINITION_ENV,
  SUBAGENT_SCOPE_ENV,
  SUBAGENT_EXTENSION_PATH,
  STREAM_RECOVERY_EXTENSION_PATH,
  unknownAgentToolsError,
  type AgentWorkspace,
} from "@fradser/pi-subagents";
import { messageTitle, type InboxMessage, type Agent, type WorkerAssignment, type AgentUsage } from "./types.ts";
import { exactSessionRoute, resolveExactSession } from "./recipient.ts";
import type { LeaderReport } from "@fradser/pi-subagents";

/** Harness coordination cadence: outbox drain every tick, notices paced. */
const LIVE_POLL_MS = 500;
/** Minimum gap between claimable-task notices per teammate. One-shot noticing
 *  makes repeats rare; this floor keeps any residual burst from stampeding
 *  every idle teammate at once, and each wake costs a full worker turn. */
const DEFAULT_NOTICE_PACE_MS = 5 * 60 * 1000;
export const NOTICE_PACE_MS = readDurationEnv("PI_TEAMMATE_NOTICE_PACE_MS", DEFAULT_NOTICE_PACE_MS);
/** Consecutive verify failures before the harness stops inviting resubmission and escalates to the leader instead. */
export const VERIFY_FAILURE_ESCALATE_AFTER = 2;
/** Claimable task ids remembered per teammate. markTasksNoticed prunes stale
 *  ids on every notice, so slots are occupied only by currently-claimable
 *  work; the cap is far above any realistic concurrent tasks size. */
const MAX_NOTICED_TASK_IDS = 256;
/** Claimable tasks listed in one wake-prompt tasks notice. */
const WAKE_NOTICE_TASK_LIMIT = 10;
/** Console-only silence marker: after this long without output the roster
 * shows "stalled". It never notifies the leader or terminates anything. */
const DEFAULT_STALL_SILENCE_MS = 5 * 60 * 1000;
const STALL_SILENCE_MS = readDurationEnv("PI_TEAMMATE_STALL_SILENCE_MS", DEFAULT_STALL_SILENCE_MS);
/** Fully-consumed inboxes larger than this are truncated. */
const INBOX_COMPACT_BYTES = 256 * 1024;

function readDurationEnv(name: string, fallback: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === "") return fallback;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 ? value : fallback;
}

export function stallSilenceMs(teammate: Pick<Agent, "lastOutputAt">, now = Date.now()): number | undefined {
  if (teammate.lastOutputAt === undefined) return undefined;
  return Math.max(0, now - teammate.lastOutputAt);
}

export function formatSilenceDuration(milliseconds: number): string {
  const totalMinutes = Math.floor(Math.max(0, milliseconds) / 60_000);
  if (totalMinutes < 1) return "less than 1m";
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours > 0) return `${hours}h${minutes > 0 ? ` ${minutes}m` : ""}`;
  return `${minutes}m`;
}

/** Console-only silence threshold for the roster "stalled" marker. */
export function stallThresholdMs(_teammate: Pick<Agent, "modelOutputSeen" | "activeTool">): number {
  return STALL_SILENCE_MS;
}

let livePollTimer: ReturnType<typeof setInterval> | undefined;
let generation = 0;
let runtimeStateFile = "";
let tasksFile = "";
let leaderCwd = "";
/** Live view of the leader session's current model, resolved at spawn time. */
let leaderModelRef: () => string | undefined = () => undefined;
let leaderThinkingLevelRef: () => LeaderThinkingLevel | undefined = () => undefined;
let sendUpdate: (report: LeaderReport) => void = () => {};
let notifyChange: () => void = () => {};

const pendingShutdowns = new Set<string>();
const confirmedStopTimes = new Map<string, number>();
/** Confirmed-stop and finish bookkeeping is per incarnation or per assignment
 *  attempt, so a long session accumulates one entry each. Keep the same bounded
 *  FIFO shape the peer-delivery dedupe uses instead of growing without limit. */
const MAX_RUNTIME_BOOKKEEPING_ENTRIES = 512;

function rememberBounded<T>(entries: Map<string, T> | Set<string>, key: string, value?: T): void {
  if (entries instanceof Map) entries.set(key, value as T);
  else entries.add(key);
  for (const oldest of entries.keys()) {
    if (entries.size <= MAX_RUNTIME_BOOKKEEPING_ENTRIES) break;
    entries.delete(oldest);
  }
}
const closeFinalizations = new Map<string, Promise<void>>();

export function getConfirmedStopTime(spawnId: string): number | undefined {
  return confirmedStopTimes.get(spawnId);
}
/** Task ids under verification, bound to one exact submission via token so a
 *  release/re-claim or newer submission invalidates any older in-flight gate. */
const verifyingTasks = new Map<string, { worker: string; spawnId: string; assignmentId: string; submissionId: string; token: string }>();
/** In-flight gate reviewers by task id. Invalidating a holding's authority must
 *  also stop its reviewer child, not merely discard the verdict it returns. */
const verifyAborts = new Map<string, { controller: AbortController; submissionId: string }>();

/** Drop any in-flight gate for one task and stop its reviewer process. Every
 *  invalidation path uses this so Work authority and child processes cannot
 *  diverge. */
function invalidateVerifyGate(taskId: string): void {
  verifyingTasks.delete(taskId);
  const active = verifyAborts.get(taskId);
  if (!active) return;
  verifyAborts.delete(taskId);
  active.controller.abort();
}

/** Start one gate attempt, aborting any earlier reviewer for the same task. */
function runVerifyGate(
  intent: import("./types").TaskIntent,
  subject: string,
  submissionId: string,
  token: string,
  input: VerifyReviewInput,
): void {
  const previous = verifyAborts.get(intent.taskId);
  if (previous) {
    verifyAborts.delete(intent.taskId);
    previous.controller.abort();
  }
  const controller = new AbortController();
  verifyAborts.set(intent.taskId, { controller, submissionId });
  // A reviewer crash is a concrete failed gate. A missing verdict is handled
  // separately as inconclusive so prose-format drift cannot count as a defect.
  Promise.resolve()
    .then(() => verifyGateRunner({ ...input, signal: controller.signal }))
    .then((outcome) => resolveGateOutcome(intent, subject, submissionId, token, outcome))
    .catch((error) => resolveGateOutcome(intent, subject, submissionId, token, {
      kind: "fail",
      detail: truncated(`(completion review crashed) ${error instanceof Error ? error.message : String(error)}`),
    }));
}
type PendingSubmission = import("./types").TaskIntent & { assignmentId: string; verify: string | undefined };
/** Submitted Work waits for its authoring Worker to settle before a gate can
 * inspect its files. This applies to direct automatic and tasks submissions. */
const pendingSubmissions = new Map<string, PendingSubmission>();
/** Idle nudges already fired per teammate incarnation (one per transition). */
const idleNudgesSent = new Set<string>();
/** One finish entry per assignment attempt; repeated terminal reports stay ordinary report rows. */
const announcedFinishKeys = new Set<string>();
/** Consecutive verify failures per taskId:spawnId holder incarnation. */
const verifyFailures = new Map<string, VerifyFailureRecord>();
/** Self-finalize requests delivered per teammate incarnation before escalating to the leader. */
const selfFinalizeAttempts = new Set<string>();
const pendingDeliveries = new Map<string, InboxMessage[]>();
/** Role and first-input delivery are pinned per incarnation, never re-resolved
 * when a later send or first idle wake begins. */
const residentSequences = new Map<string, { rolePrompt: string; roleDelivered: boolean }>();
/** A correlated control receipt may arrive after result callbacks. Keep the
 * exact incarnation reserved until that receipt resolves. */
const pendingResidentInputs = new Set<string>();

// ── Lifecycle ─────────────────────────────────────────────────────

export interface MachineHooks {
  sendUpdate: (report: LeaderReport) => void;
  notifyChange: () => void;
}

export function initTeamMachine(
  ctx: Pick<ExtensionContext, "sessionManager" | "cwd" | "model" | "thinkingLevel">,
  hooks: MachineHooks,
): void {
  generation++;
  leaderCwd = ctx.cwd || process.cwd();
  leaderModelRef = () => (ctx.model ? modelLabel(ctx.model) : undefined);
  leaderThinkingLevelRef = () => ctx.thinkingLevel;
  const sessionFile = ctx.sessionManager?.getSessionFile();
  runtimeStateFile = stateFilePath(sessionFile, leaderCwd);
  tasksFile = tasksFilePath(sessionFile, leaderCwd);
  sendUpdate = hooks.sendUpdate;
  notifyChange = hooks.notifyChange;
  // The tasks and runtime dir are keyed per session, so two Leader processes
  // holding the same session would overwrite each other's single-writer state.
  // Detection is a report, not a block: the harness never takes ownership away
  // from a session the user may legitimately be resuming.
  claimLeaderLease();
  // Resume: reload a persisted tasks; claims die with their holders. A task set
  // that cannot be loaded is archived rather than silently discarded or allowed
  // to prevent extension reload.
  try {
    const persisted = readTasksFile(tasksFile);
    if (persisted) loadTasks(persisted.tasks);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    let preservation: string;
    try {
      const archived = `${tasksFile}.incompatible-${Date.now()}`;
      fs.renameSync(tasksFile, archived);
      preservation = `Archived preserved snapshot: ${archived}`;
    } catch {
      // An unusable agents directory must still not turn preservation into a
      // fatal startup error: report where the snapshot stayed instead.
      preservation = `The preserved snapshot could not be archived and stays in place: ${tasksFile}`;
    }
    deliverToLeader({ from: "harness", subject: "Incompatible Work snapshot", body: `${detail}\n${preservation}` });
  }
}

/** Re-bind the leader context closures after a mid-session model or
 *  thinking-level switch, so later spawns resolve against the current
 *  session configuration instead of the session_start snapshot. */
export function syncLeaderContext(
  ctx: Pick<ExtensionContext, "model" | "thinkingLevel">,
): void {
  leaderModelRef = () => (ctx.model ? modelLabel(ctx.model) : undefined);
  leaderThinkingLevelRef = () => ctx.thinkingLevel;
}

export function shutdownTeamMachine(): void {
  generation++;
  if (livePollTimer) clearInterval(livePollTimer);
  livePollTimer = undefined;
  runtimeStateFile = "";
  tasksFile = "";
  leaderCwd = "";
  leaderModelRef = () => undefined;
  leaderThinkingLevelRef = () => undefined;
  setVerifyGateRunner(undefined);
  sendUpdate = () => {};
  notifyChange = () => {};
  pendingShutdowns.clear();
  confirmedStopTimes.clear();
  closeFinalizations.clear();
  verifyingTasks.clear();
  for (const active of verifyAborts.values()) active.controller.abort();
  verifyAborts.clear();
  pendingSubmissions.clear();
  idleNudgesSent.clear();
  selfFinalizeAttempts.clear();
  pendingDeliveries.clear();
  residentSequences.clear();
  pendingResidentInputs.clear();
  verifyFailures.clear();
  inconclusiveParks.clear();
  verifyFailureParks.clear();
  unexpectedExecutionParks.clear();
  announcedFinishKeys.clear();
  snapshotFailure = undefined;
  writtenStateRevision = -1;
  writtenRosterRevision = -1;
  writtenTasksRevision = -1;
  writtenProgressRevision = -1;
  lastStateWriteAt = 0;
}

// ── Spawn model resolution ────────────────────────────────────

/** How a spawn's effective model was chosen. */
export type SpawnModelSource = "pin" | "inherit" | "team-default" | "leader-session" | "none";

/**
 * Resolve the effective spawn model. Precedence: explicit role pin beats the
 * `inherit` alias (the leader session's current model), which beats the team
 * default set from the console; if unset, falls back to the current session's
 * model; with none of these Pi picks its own default.
 * The value is resolved at spawn time so mid-session leader model switches
 * apply to later spawns.
 */
export function resolveSpawnModel(
  pinned: string | undefined,
  teamDefault: string | undefined,
  leaderModel: string | undefined,
): { model?: string; source: SpawnModelSource } {
  const pin = pinned?.trim();
  if (pin && pin.toLowerCase() !== MODEL_INHERIT_ALIAS) return { model: pin, source: "pin" };
  if (pin && leaderModel) return { model: leaderModel, source: "inherit" };
  const fallback = teamDefault?.trim();
  if (fallback) return { model: fallback, source: "team-default" };
  const currentLeader = leaderModel?.trim();
  if (currentLeader) return { model: currentLeader, source: "leader-session" };
  return { model: undefined, source: "none" };
}

/** The leader session's current model reference, when one is selected. */
export function currentLeaderModelRef(): string | undefined {
  const fromRef = leaderModelRef();
  if (fromRef) return fromRef;
  if (process.env.PI_PROVIDER && process.env.PI_MODEL) {
    return `${process.env.PI_PROVIDER}/${process.env.PI_MODEL}`;
  }
  return process.env.PI_MODEL;
}

/** The leader session's current thinking level, when one is selected. */
export function currentLeaderThinkingLevel(): LeaderThinkingLevel | undefined {
  const fromRef = leaderThinkingLevelRef();
  if (fromRef) return fromRef;
  const fromEnv = process.env.PI_REASONING_LEVEL?.trim();
  if (fromEnv && THINKING_LEVELS.includes(fromEnv as LeaderThinkingLevel)) {
    return fromEnv as LeaderThinkingLevel;
  }
  return undefined;
}

/** Terminate every resident teammate; returns unconfirmed-close diagnostics. */
export async function teardownAgents(): Promise<string[]> {
  // Session shutdown is an intentional lifecycle transition. Mark every
  // resident before signalling so close callbacks do not misclassify normal
  // session teardown as an unexpected crash and enqueue a follow-up turn.
  for (const teammate of livingAgents()) pendingShutdowns.add(teammate.name);
  const results = await terminateAllAgents();
  const diagnostics: string[] = [];
  for (const result of results) {
    if (!result.confirmedClosed) diagnostics.push(`Agent ${result.name} could not be confirmed closed.`);
    updateAgent(result.name, { status: "stopped" });
  }
  return diagnostics;
}

/** Remove the current session's runtime dir; the task set persists. */
export function removeRuntimeDir(ctx: Pick<ExtensionContext, "sessionManager" | "cwd">): void {
  removeSessionStateDir(ctx.sessionManager?.getSessionFile(), ctx.cwd || process.cwd());
}

function requireStateFile(): string {
  if (!runtimeStateFile) throw new Error("Agent Teams session state is unavailable.");
  return runtimeStateFile;
}

/** Directory of the current session's runtime files (for UI mail inspection). */
export function runtimeDirPath(): string {
  const file = runtimeStateFile;
  if (!file) return "";
  return file.slice(0, Math.max(file.lastIndexOf("/"), 0));
}

/** Consecutive snapshot writes that failed. The tick retries, so only a
 *  persistent failure (no successful write in this many attempts) is reported
 *  instead of being silently invisible. */
const SNAPSHOT_FAILURE_REPORT_AFTER = 3;
let snapshotFailure: { count: number; reported: boolean; detail: string } | undefined;
/** Revisions already on disk. -1 makes the first flush after a (re)init write
 *  every artifact. */
let writtenStateRevision = -1;
let writtenRosterRevision = -1;
let writtenTasksRevision = -1;
let writtenProgressRevision = -1;
let lastStateWriteAt = 0;
/** Roughly 2 poll ticks: the debug snapshot follows progress, but not per token. */
export const STATE_SNAPSHOT_MIN_INTERVAL_MS = 1_000;

/** Runtime dir that holds the leader lease for the current session. */
function leaderLockPath(stateFile: string): string {
  return path.join(path.dirname(stateFile), "leader.pid");
}

function isProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

/** Record this process as the session's Leader, warning when another live one
 *  still holds the same session. The lease dies with the runtime dir. */
function claimLeaderLease(): void {
  const lock = leaderLockPath(requireStateFile());
  let previous: number | undefined;
  try {
    const parsed = Number(fs.readFileSync(lock, "utf-8").trim());
    if (Number.isInteger(parsed) && parsed > 0 && parsed !== process.pid) previous = parsed;
  } catch {
    // No lease yet, or an unreadable one: this process takes it either way.
  }
  try {
    fs.mkdirSync(path.dirname(lock), { recursive: true, mode: 0o700 });
    fs.writeFileSync(lock, `${process.pid}\n`, { encoding: "utf-8", mode: 0o600 });
  } catch {
    return;
  }
  if (previous !== undefined && isProcessAlive(previous)) {
    deliverToLeader({
      from: "harness",
      subject: "Another Leader process shares this session",
      body: `Leader process ${previous} is still running for this session's Work directory. Two Leaders writing one session would overwrite each other's Work state; finish or stop the other Pi session (or confirm it exited) before editing Work here.`,
    });
  }
}

function flushSnapshots(): void {
  const stateFile = requireStateFile();
  const rosterRev = rosterRevision();
  const tasksRev = tasksRevision();
  const stateRev = stateRevision();
  const progressRev = progressRevision();
  const needsRoster = rosterRev !== writtenRosterRevision;
  const needsTasks = tasksRev !== writtenTasksRevision;
  // The whole-state file exists for forensics; nothing in the runtime reads it
  // back. It still tracks streamed progress, but at a bounded rate instead of
  // rewriting the state on every token.
  const needsState = stateRev !== writtenStateRevision
    || (progressRev !== writtenProgressRevision && Date.now() - lastStateWriteAt >= STATE_SNAPSHOT_MIN_INTERVAL_MS);
  if (!needsRoster && !needsTasks && !needsState) return;
  try {
    if (needsState) writeStateFile(stateFile, getState());
    if (needsRoster) {
      writeRoster(rosterPath(stateFile), livingAgents().map((t) => ({
        name: t.name,
        role: t.role,
        spawnId: t.spawnId,
        status: t.status,
        tools: t.tools,
        currentTaskId: t.currentTaskId,
        assignment: t.assignment,
      })));
    }
    if (needsTasks && tasksFile) writeTasksFile(tasksFile, getState().tasks);
    // Only a fully successful flush advances the revisions, so a failed write
    // stays dirty and the next poll retries it.
    if (needsState) {
      writtenStateRevision = stateRev;
      writtenProgressRevision = progressRev;
      lastStateWriteAt = Date.now();
    }
    if (needsRoster) writtenRosterRevision = rosterRev;
    if (needsTasks) writtenTasksRevision = tasksRev;
    snapshotFailure = undefined;
  } catch (error) {
    // The next poll retries. A transient failure stays quiet, but a persistent
    // one is surfaced once: durable Work state silently diverging from memory
    // is a decision the Leader must be able to make.
    const detail = error instanceof Error ? error.message : String(error);
    const count = (snapshotFailure?.count ?? 0) + 1;
    const alreadyReported = snapshotFailure?.reported ?? false;
    snapshotFailure = { count, reported: alreadyReported, detail };
    if (count >= SNAPSHOT_FAILURE_REPORT_AFTER && !alreadyReported) {
      snapshotFailure.reported = true;
      deliverToLeader({
        from: "harness",
        subject: "Work snapshot writes are failing",
        body: `The durable Work snapshot under ${path.dirname(stateFile)} has failed ${count} consecutive writes (${detail}). In-memory Work state is still authoritative for this session; the files on disk are stale. Check disk space and permissions before ending the session.`,
      });
    }
  }
}

export function publishStateSnapshot(): void {
  drainTeammateOutboxes();
  flushSnapshots();
}

export function ensureLivePoll(): void {
  const busy = livingAgents().length > 0 || verifyingTasks.size > 0 || pendingDeliveries.size > 0;
  if (busy && !livePollTimer && runtimeStateFile) {
    livePollTimer = setInterval(() => {
      try {
        tick();
      } catch {
        // Never let a poll error break the extension.
      }
    }, LIVE_POLL_MS);
  } else if (!busy && livePollTimer) {
    clearInterval(livePollTimer);
    livePollTimer = undefined;
  }
}

function tick(): void {
  drainTeammateOutboxes();
  processTaskIntents();
  routePeerInboxes();
  wakeIdleTeammates();
  flushSnapshots();
  ensureLivePoll();
  notifyChange();
}

// ── Spawning ──────────────────────────────────────────────────────

export function spawnAgent(input: {
  name: string;
  role: string;
  workId?: string;
  /** Internal binding of an existing Work Item, never exposed as a public field. */
  existingWorkId?: string;
  context?: ResidentSpawnOptions["context"];
  model?: string;
  prompt?: string;
  resources?: string[];
  verify?: string;
  handoffFrom?: string;
  /** Explicit invocation tools may narrow an existing role, never widen it. */
  tools?: string[];
  definition?: Omit<AgentDefinitionInput, "name" | "tools"> & {
    tools?: string[];
  };
}): { ok: true; agent: Agent; readiness?: Promise<string | undefined> } | { ok: false; error: string } {
  const stateFile = requireStateFile();
  const invalid = validateSpawnInput(input);
  if (invalid) return { ok: false, error: invalid };
  if (input.handoffFrom) {
    const predecessor = getAgent(input.handoffFrom);
    if (!predecessor) return { ok: false, error: `Cannot hand off from @${input.handoffFrom}: teammate not found.` };
    if (predecessor.status !== "stopped") {
      return { ok: false, error: `Cannot hand off from living @${input.handoffFrom}. Shut it down or wait for it to stop before spawning a successor.` };
    }
  }
  const existingWork = input.existingWorkId ? getState().tasks[input.existingWorkId] : undefined;
  if (input.existingWorkId && (!existingWork || existingWork.status !== "pending" || !taskDependenciesMet(existingWork))) {
    return { ok: false, error: `Work Item "${input.existingWorkId}" is not pending and claimable.` };
  }
  const resolved = resolveAgent(input.role, leaderCwd);
  // Reject tool ids the bare child could never grant before any side effect:
  // a silent --tools drop here is how reviewers end up blind mid-audit.
  const requestedTools = input.tools ?? (input.definition && inlineDefinitionApplies(resolved) ? input.definition.tools : resolved?.tools);
  if (resolved && input.tools !== undefined && !(input.definition && inlineDefinitionApplies(resolved))) {
    const widened = input.tools.filter(tool => !resolved.tools.includes(tool));
    if (widened.length > 0) return { ok: false, error: `Invocation cannot widen @${resolved.name}'s tool grant: ${widened.join(", ")}.` };
  }
  const unknownTools = unknownAgentTools(requestedTools, [
    ...AGENT_MEMORY_CAPABILITY_TOOLS,
    ...WORKER_CAPABILITY_TOOLS,
  ]);
  if (unknownTools.length > 0) return { ok: false, error: unknownAgentToolsError(unknownTools, WORKER_CAPABILITY_TOOLS) };
  let agent: AgentDefinition | undefined = resolved;
  if (input.definition && inlineDefinitionApplies(resolved)) {
    try {
      const generated = input.definition;
      const roleInput: AgentDefinitionInput = {
        name: input.role,
        description: generated.description,
        tools: requestedTools ?? [],
        model: generated.model,
        verify: generated.verify,
        prompt: generated.prompt,
      };
      agent = registerSessionAgent(roleInput);
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
  }
  if (!agent) return { ok: false, error: unknownAgentError(input.role, leaderCwd) };

  // Disk scope is the only durable identity declaration. Every disk role has
  // Memory; a session role cannot acquire it through an invocation flag.
  const durable = agent.scope !== "session";
  if (requestedTools?.some((tool) => AGENT_MEMORY_CAPABILITY_TOOLS.includes(tool)) && !durable) {
    return { ok: false, error: agentMemoryUnavailableError(agent.name) };
  }

  // Both packages contribute a worker extension to one child. `--extension` is
  // repeatable and `--no-extensions` still loads explicit paths, so neither
  // package has to know about the other; each declares its own capability tools.
  // The subagents contribution is conditional: loading its extension into a
  // child that has no memory folder would register nothing and advertise a tool
  // the child cannot use.
  const memoryEnabled = durable;
  const capabilityTools = [
    ...(memoryEnabled ? AGENT_MEMORY_CAPABILITY_TOOLS : []),
    ...WORKER_CAPABILITY_TOOLS,
  ];
  const workerExtensions = [
    STREAM_RECOVERY_EXTENSION_PATH,
    ...(memoryEnabled ? [SUBAGENT_EXTENSION_PATH] : []),
    WORKER_EXTENSION_PATH,
  ];
  const executionTools = requestedTools ?? agent.tools;
  const effectiveTools = resolveAgentTools(executionTools, capabilityTools);
  let workspace: AgentWorkspace | undefined;
  try {
    // Provision only data for an existing disk identity, never an agent.md.
    if (durable) workspace = ensureAgentWorkspace({ agentName: agent.name, cwd: leaderCwd });
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
  const workerCwd = workspace?.cwd ?? leaderCwd;
  const sessionDir = workspace?.sessionDir;
  const hasSavedSession = sessionDir && assertPrivateSessionFiles(sessionDir);

  const spawnId = randomUUID();
  const effectiveKickoff = buildSuccessorHandoff(input.prompt, input.handoffFrom);
  const directResources = input.existingWorkId
    ? existingWork!.resources
    : effectiveKickoff?.trim()
      ? resolveDirectResources(input.resources, input.handoffFrom)
      : [];
  const conflict = activeAssignmentConflict(directResources);
  if (conflict) {
    return { ok: false, error: `Direct assignment resources conflict with @${conflict.name}'s ${conflict.assignment?.kind} assignment "${conflict.assignment?.id}".` };
  }
  const registered = registerAgent(newTeammate(input, spawnId, workerCwd));
  if (!registered.ok) return { ok: false, error: registered.error };

  const spawnModel = resolveSpawnModel(input.model ?? agent.model, getTeamDefaultModel(), currentLeaderModelRef());
  // Record the grant before the first wake: a role derived without tools shows
  // its narrow capability-only allowlist right on the spawn surface.
  const assignment = directAssignment(effectiveKickoff, directResources, spawnId);
  if (assignment) {
    const directWork = input.existingWorkId
      ? bindTask(input.existingWorkId, input.name, assignment, { from: ["pending"] })
      : createBoundWork({
        id: getAgent(input.name)?.workId ?? `work:${spawnId}`,
        subject: effectiveKickoff ? messageTitle(effectiveKickoff) : "Direct work",
        description: effectiveKickoff,
        resources: directResources,
        verify: input.verify,
        holder: input.name,
        assignment,
      });
    if (!directWork.ok) {
      updateAgent(input.name, { status: "stopped" });
      return { ok: false, error: directWork.reason };
    }
  }
  residentSequences.set(spawnId, { rolePrompt: agent.prompt, roleDelivered: false });
  updateAgent(input.name, {
    scope: agent.scope,
    source: agent.source,
    projectCwd: leaderCwd,
    ...(workspace ? { workspacePath: workspace.workspacePath, sessionDir } : {}),
    model: spawnModel.model,
    context: input.context === undefined ? "fresh" : "fork",
    tools: effectiveTools,
    ...(assignment ? {} : { assignment }),
  });
  // Flush before the kickoff is written: a fast child must not read a stale
  // worker-readable roster missing its own entry or tool grant.
  publishStateSnapshot();

  // Settles from native control events, never a polling loop or a model turn.
  // Resolve failures as values so internal synchronous spawn callers cannot
  // produce an unhandled rejection when they do not await startup.
  let settleReadiness!: (error: string | undefined) => void;
  const readiness = new Promise<string | undefined>((resolve) => { settleReadiness = resolve; });
  pendingResidentInputs.add(spawnId);
  void readiness.then(() => { pendingResidentInputs.delete(spawnId); });
  const started = spawnResident({
    agentName: input.name,
    description: assignment ? `[agent-teams-assignment:${assignment.id}]\n` + buildKickoffPrompt(
      input.name,
      input.role,
      agent.prompt,
      effectiveKickoff,
    ) : undefined,
    model: spawnModel.model,
    thinking: currentLeaderThinkingLevel(),
    context: input.context,
    tools: executionTools,
    extensions: workerExtensions,
    capabilityTools,
    cwd: workerCwd,
    session: durable ? (hasSavedSession ? "resume" : "persist") : "none",
    ...(sessionDir ? { sessionDir } : {}),
    // Both kinds launch in the original project. Scratch is data, not a new
    // trusted checkout; do not force project approval merely for durability.
    env: teammateEnv(stateFile, input, spawnId, agent, effectiveTools),
    onUpdate: (progress) => {
      applyProgress(input.name, spawnId, progress);
      if (!assignment) {
        if (progress.controlError) settleReadiness(progress.controlError);
        else if (progress.ready) settleReadiness(undefined);
      }
    },
    onError: (error) => {
      settleReadiness(`Resident startup readiness failed: ${error.message}`);
      if (getAgent(input.name)?.spawnId !== spawnId) return;
      if (input.existingWorkId) revertUndeliveredTake(input.existingWorkId, input.name, `Agent failed to start: ${error.message}`);
      failSpawn(input.name, error.message, input.existingWorkId);
    },
    onExit: (result) => {
      settleReadiness("Resident exited before startup readiness was acknowledged.");
      closeFinalizations.set(spawnId, handleTeammateClose(input.name, spawnId, result));
    },
  });
  if ("error" in started) {
    settleReadiness(started.error);
    if (input.existingWorkId) revertUndeliveredTake(input.existingWorkId, input.name, `Agent failed to start: ${started.error}`);
    else if (assignment) discardTask(getAgent(input.name)?.workId ?? `work:${spawnId}`, input.name);
    failSpawn(input.name, started.error, input.existingWorkId);
    return { ok: false, error: started.error };
  }
  updateAgent(input.name, { pid: started.pid, envPolicy: started.envPolicy });
  if (assignment) {
    // Attach both outcomes immediately, even for synchronous internal callers.
    // A writable pipe proves neither accepted input nor completed execution.
    const rejectInput = (error: string) => {
      if (getAgent(input.name)?.spawnId === spawnId) updateAgent(input.name, { error });
      settleReadiness(error);
    };
    if (!started.accepted) rejectInput("Resident kickoff input acknowledgement is unavailable.");
    else void started.accepted.then((accepted) => {
      const current = getAgent(input.name);
      if (!accepted) rejectInput("Resident kickoff input was not accepted. Inspect or stop before retrying.");
      else if (!current || current.spawnId !== spawnId || current.status === "stopped") {
        rejectInput("Resident exited or was replaced before kickoff input was acknowledged.");
      } else {
        // A fast result may settle before the RPC response. Do not revive it.
        if (current.status === "starting") updateAgent(input.name, { status: "working" });
        const sequence = residentSequences.get(spawnId);
        if (sequence) sequence.roleDelivered = true;
        settleReadiness(undefined);
      }
    }).catch((error) => rejectInput(error instanceof Error ? error.message : String(error)));
  }
  const contextWorkId = getAgent(input.name)?.workId;
  if (contextWorkId && workspace) setTaskContext(contextWorkId, { workspacePath: workspace.workspacePath });
  // Keep starting until native readiness or accepted kickoff input; settlement
  // leaves both temporary and durable incarnations idle, never closed.
  publishStateSnapshot();
  ensureLivePoll();
  notifyChange();
  return { ok: true, agent: getAgent(input.name)!, readiness };
}

/** True when a spawn's inline definition should create or replace the role:
 *  nothing resolved, or only a session-scoped generated role did. Filesystem
 *  scopes are user-owned and always win over inline input.
 *
 *  Owned by `@fradser/pi-subagents` and re-exported here, because the standalone
 *  spawner has to answer the same question. Two copies of this rule is how the
 *  two spawn paths came to disagree about which role a child received. */
export { inlineDefinitionApplies };

/** A session role has no durable Memory capability to contribute. */
export function agentMemoryUnavailableError(name: string): string {
  return `Temporary Agent "${name}" has no Agent Memory. Remove ${AGENT_MEMORY_CAPABILITY_TOOLS.join(" and ")} from its tools; durable Memory belongs only to a user-authored disk agent.md.`;
}

/** Spawn failure for execution-tool ids outside the teammate universe.
 *
 *  Re-exported from `@fradser/pi-subagents`, which owns the universe and the
 *  message beside it: the standalone spawner refuses the same ids for the same
 *  reason, and a second copy of this text is a second copy to drift. */
export { unknownAgentToolsError };

/** Spawn failure for an unresolvable agent name. Definitions resolve live at
 *  spawn time, so the available-agents list in the cached session guidance can
 *  go stale (e.g. another session removed the file); name every checked scope
 *  and the recovery path. */
export function unknownAgentError(name: string, cwd: string): string {
  const available = [...discoverAgents(cwd).keys()];
  return [
    `Agent "${name}" not found in any scope.`,
    `Checked: ${cwd}/.pi/agents/<name>.local/agent.md, ${cwd}/.pi/agents/<name>/agent.md, ${path.join(getAgentDir(), "agents", "<name>", "agent.md")}, and in-memory session roles.`,
    'The available-agents list in your guidance may be stale: definition files can change mid-session (for example removed by a parallel session).',
    'Recover with agent action=start using an existing name, or supply description and role_prompt derived from references/agent-roles.md for a temporary role.',
    `Available now: ${available.length > 0 ? available.join(", ") : "(none)"}.`,
  ].join(' ');
}

function validateSpawnInput(input: { name: string }): string | undefined {
  if (!isValidAgentName(input.name)) {
    return `Invalid teammate name "${input.name}". Use letters, digits, dots, dashes, underscores.`;
  }
  if (livingAgents().some((t) => t.name === input.name)) {
    return `A living teammate named "${input.name}" already exists.`;
  }
  return undefined;
}

function newTeammate(
  input: { name: string; role: string; workId?: string },

  spawnId: string,
  workerCwd: string,
): Agent {
  return {
    name: input.name,
    role: input.role,
    spawnId,
    workId: input.workId,
    pid: 0,
    status: "starting",
    cwd: workerCwd,
    turns: 0,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    lastOutputAt: Date.now(),
  };
}

export function directAssignment(
  kickoff: string | undefined,
  resources: string[],
  spawnId: string,
): WorkerAssignment | undefined {
  if (!kickoff?.trim()) return undefined;
  return {
    id: `direct:${spawnId}`,
    kind: "direct",
    resources,
  };
}

export function resolveDirectResources(resources: string[] | undefined, handoffFrom: string | undefined): string[] {
  const explicit = normalizeResources(resources);
  if (explicit.length > 0) return explicit;
  const prior = handoffFrom ? getAgent(handoffFrom) : undefined;
  return normalizeResources(prior?.assignment?.resources ?? prior?.lastAssignment?.resources);
}

export function buildSuccessorHandoff(kickoff: string | undefined, handoffFrom: string | undefined): string | undefined {
  if (!handoffFrom?.trim()) return kickoff;
  const prior = getAgent(handoffFrom);
  const reports = getState().leaderMailbox
    .filter((message) => message.from === handoffFrom)
    .slice(-3)
    .map((message) => `${message.subject}: ${truncated(message.body, 1000)}`);
  const assignment = prior?.assignment ?? prior?.lastAssignment;
  const taskId = prior?.currentTaskId ?? prior?.lastTaskId;
  // A structured brief rather than concatenated prose. @fradser/pi-tasks owns the shape, so
  // a successor handoff, a recheck, and a standalone tasks all produce the same
  // sections, and an oversized brief is clipped and marked instead of silently
  // truncated. Prior reports go in `priorFindings` deliberately: that is the field
  // a recheck must not lose when a reopen clears the result.
  const { handoff } = buildTaskHandoff({
    candidate: prior?.cwd ? `workspace ${prior.cwd}` : undefined,
    delta: assignment ? `${assignment.kind} ${assignment.id}` : "assignment unavailable",
    verification: taskId ? `prior tasks claim ${taskId}` : "no prior tasks claim",
    priorFindings: reports.length > 0 ? reports : undefined,
    outstanding: [
      "Verify current files yourself; do not claim the predecessor's tasks Work unless the leader explicitly assigns it.",
    ],
  });
  const brief = [
    `=== SUCCESSOR HANDOFF FROM @${handoffFrom} ===`,
    formatTaskHandoff(handoff),
  ].filter(Boolean).join("\n");
  return [kickoff?.trim(), brief].filter(Boolean).join("\n\n");
}

function teammateEnv(
  stateFile: string,
  input: { name: string; role: string },
  spawnId: string,
  definition: AgentDefinition,
  tools: readonly string[],
): Record<string, string | undefined> {
  return {
    PI_TEAMMATE_WORKER_NAME: input.name,
    PI_TEAMMATE_SPAWN_ID: spawnId,
    PI_TEAMMATE_OUTBOX_FILE: workerOutboxPath(stateFile, input.name, spawnId),
    PI_TEAMMATE_INBOX_FILE: inboxPath(stateFile, input.name),
    PI_TEAMMATE_ROSTER_FILE: rosterPath(stateFile),
    PI_TEAMMATE_TASKS_FILE: tasksFile,
    PI_TEAMMATE_CLAIMS_DIR: claimsDir(taskDirectory()),
    PI_TEAMMATE_SUBMISSIONS_DIR: submissionsDir(taskDirectory()),
    PI_TEAMMATE_ROLE_AGENT: input.role,
    // The tasks's own binding, named by the tasks. `PI_TEAMMATE_WORKER_NAME` is
    // this package's private vocabulary; a child that read it to decide who it is
    // on the tasks would couple the tasks to this package's naming.
    [TASK_HOLDER_ENV]: input.name,
    PI_TEAMMATE_VERIFY_DEFAULT: definition.verify ?? "",
    // The subagent worker extension reads these. Named for that package rather
    // than reusing PI_TEAMMATE_*, so the execution layer never has to learn this
    // package's vocabulary.
    ...(definition.scope !== "session" ? {
      [SUBAGENT_ROLE_ENV]: definition.name,
      [SUBAGENT_TOOLS_ENV]: tools.join(","),
      [SUBAGENT_DEFINITION_ENV]: definition.source,
      [SUBAGENT_SCOPE_ENV]: definition.scope,
    } : {}),
    PI_SUBAGENT_PROJECT_CWD: leaderCwd,
  };
}

export function buildKickoffPrompt(
  name: string,
  agentName: string,
  rolePrompt: string,
  kickoff: string | undefined,
): string {
  const header = [
    `You are a FULLY AUTONOMOUS resident agent named "${name}" (role: ${agentName}) in a pi multi-agent team.`,
    "You stay alive between tasks. The harness wakes you with new prompts when",
    "messages arrive for you or when the task set has unclaimed work.",
    `Original project: ${leaderCwd}. A private scratch cwd is not a checkout; project edits change the original working tree directly.`,
  ].filter(Boolean).join(" ");
  // A role may state a purpose without instructions, so an empty body is said
  // rather than printed as a heading with nothing under it — a child told "ROLE
  // PROMPT (x) ===" and nothing else cannot tell whether it was given a role.
  const roleSection = rolePrompt.trim()
    ? `=== ROLE PROMPT (${agentName}) ===\n${rolePrompt.trim()}`
    : `=== ROLE (${agentName}) ===\nThis role states what you are for and carries no standing instructions. Take the task below as it comes.`;
  const taskSection = kickoff?.trim()
    ? `=== KICKOFF TASK ===\n${kickoff.trim()}\n\nExecute this assigned task directly; this task text is the whole assignment, so use task tools only when the assignment requires them.`
    : "=== KICKOFF TASK ===\n(none yet — list the tasks with task action=list and take one with task update status=in_progress)";
  return `${header}\n\n${roleSection}\n\n${taskSection}`;
}

function buildFreshAssignmentPrompt(teammate: Agent, assignmentId: string, task: string): string {
  return `[agent-teams-assignment:${assignmentId}]\n${buildKickoffPrompt(
    teammate.name,
    teammate.role,
    residentSequences.get(teammate.spawnId)?.rolePrompt ?? resolveAgent(teammate.role, leaderCwd)?.prompt ?? "",
    task,
  )}`;
}

function taskDirectory(): string {
  return path.dirname(tasksFile);
}

export function applyProgress(name: string, spawnId: string, progress: {
  text: string;
  activeTool?: string;
  liveThinking?: string;
  turns: number;
  finalResponse?: boolean;
  modelOutputSeen?: boolean;
  ready?: boolean;
  usage?: AgentUsage;
  controlError?: string;
}): void {
  const teammate = getAgent(name);
  // A stale callback from an older incarnation must not touch the current one.
  if (!teammate || teammate.spawnId !== spawnId || teammate.status === "stopped") return;
  if (progress.controlError) {
    updateAgent(name, { error: progress.controlError });
    deliverDiagnostic(name, progress.controlError);
    sendUpdate({ agent: name, spawnId, body: progress.controlError, origin: "harness", harnessEvent: { type: "control-rejected", subject: `@${name} control rejected` }, finished: false });
  }
  updateAgentProgress(name, teammate.spawnId, {
    liveText: progress.text,
    activeTool: progress.activeTool,
    liveThinking: progress.liveThinking,
    turns: progress.turns,
    sequenceEnded: progress.finalResponse,
    modelOutputSeen: progress.modelOutputSeen,
    usage: progress.usage,
  });
  updateAgent(name, { lastOutputAt: Date.now(), ...(progress.finalResponse === false ? { status: "working" } : {}) });
  if (progress.finalResponse === false && teammate.currentTaskId && verifyingTasks.has(teammate.currentTaskId)) {
    const holding = `${teammate.currentTaskId}:${spawnId}`;
    invalidateVerifyGate(teammate.currentTaskId);
    unexpectedExecutionParks.add(holding);
    sendUpdate({
      agent: name,
      spawnId,
      origin: "harness",
      harnessEvent: { type: "review-invalidated", subject: `Verification invalidated · ${getTask(teammate.currentTaskId)?.subject ?? "Work"}` },
      body: `Observed new execution for @${name} while verification was in flight. The review was invalidated; Work "${teammate.currentTaskId}" remains held until explicit leader direction authorizes a revision.`,
      finished: false,
    });
  }
  if (progress.finalResponse && teammate.status !== "idle") {
    updateAgent(name, { status: "idle", activeTool: undefined });
    drainTeammateOutboxes(name);
    processTaskIntents();
    const pending = pendingSubmissions.get(name);
    if (pending?.spawnId === spawnId && getAgent(name)?.assignment?.id === pending.assignmentId) {
      pendingSubmissions.delete(name);
      archiveDeferredDeliveries(getAgent(name)!);
      beginVerifyOrComplete(pending, pending.verify);
    }
    nudgeIfUnfinalized(name, spawnId);
  }
  if (progress.ready || progress.controlError) {
    publishStateSnapshot();
    notifyChange();
  }
  ensureLivePoll();
}

interface VerifyFailureRecord {
  count: number;
  escalated: boolean;
}

/** One verdict-only retry per exact verify submission. */
const inconclusiveVerifications = new Map<string, number>();
/** Two inconclusive reviews park a holding until explicit Work recovery. */
const inconclusiveParks = new Map<string, { worker: string; spawnId: string }>();
/** Repeated verify failures retain authority until explicit Work recovery. */
const verifyFailureParks = new Map<string, { worker: string; spawnId: string }>();
/** Owner execution observed during review; explicit Leader recovery is required. */
const unexpectedExecutionParks = new Set<string>();

type FinishIdentity = Pick<LeaderReport, "agent" | "spawnId" | "assignmentId" | "finished">;

function finishKey(report: FinishIdentity): string {
  return `${report.agent ?? "agent"}:${report.spawnId ?? "session"}:${report.assignmentId ?? "unassigned"}`;
}

/** Announce each assignment attempt once, including later work in the same process. */
export function markTeammateFinished(report: FinishIdentity): boolean {
  if (!report.finished) return false;
  const key = finishKey(report);
  if (announcedFinishKeys.has(key)) return false;
  rememberBounded(announcedFinishKeys, key);
  return true;
}

/** Only an open current assignment can owe a final result. */
export function hasUnfinalizedReport(name: string): boolean {
  const teammate = getAgent(name);
  return Boolean(teammate?.assignment && !teammate.assignment.closed
    && !teammate.reportSequenceEnded && !verificationFrozen(teammate));
}

/** One light reminder per idle transition when work looks unfinished. */
function nudgeIfUnfinalized(name: string, spawnId: string): void {
  if (!hasUnfinalizedReport(name)) return;
  const key = `${name}:${spawnId}:${getAgent(name)?.assignment?.id}`;
  if (!selfFinalizeAttempts.has(key)) {
    // First miss: give the worker one chance to fix its own bookkeeping
    // before bothering the leader. The inbox message wakes it on the next tick.
    selfFinalizeAttempts.add(key);
    deliverFeedback(
      name,
      "Assignment not finalized",
      `Current assignment "${getAgent(name)?.assignment?.id ?? "unassigned"}" has no automatic final result yet. Return a final answer or submit the current Work outcome.`,
    );
    return;
  }
  if (idleNudgesSent.has(key)) return;
  idleNudgesSent.add(key);
  const reminder = `@${name} is idle but current assignment "${getAgent(name)?.assignment?.id ?? "unassigned"}" has no terminal report after one finalization request. Decide whether to resume or release the assignment.`;
  deliverToLeader({ from: "harness", subject: `Idle without terminal report: @${name}`, body: reminder });
  sendUpdate({
    agent: name,
    body: reminder,
    origin: "harness",
    harnessEvent: { type: "unfinalized-report", subject: `@${name} idle without terminal report` },
    finished: false,
  });
}

function failSpawn(name: string, error: string, existingWorkId?: string): void {
  const teammate = getAgent(name);
  if (!existingWorkId && teammate?.assignment?.kind === "direct" && teammate.currentTaskId) {
    discardTask(teammate.currentTaskId, name);
  } else {
    failTasksHeldBy(name, `Agent failed to start: ${error}`);
  }
  updateAgent(name, { status: "stopped", error });
  if (teammate) {
    residentSequences.delete(teammate.spawnId);
    clearWorkerRunEvents(name, teammate.spawnId);
    removeWorkerOutbox(requireStateFile(), name, teammate.spawnId);
  }
  deliverToLeader({
    from: name,
    subject: "Agent failed to start",
    body: `Agent @${name} could not start.\nError: ${error}`,
  });
  publishStateSnapshot();
  notifyChange();
}

// ── Shutdown and close ────────────────────────────────────────────

export async function shutdownAgentExact(name: string, spawnId: string): Promise<{ ok: true; body: string } | { ok: false; error: string }> {
  const existing = getAgent(name);
  if (!existing || existing.spawnId !== spawnId || existing.status === "stopped") {
    return { ok: false, error: `No living session named "${exactSessionRoute(name, spawnId)}".` };
  }
  return shutdownAgent(name);
}

export async function shutdownAgent(name: string): Promise<{ ok: true; body: string } | { ok: false; error: string }> {
  const teammate = getAgent(name);
  if (!teammate || teammate.status === "stopped") return { ok: false, error: `No living teammate named "${name}".` };
  pendingShutdowns.add(name);
  const terminated = await terminateAgent(name);
  if (terminated.outcome === "unconfirmed") {
    return { ok: false, error: `Agent @${name} could not be confirmed closed; shutdown remains pending.` };
  }
  if (terminated.outcome === "missing" && !confirmedStopTimes.has(teammate.spawnId)) {
    rememberBounded(confirmedStopTimes, teammate.spawnId, Date.now());
    // The child was already gone; synthesize the close bookkeeping.
    pendingShutdowns.delete(name);
    const released = failTasksHeldBy(name, "Agent was stopped.");
    for (const task of released) {
      clearInconclusiveForHolding(task.id, teammate.spawnId);
      invalidateVerifyGate(task.id);
      rearmTaskNotice(task.id);
    }
    updateAgent(name, { status: "stopped", activeTool: undefined });
    pendingDeliveries.delete(name);
    residentSequences.delete(teammate.spawnId);
    idleNudgesSent.delete(`${name}:${teammate.spawnId}`);
    selfFinalizeAttempts.delete(`${name}:${teammate.spawnId}`);
    // No close event will fire for an already-gone child, so this branch is
    // the only chance to put the shutdown summary on the delivery channel.
    const summary = summarizeShutdown(name, released.length, 0, undefined);
    deliverToLeader({ from: name, subject: "Agent stopped", body: summary });
    publishStateSnapshot();
    notifyChange();
    return { ok: true, body: summary };
  }
  await closeFinalizations.get(teammate.spawnId);
  return { ok: true, body: `Agent @${name} stopped.` };
}

async function handleTeammateClose(name: string, spawnId: string, result: AgentProcessResult): Promise<void> {
  if (!runtimeStateFile) return;
  const teammate = getAgent(name);
  if (!teammate || teammate.spawnId !== spawnId || teammate.status === "stopped") return;
  rememberBounded(confirmedStopTimes, spawnId, Date.now());
  const requested = pendingShutdowns.has(name);
  const crashed = !requested && !isCleanExit(result);

  // Drain final reports before tearing down replay metadata so nothing
  // written before close is lost.
  drainTeammateOutboxes();

  // A clean idle close with no outstanding result is a lifecycle fact, not a
  // failed assignment. Keep it visible without starting another leader turn.
  const cleanIdleClose = !crashed && teammate.status === "idle"
    && !hasUnfinalizedReport(name) && !verificationFrozen(teammate)
    && !pendingSubmissions.has(name) && !pendingResidentInputs.has(spawnId)
    && !pendingDeliveries.has(name) && !hasUnreadPeerMail(teammate);
  const released = failTasksHeldBy(name, requested ? "Agent was stopped." : "Agent stopped unexpectedly.");
  for (const task of released) {
    clearInconclusiveForHolding(task.id, teammate.spawnId);
    invalidateVerifyGate(task.id);
    rearmTaskNotice(task.id);
  }
  pendingShutdowns.delete(name);
  // A stopped teammate must not keep the poll loop or its queue alive.
  pendingSubmissions.delete(name);
  pendingDeliveries.delete(name);
  residentSequences.delete(spawnId);
  idleNudgesSent.delete(`${name}:${teammate.spawnId}`);
  selfFinalizeAttempts.delete(`${name}:${teammate.spawnId}`);
  updateAgent(name, {
    status: "stopped",
    activeTool: undefined,
    error: requested ? undefined : closeErrorText(result, crashed),
  });
  clearWorkerRunEvents(name, teammate.spawnId);
  removeWorkerOutbox(requireStateFile(), name, teammate.spawnId);

  if (requested || (cleanIdleClose && released.length === 0)) {
    const summary = summarizeShutdown(name, released.length, result.exitCode, result.usage);
    deliverToLeader({ from: name, subject: "Agent stopped", body: summary });
    // Requested stops and clean idle closure need no additional leader turn.
  } else {
    deliverToLeader({ from: name, subject: "Agent stopped unexpectedly", body: crashDiagnostic(name, result, released) });
    const closeReport = {
      agent: name,
      spawnId: teammate.spawnId,
      body: `@${name} stopped unexpectedly${released.length > 0 ? `; claimed task(s) ${released.map((t) => t.id).join(", ")} returned to the tasks` : ""}.`,
      origin: "harness" as const,
      harnessEvent: { type: "unexpected-stop", subject: `@${name} stopped unexpectedly` },
      finished: false,
    };
    sendUpdate(closeReport);
  }
  publishStateSnapshot();
  ensureLivePoll();
  notifyChange();
}

function closeErrorText(result: AgentProcessResult, crashed: boolean): string | undefined {
  if (!crashed) return undefined;
  return `Closed unexpectedly (code ${result.exitCode ?? "unknown"}${result.signal ? `, signal ${result.signal}` : ""}).`;
}

function crashDiagnostic(name: string, result: AgentProcessResult, released: Array<{ id: string }>): string {
  return [
    `Agent @${name} closed without a shutdown request.`,
    result.stderr?.trim() ? `stderr: ${result.stderr.trim()}` : undefined,
    released.length > 0 ? `Released claimed task(s): ${released.map((t) => t.id).join(", ")}.` : undefined,
    result.stdout?.trim() ? `Last output: ${result.stdout.trim()}` : undefined,
  ].filter(Boolean).join("\n");
}

function summarizeShutdown(
  name: string,
  releasedCount: number,
  exitCode: number | null | undefined,
  usage?: import("./types").AgentUsage,
): string {
  const lines = [`Agent @${name} stopped (exit code ${exitCode ?? "unknown"}).`];
  if (releasedCount > 0) lines.push(`Released claimed task(s): ${releasedCount}.`);
  if (usage) lines.push(`Lifetime usage: ${usage.totalTokens} tokens, $${usage.cost.toFixed(4)}.`);
  return lines.join("\n");
}

// ── Report outbox draining ────────────────────────────────────────

/** Poll one batch per worker; explicit control drains its recipient's existing snapshot. */
export function drainTeammateOutboxes(recipient?: string): void {
  const stateFile = requireStateFile();
  for (const teammate of livingAgents()) {
    const key = `${teammate.name}:${teammate.spawnId}`;
    const file = workerOutboxPath(stateFile, teammate.name, teammate.spawnId);
    const endOffset = teammate.name === recipient ? fs.statSync(file, { throwIfNoEntry: false })?.size ?? 0 : undefined;
    const offsets = getState().workerEventOffsets;
    while (true) {
      const previousOffset = offsets[key] ?? 0;
      const { records, nextOffset, diagnostics } = readJsonlBatch(file, previousOffset, endOffset);
      if (nextOffset !== previousOffset) {
        offsets[key] = nextOffset;
      }
      for (const diagnostic of diagnostics) deliverDiagnostic(teammate.name, diagnostic);
      for (const record of records) {
        applyOutboxRecord(teammate, record);
      }
      if (endOffset === undefined || nextOffset >= endOffset || nextOffset <= previousOffset) break;
    }
  }
}

function deliverDiagnostic(from: string, detail: string): void {
  deliverToLeader({ from, subject: "Agent channel diagnostic", body: detail });
}

function applyOutboxRecord(teammate: Agent, record: unknown): boolean {
  if (!isWorkerEvent(record)) return false;
  if (record.worker !== teammate.name || record.spawnId !== teammate.spawnId) return false;
  const ids = getState().workerEventIds;
  const eventKey = `${teammate.spawnId}:${record.id}`;
  if (ids[eventKey]) return false;
  ids[eventKey] = teammate.spawnId;

  const reportAssignmentId = teammate.assignment?.id ?? teammate.lastAssignment?.id;
  if (record.assignmentId !== reportAssignmentId || teammate.reportSequenceEnded) return false;
  const archived = pendingShutdowns.has(teammate.name);
  const status = record.status;
  if (status === "completed" || status === "failed") {
    const taskId = teammate.currentTaskId;
    const task = taskId ? getTask(taskId) : undefined;
    if (teammate.assignment && taskId && task?.claimedBy === teammate.name
      && (task.status === "in_progress" || task.status === "superseded")) {
      applySubmissionMarker({
        taskId, participant: teammate.name, spawnId: teammate.spawnId, assignmentId: teammate.assignment.id,
        status, result: record.body, timestamp: record.timestamp ?? Date.now(),
      });
    } else {
      receiveWorkerMessage(record, { archived: true });
    }
    return true;
  }
  receiveWorkerMessage({
    id: record.id,
    type: "message",
    worker: teammate.name,
    spawnId: teammate.spawnId,
    assignmentId: record.assignmentId,
    body: record.body,
    status: record.status,
    timestamp: record.timestamp,
  }, { archived });
  // Informational events carry no Work acceptance authority.
  const report = {
    agent: teammate.name,
    role: teammate.role,
    spawnId: teammate.spawnId,
    body: record.body,
    origin: "agent" as const,
    eventId: record.id,
    assignmentId: record.assignmentId,
    ...(teammate.inputId ? { inputId: teammate.inputId } : {}),
    workId: teammate.workId,
    status: record.status,
    timestamp: record.timestamp ?? Date.now(),
    finished: false,
    ...(archived ? { archived: true } : {}),
  };
  if (!archived) sendUpdate(report);
  return true;
}

// ── Peer inbox routing ────────────────────────────────────────────

/**
 * Route new inbox messages. Idle agents get the content queued for their
 * next wake-up; working agents receive it immediately through their
 * control stream (falling back to queueing when the stream is unavailable).
 */
export function routePeerInboxes(): void {
  const stateFile = requireStateFile();
  for (const teammate of livingAgents()) {
    if (pendingShutdowns.has(teammate.name)) continue;
    const inboxName = teammate.name;
    const inbox = inboxPath(stateFile, inboxName);
    const offset = getPeerInboxOffset(inboxName);
    const { records, nextOffset } = readJsonlBatch(inbox, offset);
    if (nextOffset === offset) {
      continueMaybeCompact(inbox, inboxName, offset);
      continue;
    }
    setPeerInboxOffset(inboxName, nextOffset);
    for (const record of records) {
      const message = parseInboxMessage(record);
      if (!message || isPeerDelivered(inboxName, message.id)) continue;
      markPeerDelivered(inboxName, message.id);
      // Mail addressed to an earlier incarnation is not this resident's to read.
      // Dropping it is recorded once so a replacement never inherits stale
      // intent, and the sender — never the leader's context — is told.
      if (message.toSpawnId && message.toSpawnId !== teammate.spawnId) {
        setPeerDeliveryState(message.id, "dropped");
        deliverFeedback(
          message.from,
          "Message not delivered",
          `Your message "${message.subject}" was addressed to an earlier incarnation of @${inboxName} that is no longer running, so it was not delivered. Re-resolve the recipient and send it again.`,
        );
        continue;
      }
      dispatchInboxMessage(teammate, message);
    }
  }
}

/** Inspect unread mail without routing it or changing delivery evidence. */
function hasUnreadPeerMail(teammate: Agent): boolean {
  const inbox = inboxPath(requireStateFile(), teammate.name);
  let endOffset: number;
  try {
    endOffset = fs.statSync(inbox, { throwIfNoEntry: false })?.size ?? 0;
  } catch {
    // An unreadable inbox cannot establish that this child owes no input.
    return true;
  }
  let offset = getPeerInboxOffset(teammate.name);
  if (offset > endOffset) offset = 0;
  while (offset < endOffset) {
    const batch = readJsonlBatch(inbox, offset, endOffset);
    if (batch.diagnostics.length || batch.nextOffset <= offset) return true;
    for (const record of batch.records) {
      const message = parseInboxMessage(record);
      if (!message) return true;
      if (!isPeerDelivered(teammate.name, message.id)
        && (!message.toSpawnId || message.toSpawnId === teammate.spawnId)) return true;
    }
    offset = batch.nextOffset;
  }
  return false;
}

function parseInboxMessage(record: unknown): InboxMessage | undefined {
  if (!record || typeof record !== "object") return undefined;
  const candidate = record as Partial<InboxMessage>;
  if (typeof candidate.id !== "string" || typeof candidate.from !== "string") return undefined;
  if (typeof candidate.subject !== "string" || typeof candidate.body !== "string") return undefined;
  if (candidate.toSpawnId !== undefined && typeof candidate.toSpawnId !== "string") return undefined;
  return { ...candidate, timestamp: candidate.timestamp ?? Date.now() } as InboxMessage;
}

function submissionPending(teammate: Agent): boolean {
  const pending = pendingSubmissions.get(teammate.name);
  if (pending?.spawnId === teammate.spawnId && pending.assignmentId === teammate.assignment?.id) return true;
  const task = teammate.currentTaskId ? getState().tasks[teammate.currentTaskId] : undefined;
  return teammate.assignment?.kind === "direct" && teammate.assignment.closed === true
    && task?.status === "in_progress" && task.claimedBy === teammate.name;
}

function gateInFlight(teammate: Agent): boolean {
  return teammate.currentTaskId !== undefined && verifyingTasks.has(teammate.currentTaskId);
}

function verificationFrozen(teammate: Agent): boolean {
  const taskId = teammate.currentTaskId;
  if (!taskId) return false;
  const holding = `${taskId}:${teammate.spawnId}`;
  return submissionPending(teammate) || gateInFlight(teammate) || verifyFailureParks.has(holding) || unexpectedExecutionParks.has(holding) || inconclusiveParks.has(holding);
}

/** Deferred deliveries archived when an accepted result closed the Task they
 *  were waiting behind. Leader-side, not on the task: a peer message is a
 *  coordination record, and the task store states what must be done rather than what
 *  was said about it. Bounded per Task because nothing ever reads the whole
 *  archive. */
const archivedDeliveries = new Map<string, Array<{ from: string; subject: string; body: string; timestamp: number }>>();

function archiveDeferredDeliveries(teammate: Agent): void {
  const deliveries = pendingDeliveries.get(teammate.name) ?? [];
  if (deliveries.length === 0) return;
  pendingDeliveries.delete(teammate.name);
  const taskId = teammate.currentTaskId;
  if (taskId) {
    const archived = archivedDeliveries.get(taskId) ?? [];
    archived.push(...deliveries.map(({ from, subject, body, timestamp }) => ({ from, subject, body, timestamp })));
    archivedDeliveries.set(taskId, archived.slice(-20));
    markTasksChanged();
  }
  for (const delivery of deliveries) setPeerDeliveryState(delivery.id, "routed");
}

function dispatchInboxMessage(teammate: Agent, message: InboxMessage): void {
  if (verificationFrozen(teammate)) {
    setPeerDeliveryState(message.id, "queued");
    const queued = pendingDeliveries.get(teammate.name) ?? [];
    queued.push(message);
    pendingDeliveries.set(teammate.name, queued);
    ensureLivePoll();
    return;
  }
  const marker = teammate.assignment ? `[agent-teams-assignment:${teammate.assignment.id}]\n` : "";
  const routed = !teammate.reportSequenceEnded && (
    teammate.status === "working"
    || teammate.status === "starting"
    || isFreshAssignmentPending(teammate.name)
  )
    ? sendAgentFollowUp(teammate.name, `${marker}${formatDelivery([message])}`)
    : false;
  if (routed) {
    setPeerDeliveryState(message.id, "routed");
    return;
  }
  setPeerDeliveryState(message.id, "queued");
  const queued = pendingDeliveries.get(teammate.name) ?? [];
  queued.push(message);
  pendingDeliveries.set(teammate.name, queued);
  ensureLivePoll();
}

export type ResidentControlResult = { ok: true } | { ok: false; error: string };

/** Policy check for a bounded input reservation. No task or sequence is created. */
export function authorizeResidentInput(name: string, spawnId: string): ResidentControlResult {
  let agent = currentHostedResident(name, spawnId);
  if (!agent) return { ok: false, error: "The exact hosted child is unavailable." };
  if (pendingShutdowns.has(name) || agent.leaderRequestedEnd) return { ok: false, error: "The hosted child is stopping." };
  // Consume the predecessor while its settlement flag and input ID still belong
  // to that sequence. The queue changes them only after this policy succeeds.
  drainTeammateOutboxes(name);
  agent = currentHostedResident(name, spawnId);
  if (!agent) return { ok: false, error: "The exact hosted child changed during report delivery." };
  if (pendingShutdowns.has(name) || agent.leaderRequestedEnd) return { ok: false, error: "The hosted child is stopping." };
  if (isFreshAssignmentPending(name) || verificationFrozen(agent)) return { ok: false, error: "Task verification or assignment reset prevents input reservation." };
  return { ok: true };
}

function currentHostedResident(name: string, spawnId: string): Agent | undefined {
  const agent = getAgent(name);
  return agent && agent.spawnId === spawnId && agent.status !== "stopped" && !agent.standalone ? agent : undefined;
}

/** Continue one idle incarnation without resetting its Pi session or spawning.
 * A later independent input gets attempt-bound result authority before delivery;
 * an unfinished current holding continues under its existing authority. */
export async function sendResidentSequence(name: string, spawnId: string, input: string): Promise<ResidentControlResult> {
  const agent = currentHostedResident(name, spawnId);
  if (!agent) return { ok: false, error: `No living hosted session "${exactSessionRoute(name, spawnId)}".` };
  if (!input.trim()) return { ok: false, error: "Send requires non-empty input." };
  if (pendingShutdowns.has(name) || agent.leaderRequestedEnd) return { ok: false, error: `@${name} is stopping.` };
  if (agent.status !== "idle" || pendingResidentInputs.has(spawnId) || isFreshAssignmentPending(name)) {
    return { ok: false, error: `@${name} is not idle for new input; inspect or interrupt its active sequence.` };
  }
  drainTeammateOutboxes(name);
  // Draining may synchronously start the final report's verification gate.
  if (verificationFrozen(agent)) return { ok: false, error: `@${name}'s Task is awaiting verification or explicit recovery; input cannot bypass that authority.` };
  const currentTask = agent.currentTaskId ? getTask(agent.currentTaskId) : undefined;
  const continuing = agent.assignment && !agent.assignment.closed && currentTask?.status === "in_progress" && currentTask.claimedBy === name;
  if (!continuing && currentTask && ["in_progress", "superseded"].includes(currentTask.status)) {
    return { ok: false, error: `@${name} still retains Task authority; settle or recover it before independent input.` };
  }
  const previousReportEnded = agent.reportSequenceEnded;
  const previousWorkId = agent.workId;
  let newTaskId: string | undefined;
  if (!continuing) {
    const assignment: WorkerAssignment = { id: `direct:${randomUUID()}`, kind: "direct", resources: [] };
    newTaskId = `work:${randomUUID()}`;
    const bound = createBoundWork({ id: newTaskId, subject: messageTitle(input), description: input, holder: name, assignment });
    if (!bound.ok) return { ok: false, error: bound.reason };
    updateAgent(name, { workId: newTaskId });
  }
  const assignmentId = agent.assignment!.id;
  const sequence = residentSequences.get(spawnId);
  const deliverRole = sequence !== undefined && !sequence.roleDelivered;
  const payload = `[agent-teams-assignment:${assignmentId}]\n` + (deliverRole
    ? buildKickoffPrompt(name, agent.role, sequence.rolePrompt, input)
    : input);
  pendingResidentInputs.add(spawnId);
  // Reserve synchronously so sibling sends cannot race the acknowledgement.
  updateAgent(name, { status: "working", sequenceEnded: false, reportSequenceEnded: false, error: undefined, lastOutputAt: Date.now() });
  publishStateSnapshot();
  try {
    const accepted = await deliverResidentPrompt(name, payload);
    const current = currentHostedResident(name, spawnId);
    if (!current) return { ok: false, error: "Resident exited or was replaced before input acknowledgement." };
    if (!accepted) {
      // A confirmed negative ack did not authorize a new turn. Do not undo
      // evidence if this attempt already settled before the response arrived.
      if (current.sequenceEnded !== true && current.assignment?.id === assignmentId) {
        if (newTaskId && getTask(newTaskId)?.status === "in_progress") {
          discardTask(newTaskId, name);
          updateAgent(name, { workId: previousWorkId });
        }
        updateAgent(name, { status: "idle", sequenceEnded: true, reportSequenceEnded: previousReportEnded });
      }
      return { ok: false, error: `@${name} did not accept input; no new turn was confirmed.` };
    }
    if (sequence) sequence.roleDelivered = true;
    return { ok: true };
  } catch (error) {
    // RPC timeout is uncertain: input may have begun. Retain the attempt and
    // working reservation; retrying must not create a competing input turn.
    const detail = error instanceof Error ? error.message : String(error);
    if (currentHostedResident(name, spawnId)) updateAgent(name, { error: detail });
    return { ok: false, error: detail };
  } finally {
    pendingResidentInputs.delete(spawnId);
    if (runtimeStateFile) publishStateSnapshot();
    notifyChange();
  }
}

/** Native acknowledged steering stays in the current sequence and attempt. */
export async function interruptResidentSequence(name: string, spawnId: string, input: string): Promise<ResidentControlResult> {
  const agent = currentHostedResident(name, spawnId);
  if (!agent) return { ok: false, error: `No living hosted session "${exactSessionRoute(name, spawnId)}".` };
  if (!input.trim()) return { ok: false, error: "Interrupt requires non-empty input." };
  if (agent.status === "idle") return { ok: false, error: `@${name} is idle; use send.` };
  if (pendingShutdowns.has(name) || agent.leaderRequestedEnd) return { ok: false, error: `@${name} is stopping.` };
  if (isFreshAssignmentPending(name) || verificationFrozen(agent)) return { ok: false, error: `@${name}'s attempt is resetting or awaiting verification; steering cannot bypass it.` };
  try {
    const accepted = await deliverResidentSteer(name, input);
    if (!currentHostedResident(name, spawnId)) return { ok: false, error: "Resident exited or was replaced before steer acknowledgement." };
    return accepted ? { ok: true } : { ok: false, error: `@${name} did not accept the steer; its sequence is unchanged.` };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

/** Route the leader's addressed agent_event through the same delivery path. */
export type MessageRoutingOutcome = "steered" | "queued";

export type SendLeaderMessageResult =
  | { ok: true; outcome: MessageRoutingOutcome; priorTerminalReport?: string }
  | { ok: true; outcome: "not-sent"; terminalReport: string }
  | { ok: false; error: string };

/** Body of the teammate's recorded terminal report, when its latest leader
 * mailbox entry carries terminal status. Lets the leader read the report
 * directly instead of steering the teammate into a duplicate resend. */
function recordedTerminalReportBody(name: string): string | undefined {
  const teammate = getAgent(name);
  const assignmentId = teammate?.assignment?.id ?? teammate?.lastAssignment?.id;
  const mailbox = getState().leaderMailbox;
  for (let i = mailbox.length - 1; i >= 0; i--) {
    const message = mailbox[i];
    if (message.archived || message.from !== name || message.assignmentId !== assignmentId || message.spawnId !== teammate?.spawnId) continue;
    if (message.status === "completed" || message.status === "failed") return message.body;
  }
  const taskId = teammate?.lastTaskId;
  const task = taskId ? getTask(taskId) : undefined;
  return task?.status === "completed" ? task.result : undefined;
}

export type AssignExistingWorkResult =
  | { ok: true; workId: string; owner: string; assignmentId: string }
  | { ok: false; error: string };

/** Assign one pending Work Item to an exact idle resident through a fresh Pi
 * session. The record is claimed before reset; reset failure releases it. */
export function assignExistingWork(workId: string, session: string): AssignExistingWorkResult {
  const teammate = resolveExactSession(session, listAgents());
  if (!teammate) return { ok: false, error: "Work assignment requires a current exact session route." };
  const owner = teammate.name;
  const task = getState().tasks[workId];
  if (!teammate || teammate.status === "stopped") return { ok: false, error: `No living teammate named "${owner}".` };
  if (task?.status === "in_progress" && task.claimedBy === owner
    && teammate.currentTaskId === workId && teammate.assignment && !teammate.assignment.closed) {
    return { ok: true, workId, owner, assignmentId: teammate.assignment.id };
  }
  if (teammate.status !== "idle" || teammate.assignment || isFreshAssignmentPending(owner)) {
    return { ok: false, error: `@${owner} is not an idle session available for Work assignment.` };
  }
  if (!task || task.status !== "pending") return { ok: false, error: `Work Item "${workId}" is not pending.` };
  if (!taskDependenciesMet(task)) return { ok: false, error: `Work Item "${workId}" has unmet dependencies.` };
  if (activeAssignmentConflict(task.resources, owner)) return { ok: false, error: `Work Item "${workId}" conflicts with active Work resources.` };
  const assignment = { id: `direct:${randomUUID()}`, kind: "direct" as const, resources: task.resources };
  const claimed = bindTask(workId, owner, assignment, { from: ["pending"] });
  if (!claimed.ok) return { ok: false, error: claimed.reason };
  updateAgent(owner, { reportSequenceEnded: false });
  flushSnapshots();
  const prompt = buildFreshAssignmentPrompt(teammate, assignment.id, [
    `Work Item ${task.id}: ${task.subject}`,
    task.description,
    "Complete this assignment and return the result as your final answer.",
  ].filter(Boolean).join("\n\n"));
  void deliverFreshAssignment(owner, prompt).then((sent) => {
    if (sent) {
      updateAgent(owner, { status: "working", sequenceEnded: false, lastOutputAt: Date.now() });
      return;
    }
    if (getAgent(owner)?.assignment?.id === assignment.id) {
      revertUndeliveredTake(workId, owner, "Pi session reset failed before the assigned Work started.");
    }
    deliverDiagnostic(owner, "Pi session reset failed; the assigned Work was not delivered.");
  });
  return { ok: true, workId, owner, assignmentId: assignment.id };
}

export type ReopenExistingWorkResult =
  | { ok: true; workId: string; subject: string; resources: string[] }
  | { ok: false; error: string };

/** Reopen only a completed Work Item. Active, parked, superseded, and released
 * states remain governed by their explicit lifecycle transitions. */
export function reopenExistingWork(workId: string): ReopenExistingWorkResult {
  const reopened = reopenTask(workId);
  if (!reopened.ok) return { ok: false, error: reopened.reason };
  publishStateSnapshot();
  ensureLivePoll();
  notifyChange();
  return { ok: true, workId: reopened.task.id, subject: reopened.task.subject, resources: reopened.task.resources };
}


export function sendLeaderMessage(
  to: string,
  message: string,
  options?: { reopen?: boolean | "if-closed"; resources?: string[]; workId?: string },
): SendLeaderMessageResult {
  drainTeammateOutboxes(to);
  const teammate = getAgent(to);
  if (!teammate || teammate.status === "stopped") return { ok: false, error: `No living teammate named "${to}".` };
  if (pendingShutdowns.has(to)) return { ok: false, error: `Agent @${to} is stopping; new work is not accepted.` };
  // Explicit work control chooses after draining, not from a stale caller snapshot.
  const selectedWorkId = options?.workId ?? teammate.workId;
  const unexpectedParkKey = selectedWorkId ? `${selectedWorkId}:${teammate.spawnId}` : undefined;
  const recoveringUnexpectedExecution = options?.reopen === true && unexpectedParkKey !== undefined
    && unexpectedExecutionParks.has(unexpectedParkKey);
  if (verificationFrozen(teammate) && !recoveringUnexpectedExecution) {
    const envelope: InboxMessage = {
      id: randomUUID(), from: "leader", subject: messageTitle(message), body: message, timestamp: Date.now(), toSpawnId: teammate.spawnId,
    };
    const queued = pendingDeliveries.get(teammate.name) ?? [];
    queued.unshift(envelope);
    pendingDeliveries.set(teammate.name, queued);
    ensureLivePoll();
    return { ok: true, outcome: "queued" };
  }
  const selectedExistingWork = selectedWorkId ? getState().tasks[selectedWorkId] : undefined;
  const reopen = options?.reopen === "if-closed"
    ? teammate.assignment?.closed === true || selectedExistingWork?.status === "completed"
    : options?.reopen;
  if (options?.reopen === undefined && (!teammate.assignment || teammate.assignment.closed)) {
    const prior = recordedTerminalReportBody(to);
    if (prior) return { ok: true, outcome: "not-sent", terminalReport: prior };
    return { ok: false, error: `@${to} has no open assignment. Take pending work with task update status=in_progress, or move a completed task back with task update status=pending first.` };
  }
  const retryReleasedWork = selectedExistingWork?.status === "pending" && teammate.assignment === undefined;
  if (teammate.assignment?.kind === "direct" && teammate.assignment.closed && !reopen && !retryReleasedWork) {
    const prior = recordedTerminalReportBody(to);
    if (prior) return { ok: true, outcome: "not-sent", terminalReport: prior };
    return { ok: false, error: `@${to} has a closed direct assignment. Use reopen=true for an explicit next assignment.` };
  }
  // A task set holder keeps its task after a terminal report. The leader must be
  // able to steer it for verify feedback or an inconclusive decision without
  // replacing its assignment.
  const activeTaskHolder = teammate.assignment?.kind === "task" && !teammate.assignment.closed;
  if (teammate.reportSequenceEnded && !reopen && !retryReleasedWork && !activeTaskHolder) {
    const prior = recordedTerminalReportBody(to);
    if (prior) return { ok: true, outcome: "not-sent", terminalReport: prior };
    return { ok: false, error: `@${to} already sent a terminal report. Move the task back with task update status=pending before another attempt.` };
  }
  const priorTerminalReport = teammate.reportSequenceEnded ? recordedTerminalReportBody(to) : undefined;
  const taskParkKey = teammate.currentTaskId ? `${teammate.currentTaskId}:${teammate.spawnId}` : undefined;
  if ((reopen || retryReleasedWork) && selectedWorkId && verifyingTasks.has(selectedWorkId)) {
    return { ok: false, error: `Work Item "${selectedWorkId}" is awaiting verification; wait for the gate outcome before reopening.` };
  }
  if (reopen && teammate.assignment && !teammate.assignment.closed && !recoveringUnexpectedExecution) {
    const action = teammate.assignment.kind === "task"
      ? `task complete, or be superseded`
      : "send a terminal report or be explicitly released";
    return { ok: false, error: `@${to} still owns active ${teammate.assignment.kind} assignment "${teammate.assignment.id}". It must ${action} before a direct assignment can open.` };
  }
  const opensDirectAssignment = reopen || retryReleasedWork || teammate.assignment === undefined;
  if (opensDirectAssignment) {
    const existingWork = getState().tasks[selectedWorkId ?? ""];
    const reclaimingExistingWork = (reopen && (existingWork?.status === "completed" || recoveringUnexpectedExecution)) || retryReleasedWork;
    const resources = reclaimingExistingWork
      ? existingWork.resources
      : normalizeResources(options?.resources);
    const assignment = {
      id: `direct:${randomUUID()}`,
      kind: "direct" as const,
      resources,
    };
    if (reclaimingExistingWork) {
      const reclaimed = bindTask(
        selectedWorkId ?? "",
        to,
        assignment,
        {
          from: [retryReleasedWork ? "pending" : recoveringUnexpectedExecution ? "in_progress" : "completed"],
          // An unexpected execution left the previous holder's lease unreturned.
          // Binding anyway is the point: the holder is gone, so waiting for a
          // lease nobody will give back would strand the task.
          allowHeldLease: recoveringUnexpectedExecution,
        },
      );
      if (!reclaimed.ok) return { ok: false, error: reclaimed.reason };
    } else {
      const conflict = activeAssignmentConflict(resources, to);
      if (conflict) {
        return { ok: false, error: `Direct assignment resources conflict with @${conflict.name}'s ${conflict.assignment?.kind} assignment "${conflict.assignment?.id}".` };
      }
      if (selectedWorkId) {
        const bound = createBoundWork({
          id: selectedWorkId,
          subject: messageTitle(message),
          description: message,
          resources,
          holder: to,
          assignment,
        });
        if (!bound.ok) return { ok: false, error: bound.reason };
        updateAgent(to, { workId: selectedWorkId });
      } else {
        assignAgent(to, assignment, undefined);
      }
    }
    updateAgent(to, { reportSequenceEnded: false });
  }
  // A successfully accepted leader message is the explicit direction that
  // unblocks a twice-inconclusive tasks holding; rejected reopen does nothing.
  if (taskParkKey) {
    inconclusiveParks.delete(taskParkKey);
    verifyFailureParks.delete(taskParkKey);
    unexpectedExecutionParks.delete(taskParkKey);
  }
  if (activeTaskHolder) updateAgent(to, { reportSequenceEnded: false });
  const envelope: InboxMessage = {
    id: randomUUID(),
    from: "leader",
    subject: messageTitle(message),
    body: `${opensDirectAssignment || (activeTaskHolder && priorTerminalReport !== undefined) ? `[agent-teams-assignment:${teammate.assignment?.id ?? "none"}]\n` : ""}${message}`,
    timestamp: Date.now(),
    toSpawnId: teammate.spawnId,
  };
  flushSnapshots();
  if (opensDirectAssignment) {
    void deliverFreshAssignment(teammate.name, formatDelivery([envelope])).then((sent) => {
      if (sent) {
        updateAgent(to, { status: "working", sequenceEnded: false, lastOutputAt: Date.now() });
        return;
      }
      const current = getAgent(to);
      const currentTaskId = current?.currentTaskId;
      if (current?.assignment?.id === teammate.assignment?.id && currentTaskId) {
        revertUndeliveredTake(currentTaskId, to, "Pi session reset failed before the new Assignment Attempt started.");
      } else if (current?.assignment?.id === teammate.assignment?.id) {
        assignAgent(to, undefined, undefined);
      }
      deliverDiagnostic(to, "Pi session reset failed; the new Assignment Attempt was not delivered.");
    });
    return { ok: true, outcome: "queued", ...(priorTerminalReport ? { priorTerminalReport } : {}) };
  }
  const steered = sendAgentSteer(teammate.name, formatDelivery([envelope]));
  if (steered) updateAgent(to, { status: "working", sequenceEnded: false, lastOutputAt: Date.now() });
  if (steered) return { ok: true, outcome: "steered", ...(priorTerminalReport ? { priorTerminalReport } : {}) };
  const queued = pendingDeliveries.get(teammate.name) ?? [];
  queued.unshift(envelope);
  pendingDeliveries.set(teammate.name, queued);
  ensureLivePoll();
  return { ok: true, outcome: "queued", ...(priorTerminalReport ? { priorTerminalReport } : {}) };
}

function continueMaybeCompact(inbox: string, inboxName: string, offset: number): void {
  let size = 0;
  try {
    size = fs.statSync(inbox).size;
  } catch {
    return;
  }
  // Truncate only fully-consumed inboxes; message ids make replay safe.
  // Rotation, not truncation: a teammate appending concurrently would lose its
  // message inside the stat/truncate window, while a rename always preserves
  // the records on disk and lets the next append start a fresh file.
  if (size > INBOX_COMPACT_BYTES && offset >= size) {
    try {
      fs.renameSync(inbox, `${inbox}.compacted-${Date.now()}`);
    } catch {
      return;
    }
    setPeerInboxOffset(inboxName, 0);
  }
}

/** Deliver harness feedback (e.g. verify failures) into a teammate inbox. */
export function deliverFeedback(to: string, subject: string, body: string): void {
  const stateFile = requireStateFile();
  appendInboxMessage(inboxPath(stateFile, to), { id: randomUUID(), from: "harness", subject, body });
  ensureLivePoll();
}

// ── Task intents and verify gating ────────────────────────────────

/** Apply claim markers, then submission markers (with verify gating). */
export function processTaskIntents(): void {
  const claims = claimsDir(taskDirectory());
  const submissions = submissionsDir(taskDirectory());
  let guard = 0;
  while (guard++ < 64) {
    const { intent, diagnostic } = takeTaskIntent(claims);
    if (diagnostic) {
      deliverToLeader({ from: "tasks", subject: "Task intent diagnostic", body: diagnostic });
      continue;
    }
    if (!intent) break;
    applyClaimMarker(intent);
  }
  guard = 0;
  while (guard++ < 64) {
    const { intent, diagnostic } = takeTaskIntent(submissions);
    if (diagnostic) {
      deliverToLeader({ from: "tasks", subject: "Task intent diagnostic", body: diagnostic });
      continue;
    }
    if (!intent) break;
    applySubmissionMarker(intent);
  }
}

function applyClaimMarker(intent: import("./types").TaskIntent): void {
  const sender = findLivingTeammate(intent);
  if (!sender || pendingShutdowns.has(sender.name)) return;
  const outcome = applyClaimIntent(intent);
  if (outcome.applied) {
    clearInconclusiveForHolding(intent.taskId, intent.spawnId);
    // A new holding must not inherit an in-flight gate from a previous one.
    invalidateVerifyGate(intent.taskId);
    updateAgent(intent.participant, { currentTaskId: intent.taskId });
    const teammate = getAgent(intent.participant);
    const task = getState().tasks[intent.taskId];
    if (!teammate?.assignment || !task) return;
    const kickoff = [
      `Claim accepted for Work Item ${task.id}: ${task.subject}`,
      task.description,
      "Complete this task with task action=complete outcome=success.",
    ].filter(Boolean).join("\n\n");
    const assignmentId = teammate.assignment.id;
    flushSnapshots();
    void deliverFreshAssignment(teammate.name, buildFreshAssignmentPrompt(teammate, assignmentId, kickoff)).then((sent) => {
      if (sent) return;
      if (getAgent(teammate.name)?.assignment?.id === assignmentId) {
        revertUndeliveredTake(task.id, teammate.name, "Pi session reset failed before the claimed Assignment Attempt started.");
      }
      deliverDiagnostic(teammate.name, "Pi session reset failed; the claimed Assignment Attempt was not delivered.");
    });
    return;
  }
  deliverFeedback(intent.participant, "Claim rejected", outcome.reason ?? "The task is no longer available.");
}

function applySubmissionMarker(intent: import("./types").TaskIntent): void {
  if (intent.status !== "completed" && intent.status !== "failed") {
    deliverFeedback(intent.participant, "Submission rejected", `Task "${intent.taskId}" has an invalid submission status.`);
    return;
  }
  const sender = findLivingTeammate(intent);
  if (!sender || !sender.assignment || intent.assignmentId !== sender.assignment.id) return;
  const task = getState().tasks[intent.taskId];
  const pending = pendingSubmissions.get(intent.participant);
  if (pending?.spawnId === intent.spawnId && pending.assignmentId === intent.assignmentId) return;
  if (!task || (task.status !== "in_progress" && task.status !== "superseded") || task.claimedBy !== intent.participant) {
    deliverFeedback(intent.participant, "Submission rejected", `Task "${intent.taskId}" is not currently yours.`);
    return;
  }
  if (task.status === "superseded") {
    if (intent.status !== "failed") {
      deliverFeedback(intent.participant, "Submission rejected", `Task "${intent.taskId}" was superseded by "${task.supersededBy ?? "a replacement"}". Stop work and submit failed to acknowledge cancellation.`);
      return;
    }
    if (sender.sequenceEnded === false) {
      pendingSubmissions.set(intent.participant, { ...intent, assignmentId: sender.assignment.id, verify: undefined });
    } else {
      releaseSupersededHolding(intent);
    }
    return;
  }
  const parkKey = `${intent.taskId}:${intent.spawnId}`;
  if (intent.status === "completed" && (verifyFailureParks.has(parkKey) || unexpectedExecutionParks.has(parkKey))) {
    const reason = unexpectedExecutionParks.has(parkKey)
      ? "unexpected execution during verification"
      : "two explicit verification failures";
    deliverFeedback(
      intent.participant,
      "Submission rejected while verification is parked",
      `Task "${intent.taskId}" has ${reason}. Wait for explicit Work release and reassignment before submitting another completed outcome.`,
    );
    return;
  }
  if (intent.status === "completed" && verifyingTasks.has(intent.taskId)) {
    deliverFeedback(
      intent.participant,
      "Submission rejected while verification is running",
      `Task "${intent.taskId}" already has a completion review or verdict clarification in flight. Wait for it to pass, fail, or become inconclusive before submitting another completed outcome.`,
    );
    return;
  }
  const verify = intent.status === "completed" ? task.verify ?? resolveAgent(sender.role, leaderCwd)?.verify : undefined;
  const assignmentId = sender.assignment?.id;
  if (!assignmentId) return;
  if (sender.sequenceEnded === false) pendingSubmissions.set(intent.participant, { ...intent, assignmentId, verify });
  else beginVerifyOrComplete(intent, verify);
}

/** Fold one more verify failure into bookkeeping. The first failure invites a
 *  fix-and-resubmit cycle; from the second the harness escalates to the leader
 *  exactly once per holding and stays quiet after that. */
export function reactToVerifyFailure(
  previous: VerifyFailureRecord | undefined,
): VerifyFailureRecord & { escalateToLeader: boolean } {
  const count = (previous?.count ?? 0) + 1;
  const escalated = previous?.escalated === true || count >= VERIFY_FAILURE_ESCALATE_AFTER;
  return { count, escalated, escalateToLeader: escalated && previous?.escalated !== true };
}

function authorizeDirectRevision(intent: import("./types").TaskIntent, detail: string): boolean {
  const teammate = getAgent(intent.participant);
  const task = getState().tasks[intent.taskId];
  if (!teammate || teammate.spawnId !== intent.spawnId || teammate.assignment?.kind !== "direct" || !task) return false;
  const assignment = {
    id: `direct:${randomUUID()}`,
    kind: "direct" as const,
    resources: task.resources,
  };
  assignAgent(intent.participant, assignment, intent.taskId);
  updateAgent(intent.participant, { reportSequenceEnded: false });
  flushSnapshots();
  const revisionBrief = [
    `The completion gate failed for Work Item ${intent.taskId}: ${task.subject}. Revise the result and return a new final answer.`,
    task.description,
    task.verify ? `Verification criteria:\n${task.verify}` : undefined,
    `Review failure detail:\n${detail}`,
  ].filter(Boolean).join("\n\n");
  const prompt = buildFreshAssignmentPrompt(
    teammate,
    assignment.id,
    revisionBrief,
  );
  void deliverFreshAssignment(teammate.name, prompt).then((sent) => {
    if (sent) return;
    if (getAgent(teammate.name)?.assignment?.id === assignment.id) {
      revertUndeliveredTake(intent.taskId, teammate.name, "Pi session reset failed before the verification revision started.");
    }
    deliverDiagnostic(teammate.name, "Pi session reset failed; the verification revision was not delivered.");
  });
  return true;
}

function beginVerifyOrComplete(intent: import("./types").TaskIntent, verify: string | undefined): void {
  const task = getState().tasks[intent.taskId];
  if (!task) return;
  if (task.status === "superseded") {
    if (intent.status === "failed") releaseSupersededHolding(intent);
    return;
  }
  if (intent.status === "failed") {
    finishFailure(intent);
    return;
  }
  if (!verify?.trim()) {
    finishCompletion(intent);
    return;
  }
  // The gate is bound to this exact submission via a unique token: a
  // release/re-claim or newer submission between submit and verify resolution
  // must not let the stale result complete the new holding.
  const submissionId = `${intent.taskId}:${intent.spawnId}:${randomUUID()}`;
  const token = randomUUID();
  const assignmentId = getAgent(intent.participant)?.assignment?.id;
  if (!assignmentId) return;
  verifyingTasks.set(intent.taskId, { worker: intent.participant, spawnId: intent.spawnId, assignmentId, submissionId, token });
  const input: VerifyReviewInput = {
    verify,
    taskSubject: task.subject,
    workerResult: intent.result ?? "",
    cwd: leaderCwd,
  };
  runVerifyGate(intent, task.subject, submissionId, token, input);
}

/** Apply one gate outcome to its submission, guarded by the binding token. */
function resolveGateOutcome(
  intent: import("./types").TaskIntent,
  subject: string,
  submissionId: string,
  token: string,
  outcome: VerifyReviewOutcome,
): void {
  const active = verifyingTasks.get(intent.taskId);
  if (active?.token !== token || active.submissionId !== submissionId) return;
  verifyingTasks.delete(intent.taskId);
  const registered = verifyAborts.get(intent.taskId);
  if (registered?.submissionId === submissionId) verifyAborts.delete(intent.taskId);
  const current = getState().tasks[intent.taskId];
  const holder = getAgent(intent.participant);
  const stillHolds = current?.status === "in_progress"
    && current.claimedBy === intent.participant
    && holder?.spawnId === intent.spawnId
    && holder.assignment?.id === active.assignmentId
    && !pendingShutdowns.has(intent.participant);
  if (!stillHolds) return;
  if (outcome.kind === "pass") {
    inconclusiveVerifications.delete(submissionId);
    archiveDeferredDeliveries(holder);
    finishCompletion(intent);
  } else if (outcome.kind === "inconclusive") {
    const detail = outcome.detail ?? "(reviewer omitted a machine-readable verdict)";
    requestVerifyVerdict(intent, subject, submissionId, detail);
  } else {
    inconclusiveVerifications.delete(submissionId);
    const key = `${intent.taskId}:${intent.spawnId}`;
    const reaction = reactToVerifyFailure(verifyFailures.get(key));
    verifyFailures.set(key, reaction);
    const detail = outcome.detail ?? "(no review output)";
    if (reaction.count >= VERIFY_FAILURE_ESCALATE_AFTER) {
      // An unfixable gate stops the loop. It used to park the task with its
      // holder, which left a runtime state only a leader-side release action could
      // clear, and that action no longer exists.
      //
      // So it becomes what it factually is: the attempt ran and did not deliver
      // an accepted result. The task returns to pending under a recovery hold, and
      // whoever retries has to say what changed — which is the only thing that
      // could possibly make a third attempt worth running.
      const parked = completeTaskWithOutcome(
        intent.taskId,
        intent.participant,
        "failed",
        `The completion gate failed ${reaction.count} consecutive times: ${detail}`,
      );
      if (parked.ok) {
        verifyFailureParks.delete(`${intent.taskId}:${intent.spawnId}`);
        clearInconclusiveForHolding(intent.taskId, intent.spawnId);
        freeAgentFromTask(intent.participant, intent.taskId);
        rearmTaskNotice(intent.taskId);
        publishStateSnapshot();
      }
      if (reaction.escalateToLeader) {
        notifyTaskOutcome(subject, `verify failed ${reaction.count} times for ${intent.taskId}: manual attention needed`, detail);
        // The holder is out of the task, so the leader is the only route left; the
        // task itself is now pending and will not be retried unattended.
        sendUpdate({
          agent: "tasks",
          origin: "harness",
          harnessEvent: { type: "verify-escalation", subject: `Verify gate failed · ${subject}` },
          body: `Verify gate for "${subject}" (${intent.taskId}) failed ${reaction.count} consecutive times.\n\n${detail}\n\nThe attempt is recorded as not delivered and the task is pending under a recovery hold. It will not be retried until somebody takes it with a stated reason.`,
          finished: false,
        });
      }
      deliverFeedback(
        intent.participant,
        `Verify still failing for ${intent.taskId}`,
        [`The completion gate for "${subject}" failed again (${reaction.count} consecutive failures).`, detail, "This attempt is recorded as not delivered, so the task is pending under a recovery hold. Retrying requires a stated reason describing what changed; ordinary messages do not authorize another submission."].join("\n"),
      );
    } else {
      const directRevision = authorizeDirectRevision(intent, detail);
      if (!directRevision) {
        deliverFeedback(
          intent.participant,
          `Verify failed for ${intent.taskId}`,
          [
            `The completion gate for "${subject}" failed.`,
            detail,
            "Fix the issues and redeliver with task action=complete outcome=success.",
          ].join("\n"),
        );
      }
      notifyTaskOutcome(subject, `verify gate failed for ${intent.taskId}`, detail);
    }
  }
  ensureLivePoll();
  notifyChange();
}

function requestVerifyVerdict(
  intent: import("./types").TaskIntent,
  subject: string,
  submissionId: string,
  detail: string,
): void {
  const attempts = inconclusiveVerifications.get(submissionId) ?? 0;
  if (attempts === 0) {
    inconclusiveVerifications.set(submissionId, 1);
    const task = getState().tasks[intent.taskId];
    if (!task) return;
    const token = randomUUID();
    const assignmentId = getAgent(intent.participant)?.assignment?.id;
    if (!assignmentId) return;
    verifyingTasks.set(intent.taskId, { worker: intent.participant, spawnId: intent.spawnId, assignmentId, submissionId, token });
    const input: VerifyReviewInput = {
      verify: `${task.verify ?? resolveAgent(getAgent(intent.participant)?.role ?? "", leaderCwd)?.verify ?? ""}\n\nThe previous review was inconclusive:\n${detail}\n\nReply with exactly one line: ${VERIFY_VERDICT_PASS} or ${VERIFY_VERDICT_FAIL} - <reasons>.`,
      taskSubject: task.subject,
      workerResult: intent.result ?? "",
      cwd: leaderCwd,
    };
    runVerifyGate(intent, subject, submissionId, token, input);
    return;
  }
  // The park used to be a distinct state: the task stayed in progress, held, with
  // the runtime refusing further submissions, and a leader-side action was the only
  // way out. That action no longer exists, and inventing a runtime state nothing
  // can clear is worse than using the one that can.
  //
  // So an inconclusive verdict is recorded as what it is — the attempt did not
  // deliver an accepted result — and the task returns to pending under a recovery
  // hold. Any participant may then take it with a stated reason, and the hold's
  // purpose is exactly this: one inconclusive reviewer must not be retried
  // unattended by whichever participant happens to be idle.
  inconclusiveParks.delete(`${intent.taskId}:${intent.spawnId}`);
  const parked = completeTaskWithOutcome(
    intent.taskId,
    intent.participant,
    "failed",
    `Verification was inconclusive twice for ${intent.taskId}: ${detail}`,
  );
  if (!parked.ok) return;
  clearInconclusiveForHolding(intent.taskId, intent.spawnId);
  invalidateVerifyGate(intent.taskId);
  freeAgentFromTask(intent.participant, intent.taskId);
  rearmTaskNotice(intent.taskId);
  publishStateSnapshot();
  notifyTaskOutcome(subject, `verify inconclusive for ${intent.taskId}: a stated reason is needed to retry`, detail);
  deliverFeedback(
    intent.participant,
    `Verification inconclusive for ${intent.taskId}`,
    `The reviewer twice omitted a machine-readable verdict, so this attempt did not deliver an accepted result. The task is pending under a recovery hold. Take it again with a stated reason, or change the task's verification.\n\n${detail}`,
  );
  sendUpdate({
    agent: "tasks",
    origin: "harness",
    harnessEvent: { type: "verify-inconclusive", subject: `Verify verdict missing · ${subject}` },
    body: `Verification for "${subject}" (${intent.taskId}) was inconclusive twice, so the attempt is recorded as not delivered and the task is pending under a recovery hold.\n\n${detail}`,
    finished: false,
  });
}

/** Drop every per-holding gate record for one task incarnation. Every authority
 *  invalidation routes through here so no counter or park outlives the holding
 *  it was created for. */
function clearInconclusiveForHolding(taskId: string, spawnId: string): void {
  const prefix = `${taskId}:${spawnId}:`;
  for (const key of inconclusiveVerifications.keys()) {
    if (key.startsWith(prefix)) inconclusiveVerifications.delete(key);
  }
  const holding = `${taskId}:${spawnId}`;
  inconclusiveParks.delete(holding);
  verifyFailureParks.delete(holding);
  unexpectedExecutionParks.delete(holding);
  verifyFailures.delete(holding);
}

function finishCompletion(intent: import("./types").TaskIntent): void {
  const task = getState().tasks[intent.taskId];
  if (!task) return;
  const teammate = getAgent(intent.participant);
  const assignmentId = teammate?.assignment?.id;
  if (!teammate || !assignmentId) return;
  retirePendingSubmission(intent);
  const completed = completeTaskWithOutcome(intent.taskId, intent.participant, "success", intent.result);
  if (!completed) return;
  clearInconclusiveForHolding(intent.taskId, intent.spawnId);
  freeAgentFromTask(intent.participant, intent.taskId);
  announceWorkOutcome(intent, teammate, assignmentId);
}

function retirePendingSubmission(intent: import("./types").TaskIntent): void {
  const pending = pendingSubmissions.get(intent.participant);
  if (pending?.spawnId === intent.spawnId && pending.assignmentId === intent.assignmentId) {
    pendingSubmissions.delete(intent.participant);
  }
}

function releaseSupersededHolding(intent: import("./types").TaskIntent): void {
  retirePendingSubmission(intent);
  acknowledgeSupersession(intent.taskId, intent.participant, intent.result?.trim() || "Superseded task cancellation acknowledged.");
  clearInconclusiveForHolding(intent.taskId, intent.spawnId);
  invalidateVerifyGate(intent.taskId);
}

function finishFailure(intent: import("./types").TaskIntent): void {
  const teammate = getAgent(intent.participant);
  const assignmentId = teammate?.assignment?.id;
  if (!teammate || !assignmentId) return;
  retirePendingSubmission(intent);
  const released = completeTaskWithOutcome(intent.taskId, intent.participant, "failed", intent.result?.trim() || "Agent reported failure.");
  if (!released) return;
  clearInconclusiveForHolding(intent.taskId, intent.spawnId);
  invalidateVerifyGate(intent.taskId);
  // Failure is evidence for deliberate recovery, not a fresh work offer to
  // every idle resident. Explicit work.assign starts the next attempt.
  announceWorkOutcome(intent, teammate, assignmentId);
}

function announceWorkOutcome(intent: import("./types").TaskIntent, agent: Agent, assignmentId: string): void {
  updateAgent(intent.participant, { reportSequenceEnded: true });
  const eventId = randomUUID();
  const status = intent.status === "failed" ? "failed" : "completed";
  const report: LeaderReport = {
    agent: intent.participant, role: agent.role, spawnId: intent.spawnId,
    workId: intent.taskId, assignmentId, status, finished: true,
    ...(agent.inputId ? { inputId: agent.inputId } : {}),
    origin: "agent", eventId, timestamp: intent.timestamp,
    body: intent.result || "(no result summary submitted)",
  };
  receiveWorkerMessage({
    id: eventId, type: "message", worker: intent.participant, spawnId: intent.spawnId,
    assignmentId, status, body: report.body, timestamp: report.timestamp,
  });
  sendUpdate(report);
}

// ── Verify gate: fresh one-shot reviewer with a VERDICT protocol ──

/** The reviewer's reply must end with exactly one of these verdict lines. */
export const VERIFY_VERDICT_PASS = "VERDICT: PASS";
export const VERIFY_VERDICT_FAIL = "VERDICT: FAIL";

export interface VerifyReviewInput {
  /** The acceptance-gate prompt (task-level or agent-role default). */
  verify: string;
  /** Tasks subject of the gated task. */
  taskSubject: string;
  /** The claimer's own result summary; evidence, never trusted alone. */
  workerResult: string;
  /** Original project working tree to review, never the private scratch cwd. */
  cwd: string;
  /** Aborted when the holding's authority is invalidated (release, stop, new
   *  claim, supersession, or resumed owner execution), so an orphaned reviewer
   *  cannot keep a child process running against a tree it no longer judges. */
  signal?: AbortSignal;
}

export type VerifyReviewOutcome =
  | { kind: "pass" }
  | { kind: "fail"; detail?: string }
  | { kind: "inconclusive"; detail?: string };

/** Compose the reviewer prompt: fresh context, independent checks, explicit verdict line. */
export function buildVerifyReviewPrompt(input: VerifyReviewInput): string {
  const result = input.workerResult.trim().slice(0, 4000);
  return [
    "You are a fresh completion-gate reviewer for one participant task in the shared task set.",
    `Task subject: ${input.taskSubject}`,
    result ? `The claimer's result summary:\n${result}` : "The claimer provided no result summary.",
    "Independently verify the work against the acceptance gate below using your tools; do not trust the summary alone. Do not modify any files.",
    "Acceptance gate:",
    input.verify.trim(),
    "",
    `End your final message with exactly one verdict line: "${VERIFY_VERDICT_PASS}" if the gate holds, or "${VERIFY_VERDICT_FAIL} - <reasons>" if it does not.`,
  ].join("\n");
}

/** Parse the reviewer's reply into a gate outcome, scanning from the final
 *  line upward. PASS must be an exact verdict line ("VERDICT: PASS", no
 *  trailing content) so a contradictory suffix cannot sneak through; FAIL
 *  carries its reasons. A missing or malformed verdict fails the gate so an
 *  ambiguous review never completes a task. */
export function parseVerifyVerdict(text: string): VerifyReviewOutcome {
  const lines = text.trim().split("\n");
  for (let index = lines.length - 1; index >= 0; index--) {
    const candidate = lines[index].trim();
    if (/^verdict:\s*pass$/i.test(candidate)) return { kind: "pass" };
    const failMatch = /^verdict:\s*fail\b[\s:-]*(.*)$/i.exec(candidate);
    if (failMatch) {
      return { kind: "fail", detail: truncated(failMatch[1].trim()) || "(no reasons given)" };
    }
  }
  return {
    kind: "inconclusive",
    detail: `(no ${VERIFY_VERDICT_PASS}/FAIL verdict line in the review)\n${truncated(text.trim())}`,
  };
}

function truncated(text: string, cap = 4000): string {
  const suffix = "\n…[truncated]";
  return text.length <= cap ? text : text.slice(0, Math.max(0, cap - suffix.length)) + suffix;
}

/** Inspection grant for the gate reviewer: it may run the project's own checks
 *  but holds no `edit`/`write` tool. The limit is the tool set, not the file
 *  system: a shell can still write, so treat this as intent-level, not enforced. */
export const VERIFY_REVIEW_TOOLS: readonly string[] = ["read", "bash", "grep", "find", "ls"];

/** Complete worker options for one gate review. The reviewer runs as a bare Pi
 *  child: no extension, skill, prompt-template, context-file, or theme discovery
 *  and no persisted session, so judging a gate cannot load the leader's extension
 *  surface, run automatic memory learning, write memory files, or leave a session
 *  record behind. Uses the team's model resolution chain (team default, else the
 *  leader model) rather than any role pin. */
export function buildVerifyReviewWorkerOptions(input: VerifyReviewInput): RunPiWorkerOptions {
  return {
    prompt: buildVerifyReviewPrompt(input),
    cwd: input.cwd || leaderCwd,
    tools: [...VERIFY_REVIEW_TOOLS],
    minimal: true,
    model: resolveSpawnModel(undefined, getTeamDefaultModel(), currentLeaderModelRef()).model,
    ...(input.signal ? { signal: input.signal } : {}),
  };
}

/** Run the gate as a one-shot bare Pi worker: a brand-new context that inspects
 *  the working tree itself before answering. */
export async function runVerifyReview(input: VerifyReviewInput): Promise<VerifyReviewOutcome> {
  const outcome = await runPiWorker(buildVerifyReviewWorkerOptions(input));
  // A reviewer that did not exit cleanly produced no trustworthy verdict,
  // even if partial output happens to contain a PASS line.
  if (outcome.exitCode !== 0) {
    return { kind: "fail", detail: truncated(`reviewer exited with code ${outcome.exitCode}: ${(outcome.stderr || outcome.text || "no output").trim()}`) };
  }
  return parseVerifyVerdict(outcome.text);
}

/** Active gate runner; tests inject a stub through setVerifyGateRunner. */
let verifyGateRunner: (input: VerifyReviewInput) => Promise<VerifyReviewOutcome> = runVerifyReview;

/** Replace the completion-gate runner (test seam); undefined restores the real reviewer. */
export function setVerifyGateRunner(runner: ((input: VerifyReviewInput) => Promise<VerifyReviewOutcome>) | undefined): void {
  verifyGateRunner = runner ?? runVerifyReview;
}

function freeAgentFromTask(agentName: string, taskId: string): void {
  const entry = getAgent(agentName);
  if (entry?.currentTaskId === taskId) updateAgent(agentName, { currentTaskId: undefined });
}

function notifyTaskOutcome(subject: string, headline: string, body: string): void {
  deliverToLeader({
    from: "tasks",
    subject: `Task ${headline}: ${subject}`,
    body: body || "(no result summary submitted)",
  });
}

function findLivingTeammate(intent: import("./types").TaskIntent): Agent | undefined {
  const teammate = getAgent(intent.participant);
  return teammate && teammate.status !== "stopped" && teammate.spawnId === intent.spawnId ? teammate : undefined;
}

// ── Wake-ups ──────────────────────────────────────────────────────

/** Claimable tasks the teammate has not been notified about yet. */
export function freshClaimableTasks<T extends { id: string }>(
  noticedIds: readonly string[] | undefined,
  tasks: readonly T[],
): T[] {
  const noticed = new Set(noticedIds ?? []);
  return tasks.filter((task) => !noticed.has(task.id));
}

/** Retain only noticed ids that are still claimable, so a long tasks's history
 *  can never evict a live one and resurrect an old wake-up. */
export function retainLiveNoticedIds(noticedIds: readonly string[], claimableIds: ReadonlySet<string>): string[] {
  return noticedIds.filter((id) => claimableIds.has(id));
}

function markTasksNoticed(name: string, taskIds: string[]): void {
  if (taskIds.length === 0) return;
  const teammate = getAgent(name);
  if (!teammate) return;
  const live = retainLiveNoticedIds(teammate.noticedTaskIds ?? [], new Set(claimableTasks().map((task) => task.id)));
  const merged = [...live, ...taskIds];
  while (merged.length > MAX_NOTICED_TASK_IDS) merged.shift();
  updateAgent(name, { noticedTaskIds: merged });
}

/** A released task becomes noticeable again for every living teammate. */
function rearmTaskNotice(taskId: string): void {
  for (const teammate of livingAgents()) {
    if (teammate.noticedTaskIds?.includes(taskId)) {
      updateAgent(teammate.name, { noticedTaskIds: teammate.noticedTaskIds.filter((id) => id !== taskId) });
    }
  }
}

/**
 * Compose one wake-up prompt per idle teammate from queued inbox deliveries
 * plus a task set notice covering only claimable work that teammate has never
 * been shown. Teammates with nothing new are never woken.
 */
export function wakeIdleTeammates(immediateTaskId?: string): string[] {
  const notified: string[] = [];
  for (const teammate of idleAgents()) {
    if (pendingShutdowns.has(teammate.name) || pendingResidentInputs.has(teammate.spawnId) || verificationFrozen(teammate)) continue;
    const deliveries = pendingDeliveries.get(teammate.name) ?? [];
    // A terminal direct assignment stays closed until explicit reopen; a task set
    // holder must submit rather than drifting into more task work.
    const taskEligible = teammate.assignment === undefined;
    const fresh = taskEligible
      ? freshClaimableTasks(teammate.noticedTaskIds, claimableTasks().filter((task) => !activeAssignmentConflict(task.resources, teammate.name)))
      : [];
    const immediateNotice = immediateTaskId !== undefined && fresh.some((task) => task.id === immediateTaskId);
    const dueNotice = fresh.length > 0 && (immediateNotice || noticeDue(teammate));
    if (deliveries.length === 0 && !dueNotice) continue;
    const prioritized = immediateTaskId === undefined
      ? fresh
      : [
          ...fresh.filter((task) => task.id === immediateTaskId),
          ...fresh.filter((task) => task.id !== immediateTaskId),
        ];
    const noticed = prioritized.slice(0, WAKE_NOTICE_TASK_LIMIT);
    const sequence = residentSequences.get(teammate.spawnId);
    const role = !teammate.assignment && (sequence ? !sequence.roleDelivered : teammate.turns === 0)
      ? `=== ROLE PROMPT (${teammate.role}) ===\n${sequence?.rolePrompt ?? resolveAgent(teammate.role, leaderCwd)?.prompt ?? ""}\n\n`
      : "";
    const prompt = `${teammate.assignment ? `[agent-teams-assignment:${teammate.assignment.id}]\n` : ""}${role}${buildWakePrompt(deliveries, noticed, dueNotice)}`;
    if (!deliverPrompt(teammate.name, prompt)) continue;
    if (sequence) sequence.roleDelivered = true;
    for (const delivery of deliveries) setPeerDeliveryState(delivery.id, "routed");
    notified.push(teammate.name);
    pendingDeliveries.delete(teammate.name);
    if (dueNotice) markTasksNoticed(teammate.name, noticed.map((task) => task.id));
    // A delivered prompt is fresh activity: restart the silence clock so a
    // long-idle teammate is never insta-flagged as stalled on wake.
    updateAgent(teammate.name, {
      status: "working",
      sequenceEnded: false,
      // A generic peer/harness/tasks wake-up never opens a terminal direct
      // assignment. Only an explicit Work assignment owns that transition.
      ...(teammate.assignment?.kind === "direct" && teammate.assignment.closed
        ? {}
        : { reportSequenceEnded: false }),
      lastOutputAt: Date.now(),
      ...(dueNotice ? { lastNoticeAt: Date.now() } : {}),
    });
  }
  return notified;
}

function noticeDue(teammate: Agent): boolean {
  return teammate.lastNoticeAt === undefined || Date.now() - teammate.lastNoticeAt >= NOTICE_PACE_MS;
}

export function buildWakePrompt(
  deliveries: InboxMessage[],
  claimable: Array<{ id: string; subject: string }>,
  includeNotice: boolean,
): string {
  const sections: string[] = [];
  if (deliveries.length > 0) {
    sections.push(`=== INBOX (${deliveries.length} new) ===\n${formatDelivery(deliveries)}`);
  }
  if (includeNotice && claimable.length > 0) {
    const listed = claimable.slice(0, 10).map((task) => `${task.id} (${task.subject})`).join(", ");
    sections.push(`=== TASK NOTICE ===\nUnclaimed tasks: ${listed}\nUse task action=list for details and task update status=in_progress to take one if it suits your role.`);
  }
  if (sections.length === 0) return "";
  const leader = deliveries.find((message) => message.from === "leader" && message.body.startsWith("[agent-teams-assignment:"));
  const marker = leader?.body.split("\n", 1)[0];
  return `${marker ? `${marker}\n` : ""}Wake up. New activity for you:\n\n${sections.join("\n\n")}\n\nHandle the items above, then go idle again.`;
}

function formatDelivery(messages: InboxMessage[]): string {
  const leader = messages.find((message) => message.from === "leader" && message.body.startsWith("[agent-teams-assignment:"));
  const marker = leader?.body.split("\n", 1)[0];
  return `${marker ? `${marker}\n` : ""}${messages.map((message) => `From ${message.from} · ${message.subject}\n${message.body}`).join("\n\n---\n\n")}`;
}

// ── Tasks helpers shared with tools.ts ────────────────────────────

/** A refusal that reached the coordinator's own task surface keeps the store's
 *  shape — code, detail, reason — rather than being flattened to a sentence, so
 *  a coordinator can still branch on why a creation was refused. It is re-exported
 *  because `createCoordinatedTask` is the coordinator's task entry point. */
export type { TaskRefusalResult };

export interface TaskCreationResult {
  ok: true;
  id: string;
  notifiedTeammates: string[];
  livingAgents: number;
  claimable: boolean;
  resourceBlocked: boolean;
  supersededTaskIds: string[];
}

/** Run the coordination side effects of superseding work.
 *
 * Split out because the tasks transition itself belongs to @fradser/pi-tasks
 * now, and this package hears about it on `pi-tasks:task-created` rather than
 * performing it. A superseded holder keeps its assignment and resource lease
 * until it acknowledges cancellation, so its feedback has to be routable before
 * the replacement is announced.
 *
 * @returns the ids that were superseded, for the caller's report.
 */
export function settleSupersededWork(replaced: readonly Task[], replacementId: string): string[] {
  for (const task of replaced) {
    const holder = task.claimedBy ? getAgent(task.claimedBy) : undefined;
    invalidateVerifyGate(task.id);
    if (holder) unexpectedExecutionParks.delete(`${task.id}:${holder.spawnId}`);
    for (const [name, pending] of pendingSubmissions) {
      if (pending.taskId === task.id) pendingSubmissions.delete(name);
    }
    if (holder) {
      archiveDeferredDeliveries(holder);
      const holding = `${task.id}:${holder.spawnId}`;
      verifyFailureParks.delete(holding);
      inconclusiveParks.delete(holding);
      deliverFeedback(
        holder.name,
        `Task superseded: ${task.id}`,
        `Task "${task.id}" was superseded by "${replacementId}". Stop work immediately and acknowledge the cancellation with task complete outcome="failed" so its resources are released.`,
      );
    }
    for (const key of [...verifyFailures.keys()]) {
      if (key.startsWith(`${task.id}:`)) verifyFailures.delete(key);
    }
    for (const key of [...inconclusiveVerifications.keys()]) {
      if (key.startsWith(`${task.id}:`)) inconclusiveVerifications.delete(key);
    }
    rearmTaskNotice(task.id);
  }
  return replaced.map((task) => task.id);
}

/** A task was created by @fradser/pi-tasks' own `task` tool.
 *
 * This is the whole of the leader's response to a task set transition: settle what
 * the supersession displaced, offer the new task to idle residents, and refresh
 * what the console shows. It arrives as an event rather than a call so
 * `@fradser/pi-tasks` never has to know a resident exists, and so a standalone
 * tasks with nobody listening still works.
 */
export function onTaskCreated(input: { id: string; replaced?: string[] }): void {
  const replaced = (input.replaced ?? []).map((id) => getState().tasks[id]).filter(Boolean) as Task[];
  if (replaced.length > 0) settleSupersededWork(replaced, input.id);
  publishStateSnapshot();
  // Creation is a user-visible boundary: an idle resident should not have to
  // wait for a later poll tick to see new work.
  wakeIdleTeammates(input.id);
  publishStateSnapshot();
  notifyChange();
}

/** A task was taken.
 *
 * This is where a re-take invalidates a verification gate left over from the
 * previous attempt. That work used to sit in the leader-side release action, which
 * no longer exists: a task returns to pending because a participant failed it,
 * because the runtime reverted a half-finished start, or because its holder
 * exited. Whichever route brought it back, a reviewer still judging the old
 * candidate must not be able to accept the new one.
 */
export function onTaskTaken(input: { id: string }): void {
  invalidateVerifyGate(input.id);
  rearmTaskNotice(input.id);
  onTaskChanged();
}

/** Any other tasks transition: no resident needs waking, but the snapshot and the
 *  console both show the tasks, so both are refreshed. */
export function onTaskChanged(): void {
  publishStateSnapshot();
  notifyChange();
}

/** Create a task and synchronously offer it to currently-idle agents.
 *
 * The normal poll loop still handles later dependency unlocks and queued mail,
 * but task creation is a user-visible boundary: an idle teammate should not
 * have to wait for a future timer tick before it can see newly-created work.
 */
export function createCoordinatedTask(input: {
  subject: string;
  description?: string;
  dependsOn?: string[];
  verify?: string;
  resources?: string[];
  supersedes?: string[];
}): TaskCreationResult | TaskRefusalResult {
  const created = createTask(input);
  if (!created.ok) return created;
  const supersededTaskIds = settleSupersededWork(created.superseded, created.task.id);
  publishStateSnapshot();
  const resourceBlocked = activeAssignmentConflict(created.task.resources) !== undefined;
  const notifiedTeammates = wakeIdleTeammates(created.task.id);
  publishStateSnapshot();
  notifyChange();
  return {
    ok: true,
    id: created.task.id,
    notifiedTeammates,
    livingAgents: livingAgents().length,
    claimable: claimableTasks().some((task) => task.id === created.task.id) && !resourceBlocked,
    resourceBlocked,
    supersededTaskIds,
  };
}

/** Worker-side submission through an exclusive-create marker file. */
export function attemptSubmission(
  agentName: string,
  spawnId: string,
  taskId: string,
  status: "completed" | "failed",
  result?: string,
): boolean {
  return createTaskIntent(submissionsDir(taskDirectory()), taskId, {
    taskId,
    participant: agentName,
    spawnId,
    assignmentId: getAgent(agentName)?.assignment?.id,
    status,
    result,
    timestamp: Date.now(),
  });
}
