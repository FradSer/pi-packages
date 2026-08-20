/** Passive teammate widget and interactive full-screen console. */

import { truncateToWidth, Key, matchesKey } from "@earendil-works/pi-tui";
import { createPiThemeStyle, PI_SPINNER_FRAMES, PI_SPINNER_INTERVAL_MS } from "@fradser/pi-kit";
import type { ExtensionUIContext } from "@earendil-works/pi-coding-agent";
import { truncateTail, DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES } from "@earendil-works/pi-coding-agent";
import {
  clampConsoleScroll, consoleScrollRange, maxConsoleBody, scrollConsoleDetail, wrapConsoleDetail,
} from "./console-viewport";
import { getNodeByWorkerKey, getState, listNodes } from "./state";
import { cancelNodeAndTerminate, ensureLivePoll } from "./run-machine";
import { fitTeammateRow, formatTeammateLabel, runningTeammateActivity } from "./activity";
import type { Node } from "./types";

export { runningTeammateActivity } from "./activity";

function cap(text: string | undefined, maxBytes = DEFAULT_MAX_BYTES): string {
  if (!text) return "";
  if (text.length <= maxBytes) return text;
  const t = truncateTail(text, { maxLines: DEFAULT_MAX_LINES, maxBytes });
  return `${t.content}\n…[truncated ${text.length - t.content.length} chars]`;
}

// ── Team UI: passive widget + full-screen console ──────────────────
// The widget below the editor is DISPLAY-ONLY. ALL interaction happens in the
// full-screen Team Console (/teammate), which owns input via ctx.ui.custom.

const TEAM_COLORS = ["success", "warning", "error", "mdLink"] as const;
let spinnerTimer: ReturnType<typeof setInterval> | undefined;
let spinnerFrame = 0;

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

export function runningTeammateLabel(node: Node, maxActivityWidth?: number): string {
  return formatTeammateLabel(PI_SPINNER_FRAMES[spinnerFrame], runningTeammateActivity(node), maxActivityWidth);
}

function ensureSpinner(): void {
  const running = listNodes().some((node) => node.status === "running");
  if (running && !spinnerTimer) {
    spinnerTimer = setInterval(() => {
      spinnerFrame = (spinnerFrame + 1) % PI_SPINNER_FRAMES.length;
    }, PI_SPINNER_INTERVAL_MS);
    spinnerTimer.unref?.();
  } else if (!running && spinnerTimer) {
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

  const running = listNodes().filter((node) => node.status === "running");
  if (running.length === 0) {
    ctx.ui.setWidget("teammate", undefined);
    return;
  }

  ctx.ui.setWidget("teammate", (tui, theme) => {
    const timer = setInterval(() => tui.requestRender(), PI_SPINNER_INTERVAL_MS);
    timer.unref?.();
    const style = createPiThemeStyle(theme);
    const assignedColors = new Map<string, (typeof TEAM_COLORS)[number]>();
    return {
      placement: "belowEditor",
      render: (width: number) => {
        const running = listNodes().filter((n) => n.status === "running");
        if (running.length === 0) return [];
        const runningKeys = new Set(running.map((node) => node.workerKey));
        for (const key of assignedColors.keys()) {
          if (!runningKeys.has(key)) assignedColors.delete(key);
        }
        const usedColors = new Set(assignedColors.values());
        for (const node of running) {
          if (!assignedColors.has(node.workerKey)) {
            const start = hashName(node.workerKey) % TEAM_COLORS.length;
            const color = TEAM_COLORS.find((_, offset) => !usedColors.has(TEAM_COLORS[(start + offset) % TEAM_COLORS.length]));
            assignedColors.set(node.workerKey, color ?? TEAM_COLORS[start]);
            usedColors.add(color ?? TEAM_COLORS[start]);
          }
        }
        const lines: string[] = [];
        for (const node of running) {
          const spinner = PI_SPINNER_FRAMES[spinnerFrame];
          const color = assignedColors.get(node.workerKey) ?? TEAM_COLORS[hashName(node.workerKey) % TEAM_COLORS.length];
          const line = fitTeammateRow(
            spinner,
            style.fg(color, node.agent),
            runningTeammateActivity(node),
            width,
            (activity) => theme.bold(style.fg("accent", activity)),
          );
          lines.push(line);
        }
        return lines;
      },
      invalidate: () => {},
      dispose: () => clearInterval(timer),
    };
  });
}

export function refreshTeamUI(ctx?: { ui?: ExtensionUIContext; mode?: string }): void {
  ensureTeamWidget(ctx);
  ensureLivePoll();
  ensureSpinner();
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
      renderTimer = setInterval(requestRender, PI_SPINNER_INTERVAL_MS);
      renderTimer.unref?.();
    };
    const stopLiveRefresh = () => {
      if (!renderTimer) return;
      clearInterval(renderTimer);
      renderTimer = undefined;
    };
    startLiveRefresh();

    // btw-style callbacks (same accent/muted/dim/border/success/error language as pi-btw-fradser).
    const style = createPiThemeStyle(theme);

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
      const maxLineWidth = Math.max(10, width - 1);
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
        const color = TEAM_COLORS[hashName(node.agent) % TEAM_COLORS.length];
        const name = theme.bold(theme.fg(color, node.agent));
        let status: string;
        if (node.status === "running") {
          const prefix = `${marker}${name} `;
          const spinner = PI_SPINNER_FRAMES[spinnerFrame];
          const availableActivityWidth = Math.max(0, maxLineWidth - prefix.length - spinner.length - 1);
          status = theme.fg("warning", runningTeammateLabel(node, availableActivityWidth));
        } else if (node.status === "completed") {
          status = style.success("✓ completed");
        } else if (node.status === "failed") {
          status = style.error("✗ failed");
        } else {
          status = style.dim(`○ ${node.status}`);
        }
        lines.push(`${marker}${name} ${status}`);
      }
      lines.push("", style.dim("↑↓ select · enter open · esc/q close · x cancel"), border);
      return lines.map((l) => truncateToWidth(l, maxLineWidth));
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
          // Mouse-wheel scrolling (SGR wheel events, same as pi-btw-fradser).
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

