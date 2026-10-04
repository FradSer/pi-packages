/**
 * The goal dashboard: a passive status row below the editor, and an expanded
 * panel with the objective, its contract, and why it stopped.
 *
 * All geometry and row language come from pi-kit — `renderPiWidgetRow` for the
 * single-line status, `renderPiPanel` for the frame, `computeScrollWindow` for
 * the scroll slice, and `createPiThemeStyle` for the colors. This module owns
 * only what the goal actually has to say, so the row and the panel cannot drift
 * apart from every other package that uses them.
 */

import { Key, matchesKey, truncateToWidth, visibleWidth, type Component } from "@earendil-works/pi-tui";
import {
  computeScrollWindow,
  createLiveActivityWidget,
  maxBodyHeight,
  renderPiPanel,
  type PiThemeStyle,
} from "@fradser/pi-kit";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import type { GoalCore } from "./core.ts";
import { statusLabel } from "./prompt.ts";
import { formatElapsed, type GoalRecord } from "./record.ts";

/** One passive row below the editor. It is never interactive and never owns
 * input: a widget that grabs keys cannot be dismissed predictably. */
const widget = createLiveActivityWidget({
  key: "goal-status",
  placement: "belowEditor",
  leadingSpaces: 0,
  fit: truncateToWidth,
  activityFormat: "plain",
});

export function refreshDashboard(core: GoalCore, ctx: ExtensionContext): void {
  if (ctx.mode !== "tui") return;
  widget.update(ctx, widgetActivities(core));
}

export function clearDashboard(ctx: ExtensionContext): void {
  widget.clear(ctx);
}

/**
 * A goal is not partway through a list, so there is no fraction to report. Elapsed
 * time is the one figure that is both honest and useful: it tells a person
 * whether this is the goal they expected to be running.
 */
function widgetActivities(core: GoalCore) {
  if (core.checkProgress) {
    return [{ id: "goal-check", identity: "goal check", activity: core.checkProgress.label, status: "running" as const }];
  }
  const goal = core.goal;
  if (!goal) return [];
  return [{
    id: goal.id,
    identity: "goal",
    activity: `${statusLabel(goal)} · ${formatElapsed(goal.usage.activeSeconds)}`,
    status: goal.status === "active" && goal.autoContinue ? ("running" as const) : ("pending" as const),
  }];
}

export interface DashboardOptions {
  /** Content width, excluding the panel border. */
  width: number;
  /** Terminal rows available, used to bound the scrollable body. */
  rows?: number;
  scroll: number;
  style: PiThemeStyle;
  goal: GoalRecord;
  check?: { label: string } | undefined;
}

export interface DashboardFrame {
  lines: string[];
  bodyHeight: number;
  maxScroll: number;
}

/** Rows the body may use before the panel stops growing. A tall terminal is
 *  useless if the goal has one line of state, so the cap is bounded by
 *  content as well as by the terminal. */
function bodyBudget(rows: number | undefined, contentLines: number): number {
  const byTerminal = rows === undefined ? Number.POSITIVE_INFINITY : maxBodyHeight(rows, 0.6);
  return Math.max(3, Math.min(byTerminal, contentLines));
}

/**
 * Render the expanded panel.
 *
 * Every line is width-bounded with `visibleWidth`, not by slicing characters:
 * the theme emits ANSI, and a CJK objective is double-width, so a slice-based
 * bound would emit colour codes the terminal renders as text and would overrun
 * narrow terminals by the width of the goal id.
 */
export function renderDashboard(options: DashboardOptions): DashboardFrame {
  const { style, goal } = options;
  const inner = Math.max(12, options.width - 2);
  const body: string[] = [];

  body.push(truncateToWidth(`${style.accent(goal.id)}  ${style.fg("muted", goal.objective.replace(/\s+/g, " ").trim())}`, inner, "…"));
  body.push(truncateToWidth(style.dim([
    `status ${statusLabel(goal)}`,
    `${formatElapsed(goal.usage.activeSeconds)} elapsed`,
  ].join("  ·  ")), inner, "…"));
  for (const [heading, text] of [["Contract", goal.verificationContract], ["Paused", goal.pauseReason]] as const) {
    if (!text?.trim()) continue;
    body.push("");
    body.push(style.fg("accent", heading));
    for (const line of wrap(text.trim(), inner - 2)) {
      body.push(truncateToWidth(`  ${style.dim(line)}`, inner, "…"));
    }
  }
  if (options.check) {
    body.push("");
    body.push(style.fg("accent", "Check"));
    body.push(truncateToWidth(`  ${options.check.label}`, inner, "…"));
  }

  const maxBody = bodyBudget(options.rows, body.length);
  const window = computeScrollWindow(body, options.scroll, maxBody);
  const slice = body.slice(window.start, window.end);
  const footer = window.clampedScroll > 0
    ? "↑↓ scroll · Esc close"
    : goal.status === "active" ? "Esc close · /goal pause" : "Esc close · /goal resume";
  const lines = renderPiPanel({ width: options.width, style, fit: truncateToWidth, title: "pi-goal", body: slice, footer });
  return { lines, bodyHeight: slice.length, maxScroll: Math.max(0, body.length - slice.length) };
}

/**
 * The interactive panel.
 *
 * It owns its own input because it is opened through `ctx.ui.custom`, which hands
 * it the terminal's key stream for as long as it is up. Nothing outside this
 * component reads a key, so closing it always restores the editor.
 */
export function createDashboardOverlay(options: {
  goal: GoalRecord;
  style: PiThemeStyle;
  width: number;
  rows: number;
  check?: { label: string } | undefined;
  onClose: () => void;
}): Component {
  let scroll = 0;
  const draw = (): string[] =>
    renderDashboard({ ...options, scroll }).lines;
  return {
    render(width: number): string[] {
      // Honour the live width rather than the width at open time: the terminal
      // can be resized while the panel is up, and a panel that keeps its old
      // geometry wraps or truncates into unreadability.
      if (width !== options.width) options.width = width;
      return draw();
    },
    invalidate(): void {
      // Nothing memoized: every render redraws, so there is nothing to drop.
    },
    handleInput(data: string): boolean {
      const step = 1;
      const page = 6;
      if (matchesKey(data, Key.escape)) {
        options.onClose();
        return true;
      }
      if (matchesKey(data, Key.up)) scroll = Math.max(0, scroll - step);
      else if (matchesKey(data, Key.down)) scroll += step;
      else if (matchesKey(data, Key.pageUp)) scroll = Math.max(0, scroll - page);
      else if (matchesKey(data, Key.pageDown)) scroll += page;
      else if (matchesKey(data, Key.home)) scroll = 0;
      else if (matchesKey(data, Key.end)) scroll = Number.MAX_SAFE_INTEGER;
      else return false;
      // Clamp against the real maximum so the footer and the body agree.
      const { maxScroll } = renderDashboard({ ...options, scroll: 0 });
      scroll = Math.min(scroll, maxScroll);
      return true;
    },
  };
}



/** Word wrap on visible width, so a CJK objective wraps at the column it
 * actually occupies rather than at the character count. */
function wrap(text: string, width: number): string[] {
  const limit = Math.max(8, width);
  const lines: string[] = [];
  let current = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    if (current && visibleWidth(`${current} ${word}`) > limit) {
      lines.push(current);
      current = word;
      continue;
    }
    current = current ? `${current} ${word}` : word;
    // A single word wider than the line has to break, or it would overrun.
    while (visibleWidth(current) > limit) {
      let cut = current.length;
      while (cut > 1 && visibleWidth(current.slice(0, cut)) > limit) cut -= 1;
      lines.push(current.slice(0, cut));
      current = current.slice(cut);
    }
  }
  if (current) lines.push(current);
  return lines.length > 0 ? lines : [""];
}
