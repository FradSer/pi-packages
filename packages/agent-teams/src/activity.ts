import { truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import { renderLiveActivityMarkdown, type PiMarkdownThemeSource } from "@fradser/pi-kit";
import type { Teammate } from "./types.ts";

/** Console rows paint a whole status line in their own color, so the shared
 * markdown renderer runs with a passthrough theme: literal markup is still
 * stripped and the result stays one line, with no competing colors. */
const COLORLESS_ACTIVITY_THEME: PiMarkdownThemeSource = { fg: (_color, text) => text };

/** Render streamed activity as one compact Markdown line for a console row. */
export function renderActivityMarkdown(text: string): string {
  return renderLiveActivityMarkdown(text, COLORLESS_ACTIVITY_THEME);
}

function extractLatestLine(text: string | undefined): string | undefined {
  if (!text) return undefined;
  const lines = text.split("\n");
  for (let i = lines.length - 1; i >= 0; i--) {
    const trimmed = lines[i].replace(/\s+/g, " ").trim();
    if (trimmed.length > 0 && !trimmed.startsWith("... [truncated") && !trimmed.startsWith("…[truncated")) {
      return trimmed;
    }
  }
  return undefined;
}

/** Extract the current teammate activity without imposing a display width. */
export function runningTeammateActivity(teammate: Teammate): string {
  const tool = teammate.activeTool?.replace(/\s+/g, " ").trim();
  if (tool) return tool;

  return extractLatestLine(teammate.liveThinking)
    ?? extractLatestLine(teammate.liveText)
    ?? "Working...";
}

export interface TeammateRowWidths {
  lineWidth: number;
  nameWidth: number;
  activityWidth: number;
}

/** Reserve enough width for the live activity before truncating the identity. */
export function teammateRowWidths(spinner: string, agent: string, width: number): TeammateRowWidths {
  const lineWidth = Math.max(10, width - 1);
  const fixedWidth = visibleWidth(`${spinner}  · `);
  const availableWidth = Math.max(2, lineWidth - fixedWidth);
  const nameWidth = Math.max(1, Math.min(visibleWidth(agent), Math.floor(availableWidth * 0.4)));
  return {
    lineWidth,
    nameWidth,
    activityWidth: Math.max(1, availableWidth - nameWidth),
  };
}

/** Fit a console status label to the requested activity width. */
export function formatTeammateLabel(
  spinner: string,
  activity: string,
  maxActivityWidth?: number,
): string {
  if (maxActivityWidth === undefined) return `${spinner} ${renderActivityMarkdown(activity)}`;
  if (maxActivityWidth <= 0) return spinner;
  return `${spinner} ${truncateToWidth(renderActivityMarkdown(activity), maxActivityWidth)}`;
}
