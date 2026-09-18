/**
 * Team machine — resident teammate lifecycle, peer mail routing, task-intent
 * processing, verify gating, and the harness poll loop that wakes idle
 * teammates. The leader model never polls; this loop is the coordination
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
import { MODEL_INHERIT_ALIAS, discoverAgents, persistAgentDefinition, registerSessionAgent, resolveAgent, type AgentDefinition, type AgentDefinitionInput } from "./agents.ts";
import {
  activeAssignmentConflict,
  applyClaimIntent,
  assignTeammate,
  claimableTasks,
  clearWorkerRunEvents,
  completeTask,
  createTask,
  createDirectWork,
  discardDirectWork,
  deliverToLeader,
  getPeerInboxOffset,
  getState,
  getTeammate,
  getTeamDefaultModel,
  idleTeammates,
  isPeerDelivered,
  isValidTeammateName,
  listTeammates,
  livingTeammates,
  loadBoard,
  markPeerDelivered,
  getTask,
  normalizeResources,
  registerTeammate,
  releaseTask,
  releaseTasksOf,
  reclaimDirectWork,
  taskDependenciesMet,
  receiveWorkerMessage,
  reopenCompletedWork,
  setPeerInboxOffset,
  setPeerDeliveryState,
  updateTeammate,
  updateTeammateProgress,
} from "./state.ts";
import {
  appendInboxMessage,
  boardFilePath,
  claimsDir,
  createTaskIntent,
  inboxPath,
  readBoardFile,
  readJsonlBatch,
  removeSessionStateDir,
  removeWorkerOutbox,
  rosterPath,
  stateFilePath,
  submissionsDir,
  takeTaskIntent,
  writeBoardFile,
  writeRoster,
  writeStateFile,
  workerOutboxPath,
} from "./statefile.ts";
import { isWorkerEvent } from "./types.ts";
import {
  deliverFreshAssignment,
  deliverPrompt,
  isCleanExit,
  isFreshAssignmentPending,
  resolveWorkerTools,
  sendWorkerSteer,
  sendWorkerFollowUp,
  spawnResident,
  terminateAllTeammates,
  terminateTeammate,
  unknownWorkerTools,
  WORKER_TOOL_UNIVERSE,
  type WorkerProcessResult,
  type ResidentSpawnOptions,
} from "./spawner.ts";
import { captureWorktreeDiff, cleanupWorktree, createWorktree, discardWorktree } from "./worktree.ts";
import { messageTitle, type InboxMessage, type Teammate, type WorkerAssignment, type WorkerUsage } from "./types.ts";
import { exactSessionRoute, resolveExactSession } from "./recipient.ts";
import type { LeaderReport } from "./leader-reports.ts";

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
 *  work; the cap is far above any realistic concurrent board size. */
const MAX_NOTICED_TASK_IDS = 256;
/** Claimable tasks listed in one wake-prompt board notice. */
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

export function stallSilenceMs(teammate: Pick<Teammate, "lastOutputAt">, now = Date.now()): number | undefined {
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
export function stallThresholdMs(_teammate: Pick<Teammate, "modelOutputSeen" | "activeTool">): number {
  return STALL_SILENCE_MS;
}

let livePollTimer: ReturnType<typeof setInterval> | undefined;
let generation = 0;
let runtimeStateFile = "";
let boardFile = "";
let leaderCwd = "";
/** Live view of the leader session's current model, resolved at spawn time. */
let leaderModelRef: () => string | undefined = () => undefined;
let leaderThinkingLevelRef: () => LeaderThinkingLevel | undefined = () => undefined;
let sendUpdate: (report: LeaderReport) => void = () => {};
let notifyChange: () => void = () => {};

const pendingShutdowns = new Set<string>();
const confirmedStopTimes = new Map<string, number>();
const closeFinalizations = new Map<string, Promise<void>>();

export function getConfirmedStopTime(spawnId: string): number | undefined {
  return confirmedStopTimes.get(spawnId);
}
/** Task ids under verification, bound to one exact submission via token so a
 *  release/re-claim or newer submission invalidates any older in-flight gate. */
const verifyingTasks = new Map<string, { worker: string; spawnId: string; assignmentId: string; submissionId: string; token: string }>();
type PendingSubmission = import("./types").TaskIntent & { assignmentId: string; verify: string | undefined };
/** Submitted Work waits for its authoring Worker to settle before a gate can
 * inspect its files. This applies to direct automatic and board submissions. */
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
const liveWorktrees = new Map<string, ReturnType<typeof createWorktree>>();

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
  boardFile = boardFilePath(sessionFile, leaderCwd);
  sendUpdate = hooks.sendUpdate;
  notifyChange = hooks.notifyChange;
  // Resume: reload a persisted board; claims die with their holders. A board
  // from a removed public surface is archived rather than silently discarded
  // or allowed to prevent extension reload.
  try {
    const persisted = readBoardFile(boardFile);
    if (persisted) loadBoard(persisted.tasks);
  } catch (error) {
    const archived = `${boardFile}.incompatible-${Date.now()}`;
    fs.renameSync(boardFile, archived);
    const detail = error instanceof Error ? error.message : String(error);
    deliverToLeader({ from: "harness", subject: "Incompatible Work snapshot", body: `${detail}\nArchived preserved snapshot: ${archived}` });
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
  boardFile = "";
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
  pendingSubmissions.clear();
  idleNudgesSent.clear();
  selfFinalizeAttempts.clear();
  pendingDeliveries.clear();
  verifyFailures.clear();
  inconclusiveParks.clear();
  verifyFailureParks.clear();
  unexpectedExecutionParks.clear();
  announcedFinishKeys.clear();
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
export async function teardownTeammates(): Promise<string[]> {
  // Session shutdown is an intentional lifecycle transition. Mark every
  // resident before signalling so close callbacks do not misclassify normal
  // session teardown as an unexpected crash and enqueue a follow-up turn.
  for (const teammate of livingTeammates()) pendingShutdowns.add(teammate.name);
  const results = await terminateAllTeammates();
  const diagnostics: string[] = [];
  for (const result of results) {
    if (!result.confirmedClosed) diagnostics.push(`Agent ${result.name} could not be confirmed closed.`);
    updateTeammate(result.name, { status: "stopped" });
  }
  return diagnostics;
}

/** Remove the current session's runtime dir; the task board persists. */
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

function flushSnapshots(): void {
  const stateFile = requireStateFile();
  try {
    writeStateFile(stateFile, getState());
    writeRoster(rosterPath(stateFile), livingTeammates().map((t) => ({
      name: t.name,
      agent: t.agent,
      spawnId: t.spawnId,
      status: t.status,
      tools: t.tools,
      currentTaskId: t.currentTaskId,
      assignment: t.assignment,
    })));
    if (boardFile) writeBoardFile(boardFile, getState().tasks);
  } catch {
    // The next poll retries the snapshot.
  }
}

export function publishStateSnapshot(): void {
  drainTeammateOutboxes();
  flushSnapshots();
}

export function ensureLivePoll(): void {
  const busy = livingTeammates().length > 0 || verifyingTasks.size > 0 || pendingDeliveries.size > 0;
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

export function spawnTeammate(input: {
  name: string;
  agent: string;
  workId?: string;
  /** Internal binding of an existing Work Item, never exposed as a public field. */
  existingWorkId?: string;
  context?: ResidentSpawnOptions["context"];
  model?: string;
  prompt?: string;
  resources?: string[];
  verify?: string;
  handoffFrom?: string;
  definition?: Omit<AgentDefinitionInput, "name" | "tools"> & {
    tools?: string[];
    persist?: boolean;
    persistScope?: "project" | "project-local";
  };
}): { ok: true; teammate: Teammate; readiness?: Promise<string | undefined> } | { ok: false; error: string } {
  const stateFile = requireStateFile();
  const invalid = validateSpawnInput(input);
  if (invalid) return { ok: false, error: invalid };
  if (input.handoffFrom) {
    const predecessor = getTeammate(input.handoffFrom);
    if (!predecessor) return { ok: false, error: `Cannot hand off from @${input.handoffFrom}: teammate not found.` };
    if (predecessor.status !== "stopped") {
      return { ok: false, error: `Cannot hand off from living @${input.handoffFrom}. Shut it down or wait for it to stop before spawning a successor.` };
    }
  }
  const existingWork = input.existingWorkId ? getState().tasks[input.existingWorkId] : undefined;
  if (input.existingWorkId && (!existingWork || existingWork.status !== "pending" || !taskDependenciesMet(existingWork))) {
    return { ok: false, error: `Work Item "${input.existingWorkId}" is not pending and claimable.` };
  }
  const resolved = resolveAgent(input.agent, leaderCwd);
  // Reject tool ids the bare child could never grant before any side effect:
  // a silent --tools drop here is how reviewers end up blind mid-audit.
  const requestedTools = input.definition && inlineDefinitionApplies(resolved) ? input.definition.tools : resolved?.tools;
  const unknownTools = unknownWorkerTools(requestedTools);
  if (unknownTools.length > 0) return { ok: false, error: unknownWorkerToolsError(unknownTools) };
  let agent: AgentDefinition | undefined = resolved;
  if (input.definition && inlineDefinitionApplies(resolved)) {
    try {
      const generated = input.definition;
      const roleInput: AgentDefinitionInput = {
        name: input.agent,
        description: generated.description,
        tools: generated.tools ?? [],
        model: generated.model,
        verify: generated.verify,
        worktree: generated.worktree,
        prompt: generated.prompt,
      };
      agent = generated.persist
        ? persistAgentDefinition(roleInput, generated.persistScope ?? "project-local", leaderCwd)
        : registerSessionAgent(roleInput);
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
  }
  if (!agent) return { ok: false, error: unknownAgentError(input.agent, leaderCwd) };

  let isolation: Teammate["isolation"] = "none";
  let workerCwd = leaderCwd;
  if (agent.worktree) {
    const worktree = createWorktree(workerCwd, `${input.name}-${Date.now()}`);
    if ("error" in worktree) return { ok: false, error: `Cannot isolate teammate: ${worktree.error}` };
    liveWorktrees.set(input.name, worktree);
    isolation = "worktree";
    workerCwd = worktree.cwd;
  }

  const spawnId = randomUUID();
  const effectiveKickoff = buildSuccessorHandoff(input.prompt, input.handoffFrom);
  const directResources = input.existingWorkId
    ? existingWork!.resources
    : effectiveKickoff?.trim()
      ? resolveDirectResources(input.resources, input.handoffFrom)
      : [];
  const conflict = activeAssignmentConflict(directResources);
  if (conflict) {
    discardWorktreeQuietly(input.name);
    return { ok: false, error: `Direct assignment resources conflict with @${conflict.name}'s ${conflict.assignment?.kind} assignment "${conflict.assignment?.id}".` };
  }
  const registered = registerTeammate(newTeammate(input, spawnId, isolation, workerCwd));
  if (!registered.ok) {
    discardWorktreeQuietly(input.name);
    return { ok: false, error: registered.error };
  }

  const spawnModel = resolveSpawnModel(input.model ?? agent.model, getTeamDefaultModel(), currentLeaderModelRef());
  // Record the grant before the first wake: a role derived without tools shows
  // its narrow capability-only allowlist right on the spawn surface.
  const assignment = directAssignment(effectiveKickoff, directResources, spawnId);
  if (assignment) {
    const directWork = input.existingWorkId
      ? reclaimDirectWork(input.existingWorkId, input.name, assignment, "pending")
      : createDirectWork({
        id: getTeammate(input.name)?.workId ?? `work:${spawnId}`,
        subject: effectiveKickoff ?? "Direct work",
        resources: directResources,
        verify: input.verify,
        workerName: input.name,
        assignment,
      });
    if (!directWork.ok) {
      updateTeammate(input.name, { status: "stopped" });
      discardWorktreeQuietly(input.name);
      return { ok: false, error: directWork.error };
    }
  }
  updateTeammate(input.name, {
    model: spawnModel.model,
    context: input.context === undefined ? "fresh" : "fork",
    tools: resolveWorkerTools(agent.tools),
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
  const started = spawnResident({
    workerName: input.name,
    description: assignment ? `[agent-teams-assignment:${assignment.id}]\n` + buildKickoffPrompt(
      input.name,
      input.agent,
      agent.prompt,
      effectiveKickoff,
      isolation,
    ) : undefined,
    model: spawnModel.model,
    thinking: currentLeaderThinkingLevel(),
    context: input.context,
    tools: agent.tools,
    cwd: workerCwd,
    env: teammateEnv(stateFile, input, spawnId, agent.verify),
    onUpdate: (progress) => {
      applyProgress(input.name, spawnId, progress);
      if (progress.controlError) settleReadiness(progress.controlError);
      else if (progress.ready) settleReadiness(undefined);
    },
    onError: (error) => {
      settleReadiness(`Resident startup readiness failed: ${error.message}`);
      if (getTeammate(input.name)?.spawnId !== spawnId) return;
      if (input.existingWorkId) releaseTask(input.existingWorkId, `Agent failed to start: ${error.message}`);
      failSpawn(input.name, error.message, input.existingWorkId);
    },
    onExit: (result) => {
      settleReadiness("Resident exited before startup readiness was acknowledged.");
      closeFinalizations.set(spawnId, handleTeammateClose(input.name, spawnId, result));
    },
  });
  if ("error" in started) {
    if (input.existingWorkId) releaseTask(input.existingWorkId, `Agent failed to start: ${started.error}`);
    else if (assignment) discardDirectWork(getTeammate(input.name)?.workId ?? `work:${spawnId}`, input.name);
    failSpawn(input.name, started.error, input.existingWorkId);
    return { ok: false, error: started.error };
  }
  updateTeammate(input.name, { pid: started.pid });
  // Keep starting until model activity or the unassigned child's native
  // readiness acknowledgement arrives; spawning alone does not prove idle.
  publishStateSnapshot();
  ensureLivePoll();
  notifyChange();
  return { ok: true, teammate: getTeammate(input.name)!, ...(assignment ? {} : { readiness }) };
}

/** True when a spawn's inline definition should create or replace the role:
 *  nothing resolved, or only a session-scoped generated role did. Filesystem
 *  scopes are user-owned and always win over inline input. */
export function inlineDefinitionApplies(resolved: AgentDefinition | undefined): boolean {
  return !resolved || resolved.scope === "session";
}

/** Spawn failure for execution-tool ids outside the teammate universe. */
export function unknownWorkerToolsError(unknown: readonly string[]): string {
  return [
    `Unknown tool id${unknown.length === 1 ? "" : "s"} for a teammate: ${unknown.join(", ")}.`,
    "A teammate child runs a bare pi process (--no-extensions), so only pi built-in tools plus the teammate capability set can be granted.",
    `Valid ids: ${WORKER_TOOL_UNIVERSE.join(", ")}.`,
    "MCP or project-extension tools cannot reach a teammate; perform that work in the leader session instead.",
  ].join(" ");
}

/** Spawn failure for an unresolvable agent name. Definitions resolve live at
 *  spawn time, so the available-agents list in the cached session guidance can
 *  go stale (e.g. another session removed the file); name every checked scope
 *  and the recovery path. */
export function unknownAgentError(name: string, cwd: string): string {
  const available = [...discoverAgents(cwd).keys()];
  return [
    `Agent "${name}" not found in any scope.`,
    `Checked: ${cwd}/.pi/agents/<name>.local.md, ${cwd}/.pi/agents/<name>.md, ${path.join(getAgentDir(), "agents")}, and in-memory session roles.`,
    'The available-agents list in your guidance may be stale: definition files can change mid-session (for example removed by a parallel session).',
    'Recover by retrying agent action=delegate or start with name and an existing agent role id, or with name, a new agent role id, and an inline definition derived from references/agent-roles.md that includes description and prompt.',
    `Available now: ${available.length > 0 ? available.join(", ") : "(none)"}.`,
  ].join(' ');
}

function validateSpawnInput(input: { name: string }): string | undefined {
  if (!isValidTeammateName(input.name)) {
    return `Invalid teammate name "${input.name}". Use letters, digits, dots, dashes, underscores.`;
  }
  if (livingTeammates().some((t) => t.name === input.name)) {
    return `A living teammate named "${input.name}" already exists.`;
  }
  return undefined;
}

function newTeammate(
  input: { name: string; agent: string; workId?: string },

  spawnId: string,
  isolation: Teammate["isolation"],
  workerCwd: string,
): Teammate {
  return {
    name: input.name,
    agent: input.agent,
    spawnId,
    workId: input.workId,
    pid: 0,
    status: "starting",
    cwd: workerCwd,
    isolation,
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
  const prior = handoffFrom ? getTeammate(handoffFrom) : undefined;
  return normalizeResources(prior?.assignment?.resources ?? prior?.lastAssignment?.resources);
}

export function buildSuccessorHandoff(kickoff: string | undefined, handoffFrom: string | undefined): string | undefined {
  if (!handoffFrom?.trim()) return kickoff;
  const prior = getTeammate(handoffFrom);
  const reports = getState().leaderMailbox
    .filter((message) => message.from === handoffFrom)
    .slice(-3)
    .map((message) => `- ${message.subject}: ${truncated(message.body, 1000)}`)
    .join("\n");
  const assignment = prior?.assignment ?? prior?.lastAssignment;
  const taskId = prior?.currentTaskId ?? prior?.lastTaskId;
  const handoff = [
    `=== SUCCESSOR HANDOFF FROM @${handoffFrom} ===`,
    assignment ? `Prior assignment: ${assignment.kind} ${assignment.id}` : "Prior assignment: unavailable",
    taskId ? `Prior board claim: ${taskId}` : "Prior board claim: none",
    reports ? `Recent leader reports:\n${reports}` : "Recent leader reports: none",
    "Verify current files yourself; do not claim the predecessor's board task unless the leader explicitly assigns it.",
  ].join("\n");
  return [kickoff?.trim(), handoff].filter(Boolean).join("\n\n");
}

function teammateEnv(
  stateFile: string,
  input: { name: string; agent: string },
  spawnId: string,
  verify: string | undefined,
): Record<string, string | undefined> {
  return {
    PI_TEAMMATE_WORKER_NAME: input.name,
    PI_TEAMMATE_SPAWN_ID: spawnId,
    PI_TEAMMATE_OUTBOX_FILE: workerOutboxPath(stateFile, input.name, spawnId),
    PI_TEAMMATE_INBOX_FILE: inboxPath(stateFile, input.name),
    PI_TEAMMATE_ROSTER_FILE: rosterPath(stateFile),
    PI_TEAMMATE_BOARD_FILE: boardFile,
    PI_TEAMMATE_CLAIMS_DIR: claimsDir(boardDirectory()),
    PI_TEAMMATE_SUBMISSIONS_DIR: submissionsDir(boardDirectory()),
    PI_TEAMMATE_ROLE_AGENT: input.agent,
    PI_TEAMMATE_VERIFY_DEFAULT: verify ?? "",
  };
}

export function buildKickoffPrompt(
  name: string,
  agentName: string,
  rolePrompt: string,
  kickoff: string | undefined,
  isolation: Teammate["isolation"],
): string {
  const header = [
    `You are a FULLY AUTONOMOUS resident teammate named "${name}" (agent: ${agentName}) in a pi multi-agent team.`,
    "You stay alive between tasks. The harness wakes you with new prompts when",
    "messages arrive for you or when the task board has unclaimed work.",
    isolation === "worktree" ? "You are working inside your own dedicated git worktree." : "",
  ].filter(Boolean).join(" ");
  const roleSection = `=== ROLE PROMPT (${agentName}) ===\n${rolePrompt}`;
  const taskSection = kickoff?.trim()
    ? `=== KICKOFF TASK ===\n${kickoff.trim()}\n\nExecute this assigned task directly. Do not call work action=list or check the task board unless this task explicitly instructs you to do so.`
    : "=== KICKOFF TASK ===\n(none yet — inspect Work with action=list and claim suitable Work with action=claim)";
  return `${header}\n\n${roleSection}\n\n${taskSection}`;
}

function buildFreshAssignmentPrompt(teammate: Teammate, assignmentId: string, task: string): string {
  return `[agent-teams-assignment:${assignmentId}]\n${buildKickoffPrompt(
    teammate.name,
    teammate.agent,
    resolveAgent(teammate.agent, leaderCwd)?.prompt ?? "",
    task,
    teammate.isolation,
  )}`;
}

function discardWorktreeQuietly(name: string): void {
  const handle = liveWorktrees.get(name);
  if (!handle || "error" in handle) return;
  liveWorktrees.delete(name);
  // A failed spawn never produced work; the empty branch goes too.
  discardWorktree(handle);
}

function boardDirectory(): string {
  return path.dirname(boardFile);
}

export function applyProgress(name: string, spawnId: string, progress: {
  text: string;
  activeTool?: string;
  liveThinking?: string;
  turns: number;
  finalResponse?: boolean;
  modelOutputSeen?: boolean;
  ready?: boolean;
  usage?: WorkerUsage;
  controlError?: string;
}): void {
  const teammate = getTeammate(name);
  // A stale callback from an older incarnation must not touch the current one.
  if (!teammate || teammate.spawnId !== spawnId || teammate.status === "stopped") return;
  if (progress.controlError) {
    updateTeammate(name, { error: progress.controlError });
    deliverDiagnostic(name, progress.controlError);
    sendUpdate({ teammate: name, spawnId, body: progress.controlError, origin: "harness", harnessEvent: { type: "control-rejected", subject: `@${name} control rejected` }, finished: false });
  }
  updateTeammateProgress(name, teammate.spawnId, {
    liveText: progress.text,
    activeTool: progress.activeTool,
    liveThinking: progress.liveThinking,
    turns: progress.turns,
    sequenceEnded: progress.finalResponse,
    modelOutputSeen: progress.modelOutputSeen,
    usage: progress.usage,
  });
  updateTeammate(name, { lastOutputAt: Date.now(), ...(progress.finalResponse === false ? { status: "working" } : {}) });
  if (progress.finalResponse === false && teammate.currentTaskId && verifyingTasks.has(teammate.currentTaskId)) {
    const holding = `${teammate.currentTaskId}:${spawnId}`;
    verifyingTasks.delete(teammate.currentTaskId);
    unexpectedExecutionParks.add(holding);
    sendUpdate({
      teammate: name,
      spawnId,
      origin: "harness",
      harnessEvent: { type: "review-invalidated", subject: `Verification invalidated · ${getTask(teammate.currentTaskId)?.subject ?? "Work"}` },
      body: `Observed new execution for @${name} while verification was in flight. The review was invalidated; Work "${teammate.currentTaskId}" remains held until explicit leader direction authorizes a revision.`,
      finished: false,
    });
  }
  if (progress.finalResponse && teammate.status !== "idle") {
    updateTeammate(name, { status: "idle", activeTool: undefined });
    drainTeammateOutboxes(name);
    processTaskIntents();
    const pending = pendingSubmissions.get(name);
    if (pending?.spawnId === spawnId && getTeammate(name)?.assignment?.id === pending.assignmentId) {
      pendingSubmissions.delete(name);
      archiveDeferredDeliveries(getTeammate(name)!);
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

type FinishIdentity = Pick<LeaderReport, "teammate" | "agent" | "spawnId" | "assignmentId" | "finished">;

function finishKey(report: FinishIdentity): string {
  return `${report.teammate ?? report.agent ?? "teammate"}:${report.spawnId ?? "session"}:${report.assignmentId ?? "unassigned"}`;
}

/** Announce each assignment attempt once, including later work in the same process. */
export function markTeammateFinished(report: FinishIdentity): boolean {
  if (!report.finished) return false;
  const key = finishKey(report);
  if (announcedFinishKeys.has(key)) return false;
  announcedFinishKeys.add(key);
  return true;
}

/** Only an open current assignment can owe a final result. */
export function hasUnfinalizedReport(name: string): boolean {
  const teammate = getTeammate(name);
  return Boolean(teammate?.assignment && !teammate.assignment.closed
    && !teammate.reportSequenceEnded && !verificationFrozen(teammate));
}

/** One light reminder per idle transition when work looks unfinished. */
function nudgeIfUnfinalized(name: string, spawnId: string): void {
  if (!hasUnfinalizedReport(name)) return;
  const key = `${name}:${spawnId}:${getTeammate(name)?.assignment?.id}`;
  if (!selfFinalizeAttempts.has(key)) {
    // First miss: give the worker one chance to fix its own bookkeeping
    // before bothering the leader. The inbox message wakes it on the next tick.
    selfFinalizeAttempts.add(key);
    deliverFeedback(
      name,
      "Assignment not finalized",
      `Current assignment "${getTeammate(name)?.assignment?.id ?? "unassigned"}" has no automatic final result yet. Return a final answer or submit the current Work outcome.`,
    );
    return;
  }
  if (idleNudgesSent.has(key)) return;
  idleNudgesSent.add(key);
  const reminder = `@${name} is idle but current assignment "${getTeammate(name)?.assignment?.id ?? "unassigned"}" has no terminal report after one finalization request. Decide whether to resume or release the assignment.`;
  deliverToLeader({ from: "harness", subject: `Idle without terminal report: @${name}`, body: reminder });
  sendUpdate({
    teammate: name,
    body: reminder,
    origin: "harness",
    harnessEvent: { type: "unfinalized-report", subject: `@${name} idle without terminal report` },
    finished: false,
  });
}

function failSpawn(name: string, error: string, existingWorkId?: string): void {
  const teammate = getTeammate(name);
  if (!existingWorkId && teammate?.assignment?.kind === "direct" && teammate.currentTaskId) {
    discardDirectWork(teammate.currentTaskId, name);
  } else {
    releaseTasksOf(name, `Agent failed to start: ${error}`);
  }
  discardWorktreeQuietly(name);
  updateTeammate(name, { status: "stopped", error });
  if (teammate) {
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

export async function shutdownTeammateExact(name: string, spawnId: string): Promise<{ ok: true; body: string } | { ok: false; error: string }> {
  const existing = getTeammate(name);
  if (!existing || existing.spawnId !== spawnId || existing.status === "stopped") {
    return { ok: false, error: `No living session named "${exactSessionRoute(name, spawnId)}".` };
  }
  return shutdownTeammate(name);
}

export async function shutdownTeammate(name: string): Promise<{ ok: true; body: string } | { ok: false; error: string }> {
  const teammate = getTeammate(name);
  if (!teammate || teammate.status === "stopped") return { ok: false, error: `No living teammate named "${name}".` };
  pendingShutdowns.add(name);
  const terminated = await terminateTeammate(name);
  if (terminated.outcome === "unconfirmed") {
    return { ok: false, error: `Agent @${name} could not be confirmed closed; shutdown remains pending.` };
  }
  if (terminated.outcome === "missing" && !confirmedStopTimes.has(teammate.spawnId)) {
    confirmedStopTimes.set(teammate.spawnId, Date.now());
    // The child was already gone; synthesize the close bookkeeping.
    pendingShutdowns.delete(name);
    const released = releaseTasksOf(name, "Agent was stopped.");
    for (const task of released) {
      verifyFailures.delete(`${task.id}:${teammate.spawnId}`);
      clearInconclusiveForHolding(task.id, teammate.spawnId);
      verifyingTasks.delete(task.id);
      rearmTaskNotice(task.id);
    }
    updateTeammate(name, { status: "stopped", activeTool: undefined });
    pendingDeliveries.delete(name);
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

async function handleTeammateClose(name: string, spawnId: string, result: WorkerProcessResult): Promise<void> {
  if (!runtimeStateFile) return;
  const teammate = getTeammate(name);
  if (!teammate || teammate.spawnId !== spawnId || teammate.status === "stopped") return;
  confirmedStopTimes.set(spawnId, Date.now());
  const requested = pendingShutdowns.has(name);
  const crashed = !requested && !isCleanExit(result);

  await finalizeWorktree(name);

  // Drain final reports before tearing down replay metadata so nothing
  // written before close is lost.
  drainTeammateOutboxes();

  const released = releaseTasksOf(name, requested ? "Agent was stopped." : "Agent stopped unexpectedly.");
  for (const task of released) {
    verifyFailures.delete(`${task.id}:${teammate.spawnId}`);
    clearInconclusiveForHolding(task.id, teammate.spawnId);
    verifyingTasks.delete(task.id);
    rearmTaskNotice(task.id);
  }
  pendingShutdowns.delete(name);
  // A stopped teammate must not keep the poll loop or its queue alive.
  pendingDeliveries.delete(name);
  idleNudgesSent.delete(`${name}:${teammate.spawnId}`);
  selfFinalizeAttempts.delete(`${name}:${teammate.spawnId}`);
  updateTeammate(name, {
    status: "stopped",
    activeTool: undefined,
    error: requested ? undefined : closeErrorText(result, crashed),
  });
  clearWorkerRunEvents(name, teammate.spawnId);
  removeWorkerOutbox(requireStateFile(), name, teammate.spawnId);

  if (requested) {
    const summary = summarizeShutdown(name, released.length, result.exitCode, result.usage);
    deliverToLeader({ from: name, subject: "Agent stopped", body: summary });
    // A requested shutdown is already represented by the tool lifecycle row;
    // keep its summary in the console mailbox without starting a leader turn.
  } else {
    deliverToLeader({ from: name, subject: "Agent stopped unexpectedly", body: crashDiagnostic(name, result, released) });
    const closeReport = {
      teammate: name,
      spawnId: teammate.spawnId,
      body: `@${name} stopped unexpectedly${released.length > 0 ? `; claimed task(s) ${released.map((t) => t.id).join(", ")} returned to the board` : ""}.`,
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

function closeErrorText(result: WorkerProcessResult, crashed: boolean): string | undefined {
  if (!crashed) return undefined;
  return `Closed unexpectedly (code ${result.exitCode ?? "unknown"}${result.signal ? `, signal ${result.signal}` : ""}).`;
}

function crashDiagnostic(name: string, result: WorkerProcessResult, released: Array<{ id: string }>): string {
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
  usage?: import("./types").WorkerUsage,
): string {
  const lines = [`Agent @${name} stopped (exit code ${exitCode ?? "unknown"}).`];
  if (releasedCount > 0) lines.push(`Released claimed task(s): ${releasedCount}.`);
  if (usage) lines.push(`Lifetime usage: ${usage.totalTokens} tokens, $${usage.cost.toFixed(4)}.`);
  return lines.join("\n");
}

async function finalizeWorktree(name: string): Promise<void> {
  const handle = liveWorktrees.get(name);
  if (!handle || "error" in handle) {
    liveWorktrees.delete(name);
    return;
  }
  liveWorktrees.delete(name);
  const captured = captureWorktreeDiff(handle);
  // Cleanup commits any remaining work onto the kept branch before removing
  // the directory: staging alone would die with the worktree.
  const cleaned = cleanupWorktree(handle);
  if (!captured.ok) {
    // The branch survives cleanup, so nothing is lost; wake the leader with
    // the recovery path because this requires a decision.
    const body = `Capturing @${name}'s worktree diff failed (${captured.error}). The branch ${handle.branch} was kept; inspect it manually.`;
    deliverToLeader({ from: name, subject: "Worktree diff capture failed", body });
    sendUpdate({
      teammate: name,
      origin: "harness",
      harnessEvent: { type: "worktree-capture-failed", subject: `@${name} worktree diff capture failed` },
      body,
      finished: false,
    });
    return;
  }
  const changed = captured.diff.patch.trim().length > 0;
  deliverToLeader({
    from: name,
    subject: "Worktree diff captured",
    body: changed
      ? `Agent @${name}'s worktree diff:\n\n=== Worktree changes ===\n${captured.diff.diffStat}\n\n${captured.diff.patch}`
      : `Agent @${name}'s worktree diff:\n(no worktree changes)`,
  });
  // Changed work must reach the leader even though the worktree directory is
  // gone: dispatch a bounded preview plus the branch retrieval command. A
  // clean worktree carries no information and stays log-only.
  if (changed) {
    sendUpdate({
      teammate: name,
      spawnId: getTeammate(name)?.spawnId,
      origin: "harness",
      harnessEvent: { type: "worktree-changes", subject: `@${name} worktree changes captured` },
      body: [
        `Worktree changes captured for @${name} (${captured.diff.diffStat.trim() || "diff"}).`,
        "",
        truncated(captured.diff.patch),
        "",
        `Full diff: git diff ${handle.baseCommit}..${handle.branch}`,
      ].join("\n"),
      finished: false,
    });
  }
  if (!cleaned.ok) {
    const subject = cleaned.error?.includes("worktree left in place") ? "Worktree cleanup aborted" : "Worktree cleanup issue";
    const body = `Cleaning up @${name}'s worktree reported problems (${cleaned.error ?? "unknown cleanup failure"}).`;
    deliverToLeader({ from: name, subject, body });
    sendUpdate({
      teammate: name,
      origin: "harness",
      harnessEvent: { type: "worktree-cleanup-failed", subject: `@${name} worktree cleanup issue` },
      body,
      finished: false,
    });
  }
}

// ── Report outbox draining ────────────────────────────────────────

/** Poll one batch per worker; explicit control drains its recipient's existing snapshot. */
export function drainTeammateOutboxes(recipient?: string): void {
  const stateFile = requireStateFile();
  for (const teammate of livingTeammates()) {
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

function applyOutboxRecord(teammate: Teammate, record: unknown): boolean {
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
      && (task.status === "claimed" || task.status === "superseded")) {
      applySubmissionMarker({
        taskId, worker: teammate.name, spawnId: teammate.spawnId, assignmentId: teammate.assignment.id,
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
    teammate: teammate.name,
    agent: teammate.agent,
    spawnId: teammate.spawnId,
    body: record.body,
    origin: "teammate" as const,
    eventId: record.id,
    assignmentId: record.assignmentId,
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
 * Route new inbox messages. Idle teammates get the content queued for their
 * next wake-up; working teammates receive it immediately through their
 * control stream (falling back to queueing when the stream is unavailable).
 */
export function routePeerInboxes(): void {
  const stateFile = requireStateFile();
  for (const teammate of livingTeammates()) {
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
      dispatchInboxMessage(teammate, message);
    }
  }
}

function parseInboxMessage(record: unknown): InboxMessage | undefined {
  if (!record || typeof record !== "object") return undefined;
  const candidate = record as Partial<InboxMessage>;
  if (typeof candidate.id !== "string" || typeof candidate.from !== "string") return undefined;
  if (typeof candidate.subject !== "string" || typeof candidate.body !== "string") return undefined;
  return { ...candidate, timestamp: candidate.timestamp ?? Date.now() } as InboxMessage;
}

function submissionPending(teammate: Teammate): boolean {
  const pending = pendingSubmissions.get(teammate.name);
  if (pending?.spawnId === teammate.spawnId && pending.assignmentId === teammate.assignment?.id) return true;
  const task = teammate.currentTaskId ? getState().tasks[teammate.currentTaskId] : undefined;
  return teammate.assignment?.kind === "direct" && teammate.assignment.closed === true
    && task?.status === "claimed" && task.claimedBy === teammate.name;
}

function gateInFlight(teammate: Teammate): boolean {
  return teammate.currentTaskId !== undefined && verifyingTasks.has(teammate.currentTaskId);
}

function verificationFrozen(teammate: Teammate): boolean {
  const taskId = teammate.currentTaskId;
  if (!taskId) return false;
  const holding = `${taskId}:${teammate.spawnId}`;
  return submissionPending(teammate) || gateInFlight(teammate) || verifyFailureParks.has(holding) || unexpectedExecutionParks.has(holding) || inconclusiveParks.has(holding);
}

function archiveDeferredDeliveries(teammate: Teammate): void {
  const deliveries = pendingDeliveries.get(teammate.name) ?? [];
  if (deliveries.length === 0) return;
  pendingDeliveries.delete(teammate.name);
  const task = teammate.currentTaskId ? getState().tasks[teammate.currentTaskId] : undefined;
  if (task) {
    task.deferredMessages = [
      ...(task.deferredMessages ?? []),
      ...deliveries.map(({ from, subject, body, timestamp }) => ({ from, subject, body, timestamp })),
    ].slice(-20);
    task.updatedAt = Date.now();
  }
  for (const delivery of deliveries) setPeerDeliveryState(delivery.id, "routed");
}

function dispatchInboxMessage(teammate: Teammate, message: InboxMessage): void {
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
    ? sendWorkerFollowUp(teammate.name, `${marker}${formatDelivery([message])}`)
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
  const teammate = getTeammate(name);
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
  const teammate = resolveExactSession(session, listTeammates());
  if (!teammate) return { ok: false, error: "Work assignment requires a current exact session route." };
  const owner = teammate.name;
  const task = getState().tasks[workId];
  if (!teammate || teammate.status === "stopped") return { ok: false, error: `No living teammate named "${owner}".` };
  if (task?.status === "claimed" && task.claimedBy === owner
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
  const claimed = reclaimDirectWork(workId, owner, assignment, "pending");
  if (!claimed.ok) return claimed;
  updateTeammate(owner, { reportSequenceEnded: false });
  flushSnapshots();
  const prompt = buildFreshAssignmentPrompt(teammate, assignment.id, [
    `Work Item ${task.id}: ${task.subject}`,
    task.description,
    "Complete this assignment and return the result as your final answer.",
  ].filter(Boolean).join("\n\n"));
  void deliverFreshAssignment(owner, prompt).then((sent) => {
    if (sent) {
      updateTeammate(owner, { status: "working", sequenceEnded: false, lastOutputAt: Date.now() });
      return;
    }
    if (getTeammate(owner)?.assignment?.id === assignment.id) {
      releaseTask(workId, "Pi session reset failed before the assigned Work started.");
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
  const reopened = reopenCompletedWork(workId);
  if (!reopened.ok) return reopened;
  publishStateSnapshot();
  ensureLivePoll();
  notifyChange();
  return { ok: true, workId: reopened.task.id, subject: reopened.task.subject, resources: reopened.task.resources };
}

export type ReleaseExistingWorkResult =
  | { ok: true; workId: string; subject: string; resources: string[] }
  | { ok: false; error: string };

/** Return one claimed Work Item to pending. This invalidates all in-memory
 * submission/review authority before the single-writer state release. */
export function releaseExistingWork(workId: string, reason: string): ReleaseExistingWorkResult {
  const task = getState().tasks[workId];
  if (!task || task.status !== "claimed") return { ok: false, error: `Work Item "${workId}" is not claimed.` };
  const holder = task.claimedBy ? getTeammate(task.claimedBy) : undefined;
  if (holder) {
    pendingSubmissions.delete(holder.name);
    verifyingTasks.delete(workId);
    verifyFailures.delete(`${workId}:${holder.spawnId}`);
    clearInconclusiveForHolding(workId, holder.spawnId);
    verifyFailureParks.delete(`${workId}:${holder.spawnId}`);
    unexpectedExecutionParks.delete(`${workId}:${holder.spawnId}`);
    archiveDeferredDeliveries(holder);
  }
  const released = releaseTask(workId, reason);
  if (!released) return { ok: false, error: `Work Item "${workId}" could not be released.` };
  rearmTaskNotice(workId);
  publishStateSnapshot();
  ensureLivePoll();
  notifyChange();
  return { ok: true, workId: released.id, subject: released.subject, resources: released.resources };
}

export function sendLeaderMessage(
  to: string,
  message: string,
  options?: { reopen?: boolean | "if-closed"; resources?: string[]; workId?: string },
): SendLeaderMessageResult {
  drainTeammateOutboxes(to);
  const teammate = getTeammate(to);
  if (!teammate || teammate.status === "stopped") return { ok: false, error: `No living teammate named "${to}".` };
  if (pendingShutdowns.has(to)) return { ok: false, error: `Agent @${to} is stopping; new work is not accepted.` };
  // Explicit work control chooses after draining, not from a stale caller snapshot.
  const selectedWorkId = options?.workId ?? teammate.workId;
  const unexpectedParkKey = selectedWorkId ? `${selectedWorkId}:${teammate.spawnId}` : undefined;
  const recoveringUnexpectedExecution = options?.reopen === true && unexpectedParkKey !== undefined
    && unexpectedExecutionParks.has(unexpectedParkKey);
  if (verificationFrozen(teammate) && !recoveringUnexpectedExecution) {
    const envelope: InboxMessage = {
      id: randomUUID(), from: "leader", subject: messageTitle(message), body: message, timestamp: Date.now(),
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
    return { ok: false, error: `@${to} has no open assignment. Use work action=assign for pending Work, or work action=reopen then assign for completed Work.` };
  }
  const retryReleasedWork = selectedExistingWork?.status === "pending" && teammate.assignment === undefined;
  if (teammate.assignment?.kind === "direct" && teammate.assignment.closed && !reopen && !retryReleasedWork) {
    const prior = recordedTerminalReportBody(to);
    if (prior) return { ok: true, outcome: "not-sent", terminalReport: prior };
    return { ok: false, error: `@${to} has a closed direct assignment. Use reopen=true for an explicit next assignment.` };
  }
  // A board holder keeps its task after a terminal report. The leader must be
  // able to steer it for verify feedback or an inconclusive decision without
  // replacing its assignment.
  const activeBoardHolder = teammate.assignment?.kind === "board" && !teammate.assignment.closed;
  if (teammate.reportSequenceEnded && !reopen && !retryReleasedWork && !activeBoardHolder) {
    const prior = recordedTerminalReportBody(to);
    if (prior) return { ok: true, outcome: "not-sent", terminalReport: prior };
    return { ok: false, error: `@${to} already sent a terminal report. Use work action=reopen followed by work action=assign for another Work attempt.` };
  }
  const priorTerminalReport = teammate.reportSequenceEnded ? recordedTerminalReportBody(to) : undefined;
  const boardParkKey = teammate.currentTaskId ? `${teammate.currentTaskId}:${teammate.spawnId}` : undefined;
  if ((reopen || retryReleasedWork) && selectedWorkId && verifyingTasks.has(selectedWorkId)) {
    return { ok: false, error: `Work Item "${selectedWorkId}" is awaiting verification; wait for the gate outcome before reopening.` };
  }
  if (reopen && teammate.assignment && !teammate.assignment.closed && !recoveringUnexpectedExecution) {
    const action = teammate.assignment.kind === "board"
      ? `work action=submit or be released/superseded`
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
      const reclaimed = reclaimDirectWork(
        selectedWorkId ?? "",
        to,
        assignment,
        retryReleasedWork ? "pending" : recoveringUnexpectedExecution ? "claimed" : "completed",
        recoveringUnexpectedExecution,
      );
      if (!reclaimed.ok) return reclaimed;
    } else {
      const conflict = activeAssignmentConflict(resources, to);
      if (conflict) {
        return { ok: false, error: `Direct assignment resources conflict with @${conflict.name}'s ${conflict.assignment?.kind} assignment "${conflict.assignment?.id}".` };
      }
      if (selectedWorkId) {
        const created = createDirectWork({
          id: selectedWorkId,
          subject: message,
          resources,
          workerName: to,
          assignment,
        });
        if (!created.ok) return created;
        updateTeammate(to, { workId: selectedWorkId });
      } else {
        assignTeammate(to, assignment, undefined);
      }
    }
    updateTeammate(to, { reportSequenceEnded: false });
  }
  // A successfully accepted leader message is the explicit direction that
  // unblocks a twice-inconclusive board holding; rejected reopen does nothing.
  if (boardParkKey) {
    inconclusiveParks.delete(boardParkKey);
    verifyFailureParks.delete(boardParkKey);
    unexpectedExecutionParks.delete(boardParkKey);
  }
  if (activeBoardHolder) updateTeammate(to, { reportSequenceEnded: false });
  const envelope: InboxMessage = {
    id: randomUUID(),
    from: "leader",
    subject: messageTitle(message),
    body: `${opensDirectAssignment || (activeBoardHolder && priorTerminalReport !== undefined) ? `[agent-teams-assignment:${teammate.assignment?.id ?? "none"}]\n` : ""}${message}`,
    timestamp: Date.now(),
  };
  flushSnapshots();
  if (opensDirectAssignment) {
    void deliverFreshAssignment(teammate.name, formatDelivery([envelope])).then((sent) => {
      if (sent) {
        updateTeammate(to, { status: "working", sequenceEnded: false, lastOutputAt: Date.now() });
        return;
      }
      const current = getTeammate(to);
      const currentTaskId = current?.currentTaskId;
      if (current?.assignment?.id === teammate.assignment?.id && currentTaskId) {
        releaseTask(currentTaskId, "Pi session reset failed before the new Assignment Attempt started.");
      } else if (current?.assignment?.id === teammate.assignment?.id) {
        assignTeammate(to, undefined, undefined);
      }
      deliverDiagnostic(to, "Pi session reset failed; the new Assignment Attempt was not delivered.");
    });
    return { ok: true, outcome: "queued", ...(priorTerminalReport ? { priorTerminalReport } : {}) };
  }
  const steered = sendWorkerSteer(teammate.name, formatDelivery([envelope]));
  if (steered) updateTeammate(to, { status: "working", sequenceEnded: false, lastOutputAt: Date.now() });
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
  if (size > INBOX_COMPACT_BYTES && offset >= size) {
    fs.truncateSync(inbox, 0);
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
  const claims = claimsDir(boardDirectory());
  const submissions = submissionsDir(boardDirectory());
  let guard = 0;
  while (guard++ < 64) {
    const { intent, diagnostic } = takeTaskIntent(claims);
    if (diagnostic) {
      deliverToLeader({ from: "task-board", subject: "Task intent diagnostic", body: diagnostic });
      continue;
    }
    if (!intent) break;
    applyClaimMarker(intent);
  }
  guard = 0;
  while (guard++ < 64) {
    const { intent, diagnostic } = takeTaskIntent(submissions);
    if (diagnostic) {
      deliverToLeader({ from: "task-board", subject: "Task intent diagnostic", body: diagnostic });
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
    verifyFailures.delete(`${intent.taskId}:${intent.spawnId}`);
    clearInconclusiveForHolding(intent.taskId, intent.spawnId);
    // A new holding must not inherit an in-flight gate from a previous one.
    verifyingTasks.delete(intent.taskId);
    updateTeammate(intent.worker, { currentTaskId: intent.taskId });
    const teammate = getTeammate(intent.worker);
    const task = getState().tasks[intent.taskId];
    if (!teammate?.assignment || !task) return;
    const kickoff = [
      `Claim accepted for Work Item ${task.id}: ${task.subject}`,
      task.description,
      "Complete this assignment with work action=submit.",
    ].filter(Boolean).join("\n\n");
    const assignmentId = teammate.assignment.id;
    flushSnapshots();
    void deliverFreshAssignment(teammate.name, buildFreshAssignmentPrompt(teammate, assignmentId, kickoff)).then((sent) => {
      if (sent) return;
      if (getTeammate(teammate.name)?.assignment?.id === assignmentId) {
        releaseTask(task.id, "Pi session reset failed before the claimed Assignment Attempt started.");
      }
      deliverDiagnostic(teammate.name, "Pi session reset failed; the claimed Assignment Attempt was not delivered.");
    });
    return;
  }
  deliverFeedback(intent.worker, "Claim rejected", outcome.reason ?? "The task is no longer available.");
}

function applySubmissionMarker(intent: import("./types").TaskIntent): void {
  if (intent.status !== "completed" && intent.status !== "failed") {
    deliverFeedback(intent.worker, "Submission rejected", `Task "${intent.taskId}" has an invalid submission status.`);
    return;
  }
  const sender = findLivingTeammate(intent);
  if (!sender || !sender.assignment || intent.assignmentId !== sender.assignment.id) return;
  const task = getState().tasks[intent.taskId];
  const pending = pendingSubmissions.get(intent.worker);
  if (pending?.spawnId === intent.spawnId && pending.assignmentId === intent.assignmentId) return;
  if (!task || (task.status !== "claimed" && task.status !== "superseded") || task.claimedBy !== intent.worker) {
    deliverFeedback(intent.worker, "Submission rejected", `Task "${intent.taskId}" is not currently yours.`);
    return;
  }
  if (task.status === "superseded") {
    if (intent.status !== "failed") {
      deliverFeedback(intent.worker, "Submission rejected", `Task "${intent.taskId}" was superseded by "${task.supersededBy ?? "a replacement"}". Stop work and submit failed to acknowledge cancellation.`);
      return;
    }
    if (sender.sequenceEnded === false) {
      pendingSubmissions.set(intent.worker, { ...intent, assignmentId: sender.assignment.id, verify: undefined });
    } else {
      releaseSupersededHolding(intent);
    }
    return;
  }
  const parkKey = `${intent.taskId}:${intent.spawnId}`;
  if (intent.status === "completed" && (inconclusiveParks.has(parkKey) || verifyFailureParks.has(parkKey))) {
    const reason = inconclusiveParks.has(parkKey)
      ? "two inconclusive reviews"
      : "two explicit verification failures";
    deliverFeedback(
      intent.worker,
      "Submission rejected while verification is parked",
      `Task "${intent.taskId}" has ${reason}. Wait for explicit Work release and reassignment before submitting another completed outcome.`,
    );
    return;
  }
  if (intent.status === "completed" && verifyingTasks.has(intent.taskId)) {
    deliverFeedback(
      intent.worker,
      "Submission rejected while verification is running",
      `Task "${intent.taskId}" already has a completion review or verdict clarification in flight. Wait for it to pass, fail, or become inconclusive before submitting another completed outcome.`,
    );
    return;
  }
  const verify = intent.status === "completed" ? task.verify ?? resolveAgent(sender.agent, leaderCwd)?.verify : undefined;
  const assignmentId = sender.assignment?.id;
  if (!assignmentId) return;
  if (sender.sequenceEnded === false) pendingSubmissions.set(intent.worker, { ...intent, assignmentId, verify });
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
  const teammate = getTeammate(intent.worker);
  const task = getState().tasks[intent.taskId];
  if (!teammate || teammate.spawnId !== intent.spawnId || teammate.assignment?.kind !== "direct" || !task) return false;
  const assignment = {
    id: `direct:${randomUUID()}`,
    kind: "direct" as const,
    resources: task.resources,
  };
  assignTeammate(intent.worker, assignment, intent.taskId);
  updateTeammate(intent.worker, { reportSequenceEnded: false });
  flushSnapshots();
  const prompt = buildFreshAssignmentPrompt(
    teammate,
    assignment.id,
    `The completion gate failed for Work Item ${intent.taskId}. Revise the result and return a new final answer.\n\n${detail}`,
  );
  void deliverFreshAssignment(teammate.name, prompt).then((sent) => {
    if (sent) return;
    if (getTeammate(teammate.name)?.assignment?.id === assignment.id) {
      releaseTask(intent.taskId, "Pi session reset failed before the verification revision started.");
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
  const assignmentId = getTeammate(intent.worker)?.assignment?.id;
  if (!assignmentId) return;
  verifyingTasks.set(intent.taskId, { worker: intent.worker, spawnId: intent.spawnId, assignmentId, submissionId, token });
  const input: VerifyReviewInput = {
    verify,
    taskSubject: task.subject,
    workerResult: intent.result ?? "",
    cwd: getTeammate(intent.worker)?.cwd || leaderCwd,
  };
  // A reviewer crash is a concrete failed gate. A missing verdict is handled
  // separately as inconclusive so prose-format drift cannot count as a defect.
  Promise.resolve()
    .then(() => verifyGateRunner(input))
    .then((outcome) => resolveGateOutcome(intent, task.subject, submissionId, token, outcome))
    .catch((error) => resolveGateOutcome(intent, task.subject, submissionId, token, {
      kind: "fail",
      detail: truncated(`(completion review crashed) ${error instanceof Error ? error.message : String(error)}`),
    }));
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
  const current = getState().tasks[intent.taskId];
  const holder = getTeammate(intent.worker);
  const stillHolds = current?.status === "claimed"
    && current.claimedBy === intent.worker
    && holder?.spawnId === intent.spawnId
    && holder.assignment?.id === active.assignmentId;
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
      // An unfixable gate parks the task with its holder instead of
      // looping: no further resubmit invitations, one leader escalation.
      verifyFailureParks.set(`${intent.taskId}:${intent.spawnId}`, { worker: intent.worker, spawnId: intent.spawnId });
      if (reaction.escalateToLeader) {
        notifyTaskOutcome(subject, `verify failed ${reaction.count} times for ${intent.taskId}: manual attention needed`, detail);
        // The holder is parked and will not narrate further; the parked task
        // reaches the leader through the delivery channel itself.
        sendUpdate({
          teammate: "task-board",
          origin: "harness",
          harnessEvent: { type: "verify-escalation", subject: `Verify gate failed · ${subject}` },
          body: `Verify gate for "${subject}" (${intent.taskId}) failed ${reaction.count} consecutive times.\n\n${detail}\n\nThe task stays claimed by @${intent.worker}; decide how to proceed.`,
          finished: false,
        });
      }
      deliverFeedback(
        intent.worker,
        `Verify still failing for ${intent.taskId}`,
        [`The completion gate for "${subject}" failed again (${reaction.count} consecutive failures).`, detail, "The task stays claimed by you. Do not resubmit or reclaim it; the leader has been notified and will decide next steps."].join("\n"),
      );
    } else {
      const directRevision = authorizeDirectRevision(intent, detail);
      if (!directRevision) {
        deliverFeedback(
          intent.worker,
          `Verify failed for ${intent.taskId}`,
          [
            `The completion gate for "${subject}" failed.`,
            detail,
            "Fix the issues and resubmit with work action=submit.",
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
    const assignmentId = getTeammate(intent.worker)?.assignment?.id;
    if (!assignmentId) return;
    verifyingTasks.set(intent.taskId, { worker: intent.worker, spawnId: intent.spawnId, assignmentId, submissionId, token });
    const input: VerifyReviewInput = {
      verify: `${task.verify ?? resolveAgent(getTeammate(intent.worker)?.agent ?? "", leaderCwd)?.verify ?? ""}\n\nThe previous review was inconclusive:\n${detail}\n\nReply with exactly one line: ${VERIFY_VERDICT_PASS} or ${VERIFY_VERDICT_FAIL} - <reasons>.`,
      taskSubject: task.subject,
      workerResult: intent.result ?? "",
      cwd: getTeammate(intent.worker)?.cwd || leaderCwd,
    };
    Promise.resolve()
      .then(() => verifyGateRunner(input))
      .then((outcome) => resolveGateOutcome(intent, subject, submissionId, token, outcome))
      .catch((error) => resolveGateOutcome(intent, subject, submissionId, token, {
        kind: "fail",
        detail: truncated(`(verdict clarification crashed) ${error instanceof Error ? error.message : String(error)}`),
      }));
    return;
  }
  inconclusiveParks.set(`${intent.taskId}:${intent.spawnId}`, { worker: intent.worker, spawnId: intent.spawnId });
  notifyTaskOutcome(subject, `verify inconclusive for ${intent.taskId}: manual verdict needed`, detail);
  deliverFeedback(
    intent.worker,
    `Verification inconclusive for ${intent.taskId}`,
    `The reviewer twice omitted a machine-readable verdict. Your task remains claimed without a verify failure. Wait for explicit Work release and reassignment; ordinary messages do not authorize another submission.\n\n${detail}`,
  );
  sendUpdate({
    teammate: "task-board",
    origin: "harness",
    harnessEvent: { type: "verify-inconclusive", subject: `Verify verdict missing · ${subject}` },
    body: `Verification for "${subject}" (${intent.taskId}) was inconclusive twice. It remains claimed by @${intent.worker} without counting as a verify failure.\n\n${detail}`,
    finished: false,
  });
}

function clearInconclusiveForHolding(taskId: string, spawnId: string): void {
  const prefix = `${taskId}:${spawnId}:`;
  for (const key of inconclusiveVerifications.keys()) {
    if (key.startsWith(prefix)) inconclusiveVerifications.delete(key);
  }
  inconclusiveParks.delete(`${taskId}:${spawnId}`);
  verifyFailureParks.delete(`${taskId}:${spawnId}`);
}

function finishCompletion(intent: import("./types").TaskIntent): void {
  const task = getState().tasks[intent.taskId];
  if (!task) return;
  const teammate = getTeammate(intent.worker);
  const assignmentId = teammate?.assignment?.id;
  if (!teammate || !assignmentId) return;
  retirePendingSubmission(intent);
  const completed = completeTask(intent.taskId, intent.result);
  if (!completed) return;
  verifyFailures.delete(`${intent.taskId}:${intent.spawnId}`);
  clearInconclusiveForHolding(intent.taskId, intent.spawnId);
  freeTeammateFromTask(intent.worker, intent.taskId);
  announceWorkOutcome(intent, teammate, assignmentId);
}

function retirePendingSubmission(intent: import("./types").TaskIntent): void {
  const pending = pendingSubmissions.get(intent.worker);
  if (pending?.spawnId === intent.spawnId && pending.assignmentId === intent.assignmentId) {
    pendingSubmissions.delete(intent.worker);
  }
}

function releaseSupersededHolding(intent: import("./types").TaskIntent): void {
  retirePendingSubmission(intent);
  releaseTask(intent.taskId, intent.result?.trim() || "Superseded task cancellation acknowledged.");
  clearInconclusiveForHolding(intent.taskId, intent.spawnId);
  verifyingTasks.delete(intent.taskId);
}

function finishFailure(intent: import("./types").TaskIntent): void {
  const teammate = getTeammate(intent.worker);
  const assignmentId = teammate?.assignment?.id;
  if (!teammate || !assignmentId) return;
  retirePendingSubmission(intent);
  const released = releaseTask(intent.taskId, intent.result?.trim() || "Agent reported failure.");
  if (!released) return;
  verifyFailures.delete(`${intent.taskId}:${intent.spawnId}`);
  clearInconclusiveForHolding(intent.taskId, intent.spawnId);
  verifyingTasks.delete(intent.taskId);
  rearmTaskNotice(intent.taskId);
  announceWorkOutcome(intent, teammate, assignmentId);
}

function announceWorkOutcome(intent: import("./types").TaskIntent, teammate: Teammate, assignmentId: string): void {
  updateTeammate(intent.worker, { reportSequenceEnded: true });
  const eventId = randomUUID();
  const status = intent.status === "failed" ? "failed" : "completed";
  const report: LeaderReport = {
    teammate: intent.worker, agent: teammate.agent, spawnId: intent.spawnId,
    workId: intent.taskId, assignmentId, status, finished: true,
    origin: "teammate", eventId, timestamp: intent.timestamp,
    body: intent.result || "(no result summary submitted)",
  };
  receiveWorkerMessage({
    id: eventId, type: "message", worker: intent.worker, spawnId: intent.spawnId,
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
  /** Board subject of the gated task. */
  taskSubject: string;
  /** The claimer's own result summary; evidence, never trusted alone. */
  workerResult: string;
  /** Working directory to review: the holder's worktree root when isolated,
   *  else the leader cwd — the reviewer must inspect the claimed work's tree. */
  cwd: string;
}

export type VerifyReviewOutcome =
  | { kind: "pass" }
  | { kind: "fail"; detail?: string }
  | { kind: "inconclusive"; detail?: string };

/** Compose the reviewer prompt: fresh context, independent checks, explicit verdict line. */
export function buildVerifyReviewPrompt(input: VerifyReviewInput): string {
  const result = input.workerResult.trim().slice(0, 4000);
  return [
    "You are a fresh completion-gate reviewer for one teammate task on a shared board.",
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

/** Read-only inspection grant for the gate reviewer: it may run the project's
 *  own checks but cannot edit or write the tree it is judging. */
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

function freeTeammateFromTask(workerName: string, taskId: string): void {
  const teammate = getTeammate(workerName);
  if (teammate?.currentTaskId === taskId) updateTeammate(workerName, { currentTaskId: undefined });
}

function notifyTaskOutcome(subject: string, headline: string, body: string): void {
  deliverToLeader({
    from: "task-board",
    subject: `Task ${headline}: ${subject}`,
    body: body || "(no result summary submitted)",
  });
}

function findLivingTeammate(intent: import("./types").TaskIntent): Teammate | undefined {
  const teammate = getTeammate(intent.worker);
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

/** Retain only noticed ids that are still claimable, so a long board's history
 *  can never evict a live one and resurrect an old wake-up. */
export function retainLiveNoticedIds(noticedIds: readonly string[], claimableIds: ReadonlySet<string>): string[] {
  return noticedIds.filter((id) => claimableIds.has(id));
}

function markTasksNoticed(name: string, taskIds: string[]): void {
  if (taskIds.length === 0) return;
  const teammate = getTeammate(name);
  if (!teammate) return;
  const live = retainLiveNoticedIds(teammate.noticedTaskIds ?? [], new Set(claimableTasks().map((task) => task.id)));
  const merged = [...live, ...taskIds];
  while (merged.length > MAX_NOTICED_TASK_IDS) merged.shift();
  updateTeammate(name, { noticedTaskIds: merged });
}

/** A released task becomes noticeable again for every living teammate. */
function rearmTaskNotice(taskId: string): void {
  for (const teammate of livingTeammates()) {
    if (teammate.noticedTaskIds?.includes(taskId)) {
      updateTeammate(teammate.name, { noticedTaskIds: teammate.noticedTaskIds.filter((id) => id !== taskId) });
    }
  }
}

/**
 * Compose one wake-up prompt per idle teammate from queued inbox deliveries
 * plus a board notice covering only claimable work that teammate has never
 * been shown. Teammates with nothing new are never woken.
 */
export function wakeIdleTeammates(immediateTaskId?: string): string[] {
  const notified: string[] = [];
  for (const teammate of idleTeammates()) {
    if (pendingShutdowns.has(teammate.name) || verificationFrozen(teammate)) continue;
    const deliveries = pendingDeliveries.get(teammate.name) ?? [];
    // A terminal direct assignment stays closed until explicit reopen; a board
    // holder must submit rather than drifting into more board work.
    const boardEligible = teammate.assignment === undefined;
    const fresh = boardEligible
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
    const role = !teammate.assignment && teammate.turns === 0
      ? `=== ROLE PROMPT (${teammate.agent}) ===\n${resolveAgent(teammate.agent, leaderCwd)?.prompt ?? ""}\n\n`
      : "";
    const prompt = `${teammate.assignment ? `[agent-teams-assignment:${teammate.assignment.id}]\n` : ""}${role}${buildWakePrompt(deliveries, noticed, dueNotice)}`;
    if (!deliverPrompt(teammate.name, prompt)) continue;
    for (const delivery of deliveries) setPeerDeliveryState(delivery.id, "routed");
    notified.push(teammate.name);
    pendingDeliveries.delete(teammate.name);
    if (dueNotice) markTasksNoticed(teammate.name, noticed.map((task) => task.id));
    // A delivered prompt is fresh activity: restart the silence clock so a
    // long-idle teammate is never insta-flagged as stalled on wake.
    updateTeammate(teammate.name, {
      status: "working",
      sequenceEnded: false,
      // A generic peer/harness/board wake-up never opens a terminal direct
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

function noticeDue(teammate: Teammate): boolean {
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
    sections.push(`=== BOARD NOTICE ===\nUnclaimed tasks: ${listed}\nUse work action=list for details and work action=claim to take one if appropriate for your role.`);
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

// ── Board helpers shared with tools.ts ────────────────────────────

export interface BoardTaskCreationResult {
  ok: true;
  id: string;
  notifiedTeammates: string[];
  livingTeammates: number;
  claimable: boolean;
  resourceBlocked: boolean;
  supersededTaskIds: string[];
}

/** Create a task and synchronously offer it to currently-idle teammates.
 *
 * The normal poll loop still handles later dependency unlocks and queued mail,
 * but task creation is a user-visible boundary: an idle teammate should not
 * have to wait for a future timer tick before it can see newly-created work.
 */
export function createBoardTask(input: {
  subject: string;
  description?: string;
  dependsOn?: string[];
  verify?: string;
  resources?: string[];
  supersedes?: string[];
}): BoardTaskCreationResult | { ok: false; error: string } {
  const created = createTask(input);
  if (!created.ok) return created;
  for (const task of created.superseded) {
    // A superseded holder intentionally retains its assignment/resource until
    // it submits failed or stops; cancellation is lifecycle control, so it
    // must unpark the holder before its feedback can be routed.
    const holder = task.claimedBy ? getTeammate(task.claimedBy) : undefined;
    verifyingTasks.delete(task.id);
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
        `Work Item "${task.id}" was superseded by "${created.task.id}". Stop work immediately and use work action=submit with outcome="failed" to acknowledge cancellation and release its resources.`,
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
  publishStateSnapshot();
  const resourceBlocked = activeAssignmentConflict(created.task.resources) !== undefined;
  const notifiedTeammates = wakeIdleTeammates(created.task.id);
  publishStateSnapshot();
  notifyChange();
  return {
    ok: true,
    id: created.task.id,
    notifiedTeammates,
    livingTeammates: livingTeammates().length,
    claimable: claimableTasks().some((task) => task.id === created.task.id) && !resourceBlocked,
    resourceBlocked,
    supersededTaskIds: created.superseded.map((task) => task.id),
  };
}

/** Worker-side submission through an exclusive-create marker file. */
export function attemptSubmission(
  workerName: string,
  spawnId: string,
  taskId: string,
  status: "completed" | "failed",
  result?: string,
): boolean {
  return createTaskIntent(submissionsDir(boardDirectory()), taskId, {
    taskId,
    worker: workerName,
    spawnId,
    assignmentId: getTeammate(workerName)?.assignment?.id,
    status,
    result,
    timestamp: Date.now(),
  });
}
