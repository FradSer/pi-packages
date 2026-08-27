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
import { modelLabel, runPiWorker } from "@fradser/pi-kit";
import { MODEL_INHERIT_ALIAS, discoverAgents, persistAgentDefinition, registerSessionAgent, resolveAgent, type AgentDefinition, type AgentDefinitionInput } from "./agents.ts";
import {
  applyClaimIntent,
  claimableTasks,
  clearStateDirty,
  clearWorkerRunEvents,
  completeTask,
  createTask,
  deliverToLeader,
  getPeerInboxOffset,
  getState,
  getTeammate,
  getTeamDefaultModel,
  idleTeammates,
  isPeerDelivered,
  isValidTeammateName,
  listTasks,
  livingTeammates,
  loadBoard,
  markPeerDelivered,
  markStateDirty,
  registerTeammate,
  releaseTask,
  releaseTasksOf,
  receiveWorkerMessage,
  setPeerInboxOffset,
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
  deliverPrompt,
  isCleanExit,
  resolveWorkerTools,
  sendWorkerSteer,
  spawnResident,
  terminateAllTeammates,
  terminateTeammate,
  unknownWorkerTools,
  WORKER_TOOL_UNIVERSE,
  type WorkerProcessResult,
} from "./spawner.ts";
import { captureWorktreeDiff, cleanupWorktree, createWorktree, discardWorktree } from "./worktree.ts";
import { messageTitle, type InboxMessage, type Teammate, type WorkerUsage } from "./types.ts";
import type { FollowUpReport } from "./follow-up-queue.ts";

export const MAX_SESSION_WORKERS = 8;
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
/** Silence is not a work deadline: active stream output keeps a teammate alive.
 * The watchdog may only notify; termination decisions belong to the leader model. */
const DEFAULT_STALL_NOTICE_MS = 30 * 60 * 1000;
export const STALL_NOTICE_MS = readDurationEnv("PI_TEAMMATE_STALL_NOTICE_MS", DEFAULT_STALL_NOTICE_MS);
/** Silence with zero lifetime model output and no tool running is the provider-
 * hang signature: an in-flight request stuck on the model backend will not
 * recover by waiting or steering, so flag it well before the general window so
 * the leader can respawn early. Defaults to five minutes, independent of the
 * notice-pace floor; 0 disables the tier. */
const DEFAULT_SILENT_STALL_MS = 5 * 60 * 1000;
export const SILENT_STALL_MS = readDurationEnv("PI_TEAMMATE_SILENT_STALL_MS", DEFAULT_SILENT_STALL_MS);
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

export function isStallThresholdReached(
  teammate: Pick<Teammate, "lastOutputAt">,
  now: number,
  thresholdMs: number,
): boolean {
  const silence = stallSilenceMs(teammate, now);
  return thresholdMs > 0 && silence !== undefined && silence >= thresholdMs;
}

export function formatSilenceDuration(milliseconds: number): string {
  const totalMinutes = Math.floor(Math.max(0, milliseconds) / 60_000);
  if (totalMinutes < 1) return "less than 1m";
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours > 0) return `${hours}h${minutes > 0 ? ` ${minutes}m` : ""}`;
  return `${minutes}m`;
}

/** True when the stream has delivered recognized model activity (text,
 * thinking, tool-call, or tool execution events) at least once — the stall
 * classifier. Usage totals stay diagnostics only: providers may omit them
 * after real output, and an empty message_end artifact must not count. */
export function hasModelOutput(teammate: Pick<Teammate, "modelOutputSeen">): boolean {
  return teammate.modelOutputSeen === true;
}

/** Silence threshold for one teammate. A worker that has never received model
 * output and runs no tool is almost certainly blocked on the provider rather
 * than doing slow work; that signature uses the shorter silent-stall window. */
export function stallThresholdMs(teammate: Pick<Teammate, "modelOutputSeen" | "activeTool">): number {
  if (STALL_NOTICE_MS <= 0 || SILENT_STALL_MS <= 0) return STALL_NOTICE_MS;
  if (!hasModelOutput(teammate) && !teammate.activeTool) return SILENT_STALL_MS;
  return STALL_NOTICE_MS;
}

function usageLine(usage: WorkerUsage | undefined): string {
  if (!usage) return "";
  return ` Lifetime usage: ${usage.totalTokens} tokens, $${usage.cost.toFixed(4)}.`;
}

/** Stall notice body with the diagnostics a leader needs to decide: silence
 * duration, spawn age, lifetime usage, and — for the zero-output provider-hang
 * signature — the remedy that actually works (shutdown + respawn). */
export function stallNoticeBody(
  teammate: Pick<Teammate, "name" | "createdAt" | "activeTool" | "modelOutputSeen" | "usage">,
  silenceMs: number,
  now = Date.now(),
): string {
  const head = `@${teammate.name} has been silent for ${formatSilenceDuration(silenceMs)} (spawn age ${formatSilenceDuration(Math.max(0, now - teammate.createdAt))}).`;
  if (!hasModelOutput(teammate) && !teammate.activeTool) {
    return `${head} No model output received yet.${usageLine(teammate.usage)} An in-flight request stuck on the provider will not recover by steering; recovery usually means shutting this teammate down and respawning a successor (optionally pinning another model). Decide: keep waiting, steer again, or shut it down.`;
  }
  const toolNote = teammate.activeTool ? ` Tool still running: ${teammate.activeTool}.` : "";
  return `${head}${toolNote}${usageLine(teammate.usage)} The child may be blocked in a provider or tool call; steer delivery is uncertain. Decide: keep waiting, steer again, or shut it down (and respawn a successor with context from the original kickoff, its mailbox reports, board claims, and the /agent-teams detail transcript).`;
}

let livePollTimer: ReturnType<typeof setInterval> | undefined;
let generation = 0;
let runtimeStateFile = "";
let boardFile = "";
let leaderCwd = "";
/** Live view of the leader session's current model, resolved at spawn time. */
let leaderModelRef: () => string | undefined = () => undefined;
let sendUpdate: (report: FollowUpReport) => void = () => {};
let notifyChange: () => void = () => {};

const pendingShutdowns = new Set<string>();
/** Task ids under verification, bound to one exact submission via token so a
 *  release/re-claim or newer submission invalidates any older in-flight gate. */
const verifyingTasks = new Map<string, { worker: string; spawnId: string; token: string }>();
/** Idle nudges already fired per teammate incarnation (one per transition). */
const idleNudgesSent = new Set<string>();
/** One finish entry per spawn incarnation; repeated terminal reports stay ordinary report rows. */
const announcedFinishKeys = new Set<string>();
/** Incarnations whose terminal report reached the leader pipeline, queued or dispatched. */
const terminalReportKeys = new Set<string>();
/** Consecutive verify failures per taskId:spawnId holder incarnation. */
const verifyFailures = new Map<string, VerifyFailureRecord>();
/** Self-finalize requests delivered per teammate incarnation before escalating to the leader. */
const selfFinalizeAttempts = new Set<string>();
const pendingDeliveries = new Map<string, InboxMessage[]>();
const liveWorktrees = new Map<string, ReturnType<typeof createWorktree>>();

// ── Lifecycle ─────────────────────────────────────────────────────

export interface MachineHooks {
  sendUpdate: (report: FollowUpReport) => void;
  notifyChange: () => void;
}

export function initTeamMachine(
  ctx: Pick<ExtensionContext, "sessionManager" | "cwd" | "model">,
  hooks: MachineHooks,
): void {
  generation++;
  leaderCwd = ctx.cwd || process.cwd();
  leaderModelRef = () => (ctx.model ? modelLabel(ctx.model) : undefined);
  const sessionFile = ctx.sessionManager?.getSessionFile();
  runtimeStateFile = stateFilePath(sessionFile, leaderCwd);
  boardFile = boardFilePath(sessionFile, leaderCwd);
  sendUpdate = hooks.sendUpdate;
  notifyChange = hooks.notifyChange;
  // Resume: reload a persisted board; claims die with their holders.
  const persisted = readBoardFile(boardFile);
  if (persisted) loadBoard(persisted.tasks);
}

export function shutdownTeamMachine(): void {
  generation++;
  if (livePollTimer) clearInterval(livePollTimer);
  livePollTimer = undefined;
  runtimeStateFile = "";
  boardFile = "";
  leaderCwd = "";
  leaderModelRef = () => undefined;
  setVerifyGateRunner(undefined);
  sendUpdate = () => {};
  notifyChange = () => {};
  pendingShutdowns.clear();
  verifyingTasks.clear();
  idleNudgesSent.clear();
  selfFinalizeAttempts.clear();
  pendingDeliveries.clear();
  verifyFailures.clear();
  announcedFinishKeys.clear();
  terminalReportKeys.clear();
}

// ── Spawn model resolution ────────────────────────────────────

/** How a spawn's effective model was chosen. */
export type SpawnModelSource = "pin" | "inherit" | "team-default" | "none";

/**
 * Resolve the effective spawn model. Precedence: explicit role pin beats the
 * `inherit` alias (the leader session's current model), which beats the team
 * default set from the console; with none of these Pi picks its own default.
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
  return { model: undefined, source: "none" };
}

/** The leader session's current model reference, when one is selected. */
export function currentLeaderModelRef(): string | undefined {
  return leaderModelRef();
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
    if (!result.confirmedClosed) diagnostics.push(`Teammate ${result.name} could not be confirmed closed.`);
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
    writeRoster(rosterPath(stateFile), livingTeammates().map((t) => ({ name: t.name, agent: t.agent, status: t.status, tools: t.tools })));
    if (boardFile) writeBoardFile(boardFile, getState().tasks);
    clearStateDirty();
  } catch {
    // Keep the dirty bit set so the next poll retries the snapshot.
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
  checkStalledTeammates();
  flushSnapshots();
  ensureLivePoll();
  notifyChange();
}

// ── Spawning ──────────────────────────────────────────────────────

export function spawnTeammate(input: {
  name: string;
  agent: string;
  prompt?: string;
  definition?: Omit<AgentDefinitionInput, "name" | "tools"> & {
    tools?: string[];
    persist?: boolean;
    persistScope?: "project" | "project-local";
  };
}): { ok: true; teammate: Teammate } | { ok: false; error: string } {
  const stateFile = requireStateFile();
  const invalid = validateSpawnInput(input);
  if (invalid) return { ok: false, error: invalid };
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
  const registered = registerTeammate(newTeammate(input, spawnId, isolation, workerCwd));
  if (!registered.ok) {
    discardWorktreeQuietly(input.name);
    return { ok: false, error: registered.error };
  }

  const spawnModel = resolveSpawnModel(agent.model, getTeamDefaultModel(), leaderModelRef());
  // Record the grant before the first wake: a role derived without tools shows
  // its narrow capability-only allowlist right on the spawn surface.
  updateTeammate(input.name, { model: spawnModel.model, tools: resolveWorkerTools(agent.tools) });
  // Flush before the kickoff is written: a fast child must not read a stale
  // worker-readable roster missing its own entry or tool grant.
  publishStateSnapshot();

  const started = spawnResident({
    workerName: input.name,
    description: buildKickoffPrompt(input.name, input.agent, agent.prompt, input.prompt, isolation),
    model: spawnModel.model,
    tools: agent.tools,
    cwd: workerCwd,
    env: teammateEnv(stateFile, input, spawnId, agent.verify),
    onUpdate: (progress) => applyProgress(input.name, spawnId, progress),
    onExit: (result) => void handleTeammateClose(input.name, spawnId, result),
  });
  if ("error" in started) {
    failSpawn(input.name, started.error);
    return { ok: false, error: started.error };
  }
  updateTeammate(input.name, { pid: started.pid });
  // Status stays "starting" until real stream events arrive: every spawned
  // teammate runs a kickoff turn, so marking prompt-less spawns idle here used
  // to mislabel an actively-running turn as idle and misroute deliveries
  // (queued instead of steered, then lost inside the running turn).
  publishStateSnapshot();
  ensureLivePoll();
  notifyChange();
  return { ok: true, teammate: getTeammate(input.name)! };
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
    'Recover by spawning with an inline definition derived from references/agent-roles.md, choose an existing role, or create the role first.',
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
  if (livingTeammates().length >= MAX_SESSION_WORKERS) {
    return `Session cap reached: at most ${MAX_SESSION_WORKERS} teammates may be alive at once.`;
  }
  return undefined;
}

function newTeammate(
  input: { name: string; agent: string },
  spawnId: string,
  isolation: Teammate["isolation"],
  workerCwd: string,
): Teammate {
  return {
    name: input.name,
    agent: input.agent,
    spawnId,
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

function buildKickoffPrompt(
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
    ? `=== KICKOFF TASK ===\n${kickoff.trim()}`
    : "=== KICKOFF TASK ===\n(none yet — check the task board with task_list and claim suitable work with task_claim)";
  return `${header}\n\n${roleSection}\n\n${taskSection}`;
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

function applyProgress(name: string, spawnId: string, progress: {
  text: string;
  activeTool?: string;
  liveThinking?: string;
  turns: number;
  finalResponse?: boolean;
  modelOutputSeen?: boolean;
  usage?: WorkerUsage;
}): void {
  const teammate = getTeammate(name);
  // A stale callback from an older incarnation must not touch the current one.
  if (!teammate || teammate.spawnId !== spawnId || teammate.status === "stopped") return;
  updateTeammateProgress(name, teammate.spawnId, {
    liveText: progress.text,
    activeTool: progress.activeTool,
    liveThinking: progress.liveThinking,
    turns: progress.turns,
    sequenceEnded: progress.finalResponse === true ? true : undefined,
    modelOutputSeen: progress.modelOutputSeen,
    usage: progress.usage,
  });
  updateTeammate(name, { lastOutputAt: Date.now(), stallNoticeSentAt: undefined });
  if (progress.finalResponse && teammate.status !== "idle") {
    updateTeammate(name, { status: "idle", activeTool: undefined });
    nudgeIfUnfinalized(name, spawnId);
  }
  ensureLivePoll();
}

export function formatAgentHealthReport(
  state: "stalled",
  teammate: Pick<Teammate, "name" | "agent">,
  body: string,
  silenceMs: number,
): FollowUpReport {
  return {
    teammate: teammate.name,
    agent: teammate.agent,
    body,
    finished: false,
    health: { state, silenceMs },
  };
}

function checkStalledTeammates(now = Date.now()): void {
  if (STALL_NOTICE_MS <= 0) return;
  for (const teammate of livingTeammates()) {
    if (teammate.status !== "working" && teammate.status !== "starting") continue;
    const silence = stallSilenceMs(teammate, now);
    if (silence === undefined || teammate.stallNoticeSentAt !== undefined) continue;
    if (silence < stallThresholdMs(teammate)) continue;
    const body = stallNoticeBody(teammate, silence, now);
    updateTeammate(teammate.name, { stallNoticeSentAt: now });
    deliverToLeader({ from: "harness", subject: `Possible stall: @${teammate.name}`, body });
    sendUpdate(formatAgentHealthReport("stalled", teammate, body, silence));
  }
}

interface VerifyFailureRecord {
  count: number;
  escalated: boolean;
}

/** Record one finish entry per spawn incarnation; later terminal reports from
 *  the same resident stay ordinary report rows. */
export function markTeammateFinished(
  report: Pick<FollowUpReport, "teammate" | "agent" | "spawnId" | "finished">,
): boolean {
  if (!report.finished) return false;
  const name = report.teammate ?? report.agent ?? "teammate";
  const key = `${name}:${report.spawnId ?? "session"}`;
  if (announcedFinishKeys.has(key)) return false;
  announcedFinishKeys.add(key);
  return true;
}

/** True when this teammate's current incarnation already announced its finish entry. */
export function hasAnnouncedFinish(name: string): boolean {
  const spawnId = getTeammate(name)?.spawnId;
  return announcedFinishKeys.has(`${name}:${spawnId ?? "session"}`);
}

/** Remember at send time that this incarnation produced a terminal report, so
 *  end-of-life suppression covers reports still queued for dispatch. */
export function recordTerminalReport(
  report: Pick<FollowUpReport, "teammate" | "agent" | "spawnId" | "finished">,
): void {
  if (!report.finished) return;
  const name = report.teammate ?? report.agent ?? "teammate";
  terminalReportKeys.add(`${name}:${report.spawnId ?? "session"}`);
}

/** True when this teammate's current incarnation has a terminal report in the
 *  leader pipeline, whether or not its finish entry has been dispatched yet. */
export function hasTerminalReport(name: string): boolean {
  const spawnId = getTeammate(name)?.spawnId;
  return terminalReportKeys.has(`${name}:${spawnId ?? "session"}`);
}

/** True when the teammate's last leader-bound report lacks a terminal status. */
export function hasUnfinalizedReport(name: string): boolean {
  const mailbox = getState().leaderMailbox;
  for (let i = mailbox.length - 1; i >= 0; i--) {
    if (mailbox[i].from !== name) continue;
    return mailbox[i].status !== "completed" && mailbox[i].status !== "failed";
  }
  return false;
}

/** One light reminder per idle transition when work looks unfinished. */
function nudgeIfUnfinalized(name: string, spawnId: string): void {
  const key = `${name}:${spawnId}`;
  // The terminal report may have been written to the outbox file but not yet
  // drained into the leader mailbox by the next tick; drain before deciding.
  drainTeammateOutboxes();
  if (!hasUnfinalizedReport(name)) return;
  if (!selfFinalizeAttempts.has(key)) {
    // First miss: give the worker one chance to fix its own bookkeeping
    // before bothering the leader. The inbox message wakes it on the next tick.
    selfFinalizeAttempts.add(key);
    deliverFeedback(
      name,
      "Assignment not finalized",
      'Your latest message to the leader carried no terminal status. Send send_message(to="leader", message=...) now with status="completed" or status="failed" summarizing your final result.',
    );
    return;
  }
  if (idleNudgesSent.has(key)) return;
  idleNudgesSent.add(key);
  const reminder = `@${name} is now idle but its last report was not marked status="completed" or "failed". Its conclusions may be stuck in the mailbox — ask it to finalize or inspect the /agent-teams console.`;
  deliverToLeader({ from: "harness", subject: `Idle without terminal report: @${name}`, body: reminder });
  sendUpdate({
    teammate: name,
    body: reminder,
    origin: "harness",
    harnessEvent: { type: "unfinalized-report", subject: `@${name} idle without terminal report` },
    finished: false,
  });
}

function failSpawn(name: string, error: string): void {
  const teammate = getTeammate(name);
  discardWorktreeQuietly(name);
  updateTeammate(name, { status: "stopped", error });
  if (teammate) {
    clearWorkerRunEvents(name, teammate.spawnId);
    removeWorkerOutbox(requireStateFile(), name, teammate.spawnId);
  }
  deliverToLeader({
    from: name,
    subject: "Teammate failed to start",
    body: `Teammate @${name} could not start.\nError: ${error}`,
  });
  publishStateSnapshot();
  notifyChange();
}

// ── Shutdown and close ────────────────────────────────────────────

export async function shutdownTeammate(name: string): Promise<{ ok: true; body: string } | { ok: false; error: string }> {
  const teammate = getTeammate(name);
  if (!teammate || teammate.status === "stopped") return { ok: false, error: `No living teammate named "${name}".` };
  pendingShutdowns.add(name);
  const terminated = await terminateTeammate(name);
  if (!terminated) {
    // The child was already gone; synthesize the close bookkeeping.
    pendingShutdowns.delete(name);
    const released = releaseTasksOf(name, "Teammate was shut down.");
    for (const task of released) {
      verifyFailures.delete(`${task.id}:${teammate.spawnId}`);
      verifyingTasks.delete(task.id);
      rearmTaskNotice(task.id);
    }
    updateTeammate(name, { status: "stopped", activeTool: undefined });
    idleNudgesSent.delete(`${name}:${teammate.spawnId}`);
    selfFinalizeAttempts.delete(`${name}:${teammate.spawnId}`);
    // No close event will fire for an already-gone child, so this branch is
    // the only chance to put the shutdown summary on the delivery channel.
    const summary = summarizeShutdown(name, released.length, 0, undefined);
    deliverToLeader({ from: name, subject: "Teammate shut down", body: summary });
    publishStateSnapshot();
    notifyChange();
    return { ok: true, body: summary };
  }
  // Close finalization completes state transitions and reporting.
  return {
    ok: true,
    body: `Shutdown requested for @${name}.`,
  };
}

async function handleTeammateClose(name: string, spawnId: string, result: WorkerProcessResult): Promise<void> {
  if (!runtimeStateFile) return;
  const teammate = getTeammate(name);
  if (!teammate || teammate.spawnId !== spawnId || teammate.status === "stopped") return;
  const requested = pendingShutdowns.has(name);
  const crashed = !requested && !isCleanExit(result);

  await finalizeWorktree(name);

  // Drain final reports before tearing down replay metadata so nothing
  // written before close is lost.
  drainTeammateOutboxes();

  const released = releaseTasksOf(name, requested ? "Teammate was shut down." : "Teammate stopped unexpectedly.");
  for (const task of released) {
    verifyFailures.delete(`${task.id}:${teammate.spawnId}`);
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
    deliverToLeader({ from: name, subject: "Teammate shut down", body: summary });
    // A requested shutdown is already represented by the tool lifecycle row;
    // keep its summary in the console mailbox without starting a leader turn.
  } else {
    deliverToLeader({ from: name, subject: "Teammate stopped unexpectedly", body: crashDiagnostic(name, result, released) });
    const closeReport = {
      teammate: name,
      spawnId: teammate.spawnId,
      body: `@${name} stopped unexpectedly${released.length > 0 ? `; claimed task(s) ${released.map((t) => t.id).join(", ")} returned to the board` : ""}.`,
      origin: "harness" as const,
      harnessEvent: { type: "unexpected-stop", subject: `@${name} stopped unexpectedly` },
      finished: false,
    };
    recordTerminalReport(closeReport);
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
    `Teammate @${name} closed without a shutdown request.`,
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
  const lines = [`Teammate @${name} shut down (exit code ${exitCode ?? "unknown"}).`];
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
      ? `Teammate @${name}'s worktree diff:\n\n=== Worktree changes ===\n${captured.diff.diffStat}\n\n${captured.diff.patch}`
      : `Teammate @${name}'s worktree diff:\n(no worktree changes)`,
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

/** Drain validated report events from every living teammate's outbox. */
export function drainTeammateOutboxes(): void {
  const stateFile = requireStateFile();
  let changed = false;
  for (const teammate of livingTeammates()) {
    const key = `${teammate.name}:${teammate.spawnId}`;
    const offsets = getState().workerEventOffsets;
    const previousOffset = offsets[key] ?? 0;
    const { records, nextOffset, diagnostics } = readJsonlBatch(
      workerOutboxPath(stateFile, teammate.name, teammate.spawnId),
      previousOffset,
    );
    if (nextOffset !== previousOffset) {
      offsets[key] = nextOffset;
      changed = true;
    }
    for (const diagnostic of diagnostics) deliverDiagnostic(teammate.name, diagnostic);
    for (const record of records) {
      if (applyOutboxRecord(teammate, record)) changed = true;
    }
  }
  // Persist on transitions, not per poll tick.
  if (changed) markStateDirty();
}

function deliverDiagnostic(from: string, detail: string): void {
  deliverToLeader({ from, subject: "Teammate channel diagnostic", body: detail });
}

function applyOutboxRecord(teammate: Teammate, record: unknown): boolean {
  if (!isWorkerEvent(record)) return false;
  if (record.worker !== teammate.name || record.spawnId !== teammate.spawnId) return false;
  const ids = getState().workerEventIds;
  const eventKey = `${teammate.spawnId}:${record.id}`;
  if (ids[eventKey]) return false;
  ids[eventKey] = teammate.spawnId;
  markStateDirty();

  if (teammate.reportSequenceEnded) return false;
  const terminal = record.status === "completed" || record.status === "failed";
  if (terminal) {
    updateTeammate(teammate.name, {
      reportSequenceEnded: true,
      status: "idle",
      activeTool: undefined,
      sequenceEnded: true,
    });
  }
  receiveWorkerMessage({
    id: record.id,
    type: "message",
    worker: teammate.name,
    spawnId: teammate.spawnId,
    body: record.body,
    status: record.status,
    timestamp: record.timestamp,
  });
  // Every accepted teammate-authored report reaches the leader's context as
  // its own turn; terminal statuses additionally end the report sequence.
  const finished = terminal;
  const report = {
    teammate: teammate.name,
    agent: teammate.agent,
    spawnId: teammate.spawnId,
    body: record.body,
    origin: "teammate" as const,
    eventId: record.id,
    status: record.status,
    timestamp: record.timestamp ?? Date.now(),
    finished,
  };
  if (finished) recordTerminalReport(report);
  sendUpdate(report);
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

function dispatchInboxMessage(teammate: Teammate, message: InboxMessage): void {
  const delivered = teammate.status === "working"
    ? sendWorkerSteer(teammate.name, formatDelivery([message]))
    : false;
  if (delivered) return;
  const queued = pendingDeliveries.get(teammate.name) ?? [];
  queued.push(message);
  pendingDeliveries.set(teammate.name, queued);
  ensureLivePoll();
}

/** Route the leader's addressed send_message through the same delivery path. */
export type MessageRoutingOutcome = "steered" | "queued";

export function sendLeaderMessage(
  to: string,
  message: string,
  options?: { reopen?: boolean },
): { ok: true; outcome: MessageRoutingOutcome } | { ok: false; error: string } {
  const teammate = getTeammate(to);
  if (!teammate || teammate.status === "stopped") return { ok: false, error: `No living teammate named "${to}".` };
  if (teammate.reportSequenceEnded && !options?.reopen) {
    return { ok: false, error: `@${to} already sent a terminal report. Use teammate_spawn for a new assignment or send_message with reopen=true for an explicit follow-up assignment.` };
  }
  if (options?.reopen) updateTeammate(to, { reportSequenceEnded: false });
  const envelope: InboxMessage = {
    id: randomUUID(),
    from: "leader",
    subject: messageTitle(message),
    body: message,
    timestamp: Date.now(),
  };
  const steered = teammate.status === "working" && sendWorkerSteer(teammate.name, formatDelivery([envelope]));
  if (steered) return { ok: true, outcome: "steered" };
  const queued = pendingDeliveries.get(teammate.name) ?? [];
  queued.push(envelope);
  pendingDeliveries.set(teammate.name, queued);
  ensureLivePoll();
  return { ok: true, outcome: "queued" };
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
  if (!sender) return;
  const outcome = applyClaimIntent(intent);
  if (outcome.applied) {
    verifyFailures.delete(`${intent.taskId}:${intent.spawnId}`);
    // A new holding must not inherit an in-flight gate from a previous one.
    verifyingTasks.delete(intent.taskId);
    updateTeammate(intent.worker, { currentTaskId: intent.taskId });
    return;
  }
  deliverFeedback(intent.worker, "Claim rejected", outcome.reason ?? "The task is no longer available.");
}

function applySubmissionMarker(intent: import("./types").TaskIntent): void {
  const sender = findLivingTeammate(intent);
  if (!sender) return;
  const task = getState().tasks[intent.taskId];
  if (!task || task.status !== "claimed" || task.claimedBy !== intent.worker) {
    deliverFeedback(intent.worker, "Submission rejected", `Task "${intent.taskId}" is not currently yours.`);
    return;
  }
  if (intent.status === "failed") {
    releaseTask(intent.taskId, intent.result?.trim() || "Teammate reported failure.");
    verifyFailures.delete(`${intent.taskId}:${intent.spawnId}`);
    verifyingTasks.delete(intent.taskId);
    rearmTaskNotice(intent.taskId);
    freeTeammateFromTask(intent.worker, intent.taskId);
    notifyTaskOutcome(task.subject, `${intent.worker} reported failure`, intent.result ?? "");
    return;
  }
  beginVerifyOrComplete(intent, task.verify ?? resolveAgent(sender.agent, leaderCwd)?.verify);
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

function beginVerifyOrComplete(intent: import("./types").TaskIntent, verify: string | undefined): void {
  const task = getState().tasks[intent.taskId];
  if (!task) return;
  if (!verify?.trim()) {
    finishCompletion(intent, task.subject);
    return;
  }
  // The gate is bound to this exact submission via a unique token: a
  // release/re-claim or newer submission between submit and verify resolution
  // must not let the stale result complete the new holding.
  const token = randomUUID();
  verifyingTasks.set(intent.taskId, { worker: intent.worker, spawnId: intent.spawnId, token });
  const input: VerifyReviewInput = {
    verify,
    taskSubject: task.subject,
    workerResult: intent.result ?? "",
    cwd: getTeammate(intent.worker)?.cwd || leaderCwd,
  };
  // A runner that throws synchronously or rejects is a failed gate, never a
  // silent stuck claim: the holder gets feedback and escalation still applies.
  Promise.resolve()
    .then(() => verifyGateRunner(input))
    .then((outcome) => resolveGateOutcome(intent, task.subject, token, outcome))
    .catch((error) => resolveGateOutcome(intent, task.subject, token, {
      ok: false,
      detail: truncated(`(completion review crashed) ${error instanceof Error ? error.message : String(error)}`),
    }));
}

/** Apply one gate outcome to its submission, guarded by the binding token. */
function resolveGateOutcome(
  intent: import("./types").TaskIntent,
  subject: string,
  token: string,
  outcome: VerifyReviewOutcome,
): void {
  if (verifyingTasks.get(intent.taskId)?.token !== token) return;
  verifyingTasks.delete(intent.taskId);
  const current = getState().tasks[intent.taskId];
  const stillHolds = current?.status === "claimed"
    && current.claimedBy === intent.worker
    && getTeammate(intent.worker)?.spawnId === intent.spawnId;
  if (!stillHolds) return;
  if (outcome.ok) {
    finishCompletion(intent, subject);
  } else {
    const key = `${intent.taskId}:${intent.spawnId}`;
    const reaction = reactToVerifyFailure(verifyFailures.get(key));
    verifyFailures.set(key, reaction);
    const detail = outcome.detail ?? "(no review output)";
    if (reaction.count >= VERIFY_FAILURE_ESCALATE_AFTER) {
      // An unfixable gate parks the task with its holder instead of
      // looping: no further resubmit invitations, one leader escalation.
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
      deliverFeedback(
        intent.worker,
        `Verify failed for ${intent.taskId}`,
        [`The completion gate for "${subject}" failed.`, detail, "Fix the issues and resubmit with task_submit."].join("\n"),
      );
      notifyTaskOutcome(subject, `verify gate failed for ${intent.taskId}`, detail);
    }
  }
  ensureLivePoll();
  notifyChange();
}

function finishCompletion(intent: import("./types").TaskIntent, subject: string): void {
  const task = getState().tasks[intent.taskId];
  if (!task) return;
  const completed = completeTask(intent.taskId, intent.result);
  if (!completed) return;
  verifyFailures.delete(`${intent.taskId}:${intent.spawnId}`);
  freeTeammateFromTask(intent.worker, intent.taskId);
  notifyTaskOutcome(subject, `${intent.worker} completed`, intent.result ?? "");
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

export type VerifyReviewOutcome = { ok: boolean; detail?: string };

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
    if (/^verdict:\s*pass$/i.test(candidate)) return { ok: true };
    const failMatch = /^verdict:\s*fail\b[\s:-]*(.*)$/i.exec(candidate);
    if (failMatch) {
      return { ok: false, detail: truncated(failMatch[1].trim()) || "(no reasons given)" };
    }
  }
  return { ok: false, detail: `(no ${VERIFY_VERDICT_PASS}/FAIL verdict line in the review)\n${truncated(text.trim())}` };
}

function truncated(text: string, cap = 4000): string {
  const suffix = "\n…[truncated]";
  return text.length <= cap ? text : text.slice(0, Math.max(0, cap - suffix.length)) + suffix;
}

/** Run the gate as a one-shot Pi worker: a brand-new context that inspects
 *  the working tree itself before answering. Uses the team's model resolution
 *  chain (team default, else Pi default) rather than any role pin. */
export async function runVerifyReview(input: VerifyReviewInput): Promise<VerifyReviewOutcome> {
  const outcome = await runPiWorker({
    prompt: buildVerifyReviewPrompt(input),
    cwd: input.cwd || leaderCwd,
    model: resolveSpawnModel(undefined, getTeamDefaultModel(), leaderModelRef()).model,
  });
  // A reviewer that did not exit cleanly produced no trustworthy verdict,
  // even if partial output happens to contain a PASS line.
  if (outcome.exitCode !== 0) {
    return { ok: false, detail: truncated(`reviewer exited with code ${outcome.exitCode}: ${(outcome.stderr || outcome.text || "no output").trim()}`) };
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
    const deliveries = pendingDeliveries.get(teammate.name) ?? [];
    const fresh = freshClaimableTasks(teammate.noticedTaskIds, claimableTasks());
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
    const prompt = buildWakePrompt(deliveries, noticed, dueNotice);
    if (!deliverPrompt(teammate.name, prompt)) continue;
    notified.push(teammate.name);
    pendingDeliveries.delete(teammate.name);
    if (dueNotice) markTasksNoticed(teammate.name, noticed.map((task) => task.id));
    // A delivered prompt is fresh activity: restart the silence clock so a
    // long-idle teammate is never insta-flagged as stalled on wake.
    updateTeammate(teammate.name, {
      status: "working",
      sequenceEnded: false,
      reportSequenceEnded: false,
      lastOutputAt: Date.now(),
      stallNoticeSentAt: undefined,
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
    sections.push(`=== BOARD NOTICE ===\nUnclaimed tasks: ${listed}\nUse task_list for details and task_claim to take one if appropriate for your role.`);
  }
  if (sections.length === 0) return "";
  return `Wake up. New activity for you:\n\n${sections.join("\n\n")}\n\nHandle the items above, then go idle again.`;
}

function formatDelivery(messages: InboxMessage[]): string {
  return messages.map((message) => `From ${message.from} · ${message.subject}\n${message.body}`).join("\n\n---\n\n");
}

// ── Board helpers shared with tools.ts ────────────────────────────

export interface BoardTaskCreationResult {
  ok: true;
  id: string;
  notifiedTeammates: string[];
  livingTeammates: number;
  claimable: boolean;
}

export function formatBoardTaskCreation(subject: string, created: BoardTaskCreationResult): string {
  const status = created.claimable ? "pending/claimable" : "pending/blocked";
  const routing = created.notifiedTeammates.length > 0
    ? `notified=${created.notifiedTeammates.map((name) => `@${name}`).join(",")}`
    : created.livingTeammates === 0
      ? "notified=none (no living teammates)"
      : "notified=none (no idle teammate)";
  const next = !created.claimable
    ? "NEXT · waits for dependencies"
    : created.livingTeammates === 0
      ? "NEXT · leader: teammate_spawn"
      : "NEXT · worker: task_claim";
  return [
    `BOARD · current session`,
    `CREATED · ${created.id} · ${status} · ${subject}`,
    `ROUTING · ${routing}`,
    next,
  ].join("\n");
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
}): BoardTaskCreationResult | { ok: false; error: string } {
  const created = createTask(input);
  if (!created.ok) return created;
  publishStateSnapshot();
  const notifiedTeammates = wakeIdleTeammates(created.task.id);
  publishStateSnapshot();
  notifyChange();
  return {
    ok: true,
    id: created.task.id,
    notifiedTeammates,
    livingTeammates: livingTeammates().length,
    claimable: claimableTasks().some((task) => task.id === created.task.id),
  };
}

export function boardOverview(): Array<import("./types").BoardTask> {
  return listTasks();
}

/** Worker-side claim attempt through an exclusive-create marker file. */
export function attemptClaim(workerName: string, spawnId: string, taskId: string): boolean {
  return createTaskIntent(claimsDir(boardDirectory()), taskId, {
    taskId,
    worker: workerName,
    spawnId,
    status: "completed",
    timestamp: Date.now(),
  });
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
    status,
    result,
    timestamp: Date.now(),
  });
}
