/**
 * Team machine — resident teammate lifecycle, peer mail routing, task-intent
 * processing, verify gating, and the harness poll loop that wakes idle
 * teammates. The leader model never polls; this loop is the coordination
 * engine described by the BDD contract.
 */

import { exec } from "node:child_process";
import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { discoverAgents, persistAgentDefinition, registerSessionAgent, resolveAgent, type AgentDefinitionInput } from "./agents.ts";
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
  sendWorkerSteer,
  spawnResident,
  terminateAllTeammates,
  terminateTeammate,
  type WorkerProcessResult,
} from "./spawner.ts";
import { captureWorktreeDiff, cleanupWorktree, createWorktree } from "./worktree.ts";
import { messageTitle, type InboxMessage, type Teammate } from "./types.ts";
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

let livePollTimer: ReturnType<typeof setInterval> | undefined;
let generation = 0;
let runtimeStateFile = "";
let boardFile = "";
let leaderCwd = "";
let sendUpdate: (report: FollowUpReport) => void = () => {};
let notifyChange: () => void = () => {};

const pendingShutdowns = new Set<string>();
/** Task ids under verification, bound to one exact submission via token so a
 *  release/re-claim or newer submission invalidates any older in-flight gate. */
const verifyingTasks = new Map<string, { worker: string; spawnId: string; token: string }>();
/** Idle nudges already fired per teammate incarnation (one per transition). */
const idleNudgesSent = new Set<string>();
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
  ctx: Pick<ExtensionContext, "sessionManager" | "cwd">,
  hooks: MachineHooks,
): void {
  generation++;
  leaderCwd = ctx.cwd || process.cwd();
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
  sendUpdate = () => {};
  notifyChange = () => {};
  pendingShutdowns.clear();
  verifyingTasks.clear();
  idleNudgesSent.clear();
  selfFinalizeAttempts.clear();
  pendingDeliveries.clear();
  verifyFailures.clear();
}

/** Terminate every resident teammate; returns unconfirmed-close diagnostics. */
export async function teardownTeammates(): Promise<string[]> {
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
    writeRoster(rosterPath(stateFile), livingTeammates().map((t) => ({ name: t.name, agent: t.agent, status: t.status })));
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
  let agent = resolveAgent(input.agent, leaderCwd);
  if (!agent && input.definition) {
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

  const started = spawnResident({
    workerName: input.name,
    description: buildKickoffPrompt(input.name, input.agent, agent.prompt, input.prompt, isolation),
    model: agent.model,
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
  // A prompt-less spawn has no stream activity; it is idle from birth.
  if (!input.prompt?.trim()) updateTeammate(input.name, { status: "idle" });
  publishStateSnapshot();
  ensureLivePoll();
  notifyChange();
  return { ok: true, teammate: getTeammate(input.name)! };
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
  cleanupWorktree(handle);
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
  });
  updateTeammate(name, { lastOutputAt: Date.now(), stallNoticeSentAt: undefined });
  if (progress.finalResponse && teammate.status !== "idle") {
    updateTeammate(name, { status: "idle", activeTool: undefined });
    nudgeIfUnfinalized(name, spawnId);
  }
  ensureLivePoll();
}

function checkStalledTeammates(now = Date.now()): void {
  if (STALL_NOTICE_MS <= 0) return;
  for (const teammate of livingTeammates()) {
    if (teammate.status !== "working" && teammate.status !== "starting") continue;
    const silence = stallSilenceMs(teammate, now);
    if (silence === undefined) continue;
    if (silence < STALL_NOTICE_MS || teammate.stallNoticeSentAt !== undefined) continue;
    const body = `@${teammate.name} has produced no RPC output for ${formatSilenceDuration(silence)}. The child may be blocked in a provider or tool call; steer delivery is uncertain. Decide: keep waiting, steer again, or shut it down (and respawn a successor with context from the original kickoff, its mailbox reports, board claims, and the /agent-teams detail transcript).`;
    updateTeammate(teammate.name, { stallNoticeSentAt: now });
    deliverToLeader({ from: "harness", subject: `Possible stall: @${teammate.name}`, body });
    sendUpdate({ teammate: teammate.name, agent: teammate.agent, body, finished: false });
  }
}

interface VerifyFailureRecord {
  count: number;
  escalated: boolean;
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
  sendUpdate({ teammate: name, body: reminder, finished: false });
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
    publishStateSnapshot();
    notifyChange();
    return { ok: true, body: summarizeShutdown(name, released.length, 0, undefined) };
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

  deliverToLeader(requested
    ? { from: name, subject: "Teammate shut down", body: summarizeShutdown(name, released.length, result.exitCode, result.usage) }
    : { from: name, subject: "Teammate stopped unexpectedly", body: crashDiagnostic(name, result, released) });

  if (!requested) {
    sendUpdate({
      teammate: name,
      body: `@${name} stopped unexpectedly${released.length > 0 ? `; claimed task(s) ${released.map((t) => t.id).join(", ")} returned to the board` : ""}.`,
      finished: true,
    });
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
  const patchNote = captured.ok && captured.diff.patch.trim()
    ? `\n\n=== Worktree changes ===\n${captured.diff.diffStat}\n\n${captured.diff.patch}`
    : captured.ok
      ? "\n(no worktree changes)"
      : `\n(worktree diff capture failed: ${captured.error})`;
  cleanupWorktree(handle);
  deliverToLeader({
    from: name,
    subject: "Worktree diff captured",
    body: `Teammate @${name}'s worktree diff:${patchNote}`,
  });
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
  if (ids[`${teammate.spawnId}:${record.id}`]) return false;
  ids[`${teammate.spawnId}:${record.id}`] = teammate.spawnId;
  receiveWorkerMessage({
    id: record.id,
    type: "message",
    worker: teammate.name,
    spawnId: teammate.spawnId,
    body: record.body,
    status: record.status,
  });
  if (record.status === "completed" || record.status === "failed") {
    // The assignment ends; the resident itself stays alive until sequence end.
    sendUpdate({
      teammate: teammate.name,
      agent: teammate.agent,
      spawnId: teammate.spawnId,
      body: record.body,
      finished: true,
    });
  }
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
export function sendLeaderMessage(to: string, message: string): { ok: true; queued: boolean; stalledMs?: number } | { ok: false; error: string } {
  const teammate = getTeammate(to);
  if (!teammate || teammate.status === "stopped") return { ok: false, error: `No living teammate named "${to}".` };
  const envelope: InboxMessage = {
    id: randomUUID(),
    from: "leader",
    subject: messageTitle(message),
    body: message,
    timestamp: Date.now(),
  };
  const delivered = teammate.status === "working" && sendWorkerSteer(teammate.name, formatDelivery([envelope]));
  if (delivered) {
    // A control-stream write succeeds even when the child never reads it;
    // surface prolonged silence so the leader knows delivery is uncertain.
    const stalled = isStallThresholdReached(teammate, Date.now(), STALL_NOTICE_MS);
    const silence = stallSilenceMs(teammate);
    return { ok: true, queued: false, ...(stalled && silence !== undefined ? { stalledMs: silence } : {}) };
  }
  const queued = pendingDeliveries.get(teammate.name) ?? [];
  queued.push(envelope);
  pendingDeliveries.set(teammate.name, queued);
  ensureLivePoll();
  return { ok: true, queued: true };
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
  runVerifyCommand(verify)
    .then((outcome) => {
      if (verifyingTasks.get(intent.taskId)?.token !== token) return;
      verifyingTasks.delete(intent.taskId);
      const current = getState().tasks[intent.taskId];
      const stillHolds = current?.status === "claimed"
        && current.claimedBy === intent.worker
        && getTeammate(intent.worker)?.spawnId === intent.spawnId;
      if (!stillHolds) return;
      if (outcome.ok) finishCompletion(intent, task.subject);
      else {
        const key = `${intent.taskId}:${intent.spawnId}`;
        const reaction = reactToVerifyFailure(verifyFailures.get(key));
        verifyFailures.set(key, reaction);
        const detail = outcome.detail ?? "(no verify output)";
        if (reaction.count >= VERIFY_FAILURE_ESCALATE_AFTER) {
          // An unfixable gate parks the task with its holder instead of
          // looping: no further resubmit invitations, one leader escalation.
          if (reaction.escalateToLeader) {
            notifyTaskOutcome(task.subject, `verify failed ${reaction.count} times for ${intent.taskId}: manual attention needed`, detail);
          }
          deliverFeedback(
            intent.worker,
            `Verify still failing for ${intent.taskId}`,
            [`The completion gate for "${task.subject}" failed again (${reaction.count} consecutive failures).`, detail, "The task stays claimed by you. Do not resubmit or reclaim it; the leader has been notified and will decide next steps."].join("\n"),
          );
        } else {
          deliverFeedback(
            intent.worker,
            `Verify failed for ${intent.taskId}`,
            [`The completion gate for "${task.subject}" failed.`, detail, "Fix the issues and resubmit with task_submit."].join("\n"),
          );
          notifyTaskOutcome(task.subject, `verify gate failed for ${intent.taskId}`, detail);
        }
      }
      ensureLivePoll();
      notifyChange();
    })
    .catch(() => {
      if (verifyingTasks.get(intent.taskId)?.token === token) verifyingTasks.delete(intent.taskId);
    });
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

function runVerifyCommand(command: string): Promise<{ ok: boolean; detail?: string }> {
  return new Promise((resolve) => {
    exec(command, { cwd: leaderCwd, maxBuffer: 1024 * 1024 }, (error, _stdout, stderr) => {
      const code = (error as { code?: number | string } | null)?.code;
      if (error) {
        resolve({ ok: false, detail: `verify exited with code ${code ?? "unknown"}: ${(stderr || error.message).slice(0, 4000)}` });
        return;
      }
      resolve({ ok: true });
    });
  });
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
export function wakeIdleTeammates(): void {
  for (const teammate of idleTeammates()) {
    const deliveries = pendingDeliveries.get(teammate.name) ?? [];
    const fresh = freshClaimableTasks(teammate.noticedTaskIds, claimableTasks());
    const dueNotice = fresh.length > 0 && noticeDue(teammate);
    if (deliveries.length === 0 && !dueNotice) continue;
    const noticed = fresh.slice(0, WAKE_NOTICE_TASK_LIMIT);
    const prompt = buildWakePrompt(deliveries, noticed, dueNotice);
    if (!deliverPrompt(teammate.name, prompt)) continue;
    pendingDeliveries.delete(teammate.name);
    if (dueNotice) markTasksNoticed(teammate.name, noticed.map((task) => task.id));
    // A delivered prompt is fresh activity: restart the silence clock so a
    // long-idle teammate is never insta-flagged as stalled on wake.
    updateTeammate(teammate.name, {
      status: "working",
      sequenceEnded: false,
      lastOutputAt: Date.now(),
      stallNoticeSentAt: undefined,
      ...(dueNotice ? { lastNoticeAt: Date.now() } : {}),
    });
  }
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

export function createBoardTask(input: {
  subject: string;
  description?: string;
  dependsOn?: string[];
  verify?: string;
}): { ok: true; id: string } | { ok: false; error: string } {
  const created = createTask(input);
  if (!created.ok) return created;
  publishStateSnapshot();
  notifyChange();
  return { ok: true, id: created.task.id };
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
