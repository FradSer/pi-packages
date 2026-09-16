import assert from "node:assert/strict";
import { stripVTControlCharacters } from "node:util";
import { initTheme, type ExtensionAPI, type ToolDefinition } from "@earendil-works/pi-coding-agent";
import { visibleWidth } from "@earendil-works/pi-tui";
import registerContextTools from "../extensions/context-tools.ts";

initTheme("dark", false);

let tool: ToolDefinition | undefined;
registerContextTools({ registerTool: (definition: ToolDefinition) => { tool = definition; } } as ExtensionAPI);
assert.ok(tool?.renderCall);
let color = 35;
const bgCalls: string[] = [];
const theme = {
  fg: (_name: string, text: string) => `\x1b[${color}m${text}\x1b[39m`,
  bg: (name: string, text: string) => { bgCalls.push(name); return text; },
  bold: (text: string) => `\x1b[1m${text}\x1b[22m`,
};
const toolCallId = "call-context-rendering";
for (const args of [{}, { query: undefined }, { query: null }, { query: 42 }, { query: {} }, { query: " \n " }]) {
  const pending = tool.renderCall(args, theme as never, { toolCallId } as never);
  assert.equal(
    stripVTControlCharacters(pending.render(200).join("\n")).trimEnd(),
    "[context] research started · context request",
  );
}
const started = tool.renderCall({ query: "  Verify   runtime behavior  " }, theme as never, { toolCallId } as never);
const otherStarted = tool.renderCall({ query: "Inspect cancellation behavior" }, theme as never, { toolCallId: "call-context-rendering-2" } as never);
const wideStarted = stripVTControlCharacters(started.render(200).join("\n")).trimEnd();
assert.equal(wideStarted, "[context] research started · Verify runtime behavior");
assert.ok(!wideStarted.includes(".md"));
assert.equal(
  stripVTControlCharacters(otherStarted.render(200).join("\n")).trimEnd(),
  "[context] research started · Inspect cancellation behavior",
);
assert.ok(started.render(200)[0].startsWith("\x1b[35m\x1b[1m[context]"));
for (const width of [40, 80, 160, 200, 40, 200, 0, 1, 10]) {
  assert.ok(started.render(width).every((line) => visibleWidth(line) <= width), `started row exceeds ${width}`);
}
color = 36;
started.invalidate();
assert.ok(started.render(200)[0].includes("\x1b[36m"));
color = 35;

assert.ok(tool.renderResult);
const completed = tool.renderResult(
  { content: [{ type: "text", text: "Complete research answer that remains model-facing." }], details: {} },
  { expanded: false, isPartial: false }, theme as never,
  { args: { query: "Verify runtime behavior" }, toolCallId } as never,
);
const collapsedText = stripVTControlCharacters(completed.render(200).join("\n"));
assert.ok(collapsedText.includes("[context] researched · Verify runtime behavior"), `collapsed row missing researched title: ${collapsedText}`);
for (const width of [40, 80, 160, 200]) {
  assert.ok(completed.render(width).every((line) => visibleWidth(line) <= width), `completed row exceeds ${width}`);
}
completed.invalidate();

const expandedCompleted = tool.renderResult(
  { content: [{ type: "text", text: "Complete research answer that remains model-facing." }], details: {} },
  { expanded: true, isPartial: false }, theme as never,
  { args: { query: "Verify runtime behavior" }, toolCallId } as never,
);
const expandedText = stripVTControlCharacters(expandedCompleted.render(200).join("\n"));
assert.ok(expandedText.includes("Complete research answer that remains model-facing."), `expanded row missing detail text: ${expandedText}`);
assert.ok(collapsedText.includes("to expand"), `collapsed row missing expand hint: ${collapsedText}`);

// D1 regression: a partial (still-running) result must render as pending, never
// as a green "researched" success band.
bgCalls.length = 0;
const partial = tool.renderResult(
  { content: [{ type: "text", text: "Working..." }], details: {} },
  { expanded: false, isPartial: true }, theme as never,
  { args: { query: "Verify runtime behavior" }, toolCallId } as never,
);
const partialText = stripVTControlCharacters(partial.render(200).join("\n"));
assert.ok(!partialText.includes("researched"), `partial row must not claim researched: ${partialText}`);
assert.ok(partialText.includes("[context] researching"), `partial row missing researching title: ${partialText}`);
assert.ok(bgCalls.includes("toolPendingBg"), `partial row must paint toolPendingBg, saw: ${bgCalls.join(",")}`);
assert.ok(!bgCalls.includes("toolSuccessBg"), `partial row must not paint toolSuccessBg, saw: ${bgCalls.join(",")}`);

// D2 regression: expanded details must wrap, not truncate — the complete
// answer stays visible at narrow widths.
const longAnswer = "A".repeat(400);
const longExpanded = tool.renderResult(
  { content: [{ type: "text", text: longAnswer }], details: {} },
  { expanded: true, isPartial: false }, theme as never,
  { args: { query: "Verify runtime behavior" }, toolCallId } as never,
);
const longLines = longExpanded.render(80);
for (const line of longLines) {
  assert.ok(visibleWidth(line) <= 80, `expanded long line exceeds width: ${line}`);
}
const longJoined = stripVTControlCharacters(longLines.join("\n")).replace(/\s/g, "");
assert.ok(longJoined.includes(longAnswer), "expanded details truncated instead of wrapped");

const failed = tool.renderResult(
  { content: [{ type: "text", text: "Isolated Pi research failed\ninternal detail" }], details: {} },
  { expanded: false, isPartial: false }, theme as never,
  { args: { query: "Verify runtime behavior" }, toolCallId, isError: true } as never,
);
const failedLines = failed.render(200).map((line) => stripVTControlCharacters(line).trimEnd());
assert.ok(failedLines.some((line) => line.includes("Isolated Pi research failed")), `failed row missing error: ${failedLines.join("\n")}`);

bgCalls.length = 0;
completed.render(200);
assert.ok(bgCalls.includes("toolSuccessBg"), `settled row must paint toolSuccessBg, saw: ${bgCalls.join(",")}`);
bgCalls.length = 0;
failed.render(200);
assert.ok(bgCalls.includes("toolErrorBg"), `failed row must paint toolErrorBg, saw: ${bgCalls.join(",")}`);

console.log("Context rendering passed: pending/researched/failed lifecycle bands with wrapped full-detail expansion.");
