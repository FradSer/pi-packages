import { keyHint, type Theme } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import {
  createStaticToolLifecycleResultRenderer,
  eventToolLifecycle,
  type ToolLifecycleSpec,
} from "@fradser/pi-kit";
import { plainText, failureBody, type CoordinationRow } from "./tool-copy.ts";

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
  options: { expanded?: boolean; isPartial?: boolean },
  theme: Pick<Theme, "fg" | "bold" | "bg">,
  context: { isError?: boolean },
  spec: ToolLifecycleSpec,
  details?: readonly string[],
): { render: (width: number) => string[]; invalidate: () => void } {
  const text = textOf(result);
  // One expansion-body rule: detail lines derive from the model-facing content,
  // scrubbed of the identifiers a person should not read, unless a caller
  // passes explicit lines for a body that must differ from what the model sees.
  const effectiveDetails = details ?? text.split("\n").map((line) => plainText(line)).filter((line) => line.trim());
  return createStaticToolLifecycleResultRenderer({
    createSpec: () => ({ ...spec, details: effectiveDetails }),
    expandHint: keyHint("app.tools.expand", "to expand"),
    fit: truncateToWidth,
    visibleWidth,
    wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  })(result, options, theme, context);
}

/**
 * Render one coordination row (`agent`, `work`, `agent_event`) from its
 * human-facing subject and body. Model content keeps the exact handles; the
 * transcript only ever shows names, subjects, and the text that was passed.
 * A failed call goes through the shared failure band, which renders the result
 * text verbatim, so the display copy is scrubbed here.
 */
export function renderCoordinationRow(
  result: ToolResultText,
  options: { expanded?: boolean; isPartial?: boolean },
  theme: Pick<Theme, "fg" | "bold" | "bg">,
  context: { args?: unknown; isError?: boolean },
  tool: string,
  row: CoordinationRow,
): { render: (width: number) => string[]; invalidate: () => void } {
  if (!context.isError) {
    return renderLifecycleResult(result, options, theme, context, eventToolLifecycle(tool, row.subject), row.body);
  }
  const failure = failureBody(result);
  const display: ToolResultText = { ...result, content: [{ type: "text", text: failure.join(" ") }] };
  return renderLifecycleResult(display, options, theme, context, eventToolLifecycle(tool, row.subject), []);
}
