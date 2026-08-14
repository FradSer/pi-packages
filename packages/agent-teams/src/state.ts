/**
 * Teammate state management for the current session only.
 */

import type { MailboxMessage, SpawnInfo, Task, Teammate, TeammateState, WorkerMessageEvent } from "./types";

function emptyState(): TeammateState {
  return {
    teammates: {},
    mailboxes: {},
    tasks: {},
    messageCounter: 0,
    taskCounter: 0,
    workerEventOffsets: {},
    workerEventIds: {},
  };
}

let state = emptyState();

function nextMessageId(): string {
  return `msg_${++state.messageCounter}`;
}

function nextTaskId(): string {
  return `task_${++state.taskCounter}`;
}

export function resetState(): void {
  state = emptyState();
}

// ── Teammate registry ─────────────────────────────────────────────

export function registerTeammate(teammate: Omit<Teammate, "status">): { ok: boolean; error?: string } {
  if (state.teammates[teammate.name]) {
    return { ok: false, error: `Teammate "${teammate.name}" is already registered.` };
  }
  state.teammates[teammate.name] = { ...teammate, status: "idle" };
  if (!state.mailboxes[teammate.name]) {
    state.mailboxes[teammate.name] = [];
  }
  return { ok: true };
}

// ── Liveness ──────────────────────────────────────────────────────

/** Mark a teammate as running a spawned worker for the given task. */
export function markTeammateRunning(name: string, taskId: string, runId: string): { ok: boolean; error?: string } {
  const teammate = state.teammates[name];
  if (!teammate) {
    return { ok: false, error: `Teammate "${name}" not found.` };
  }
  teammate.status = "running";
  teammate.currentTaskId = taskId;
  teammate.currentRunId = runId;
  teammate.lastActiveAt = Date.now();
  return { ok: true };
}

/** Mark a teammate idle again (worker finished or failed to start). */
export function markTeammateIdle(name: string, runId?: string): { ok: boolean; error?: string } {
  const teammate = state.teammates[name];
  if (!teammate) {
    return { ok: false, error: `Teammate "${name}" not found.` };
  }
  if (runId && teammate.currentRunId !== runId) {
    return { ok: false, error: `Teammate "${name}" belongs to a newer worker run.` };
  }
  teammate.status = "idle";
  teammate.currentTaskId = undefined;
  teammate.currentRunId = undefined;
  teammate.lastActiveAt = Date.now();
  return { ok: true };
}

/** Drop per-run replay metadata after its final state snapshot was persisted. */
export function clearWorkerRunEvents(workerName: string, runId: string): void {
  const outboxKey = `${workerName}:${runId}`;
  delete state.workerEventOffsets[outboxKey];
  for (const id of Object.keys(state.workerEventIds)) {
    if (id.startsWith(`${runId}:`)) delete state.workerEventIds[id];
  }
}

export function getTeammate(name: string): Teammate | undefined {
  return state.teammates[name];
}

/**
 * Unregister a teammate and delete its mailbox. Refuses while the teammate is
 * running a spawned worker (the task must be cancelled before removing).
 */
export function removeTeammate(name: string): { ok: boolean; error?: string } {
  const teammate = state.teammates[name];
  if (!teammate) {
    return { ok: false, error: `Teammate "${name}" not found.` };
  }
  const activeTask = Object.values(state.tasks).find(
    (task) => task.assignee === name && (task.status === "assigned" || task.status === "in_progress"),
  );
  if (teammate.status === "running" || activeTask) {
    return {
      ok: false,
      error: `Teammate "${name}" has active task "${activeTask?.id ?? teammate.currentTaskId}" — cancel or complete it before removing.`,
    };
  }
  delete state.teammates[name];
  delete state.mailboxes[name];
  return { ok: true };
}

/**
 * Configure an existing teammate's description, prompt, model, or tools.
 * A running worker keeps the configuration it started with.
 */
export function configureTeammate(
  name: string,
  config: { description?: string; prompt?: string; model?: string; tools?: string[] },
): { ok: boolean; error?: string } {
  const teammate = state.teammates[name];
  if (!teammate) {
    return { ok: false, error: `Teammate "${name}" not found.` };
  }
  if (Object.values(config).every((value) => value === undefined)) {
    return { ok: false, error: "Provide at least one teammate configuration field." };
  }
  if (config.description !== undefined) teammate.description = config.description;
  if (config.prompt !== undefined) teammate.prompt = config.prompt;
  if (config.model !== undefined) teammate.model = config.model;
  if (config.tools !== undefined) teammate.tools = config.tools;
  return { ok: true };
}

export function listTeammates(): Teammate[] {
  return Object.values(state.teammates);
}

function sameTools(left?: string[], right?: string[]): boolean {
  return JSON.stringify(left ?? []) === JSON.stringify(right ?? []);
}

/** Find an idle teammate with a compatible role and execution configuration. */
export function findReusableTeammate(criteria: Pick<Teammate, "role" | "prompt" | "model" | "tools">): Teammate | undefined {
  return Object.values(state.teammates).find((teammate) =>
    teammate.status === "idle"
    && teammate.role === criteria.role
    && teammate.prompt === criteria.prompt
    && teammate.model === criteria.model
    && sameTools(teammate.tools, criteria.tools),
  );
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

export function readMailbox(
  name: string,
  opts: { unreadOnly?: boolean; markRead?: boolean } = {},
): MailboxMessage[] {
  const mailbox = state.mailboxes[name] ?? [];
  let messages = opts.unreadOnly !== false ? mailbox.filter((m) => !m.read) : [...mailbox];

  if (opts.markRead !== false) {
    for (const msg of messages) {
      msg.read = true;
    }
  }

  return messages;
}

export function getUnreadCount(name: string): number {
  return (state.mailboxes[name] ?? []).filter((m) => !m.read).length;
}

/** Every message across every mailbox (for building full conversation transcripts). */
export function listAllMessages(): MailboxMessage[] {
  return Object.values(state.mailboxes).flat();
}

/**
 * Mark the task-assignment notification(s) for a task as read once the task
 * actually starts (spawned or set in_progress). Keeps the footer unread count
 * meaningful: assignment notifications are consumed when work begins instead
 * of piling up as stale "unread" items.
 */
export function markTaskNotificationsRead(taskId: string): void {
  for (const mailbox of Object.values(state.mailboxes)) {
    for (const msg of mailbox) {
      if (msg.taskId === taskId) msg.read = true;
    }
  }
}

/** Mark only a worker's messages for a completed task in the leader inbox.
 * Completion messages are consumed when their result is delivered to the
 * leader; unrelated messages and other tasks remain unread. */
export function markLeaderMessagesReadForTask(taskId: string, from?: string): number {
  const mailbox = state.mailboxes.agent ?? [];
  let marked = 0;
  for (const msg of mailbox) {
    if (msg.taskId !== taskId || (from && msg.from !== from) || msg.read) continue;
    msg.read = true;
    marked++;
  }
  return marked;
}

// ── Task management ───────────────────────────────────────────────

function normalizeTaskPaths(paths: string[]): { ok: true; paths: string[] } | { ok: false; error: string } {
  if (paths.length === 0) return { ok: false, error: "Provide at least one task path." };
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
    if (!valid) return { ok: false, error: `Invalid task path: "${rawPath}".` };
    if (normalized.includes(candidate)) return { ok: false, error: `Duplicate task path: "${rawPath}".` };
    if (normalized.some((path) => pathsOverlap(path, candidate))) {
      return { ok: false, error: `Overlapping task paths: "${rawPath}".` };
    }
    normalized.push(candidate);
  }
  return { ok: true, paths: normalized };
}

function pathsOverlap(left: string, right: string): boolean {
  return left === "." || right === "." || left === right || left.startsWith(`${right}/`) || right.startsWith(`${left}/`);
}

export function createTask(
  title: string,
  description: string,
  paths: string[],
  access: Task["access"],
  assignee: string,
  assignedBy: string,
  blockedBy: string[] = [],
): { ok: boolean; task?: Task; error?: string } {
  const normalizedPaths = normalizeTaskPaths(paths);
  if (!normalizedPaths.ok) return normalizedPaths;
  const uniqueBlockedBy = [...new Set(blockedBy)];
  for (const dep of uniqueBlockedBy) {
    if (!state.tasks[dep]) {
      return { ok: false, error: `Task "${dep}" (blockedBy) not found.` };
    }
  }
  const task: Task = {
    id: nextTaskId(),
    title,
    description,
    paths: normalizedPaths.paths,
    access,
    assignee,
    assignedBy,
    status: "assigned",
    blocks: [],
    unblockedNotificationTaskIds: [],
    blockedBy: uniqueBlockedBy,
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
  state.tasks[task.id] = task;
  // Register this task as a blocker on each dependency's blocks list.
  for (const dep of uniqueBlockedBy) {
    const depTask = state.tasks[dep];
    if (depTask && !depTask.blocks.includes(task.id)) {
      depTask.blocks.push(task.id);
    }
  }
  return { ok: true, task };
}

export function cancelTask(taskId: string): { ok: boolean; task?: Task; error?: string } {
  const task = state.tasks[taskId];
  if (!task) return { ok: false, error: `Task "${taskId}" not found.` };
  if (task.status === "completed" || task.status === "cancelled") {
    return { ok: false, error: `Task "${taskId}" is already ${task.status}.` };
  }
  if (task.spawn?.status === "running") {
    return {
      ok: false,
      error: `Task "${taskId}" still has a running worker and cannot be cancelled until it closes.`,
    };
  }
  task.status = "cancelled";
  task.completedAt = Date.now();
  task.updatedAt = Date.now();
  return { ok: true, task };
}

/**
 * Whether a task is ready to start: every task in blockedBy must be
 * completed (or cancelled — a cancelled blocker no longer holds work back).
 * Returns the list of unmet blocking task IDs.
 */
export function findSharedWorkspaceWriteConflict(taskId: string): Task | undefined {
  const task = state.tasks[taskId];
  if (!task || task.access !== "write") return undefined;
  return Object.values(state.tasks).find((other) =>
    other.id !== task.id
    && other.status === "in_progress"
    && other.spawn?.status === "running"
    && other.spawn.isolation !== "worktree"
    && other.access === "write"
    && task.paths.some((path) => other.paths.some((otherPath) => pathsOverlap(path, otherPath))),
  );
}

export function isTaskReady(taskId: string): { ready: boolean; unmet: string[] } {
  const task = state.tasks[taskId];
  if (!task) return { ready: false, unmet: [] };
  const unmet = task.blockedBy.filter((dep) => {
    const depTask = state.tasks[dep];
    return !depTask
      || (depTask.status !== "completed" && depTask.status !== "cancelled")
      || depTask.spawn?.status === "running";
  });
  return { ready: unmet.length === 0, unmet };
}

/**
 * Attach child-process execution info to a task. When the spawn finishes,
 * the task status is updated to match (completed/failed) and the result is
 * written to the task.
 */
export function setSpawnInfo(taskId: string, info: SpawnInfo): { ok: boolean; task?: Task; error?: string } {
  const task = state.tasks[taskId];
  if (!task) {
    return { ok: false, error: `Task "${taskId}" not found.` };
  }
  task.spawn = info;
  task.updatedAt = Date.now();

  if (info.status === "completed" && task.status !== "cancelled") {
    task.status = "completed";
    task.completedAt = Date.now();
    if (info.stdout && task.result === undefined) task.result = info.stdout;
  } else if (info.status === "failed" && task.status !== "cancelled") {
    task.status = "failed";
    task.completedAt = Date.now();
    task.errorMessage = info.error ?? info.stderr ?? `Child process exited with code ${info.exitCode ?? "unknown"}.`;
  }
  return { ok: true, task };
}

export function updateTaskStatus(
  taskId: string,
  status: Task["status"],
  result?: string,
  errorMessage?: string,
): { ok: boolean; task?: Task; error?: string } {
  const task = state.tasks[taskId];
  if (!task) {
    return { ok: false, error: `Task "${taskId}" not found.` };
  }

  task.status = status;
  task.updatedAt = Date.now();

  if (result !== undefined) task.result = result;
  if (errorMessage !== undefined) task.errorMessage = errorMessage;
  if (status === "completed" || status === "failed") {
    task.completedAt = Date.now();
  }

  return { ok: true, task };
}

export function listTasks(filters: { status?: string; assignee?: string } = {}): Task[] {
  let tasks = Object.values(state.tasks);
  if (filters.status) {
    tasks = tasks.filter((t) => t.status === filters.status);
  }
  if (filters.assignee) {
    tasks = tasks.filter((t) => t.assignee === filters.assignee);
  }
  // Sort by most recent first
  tasks.sort((a, b) => b.updatedAt - a.updatedAt);
  return tasks;
}

export function getTask(taskId: string): Task | undefined {
  return state.tasks[taskId];
}

/** Remove terminal tasks after the leader has synthesized their outcomes. */
/** Retire idle teammates only after their mailbox is clear and their idle TTL has elapsed. */
export function retireExpiredTeammates(idleTtlMs: number, now = Date.now()): number {
  if (idleTtlMs <= 0) return 0;
  let retired = 0;
  for (const teammate of Object.values(state.teammates)) {
    const hasActiveTask = Object.values(state.tasks).some(
      (task) => task.assignee === teammate.name && (task.status === "assigned" || task.status === "in_progress"),
    );
    const hasUnreadMessages = (state.mailboxes[teammate.name] ?? []).some((message) => !message.read);
    const idleSince = teammate.lastActiveAt ?? teammate.registeredAt;
    if (teammate.status !== "idle" || hasActiveTask || hasUnreadMessages || now - idleSince < idleTtlMs) continue;
    delete state.teammates[teammate.name];
    delete state.mailboxes[teammate.name];
    retired++;
  }
  return retired;
}

/** Prepare a failed task for an explicitly requested fresh run by its idle teammate. */
export function retryFailedTask(taskId: string): { ok: boolean; task?: Task; error?: string } {
  const task = state.tasks[taskId];
  if (!task) return { ok: false, error: `Task "${taskId}" not found.` };
  if (task.status !== "failed" || task.spawn?.status === "running") {
    return { ok: false, error: `Task "${taskId}" is ${task.status}, not a settled failed task.` };
  }
  const teammate = state.teammates[task.assignee];
  if (!teammate || teammate.status !== "idle") {
    return { ok: false, error: `Teammate "${task.assignee}" is unavailable for retry.` };
  }
  task.status = "assigned";
  task.result = undefined;
  task.errorMessage = undefined;
  task.completedAt = undefined;
  task.spawn = undefined;
  task.updatedAt = Date.now();
  return { ok: true, task };
}

export function pruneFinishedTasks(): number {
  const terminal = new Set<Task["status"]>(["completed", "failed", "cancelled"]);
  let removed = 0;
  for (const [id, task] of Object.entries(state.tasks)) {
    if (!terminal.has(task.status) || task.spawn?.status === "running") continue;
    for (const dependency of Object.values(state.tasks)) {
      dependency.blocks = dependency.blocks.filter((blockedId) => blockedId !== id);
      dependency.blockedBy = dependency.blockedBy.filter((blockerId) => blockerId !== id);
      dependency.unblockedNotificationTaskIds = dependency.unblockedNotificationTaskIds?.filter((notifiedId) => notifiedId !== id);
    }
    delete state.tasks[id];
    removed++;
  }
  return removed;
}

// ── State inspection ──────────────────────────────────────────────

export function getState(): TeammateState {
  return state;
}

export function getSummary(): string | undefined {
  const teammateCount = Object.keys(state.teammates).length;
  // Nothing to show until the first teammate is registered — an all-zero footer
  // ("0 teammate(s) | 0 unread message(s) | 0 active task(s), 0 total") is noise
  // on session entry. setStatus(..., undefined) clears the footer.
  if (teammateCount === 0) return undefined;
  const unreadTotal = Object.keys(state.mailboxes).reduce(
    (sum, name) => sum + getUnreadCount(name),
    0,
  );
  const activeTasks = Object.values(state.tasks).filter(
    (t) => t.status === "assigned" || t.status === "in_progress",
  ).length;
  const totalTasks = Object.keys(state.tasks).length;

  const parts: string[] = [];
  parts.push(`${teammateCount} teammate(s)`);
  parts.push(`${unreadTotal} unread message(s)`);
  parts.push(`${activeTasks} active task(s), ${totalTasks} total`);
  return parts.join(" | ");
}