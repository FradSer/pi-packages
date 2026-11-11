import { truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import { renderLiveActivityMarkdown, resolveLiveActivity, type PiMarkdownThemeSource } from "@fradser/pi-kit";

/** Bound by the extension entry, which alone owns the ExtensionAPI. Read per
 *  call, so a mid-session settings change reaches every teammate activity row:
 *  the widget, the console status line and expanded tool details alike. */
let hiddenThinking: () => boolean = () => false;
export function configureTeamActivity(reader: () => boolean): void {
  hiddenThinking = reader;
}
import type { Agent } from "./types.ts";

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

/** Extract the current teammate activity without imposing a display width.
 *  `hideThinking` comes from Pi's setting, so the shared pi-kit policy replaces
 *  reasoning with Pi's label on both the widget and the console row. */
export function runningTeammateActivity(teammate: Agent, hideThinking: boolean = hiddenThinking()): string {
  return resolveLiveActivity({
    tool: teammate.activeTool?.replace(/\s+/g, " ").trim(),
    thinking: extractLatestLine(teammate.liveThinking),
    text: extractLatestLine(teammate.liveText),
  }, hideThinking) ?? "Working...";
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
export function formatAgentLabel(
  spinner: string,
  activity: string,
  maxActivityWidth?: number,
): string {
  if (maxActivityWidth === undefined) return `${spinner} ${renderActivityMarkdown(activity)}`;
  if (maxActivityWidth <= 0) return spinner;
  return `${spinner} ${truncateToWidth(renderActivityMarkdown(activity), maxActivityWidth)}`;
}
