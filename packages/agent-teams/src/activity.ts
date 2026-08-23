import { Markdown, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import type { MarkdownTheme } from "@earendil-works/pi-tui";
import { buildMarkdownThemeCallbacks, createPiThemeStyle } from "@fradser/pi-kit";
import type { Teammate } from "./types.ts";

const ACTIVITY_THEME: MarkdownTheme = {
  ...buildMarkdownThemeCallbacks(createPiThemeStyle({
    fg: (_color, text) => text,
  })),
  hr: () => "---",
};

/** Render streamed activity as one compact Markdown line for the widget. */
export function renderActivityMarkdown(text: string, theme: MarkdownTheme = ACTIVITY_THEME): string {
  const markdown = new Markdown(text, 0, 0, theme);
  return markdown.render(Math.max(1, visibleWidth(text) + 1)).join(" ").replace(/\s+/g, " ").trim();
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
  const fixedWidth = visibleWidth(` ${spinner}  · `);
  const availableWidth = Math.max(2, lineWidth - fixedWidth);
  const nameWidth = Math.max(1, Math.min(visibleWidth(agent), Math.floor(availableWidth * 0.4)));
  return {
    lineWidth,
    nameWidth,
    activityWidth: Math.max(1, availableWidth - nameWidth),
  };
}

/** Fit one widget row to its terminal width while keeping it on one line. */
export function fitTeammateRow(
  spinner: string,
  agent: string,
  activity: string,
  width: number,
  formatActivity: (text: string) => string = (text) => text,
  markdownTheme: MarkdownTheme = ACTIVITY_THEME,
): string {
  const sizes = teammateRowWidths(spinner, agent, width);
  const nameText = truncateToWidth(agent, sizes.nameWidth);
  const activityText = formatActivity(truncateToWidth(renderActivityMarkdown(activity, markdownTheme), sizes.activityWidth));
  const line = ` ${spinner} ${nameText} · ${activityText}`;
  return truncateToWidth(line, sizes.lineWidth);
}

/** Fit a console status label to the requested activity width. */
export function formatTeammateLabel(
  spinner: string,
  activity: string,
  maxActivityWidth?: number,
  markdownTheme: MarkdownTheme = ACTIVITY_THEME,
): string {
  if (maxActivityWidth === undefined) return `${spinner} ${renderActivityMarkdown(activity, markdownTheme)}`;
  if (maxActivityWidth <= 0) return spinner;
  return `${spinner} ${truncateToWidth(renderActivityMarkdown(activity, markdownTheme), maxActivityWidth)}`;
}
