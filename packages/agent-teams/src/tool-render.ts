import { keyHint, type Theme } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import {
  createStaticToolLifecycleResultRenderer,
  type ToolLifecycleSpec,
} from "@fradser/pi-kit";

export interface ToolResultText {
  content: Array<{ type: string; text?: string }>;
  details?: unknown;
}

export function textOf(result: ToolResultText): string {
  return result.content.find((part) => part.type === "text")?.text ?? "";
}

export function emptyToolCall(): { render: () => string[]; invalidate: () => void } {
  return { render: () => [], invalidate: () => {} };
}

export function renderLifecycleResult(
  result: ToolResultText,
  options: { expanded?: boolean },
  theme: Pick<Theme, "fg" | "bold" | "bg">,
  context: { isError?: boolean },
  spec: ToolLifecycleSpec,
  details?: readonly string[],
): { render: (width: number) => string[]; invalidate: () => void } {
  const text = textOf(result);
  // One expansion-body rule: detail lines derive from the model-facing content
  // unless a caller passes explicit lines (only when the human body must
  // differ from what the model sees).
  const effectiveDetails = details ?? text.split("\n").filter((line) => line.trim());
  return createStaticToolLifecycleResultRenderer({
    createSpec: () => ({ ...spec, details: effectiveDetails }),
    expandHint: keyHint("app.tools.expand", "to expand"),
    fit: truncateToWidth,
    visibleWidth,
    wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  })(result, options, theme, context);
}

export function resultDetails(result: ToolResultText): string[] {
  return textOf(result).split("\n").filter((line) => line.trim());
}
