/**
 * Plan overlay — displays the generated plan with scrollable content
 * and an action menu for next steps.
 *
 * Similar to btw's overlay but read-only (no input composer).
 * Shows the plan as Markdown with keyboard scrolling support.
 */

import {
  type Component,
  Key,
  Markdown,
  type MarkdownTheme,
  matchesKey,
  type TUI,
} from "@earendil-works/pi-tui";
import {
  buildMarkdownThemeCallbacks,
  maxBodyHeight,
  padLine,
  type PiThemeStyle,
} from "@fradser/pi-kit";

export type PlanOverlayStyle = PiThemeStyle;

export interface PlanOverlayOptions {
  /** Path to the plan file. */
  planPath: string;
  /** Plan content as Markdown. */
  planContent: string;
  /** Called when the overlay should close. */
  onClose: () => void;
  /** Called when user selects an action. */
  onAction: (action: PlanAction) => void;
}

export type PlanAction =
  | "implement-here"
  | "implement-fresh"
  | "view-plan"
  | "stay"
  | "exit";

const ACTIONS: { id: PlanAction; label: string }[] = [
  { id: "implement-here", label: "Yes, implement here" },
  { id: "implement-fresh", label: "Start fresh and implement" },
  { id: "view-plan", label: "View full plan" },
  { id: "stay", label: "Stay in plan mode" },
  { id: "exit", label: "Exit plan mode" },
];

/** Cap the plan body at ~60% of the terminal height. */
function maxPlanBody(rows: number): number {
  return maxBodyHeight(rows, 0.6);
}

function buildMarkdownTheme(style: PlanOverlayStyle): MarkdownTheme {
  return buildMarkdownThemeCallbacks(style) as MarkdownTheme;
}

export function createPlanOverlay(
  tui: TUI,
  style: PlanOverlayStyle,
  options: PlanOverlayOptions,
): Component {
  const mdTheme = buildMarkdownTheme(style);
  const markdown = new Markdown(options.planContent, 0, 0, mdTheme, undefined, { renderLatex: false });

  let scroll = 0;
  let selectedIndex = 0;
  let closed = false;

  const scrollBy = (delta: number, maxBody: number) => {
    const contentWidth = Math.max(20, tui.terminal.columns - 4);
    const lines = markdown.render(contentWidth);
    const max = Math.max(0, lines.length - maxBody);
    const next = Math.max(0, Math.min(max, scroll + delta));
    if (next !== scroll) {
      scroll = next;
      tui.requestRender();
    }
  };

  return {
    handleInput(data: string) {
      if (closed) return;

      // Scrolling keys
      const maxBody = maxPlanBody(tui.terminal.rows);
      if (matchesKey(data, Key.up)) {
        if (selectedIndex > 0) {
          selectedIndex--;
          tui.requestRender();
        } else {
          scrollBy(-1, maxBody);
        }
        return;
      }
      if (matchesKey(data, Key.down)) {
        if (selectedIndex < ACTIONS.length - 1) {
          selectedIndex++;
          tui.requestRender();
        } else {
          scrollBy(1, maxBody);
        }
        return;
      }
      if (matchesKey(data, Key.pageUp)) {
        scrollBy(-Math.max(1, maxBody - 1), maxBody);
        return;
      }
      if (matchesKey(data, Key.pageDown)) {
        scrollBy(Math.max(1, maxBody - 1), maxBody);
        return;
      }
      if (matchesKey(data, Key.home)) {
        scroll = 0;
        selectedIndex = 0;
        tui.requestRender();
        return;
      }
      if (matchesKey(data, Key.end)) {
        scroll = Number.MAX_SAFE_INTEGER;
        const contentWidth = Math.max(20, tui.terminal.columns - 4);
        const lines = markdown.render(contentWidth);
        const max = Math.max(0, lines.length - maxBody);
        scroll = Math.min(scroll, max);
        tui.requestRender();
        return;
      }

      // Enter selects the action
      if (data === "\r" || data === "\n") {
        const action = ACTIONS[selectedIndex];
        if (action) {
          closed = true;
          options.onAction(action.id);
        }
        return;
      }

      // Escape closes
      if (matchesKey(data, Key.escape)) {
        closed = true;
        options.onClose();
        return;
      }

      // Mouse wheel scrolling
      const sgrWheel = /^\x1b\[<(\d+);(\d+);(\d+)[Mm]$/.exec(data);
      if (sgrWheel) {
        const button = Number.parseInt(sgrWheel[1], 10);
        if ((button & 64) !== 0) {
          const direction = button & 3;
          if (direction === 0) scrollBy(-3, maxBody);
          else if (direction === 1) scrollBy(3, maxBody);
        }
        return;
      }
    },

    render(width: number): string[] {
      const maxBody = maxPlanBody(tui.terminal.rows);
      const contentWidth = Math.max(20, width - 4);

      const border = style.border("─".repeat(Math.max(1, width)));
      const lines: string[] = [];

      // Top border + header
      lines.push(border);
      lines.push(padLine(`  ${style.accent("Plan ready")}  ${style.dim(options.planPath)}`, width));
      lines.push("");

      // Plan content (scrollable)
      const mdLines = markdown.render(contentWidth).map((line) =>
        line.includes("__OVERLAY_SEPARATOR__") ? "__OVERLAY_SEPARATOR__" : line,
      );
      const viewport = Math.min(mdLines.length, maxBody);
      const max = Math.max(0, mdLines.length - viewport);
      if (scroll > max) scroll = max;
      const windowLines = mdLines.slice(scroll, scroll + viewport);

      for (const line of windowLines) {
        if (line === "__OVERLAY_SEPARATOR__") {
          const separator = style.dim("─".repeat(Math.max(1, width - 4)));
          lines.push(`${" ".repeat(2)}${separator}${" ".repeat(2)}`);
        } else {
          lines.push(padLine(`  ${line}`, width));
        }
      }

      // Spacer
      const remainingSpace = maxBody - windowLines.length;
      for (let i = 0; i < remainingSpace; i++) {
        lines.push("");
      }

      // Action menu
      lines.push("");
      lines.push(padLine(`  ${style.muted("What would you like to do?")}`, width));
      lines.push("");

      for (let i = 0; i < ACTIONS.length; i++) {
        const action = ACTIONS[i];
        const isSelected = i === selectedIndex;
        const prefix = isSelected ? style.accent("❯") : " ";
        const label = isSelected ? style.accent(action.label) : style.muted(action.label);
        lines.push(padLine(`  ${prefix} ${i + 1}. ${label}`, width));
      }

      // Footer
      lines.push("");
      const footer = style.dim("↑↓ navigate · enter select · esc close · pgup/pgdn scroll");
      lines.push(padLine(`  ${footer}`, width));
      lines.push(border);

      return lines;
    },

    invalidate() {
      markdown?.invalidate();
    },
  };
}
