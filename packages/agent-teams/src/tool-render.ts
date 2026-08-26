import { keyHint, type Theme } from "@earendil-works/pi-coding-agent";
import { Text, truncateToWidth } from "@earendil-works/pi-tui";
import {
  formatExpandHint,
  formatToolErrorLine,
  renderToolLifecycle,
  type ToolLifecycleSpec,
} from "@fradser/pi-kit";

export interface ToolResultText {
  content: Array<{ type: string; text?: string }>;
}

export function textOf(result: ToolResultText): string {
  return result.content.find((part) => part.type === "text")?.text ?? "";
}

export function emptyToolCall(): Text {
  return new Text("", 0, 0);
}

export function renderLifecycleResult(
  result: ToolResultText,
  options: { expanded?: boolean },
  theme: Pick<Theme, "fg" | "bold">,
  context: { isError?: boolean },
  spec: ToolLifecycleSpec,
  details: readonly string[] = [],
): { render: (width: number) => string[]; invalidate: () => void } | Text {
  const text = textOf(result);
  const effectiveDetails = details.length > 0 ? details : (spec.details ?? []);
  if (context.isError) return new Text(theme.fg("error", formatToolErrorLine(text)), 0, 0);
  return {
    render: (width) => renderToolLifecycle(
      { ...spec, details: effectiveDetails },
      {
        width,
        expanded: options.expanded,
        expandHint: spec.kind === "event" && effectiveDetails.length > 0
          ? formatExpandHint(keyHint("app.tools.expand", "to expand"), theme)
          : undefined,
        titleStyle: (line) => theme.fg("toolTitle", theme.bold(line)),
        detailStyle: (line) => theme.fg("customMessageText", line),
        truncate: truncateToWidth,
        line: (line) => line,
      },
    ),
    invalidate: () => {},
  };
}

export function resultDetails(result: ToolResultText): string[] {
  return textOf(result).split("\n").filter((line) => line.trim());
}
