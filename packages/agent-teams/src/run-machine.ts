/** Run scheduling, worker lifecycle, persistence, and session resource limits. */

import { randomUUID } from "node:crypto";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { resolveAgent } from "./agents";
import { isWorkerEvent } from "./worker";
import {
  cancelBlockedDependents, cancelNode, cancelRun, clearWorkerRunEvents, clearStateDirty, isStateDirty,
  deliverToLeader, failRunTimeout, findSharedWorkspaceWriteConflict, getNode,
  getRun, getState, listNodes, listRuns, markNodeRunning, markStateDirty,
  readyPendingNodes, receiveWorkerMessage, runningNodeCount, settleRun, setNodeSpawnInfo,
  SUMMARY_NODE_ID, updateNodeSpawnProgress, updateNodeStatus,
} from "./state";
import {
  CancellationIntents, buildAutonomousPrompt, finishReportedWorker, isCompletedWorkerExit,
  POST_REPORT_GRACE_MS, spawnPiWorker, terminateWorker,
  type WorkerProcessResult,
} from "./spawner";
import { buildNodeTerminalResult } from "./terminal";
import { captureWorktreeDiff, cleanupWorktree, createWorktree, discardWorktree } from "./worktree";
import { readWorkerEvents, removeWorkerOutbox, stateFilePath, workerOutboxPath, writeStateFile } from "./statefile";

export interface DispatchCtx {
  ui: ExtensionContext["ui"];
  sessionManager?: { getSessionFile(): string | undefined };
  cwd?: string;
}

export const MAX_SESSION_WORKERS = 8;
// No default node timeout — workers run until they complete or are cancelled.
const LIVE_POLL_MS = 500;
const cancellationIntents = new CancellationIntents();
const reportedWorkerShutdowns = new Set<string>();
let liveStateFile: string | undefined;
let livePollTimer: ReturnType<typeof setInterval> | undefined;
let machineCtx: DispatchCtx | undefined;
let sendUpdate: (subject: string, body: string, runId?: string) => void = () => {};
let notifyChange: () => void = () => {};

export function initRunMachine(ctx: DispatchCtx, stateFile: string, hooks: { sendUpdate: typeof sendUpdate; notifyChange: () => void }): void {
  machineCtx = ctx;
  liveStateFile = stateFile;
  sendUpdate = hooks.sendUpdate;
  notifyChange = hooks.notifyChange;
}

export function ensureRunContext(ctx: DispatchCtx): void {
  machineCtx = ctx;
  if (!liveStateFile && ctx.sessionManager) {
    liveStateFile = stateFilePath(ctx.sessionManager.getSessionFile(), ctx.cwd ?? process.cwd());
  }
}

export function shutdownRunMachine(): void {
  if (livePollTimer) clearInterval(livePollTimer);
  livePollTimer = undefined;
  liveStateFile = undefined;
  machineCtx = undefined;
  sendUpdate = () => {};
  notifyChange = () => {};
}

function currentStateFile(): string {
  if (!liveStateFile) throw new Error("Agent Teams session state is unavailable.");
  return liveStateFile;
}

function flushStateSnapshot(): void {
  if (!liveStateFile || !isStateDirty()) return;
  try {
    writeStateFile(liveStateFile, getState());
    clearStateDirty();
  } catch {
    // Keep the dirty bit set so the next poll retries the snapshot.
  }
}

export function publishStateSnapshot(): void {
  applyWorkerEvents();
  flushStateSnapshot();
}

/** Apply complete, validated event records from every running node's outbox. */
export function applyWorkerEvents(): void {
  const stateFile = currentStateFile();
  const state = getState();
  for (const run of Object.values(state.runs)) {
    for (const node of Object.values(run.nodes)) {
      const spawn = node.spawn;
      if (!spawn || spawn.status !== "running") continue;
      const spawnId = spawn.spawnId;
      const outboxKey = `${node.workerKey}:${spawnId}`;
      const outbox = workerOutboxPath(stateFile, node.workerKey, spawnId);
      const { events, nextOffset } = readWorkerEvents(outbox, state.workerEventOffsets[outboxKey] ?? 0);
      state.workerEventOffsets[outboxKey] = nextOffset;
      for (const value of events) {
        if (!isWorkerEvent(value) || state.workerEventIds[`${spawnId}:${value.id}`]) continue;
        const event = value;
        if (event.worker !== node.workerKey || event.spawnId !== spawnId) continue;
        if (event.type === "message") {
          state.workerEventIds[`${spawnId}:${event.id}`] = spawnId;
          receiveWorkerMessage({
            id: event.id,
            worker: node.workerKey,
            spawnId,
            type: "message",
            subject: event.subject,
            body: event.body,
          });
          if (event.status && !["completed", "failed", "cancelled"].includes(node.status)) {
            if (event.status === "completed") {
              updateNodeStatus(run.id, node.id, "completed", event.body, undefined);
              requestReportedWorkerShutdown(node.workerKey, spawnId);
            } else if (event.status === "failed") {
              updateNodeStatus(run.id, node.id, "failed", undefined, event.body);
              requestReportedWorkerShutdown(node.workerKey, spawnId);
            }
          }
          continue;
        }
      }
    }
  }
}

/** End a process that already sent a terminal report, without changing its result to cancelled. */
function requestReportedWorkerShutdown(workerKey: string, spawnId: string): void {
  if (reportedWorkerShutdowns.has(spawnId)) return;
  reportedWorkerShutdowns.add(spawnId);
  void finishReportedWorker(workerKey, POST_REPORT_GRACE_MS)
    .catch(() => false)
    .finally(() => {
      reportedWorkerShutdowns.delete(spawnId);
    });
}

/** Persist final node state before compacting an exhausted per-spawn outbox. */
function compactFinishedNodeRun(stateFile: string, workerKey: string, spawnId: string): void {
  try {
    // First persist the final board while its event cursor still points past
    // every applied record. A crash here preserves replay protection.
    writeStateFile(stateFile, getState());
    clearWorkerRunEvents(workerKey, spawnId);
    writeStateFile(stateFile, getState());
    clearStateDirty();
    removeWorkerOutbox(stateFile, workerKey, spawnId);
  } catch {
    // Best-effort compaction — the in-memory board is authoritative.
  }
}


export function ensureLivePoll(): void {
  const running = listNodes().some((node) => node.status === "running");
  if (running && !livePollTimer && liveStateFile) {
    livePollTimer = setInterval(() => {
      try {
        applyWorkerEvents();
        enforceRunTimeouts();
        flushStateSnapshot();
        notifyChange();
        ensureLivePoll();
      } catch {
        // Never let a poll error break the extension.
      }
    }, LIVE_POLL_MS);
  } else if (!running && livePollTimer) {
    clearInterval(livePollTimer);
    livePollTimer = undefined;
  }
}

/** Fail runs whose run-level hard wall-clock cap was exceeded. */
function enforceRunTimeouts(): void {
  for (const run of listRuns()) {
    if (run.status !== "running" || !run.deadlineAt || Date.now() < run.deadlineAt) continue;
    const failed = failRunTimeout(run.id, `Run timed out after ${Math.round((run.timeoutMs ?? 0) / 1000)}s.`);
    if (!failed.ok) continue;
    for (const nodeId of failed.runningNodeIds) {
      // Spawn was cleared by failRunTimeout, so terminate by the stable workerKey
      // (a no-op when the child already closed).
      const node = getNode(run.id, nodeId);
      if (node) void terminateWorker(node.workerKey).catch(() => false);
    }
    onRunSettled(run.id);
    // failRunTimeout clears spawns, so those nodes' close events skip their
    // finalize path — release write-deferred nodes in OTHER runs here.
    if (machineCtx) scheduleAllRuns(machineCtx);
  }
}


// ── Run dispatch machinery ────────────────────────────────────────

/** Compact run summary for tool returns and follow-ups. When the run has a
 * synthesized __summary node result, that is shown instead of per-node
 * headlines (no truncation heuristics). */
export function buildRunSummary(runId: string): string {
  const run = getRun(runId);
  if (!run) return `Run ${runId} not found.`;
  const nodes = Object.values(run.nodes).filter((node) => node.id !== SUMMARY_NODE_ID);
  const counts = Object.values(run.nodes).reduce<Record<string, number>>((acc, node) => {
    acc[node.status] = (acc[node.status] ?? 0) + 1;
    return acc;
  }, {});
  const countsStr = Object.entries(counts).map(([status, n]) => `${status} ${n}`).join(", ");
  const lines = [`Run [${run.id}] ${countsStr}`, ""];
  if (run.summary) {
    lines.push(run.summary, "");
  } else if (nodes.length === 1) {
    const node = nodes[0];
    const deliverable = node.result?.trim() || node.errorMessage?.trim();
    if (deliverable) lines.push(deliverable, "");
  } else {
    for (const node of nodes) {
      const deliverable = node.result?.trim() || node.errorMessage?.trim();
      if (deliverable) {
        lines.push(`### [${node.id}] (${node.agent}):`, deliverable, "");
      }
    }
  }
  return lines.join("\n");
}

/** Called once a run reaches a terminal status. Idempotent: the leader summary
 * and follow-up fire only on the first settled observation (a run can transition
 * through settleRun once per node close). */
export function onRunSettled(runId: string): void {
  const run = getRun(runId);
  if (!run) return;
  if (run.settledMessageSent) return;
  run.settledMessageSent = true;
  markStateDirty();
  const summary = buildRunSummary(runId);
  deliverToLeader({ from: run.id, subject: `Run ${run.status}`, body: summary, runId: runId });
  if (run.background && !run.completionNotified) {
    // One follow-up only when no other delivery path (wait/foreground gather)
    // has already consumed the run's completion.
    run.completionNotified = true;
    markStateDirty();
    sendUpdate(`Run ${run.status}`, summary, runId);
  }
  publishStateSnapshot();
  notifyChange();
}

/**
 * Start ready nodes of a run up to its concurrency budget. Root nodes start
 * immediately; downstream nodes auto-start when their dependencies complete.
 */
export function scheduleRun(runId: string, ctx: DispatchCtx): void {
  const run = getRun(runId);
  if (!run || run.status !== "running") return;
  const settled = settleRun(runId);
  if (settled !== "running") {
    onRunSettled(runId);
    return;
  }
  const sessionBudget = MAX_SESSION_WORKERS - listNodes().filter((node) => node.status === "running").length;
  const budget = Math.min(run.concurrency - runningNodeCount(runId), sessionBudget);
  if (budget <= 0) return;
  const ready = readyPendingNodes(run);
  let started = 0;
  for (const node of ready) {
    if (started >= budget) break;
    if (!run.worktree) {
      const conflict = findSharedWorkspaceWriteConflict(runId, node.id);
      if (conflict) continue; // deferred until the overlapping writer finishes
    }
    startNode(runId, node.id, ctx);
    started++;
  }
}

/**
 * Re-schedule every running run. Write-conflict detection spans runs, so a
 * node reaching a terminal state in one run can release a deferred write node
 * in a DIFFERENT run — every termination path schedules all runs, not just
 * its own.
 */
export function scheduleAllRuns(ctx: DispatchCtx): void {
  for (const run of [...listRuns()].sort((left, right) => left.createdAt - right.createdAt)) {
    if (run.status === "running") scheduleRun(run.id, ctx);
  }
}

/**
 * Cancel one node (and its not-yet-started dependents) and terminate its live
 * workers with SIGTERM→SIGKILL. Shared by the teammate_cancel tool and the
 * /teammate console's `x` key so both paths leave identical state.
 */
export async function cancelNodeAndTerminate(
  runId: string,
  nodeId: string,
  ctx: DispatchCtx,
): Promise<{ ok: true; stopped: number } | { ok: false; error: string }> {
  const cancelled = cancelNode(runId, nodeId);
  if (!cancelled.ok) return { ok: false, error: cancelled.error ?? "Failed to cancel node." };
  for (const id of cancelled.runningNodeIds) {
    const node = getNode(runId, id);
    if (!node?.spawn) continue;
    const spawnId = node.spawn.spawnId;
    if (cancellationIntents.begin(spawnId)) {
      const terminated = await terminateWorker(node.workerKey);
      cancellationIntents.resolve(spawnId, terminated);
    }
  }
  publishStateSnapshot();
  scheduleAllRuns(ctx);
  notifyChange();
  return { ok: true, stopped: cancelled.runningNodeIds.length };
}

export async function cancelRunAndTerminate(
  runId: string,
  ctx: DispatchCtx,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const run = getRun(runId);
  if (!run) return { ok: false, error: `Run "${runId}" not found.` };
  if (run.status !== "running") return { ok: false, error: `Run "${runId}" is already ${run.status}.` };
  const cancellation = cancelRun(runId);
  if (!cancellation.ok) return { ok: false, error: cancellation.error ?? "Failed to cancel run." };
  run.status = "cancelled";
  run.finishedAt = Date.now();
  run.updatedAt = Date.now();
  run.completionNotified = true;
  markStateDirty();
  for (const nodeId of cancellation.runningNodeIds) {
    const node = getNode(runId, nodeId);
    const spawnId = node?.spawn?.spawnId;
    if (!node?.spawn || !spawnId || !cancellationIntents.begin(spawnId)) continue;
    const terminated = await terminateWorker(node.workerKey);
    cancellationIntents.resolve(spawnId, terminated);
  }
  publishStateSnapshot();
  onRunSettled(runId);
  scheduleAllRuns(ctx);
  notifyChange();
  return { ok: true };
}

/** Spawn one node's worker process. Always asynchronous; the node settles via
 * finalizeNode when the child closes. */
export function startNode(runId: string, nodeId: string, ctx: DispatchCtx): void {
  const run = getRun(runId);
  const node = run?.nodes[nodeId];
  if (!run || !node || node.status !== "pending") return;
  const agent = resolveAgent(node.agent, run.cwd);
  const stateFile = liveStateFile ?? (ctx.sessionManager ? stateFilePath(ctx.sessionManager.getSessionFile(), run.cwd) : "");
  if (!agent || !stateFile) {
    updateNodeStatus(runId, nodeId, "failed", undefined, agent ? "Shared state file unavailable." : `Agent "${node.agent}" not found.`);
    cancelBlockedDependents(runId, nodeId);
    scheduleRun(runId, ctx);
    return;
  }

  const spawnId = randomUUID();
  markNodeRunning(runId, nodeId);

  // Optional git worktree isolation: run the node on its own branch.
  let worktree: ReturnType<typeof createWorktree> | undefined;
  if (run.worktree) {
    worktree = createWorktree(run.cwd, `${runId}-${nodeId}`);
    if ("error" in worktree) {
      updateNodeStatus(runId, nodeId, "failed", undefined, `Cannot isolate node: ${worktree.error}`);
      cancelBlockedDependents(runId, nodeId);
      scheduleRun(runId, ctx);
      return;
    }
  }
  const workerCwd = worktree && !("error" in worktree) ? worktree.cwd : run.cwd;
  const workerKey = node.workerKey;
  const outboxFile = workerOutboxPath(stateFile, workerKey, spawnId);
  const workerEnv = {
    PI_TEAMMATE_WORKER_NAME: workerKey,
    PI_TEAMMATE_TASK_ID: node.id,
    PI_TEAMMATE_SPAWN_ID: spawnId,
    PI_TEAMMATE_OUTBOX_FILE: outboxFile,
  };
  setNodeSpawnInfo(runId, nodeId, {
    spawnId,
    pid: 0,
    status: "running",
    startedAt: Date.now(),
    isolation: run.worktree ? "worktree" : "none",
  });

  const timeoutMs = node.timeoutMs;
  const upstream = node.dependsOn
    .map((depId) => run.nodes[depId])
    .filter((dep): dep is NonNullable<typeof dep> => Boolean(dep))
    .map((dep) => {
      const body = dep.result?.trim() || dep.errorMessage?.trim() || `${dep.status} with no written result.`;
      return `--- ${dep.id} (${dep.agent}, ${dep.status}) ---\n${body}`;
    });
  const description = [
    buildAutonomousPrompt({
      name: `${runId}/${nodeId} (${node.agent})`,
      role: node.agent,
      prompt: agent.prompt,
      taskId: nodeId,
      timeoutSec: timeoutMs ? Math.round(timeoutMs / 1000) : undefined,
    }),
    "",
    "=== TASK ===",
    `Access: ${node.access}`,
    `Paths: ${node.paths.join(", ")}`,
    node.prompt,
    ...(upstream.length > 0 ? ["", "=== UPSTREAM HANDOFF ===", ...upstream] : []),
  ].join("\n");

  const finalizeNode = (result: WorkerProcessResult, cancelled = false) => {
    // A stale close from an older spawn must not affect this node's newer spawn.
    if (getNode(runId, nodeId)?.spawn?.spawnId !== spawnId) {
      if (worktree && !("error" in worktree)) cleanupWorktree(worktree);
      return;
    }
    // Drain validated worker events before recording the final process outcome.
    applyWorkerEvents();
    let patchText = "";
    if (worktree && !("error" in worktree)) {
      const diff = captureWorktreeDiff(worktree);
      if (diff.patch.trim()) {
        patchText = `\n\n=== Worktree changes ===\n${diff.diffStat}\n\n${diff.patch}`;
      }
      cleanupWorktree(worktree);
    }
    const nodeNow = getNode(runId, nodeId);
    const reportedTerminalStatus = nodeNow?.status === "completed" || nodeNow?.status === "failed"
      ? nodeNow.status
      : undefined;
    const completedAfterFinalResponse = nodeNow?.spawn?.finalResponse === true;
    const workerReportedFailure = reportedTerminalStatus === "failed";
    const completedAfterShutdown = (reportedTerminalStatus === "completed" || completedAfterFinalResponse)
      && (result.signal === "SIGTERM" || result.exitCode === 128 + 15 || result.timedOut);
    const ok = isCompletedWorkerExit(
      result,
      reportedTerminalStatus === "completed" || completedAfterFinalResponse,
    ) && !workerReportedFailure && !cancelled;
    setNodeSpawnInfo(runId, nodeId, {
      spawnId: spawnId,
      pid: result.pid,
      status: ok ? "completed" : "failed",
      startedAt: nodeNow?.spawn?.startedAt ?? Date.now(),
      finishedAt: Date.now(),
      exitCode: result.exitCode ?? undefined,
      stdout: (result.stdout + patchText).trim() ? result.stdout + patchText : undefined,
      stderr: ok ? undefined : result.stderr,
      usage: result.usage,
      timedOut: result.timedOut,
      isolation: run.worktree ? "worktree" : "none",
      error: ok
        ? undefined
        : result.timedOut
          ? `Worker timed out after ${Math.round((timeoutMs ?? 0) / 1000)}s.`
          : result.signal
            ? `Worker was terminated by ${result.signal}.`
            : workerReportedFailure
              ? nodeNow?.errorMessage ?? "Worker reported task failure."
              : `Worker exited with code ${result.exitCode ?? "unknown"}.`,
    });
    reportedWorkerShutdowns.delete(spawnId);
    // A successful summary node becomes the run's headline result.
    if (ok && node.id === SUMMARY_NODE_ID) {
      const settledRun = getRun(runId);
      if (settledRun) {
        settledRun.summary = nodeNow?.result ?? result.stdout;
        markStateDirty();
      }
    }
    const terminalSubject = cancelled ? "Node cancelled" : ok ? "Node completed" : "Node failed";
    const terminalBody = buildNodeTerminalResult({
      runId,
      nodeId,
      agent: node.agent,
      result,
      nodeResult: nodeNow?.result,
      nodeError: nodeNow?.errorMessage,
      cancelled,
      completedAfterShutdown,
      patchText,
    });
    deliverToLeader({ from: workerKey, subject: terminalSubject, body: terminalBody, runId: runId });
    if (cancelled) {
      // A cancelled node keeps its process outcome but not a misleading error.
      const cleared = getNode(runId, nodeId);
      if (cleared) cleared.errorMessage = undefined;
      updateNodeStatus(runId, nodeId, "cancelled", nodeNow?.result, undefined);
    } else if (!ok) {
      // A failed node cancels its not-yet-started transitive dependents.
      cancelBlockedDependents(runId, nodeId);
    }
    compactFinishedNodeRun(stateFile, workerKey, spawnId);
    scheduleAllRuns(ctx);
    notifyChange();
  };

  const finish = (result: WorkerProcessResult) => {
    if (cancellationIntents.defer(spawnId, (cancelled) => finalizeNode(result, cancelled))) return;
    finalizeNode(result);
  };

  const spawnFailure = (error: Error | string) => {
    if (getNode(runId, nodeId)?.spawn?.spawnId !== spawnId) return;
    setNodeSpawnInfo(runId, nodeId, {
      spawnId: spawnId,
      pid: 0,
      status: "failed",
      startedAt: node.spawn?.startedAt ?? Date.now(),
      finishedAt: Date.now(),
      isolation: run.worktree ? "worktree" : "none",
      error: typeof error === "string" ? error : error.message,
    });
    reportedWorkerShutdowns.delete(spawnId);
    deliverToLeader({
      from: workerKey,
            subject: "Node failed",
      body: `Node [${runId}/${nodeId}] could not start.\nError: ${typeof error === "string" ? error : error.message}`,
      runId: runId,
    });
    cancelBlockedDependents(runId, nodeId);
    compactFinishedNodeRun(stateFile, workerKey, spawnId);
    if (worktree && !("error" in worktree)) discardWorktree(worktree);
    scheduleAllRuns(ctx);
    notifyChange();
  };

  const started = spawnPiWorker({
    workerName: workerKey,
    description,
    model: node.model ?? agent.model,
    tools: agent.tools,
    cwd: workerCwd,
    env: workerEnv,
    timeoutMs,
    onUpdate: (progress) => {
      updateNodeSpawnProgress(runId, nodeId, spawnId, {
        liveText: progress.text,
        activeTool: progress.activeTool,
        liveThinking: progress.liveThinking,
        turns: progress.turns,
        finalResponse: progress.finalResponse,
      });
      if (progress.finalResponse) requestReportedWorkerShutdown(workerKey, spawnId);
      notifyChange();
    },
    onExit: (result) => finish(result),
    onError: (error) => spawnFailure(error),
  });

  if ("error" in started) {
    spawnFailure(started.error);
    return;
  }

  setNodeSpawnInfo(runId, nodeId, {
    spawnId: spawnId,
    pid: started.pid,
    status: "running",
    startedAt: node.spawn?.startedAt ?? Date.now(),
    isolation: run.worktree ? "worktree" : "none",
  });
  ensureLivePoll();
  publishStateSnapshot();
  notifyChange();
}

