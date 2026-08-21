/**
 * Run-centric state management for the current session only.
 *
 * A run is a dispatched dependency-aware task graph; each node is one bounded
 * child-process worker with a stable identity of `${runId}:${nodeId}`.
 */

import type { MailboxMessage, Node, NodeStatus, Run, RunStatus, SpawnInfo, TeammateState, WorkerMessageEvent } from "./types";

function emptyState(): TeammateState {
  return {
    runs: {},
    leaderMailbox: [],
    messageCounter: 0,
    runCounter: 0,
    workerEventOffsets: {},
    workerEventIds: {},
  };
}

let state = emptyState();
let stateDirty = false;

export function markStateDirty(): void {
  stateDirty = true;
}

/** Return whether state changed since the last persisted snapshot. */
export function isStateDirty(): boolean {
  return stateDirty;
}

export function clearStateDirty(): void {
  stateDirty = false;
}

/** Return whether state changed since the last persisted snapshot, then clear it. */
export function consumeStateDirty(): boolean {
  const dirty = stateDirty;
  clearStateDirty();
  return dirty;
}

function nextMessageId(): string {
  return `msg_${++state.messageCounter}`;
}

function nextRunId(): string {
  return `run_${++state.runCounter}`;
}

export function resetState(): void {
  state = emptyState();
  markStateDirty();
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

export const MAX_STRUCTURED_OUTPUT_BYTES = 64 * 1024;
export const MAX_STRUCTURED_OUTPUT_DEPTH = 8;
export const MAX_FANOUT_ITEMS = 32;
export const MAX_LEADER_MAILBOX_MESSAGES = 4096;
export const MAX_TERMINAL_RUNS = 256;

export function structuredOutputSize(value: unknown): number {
  return Buffer.byteLength(JSON.stringify(value), "utf8");
}

export function structuredOutputDepth(value: unknown): number {
  if (!value || typeof value !== "object") return 0;
  const stack: Array<{ value: object; depth: number }> = [{ value, depth: 1 }];
  const seen = new WeakSet<object>();
  let maximum = 0;
  while (stack.length > 0) {
    const current = stack.pop()!;
    if (seen.has(current.value)) continue;
    seen.add(current.value);
    maximum = Math.max(maximum, current.depth);
    const children = Array.isArray(current.value)
      ? current.value
      : Object.values(current.value as Record<string, unknown>);
    for (const child of children) {
      if (!child || typeof child !== "object") continue;
      if (current.depth >= MAX_STRUCTURED_OUTPUT_DEPTH) return current.depth + 1;
      stack.push({ value: child, depth: current.depth + 1 });
    }
  }
  return maximum;
}

export function validateStructuredOutput(value: unknown): string | undefined {
  const depth = structuredOutputDepth(value);
  if (depth > MAX_STRUCTURED_OUTPUT_DEPTH) return `Structured output exceeds depth ${MAX_STRUCTURED_OUTPUT_DEPTH}.`;
  let serialized: string;
  try { serialized = JSON.stringify(value); } catch { return "Structured output must be JSON-serializable."; }
  if (Buffer.byteLength(serialized, "utf8") > MAX_STRUCTURED_OUTPUT_BYTES) return `Structured output exceeds ${MAX_STRUCTURED_OUTPUT_BYTES} bytes.`;
  return undefined;
}

export function resolveInputBinding(run: Run, node: Node, source: string): string {
  const separator = source.indexOf("#");
  const dependencyId = separator >= 0 ? source.slice(0, separator) : source;
  if (!node.dependsOn.includes(dependencyId)) return "(rejected: source is not a dependency)";
  const dependency = run.nodes[dependencyId];
  if (!dependency) return "(rejected: dependency not found)";
  const value = dependency.structuredOutput ?? dependency.namedOutputs ?? dependency.result;
  if (separator < 0) return JSON.stringify(value);
  const pointer = source.slice(separator + 1).replace(/^\/json/, "");
  if (!pointer) return JSON.stringify(value);
  let current: unknown = value;
  for (const part of pointer.split("/").filter(Boolean).map((item) => item.replaceAll("~1", "/").replaceAll("~0", "~"))) {
    if (!current || typeof current !== "object") return "(missing)";
    current = (current as Record<string, unknown>)[part];
  }
  return JSON.stringify(current);
}

/** Render only the explicitly selected dependency results for a node prompt. */
export function buildForkContext(run: Run, node: Node): string[] {
  return node.dependsOn
    .map((depId) => run.nodes[depId])
    .filter((dep): dep is Node => Boolean(dep))
    .filter((dep) => !node.forkContext || node.forkContext.includes(dep.id))
    .map((dep) => {
      const body = dep.result?.trim() || dep.errorMessage?.trim() || `${dep.status} with no written result.`;
      const named = dep.namedOutputs && Object.keys(dep.namedOutputs).length > 0
        ? `\nNamed outputs: ${JSON.stringify(dep.namedOutputs)}`
        : "";
      const structured = dep.structuredOutput === undefined ? "" : `\nStructured output: ${JSON.stringify(dep.structuredOutput)}`;
      return `--- ${dep.id} (${dep.agent}, ${dep.status}) ---\n${body}${named}${structured}`;
    });
}

export interface RunNodeInput {
  id: string;
  agent: string;
  prompt: string;
  paths: string[];
  access: Node["access"];
  model?: string;
  mode?: Node["mode"];
  turnBudget?: number;
  forkContext?: string[];
  inputBindings?: Record<string, string>;
  dependsOn: string[];
}

/** Reserved node id for the optional synthesized summary. */
export const SUMMARY_NODE_ID = "__summary";

/** System-generated task text for the summary node. */
function summaryNodePrompt(): string {
  return [
    "You are the final summary step of this run. Use the upstream handoffs from",
    "every completed leaf node, then write ONE concise final summary covering:",
    "overall outcome, what changed or was produced,",
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
export function normalizeEphemeralAgents(
  agents: Array<{ name: string; prompt: string; description?: string; tools?: string[]; model?: string }> | undefined,
): { ok: true; agents: Record<string, import("./types").EphemeralAgent> } | { ok: false; error: string } {
  if (!agents || agents.length === 0) return { ok: true, agents: {} };
  const seen = new Set<string>();
  const normalized: Record<string, import("./types").EphemeralAgent> = {};
  for (const agent of agents) {
    const name = agent.name.trim();
    const prompt = agent.prompt.trim();
    if (!name) return { ok: false, error: "Ephemeral agent name must not be empty." };
    if (!prompt) return { ok: false, error: `Ephemeral agent "${name}" prompt must not be empty.` };
    if (name === "__summary") return { ok: false, error: `Ephemeral agent name "${name}" is reserved.` };
    if (seen.has(name)) return { ok: false, error: `Duplicate ephemeral agent name: "${name}".` };
    seen.add(name);
    normalized[name] = {
      name,
      description: (agent.description ?? "").trim(),
      tools: [...(agent.tools ?? [])].map((tool) => tool.trim()).filter(Boolean),
      model: agent.model?.trim() || undefined,
      prompt,
    };
  }
  return { ok: true, agents: normalized };
}

export function createRun(
  input: {
    cwd: string;
    concurrency: number;
    worktree: boolean;
    background?: boolean;
    summarize?: boolean;
    summaryAgent?: string;
    ephemeralAgents?: Record<string, import("./types").EphemeralAgent>;
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
    for (const source of Object.values(node.inputBindings ?? {})) {
      const dependencyId = source.split("#", 1)[0];
      if (!node.dependsOn.includes(dependencyId)) {
        return { ok: false, error: `Node "${node.id}" input binding must reference a dependency: "${source}".` };
      }
    }
    if (node.forkContext?.some((dependencyId) => !node.dependsOn.includes(dependencyId))) {
      return { ok: false, error: `Node "${node.id}" forkContext must reference dependencies only.` };
    }
    normalized.push({
      id: node.id,
      workerKey: "", // filled after the run id is assigned
      agent: node.agent,
      prompt: node.prompt,
      paths: normalizedPaths.paths,
      access: node.access,
      model: node.model,
      mode: node.mode,
      turnBudget: node.turnBudget,
      forkContext: node.forkContext ? [...new Set(node.forkContext)] : undefined,
      inputBindings: node.inputBindings ? { ...node.inputBindings } : undefined,
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
    ephemeralAgents: input.ephemeralAgents && Object.keys(input.ephemeralAgents).length > 0 ? input.ephemeralAgents : undefined,
    status: "running",
    cancelRequested: false,
    concurrency: input.concurrency,
    worktree: input.worktree,
    background: input.background ?? true,
    nodes: {},
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
  for (const node of normalized) {
    node.workerKey = `${runId}:${node.id}`;
    run.nodes[node.id] = node;
  }
  state.runs[runId] = run;
  markStateDirty();
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

export function listActiveRuns(): Run[] {
  return listRuns().filter((run) => run.status === "running");
}

/** Compact oldest terminal runs while preserving active runs and recent history. */
export function compactTerminalRuns(): string[] {
  const terminal = listRuns()
    .filter((run) => isRunTerminal(run) && run.settledMessageSent)
    .sort((left, right) => left.updatedAt - right.updatedAt);
  const removeCount = Math.max(0, terminal.length - MAX_TERMINAL_RUNS);
  const removed = terminal.slice(0, removeCount).map((run) => run.id);
  for (const runId of removed) delete state.runs[runId];
  if (removed.length > 0) markStateDirty();
  return removed;
}

export function runningNodeCount(runId: string): number {
  const run = state.runs[runId];
  if (!run) return 0;
  return Object.values(run.nodes).filter((node) => node.spawn?.status === "running" && !node.spawn.processClosed).length;
}

export function isRunTerminal(run: Run): boolean {
  return run.status === "completed" || run.status === "failed" || run.status === "cancelled";
}

/** Claim a run's completion delivery so the follow-up is suppressed (foreground gather). */
export function markRunCompletionDelivered(runId: string): void {
  const run = state.runs[runId];
  if (run) {
    run.completionNotified = true;
    markStateDirty();
  }
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
  markStateDirty();
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
  if ((status === "completed" || status === "failed" || status === "cancelled")
    && node.spawn?.status === "running" && !node.spawn.processClosed) {
    if (status === "completed" || status === "failed") {
      node.spawn.logicalTerminalReport = status;
      node.spawn.terminalReportAccepted = true;
      if (result !== undefined) node.result = result;
      if (errorMessage !== undefined) node.errorMessage = errorMessage;
    }
    node.updatedAt = Date.now();
    state.runs[runId].updatedAt = Date.now();
    markStateDirty();
    return { ok: true, node };
  }
  node.status = status;
  node.updatedAt = Date.now();
  if (result !== undefined) node.result = result;
  if (errorMessage !== undefined) node.errorMessage = errorMessage;
  if (status === "completed" || status === "failed" || status === "cancelled") {
    node.completedAt = Date.now();
  }
  state.runs[runId].updatedAt = Date.now();
  markStateDirty();
  return { ok: true, node };
}

/**
 * Attach child-process execution info to a node and derive its status from
 * the spawn outcome (unless the node was cancelled).
 */
export function setNodeSpawnInfo(runId: string, nodeId: string, info: SpawnInfo): { ok: boolean; node?: Node; error?: string } {
  const node = getNode(runId, nodeId);
  if (!node) return { ok: false, error: `Node "${nodeId}" not found.` };
  const previous = node.spawn?.spawnId === info.spawnId ? node.spawn : undefined;
  // exitCode/signalCode and a terminal status can arrive before Node emits
  // close. Only an explicit close observation may release process resources.
  const processClosed = info.processClosed ?? previous?.processClosed ?? false;
  const status = processClosed ? info.status : (previous?.status ?? "running");
  node.spawn = { ...previous, ...info, status, processClosed };
  node.updatedAt = Date.now();
  state.runs[runId].updatedAt = Date.now();
  if (info.status === "running") {
    // A live spawn implies the node is running (idempotent with markNodeRunning).
    if (node.status === "pending") node.status = "running";
  } else if (processClosed && node.status !== "cancelled") {
    const cancelled = runIsCancellationRequested(runId);
    node.status = cancelled ? "cancelled" : info.status;
    node.completedAt = Date.now();
    if (info.stdout && node.result === undefined) node.result = info.stdout;
    if (info.status === "failed" && !cancelled) {
      node.errorMessage = info.error ?? info.stderr ?? `Child process exited with code ${info.exitCode ?? "unknown"}.`;
    }
  }
  markStateDirty();
  return { ok: true, node };
}

/** Merge a streaming child-process update into its matching running node. */
export function acceptTerminalReport(
  runId: string,
  nodeId: string,
  spawnId: string,
  status: "completed" | "failed",
  body: string,
): boolean {
  const node = getNode(runId, nodeId);
  if (!node || node.spawn?.spawnId !== spawnId || node.spawn.processClosed) return false;
  if (node.spawn.terminalReportAccepted) return false;
  node.spawn.terminalReportAccepted = true;
  node.spawn.logicalTerminalReport = status;
  if (status === "completed") node.result = body;
  else node.errorMessage = body;
  node.updatedAt = Date.now();
  state.runs[runId].updatedAt = Date.now();
  markStateDirty();
  return true;
}

function runIsCancellationRequested(runId: string): boolean {
  return state.runs[runId]?.cancelRequested === true;
}

export function updateNodeSpawnProgress(
  runId: string,
  nodeId: string,
  spawnId: string,
  progress: Pick<SpawnInfo, "liveText" | "activeTool" | "liveThinking" | "turns" | "finalResponse">,
): { ok: boolean; node?: Node; error?: string } {
  const node = getNode(runId, nodeId);
  if (!node) return { ok: false, error: `Node "${nodeId}" not found.` };
  if (node.spawn?.spawnId !== spawnId || node.spawn.status !== "running") {
    return { ok: false, error: `Node "${nodeId}" is not running the expected worker.` };
  }
  node.spawn.liveText = progress.liveText;
  node.spawn.activeTool = progress.activeTool;
  node.spawn.liveThinking = progress.liveThinking;
  node.spawn.turns = progress.turns;
  node.spawn.finalResponse = progress.finalResponse;
  node.updatedAt = Date.now();
  state.runs[runId].updatedAt = Date.now();
  markStateDirty();
  return { ok: true, node };
}

// ── Dependency readiness ──────────────────────────────────────────

/** A node is ready when every dependency has completed and its process closed. */
export function nodeIsReady(run: Run, node: Node): boolean {
  return node.dependsOn.every((dep) => {
    const dependency = run.nodes[dep];
    return dependency?.status === "completed" && (!dependency.spawn || dependency.spawn.processClosed);
  });
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
        && !other.spawn.processClosed
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
  if (cancelled.size > 1) markStateDirty();
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
  const anyOpenProcess = nodes.some((node) => node.spawn?.status === "running" && !node.spawn.processClosed);
  const anyActive = anyOpenProcess || nodes.some((node) => node.status === "running" || node.status === "pending");
  if (anyActive) return "running";
  if (run.cancelRequested) {
    run.status = "cancelled";
  } else if (nodes.some((node) => node.status === "failed")) {
    run.status = "failed";
  } else if (nodes.every((node) => node.status === "cancelled")) {
    run.status = "cancelled";
  } else {
    run.status = "completed";
  }
  run.finishedAt = Date.now();
  run.updatedAt = Date.now();
  markStateDirty();
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
  run.cancelRequested = true;
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
  markStateDirty();
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
  markStateDirty();
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
    node.nodeFollowUpSent = undefined;
    node.updatedAt = Date.now();
  }
  const reset = [...resetSet];
  run.status = "running";
  run.errorMessage = undefined;
  run.finishedAt = undefined;
  run.completionNotified = false;
  run.settledMessageSent = false;
  run.cancelRequested = false;
  run.updatedAt = Date.now();
  markStateDirty();
  return { ok: true, reset };
}

/** Drop per-spawn replay metadata after its final state snapshot was persisted. */
export function clearWorkerRunEvents(workerKey: string, spawnId: string): void {
  const outboxKey = `${workerKey}:${spawnId}`;
  delete state.workerEventOffsets[outboxKey];
  for (const id of Object.keys(state.workerEventIds)) {
    if (id.startsWith(`${spawnId}:`)) delete state.workerEventIds[id];
  }
  markStateDirty();
}

// ── Message storage ───────────────────────────────────────────────

/** Deliver a message to the single leader inbox. */
export function deliverToLeader(msg: Omit<MailboxMessage, "id" | "timestamp">): MailboxMessage {
  const full: MailboxMessage = {
    ...msg,
    id: nextMessageId(),
    timestamp: Date.now(),
  };
  state.leaderMailbox.push(full);
  if (state.leaderMailbox.length > MAX_LEADER_MAILBOX_MESSAGES) {
    state.leaderMailbox.splice(0, state.leaderMailbox.length - MAX_LEADER_MAILBOX_MESSAGES);
  }
  markStateDirty();
  return full;
}

/** Apply a validated worker event exactly once by event id. */
export function receiveWorkerMessage(event: WorkerMessageEvent): boolean {
  const sender = getNodeByWorkerKey(event.worker);
  if (!sender || sender.node.spawn?.spawnId !== event.spawnId) return false;
  if (state.leaderMailbox.some((message) => message.id === event.id)) return false;
  state.leaderMailbox.push({
    id: event.id,
    from: event.worker,
    subject: event.subject,
    body: event.body,
    runId: sender.run.id,
    timestamp: Date.now(),
  });
  if (state.leaderMailbox.length > MAX_LEADER_MAILBOX_MESSAGES) {
    state.leaderMailbox.splice(0, state.leaderMailbox.length - MAX_LEADER_MAILBOX_MESSAGES);
  }
  markStateDirty();
  return true;
}

// ── State inspection ──────────────────────────────────────────────

export function getState(): TeammateState {
  return state;
}

export function getSummary(): string | undefined {
  const runCount = Object.keys(state.runs).length;
  if (runCount === 0) return undefined;
  const messageCount = state.leaderMailbox.length;
  const activeNodes = listNodes().filter((node) => node.status === "running" || node.status === "pending").length;
  return `${runCount} run(s) | ${messageCount} message(s) | ${activeNodes} active node(s)`;
}
