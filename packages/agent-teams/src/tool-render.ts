import { keyHint, type Theme } from "@earendil-works/pi-coding-agent";
import { Text, truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import {
  formatToolErrorLine,
  renderToolLifecycle,
  safeDisplayText,
  type ToolLifecycleSpec,
} from "@fradser/pi-kit";

export interface ToolResultText {
  content: Array<{ type: string; text?: string }>;
  details?: unknown;
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
  theme: Pick<Theme, "fg" | "bold" | "bg">,
  context: { isError?: boolean },
  spec: ToolLifecycleSpec,
  details?: readonly string[],
): { render: (width: number) => string[]; invalidate: () => void } | Text {
  const text = textOf(result);
  // One expansion-body rule: detail lines derive from the model-facing content
  // unless a caller passes explicit lines (only when the human body must
  // differ from what the model sees).
  const effectiveDetails = details ?? text.split("\n").filter((line) => line.trim());
  const expandable = result.details !== undefined || effectiveDetails.length > 0;
  if (context.isError) return new Text(theme.fg("error", formatToolErrorLine(text)), 0, 0);
  return {
    render: (width) => {
      const details = options.expanded
        ? effectiveDetails.flatMap((line) => wrapTextWithAnsi(safeDisplayText(line), Math.max(1, width - 2)))
        : effectiveDetails;
      return renderToolLifecycle(
        { ...spec, details },
        {
          width,
          expanded: options.expanded,
          expandHint: keyHint("app.tools.expand", "to expand"),
          expandable,
          theme,
          fit: truncateToWidth,
          visibleWidth,
        },
      );
    },
    invalidate: () => {},
  };
}

export function resultDetails(result: ToolResultText): string[] {
  return textOf(result).split("\n").filter((line) => line.trim());
}
