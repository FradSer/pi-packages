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
  truncateToWidth,
} from "@earendil-works/pi-tui";
import {
  buildMarkdownThemeCallbacks,
  computeScrollWindow,
  renderPiPanel,
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

/** Keep the plan body within the terminal while reserving the action menu. */
function maxPlanBody(rows: number): number {
  // Border, header, spacing, prompt, five actions, footer, and border.
  return Math.max(3, rows - 14);
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
    const next = computeScrollWindow(lines, scroll + delta, maxBody).clampedScroll;
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
        const contentWidth = Math.max(20, tui.terminal.columns - 4);
        const lines = markdown.render(contentWidth);
        scroll = computeScrollWindow(lines, Number.MAX_SAFE_INTEGER, maxBody).clampedScroll;
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

      const body: string[] = [];

      // Plan content (scrollable)

      const mdLines = markdown.render(contentWidth).map((line) =>
        line.includes("__OVERLAY_SEPARATOR__") ? "__OVERLAY_SEPARATOR__" : line,
      );
      const { start, end, clampedScroll } = computeScrollWindow(mdLines, scroll, maxBody);
      scroll = clampedScroll;
      const windowLines = mdLines.slice(start, end);

      for (const line of windowLines) {
        if (line === "__OVERLAY_SEPARATOR__") {
          const separator = style.dim("─".repeat(Math.max(1, width - 4)));
          body.push(separator);
        } else {
          body.push(line);
        }
      }

      const remainingSpace = maxBody - windowLines.length;
      for (let i = 0; i < remainingSpace; i++) body.push("");

      body.push("");
      body.push(style.muted("What would you like to do?"));
      body.push("");

      for (let i = 0; i < ACTIONS.length; i++) {
        const action = ACTIONS[i];
        const isSelected = i === selectedIndex;
        const prefix = isSelected ? style.accent("❯") : " ";
        const label = isSelected ? style.accent(action.label) : style.muted(action.label);
        body.push(`${prefix} ${i + 1}. ${label}`);
      }

      return renderPiPanel({
        width,
        style,
        fit: truncateToWidth,
        title: `Plan ready  ${style.dim(options.planPath)}`,
        body,
        footer: "↑↓ navigate · enter select · esc close · pgup/pgdn scroll",
      });
    },

    invalidate() {
      markdown?.invalidate();
    },
  };
}
