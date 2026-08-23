/** Passive team widget and interactive full-screen console (roster + board). */

import { truncateToWidth, Key, matchesKey } from "@earendil-works/pi-tui";
import { createPiThemeStyle, PI_SPINNER_FRAMES, PI_SPINNER_INTERVAL_MS } from "@fradser/pi-kit";
import type { ExtensionUIContext } from "@earendil-works/pi-coding-agent";
import {
  clampConsoleScroll, consoleScrollRange, maxConsoleBody, scrollConsoleDetail, wrapConsoleDetail,
} from "./console-viewport.ts";
import { fitTeammateRow, formatTeammateLabel, runningTeammateActivity } from "./activity.ts";
import { getState, getTeammate, listTasks, listTeammates, livingTeammates } from "./state.ts";
import {
  ensureLivePoll,
  formatSilenceDuration,
  runtimeDirPath,
  shutdownTeammate,
  STALL_NOTICE_MS,
  stallSilenceMs,
} from "./team-machine.ts";
import type { Teammate } from "./types.ts";
import { inboxPath } from "./statefile.ts";
import * as fs from "node:fs";
import * as path from "node:path";

const TEAM_COLORS = ["success", "warning", "error", "mdLink"] as const;
let spinnerTimer: ReturnType<typeof setInterval> | undefined;
let spinnerFrame = 0;

function hashName(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(0) + i * 7) | 0;
  return Math.abs(h);
}

function colorFor(name: string): (typeof TEAM_COLORS)[number] {
  return TEAM_COLORS[hashName(name) % TEAM_COLORS.length];
}

function ensureSpinner(): void {
  const working = livingTeammates().some((t) => t.status === "working" || t.status === "starting");
  if (working && !spinnerTimer) {
    spinnerTimer = setInterval(() => {
      spinnerFrame = (spinnerFrame + 1) % PI_SPINNER_FRAMES.length;
    }, PI_SPINNER_INTERVAL_MS);
    spinnerTimer.unref?.();
  } else if (!working && spinnerTimer) {
    clearInterval(spinnerTimer);
    spinnerTimer = undefined;
  }
}

export function stopUiTimers(): void {
  if (spinnerTimer) {
    clearInterval(spinnerTimer);
    spinnerTimer = undefined;
  }
}

export function ensureTeamWidget(ctx?: { ui?: ExtensionUIContext; mode?: string }): void {
  if (!ctx?.ui?.setWidget) return;
  if (ctx.mode && ctx.mode !== "tui") return;

  if (livingTeammates().filter(isWorking).length === 0) {
    ctx.ui.setWidget("teammate", undefined);
    return;
  }

  ctx.ui.setWidget("teammate", (tui, theme) => {
    const timer = setInterval(() => tui.requestRender(), PI_SPINNER_INTERVAL_MS);
    timer.unref?.();
    const style = createPiThemeStyle(theme);
    return {
      placement: "belowEditor",
      render: (width: number) => {
        // Only WORKING teammates appear above the input box; idle and
        // stopped teammates stay in the /teammate console instead.
        const working = livingTeammates().filter(isWorking);
        if (working.length === 0) return [];
        const lines: string[] = [];
        for (const teammate of working) {
          lines.push(fitTeammateRow(
            PI_SPINNER_FRAMES[spinnerFrame],
            style.fg(colorFor(teammate.name), teammate.name),
            runningTeammateActivity(teammate) + stallSuffix(teammate),
            width,
            (activity) => theme.bold(style.fg("accent", activity)),
          ));
        }
        return lines;
      },
      invalidate: () => {},
      dispose: () => clearInterval(timer),
    };
  });
}

function isWorking(teammate: { status: string }): boolean {
  return teammate.status === "working" || teammate.status === "starting";
}

/** Silence marker appended once a working teammate passes the stall notice threshold. */
function stallSuffix(teammate: Teammate): string {
  if (!isWorking(teammate)) return "";
  const silence = stallSilenceMs(teammate);
  return silence !== undefined && STALL_NOTICE_MS > 0 && silence >= STALL_NOTICE_MS
    ? ` · stalled for ${formatSilenceDuration(silence)}`
    : "";
}

export function refreshTeamUI(ctx?: { ui?: ExtensionUIContext; mode?: string }): void {
  ensureTeamWidget(ctx);
  ensureLivePoll();
  ensureSpinner();
}

function cap(text: string | undefined, maxBytes = 2000): string {
  if (!text) return "";
  return text.length <= maxBytes ? text : `${text.slice(0, maxBytes)}\n…[truncated ${text.length - maxBytes} chars]`;
}

// ── Detail builders ───────────────────────────────────────────────

interface PeerMailLine {
  direction: "sent" | "received";
  counterpart: string;
  subject: string;
  body: string;
  timestamp: number;
}

function readPeerMail(teammateName: string): PeerMailLine[] {
  const runtimeDir = runtimeDirPath();
  if (!runtimeDir) return [];
  const mailDirPath = path.dirname(inboxPath(path.join(runtimeDir, "state.json"), teammateName));
  let entries: string[] = [];
  try {
    entries = fs.readdirSync(mailDirPath).filter((name) => name.startsWith("inbox-") && name.endsWith(".jsonl"));
  } catch {
    return [];
  }
  const lines: PeerMailLine[] = [];
  for (const entry of entries) {
    const recipient = decodeURIComponent(entry.slice("inbox-".length, -".jsonl".length));
    let raw = "";
    try {
      raw = fs.readFileSync(path.join(mailDirPath, entry), "utf-8");
    } catch {
      continue;
    }
    for (const line of raw.split("\n")) {
      if (!line.trim()) continue;
      try {
        const message = JSON.parse(line) as { id?: string; from?: string; subject?: string; body?: string; timestamp?: number };
        if (!message.id || !message.from || !message.subject) continue;
        if (message.from !== teammateName && recipient !== teammateName) continue;
        lines.push({
          direction: message.from === teammateName ? "sent" : "received",
          counterpart: message.from === teammateName ? recipient : message.from,
          subject: message.subject,
          body: message.body ?? "",
          timestamp: message.timestamp ?? 0,
        });
      } catch {
        continue;
      }
    }
  }
  return lines.sort((a, b) => a.timestamp - b.timestamp);
}

function indent(text: string): string[] {
  return text.split("\n").map((line) => `  ${line}`);
}

function buildTeammateDetail(name: string): string[] {
  const teammate = getTeammate(name);
  if (!teammate) return ["(teammate removed from the roster)"];
  const reports = getState().leaderMailbox.filter((message) => message.from === name);
  const lines: string[] = [
    `@${teammate.name} (${teammate.agent}) [${teammate.status}]`,
    "",
    "== teammate ==",
    `  Status: ${teammate.status}${teammate.currentTaskId ? ` | Task: ${teammate.currentTaskId}` : ""}`,
    `  Spawn: ${teammate.pid > 0 ? `pid ${teammate.pid}` : "pid unknown"} | Isolation: ${teammate.isolation}`,
    `  Created: ${new Date(teammate.createdAt).toLocaleString()}`,
  ];
  if (teammate.stoppedAt) lines.push(`  Stopped: ${new Date(teammate.stoppedAt).toLocaleString()}`);
  if (isWorking(teammate) && teammate.lastOutputAt !== undefined) {
    const silence = stallSilenceMs(teammate);
    if (silence !== undefined) {
      lines.push(`  Last output: ${new Date(teammate.lastOutputAt).toLocaleString()} (${formatSilenceDuration(silence)} ago${stallSuffix(teammate) ? " — stalled" : ""})`);
    }
  }
  if (teammate.usage) lines.push(`  Usage: ${teammate.usage.totalTokens} tokens | $${teammate.usage.cost.toFixed(4)}`);
  if (teammate.error) lines.push(`  Error: ${teammate.error}`);

  lines.push("", `== reports to leader (${reports.length}) ==`);
  if (reports.length === 0) lines.push("  (none)");
  for (const report of reports) {
    lines.push(`  -> [${report.subject}] ${new Date(report.timestamp).toLocaleString()}`, ...indent(cap(report.body)), "");
  }

  const peer = readPeerMail(name);
  lines.push(`== peer mail (${peer.length}) ==`);
  if (peer.length === 0) lines.push("  (none)");
  for (const mail of peer) {
    const arrow = mail.direction === "sent" ? `to @${mail.counterpart}` : `from @${mail.counterpart}`;
    lines.push(`  ${arrow} [${mail.subject}] ${new Date(mail.timestamp).toLocaleString()}`, ...indent(cap(mail.body)), "");
  }
  return lines;
}

function buildTaskDetail(taskId: string): string[] {
  const tasks = listTasks();
  const task = tasks.find((candidate) => candidate.id === taskId);
  if (!task) return ["(task not on the board)"];
  const byId = new Map(tasks.map((candidate) => [candidate.id, candidate]));
  return [
    `[${task.id}] ${task.subject}`,
    "",
    "== task ==",
    `  Status: ${task.status}${task.claimedBy ? ` (@${task.claimedBy})` : ""}`,
    ...(task.description ? [`  Description:`, ...indent(cap(task.description))] : []),
    ...(task.dependsOn.length > 0
      ? [`  Depends on: ${task.dependsOn.join(", ")} (${task.dependsOn.every((dep) => byId.get(dep)?.status === "completed") ? "met" : "unmet"})`]
      : []),
    `  Verify: ${task.verify ?? "(none)"}`,
    ...(task.result ? ["  Result:", ...indent(cap(task.result))] : []),
    ...(task.errorMessage ? ["  Error:", ...indent(cap(task.errorMessage))] : []),
    `  Created: ${new Date(task.createdAt).toLocaleString()}`,
    ...(task.completedAt ? [`  Completed: ${new Date(task.completedAt).toLocaleString()}`] : []),
  ];
}

// ── Full-screen console ───────────────────────────────────────────

type ConsolePage = "roster" | "board";

interface RosterRow {
  key: string;
  kind: "teammate";
}
interface BoardRow {
  key: string;
  kind: "task";
}
type ConsoleRow = RosterRow | BoardRow;

/** Full-screen Team Console — owns input via ctx.ui.custom. Pages: roster /
 * board; each row opens a scrolling detail view. */
export function openTeamConsole(ctx: { ui: ExtensionUIContext }): Promise<void> {
  return ctx.ui.custom<void>((tui, theme, _keybindings, done) => {
    let page: ConsolePage = "roster";
    let mode: "list" | "detail" = "list";
    let selectedRoster = 0;
    let selectedBoard = 0;
    let detailTitle = "";
    let offset = 0;
    let closed = false;
    let renderTimer: ReturnType<typeof setInterval> | undefined;
    const requestRender = () => {
      if (!closed) tui.requestRender();
    };
    const startLiveRefresh = () => {
      if (renderTimer) return;
      renderTimer = setInterval(requestRender, PI_SPINNER_INTERVAL_MS);
      renderTimer.unref?.();
    };
    const stopLiveRefresh = () => {
      if (!renderTimer) return;
      clearInterval(renderTimer);
      renderTimer = undefined;
    };
    startLiveRefresh();

    const style = createPiThemeStyle(theme);

    const currentRows = (): ConsoleRow[] =>
      page === "roster"
        // The console is the full roster: idle and stopped stay visible here.
        ? listTeammates().map((t) => ({ key: t.name, kind: "teammate" as const }))
        : listTasks().map((task) => ({ key: task.id, kind: "task" as const }));

    const windowLines = (full: string[], width: number): { lines: string[]; range: string } => {
      const wrapped = wrapConsoleDetail(full, width);
      const viewport = maxConsoleBody(tui.terminal.rows);
      offset = clampConsoleScroll(offset, wrapped.length, viewport);
      return {
        lines: wrapped.slice(offset, offset + viewport),
        range: consoleScrollRange(offset, wrapped.length, viewport),
      };
    };

    const headerLine = (): string => {
      const alive = livingTeammates();
      const tasks = listTasks();
      return `team  ${alive.length} alive · board ${tasks.filter((task) => task.status === "pending").length}p/${tasks.filter((task) => task.status === "claimed").length}c/${tasks.filter((task) => task.status === "completed").length}d · ${page}`;
    };

    const renderList = (width: number): string[] => {
      const rows = currentRows();
      const border = style.border("─".repeat(Math.max(1, width)));
      const lines = [border, style.accent(truncateToWidth(headerLine(), width)), ""];
      if (rows.length === 0) {
        lines.push(style.dim(page === "roster"
          ? "No living teammates. Spawn one with teammate_spawn."
          : "The task board is empty. Create tasks with task_create."));
      }
      rows.forEach((row, index) => {
        const marker = index === currentPageSelection(rows.length) ? style.accent("❯ ") : "  ";
        if (row.kind === "teammate") {
          const teammate = getTeammate(row.key)!;
          const name = theme.bold(theme.fg(colorFor(teammate.name), `@${teammate.name}`));
          let status: string;
          if (teammate.status === "working" || teammate.status === "starting") {
            const prefix = `${marker}${name} `;
            const available = Math.max(0, width - prefix.length - PI_SPINNER_FRAMES[spinnerFrame].length - 2);
            status = theme.fg("warning", formatTeammateLabel(PI_SPINNER_FRAMES[spinnerFrame], runningTeammateActivity(teammate) + stallSuffix(teammate), available));
          } else if (teammate.status === "idle") {
            status = style.dim(`○ idle${teammate.currentTaskId ? ` · ${teammate.currentTaskId}` : ""}`);
          } else {
            status = theme.fg("warning", "■ stopped");
          }
          lines.push(`${marker}${name} ${status}`);
        } else {
          const task = listTasks().find((candidate) => candidate.id === row.key)!;
          const label = theme.fg(colorFor(task.id), `[${task.id}]`);
          const holder = task.claimedBy ? style.dim(` @${task.claimedBy}`) : "";
          const statusText = task.status === "completed"
            ? style.success("✓")
            : task.status === "claimed"
              ? theme.fg("warning", "◐ claimed")
              : style.dim("○ pending");
          lines.push(truncateToWidth(`${marker}${label} ${statusText} ${theme.fg("customMessageText", task.subject)}${holder}`, Math.max(10, width - 1)));
        }
      });
      lines.push("", style.dim("↑↓ select · enter open · tab page · x shutdown · esc/q close"), border);
      return lines.map((l) => truncateToWidth(l, Math.max(10, width - 1)));
    };

    const currentPageSelection = (rowCount: number): number => {
      const selection = page === "roster" ? selectedRoster : selectedBoard;
      return rowCount === 0 ? 0 : Math.min(selection, rowCount - 1);
    };

    const renderDetail = (width: number): string[] => {
      const border = style.border("─".repeat(Math.max(1, width)));
      const source = detailSource();
      const detail = windowLines(source, width);
      const footer = style.dim(`  ${detail.range} · ↑↓ scroll · pgup/pgdn page · home/end jump · esc back · q close`);
      const lines = [
        border,
        style.accent(truncateToWidth(`agent-teams  ${detailTitle}`, width)),
        "",
        ...detail.lines.map((line) => `  ${line}`),
        "",
        footer,
        border,
      ];
      return lines.map((line) => truncateToWidth(line, Math.max(10, width - 1)));
    };

    const detailSource = (): string[] =>
      detailTitle.startsWith("[")
        ? buildTaskDetail(detailTitle.slice(1, detailTitle.indexOf("]")))
        : buildTeammateDetail(detailTitle.replace(/^@/, ""));

    return {
      render: (width) => (mode === "list" ? renderList(width) : renderDetail(width)),
      handleInput: (data: string) => {
        if (mode !== "list") {
          handleDetailInput(data);
          return;
        }
        const rows = currentRows();
        if (matchesKey(data, Key.tab)) {
          page = page === "roster" ? "board" : "roster";
          return;
        }
        if (matchesKey(data, Key.down)) bumpSelection(1, rows.length);
        if (matchesKey(data, Key.up)) bumpSelection(-1, rows.length);
        if (matchesKey(data, Key.enter)) {
          const selection = currentPageSelection(rows.length);
          const row = rows[selection];
          if (row) {
            mode = "detail";
            offset = 0;
            detailTitle = row.kind === "teammate" ? `@${row.key}` : `[${row.key}]`;
          }
          return;
        }
        if (data === "x" || data === "X") {
          const selection = currentPageSelection(rows.length);
          const row = rows[selection];
          if (page === "roster" && row?.kind === "teammate") void shutdownFromConsole(ctx, row.key);
          return;
        }
        if (matchesKey(data, Key.escape) || data === "q" || data === "Q") {
          closeConsole(done);
          return;
        }
      },
      invalidate: () => requestRender(),
      dispose: () => {
        closed = true;
        stopLiveRefresh();
      },
    };

    function closeConsole(doneFn: () => void): void {
      closed = true;
      stopLiveRefresh();
      doneFn();
    }

    function bumpSelection(delta: number, rowCount: number): void {
      if (rowCount === 0) return;
      if (page === "roster") selectedRoster = clampIndex(selectedRoster + delta, rowCount);
      else selectedBoard = clampIndex(selectedBoard + delta, rowCount);
    }

    function handleDetailInput(data: string): void {
      const source = detailSource();
      const viewport = maxConsoleBody(tui.terminal.rows);
      if (matchesKey(data, Key.escape)) {
        mode = "list";
        offset = 0;
        return;
      }
      if (data === "q" || data === "Q") {
        closeConsole(done);
        return;
      }
      const total = wrapConsoleDetail(source, tui.terminal.columns).length;
      const sgrWheel = /^\x1b\[<(\d+);(\d+);(\d+)[Mm]$/.exec(data);
      if (sgrWheel) {
        const button = Number.parseInt(sgrWheel[1], 10);
        if ((button & 64) !== 0) {
          const direction = button & 3;
          if (direction === 0) offset = scrollConsoleDetail(offset, -3, total, viewport);
          else if (direction === 1) offset = scrollConsoleDetail(offset, 3, total, viewport);
        }
        return;
      }
      if (matchesKey(data, Key.up)) offset = scrollConsoleDetail(offset, -1, total, viewport);
      else if (matchesKey(data, Key.down)) offset = scrollConsoleDetail(offset, 1, total, viewport);
      else if (matchesKey(data, Key.pageUp)) offset = scrollConsoleDetail(offset, -Math.max(1, viewport - 1), total, viewport);
      else if (matchesKey(data, Key.pageDown)) offset = scrollConsoleDetail(offset, Math.max(1, viewport - 1), total, viewport);
      else if (matchesKey(data, Key.home)) offset = 0;
      else if (matchesKey(data, Key.end)) offset = clampConsoleScroll(Number.MAX_SAFE_INTEGER, total, viewport);
    }
  });
}

async function shutdownFromConsole(ctx: { ui: ExtensionUIContext }, name: string): Promise<void> {
  const result = await shutdownTeammate(name);
  if (result.ok) ctx.ui.notify(result.body, "info");
  else ctx.ui.notify(result.error, "error");
}

function clampIndex(index: number, rowCount: number): number {
  return Math.max(0, Math.min(rowCount - 1, index));
}
