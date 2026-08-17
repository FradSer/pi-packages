/**
 * @fradser/pi-agent-teams — Pi extension for run-centric agent teams.
 *
 * Agents are declarative Markdown files (bundled, user, and project scopes).
 * A run is a dependency-aware task graph dispatched in a single call; each
 * node is a bounded child-process worker with a best-effort mailbox (validated
 * delivery, no read receipts) and per-spawn identity validation.
 *
 * Leader tools: teammate_run, teammate_status, teammate_cancel,
 * teammate_retry, teammate_message.
 *
 * Spawned workers receive teammate_message.
 */

import { randomUUID } from "node:crypto";
import { Key, matchesKey, truncateToWidth } from "@earendil-works/pi-tui";
import type { ExtensionAPI, ExtensionUIContext, Theme, ThemeColor } from "@earendil-works/pi-coding-agent";
import { truncateTail, DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES } from "@earendil-works/pi-coding-agent";
import { discoverAgents, resolveAgent, type AgentDefinition } from "./agents";
import {
  TeammateCancelParams,
  TeammateMessageParams,
  TeammateRetryParams,
  TeammateRunParams,
  TeammateStatusParams,
  type Node,
  type Run,
  type SpawnInfo,
  type WorkerEvent,
} from "./types";
import {
  cancelBlockedDependents,
  cancelNode,
  cancelRun,
  clearWorkerRunEvents,
  createRun,
  failRunTimeout,
  findSharedWorkspaceWriteConflict,
  getNode,
  getNodeByWorkerKey,
  getRun,
  getState,
  getSummary,
  handoffNodeResult,
  listAllMessages,
  listNodes,
  listRuns,
  markNodeRunning,
  markRunCompletionDelivered,
  readyPendingNodes,
  receiveWorkerMessage,
  resetState,
  resolveLeaderRecipient,
  resolveWorkerRecipient,
  resolveWorkerRecipientFromRuns,
  retryRun,
  runningNodeCount,
  sendMessage,
  settleRun,
  setNodeSpawnInfo,
  SUMMARY_NODE_ID,
  updateNodeSpawnProgress,
  updateNodeStatus,
} from "./state";
import {
  buildAutonomousPrompt,
  CancellationIntents,
  finishReportedWorker,
  isCompletedWorkerExit,
  POST_REPORT_GRACE_MS,
  spawnPiWorker,
  terminateAllWorkers,
  terminateWorker,
  type WorkerProcessResult,
} from "./spawner";
import { buildNodeTerminalResult } from "./terminal";
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
import {
  clampConsoleScroll,
  consoleScrollRange,
  maxConsoleBody,
  scrollConsoleDetail,
  wrapConsoleDetail,
} from "./console-viewport";

/** Keep shared state dirs for at most 7 days after their last write. */
const STATE_DIR_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
/** Per-node hard wall-clock cap before the worker is killed. */
const DEFAULT_NODE_TIMEOUT_MS = 30 * 60 * 1000;
const cancellationIntents = new CancellationIntents();
const reportedWorkerShutdowns = new Set<string>();

/** Truncate worker/node output to the built-in tool-output limits (50KB / 2000 lines). */
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
      && (event.status === undefined || ["in_progress", "completed", "failed"].includes(event.status as string))
      && (event.taskId === undefined || typeof event.taskId === "string");
  }
  return false;
}

/** Apply complete, validated event records from every running node's outbox. */
function applyWorkerEvents(stateFile: string): void {
  const state = getState();
  for (const run of Object.values(state.runs)) {
    for (const node of Object.values(run.nodes)) {
      const spawn = node.spawn;
      if (!spawn || spawn.status !== "running") continue;
      const spawnId = spawn.runId;
      const outboxKey = `${node.workerKey}:${spawnId}`;
      const outbox = workerOutboxPath(stateFile, node.workerKey, spawnId);
      const { events, nextOffset } = readWorkerEvents(outbox, state.workerEventOffsets[outboxKey] ?? 0);
      state.workerEventOffsets[outboxKey] = nextOffset;
      for (const value of events) {
        if (!isWorkerEvent(value) || state.workerEventIds[`${spawnId}:${value.id}`]) continue;
        const event = value;
        if (event.worker !== node.workerKey || event.runId !== spawnId) continue;
        if (event.type === "message") {
          const recipient = resolveWorkerRecipientFromRuns(state.runs, node.workerKey, event.to);
          if (!recipient.ok) continue;
          state.workerEventIds[`${spawnId}:${event.id}`] = spawnId;
          receiveWorkerMessage({
            id: event.id,
            worker: node.workerKey,
            runId: spawnId,
            type: "message",
            to: recipient.to,
            subject: event.subject,
            body: event.body,
            taskId: event.taskId === node.id ? run.id : undefined,
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
    removeWorkerOutbox(stateFile, workerKey, spawnId);
  } catch {
    // Best-effort compaction — the in-memory board is authoritative.
  }
}

let leaderPi: ExtensionAPI | undefined;
/** Dispatch context for paths that run outside a tool call (poll-driven run timeouts). */
let leaderCtx: DispatchCtx | undefined;

function sendMainSessionUpdate(subject: string, body: string, runId?: string): void {
  try {
    leaderPi?.sendMessage({
      customType: "teammate-update",
      content: `Teammate update — ${subject}${runId ? ` [${runId}]` : ""}\n${body}`,
      display: true,
      details: { runId },
    }, { triggerTurn: true, deliverAs: "followUp" });
  } catch {
    // A late run event must not prevent cleanup during shutdown.
  }
}

/** Register the only coordination capabilities available to a spawned worker. */
function registerWorkerCapabilities(pi: ExtensionAPI): void {
  pi.registerTool({
    name: "teammate_message",
    promptSnippet: "Send a direct message or final report",
    label: "Teammate Message",
    description: "Worker-only sender. Addresses team-leader (the main session) or a same-run peer (node id or runId:nodeId). Set status=\"completed\"|\"failed\" to deliver final results to team-leader.",
    parameters: TeammateMessageParams,
    async execute(_toolCallId, params) {
      const binding = workerOutboxBinding();
      if (!binding) throw new Error("This capability is available only inside a spawned teammate.");
      const snapshot = readStateFile(binding.stateFile);
      if (!snapshot) throw new Error("Shared state snapshot is unavailable.");
      const recipient = resolveWorkerRecipientFromRuns(snapshot.runs, binding.worker, params.to);
      if (!recipient.ok) throw new Error(recipient.error);
      appendWorkerEvent(binding.outbox, {
        id: randomUUID(),
        type: "message",
        worker: binding.worker,
        runId: binding.runId,
        to: recipient.to,
        subject: params.subject,
        body: params.body,
        status: params.status,
        taskId: binding.taskId,
      });
      const statusNote = params.status ? ` with status "${params.status}"` : "";
      return { content: [{ type: "text", text: `Queued message to ${recipient.to}${statusNote}.` }], details: {} };
    },
  });
}

// ── Team UI: passive widget + full-screen console ──────────────────
// The widget above the editor is DISPLAY-ONLY. ALL interaction happens in the
// full-screen Team Console (/teammate), which owns input via ctx.ui.custom.

const TEAM_COLORS = ["accent", "success", "warning", "error", "toolTitle", "mdLink"] as const;
const PANEL_IDLE_COLLAPSE_MS = 30_000;
const SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
const SPINNER_MS = 120;

let panelRequestRender: (() => void) | undefined;
let spinnerTimer: ReturnType<typeof setInterval> | undefined;
let spinnerFrame = 0;
let panelLastActivity = 0;
let panelCollapseTimer: ReturnType<typeof setTimeout> | undefined;
let widgetRegistered = false;

/** Stable per-node color (independent of row order). */
function hashName(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return Math.abs(h);
}

interface PanelRow {
  key: string;
}

/** Console/widget rows contain node status only; messages use the mailbox tool. */
function buildPanelRows(): PanelRow[] {
  return listNodes().map((node) => ({ key: node.workerKey }));
}

function shortRunLabel(runId: string): string {
  const run = getRun(runId);
  if (!run) return runId;
  return `${runId} (${Object.keys(run.nodes).length} node${Object.keys(run.nodes).length === 1 ? "" : "s"})`;
}

function runningTeammateLabel(node: Node): string {
  const frame = SPINNER_FRAMES[spinnerFrame];
  const tool = node.spawn?.activeTool;
  const thinking = (node.spawn?.liveThinking ?? "").split("\n").map((l) => l.trim()).find((l) => l.length > 0) ?? "";
  const live = (node.spawn?.liveText ?? "").split("\n").map((l) => l.trim()).find((l) => l.length > 0) ?? "";
  // Like the memory package's activity line: show what the worker is doing
  // right now — current tool when one is executing, else its live reasoning,
  // else the latest assistant text.
  const detail = tool
    ? ` ${tool}`
    : thinking
      ? ` ${truncateToWidth(thinking, 48)}`
      : live
        ? ` ${truncateToWidth(live, 48)}`
        : " working...";
  return `${frame}${detail}`;
}

function ensureSpinner(): void {
  const running = listNodes().some((node) => node.status === "running");
  if (running && !spinnerTimer) {
    spinnerTimer = setInterval(() => {
      spinnerFrame = (spinnerFrame + 1) % SPINNER_FRAMES.length;
      panelRequestRender?.();
    }, SPINNER_MS);
    spinnerTimer.unref?.();
  } else if (!running && spinnerTimer) {
    clearInterval(spinnerTimer);
    spinnerTimer = undefined;
  }
}

function isPanelCollapsed(): boolean {
  return Date.now() - panelLastActivity > PANEL_IDLE_COLLAPSE_MS;
}

function scheduleIdleCollapse(): void {
  if (panelCollapseTimer) clearTimeout(panelCollapseTimer);
  panelCollapseTimer = setTimeout(() => panelRequestRender?.(), PANEL_IDLE_COLLAPSE_MS);
  panelCollapseTimer.unref?.();
}

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

function ensureTeamWidget(ctx?: { ui?: ExtensionUIContext; mode?: string }): void {
  if (widgetRegistered || !ctx?.ui?.setWidget) return;
  if (ctx.mode && ctx.mode !== "tui") return;
  try {
    ctx.ui.setWidget("teammate", (tui, theme) => {
      panelRequestRender = () => tui.requestRender();
      ensureSpinner();
      return {
        render: (width) => panelRows(theme, width),
        invalidate: () => {},
        dispose: () => {
          stopUiTimers();
          panelRequestRender = undefined;
          widgetRegistered = false;
        },
      };
    });
    widgetRegistered = true;
  } catch {
    // Best effort if widget registration is unavailable in the current mode.
  }
}

function refreshTeamUI(ctx?: { ui?: ExtensionUIContext; mode?: string }): void {
  ensureTeamWidget(ctx);
  panelLastActivity = Date.now();
  scheduleIdleCollapse();
  ensureLivePoll();
  ensureSpinner();
  panelRequestRender?.();
}

// ── Live worker-event drain while nodes run ───────────────────────

let liveStateFile: string | undefined;
let livePollTimer: ReturnType<typeof setInterval> | undefined;
const LIVE_POLL_MS = 500;

function ensureLivePoll(): void {
  const running = listNodes().some((node) => node.status === "running");
  if (running && !livePollTimer && liveStateFile) {
    livePollTimer = setInterval(() => {
      try {
        applyWorkerEvents(liveStateFile!);
        enforceRunTimeouts();
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
    onRunSettled(run.id, leaderCtx);
    // failRunTimeout clears spawns, so those nodes' close events skip their
    // finalize path — release write-deferred nodes in OTHER runs here.
    if (leaderCtx) scheduleAllRuns(leaderCtx);
  }
}

/** Passive widget rows (display only — no selection, no key handling). */
function panelRows(theme: Theme, width?: number): string[] {
  const fg = (color: ThemeColor, s: string): string => theme.fg(color, s);
  const bold = (s: string): string => theme.bold(s);
  const fit = (line: string): string =>
    typeof width === "number" && width > 0 ? truncateToWidth(line, Math.max(10, width - 1)) : line;
  const running = listNodes().filter((node) => node.status === "running");
  // Stay out of the way until a teammate is actually working.
  if (running.length === 0) return [];
  if (isPanelCollapsed()) {
    return [` ${fit(fg("dim", `${running.length} teammate${running.length === 1 ? "" : "s"} working — /teammate`))}`];
  }
  const lines: string[] = [];
  for (const node of running) {
    const color = TEAM_COLORS[hashName(node.workerKey) % TEAM_COLORS.length];
    lines.push(` ${fit(`${bold(fg(color, node.id))} ${fg("muted", `(${node.agent})`)} ${fg("warning", runningTeammateLabel(node))}`)}`);
  }
  lines.push(` ${fit(fg("dim", "/teammate — open console"))}`);
  return lines;
}

/** Full content of a node as shown on its detail page: spawn lifecycle, live
 * worker text, captured output, result and error. */
function buildNodeSection(node: Node): string[] {
  const lines: string[] = [`- [${node.id}] ${node.status}: ${node.agent}`];
  if (node.prompt) lines.push(`  Task: ${cap(node.prompt, 2000)}`);
  lines.push(`  Access: ${node.access} | Paths: ${node.paths.join(", ")}`);
  if (node.dependsOn.length > 0) lines.push(`  Depends on: ${node.dependsOn.join(", ")}`);

  const spawn = node.spawn;
  if (spawn) {
    const stateLabel = spawn.status === "running" ? `running (pid ${spawn.pid})` : spawn.status;
    lines.push(`  Spawn: ${stateLabel} | Isolation: ${spawn.isolation ?? "none"}`);
    if (spawn.startedAt) lines.push(`  Started: ${new Date(spawn.startedAt).toLocaleString()}`);
    if (spawn.finishedAt) lines.push(`  Finished: ${new Date(spawn.finishedAt).toLocaleString()}`);
    if (spawn.exitCode !== undefined) lines.push(`  Exit code: ${spawn.exitCode}`);
    if (spawn.timedOut) lines.push("  Timed out: yes");
    if (spawn.usage) {
      const u = spawn.usage;
      lines.push(`  Usage: ${u.totalTokens} tokens (in ${u.input} / out ${u.output}) | cost $${u.cost}`);
    }
    if (spawn.turns) lines.push(`  Worker turns: ${spawn.turns}`);
    if (spawn.activeTool) lines.push(`  Current tool: ${spawn.activeTool}`);
    if (spawn.error) lines.push(`  Spawn error: ${spawn.error}`);
    if (spawn.status === "running") {
      lines.push("  --- Live worker activity ---");
      const activity = [
        ...(spawn.liveThinking?.trim() ? spawn.liveThinking.split("\n").map((l) => `  ${l}`) : []),
        ...(spawn.liveText?.trim() ? spawn.liveText.split("\n").map((l) => `  ${l}`) : []),
      ];
      lines.push(...(activity.length > 0 ? activity : ["  Waiting for the worker's first response…"]));
    }
    if (spawn.stdout) {
      lines.push("  --- Worker output ---");
      lines.push(...spawn.stdout.split("\n"));
    }
    if (spawn.stderr) {
      lines.push("  --- Worker stderr ---");
      lines.push(...spawn.stderr.split("\n"));
    }
  }

  if (node.result && node.result !== spawn?.stdout) lines.push(`  Result: ${node.result}`);
  if (node.errorMessage) lines.push(`  Error: ${node.errorMessage}`);
  return lines;
}

/** Publish the parent's current board to the shared state file so running
 * workers see leader-side changes. The in-memory board is authoritative. */
function publishToStateFile(): void {
  if (!liveStateFile) return;
  try {
    applyWorkerEvents(liveStateFile);
    writeStateFile(liveStateFile, getState());
  } catch {
    // Best effort.
  }
}

/** Node detail: node section + messages this node sent (plans, reports, peer
 * messages). Push-only: the node never reads an inbox; upstream context arrives
 * via the DAG handoff injected into its prompt. */
function buildNodeDetail(workerKey: string): string[] {
  const entry = getNodeByWorkerKey(workerKey);
  if (!entry) return ["(removed)"];
  const { run, node } = entry;
  const outgoing = listAllMessages().filter((m) => m.from === workerKey);

  const lines: string[] = [
    `${node.workerKey} (${node.agent}) [${node.status}] — run ${run.status}`,
    "",
    "== node ==",
    ...buildNodeSection(node),
    "",
    `== sent messages (${outgoing.length}) ==`,
    ...(outgoing.length === 0
      ? ["(none)"]
      : outgoing.flatMap((m) => {
          const time = new Date(m.timestamp).toLocaleString();
          return [
            `→ [${m.id}] ${m.subject} — to ${m.to} | ${time}`,
            m.taskId ? `  run ${m.taskId}` : "",
            m.body,
            "",
          ];
        })),
  ];
  return lines;
}

/** Full-screen Team Console — owns input via ctx.ui.custom, so ↑/↓ and Enter
 * are safe in here and nothing is intercepted globally. Modes: list / detail. */
function openTeamConsole(ctx: { ui: ExtensionUIContext }): Promise<void> {
  return ctx.ui.custom<void>((tui, theme, _keybindings, done) => {
    let mode: "list" | "detail" = "list";
    let selected = 0;
    let detailKey = "";
    let offset = 0;
    let closed = false;
    let renderTimer: ReturnType<typeof setInterval> | undefined;
    const requestRender = () => {
      if (!closed) tui.requestRender();
    };
    const startLiveRefresh = () => {
      if (renderTimer) return;
      renderTimer = setInterval(requestRender, SPINNER_MS);
      renderTimer.unref?.();
    };
    const stopLiveRefresh = () => {
      if (!renderTimer) return;
      clearInterval(renderTimer);
      renderTimer = undefined;
    };
    startLiveRefresh();

    // btw-style callbacks (same accent/muted/dim/border/success/error language as @fradser/pi-btw).
    const style = {
      accent: (s: string) => theme.fg("accent", s),
      muted: (s: string) => theme.fg("muted", s),
      dim: (s: string) => theme.fg("dim", s),
      border: (s: string) => theme.fg("border", s),
      success: (s: string) => theme.fg("success", s),
      error: (s: string) => theme.fg("error", s),
    };

    const windowLines = (full: string[], width: number): { lines: string[]; range: string } => {
      const wrapped = wrapConsoleDetail(full, width);
      const viewport = maxConsoleBody(tui.terminal.rows);
      offset = clampConsoleScroll(offset, wrapped.length, viewport);
      return {
        lines: wrapped.slice(offset, offset + viewport),
        range: consoleScrollRange(offset, wrapped.length, viewport),
      };
    };

    const renderList = (width: number): string[] => {
      const rows = buildPanelRows();
      if (selected >= rows.length) selected = Math.max(0, rows.length - 1);
      const border = style.border("─".repeat(Math.max(1, width)));
      const lines: string[] = [
        border,
        style.accent(truncateToWidth(`teammate  ${listNodes().filter((n) => n.status === "running").length} working / ${listNodes().length} teammate(s)`, width)),
        "",
      ];
      for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        const marker = i === selected ? style.accent("❯ ") : "  ";
        const entry = getNodeByWorkerKey(row.key);
        if (!entry) continue;
        const { node } = entry;
        const color = TEAM_COLORS[hashName(node.workerKey) % TEAM_COLORS.length];
        const name = theme.bold(theme.fg(color, node.id));
        const role = style.muted(`(${node.agent})`);
        const status = node.status === "running"
          ? theme.fg("warning", runningTeammateLabel(node))
          : node.status === "completed"
            ? style.success("✓ completed")
            : node.status === "failed"
              ? style.error("✗ failed")
              : style.dim(`○ ${node.status}`);
        lines.push(`${marker}${name} ${role} ${status}`);
      }
      lines.push("", style.dim("↑↓ select · enter open · esc/q close · x cancel"), border);
      return lines.map((l) => truncateToWidth(l, Math.max(10, width - 1)));
    };

    const renderDetail = (width: number): string[] => {
      const border = style.border("─".repeat(Math.max(1, width)));
      const detail = windowLines(buildNodeDetail(detailKey), width);
      const footer = style.dim(`  ${detail.range} · ↑↓ scroll · pgup/pgdn page · home/end jump · esc back · q close`);
      const lines = [
        border,
        style.accent(truncateToWidth(`agent-teams  ${detailKey}`, width)),
        "",
        ...detail.lines.map((line) => `  ${line}`),
        "",
        footer,
        border,
      ];
      return lines.map((line) => truncateToWidth(line, Math.max(10, width - 1)));
    };

    return {
      render: (width) =>
        mode === "list" ? renderList(width) : renderDetail(width),
      handleInput: (data: string) => {
        // Detail mode: Esc returns to the list, q closes.
        if (mode !== "list") {
          if (matchesKey(data, Key.escape)) {
            mode = "list";
            offset = 0;
            return;
          }
          if (data === "q" || data === "Q") {
            closed = true;
            stopLiveRefresh();
            done();
            return;
          }
          const detail = wrapConsoleDetail(buildNodeDetail(detailKey), tui.terminal.columns);
          const viewport = maxConsoleBody(tui.terminal.rows);
          // Mouse-wheel scrolling (SGR wheel events, same as @fradser/pi-btw).
          const sgrWheel = /^\x1b\[<(\d+);(\d+);(\d+)[Mm]$/.exec(data);
          if (sgrWheel) {
            const button = Number.parseInt(sgrWheel[1], 10);
            if ((button & 64) !== 0) {
              const direction = button & 3;
              if (direction === 0) offset = scrollConsoleDetail(offset, -3, detail.length, viewport);
              else if (direction === 1) offset = scrollConsoleDetail(offset, 3, detail.length, viewport);
            }
            return;
          }
          if (matchesKey(data, Key.up)) offset = scrollConsoleDetail(offset, -1, detail.length, viewport);
          else if (matchesKey(data, Key.down)) offset = scrollConsoleDetail(offset, 1, detail.length, viewport);
          else if (matchesKey(data, Key.pageUp)) offset = scrollConsoleDetail(offset, -Math.max(1, viewport - 1), detail.length, viewport);
          else if (matchesKey(data, Key.pageDown)) offset = scrollConsoleDetail(offset, Math.max(1, viewport - 1), detail.length, viewport);
          else if (matchesKey(data, Key.home)) offset = 0;
          else if (matchesKey(data, Key.end)) offset = clampConsoleScroll(Number.MAX_SAFE_INTEGER, detail.length, viewport);
          return;
        }

        // List mode — the console owns input, so ↑/↓/Enter are safe here.
        const rows = buildPanelRows();
        if (matchesKey(data, Key.down)) selected = Math.min(selected + 1, rows.length - 1);
        if (matchesKey(data, Key.up)) selected = Math.max(selected - 1, 0);
        if (matchesKey(data, Key.enter)) {
          const row = rows[Math.min(selected, rows.length - 1)];
          if (row?.key) {
            mode = "detail";
            detailKey = row.key;
            offset = 0;
          }
          return;
        }
        if (matchesKey(data, Key.escape) || data === "q" || data === "Q") {
          closed = true;
          stopLiveRefresh();
          done();
          return;
        }
        if (data === "x" || data === "X") {
          // Same node-cancel path as teammate_cancel nodeId: SIGTERM→SIGKILL,
          // dependents cancelled, the rest of the run continues.
          const row = rows[Math.min(selected, rows.length - 1)];
          const entry = row?.key ? getNodeByWorkerKey(row.key) : undefined;
          if (entry && (entry.node.status === "running" || entry.node.status === "pending")) {
            const runId = entry.run.id;
            const nodeId = entry.node.id;
            void cancelNodeAndTerminate(runId, nodeId, { ui: ctx.ui })
              .then((result) => {
                if (result.ok) ctx.ui.notify(`Cancelled node [${runId}/${nodeId}] — the rest of the run continues.`, "info");
                else ctx.ui.notify(result.error, "error");
              })
              .catch(() => false);
          }
          return;
        }
      },
      invalidate: () => {
        requestRender();
      },
      dispose: () => {
        closed = true;
        stopLiveRefresh();
      },
    };
  });
}

// ── Run dispatch machinery ────────────────────────────────────────

interface DispatchCtx {
  ui: ExtensionUIContext;
  sessionManager?: { getSessionFile(): string | undefined };
  cwd?: string;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function buildRunResultSummary(runId: string): string {
  const run = getRun(runId);
  if (!run) return `Run ${runId} not found.`;
  const counts = Object.values(run.nodes).reduce<Record<string, number>>((acc, node) => {
    acc[node.status] = (acc[node.status] ?? 0) + 1;
    return acc;
  }, {});
  const lines = [
    `## Run [${run.id}] ${run.status}`,
    `Nodes: ${Object.keys(run.nodes).length} (${Object.entries(counts).map(([status, n]) => `${status} ${n}`).join(", ")}) | Concurrency: ${run.concurrency} | Worktree: ${run.worktree ? "yes" : "no"}`,
    "",
  ];
  for (const node of Object.values(run.nodes)) {
    lines.push(`- [${node.id}] ${node.status}: ${node.agent}`);
    if (node.result) lines.push(`  Result: ${cap(node.result)}`);
    if (node.errorMessage) lines.push(`  Error: ${cap(node.errorMessage)}`);
    if (node.spawn?.usage) {
      const u = node.spawn.usage;
      lines.push(`  Usage: ${u.totalTokens} tokens | cost $${u.cost}`);
    }
    lines.push("");
  }

  // Full messages workers pushed to the team leader for this run — the
  // complete transcripts (plans, blockers, and full reports sent via
  // teammate_message) that the compact node results summarize.
  const leaderMessages = listAllMessages().filter(
    (m) => m.taskId === runId && m.to === "team-leader",
  );
  if (leaderMessages.length > 0) {
    lines.push(`== messages sent to the team leader (${leaderMessages.length}) ==`);
    for (const m of leaderMessages) {
      lines.push(`### [${m.from}] ${m.subject}`);
      lines.push(cap(m.body));
      lines.push("");
    }
  }
  return lines.join("\n");
}

/** Compact run summary for tool returns and follow-ups; detail lives in
 * teammate_status runId transcripts. When the run has a
 * synthesized __summary node result, that is shown instead of per-node
 * headlines (no truncation heuristics). */
function buildRunSummary(runId: string): string {
  const run = getRun(runId);
  if (!run) return `Run ${runId} not found.`;
  const counts = Object.values(run.nodes).reduce<Record<string, number>>((acc, node) => {
    acc[node.status] = (acc[node.status] ?? 0) + 1;
    return acc;
  }, {});
  const lines = [
    `## Run [${run.id}] ${run.status}`,
    `${Object.keys(run.nodes).length} node(s): ${Object.entries(counts).map(([status, n]) => `${status} ${n}`).join(", ")}`,
    "",
  ];
  if (run.summary) {
    lines.push(run.summary, "");
  }
  for (const node of Object.values(run.nodes)) {
    if (node.id === SUMMARY_NODE_ID) continue;
    lines.push(`- [${node.id}] ${node.status} (${node.agent})`);
  }
  lines.push("", `Detail: teammate_status runId=${run.id} · Console: /teammate`);
  return lines.join("\n");
}

/** Called once a run reaches a terminal status. Idempotent: the mailbox summary
 * and follow-up fire only on the first settled observation (a run can transition
 * through settleRun once per node close). */
function onRunSettled(runId: string, ctx?: DispatchCtx): void {
  const run = getRun(runId);
  if (!run) return;
  if (run.settledMessageSent) return;
  run.settledMessageSent = true;
  const summary = buildRunSummary(runId);
  sendMessage({ from: run.id, to: "team-leader", subject: `Run ${run.status}`, body: summary, taskId: runId });
  if (run.background && !run.completionNotified) {
    // One follow-up only when no other delivery path (wait/foreground gather)
    // has already consumed the run's completion.
    run.completionNotified = true;
    sendMainSessionUpdate(`Run ${run.status}`, summary, runId);
  }
  publishToStateFile();
  if (ctx) refreshTeamUI(ctx);
}

/**
 * Start ready nodes of a run up to its concurrency budget. Root nodes start
 * immediately; downstream nodes auto-start when their dependencies complete.
 */
function scheduleRun(runId: string, ctx: DispatchCtx): void {
  const run = getRun(runId);
  if (!run || run.status !== "running") return;
  const settled = settleRun(runId);
  if (settled !== "running") {
    onRunSettled(runId, ctx);
    return;
  }
  const budget = run.concurrency - runningNodeCount(runId);
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
function scheduleAllRuns(ctx: DispatchCtx): void {
  for (const run of listRuns()) {
    if (run.status === "running") scheduleRun(run.id, ctx);
  }
}

/**
 * Cancel one node (and its not-yet-started dependents) and terminate its live
 * workers with SIGTERM→SIGKILL. Shared by the teammate_cancel tool and the
 * /teammate console's `x` key so both paths leave identical state.
 */
async function cancelNodeAndTerminate(
  runId: string,
  nodeId: string,
  ctx: DispatchCtx,
): Promise<{ ok: true; stopped: number } | { ok: false; error: string }> {
  const cancelled = cancelNode(runId, nodeId);
  if (!cancelled.ok) return { ok: false, error: cancelled.error ?? "Failed to cancel node." };
  for (const id of cancelled.runningNodeIds) {
    const node = getNode(runId, id);
    if (!node?.spawn) continue;
    const spawnId = node.spawn.runId;
    if (cancellationIntents.begin(spawnId)) {
      const terminated = await terminateWorker(node.workerKey);
      cancellationIntents.resolve(spawnId, terminated);
    }
  }
  publishToStateFile();
  scheduleAllRuns(ctx);
  refreshTeamUI(ctx);
  return { ok: true, stopped: cancelled.runningNodeIds.length };
}

/** Spawn one node's worker process. Always asynchronous; the node settles via
 * finalizeNode when the child closes. */
function startNode(runId: string, nodeId: string, ctx: DispatchCtx): void {
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
    PI_TEAMMATE_RUN_ID: spawnId,
    PI_TEAMMATE_STATE_FILE: stateFile,
    PI_TEAMMATE_OUTBOX_FILE: outboxFile,
  };

  const timeoutMs = node.timeoutMs ?? DEFAULT_NODE_TIMEOUT_MS;
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
      workerKey: node.workerKey,
      stateFile,
      outboxFile,
      timeoutSec: Math.round(timeoutMs / 1000),
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
    if (getNode(runId, nodeId)?.spawn?.runId !== spawnId) {
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
      runId: spawnId,
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
          ? `Worker timed out after ${Math.round(timeoutMs / 1000)}s.`
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
      if (settledRun) settledRun.summary = nodeNow?.result ?? result.stdout;
    }
    if (ok || cancelled) {
      handoffNodeResult(runId, nodeId);
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
    sendMessage({ from: workerKey, to: "team-leader", subject: terminalSubject, body: terminalBody, taskId: runId });
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
    refreshTeamUI(ctx);
  };

  const finish = (result: WorkerProcessResult) => {
    if (cancellationIntents.defer(spawnId, (cancelled) => finalizeNode(result, cancelled))) return;
    finalizeNode(result);
  };

  const spawnFailure = (error: Error | string) => {
    if (getNode(runId, nodeId)?.spawn?.runId !== spawnId) return;
    setNodeSpawnInfo(runId, nodeId, {
      runId: spawnId,
      pid: 0,
      status: "failed",
      startedAt: node.spawn?.startedAt ?? Date.now(),
      finishedAt: Date.now(),
      isolation: run.worktree ? "worktree" : "none",
      error: typeof error === "string" ? error : error.message,
    });
    reportedWorkerShutdowns.delete(spawnId);
    sendMessage({
      from: workerKey,
      to: "team-leader",
      subject: "Node failed",
      body: `Node [${runId}/${nodeId}] could not start.\nError: ${typeof error === "string" ? error : error.message}`,
      taskId: runId,
    });
    cancelBlockedDependents(runId, nodeId);
    compactFinishedNodeRun(stateFile, workerKey, spawnId);
    if (worktree && !("error" in worktree)) discardWorktree(worktree);
    scheduleAllRuns(ctx);
    refreshTeamUI(ctx);
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
      writeStateFile(stateFile, getState());
      refreshTeamUI(ctx);
    },
    onExit: (result) => finish(result),
    onError: (error) => spawnFailure(error),
  });

  if ("error" in started) {
    spawnFailure(started.error);
    return;
  }

  setNodeSpawnInfo(runId, nodeId, {
    runId: spawnId,
    pid: started.pid,
    status: "running",
    startedAt: Date.now(),
    isolation: run.worktree ? "worktree" : "none",
  });
  publishToStateFile();
  refreshTeamUI(ctx);
}

const WORKER_GUIDANCE = `
## Spawned Teammate Protocol

You are a teammate, not the team leader. Work only on the task bound to
this process and its declared access/paths. Communication:

- Send: teammate_message to "team-leader" for plans, progress, blockers,
  and your final deliverable (with status="completed" or status="failed"); to
  same-run peers (node id) for handoffs and findings.
- Receive: messages pushed to you live in the shared state snapshot under
  mailboxes["<your worker key>"] — read that snapshot with the read tool when
  you need a leader reply or a peer handoff. Do not poll for them; DAG
  upstream results are already injected into your task prompt.
- Final deliverable: send teammate_message to "team-leader" with
  status="completed" (or "failed") and put your FULL deliverable/findings in
  the message body. The harness delivers this result to the main session after
  your process closes.

The mailbox is best-effort: process each message you read once. Do not use
leader coordination tools, claim new tasks, or overwrite files outside your
assigned scope.
`;

const TEAMMATE_GUIDANCE = `
## Agent Teams Orchestration

You are the team leader: the current Pi session owns decomposition,
delegation, synchronization, and the final user-facing answer. Workers are
isolated child processes; they do not see this conversation unless you put
the needed context in their task or send it through teammate_message.

### Agents are declarative files

Agents live in Markdown files with frontmatter (name, description, tools,
optional model); the body is the role prompt. Discovery precedence per name:
project .pi/agents > user ~/.pi/agent/agents > bundled package agents.
Call teammate_status to list available agents and route by description.
Prefer a bundled or existing agent; add a project agent under .pi/agents
only when its role materially differs. Never register runtime identities.

### Dispatch a run in one call

Use teammate_run with a tasks array: each task has id, agent, prompt, paths,
access (read default, write explicit), optional dependsOn, model, and
timeoutMs. The scheduler starts root nodes immediately, bounds concurrency,
defers overlapping shared-workspace writes — advisory scheduling across every
run in this session, not file-access isolation — unless worktree=true, and
auto-starts downstream nodes when their dependencies complete. access and
paths coordinate scheduling only; a worker's real capabilities come from its
agent definition's tools list. Teammates
always run in the background (default): the call returns the run id
immediately, the model turn stays free, and one run-completion follow-up is
delivered when the run settles. Pass background=false only to block and
gather inline (it detaches after 5 minutes so the turn is never hung); a
run-level timeoutMs fails the whole run past its cap. Multi-node runs append
a __summary node by default; pass summarize=false to skip it. For a review
pipeline: inspect -> fix -> verify with dependsOn edges.

### Coordinate and synthesize

Runs deliver one completion follow-up automatically when they settle — there is
no wait tool; collect results with teammate_status (run detail, leader-bound
message flow) or use background=false on teammate_run to gather inline. A run
cancelled with teammate_cancel fires no follow-up: the cancel result already
reported the outcome in that turn. teammate_cancel stops a run (or one
node with nodeId); teammate_retry re-runs only the failed/cancelled nodes
of a settled run. Workers message team-leader (including their final report
with status="completed") and same-run peers; completing a node hands its
result to pending dependents. Call teammate_status with the run id to read the
complete message bodies and deliverables. Only the harness-delivered run
completion (background) or wait/run results trigger model turns. After a run,
inspect the artifacts yourself: a worker's claim is not proof until its
deliverable and tests are checked. Treat failed, timed-out, cancelled, and
missing nodes explicitly; a failed node cancels its downstream dependents and
fails the run.
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
  leaderPi = pi;

  // ── Session lifecycle ───────────────────────────────────────────

  pi.on("session_start", async (_event, ctx) => {
    spinnerFrame = 0;
    resetState();
    ensureTeamWidget(ctx);
    leaderCtx = { ui: ctx.ui, sessionManager: ctx.sessionManager, cwd: ctx.cwd };
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
    await terminateAllWorkers();
    removeSessionStateDir(ctx.sessionManager.getSessionFile(), ctx.cwd || process.cwd());
    liveStateFile = undefined;
    leaderPi = undefined;
    leaderCtx = undefined;
    resetState();
  });

  // ── Inject team guidance into system prompt ─────────────────────

  pi.on("before_agent_start", async (event) => {
    return {
      systemPrompt: event.systemPrompt + TEAMMATE_GUIDANCE,
    };
  });

  // ── Leader tools ────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_run",
    promptSnippet: "Dispatch a dependency-aware task graph in one call",
    label: "Run Tasks",
    description: [
      "Dispatch a dependency-aware task graph in one call. Each task references an agent definition",
      "(bundled, user ~/.pi/agent/agents, or project .pi/agents). Root nodes start immediately;",
      "downstream nodes auto-start when their dependencies complete. Concurrency bounds simultaneous",
      "workers; overlapping shared-workspace writes are blocked unless worktree=true.",
      "Teammates run in the background by default: the call returns the run id immediately and",
      "delivers one run-completion follow-up; collect with teammate_status.",
    ].join(" "),
    parameters: TeammateRunParams,

    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const cwd = params.cwd ?? ctx.cwd ?? process.cwd();
      if (!liveStateFile && ctx.sessionManager) {
        liveStateFile = stateFilePath(ctx.sessionManager.getSessionFile(), cwd);
      }
      ensureTeamWidget(ctx);
      for (const task of params.tasks) {
        if (!resolveAgent(task.agent, cwd)) {
          throw new Error(
            `Agent "${task.agent}" not found in any scope (project .pi/agents, user ~/.pi/agent/agents, bundled). ` +
            "List agents with teammate_status to pick a valid name.",
          );
        }
      }

      const created = createRun({
        cwd,
        concurrency: params.concurrency ?? 4,
        worktree: params.worktree ?? false,
        background: params.background ?? true,
        timeoutMs: params.timeoutMs,
        summarize: params.summarize,
        summaryAgent: params.summaryAgent,
        nodes: params.tasks.map((task) => ({
          id: task.id,
          agent: task.agent,
          prompt: task.prompt,
          paths: task.paths,
          access: task.access ?? "read",
          model: task.model,
          timeoutMs: task.timeoutMs,
          dependsOn: task.dependsOn ?? [],
        })),
      });
      if (!created.ok) throw new Error(created.error ?? "Failed to create run.");
      const run = created.run;
      publishToStateFile();
      refreshTeamUI(ctx);

      scheduleRun(run.id, ctx);

      if (run.background) {
        const lines = [
          `Started run [${run.id}] "${Object.keys(run.nodes).length} node(s)" — background (returns immediately).`,
          `Concurrency: ${run.concurrency} | Worktree: ${run.worktree ? "yes" : "no"}`,
          "",
          "The main session is free to continue. Call teammate_status when you need this run's final outcome.",
        ];
        return { content: [{ type: "text", text: lines.join("\n") }], details: {} };
      }

      // Foreground gather: block until the run settles, the call is aborted,
      // or the foreground cap is exceeded (detach to background so the model
      // turn is never hung on a long run).
      const foregroundTimeoutMs = 5 * 60 * 1000;
      const foregroundDeadline = Date.now() + foregroundTimeoutMs;
      while (true) {
        if (liveStateFile) applyWorkerEvents(liveStateFile);
        const current = getRun(run.id);
        if (!current) break;
        if (current.status !== "running") break;
        if (signal?.aborted) {
          // Mirror detach: the run keeps executing in the background and
          // delivers one completion follow-up at settle.
          current.background = true;
          current.completionNotified = false;
          publishToStateFile();
          throw new Error(`Run [${run.id}] continues in the background — collect results with teammate_status.`);
        }
        if (Date.now() >= foregroundDeadline) {
          // Detach: the run keeps executing and delivers one completion follow-up.
          current.background = true;
          current.completionNotified = false;
          publishToStateFile();
          refreshTeamUI(ctx);
          return {
            content: [{ type: "text", text: `Run [${run.id}] is still running after ${Math.round(foregroundTimeoutMs / 1000)}s — detached to background. Collect results with teammate_status.` }],
            details: {},
          };
        }
        panelRequestRender?.();
        await sleep(150);
      }
      markRunCompletionDelivered(run.id);
      publishToStateFile();
      refreshTeamUI(ctx);
      return { content: [{ type: "text", text: buildRunSummary(run.id) }], details: {} };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_status",
    promptSnippet: "List agents, runs, and node detail",
    label: "Team Status",
    description: [
      "Query the team. Without a run id: returns discovered agents (name, description, scope, tools, model)",
      "plus a run overview (id, status, node counts). With a run id: returns that run's nodes with status,",
      "spawn lifecycle, and results.",
    ].join(" "),
    parameters: TeammateStatusParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      if (params.runId) {
        const run = getRun(params.runId);
        if (!run) throw new Error(`Run "${params.runId}" not found.`);
        return { content: [{ type: "text", text: buildRunResultSummary(params.runId) }], details: {} };
      }

      const agents = discoverAgents(ctx.cwd ?? process.cwd());
      const lines = ["## Agents"];
      if (agents.size === 0) {
        lines.push("(none found in bundled, user, or project scopes)");
      }
      for (const agent of agents.values()) {
        lines.push(`- **${agent.name}** (${agent.scope})`);
        if (agent.description) lines.push(`  ${agent.description}`);
        const model = agent.model ? ` | Model: ${agent.model}` : "";
        lines.push(`  Tools: ${agent.tools.join(", ") || "(role defaults)"}${model}`);
        lines.push("");
      }

      const runs = listRuns();
      lines.push(`## Runs (${runs.length})`);
      if (runs.length === 0) {
        lines.push("(none) — dispatch work with teammate_run");
      }
      for (const run of runs) {
        const counts = Object.values(run.nodes).reduce<Record<string, number>>((acc, node) => {
          acc[node.status] = (acc[node.status] ?? 0) + 1;
          return acc;
        }, {});
        const mode = run.background ? "background" : "foreground";
        const worktree = run.worktree ? " | worktree" : "";
        lines.push(`- [${run.id}] ${run.status}: ${Object.entries(counts).map(([status, n]) => `${status} ${n}`).join(", ") || "no nodes"} | ${mode}${worktree}`);
        lines.push(`  Created: ${new Date(run.createdAt).toLocaleString()}`);
        lines.push("");
      }
      return { content: [{ type: "text", text: lines.join("\n") }], details: {} };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_cancel",
    promptSnippet: "Cancel a run and stop its workers",
    label: "Cancel Run",
    description: [
      "Cancel a run: pending nodes are cancelled, running workers receive SIGTERM with a SIGKILL",
      "escalation after a bounded grace period, and the run is marked cancelled once its workers close.",
    ].join(" "),
    parameters: TeammateCancelParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      // Node-level cancel: stop one node (and its not-yet-started dependents)
      // while the rest of the run continues. The /teammate console's `x` key
      // reuses this exact path.
      if (params.nodeId) {
        const cancelled = await cancelNodeAndTerminate(params.runId, params.nodeId, ctx);
        if (!cancelled.ok) throw new Error(cancelled.error);
        return {
          content: [{ type: "text", text: `Node [${params.runId}/${params.nodeId}] cancelled — the rest of the run continues.` }],
          details: {},
        };
      }

      const run = getRun(params.runId);
      if (!run) throw new Error(`Run "${params.runId}" not found.`);
      if (run.status !== "running") {
        throw new Error(`Run "${params.runId}" is already ${run.status}.`);
      }
      const cancellation = cancelRun(params.runId);
      if (!cancellation.ok) throw new Error(cancellation.error ?? "Failed to cancel run.");

      // Mark the run cancelled immediately so settleRun from a concurrent node
      // close cannot reclassify it, and so no follow-up fires from finalize paths.
      const runAfterCancel = getRun(params.runId);
      if (runAfterCancel && runAfterCancel.status === "running") {
        runAfterCancel.status = "cancelled";
        runAfterCancel.finishedAt = Date.now();
        runAfterCancel.updatedAt = Date.now();
      }
      // The tool result already reports the cancellation in this turn; claim
      // the completion delivery so onRunSettled cannot fire an extra follow-up.
      if (runAfterCancel) runAfterCancel.completionNotified = true;

      for (const nodeId of cancellation.runningNodeIds) {
        const node = getNode(params.runId, nodeId);
        if (!node?.spawn) continue;
        const spawnId = node.spawn.runId;
        if (!cancellationIntents.begin(spawnId)) continue;
        const terminated = await terminateWorker(node.workerKey);
        if (!terminated) {
          cancellationIntents.resolve(spawnId, false);
          continue;
        }
        cancellationIntents.resolve(spawnId, true);
      }

      publishToStateFile();
      onRunSettled(params.runId, ctx);
      // Release write-deferred nodes in OTHER runs that waited on this run.
      scheduleAllRuns(ctx);
      refreshTeamUI(ctx);
      return {
        content: [{ type: "text", text: `Run [${params.runId}] cancelled — pending nodes were cancelled and running workers were stopped.` }],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_retry",
    promptSnippet: "Retry the failed or cancelled nodes of a settled run",
    label: "Retry Run Nodes",
    description: [
      "Retry the failed and cancelled nodes of a settled run without re-running the completed ones.",
      "Reset nodes return to pending and are re-dispatched by the scheduler; the run returns to running.",
      "Optionally pass nodeIds to retry only specific failed or cancelled nodes.",
    ].join(" "),
    parameters: TeammateRetryParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const retried = retryRun(params.runId, params.nodeIds);
      if (!retried.ok) throw new Error(retried.error ?? "Failed to retry run.");
      publishToStateFile();
      scheduleRun(params.runId, ctx);
      refreshTeamUI(ctx);
      return {
        content: [{
          type: "text",
          text: `Run [${params.runId}] retried — reset ${retried.reset.length} node(s): ${retried.reset.join(", ")}. Completed nodes are retained.`,
        }],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_message",
    promptSnippet: "Send a direct message to a node or broadcast to a run",
    label: "Teammate Message",
    description: [
      "Send a direct message to a node (node id or runId:nodeId), or broadcast to every node of a run",
      "(to=\"all\" with runId). Workers use the same tool to message team-leader or a same-run peer.",
    ].join(" "),
    parameters: TeammateMessageParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      if (params.to === "all") {
        const run = params.runId ? getRun(params.runId) : undefined;
        if (!run) throw new Error('to="all" requires a valid runId of a run to broadcast to.');
        const recipients = Object.values(run.nodes).filter((node) => node.status === "running" || node.status === "pending");
        for (const node of recipients) {
          sendMessage({
            from: "team-leader",
            to: node.workerKey,
            subject: `Broadcast: ${params.subject}`,
            body: params.body,
            taskId: run.id,
          });
        }
        publishToStateFile();
        refreshTeamUI(ctx);
        return {
          content: [{ type: "text", text: `Message sent to ${recipients.length} node(s) of run [${run.id}].\nSubject: ${params.subject}` }],
          details: {},
        };
      }
      const recipient = resolveLeaderRecipient(params.to, params.runId);
      if (!recipient.ok) throw new Error(recipient.error);
      sendMessage({
        from: "team-leader",
        to: recipient.to,
        subject: params.subject,
        body: params.body,
        taskId: recipient.runId,
      });
      publishToStateFile();
      refreshTeamUI(ctx);
      return {
        content: [{ type: "text", text: `Message sent to "${params.to}".\nSubject: ${params.subject}` }],
        details: {},
      };
    },
  });

  // ── Team console (full-screen, owns input) ───────────────────────

  pi.registerCommand("teammate", {
    description: "Open the full-screen teammate team console: run/node status, node details, interrupt/stop",
    handler: async (_args, ctx) => {
      if (ctx.mode !== "tui") {
        ctx.ui.notify(getSummary() ?? "No runs yet — dispatch work with teammate_run.", "info");
        return;
      }
      await openTeamConsole(ctx);
      refreshTeamUI(ctx);
    },
  });
}
