/**
 * @fradser/pi-agent-teams — Pi extension for multi-agent teams.
 *
 * Provides a mailbox-based communication system, task management,
 * and main-session orchestration for Pi agents.
 *
 * Leader tools: teammate_register, teammate_list, teammate_configure,
 * teammate_remove, teammate_message, teammate_inbox, teammate_create_task,
 * teammate_list_tasks, teammate_start_task, teammate_wait,
 * teammate_cancel_task, teammate_cleanup.
 *
 * Spawned workers receive only teammate_message, teammate_inbox, and
 * teammate_report.
 */

import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import { isKeyRelease, truncateToWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import type { ExtensionAPI, ExtensionUIContext, Theme, ThemeColor } from "@earendil-works/pi-coding-agent";
import { truncateTail, DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES } from "@earendil-works/pi-coding-agent";
import {
  EmptyParams,
  TeammateCancelTaskParams,
  TeammateConfigureParams,
  TeammateCreateTaskParams,
  TeammateInboxParams,
  TeammateListTasksParams,
  TeammateMessageParams,
  TeammateRegisterParams,
  TeammateRemoveParams,
  TeammateStartTaskParams,
  TeammateWaitParams,
  TeammateReportParams,
  type Task,
  type Teammate,
  type TeammateRole,
} from "./types";
import {
  cancelTask,
  clearWorkerRunEvents,
  configureTeammate,
  createTask,
  getState,
  getSummary,
  getTeammate,
  getUnreadCount,
  isTaskReady,
  listAllMessages,
  listTasks,
  listTeammates,
  markLeaderMessagesReadForTask,
  markTeammateIdle,
  markTeammateRunning,
  markTaskNotificationsRead,
  persistState,
  pruneFinishedTasks,
  readMailbox,
  receiveWorkerMessage,
  registerTeammate,
  removeTeammate,
  retryFailedTask,
  sendMessage,
  setSpawnInfo,
  tryRestoreState,
  updateTaskStatus,
} from "./state";
import { buildAutonomousPrompt, isSuccessfulWorkerExit, killWorker, spawnPiWorker } from "./spawner";
import { captureWorktreeDiff, cleanupWorktree, createWorktree, discardWorktree } from "./worktree";
import {
  appendWorkerEvent,
  cleanupExpiredStateDirs,
  readStateFile,
  readWorkerEvents,
  removeSessionStateDir,
  removeWorkerOutbox,
  stateFilePath,
  workerOutboxPath,
  writeStateFile,
} from "./statefile";
import type { WorkerEvent, WorkerUsage } from "./types";

/** Keep shared state dirs for at most 7 days after their last write. */
const STATE_DIR_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

/** Truncate worker/task output to the built-in tool-output limits (50KB / 2000 lines). */
function cap(text: string | undefined, maxBytes = DEFAULT_MAX_BYTES): string {
  if (!text) return "";
  if (text.length <= maxBytes) return text;
  const t = truncateTail(text, { maxLines: DEFAULT_MAX_LINES, maxBytes });
  return `${t.content}\n…[truncated ${text.length - t.content.length} chars]`;
}

function workerOutboxBinding(): { worker: string; taskId: string; runId: string; stateFile: string; outbox: string } | undefined {
  const worker = process.env.PI_TEAMMATE_WORKER_NAME;
  const taskId = process.env.PI_TEAMMATE_TASK_ID;
  const runId = process.env.PI_TEAMMATE_RUN_ID;
  const stateFile = process.env.PI_TEAMMATE_STATE_FILE;
  const outbox = process.env.PI_TEAMMATE_OUTBOX_FILE;
  return worker && taskId && runId && stateFile && outbox ? { worker, taskId, runId, stateFile, outbox } : undefined;
}

function isWorkerEvent(value: unknown): value is WorkerEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Partial<WorkerEvent>;
  if (typeof event.id !== "string" || typeof event.worker !== "string" || typeof event.runId !== "string") return false;
  if (event.type === "message") {
    return typeof event.to === "string"
      && typeof event.subject === "string"
      && typeof event.body === "string"
      && (event.taskId === undefined || typeof event.taskId === "string");
  }
  if (event.type === "message_read") return typeof event.messageId === "string";
  return event.type === "task_update"
    && typeof event.taskId === "string"
    && ["in_progress", "completed", "failed"].includes(event.status ?? "")
    && (event.result === undefined || typeof event.result === "string")
    && (event.errorMessage === undefined || typeof event.errorMessage === "string");
}

/** Apply complete, validated event records from every worker-owned outbox. */
function applyWorkerEvents(stateFile: string): void {
  const state = getState();
  for (const workerName of Object.keys(state.teammates)) {
    const teammate = getTeammate(workerName);
    if (!teammate) continue;
    const runId = teammate.currentRunId;
    if (!runId) continue;
    const outboxKey = `${workerName}:${runId}`;
    const outbox = workerOutboxPath(stateFile, workerName, runId);
    const { events, nextOffset } = readWorkerEvents(outbox, state.workerEventOffsets[outboxKey] ?? 0);
    state.workerEventOffsets[outboxKey] = nextOffset;
    for (const value of events) {
      if (!isWorkerEvent(value) || state.workerEventIds[`${runId}:${value.id}`]) continue;
      const event = value;
      if (event.worker !== workerName || event.runId !== runId) continue;
      if (event.type === "message") {
        if (event.to !== "agent" && !getTeammate(event.to)) continue;
        state.workerEventIds[`${runId}:${event.id}`] = runId;
        receiveWorkerMessage({
          id: event.id,
          worker: workerName,
          runId,
          type: "message",
          to: event.to,
          subject: event.subject,
          body: event.body,
          taskId: event.taskId === teammate.currentTaskId ? event.taskId : undefined,
        });
        continue;
      }
      if (event.type === "message_read") {
        const message = listAllMessages().find((candidate) => candidate.id === event.messageId);
        if (message?.to !== workerName) continue;
        state.workerEventIds[`${runId}:${event.id}`] = runId;
        message.read = true;
        continue;
      }
      if (event.taskId !== teammate.currentTaskId) continue;
      const task = listTasks().find((candidate) => candidate.id === event.taskId);
      if (!task || ["completed", "failed", "cancelled"].includes(task.status)) continue;
      state.workerEventIds[`${runId}:${event.id}`] = runId;
      updateTaskStatus(event.taskId, event.status, event.result, event.errorMessage);
    }
  }
}

/** Persist final task state before compacting an exhausted per-run outbox. */
function compactFinishedWorkerRun(stateFile: string, workerName: string, runId: string): void {
  try {
    // First persist the final board while its event cursor still points past
    // every applied record. A crash here preserves replay protection.
    writeStateFile(stateFile, getState());
    clearWorkerRunEvents(workerName, runId);
    writeStateFile(stateFile, getState());
    removeWorkerOutbox(stateFile, workerName, runId);
  } catch {
    // Retain metadata/outbox on a failed compaction; it is harmless because
    // the finished run is no longer current and remains safely ignored.
  }
}

function acknowledgedWorkerMessageIds(outbox: string, worker: string, runId: string): Set<string> {
  const ids = new Set<string>();
  try {
    for (const line of fs.readFileSync(outbox, "utf-8").split("\n")) {
      if (!line.trim()) continue;
      const event = JSON.parse(line) as Partial<WorkerEvent>;
      if (event.type === "message_read" && event.worker === worker && event.runId === runId && typeof event.messageId === "string") {
        ids.add(event.messageId);
      }
    }
  } catch {
    // A missing/out-of-date outbox means no local receipt has been emitted.
  }
  return ids;
}

function renderInbox(name: string, messages: Array<{ id: string; from: string; subject: string; body: string; taskId?: string; timestamp: number }>): string {
  if (messages.length === 0) return `No messages in ${name}'s inbox.`;
  const lines = [`## Inbox: ${name} (${messages.length} message${messages.length > 1 ? "s" : ""})\n`];
  for (const message of messages) {
    lines.push(`### [${message.id}] ${message.subject}`);
    lines.push(`From: ${message.from} | ${new Date(message.timestamp).toLocaleString()}`);
    if (message.taskId) lines.push(`Task: ${message.taskId}`);
    lines.push("", cap(message.body), "", "---", "");
  }
  return lines.join("\n");
}

/** Register the only coordination capabilities available to a spawned worker. */
function registerWorkerCapabilities(pi: ExtensionAPI): void {
  pi.registerTool({
    name: "teammate_message",
    promptSnippet: "Send a direct message to a teammate or the main session",
    label: "Teammate Message",
    description: "Worker-only sender. Addresses a teammate by name, or agent to message the main session through the leader-validated outbox.",
    parameters: TeammateMessageParams,
    async execute(_toolCallId, params) {
      const binding = workerOutboxBinding();
      if (!binding) return { content: [{ type: "text", text: "This capability is available only inside a spawned teammate." }], details: {}, isError: true };
      const snapshot = readStateFile(binding.stateFile);
      if (params.to === "all" || params.role) {
        return { content: [{ type: "text", text: "Workers may message one teammate or agent, not broadcast." }], details: {}, isError: true };
      }
      if (params.to !== "agent" && !snapshot?.teammates[params.to]) {
        return { content: [{ type: "text", text: `Unknown teammate recipient: ${params.to}.` }], details: {}, isError: true };
      }
      appendWorkerEvent(binding.outbox, {
        id: randomUUID(),
        type: "message",
        worker: binding.worker,
        runId: binding.runId,
        to: params.to,
        subject: params.subject,
        body: params.body,
        taskId: binding.taskId,
      });
      return { content: [{ type: "text", text: `Queued message to ${params.to}.` }], details: {} };
    },
  });

  pi.registerTool({
    name: "teammate_inbox",
    promptSnippet: "Read this teammate's inbox",
    label: "Teammate Inbox",
    description: "Worker-only inbox. Reads this worker's leader-published inbox and emits read receipts for returned messages.",
    parameters: TeammateInboxParams,
    async execute(_toolCallId, params) {
      const binding = workerOutboxBinding();
      if (!binding) return { content: [{ type: "text", text: "This capability is available only inside a spawned teammate." }], details: {}, isError: true };
      const snapshot = readStateFile(binding.stateFile);
      const unreadOnly = params.unreadOnly ?? true;
      const markRead = params.markRead ?? true;
      const acknowledged = acknowledgedWorkerMessageIds(binding.outbox, binding.worker, binding.runId);
      const messages = (snapshot?.mailboxes[binding.worker] ?? []).filter(
        (message) => !unreadOnly || (!message.read && !acknowledged.has(message.id)),
      );
      if (markRead) {
        for (const message of messages.filter((message) => !message.read)) {
          appendWorkerEvent(binding.outbox, { id: randomUUID(), type: "message_read", worker: binding.worker, runId: binding.runId, messageId: message.id });
        }
      }
      return { content: [{ type: "text", text: renderInbox(binding.worker, messages) }], details: {} };
    },
  });

  pi.registerTool({
    name: "teammate_report",
    promptSnippet: "Worker-only: report progress, completion, or failure for this worker's assigned task",
    label: "Report Teammate Task Status",
    description: "Worker-only capability. Reports progress, completion, or failure for the task bound to this worker process.",
    parameters: TeammateReportParams,
    async execute(_toolCallId, params) {
      const binding = workerOutboxBinding();
      if (!binding) return { content: [{ type: "text", text: "This capability is available only inside a spawned teammate." }], details: {}, isError: true };
      appendWorkerEvent(binding.outbox, {
        id: randomUUID(),
        type: "task_update",
        worker: binding.worker,
        runId: binding.runId,
        taskId: binding.taskId,
        status: params.status,
        result: params.result,
        errorMessage: params.errorMessage,
      });
      return { content: [{ type: "text", text: `Queued ${params.status} update for ${binding.taskId}.` }], details: {} };
    },
  });
}

/** Notify downstream assignees once all dependencies for their task are done. */
function notifyUnblockedTasks(taskId: string): void {
  const completed = listTasks().find((task) => task.id === taskId);
  if (!completed) return;
  for (const blockedId of completed.blocks) {
    const blocked = listTasks().find((task) => task.id === blockedId);
    if (!blocked || blocked.status !== "assigned" || !isTaskReady(blocked.id)) continue;
    if (completed.unblockedNotificationTaskIds?.includes(blocked.id)) continue;
    completed.unblockedNotificationTaskIds ??= [];
    completed.unblockedNotificationTaskIds.push(blocked.id);
    sendMessage({
      from: "agent",
      to: blocked.assignee,
      subject: "Task unblocked",
      body: `Task [${blocked.id}] "${blocked.title}" is ready to start. All blocking tasks are complete.`,
      taskId: blocked.id,
    });
  }
}

// ── Team UI: passive widget + full-screen console ──────────────────
// Design: the widget above the editor is DISPLAY-ONLY (no key interception —
// pi's model selector, history navigation and dialogs are never affected).
// ALL interaction happens in the full-screen Team Console (`/teammate`), which
// owns input explicitly via ctx.ui.custom, so ↑/↓/Enter are safe in there.

const TEAM_COLORS = ["accent", "success", "warning", "error", "toolTitle", "mdLink"] as const;
const PANEL_IDLE_COLLAPSE_MS = 30_000;
const SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
const SPINNER_MS = 120;

let panelRequestRender: (() => void) | undefined;
let spinnerTimer: ReturnType<typeof setInterval> | undefined;
let spinnerFrame = 0;
let panelLastActivity = 0;
let panelCollapseTimer: ReturnType<typeof setTimeout> | undefined;

/**
 * Esc arrives as a bare `\x1b` in legacy terminals, or as CSI-u `\x1b[27u`
 * (with optional `:shifted`, `;mod`, `:event` segments) once the Kitty
 * protocol (flags=7, which pi negotiates) is active in Ghostty.
 */
function isEscapeKey(data: string): boolean {
  return data === "\u001b" || /^\u001b\[27(?:[:;\d]*)?u$/.test(data);
}

/** Display label for a role: a plain registered teammate shows as "teammate". */
function displayRole(role: string): string {
  return role === "worker" ? "teammate" : role;
}

function executionToolsFor(teammate: Teammate): string[] {
  if (teammate.tools) return teammate.tools;
  switch (teammate.role) {
    case "worker":
      return ["read", "bash", "edit", "write"];
    case "reviewer":
    case "specialist":
      return ["read", "bash"];
    case "observer":
      return ["read"];
  }
}

/** Stable per-teammate color (independent of row order). */
function hashName(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return Math.abs(h);
}

interface PanelRow {
  name: string;
}
/** Console/widget rows contain teammate status only; messages use the mailbox tool. */
function buildPanelRows(): PanelRow[] {
  return listTeammates().map((teammate) => ({ name: teammate.name }));
}

function shortTaskTitle(taskId?: string): string {
  if (!taskId) return "working";
  const task = listTasks().find((candidate) => candidate.id === taskId);
  const title = task?.title.trim().replace(/\s+/g, " ") || "working";
  return title.length > 32 ? `${title.slice(0, 31)}…` : title;
}

function runningTaskLabel(teammate: Teammate): string {
  return `${SPINNER_FRAMES[spinnerFrame]} ${shortTaskTitle(teammate.currentTaskId)} · working...`;
}

function ensureSpinner(): void {
  const running = listTeammates().some((teammate) => teammate.status === "running");
  if (running && !spinnerTimer && panelRequestRender) {
    spinnerTimer = setInterval(() => {
      if (!listTeammates().some((teammate) => teammate.status === "running")) {
        clearInterval(spinnerTimer);
        spinnerTimer = undefined;
        return;
      }
      spinnerFrame = (spinnerFrame + 1) % SPINNER_FRAMES.length;
      panelRequestRender?.();
    }, SPINNER_MS);
  } else if (!running && spinnerTimer) {
    clearInterval(spinnerTimer);
    spinnerTimer = undefined;
  }
}

function isPanelCollapsed(): boolean {
  const rows = buildPanelRows();
  if (rows.length === 0) return false;
  const teammates = listTeammates();
  return teammates.length > 0 && teammates.every((t) => t.status === "idle") && Date.now() - panelLastActivity > PANEL_IDLE_COLLAPSE_MS;
}

function scheduleIdleCollapse(): void {
  if (panelCollapseTimer) clearTimeout(panelCollapseTimer);
  panelCollapseTimer = undefined;
  const teammates = listTeammates();
  if (teammates.length === 0 || !teammates.every((t) => t.status === "idle")) return;
  panelCollapseTimer = setTimeout(() => {
    panelCollapseTimer = undefined;
    panelRequestRender?.();
  }, PANEL_IDLE_COLLAPSE_MS);
}

/** Refresh the passive widget after any state change. */
function stopUiTimers(): void {
  if (spinnerTimer) {
    clearInterval(spinnerTimer);
    spinnerTimer = undefined;
  }
  if (panelCollapseTimer) {
    clearTimeout(panelCollapseTimer);
    panelCollapseTimer = undefined;
  }
}

function refreshTeamUI(_ctx: { ui: ExtensionUIContext }): void {
  panelLastActivity = Date.now();
  scheduleIdleCollapse();
  ensureLivePoll();
  ensureSpinner();
  panelRequestRender?.();
}

// ── Live worker-event drain while workers run ──────────────────────
// The leader owns state.json. Each worker appends events to its own outbox;
// while any teammate runs, the leader validates and applies those events.
let liveStateFile: string | undefined;
let livePollTimer: ReturnType<typeof setInterval> | undefined;
const LIVE_POLL_MS = 5000;

function ensureLivePoll(): void {
  const running = listTeammates().some((t) => t.status === "running");
  if (running && !livePollTimer && liveStateFile) {
    livePollTimer = setInterval(() => {
      try {
        applyWorkerEvents(liveStateFile!);
        writeStateFile(liveStateFile!, getState());
        panelRequestRender?.();
      } catch {
        // Never let a poll error break the extension.
      }
    }, LIVE_POLL_MS);
  } else if (!running && livePollTimer) {
    clearInterval(livePollTimer);
    livePollTimer = undefined;
  }
}

/** Passive widget rows (display only — no selection, no key handling). */
function panelRows(theme: Theme, width?: number): string[] {
  const fg = (color: ThemeColor, s: string): string => theme.fg(color, s);
  const bold = (s: string): string => theme.bold(s);
  const fit = (line: string): string =>
    typeof width === "number" && width > 0 ? truncateToWidth(line, Math.max(10, width - 1)) : line;
  const rows = buildPanelRows();
  if (rows.length === 0) return [];

  if (isPanelCollapsed()) {
    return [fit(fg("dim", `Team idle — ${listTeammates().length} teammate(s) — /teammate to interact`))];
  }

  const lines: string[] = [];
  for (const row of rows) {
    const t = getTeammate(row.name);
    if (!t) continue;
    const color = TEAM_COLORS[hashName(t.name) % TEAM_COLORS.length];
    const name = bold(fg(color, t.name));
    const role = fg("muted", `(${displayRole(t.role)})`);
    const status = t.status === "running" ? fg("warning", runningTaskLabel(t)) : fg("dim", "○ idle");
    lines.push(fit(`${name} ${role} ${status}`));
  }
  lines.push(fit(fg("dim", "/teammate — open console")));
  return lines;
}

/** Full content of a task as shown on an agent's detail page: description,
 * dependencies, spawn lifecycle (pid/status/timing/exit/timeout/usage), the
 * worker's final report (stdout), stderr, result and error. The worker output
 * is the agent's actual "running content" — previously hidden behind a
 * one-line status. */
function buildTaskSection(t: Task): string[] {
  const lines: string[] = [`- [${t.id}] ${t.status}: ${t.title}`];
  if (t.description) lines.push(`  ${t.description}`);
  if (t.blockedBy.length > 0) lines.push(`  Blocked by: ${t.blockedBy.join(", ")}`);
  if (t.blocks.length > 0) lines.push(`  Blocks: ${t.blocks.join(", ")}`);

  const spawn = t.spawn;
  if (spawn) {
    const stateLabel = spawn.status === "running" ? `running (pid ${spawn.pid})` : spawn.status;
    lines.push(`  Spawn: ${stateLabel}`);
    if (spawn.startedAt) lines.push(`  Started: ${new Date(spawn.startedAt).toLocaleString()}`);
    if (spawn.finishedAt) lines.push(`  Finished: ${new Date(spawn.finishedAt).toLocaleString()}`);
    if (spawn.exitCode !== undefined) lines.push(`  Exit code: ${spawn.exitCode}`);
    if (spawn.timedOut) lines.push("  Timed out: yes");
    if (spawn.usage) {
      const u = spawn.usage;
      lines.push(`  Usage: ${u.totalTokens} tokens (in ${u.input} / out ${u.output}) | cost $${u.cost}`);
    }
    if (spawn.error) lines.push(`  Spawn error: ${spawn.error}`);
    if (spawn.stdout) {
      lines.push("  --- Worker output ---");
      lines.push(...spawn.stdout.split("\n"));
    }
    if (spawn.stderr) {
      lines.push("  --- Worker stderr ---");
      lines.push(...spawn.stderr.split("\n"));
    }
  }

  // Completed spawns already fold stdout into task.result (setSpawnInfo) — avoid
  // printing the same report twice. Standalone results (update_task_status or a
  // worker-written state file) are still shown here.
  if (t.result && t.result !== spawn?.stdout) lines.push(`  Result: ${t.result}`);
  if (t.errorMessage) lines.push(`  Error: ${t.errorMessage}`);
  return lines;
}

/**
 * Write the leader's read flags back into the shared state file so the
 * SENDER (the worker) can see the read receipt: once the team leader has
 * read a message, the file copy shows read:true and the worker sees
 * "leader received ✓".
 */
function syncReadFlagsToFile(): void {
  if (!liveStateFile) return;
  try {
    applyWorkerEvents(liveStateFile);
    writeStateFile(liveStateFile, getState());
  } catch {
    // Never break reading on a receipt-sync failure.
  }
}

/**
 * Publish the parent's current board to the shared state file so running
 * workers see leader-side changes (new messages, task status) — without this,
 * message/broadcast/assign only touched the parent's memory and the
 * worker's mailbox watch never saw the message.
 */
function publishToStateFile(): void {
  if (!liveStateFile) return;
  try {
    applyWorkerEvents(liveStateFile);
    writeStateFile(liveStateFile, getState());
  } catch {
    // Best effort — the in-memory board is authoritative.
  }
}

/** Teammate detail: special sections (unread, tasks) + the FULL conversation —
 * every message the teammate received (←) and every message it sent (→),
 * merged and sorted by time. */
function buildTeammateDetail(name: string): string[] {
  const teammate = getTeammate(name);
  if (!teammate) return ["(removed)"];
  const incoming = readMailbox(name, { unreadOnly: false, markRead: false });
  const unread = incoming.filter((m) => !m.read);
  const outgoing = listAllMessages().filter((m) => m.from === name);
  const conversation = [...incoming, ...outgoing].sort((a, b) => a.timestamp - b.timestamp);
  const tasks = listTasks({ assignee: name });

  const lines: string[] = [
    `${teammate.name} (${displayRole(teammate.role)}) [${teammate.status}]`,
    teammate.description,
    teammate.model ? `Model: ${teammate.model}` : "",
    `Prompt: ${teammate.prompt}`,
    "",
    `== ${unread.length} unread message(s) ==`,
    ...(unread.length === 0 ? ["(none)"] : unread.map((m) => `[${m.id}] ${m.subject} — from ${m.from}`)),
    "",
    `== ${tasks.length} task(s) ==`,
    ...(tasks.length === 0 ? ["(none)"] : tasks.flatMap(buildTaskSection)),
    "",
    `== all conversations (${conversation.length}) ==`,
    ...(conversation.length === 0
      ? ["(no messages yet)"]
      : conversation.flatMap((m) => {
          const sent = m.from === name;
          const peer = sent ? m.to : m.from;
          const time = new Date(m.timestamp).toLocaleString();
          // Read status: outgoing → whether the leader received/read it (read
          // receipt); incoming → whether the teammate read it.
          const receipt = sent
            ? m.to === "agent"
              ? m.read
                ? "✓ leader received"
                : "○ leader pending"
              : ""
            : m.read
              ? "✓ read"
              : "● unread";
          return [
            `${sent ? "→" : "←"} [${m.id}] ${m.subject} — ${sent ? `to ${peer}` : `from ${peer}`} | ${time}${receipt ? ` | ${receipt}` : ""}`,
            m.taskId ? `  task ${m.taskId}` : "",
            m.body,
            "",
          ];
        })),
  ];
  return lines;
}

/**
 * Full-screen Team Console — owns input via ctx.ui.custom, so ↑/↓ and Enter are
 * safe in here and nothing is intercepted globally. Modes: list / detail.
 */
function openTeamConsole(ctx: { ui: ExtensionUIContext }): Promise<void> {
  return ctx.ui.custom<void>((_tui, theme, _keybindings, done) => {
    let mode: "list" | "detail" = "list";
    let selected = 0;
    let detailName = "";
    let replyMode = false;
    let replyBuffer = "";
    let offset = 0;
    const WINDOW = 20;
    const up = /^\u001b\[(?:[0-9;:]*)?A$|^\u001bOA$/;
    const down = /^\u001b\[(?:[0-9;:]*)?B$|^\u001bOB$/;

    // btw-style callbacks (same accent/muted/dim/border/success/error language as @fradser/pi-btw).
    const style = {
      accent: (s: string) => theme.fg("accent", s),
      muted: (s: string) => theme.fg("muted", s),
      dim: (s: string) => theme.fg("dim", s),
      border: (s: string) => theme.fg("border", s),
      success: (s: string) => theme.fg("success", s),
      error: (s: string) => theme.fg("error", s),
    };

    const windowLines = (full: string[], width: number): string[] => {
      const contentWidth = Math.max(20, width - 4);
      const maxOffset = Math.max(0, full.length - WINDOW);
      if (offset > maxOffset) offset = maxOffset;
      const wrapped: string[] = [];
      for (const line of full.slice(offset, offset + WINDOW)) {
        wrapped.push(...wrapTextWithAnsi(line, contentWidth));
      }
      if (full.length > WINDOW) {
        wrapped.push(style.dim(`… ${full.length - WINDOW} more lines — ↑/↓`));
      }
      return wrapped;
    };

    const renderList = (width: number): string[] => {
      const rows = buildPanelRows();
      if (selected >= rows.length) selected = Math.max(0, rows.length - 1);
      const border = style.border("─".repeat(Math.max(1, width)));
      const lines: string[] = [
        border,
        style.accent(truncateToWidth(`teammate  ${listTeammates().length} teammate(s)`, width)),
        "",
      ];
      for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        const marker = i === selected ? style.accent("❯ ") : "  ";
        const t = getTeammate(row.name);
        if (!t) continue;
        const color = TEAM_COLORS[hashName(t.name) % TEAM_COLORS.length];
        const name = theme.bold(theme.fg(color, t.name));
        const role = style.muted(`(${displayRole(t.role)})`);
        const status = t.status === "running" ? theme.fg("warning", runningTaskLabel(t)) : style.dim("○ idle");
        lines.push(`${marker}${name} ${role} ${status}`);
      }
      lines.push("", style.dim("↑↓ select · enter open · r reply · esc interrupt · x stop · q close"), border);
      return lines.map((l) => truncateToWidth(l, Math.max(10, width - 1)));
    };

    const renderDetail = (width: number): string[] => {
      const border = style.border("─".repeat(Math.max(1, width)));
      const lines = [
        border,
        style.accent(truncateToWidth(`teammate  ${detailName}`, width)),
        "",
        ...windowLines(buildTeammateDetail(detailName), width).map((l) => `  ${l}`),
        "",
        replyMode
          ? style.accent(`  Reply to ${detailName}: ${replyBuffer}_(enter send, esc cancel)`)
          : style.dim("  esc back · r reply · q close"),
        border,
      ];
      return lines.map((l) => truncateToWidth(l, Math.max(10, width - 1)));
    };

    return {
      render: (width) =>
        mode === "list" ? renderList(width) : renderDetail(width),
      invalidate: () => {},
      handleInput: (data: string) => {
        // Detail-mode inline reply input.
        if (mode === "detail" && replyMode) {
          if (isEscapeKey(data)) {
            replyMode = false;
            return;
          }
          if (data === "\r" || data === "\n") {
            if (replyBuffer.trim()) {
              sendMessage({ from: "agent", to: detailName, subject: "Direct message", body: replyBuffer.trim() });
              refreshTeamUI(ctx);
              ctx.ui.notify(`Message sent to ${detailName}.`, "info");
            }
            replyMode = false;
            replyBuffer = "";
            return;
          }
          if (data === "\x7f" || data === "\x08") {
            replyBuffer = replyBuffer.slice(0, -1);
            return;
          }
          if (data.length === 1 && data >= " " && data < "\x7f") replyBuffer += data;
          return;
        }

        // Detail mode: Esc returns to the list, q closes, r replies.
        if (mode !== "list") {
          if (isEscapeKey(data)) {
            mode = "list";
            offset = 0;
            return;
          }
          if (data === "q" || data === "Q") {
            done();
            return;
          }
          if (mode === "detail" && (data === "r" || data === "R")) {
            replyMode = true;
            return;
          }
          if (down.test(data)) offset++;
          if (up.test(data)) offset--;
          return;
        }

        // List mode — the console owns input, so ↑/↓/Enter are safe here.
        const rows = buildPanelRows();
        if (down.test(data)) selected = Math.min(selected + 1, rows.length - 1);
        if (up.test(data)) selected = Math.max(selected - 1, 0);
        if (data === "\r" || data === "\n") {
          const row = rows[Math.min(selected, rows.length - 1)];
          if (row.name) {
            mode = "detail";
            detailName = row.name;
            offset = 0;
          }
          return;
        }
        if (isEscapeKey(data) || data === "q" || data === "Q") {
          done();
          return;
        }
        if (data === "x" || data === "X") {
          const row = rows[Math.min(selected, rows.length - 1)];
          if (row.name) {
            const t = getTeammate(row.name);
            if (t?.status === "running" && killWorker(row.name, "SIGKILL")) {
              ctx.ui.notify(`Stopped ${row.name}'s worker.`, "info");
            }
          }
          return;
        }
      },
    };
  });
}

/** Wire the passive widget (display only). No input interception. */
function setupTeamWidget(ctx: { ui: ExtensionUIContext; mode: string }): void {
  if (ctx.mode !== "tui") return;
  ctx.ui.setWidget("teammate", (tui, theme) => {
    panelRequestRender = () => tui.requestRender();
    ensureSpinner();
    return {
      render: (width) => panelRows(theme, width),
      invalidate: () => {},
      dispose: () => {
        stopUiTimers();
        panelRequestRender = undefined;
      },
    };
  });
}

const WORKER_GUIDANCE = `
## Spawned Teammate Protocol

You are a worker, not the team leader. Work only on the task bound to this process. Read the leader-owned snapshot through teammate_inbox; do not mutate it. Use teammate_message for leader or peer handoffs, teammate_inbox to consume messages, and teammate_report for progress/final status. Do not use leader coordination tools, claim new tasks, change another teammate's task, or overwrite shared files outside your assigned scope.
`;

const TEAMMATE_GUIDANCE = `
## Agent Teams Orchestration

You are the team leader: the current Pi session owns decomposition, delegation, synchronization, and the final user-facing answer. Teammates are isolated workers; they do not see this conversation unless you put the needed context in their task or send it through teammate_message.

### When to use a team

Use teammates when the work has genuinely independent streams, specialist boundaries, large context, or a latency benefit from parallel execution. Do not delegate tiny edits or a task that requires constant shared decisions. Prefer one task per clear outcome and avoid overlapping file ownership.

### Design a teammate

Register a teammate with a stable, descriptive name, the narrowest useful role, an explicit responsibility, and only the tools it needs. A good teammate prompt answers:
- Role: what perspective or capability does this teammate own?
- Goal: one observable outcome, not a vague area of work.
- Context: relevant paths, requirements, constraints, and decisions already made.
- Procedure: what to inspect or do, in what order.
- Deliverable: exact file/report/test/result expected, including its location.
- Boundaries: files it may change, files it must not touch, and what it should do when blocked.
- Completion: how to verify the result and how to report status, risks, and follow-up work.

Example task description:
"Audit packages/api/src/auth.ts for token refresh bugs. Read the adjacent tests first. Do not edit files. Reproduce any suspected bug, report each finding with severity, exact lines, evidence, and a minimal fix recommendation. If no issue is confirmed, say so and list the checks performed."

### Assign and run work

1. Decompose the user goal into independent outcomes; create tasks with concise titles and complete descriptions.
2. Assign each task to the teammate whose role matches it. Add blockedBy dependencies only when a real artifact or decision is required first.
3. Spawn independent ready tasks in the same turn so workers run concurrently. Each spawn returns immediately.
4. Call teammate_wait with task IDs only when their final outcomes are needed; do not serialize independent work.
5. Give reviewers the artifact, diff, or task ID to review and ask for evidence rather than general opinions.
6. After teammate_wait, synthesize the results yourself: reconcile conflicts, inspect important outputs, run verification, and communicate one final answer.

### Communication and session delivery

Use teammate_message for every handoff, decision, blocker, and update. Workers may target one teammate or agent (the main session); the leader may target one teammate, or to=all with an optional role filter to broadcast. Use teammate_inbox to bring worker messages into this session conversation; the TUI is intentionally limited to teammate/task status and does not duplicate mailbox alerts.

### Failure and cleanup

Treat failed, timed-out, cancelled, and missing results explicitly. Do not silently accept a worker's claim: inspect its deliverable and run the relevant tests. Keep task titles short, use task descriptions for detail, and clean finished tasks only after their results have been synthesized or recorded.

Available orchestration tools include teammate_register, teammate_configure, teammate_create_task, teammate_start_task, teammate_cancel_task, teammate_wait, teammate_message, teammate_inbox, teammate_list_tasks, and teammate_cleanup.
`;

export default function (pi: ExtensionAPI) {
  // A spawned child receives only identity-bound outbox capabilities. Do not
  // register session lifecycle, UI, board, or spawn tools in this process.
  if (workerOutboxBinding()) {
    pi.on("before_agent_start", async (event) => ({
      systemPrompt: event.systemPrompt + WORKER_GUIDANCE,
    }));
    registerWorkerCapabilities(pi);
    return;
  }

  // ── Session lifecycle ───────────────────────────────────────────

  pi.on("session_start", async (_event, ctx) => {
    spinnerFrame = 0;
    // Restore persisted state, then ALWAYS surface the footer status — including
    // the empty state. Gating it on a restored snapshot left fresh sessions with
    // no status until a teammate was registered (or state was restored).
    tryRestoreState(ctx.sessionManager);
    setupTeamWidget(ctx);
    liveStateFile = stateFilePath(ctx.sessionManager.getSessionFile(), ctx.cwd || process.cwd());
    // No footer status for the team — the panel widget owns the display.
    ctx.ui.setStatus("teammate", undefined);
    refreshTeamUI(ctx);
    // Sweep abandoned shared state dirs from older sessions.
    void cleanupExpiredStateDirs(STATE_DIR_MAX_AGE_MS);
  });

  pi.on("session_shutdown", async (_event, ctx) => {
    stopUiTimers();
    if (livePollTimer) {
      clearInterval(livePollTimer);
      livePollTimer = undefined;
    }
    persistState(pi);
    // The shared state file is a working medium for spawns; drop it when the
    // session ends so ~/.pi/agent/teammate/ never accumulates one dir per run.
    removeSessionStateDir(ctx.sessionManager.getSessionFile(), process.cwd());
  });

  pi.on("turn_end", async () => {
    persistState(pi);
  });

  // ── Inject teammate guidance into system prompt ─────────────────

  pi.on("before_agent_start", async (event) => {
    return {
      systemPrompt: event.systemPrompt + TEAMMATE_GUIDANCE,
    };
  });

  // ── Leader tools ─────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_register",
    promptSnippet: "Register a teammate agent (worker/reviewer/specialist/observer)",
    label: "Register Teammate",
    description: [
      "Register a new teammate agent with a concise name, focused role, explicit responsibility, and reusable prompt.",
      "Roles: worker (default executor), reviewer (code review), specialist (domain expert), observer (read-only).",
      "The prompt must define the role, method, boundaries, deliverable, and completion criteria.",
    ].join(" "),
    parameters: TeammateRegisterParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const result = registerTeammate({
        name: params.name,
        role: params.role as TeammateRole,
        description: params.description,
        prompt: params.prompt,
        model: params.model,
        tools: params.tools,
        registeredAt: Date.now(),
      });

      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error ?? "Failed to register teammate." }],
          details: {},
          isError: true,
        };
      }

      persistState(pi);
      refreshTeamUI(ctx);

      return {
        content: [
          {
            type: "text",
            text: [
              `Registered teammate "${params.name}" (${displayRole(params.role)}).`,
              `Registered teammates: ${listTeammates().map((t) => `${t.name} (${displayRole(t.role)})`).join(", ")}`,
            ].join("\n"),
          },
        ],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_list",
    promptSnippet: "List all registered teammates",
    label: "List Teammates",
    description: "List all registered teammates with their roles and descriptions.",
    parameters: EmptyParams,

    async execute() {
      const teammates = listTeammates();
      if (teammates.length === 0) {
        return {
          content: [{ type: "text", text: "No teammates registered yet. Use teammate_register to add one." }],
          details: {},
        };
      }

      const lines: string[] = ["## Registered Teammates\n"];
      for (const t of teammates) {
        const unread = getUnreadCount(t.name);
        const liveness = t.status === "running" ? `working... · ${shortTaskTitle(t.currentTaskId)}` : "idle";
        lines.push(`- **${t.name}** (${displayRole(t.role)}) [${liveness}]`);
        lines.push(`  ${t.description}`);
        lines.push(`  Prompt: ${t.prompt}`);
        if (unread > 0) lines.push(`  - ${unread} unread message(s)`);
        if (t.model) lines.push(`  Model: ${t.model}`);
        if (t.tools && t.tools.length > 0) lines.push(`  Tools: ${t.tools.join(", ")}`);
        lines.push("");
      }

      return { content: [{ type: "text", text: lines.join("\n") }], details: {} };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_message",
    promptSnippet: "Send a direct message to a teammate",
    label: "Teammate Message",
    description: "Send a direct message to a registered teammate. Spawned teammates use the same tool to message peers or agent (the main session).",
    parameters: TeammateMessageParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      if (params.to !== "all" && params.role) {
        return { content: [{ type: "text", text: "The role filter is only valid when to is all." }], details: {}, isError: true };
      }
      const recipients = params.to === "all"
        ? listTeammates().filter((teammate) => !params.role || teammate.role === params.role)
        : [getTeammate(params.to)].filter((teammate): teammate is Teammate => Boolean(teammate));
      if (recipients.length === 0) {
        const target = params.to === "all" && params.role ? `role "${params.role}"` : `teammate "${params.to}"`;
        return { content: [{ type: "text", text: `No recipient found for ${target}.` }], details: {}, isError: true };
      }
      const messages = recipients.map((recipient) => sendMessage({
        from: "agent",
        to: recipient.name,
        subject: params.to === "all" ? `Broadcast: ${params.subject}` : params.subject,
        body: params.body,
        taskId: params.taskId,
      }));
      persistState(pi);
      publishToStateFile();
      refreshTeamUI(ctx);
      const target = params.to === "all" ? `${messages.length} teammate(s)` : `"${params.to}"`;
      return {
        content: [{ type: "text", text: `Message sent to ${target}.\nSubject: ${params.subject}` }],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_inbox",
    promptSnippet: "Read messages sent to the main session by teammates",
    label: "Teammate Inbox",
    description: "Read the main session's teammate inbox. Returned messages are marked read so workers can observe the receipt.",
    parameters: TeammateInboxParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      if (liveStateFile) applyWorkerEvents(liveStateFile);
      const messages = readMailbox("agent", {
        unreadOnly: params.unreadOnly ?? true,
        markRead: params.markRead ?? true,
      });
      if (params.markRead !== false) syncReadFlagsToFile();
      persistState(pi);
      refreshTeamUI(ctx);
      return { content: [{ type: "text", text: renderInbox("agent", messages) }], details: {} };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_create_task",
    promptSnippet: "Create and assign a task to a teammate",
    label: "Create Task",
    description: [
      "Create one focused outcome and assign it to a teammate. The team leader is the current main session,",
      "so this is always available. Put paths, constraints, procedure, deliverable, and verification in the description.",
      "Optionally specify blockedBy task IDs — inverse dependency edges are derived internally.",
      "The assignee will see the task in their task list and receive a mailbox notification.",
    ].join(" "),
    parameters: TeammateCreateTaskParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const assignee = getTeammate(params.assignee);
      if (!assignee) {
        return {
          content: [
            {
              type: "text",
              text: `Teammate "${params.assignee}" not found. Register them first with teammate_register.`,
            },
          ],
          details: {},
          isError: true,
        };
      }

      const created = createTask(params.title, params.description, params.assignee, "agent", params.blockedBy ?? []);
      if (!created.ok || !created.task) {
        return {
          content: [{ type: "text", text: created.error ?? "Failed to create task." }],
          details: {},
          isError: true,
        };
      }
      const task = created.task;

      sendMessage({
        from: "agent",
        to: params.assignee,
        subject: `New task: ${params.title}`,
        body: `You have been assigned a new task.\n\nTitle: ${params.title}\nDescription: ${params.description}\n\nTask ID: ${task.id}`,
        taskId: task.id,
      });

      persistState(pi);
      publishToStateFile();
      refreshTeamUI(ctx);

      const depNote = task.blockedBy.length > 0 ? `\nBlocked by: ${task.blockedBy.join(", ")}` : "";
      return {
        content: [
          {
            type: "text",
            text: [
              `Task created for "${params.assignee}".`,
              `Task ID: ${task.id}`,
              `Title: ${params.title}`,
              `Status: assigned`,
              depNote,
              "",
              `${params.assignee} has been notified via mailbox.`,
            ].filter(Boolean).join("\n"),
          },
        ],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_list_tasks",
    promptSnippet: "List tasks by status or assignee",
    label: "List Tasks",
    description: "List tasks, optionally filtered by status or assignee.",
    parameters: TeammateListTasksParams,

    async execute(_toolCallId, params) {
      const tasks = listTasks({
        status: params.status,
        assignee: params.assignee,
      });

      if (tasks.length === 0) {
        let msg = "No tasks found.";
        if (params.status) msg += ` Status: ${params.status}.`;
        if (params.assignee) msg += ` Assignee: ${params.assignee}.`;
        return { content: [{ type: "text", text: msg }], details: {} };
      }

      const lines: string[] = ["## Tasks\n"];
      for (const task of tasks) {
        const statusIcon =
          task.status === "completed"
            ? "\u2713"
            : task.status === "failed"
              ? "\u2717"
              : task.status === "in_progress"
                ? "\u22EF"
                : task.status === "cancelled"
                  ? "\u2212"
                  : "\u25CB";
        lines.push(`### ${statusIcon} [${task.id}] ${task.title}`);
        lines.push(`Assignee: ${task.assignee} | Status: ${task.status}`);
        if (task.spawn) {
          const spawn = task.spawn;
          const stateLabel = spawn.status === "running" ? "running (pid " + spawn.pid + ")" : spawn.status;
          lines.push(`Spawn: ${stateLabel}`);
          if (spawn.timedOut) lines.push(`Timed out: yes`);
          if (spawn.usage) {
            const u = spawn.usage;
            lines.push(`Usage: ${u.totalTokens} tokens (in ${u.input} / out ${u.output}) | cost $${u.cost}`);
          }
        }
        if (task.blockedBy.length > 0) lines.push(`Blocked by: ${task.blockedBy.join(", ")}`);
        if (task.blocks.length > 0) lines.push(`Blocks: ${task.blocks.join(", ")}`);
        lines.push(cap(task.description));
        if (task.result) lines.push(`Result: ${cap(task.result)}`);
        if (task.errorMessage) lines.push(`Error: ${cap(task.errorMessage)}`);
        lines.push(`Created: ${new Date(task.createdAt).toLocaleString()}`);
        if (task.completedAt) lines.push(`Completed: ${new Date(task.completedAt).toLocaleString()}`);
        lines.push("");
      }

      return { content: [{ type: "text", text: lines.join("\n") }], details: {} };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_wait",
    promptSnippet: "Wait for parallel teammate tasks to finish",
    label: "Wait for Teammates",
    description: [
      "Wait for a group of asynchronously spawned tasks to reach terminal status.",
      "Use this after starting independent tasks to",
      "coordinate parallel execution and collect their results together."
    ].join(" "),
    parameters: TeammateWaitParams,

    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const taskIds = [...new Set(params.taskIds)];
      const timeoutMs = params.timeoutMs ?? 5 * 60 * 1000;
      const missing = taskIds.filter((id) => !listTasks().some((task) => task.id === id));
      if (missing.length > 0) {
        return {
          content: [{ type: "text", text: `Task(s) not found: ${missing.join(", ")}.` }],
          details: {},
          isError: true,
        };
      }

      const terminal = new Set(["completed", "failed", "cancelled"]);
      const isSettled = (task: Task): boolean => terminal.has(task.status) && task.spawn?.status !== "running";
      const deadline = Date.now() + timeoutMs;

      while (true) {
        if (liveStateFile) applyWorkerEvents(liveStateFile);
        const tasks = taskIds.map((id) => listTasks().find((task) => task.id === id)!);
        if (tasks.every(isSettled)) break;
        if (signal?.aborted) {
          return {
            content: [{ type: "text", text: "Waiting for parallel tasks was cancelled." }],
            details: {},
            isError: true,
          };
        }
        if (Date.now() >= deadline) {
          const pending = tasks.filter((task) => !isSettled(task)).map((task) => `${task.id} (${task.status})`);
          return {
            content: [{ type: "text", text: `Timed out waiting for: ${pending.join(", ")}.` }],
            details: {},
            isError: true,
          };
        }
        await new Promise<void>((resolve) => setTimeout(resolve, 1000));
      }

      const tasks = taskIds.map((id) => listTasks().find((task) => task.id === id)!);
      for (const task of tasks) markLeaderMessagesReadForTask(task.id, task.assignee);
      syncReadFlagsToFile();
      persistState(pi);
      refreshTeamUI(ctx);

      const lines = ["## Parallel tasks completed\n"];
      for (const task of tasks) {
        lines.push(`Task [${task.id}] ${task.status}: ${task.title}`);
        if (task.result) lines.push(`Result: ${cap(task.result)}`);
        if (task.errorMessage) lines.push(`Error: ${cap(task.errorMessage)}`);
        lines.push("");
      }
      return { content: [{ type: "text", text: lines.join("\n") }], details: {} };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_configure",
    promptSnippet: "Configure an existing teammate (description, prompt, model, tools)",
    label: "Configure Teammate",
    description: [
      "Configure an existing teammate's description, prompt, model, or tools.",
      "A running worker keeps the configuration it started with.",
    ].join(" "),
    parameters: TeammateConfigureParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const result = configureTeammate(params.name, {
        description: params.description,
        prompt: params.prompt,
        model: params.model,
        tools: params.tools,
      });
      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error ?? "Failed to configure teammate." }],
          details: {},
          isError: true,
        };
      }
      persistState(pi);
      refreshTeamUI(ctx);
      const changed = [
        params.description !== undefined ? "description" : "",
        params.prompt !== undefined ? "prompt" : "",
        params.model !== undefined ? "model" : "",
        params.tools !== undefined ? "tools" : "",
      ].filter(Boolean).join(", ");
      return {
        content: [
          {
            type: "text",
            text: `Teammate "${params.name}" configured: ${changed} (next start).`,
          },
        ],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_start_task",
    promptSnippet: "Start an autonomous child Pi worker to execute a task",
    label: "Start Task",
    description: [
      "Start a real child Pi process as a fully autonomous teammate and return immediately.",
      "For independent work, start every ready task in the same turn, then call teammate_wait with all task IDs when results are needed.",
      "The worker watches its inbox through the leader-owned state snapshot and decides when to close.",
      "The task must be ready: every blockedBy task must be completed or cancelled.",
      "Set retry=true to explicitly restart a failed task with a fresh run identity.",
    ].join(" "),
    parameters: TeammateStartTaskParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const task = listTasks().find((t) => t.id === params.taskId);
      if (!task) {
        return {
          content: [{ type: "text", text: `Task "${params.taskId}" not found.` }],
          details: {},
          isError: true,
        };
      }

      // Resolve the teammate from the task's assignee.
      const teammate = getTeammate(task.assignee);
      if (!teammate) {
        return {
          content: [{ type: "text", text: `Teammate "${task.assignee}" (assignee of task "${params.taskId}") not found.` }],
          details: {},
          isError: true,
        };
      }

      if (teammate.status === "running") {
        return {
          content: [{ type: "text", text: `Teammate "${teammate.name}" is already running task "${teammate.currentTaskId ?? "unknown"}".` }],
          details: {},
          isError: true,
        };
      }

      // Handle retry: only when explicitly requested and the task is failed.
      if (params.retry === true) {
        if (task.status !== "failed") {
          return {
            content: [{ type: "text", text: `Task "${params.taskId}" is ${task.status}, not failed — retry is only for failed tasks.` }],
            details: {},
            isError: true,
          };
        }
        const retry = retryFailedTask(params.taskId);
        if (!retry.ok) {
          return { content: [{ type: "text", text: retry.error ?? "Could not retry failed task." }], details: {}, isError: true };
        }
      } else if (task.status === "failed") {
        return {
          content: [{ type: "text", text: `Task "${params.taskId}" is failed — use retry=true to restart it.` }],
          details: {},
          isError: true,
        };
      } else if (task.status !== "assigned") {
        return {
          content: [{ type: "text", text: `Task "${params.taskId}" cannot start from status "${task.status}".` }],
          details: {},
          isError: true,
        };
      }

      const readiness = isTaskReady(params.taskId);
      if (!readiness.ready) {
        return {
          content: [
            {
              type: "text",
              text: [
                `Task "${params.taskId}" is not ready: blocked by ${readiness.unmet.join(", ")}.`,
                "Complete or cancel those tasks first.",
              ].join(" "),
            },
          ],
          details: {},
          isError: true,
        };
      }

      const sessionFile = ctx.sessionManager.getSessionFile();
      const cwd = ctx.cwd || process.cwd();
      const stateFile = stateFilePath(sessionFile, cwd);
      // Optional git worktree isolation: run the worker on its own branch.
      let worktree: ReturnType<typeof createWorktree> | undefined;
      if (params.isolation === "worktree") {
        worktree = createWorktree(cwd, params.taskId);
        if ("error" in worktree) {
          return {
            content: [{ type: "text", text: `Cannot isolate worker: ${worktree.error}` }],
            details: {},
            isError: true,
          };
        }
      }

      const runId = randomUUID();
      markTeammateRunning(teammate.name, params.taskId, runId);
      // Consume the assignment notification: the task has now started.
      markTaskNotificationsRead(params.taskId);
      updateTaskStatus(params.taskId, "in_progress");
      // Publish run identity, task state, and mailbox before the worker starts.
      writeStateFile(stateFile, getState());
      // Start the live poll now so messages and read receipts converge while
      // the main session continues independently of this worker.
      refreshTeamUI(ctx);

      const DEFAULT_TIMEOUT_MS = 30 * 60 * 1000;
      const timeoutMs = params.timeoutMs ?? DEFAULT_TIMEOUT_MS;
      const workerCwd = worktree && !("error" in worktree) ? worktree.cwd : cwd;
      const outboxFile = workerOutboxPath(stateFile, teammate.name, runId);
      const workerEnv = {
        PI_TEAMMATE_WORKER_NAME: teammate.name,
        PI_TEAMMATE_TASK_ID: task.id,
        PI_TEAMMATE_RUN_ID: runId,
        PI_TEAMMATE_STATE_FILE: stateFile,
        PI_TEAMMATE_OUTBOX_FILE: outboxFile,
      };

      const description = [
        buildAutonomousPrompt({
          name: teammate.name,
          role: teammate.role,
          prompt: teammate.prompt,
          taskId: task.id,
          taskTitle: task.title,
          stateFile,
          outboxFile,
          timeoutSec: Math.round(timeoutMs / 1000),
        }),
        "",
        "=== TASK ===",
        task.description,
      ].join("\n");

      const finish = (result: {
        pid: number;
        exitCode: number | null;
        signal: NodeJS.Signals | null;
        stdout: string;
        stderr: string;
        usage?: WorkerUsage;
        timedOut: boolean;
      }) => {
        // A forced removal/re-registration can leave an older process alive.
        // Its completion may never mutate a newer worker run.
        if (getTeammate(teammate.name)?.currentRunId !== runId) {
          if (worktree && !("error" in worktree)) cleanupWorktree(worktree);
          return;
        }
        // Drain validated worker events before recording the final process outcome.
        applyWorkerEvents(stateFile);
        let patchText = "";
        if (worktree && !("error" in worktree)) {
          const diff = captureWorktreeDiff(worktree);
          if (diff.patch.trim()) {
            patchText = `\n\n=== Worktree changes ===\n${diff.diffStat}\n\n${diff.patch}`;
          }
          cleanupWorktree(worktree);
        }
        const reportedTask = listTasks().find((candidate) => candidate.id === params.taskId);
        const wasCancelled = reportedTask?.status === "cancelled";
        const workerReportedFailure = reportedTask?.status === "failed";
        const ok = isSuccessfulWorkerExit(result) && !workerReportedFailure && !wasCancelled;
        setSpawnInfo(params.taskId, {
          runId,
          pid: result.pid,
          status: ok ? "completed" : "failed",
          startedAt: task.spawn?.startedAt ?? Date.now(),
          finishedAt: Date.now(),
          exitCode: result.exitCode ?? undefined,
          stdout: ok ? result.stdout + patchText : undefined,
          stderr: ok ? undefined : result.stderr,
          usage: result.usage,
          timedOut: result.timedOut,
          error: ok
            ? undefined
            : result.timedOut
              ? `Worker timed out after ${Math.round(timeoutMs / 1000)}s.`
              : result.signal
                ? `Worker was terminated by ${result.signal}.`
                : workerReportedFailure
                  ? reportedTask?.errorMessage ?? "Worker reported task failure."
                  : `Worker exited with code ${result.exitCode ?? "unknown"}.`,
        });
        markTeammateIdle(teammate.name, runId);
        if (ok) notifyUnblockedTasks(params.taskId);
        compactFinishedWorkerRun(stateFile, teammate.name, runId);
        persistState(pi);
        refreshTeamUI(ctx);
      };

      const spawnFailure = (error: Error | string) => {
        if (getTeammate(teammate.name)?.currentRunId !== runId) return;
        setSpawnInfo(params.taskId, {
          runId,
          pid: 0,
          status: "failed",
          startedAt: task.spawn?.startedAt ?? Date.now(),
          finishedAt: Date.now(),
          error: typeof error === "string" ? error : error.message,
        });
        markTeammateIdle(teammate.name, runId);
        if (worktree && !("error" in worktree)) discardWorktree(worktree);
        compactFinishedWorkerRun(stateFile, teammate.name, runId);
        persistState(pi);
        refreshTeamUI(ctx);
      };

      // ── Always asynchronous: worker outlives this tool call. ────────────
      const started = spawnPiWorker({
        workerName: teammate.name,
        description,
        model: teammate.model,
        tools: executionToolsFor(teammate),
        cwd: workerCwd,
        env: workerEnv,
        timeoutMs,
        onExit: (result) => finish(result),
        onError: (error) => spawnFailure(error),
      });

      if ("error" in started) {
        spawnFailure(started.error);
        return {
          content: [{ type: "text", text: `Failed to start worker: ${started.error}` }],
          details: {},
          isError: true,
        };
      }

      setSpawnInfo(params.taskId, {
        runId,
        pid: started.pid,
        status: "running",
        startedAt: Date.now(),
      });
      persistState(pi);
      refreshTeamUI(ctx);

      const isolationNote =
        params.isolation === "worktree" && worktree && !("error" in worktree)
          ? `Isolation: worktree ${worktree.path} (branch ${worktree.branch})`
          : "Isolation: none";
      return {
        content: [
          {
            type: "text",
            text: [
              `Started "${teammate.name}" for task [${params.taskId}] "${task.title}".`,
              `PID: ${started.pid} | Model: ${teammate.model ?? "default"} | Status: working (autonomous — watches its inbox until it decides to close)`,
              isolationNote,
              "The main session is free to continue. Call teammate_wait when you need this task's final outcome.",
            ].join("\n"),
          },
        ],
        details: {},
      };
    },
  });

  // ── Management tools: cancel task, remove teammate, clean up tasks ──

  pi.registerTool({
    name: "teammate_cancel_task",
    promptSnippet: "Cancel a task and stop its worker if running",
    label: "Cancel Task",
    description: [
      "Cancel a task, marking it terminal. If the task has a running worker,",
      "the worker receives SIGTERM and the run lifecycle eventually leaves working.",
      "Already-completed or already-cancelled tasks are rejected.",
    ].join(" "),
    parameters: TeammateCancelTaskParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const task = listTasks().find((t) => t.id === params.taskId);
      if (!task) {
        return {
          content: [{ type: "text", text: `Task "${params.taskId}" not found.` }],
          details: {},
          isError: true,
        };
      }
      const result = cancelTask(params.taskId);
      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error ?? "Failed to cancel task." }],
          details: {},
          isError: true,
        };
      }
      // If the task has a running worker, send SIGTERM.
      if (task.spawn?.status === "running") {
        killWorker(task.assignee, "SIGTERM");
      }
      persistState(pi);
      publishToStateFile();
      refreshTeamUI(ctx);

      return {
        content: [
          {
            type: "text",
            text: `Task [${params.taskId}] "${task.title}" cancelled.`,
          },
        ],
        details: {},
      };
    },
  });

  pi.registerTool({
    name: "teammate_remove",
    promptSnippet: "Unregister a teammate and delete its mailbox",
    label: "Remove Teammate",
    description: [
      "Unregister a teammate and delete its mailbox.",
      "Refuses while the teammate is running a worker.",
    ].join(" "),
    parameters: TeammateRemoveParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const result = removeTeammate(params.name);
      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error ?? "Failed to remove teammate." }],
          details: {},
          isError: true,
        };
      }
      persistState(pi);
      refreshTeamUI(ctx);
      return {
        content: [
          {
            type: "text",
            text: `Removed teammate "${params.name}".\nRemaining: ${listTeammates().length} teammate(s).`,
          },
        ],
        details: {},
      };
    },
  });



  pi.registerTool({
    name: "teammate_cleanup",
    promptSnippet: "Prune completed, failed, and cancelled tasks from the board",
    label: "Clean Up Tasks",
    description: "Remove all terminal tasks after their results have been synthesized. Working and assigned tasks are retained.",
    parameters: EmptyParams,

    async execute(_toolCallId, _params, _signal, _onUpdate, ctx) {
      const removed = pruneFinishedTasks();
      persistState(pi);
      refreshTeamUI(ctx);
      return {
        content: [{ type: "text", text: `Pruned ${removed} terminal task(s).\nTasks remaining: ${Object.keys(getState().tasks).length}` }],
        details: {},
      };
    },
  });

  // ── Team console (full-screen, owns input) ───────────────────────

  pi.registerCommand("teammate", {
    description: "Open the full-screen teammate team console: teammate status, task details, replies, interrupt/stop",
    handler: async (_args, ctx) => {
      if (ctx.mode !== "tui") {
        ctx.ui.notify(getSummary() ?? "No teammates registered.", "info");
        return;
      }
      await openTeamConsole(ctx);
      refreshTeamUI(ctx);
    },
  });
}