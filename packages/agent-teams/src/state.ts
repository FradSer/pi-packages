/**
 * Run-centric state management for the current session only.
 *
 * A run is a dispatched dependency-aware task graph; each node is one bounded
 * child-process worker with a mailbox identity of `${runId}:${nodeId}`.
 */

import type { MailboxMessage, Node, NodeStatus, Run, RunStatus, SpawnInfo, TeammateState, WorkerMessageEvent } from "./types";

function emptyState(): TeammateState {
  return {
    runs: {},
    mailboxes: {},
    messageCounter: 0,
    runCounter: 0,
    workerEventOffsets: {},
    workerEventIds: {},
  };
}

let state = emptyState();

function nextMessageId(): string {
  return `msg_${++state.messageCounter}`;
}

function nextRunId(): string {
  return `run_${++state.runCounter}`;
}

export function resetState(): void {
  state = emptyState();
}

// ── Path normalization ────────────────────────────────────────────

export function pathsOverlap(left: string, right: string): boolean {
  return left === "." || right === "." || left === right || left.startsWith(`${right}/`) || right.startsWith(`${left}/`);
}

export function normalizeNodePaths(paths: string[]): { ok: true; paths: string[] } | { ok: false; error: string } {
  if (paths.length === 0) return { ok: false, error: "Provide at least one node path." };
  const normalized: string[] = [];
  for (const rawPath of paths) {
    const candidate = rawPath.replaceAll("\\", "/").replace(/^\.\//, "").replace(/\/+$/, "");
    const valid = candidate === "." || (
      candidate
      && !/^[A-Za-z]:\//.test(candidate)
      && !candidate.startsWith("/")
      && !/[*?[\]{}]/.test(candidate)
      && candidate.split("/").every((part) => part !== "" && part !== "." && part !== "..")
    );
    if (!valid) return { ok: false, error: `Invalid node path: "${rawPath}".` };
    if (normalized.includes(candidate)) return { ok: false, error: `Duplicate node path: "${rawPath}".` };
    if (normalized.some((path) => pathsOverlap(path, candidate))) {
      return { ok: false, error: `Overlapping node paths: "${rawPath}".` };
    }
    normalized.push(candidate);
  }
  return { ok: true, paths: normalized };
}

// ── Run creation ──────────────────────────────────────────────────

export interface RunNodeInput {
  id: string;
  agent: string;
  prompt: string;
  paths: string[];
  access: Node["access"];
  model?: string;
  timeoutMs?: number;
  dependsOn: string[];
}

/** Reserved node id for the optional synthesized summary. */
export const SUMMARY_NODE_ID = "__summary";

/** System-generated task text for the summary node. */
function summaryNodePrompt(): string {
  return [
    "You are the final summary step of this run. Read the shared state snapshot",
    "(state.json) and the results of every completed node, then write ONE concise",
    "final summary covering: overall outcome, what changed or was produced,",
    "verification status, confirmed risks or failures, and recommended follow-ups.",
    "Synthesize — do not repeat node results verbatim and do not report your own",
    "plan or process. The leader sees this summary as the run's headline result.",
  ].join(" ");
}

/**
 * Create a run from validated task inputs. Rejects duplicate node ids,
 * unknown dependsOn references, dependency cycles, and invalid paths before
 * any worker starts. When summarize=true, appends a reserved summary node that
 * depends on every leaf node.
 */
export function createRun(
  input: {
    cwd: string;
    concurrency: number;
    worktree: boolean;
    background?: boolean;
    timeoutMs?: number;
    summarize?: boolean;
    summaryAgent?: string;
    nodes: RunNodeInput[];
  },
): { ok: true; run: Run } | { ok: false; error: string } {
  if (input.nodes.length === 0) return { ok: false, error: "Provide at least one task." };
  const summarize = input.summarize ?? input.nodes.length > 1;
  if (summarize && input.nodes.some((node) => node.id === SUMMARY_NODE_ID)) {
    return { ok: false, error: `Node id "${SUMMARY_NODE_ID}" is reserved for the run summary.` };
  }

  const ids = new Set<string>();
  const normalized: Node[] = [];
  for (const node of input.nodes) {
    if (ids.has(node.id)) return { ok: false, error: `Duplicate node id: "${node.id}".` };
    ids.add(node.id);
    const normalizedPaths = normalizeNodePaths(node.paths);
    if (!normalizedPaths.ok) return normalizedPaths;
    for (const dep of node.dependsOn) {
      if (!ids.has(dep) && !input.nodes.some((candidate) => candidate.id === dep)) {
        return { ok: false, error: `Node "${node.id}" depends on unknown node "${dep}".` };
      }
    }
    normalized.push({
      id: node.id,
      workerKey: "", // filled after the run id is assigned
      agent: node.agent,
      prompt: node.prompt,
      paths: normalizedPaths.paths,
      access: node.access,
      model: node.model,
      timeoutMs: node.timeoutMs,
      dependsOn: [...new Set(node.dependsOn)],
      status: "pending",
      createdAt: Date.now(),
      updatedAt: Date.now(),
    });
  }

  // Cycle detection (DFS over the dependency edges).
  const visiting = new Set<string>();
  const visited = new Set<string>();
  const visit = (id: string): boolean => {
    if (visiting.has(id)) return true;
    if (visited.has(id)) return false;
    visiting.add(id);
    const node = normalized.find((candidate) => candidate.id === id)!;
    for (const dep of node.dependsOn) {
      if (visit(dep)) return true;
    }
    visiting.delete(id);
    visited.add(id);
    return false;
  };
  for (const node of normalized) {
    if (visit(node.id)) return { ok: false, error: "The task graph contains a dependency cycle." };
  }

  // Synthesized summary: default on for multi-node runs. Depends on every leaf.
  if (summarize) {
    const leaves = normalized.filter((node) => !normalized.some((other) => other.dependsOn.includes(node.id)));
    if (leaves.length > 0) {
      normalized.push({
        id: SUMMARY_NODE_ID,
        workerKey: "",
        agent: input.summaryAgent ?? "observer",
        prompt: summaryNodePrompt(),
        paths: ["."],
        access: "read",
        dependsOn: leaves.map((node) => node.id),
        status: "pending",
        createdAt: Date.now(),
        updatedAt: Date.now(),
      });
    }
  }

  const runId = nextRunId();
  const run: Run = {
    id: runId,
    cwd: input.cwd,
    status: "running",
    concurrency: input.concurrency,
    worktree: input.worktree,
    background: input.background ?? true,
    timeoutMs: input.timeoutMs,
    deadlineAt: input.timeoutMs ? Date.now() + input.timeoutMs : undefined,
    nodes: {},
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
  for (const node of normalized) {
    node.workerKey = `${runId}:${node.id}`;
    run.nodes[node.id] = node;
    if (!state.mailboxes[node.workerKey]) state.mailboxes[node.workerKey] = [];
  }
  state.runs[runId] = run;
  return { ok: true, run };
}

// ── Run / node queries ────────────────────────────────────────────

export function getRun(runId: string): Run | undefined {
  return state.runs[runId];
}

export function getNode(runId: string, nodeId: string): Node | undefined {
  return state.runs[runId]?.nodes[nodeId];
}

export function getNodeByWorkerKey(workerKey: string): { run: Run; node: Node } | undefined {
  for (const run of Object.values(state.runs)) {
    const node = Object.values(run.nodes).find((candidate) => candidate.workerKey === workerKey);
    if (node) return { run, node };
  }
  return undefined;
}

export function listRuns(): Run[] {
  return Object.values(state.runs).sort((a, b) => b.updatedAt - a.updatedAt);
}

export function runningNodeCount(runId: string): number {
  const run = state.runs[runId];
  if (!run) return 0;
  return Object.values(run.nodes).filter((node) => node.status === "running").length;
}

export function isRunTerminal(run: Run): boolean {
  return run.status === "completed" || run.status === "failed" || run.status === "cancelled";
}

/** Claim a run's completion delivery so the follow-up is suppressed (foreground gather). */
export function markRunCompletionDelivered(runId: string): void {
  const run = state.runs[runId];
  if (run) run.completionNotified = true;
}

/** Every node across every run (for console rows and liveness polls). */
export function listNodes(): Node[] {
  return Object.values(state.runs).flatMap((run) => Object.values(run.nodes));
}

// ── Node lifecycle ────────────────────────────────────────────────

export function markNodeRunning(runId: string, nodeId: string): { ok: boolean; error?: string } {
  const node = getNode(runId, nodeId);
  if (!node) return { ok: false, error: `Node "${nodeId}" not found.` };
  node.status = "running";
  node.updatedAt = Date.now();
  state.runs[runId].updatedAt = Date.now();
  return { ok: true };
}

export function updateNodeStatus(
  runId: string,
  nodeId: string,
  status: NodeStatus,
  result?: string,
  errorMessage?: string,
): { ok: boolean; node?: Node; error?: string } {
  const node = getNode(runId, nodeId);
  if (!node) return { ok: false, error: `Node "${nodeId}" not found.` };
  node.status = status;
  node.updatedAt = Date.now();
  if (result !== undefined) node.result = result;
  if (errorMessage !== undefined) node.errorMessage = errorMessage;
  if (status === "completed" || status === "failed" || status === "cancelled") {
    node.completedAt = Date.now();
  }
  state.runs[runId].updatedAt = Date.now();
  return { ok: true, node };
}

/**
 * Attach child-process execution info to a node and derive its status from
 * the spawn outcome (unless the node was cancelled).
 */
export function setNodeSpawnInfo(runId: string, nodeId: string, info: SpawnInfo): { ok: boolean; node?: Node; error?: string } {
  const node = getNode(runId, nodeId);
  if (!node) return { ok: false, error: `Node "${nodeId}" not found.` };
  node.spawn = info;
  node.updatedAt = Date.now();
  state.runs[runId].updatedAt = Date.now();

  if (info.status === "running") {
    // A live spawn implies the node is running (idempotent with markNodeRunning).
    if (node.status === "pending") node.status = "running";
  } else if (info.status === "completed" && node.status !== "cancelled") {
    node.status = "completed";
    node.completedAt = Date.now();
    if (info.stdout && node.result === undefined) node.result = info.stdout;
  } else if (info.status === "failed" && node.status !== "cancelled") {
    node.status = "failed";
    node.completedAt = Date.now();
    node.errorMessage = info.error ?? info.stderr ?? `Child process exited with code ${info.exitCode ?? "unknown"}.`;
  }
  return { ok: true, node };
}

/** Merge a streaming child-process update into its matching running node. */
export function updateNodeSpawnProgress(
  runId: string,
  nodeId: string,
  spawnId: string,
  progress: Pick<SpawnInfo, "liveText" | "activeTool" | "liveThinking" | "turns" | "finalResponse">,
): { ok: boolean; node?: Node; error?: string } {
  const node = getNode(runId, nodeId);
  if (!node) return { ok: false, error: `Node "${nodeId}" not found.` };
  if (node.spawn?.runId !== spawnId || node.spawn.status !== "running") {
    return { ok: false, error: `Node "${nodeId}" is not running the expected worker.` };
  }
  node.spawn.liveText = progress.liveText;
  node.spawn.activeTool = progress.activeTool;
  node.spawn.liveThinking = progress.liveThinking;
  node.spawn.turns = progress.turns;
  node.spawn.finalResponse = progress.finalResponse;
  node.updatedAt = Date.now();
  state.runs[runId].updatedAt = Date.now();
  return { ok: true, node };
}

// ── Dependency readiness ──────────────────────────────────────────

/** A node is ready when every dependency has completed. */
export function nodeIsReady(run: Run, node: Node): boolean {
  return node.dependsOn.every((dep) => run.nodes[dep]?.status === "completed");
}

/** Nodes that are pending, have no unmet dependencies, and are not yet spawned. */
export function readyPendingNodes(run: Run): Node[] {
  return Object.values(run.nodes)
    .filter((node) => node.status === "pending" && nodeIsReady(run, node))
    .sort((a, b) => a.id.localeCompare(b.id));
}

/**
 * The running shared-workspace write node whose paths overlap this node's,
 * if any. Searched across EVERY run in the session: a write node deferred in
 * one run must also wait for an overlapping writer dispatched by another run.
 * Worktree-isolated nodes never conflict. This is advisory scheduling
 * coordination — it defers node starts; it does not isolate file access.
 */
export function findSharedWorkspaceWriteConflict(runId: string, nodeId: string): Node | undefined {
  const run = state.runs[runId];
  const node = run?.nodes[nodeId];
  if (!run || !node || node.access !== "write") return undefined;
  for (const candidateRun of Object.values(state.runs)) {
    for (const other of Object.values(candidateRun.nodes)) {
      if (candidateRun.id === runId && other.id === node.id) continue;
      if (
        other.status === "running"
        && other.spawn?.status === "running"
        && other.spawn.isolation !== "worktree"
        && other.access === "write"
        && node.paths.some((path) => other.paths.some((otherPath) => pathsOverlap(path, otherPath)))
      ) {
        return other;
      }
    }
  }
  return undefined;
}

/** Cancel pending nodes that transitively depend on the given node. */
export function cancelBlockedDependents(runId: string, nodeId: string): number {
  const run = state.runs[runId];
  if (!run) return 0;
  const cancelled = new Set<string>([nodeId]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const node of Object.values(run.nodes)) {
      if (node.status !== "pending" || cancelled.has(node.id)) continue;
      if (node.dependsOn.some((dep) => cancelled.has(dep))) {
        node.status = "cancelled";
        node.completedAt = Date.now();
        node.updatedAt = Date.now();
        cancelled.add(node.id);
        changed = true;
      }
    }
  }
  run.updatedAt = Date.now();
  return cancelled.size - 1;
}

// ── Run settlement ────────────────────────────────────────────────

/**
 * Recompute a running run's status from its nodes. Settles only when no node
 * is running or pending: any failed node fails the run, an all-cancelled run
 * is cancelled, otherwise the run completed.
 */
export function settleRun(runId: string): RunStatus | undefined {
  const run = state.runs[runId];
  if (!run) return undefined;
  if (run.status !== "running") return run.status;
  const nodes = Object.values(run.nodes);
  const anyActive = nodes.some((node) => node.status === "running" || node.status === "pending");
  if (anyActive) return "running";
  if (nodes.some((node) => node.status === "failed")) {
    run.status = "failed";
  } else if (nodes.every((node) => node.status === "cancelled")) {
    run.status = "cancelled";
  } else {
    run.status = "completed";
  }
  run.finishedAt = Date.now();
  run.updatedAt = Date.now();
  return run.status;
}

// ── Cancel / cleanup ──────────────────────────────────────────────

/**
 * Mark a running run's pending nodes cancelled. Returns the ids of nodes with
 * live workers that the caller must terminate.
 */
export function cancelRun(runId: string): { ok: boolean; runningNodeIds: string[]; error?: string } {
  const run = state.runs[runId];
  if (!run) return { ok: false, runningNodeIds: [], error: `Run "${runId}" not found.` };
  if (isRunTerminal(run)) return { ok: false, runningNodeIds: [], error: `Run "${runId}" is already ${run.status}.` };
  const runningNodeIds: string[] = [];
  for (const node of Object.values(run.nodes)) {
    if (node.status === "running") {
      runningNodeIds.push(node.id);
    } else if (node.status === "pending") {
      node.status = "cancelled";
      node.completedAt = Date.now();
      node.updatedAt = Date.now();
    }
  }
  run.updatedAt = Date.now();
  return { ok: true, runningNodeIds };
}

/** Cancel a single node (and its not-yet-started transitive dependents).
 * Returns the ids of nodes with live workers the caller must terminate,
 * including running dependents whose cancelled prerequisites invalidate them. */
export function cancelNode(runId: string, nodeId: string): { ok: boolean; runningNodeIds: string[]; error?: string } {
  const run = state.runs[runId];
  const node = run?.nodes[nodeId];
  if (!run || !node) return { ok: false, runningNodeIds: [], error: `Node "${nodeId}" not found in run "${runId}".` };
  if (node.status === "completed" || node.status === "failed" || node.status === "cancelled") {
    return { ok: false, runningNodeIds: [], error: `Node "${nodeId}" is already ${node.status}.` };
  }

  // Cancel pending transitive dependents of the target.
  cancelBlockedDependents(runId, nodeId);

  // Propagate to RUNNING dependents whose (now cancelled) prerequisites make
  // their remaining work meaningless; the caller terminates their workers and
  // finalizeNode records them cancelled.
  const runningDependents: string[] = [];
  const invalidated = new Set<string>([nodeId]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const candidate of Object.values(run.nodes)) {
      if (candidate.status === "cancelled") {
        invalidated.add(candidate.id);
        continue;
      }
      if (candidate.status === "running" && !invalidated.has(candidate.id)
        && candidate.dependsOn.some((dep) => invalidated.has(dep))) {
        invalidated.add(candidate.id);
        runningDependents.push(candidate.id);
        changed = true;
      }
    }
  }

  const runningNodeIds: string[] = [];
  if (node.status === "running") {
    runningNodeIds.push(node.id);
  } else if (node.status === "pending") {
    node.status = "cancelled";
    node.completedAt = Date.now();
    node.updatedAt = Date.now();
  }
  for (const id of runningDependents) {
    if (!runningNodeIds.includes(id)) runningNodeIds.push(id);
  }
  run.updatedAt = Date.now();
  return { ok: true, runningNodeIds };
}

/**
 * Fail a run for exceeding its hard wall-clock cap: pending nodes are
 * cancelled and the run is marked failed; live workers must be terminated by
 * the caller.
 */
export function failRunTimeout(runId: string, errorMessage: string): { ok: boolean; runningNodeIds: string[]; error?: string } {
  const run = state.runs[runId];
  if (!run) return { ok: false, runningNodeIds: [], error: `Run "${runId}" not found.` };
  if (run.status !== "running") return { ok: false, runningNodeIds: [], error: `Run "${runId}" is already ${run.status}.` };
  const runningNodeIds: string[] = [];
  for (const node of Object.values(run.nodes)) {
    if (node.status === "running") {
      // The node's worker is terminated by the caller; clearing the spawn means
      // its late close event cannot pollute a retried (reset) node.
      node.status = "failed";
      node.errorMessage = errorMessage;
      node.completedAt = Date.now();
      node.spawn = undefined;
      node.updatedAt = Date.now();
      runningNodeIds.push(node.id);
    } else if (node.status === "pending") {
      node.status = "cancelled";
      node.completedAt = Date.now();
      node.updatedAt = Date.now();
    }
  }
  run.status = "failed";
  run.errorMessage = errorMessage;
  run.finishedAt = Date.now();
  run.updatedAt = Date.now();
  return { ok: true, runningNodeIds };
}

/**
 * Reset failed and cancelled nodes of a settled run back to pending so the
 * run can be re-dispatched. Completed nodes are retained. The run returns to
 * running; callers must scheduleRun afterwards.
 */
export function retryRun(runId: string, nodeIds?: string[]): { ok: boolean; reset: string[]; error?: string } {
  const run = state.runs[runId];
  if (!run) return { ok: false, reset: [], error: `Run "${runId}" not found.` };
  if (run.status === "running") return { ok: false, reset: [], error: `Run "${runId}" is still running; wait for it to settle first.` };
  const targets = nodeIds && nodeIds.length > 0 ? nodeIds : [];
  for (const id of targets) {
    if (!run.nodes[id]) return { ok: false, reset: [], error: `Node "${id}" not found in run "${runId}".` };
  }

  // Explicit targets may only reset failed or cancelled nodes.
  const resetSet = new Set<string>();
  for (const node of Object.values(run.nodes)) {
    if (targets.length > 0 && !targets.includes(node.id)) continue;
    if (node.status !== "failed" && node.status !== "cancelled") {
      if (targets.includes(node.id)) {
        return { ok: false, reset: [], error: `Node "${node.id}" is ${node.status}, not failed or cancelled.` };
      }
      continue;
    }
    resetSet.add(node.id);
  }

  // Propagate to cancelled dependents whose (now reset) prerequisites failed:
  // a targeted retry of node A must also re-run B, which was cancelled because
  // it depended on A.
  let changed = true;
  while (changed) {
    changed = false;
    for (const node of Object.values(run.nodes)) {
      if (resetSet.has(node.id) || node.status !== "cancelled") continue;
      if (node.dependsOn.some((dep) => resetSet.has(dep))) {
        resetSet.add(node.id);
        changed = true;
      }
    }
  }

  if (resetSet.size === 0) {
    return { ok: false, reset: [], error: "No failed or cancelled nodes to retry." };
  }
  for (const node of Object.values(run.nodes)) {
    if (!resetSet.has(node.id)) continue;
    node.status = "pending";
    node.result = undefined;
    node.errorMessage = undefined;
    node.completedAt = undefined;
    node.spawn = undefined;
    node.updatedAt = Date.now();
  }
  const reset = [...resetSet];
  run.status = "running";
  run.errorMessage = undefined;
  run.finishedAt = undefined;
  run.completionNotified = false;
  run.settledMessageSent = false;
  // Re-arm the run-level cap: a stale deadline would re-fail the retried run
  // on the very next poll.
  run.deadlineAt = run.timeoutMs ? Date.now() + run.timeoutMs : undefined;
  run.updatedAt = Date.now();
  return { ok: true, reset };
}

/** Remove terminal runs and their node mailboxes. Running and pending runs are retained. */
export function pruneFinishedRuns(): number {
  let removed = 0;
  for (const [runId, run] of Object.entries(state.runs)) {
    if (!isRunTerminal(run)) continue;
    for (const node of Object.values(run.nodes)) {
      delete state.mailboxes[node.workerKey];
    }
    delete state.runs[runId];
    removed++;
  }
  return removed;
}

/** Drop per-spawn replay metadata after its final state snapshot was persisted. */
export function clearWorkerRunEvents(workerKey: string, spawnId: string): void {
  const outboxKey = `${workerKey}:${spawnId}`;
  delete state.workerEventOffsets[outboxKey];
  for (const id of Object.keys(state.workerEventIds)) {
    if (id.startsWith(`${spawnId}:`)) delete state.workerEventIds[id];
  }
}

// ── Mailbox ───────────────────────────────────────────────────────

export function sendMessage(msg: Omit<MailboxMessage, "id" | "timestamp" | "read">): MailboxMessage {
  const full: MailboxMessage = {
    ...msg,
    id: nextMessageId(),
    timestamp: Date.now(),
    read: false,
  };
  if (!state.mailboxes[msg.to]) {
    state.mailboxes[msg.to] = [];
  }
  state.mailboxes[msg.to].push(full);
  return full;
}

/** Deliver a validated worker event exactly once using the worker event ID. */
export function receiveWorkerMessage(event: WorkerMessageEvent): boolean {
  const mailbox = state.mailboxes[event.to] ?? [];
  if (mailbox.some((message) => message.id === event.id)) return false;
  mailbox.push({
    id: event.id,
    from: event.worker,
    to: event.to,
    subject: event.subject,
    body: event.body,
    taskId: event.taskId,
    timestamp: Date.now(),
    read: false,
  });
  state.mailboxes[event.to] = mailbox;
  return true;
}

/** Resolve a worker-facing recipient: team-leader, same-run node id, or runId:nodeId. */
export function resolveWorkerRecipientFromRuns(
  runs: Record<string, Run>,
  fromWorkerKey: string,
  to: string,
): { ok: true; to: string } | { ok: false; error: string } {
  if (to === "team-leader") return { ok: true, to: "team-leader" };
  const senderRun = Object.values(runs).find((run) => Object.values(run.nodes).some((node) => node.workerKey === fromWorkerKey));
  if (!senderRun) return { ok: false, error: `Unknown sender "${fromWorkerKey}".` };
  const peer = senderRun.nodes[to] ?? (to.startsWith(`${senderRun.id}:`) ? senderRun.nodes[to.slice(senderRun.id.length + 1)] : undefined);
  if (!peer) return { ok: false, error: `Unknown peer "${to}" in run "${senderRun.id}". Use a peer node id or "team-leader".` };
  if (peer.workerKey === fromWorkerKey) return { ok: false, error: "A worker cannot message itself." };
  return { ok: true, to: peer.workerKey };
}

export function resolveWorkerRecipient(fromWorkerKey: string, to: string): { ok: true; to: string } | { ok: false; error: string } {
  return resolveWorkerRecipientFromRuns(getState().runs, fromWorkerKey, to);
}

/** Resolve a leader-facing recipient: worker key, unique node id, or runId:nodeId. */
export function resolveLeaderRecipient(to: string, runId?: string): { ok: true; to: string; runId: string } | { ok: false; error: string } {
  const byKey = getNodeByWorkerKey(to);
  if (byKey) return { ok: true, to: byKey.node.workerKey, runId: byKey.run.id };
  if (runId) {
    const node = getNode(runId, to);
    if (node) return { ok: true, to: node.workerKey, runId };
  }
  const matches = listRuns().flatMap((run) => (run.nodes[to] ? [{ run, node: run.nodes[to] }] : []));
  if (matches.length === 1) return { ok: true, to: matches[0].node.workerKey, runId: matches[0].run.id };
  if (matches.length > 1) return { ok: false, error: `Node id "${to}" is ambiguous across runs; use runId:nodeId.` };
  return { ok: false, error: `Unknown node "${to}". Use a node id, runId:nodeId, or to="all" with runId.` };
}

/** Pending/running dependents of a node (direct dependsOn edges). */
export function dependentNodes(runId: string, nodeId: string): Node[] {
  const run = state.runs[runId];
  if (!run) return [];
  return Object.values(run.nodes).filter((node) => node.dependsOn.includes(nodeId));
}

/** Push a completed node's result into each dependent's inbox. */
export function handoffNodeResult(runId: string, nodeId: string): number {
  const run = state.runs[runId];
  const node = run?.nodes[nodeId];
  if (!run || !node) return 0;
  const body = node.result?.trim() || node.errorMessage?.trim() || `${node.status} with no written result.`;
  let sent = 0;
  for (const dependent of dependentNodes(runId, nodeId)) {
    sendMessage({
      from: node.workerKey,
      to: dependent.workerKey,
      subject: `Handoff from ${node.id}`,
      body: `Upstream node [${node.id}] (${node.agent}) is ${node.status}.\n\n${body}`,
      taskId: runId,
    });
    sent++;
  }
  return sent;
}

/** Every message across every mailbox (for building conversation transcripts). */
export function listAllMessages(): MailboxMessage[] {
  return Object.values(state.mailboxes).flat();
}

// ── State inspection ──────────────────────────────────────────────

export function getState(): TeammateState {
  return state;
}

export function getSummary(): string | undefined {
  const runCount = Object.keys(state.runs).length;
  if (runCount === 0) return undefined;
  const messageCount = Object.values(state.mailboxes).reduce((sum, mailbox) => sum + mailbox.length, 0);
  const activeNodes = listNodes().filter((node) => node.status === "running" || node.status === "pending").length;
  return `${runCount} run(s) | ${messageCount} message(s) | ${activeNodes} active node(s)`;
}
