/** Passive teammate widget and interactive full-screen console. */

import { truncateToWidth, Key, matchesKey } from "@earendil-works/pi-tui";
import type { ExtensionUIContext, Theme, ThemeColor } from "@earendil-works/pi-coding-agent";
import { truncateTail, DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES } from "@earendil-works/pi-coding-agent";
import {
  clampConsoleScroll, consoleScrollRange, maxConsoleBody, scrollConsoleDetail, wrapConsoleDetail,
} from "./console-viewport";
import { getNodeByWorkerKey, getState, listNodes } from "./state";
import { cancelNodeAndTerminate, ensureLivePoll } from "./run-machine";
import type { Node } from "./types";

function cap(text: string | undefined, maxBytes = DEFAULT_MAX_BYTES): string {
  if (!text) return "";
  if (text.length <= maxBytes) return text;
  const t = truncateTail(text, { maxLines: DEFAULT_MAX_LINES, maxBytes });
  return `${t.content}\n…[truncated ${text.length - t.content.length} chars]`;
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

/** Console/widget rows contain node status and leader-report access. */
function buildPanelRows(): PanelRow[] {
  return listNodes().map((node) => ({ key: node.workerKey }));
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

export function stopUiTimers(): void {
  if (spinnerTimer) {
    clearInterval(spinnerTimer);
    spinnerTimer = undefined;
  }
  if (panelCollapseTimer) {
    clearTimeout(panelCollapseTimer);
    panelCollapseTimer = undefined;
  }
}

export function ensureTeamWidget(ctx?: { ui?: ExtensionUIContext; mode?: string }): void {
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

export function refreshTeamUI(ctx?: { ui?: ExtensionUIContext; mode?: string }): void {
  ensureTeamWidget(ctx);
  panelLastActivity = Date.now();
  scheduleIdleCollapse();
  ensureLivePoll();
  ensureSpinner();
  panelRequestRender?.();
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

/** Node detail: node section + reports this node sent to team-leader. */
function buildNodeDetail(workerKey: string): string[] {
  const entry = getNodeByWorkerKey(workerKey);
  if (!entry) return ["(removed)"];
  const { run, node } = entry;
  const outgoing = getState().leaderMailbox.filter((message) => message.from === workerKey);

  const lines: string[] = [
    `${node.workerKey} (${node.agent}) [${node.status}] — run ${run.status}`,
    "",
    "== node ==",
    ...buildNodeSection(node),
    "",
    `== reports to team-leader (${outgoing.length}) ==`,
    ...(outgoing.length === 0
      ? ["(none)"]
      : outgoing.flatMap((m) => {
          const time = new Date(m.timestamp).toLocaleString();
          return [
            `→ [${m.id}] ${m.subject} | ${time}`,
            m.runId ? `  run ${m.runId}` : "",
            m.body,
            "",
          ];
        })),
  ];
  return lines;
}

/** Full-screen Team Console — owns input via ctx.ui.custom, so ↑/↓ and Enter
 * are safe in here and nothing is intercepted globally. Modes: list / detail. */
export function openTeamConsole(ctx: { ui: ExtensionUIContext }): Promise<void> {
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

