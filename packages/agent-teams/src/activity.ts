import { truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import type { Node } from "./types";

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

/** Extract the current worker activity without imposing a display width. */
export function runningTeammateActivity(node: Node): string {
  const tool = node.spawn?.activeTool?.replace(/\s+/g, " ").trim();
  if (tool) return tool;

  return extractLatestLine(node.spawn?.liveThinking)
    ?? extractLatestLine(node.spawn?.liveText)
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
): string {
  const sizes = teammateRowWidths(spinner, agent, width);
  const nameText = truncateToWidth(agent, sizes.nameWidth);
  const activityText = formatActivity(truncateToWidth(activity, sizes.activityWidth));
  const line = ` ${spinner} ${nameText} · ${activityText}`;
  return truncateToWidth(line, sizes.lineWidth);
}

/** Fit a console status label to the requested activity width. */
export function formatTeammateLabel(spinner: string, activity: string, maxActivityWidth?: number): string {
  if (maxActivityWidth === undefined) return `${spinner} ${activity}`;
  if (maxActivityWidth <= 0) return spinner;
  return `${spinner} ${truncateToWidth(activity, maxActivityWidth)}`;
}
