/**
 * Teammate state management — in-memory state with session persistence.
 *
 * State is persisted as a pi session entry tagged with type "teammate_state_snapshot"
 * so it survives restarts and session switches.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { MailboxMessage, SpawnInfo, Task, Teammate, TeammateState } from "./types";

// Minimal interface for session entries we read — avoids deep type dependency
interface SessionEntry {
  customType?: string;
  data?: unknown;
}

let state: TeammateState = {
  teammates: {},
  mailboxes: {},
  tasks: {},
  messageCounter: 0,
  taskCounter: 0,
};

const SNAPSHOT_TYPE = "teammate_state_snapshot" as const;

function nextMessageId(): string {
  return `msg_${++state.messageCounter}`;
}

function nextTaskId(): string {
  return `task_${++state.taskCounter}`;
}

// ── Persistence ───────────────────────────────────────────────────

export function persistState(pi: ExtensionAPI): void {
  pi.appendEntry(SNAPSHOT_TYPE, JSON.stringify(state));
}

export function tryRestoreState(sessionManager: { getEntries(): unknown[] }): boolean {
  const entries = sessionManager.getEntries() as SessionEntry[];
  for (let i = entries.length - 1; i >= 0; i--) {
    const entry = entries[i];
    if (entry.customType === SNAPSHOT_TYPE && typeof entry.data === "string") {
      try {
        const parsed = JSON.parse(entry.data) as TeammateState;
        state = parsed;
        return true;
      } catch {
        // skip corrupt snapshot
      }
    }
  }
  return false;
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
export function markTeammateRunning(name: string, taskId: string): { ok: boolean; error?: string } {
  const teammate = state.teammates[name];
  if (!teammate) {
    return { ok: false, error: `Teammate "${name}" not found.` };
  }
  teammate.status = "running";
  teammate.currentTaskId = taskId;
  teammate.lastActiveAt = Date.now();
  return { ok: true };
}

/** Mark a teammate idle again (worker finished or failed to start). */
export function markTeammateIdle(name: string): { ok: boolean; error?: string } {
  const teammate = state.teammates[name];
  if (!teammate) {
    return { ok: false, error: `Teammate "${name}" not found.` };
  }
  teammate.status = "idle";
  teammate.currentTaskId = undefined;
  teammate.lastActiveAt = Date.now();
  return { ok: true };
}

export function getTeammate(name: string): Teammate | undefined {
  return state.teammates[name];
}

/**
 * Unregister a teammate and delete its mailbox. Refuses while the teammate is
 * running a spawned worker unless force is set (the child keeps running but
 * its completion finds no registry entry — safe).
 */
export function removeTeammate(name: string, force = false): { ok: boolean; error?: string } {
  const teammate = state.teammates[name];
  if (!teammate) {
    return { ok: false, error: `Teammate "${name}" not found.` };
  }
  if (!force && teammate.status === "running") {
    return {
      ok: false,
      error: `Teammate "${name}" is running a worker — wait for it to finish, or pass force to remove anyway.`,
    };
  }
  delete state.teammates[name];
  delete state.mailboxes[name];
  return { ok: true };
}

/**
 * Change the model a teammate is spawned with. Applies to its next spawn;
 * a currently running worker keeps the model it started with.
 */
export function updateTeammateModel(name: string, model: string): { ok: boolean; error?: string } {
  const teammate = state.teammates[name];
  if (!teammate) {
    return { ok: false, error: `Teammate "${name}" not found.` };
  }
  teammate.model = model;
  return { ok: true };
}

export function listTeammates(): Teammate[] {
  return Object.values(state.teammates);
}

export function getTeamLeaders(): Teammate[] {
  return Object.values(state.teammates).filter((t) => t.role === "team-leader");
}

export function getTeammatesByRole(role: string): Teammate[] {
  return Object.values(state.teammates).filter((t) => t.role === role);
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

// ── Task management ───────────────────────────────────────────────

export function createTask(
  title: string,
  description: string,
  assignee: string,
  assignedBy: string,
  blockedBy: string[] = [],
): { ok: boolean; task?: Task; error?: string } {
  for (const dep of blockedBy) {
    if (!state.tasks[dep]) {
      return { ok: false, error: `Task "${dep}" (blockedBy) not found.` };
    }
  }
  const task: Task = {
    id: nextTaskId(),
    title,
    description,
    assignee,
    assignedBy,
    status: "assigned",
    blocks: [],
    blockedBy: [...blockedBy],
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
  state.tasks[task.id] = task;
  // Register this task as a blocker on each dependency's blocks list.
  for (const dep of blockedBy) {
    const depTask = state.tasks[dep];
    if (depTask && !depTask.blocks.includes(task.id)) {
      depTask.blocks.push(task.id);
    }
  }
  return { ok: true, task };
}

/**
 * Set a task's dependency edges (blocks / blockedBy). Unknown referenced
 * task IDs are rejected. The inverse edges on the referenced tasks are kept
 * in sync so the board is always traversable in both directions.
 */
export function setTaskDeps(
  taskId: string,
  deps: { blocks?: string[]; blockedBy?: string[] },
): { ok: boolean; error?: string } {
  const task = state.tasks[taskId];
  if (!task) {
    return { ok: false, error: `Task "${taskId}" not found.` };
  }
  const resolveIds = (ids: string[] | undefined, label: string): string[] | { error: string } => {
    if (!ids) return [];
    for (const id of ids) {
      if (!state.tasks[id]) return { error: `Task "${id}" (${label}) not found.` };
    }
    return [...new Set(ids)];
  };

  const newBlocks = resolveIds(deps.blocks, "blocks");
  const newBlockedBy = resolveIds(deps.blockedBy, "blockedBy");
  if (typeof newBlocks === "object" && "error" in newBlocks) return { ok: false, error: newBlocks.error };
  if (typeof newBlockedBy === "object" && "error" in newBlockedBy) return { ok: false, error: newBlockedBy.error };

  // Remove this task from the old inverse edges.
  for (const dep of task.blockedBy) {
    const depTask = state.tasks[dep];
    if (depTask) depTask.blocks = depTask.blocks.filter((id) => id !== task.id);
  }
  for (const blocked of task.blocks) {
    const blockedTask = state.tasks[blocked];
    if (blockedTask) blockedTask.blockedBy = blockedTask.blockedBy.filter((id) => id !== task.id);
  }

  task.blockedBy = newBlockedBy;
  task.blocks = newBlocks;
  task.updatedAt = Date.now();

  // Rebuild the new inverse edges.
  for (const dep of task.blockedBy) {
    const depTask = state.tasks[dep];
    if (depTask && !depTask.blocks.includes(task.id)) depTask.blocks.push(task.id);
  }
  for (const blocked of task.blocks) {
    const blockedTask = state.tasks[blocked];
    if (blockedTask && !blockedTask.blockedBy.includes(task.id)) blockedTask.blockedBy.push(task.id);
  }
  return { ok: true };
}

/**
 * Whether a task is ready to start: every task in blockedBy must be
 * completed (or cancelled — a cancelled blocker no longer holds work back).
 * Returns the list of unmet blocking task IDs.
 */
export function isTaskReady(taskId: string): { ready: boolean; unmet: string[] } {
  const task = state.tasks[taskId];
  if (!task) return { ready: false, unmet: [] };
  const unmet = task.blockedBy.filter((dep) => {
    const depTask = state.tasks[dep];
    return !depTask || (depTask.status !== "completed" && depTask.status !== "cancelled");
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

  if (info.status === "completed") {
    task.status = "completed";
    task.completedAt = Date.now();
    if (info.stdout) task.result = info.stdout;
  } else if (info.status === "failed") {
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

/**
 * Remove a single task from the board. Refuses while a worker is running on
 * it. Dependency edges referencing the removed task are stripped from the
 * remaining tasks so the board stays traversable.
 */
export function removeTask(taskId: string): { ok: boolean; error?: string } {
  const task = state.tasks[taskId];
  if (!task) {
    return { ok: false, error: `Task "${taskId}" not found.` };
  }
  if (task.spawn?.status === "running") {
    return {
      ok: false,
      error: `Task "${taskId}" has a running worker — wait for it to finish first.`,
    };
  }
  delete state.tasks[taskId];
  for (const t of Object.values(state.tasks)) {
    t.blockedBy = t.blockedBy.filter((dep) => dep !== taskId);
    t.blocks = t.blocks.filter((b) => b !== taskId);
  }
  return { ok: true };
}

/**
 * Prune all finished tasks (completed / failed / cancelled) from the board.
 * Returns how many were removed. Terminal tasks never block anything, so
 * pruning them never strands a dependent task; edges are stripped anyway.
 */
export function pruneFinishedTasks(): number {
  const terminal = new Set(["completed", "failed", "cancelled"]);
  const ids = Object.values(state.tasks)
    .filter((t) => terminal.has(t.status))
    .map((t) => t.id);
  const idSet = new Set(ids);
  for (const id of ids) delete state.tasks[id];
  for (const t of Object.values(state.tasks)) {
    t.blockedBy = t.blockedBy.filter((dep) => !idSet.has(dep));
    t.blocks = t.blocks.filter((b) => !idSet.has(b));
  }
  return ids.length;
}

/**
 * Wipe the entire board: all teammates, mailboxes, and tasks. Refuses while
 * any teammate is running a worker. Counters reset so new ids start fresh.
 */
export function resetBoard(): {
  ok: boolean;
  error?: string;
  removedTeammates: number;
  removedTasks: number;
} {
  const running = Object.values(state.teammates).some((t) => t.status === "running");
  if (running) {
    return {
      ok: false,
      error: "A teammate is running a worker — wait for it to finish before resetting.",
      removedTeammates: 0,
      removedTasks: 0,
    };
  }
  const removedTeammates = Object.keys(state.teammates).length;
  const removedTasks = Object.keys(state.tasks).length;
  state.teammates = {};
  state.mailboxes = {};
  state.tasks = {};
  state.messageCounter = 0;
  state.taskCounter = 0;
  return { ok: true, removedTeammates, removedTasks };
}

export function getTask(taskId: string): Task | undefined {
  return state.tasks[taskId];
}

// ── State inspection (for persistence) ────────────────────────────

export function getState(): TeammateState {
  return state;
}

/**
 * Merge changes a worker wrote to the shared state file back into memory.
 * Adopts: any messages the worker added to mailboxes (replies, deduped by id)
 * and any status/result updates it made to tasks. Parent-side state wins on
 * conflict for teammates; counters only ever move forward.
 */
export function applyStateFile(file: string, readFile: (f: string) => TeammateState | undefined): void {
  const fresh = readFile(file);
  if (!fresh) return;
  for (const [name, msgs] of Object.entries(fresh.mailboxes)) {
    const existing = state.mailboxes[name] ?? [];
    const byId = new Map<string, MailboxMessage>();
    for (const m of existing) byId.set(m.id, m);
    for (const m of msgs) {
      const prior = byId.get(m.id);
      // The parent owns read state: a message the leader already consumed must
      // never be un-read by a later worker file write (live poll / exit merge).
      if (prior?.read) m.read = true;
      byId.set(m.id, m);
    }
    state.mailboxes[name] = Array.from(byId.values());
  }
  for (const [id, t] of Object.entries(fresh.tasks)) {
    const cur = state.tasks[id];
    if (!cur) continue;
    cur.status = t.status;
    if (t.result !== undefined) cur.result = t.result;
    if (t.errorMessage !== undefined) cur.errorMessage = t.errorMessage;
    if (t.completedAt) cur.completedAt = t.completedAt;
  }
  state.messageCounter = Math.max(state.messageCounter, fresh.messageCounter ?? 0);
  state.taskCounter = Math.max(state.taskCounter, fresh.taskCounter ?? 0);
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