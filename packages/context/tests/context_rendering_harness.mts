import assert from "node:assert/strict";
import { stripVTControlCharacters } from "node:util";
import type { ExtensionAPI, ToolDefinition } from "@earendil-works/pi-coding-agent";
import { visibleWidth } from "@earendil-works/pi-tui";
import registerContextTools from "../extensions/context-tools.ts";

let tool: ToolDefinition | undefined;
registerContextTools({ registerTool: (definition: ToolDefinition) => { tool = definition; } } as ExtensionAPI);
assert.ok(tool?.renderCall);
let color = 35;
const theme = {
  fg: (_name: string, text: string) => `\x1b[${color}m${text}\x1b[39m`,
  bg: (_name: string, text: string) => text,
  bold: (text: string) => `\x1b[1m${text}\x1b[22m`,
};
const toolCallId = "call-context-rendering";
const started = tool.renderCall({}, theme as never, { toolCallId } as never);
const otherStarted = tool.renderCall({}, theme as never, { toolCallId: "call-context-rendering-2" } as never);
const wideStarted = stripVTControlCharacters(started.render(200).join("\n")).trimEnd();
assert.equal(wideStarted, "[agent] @conext-research started · agents/context-researcher.md");
assert.equal(stripVTControlCharacters(otherStarted.render(200).join("\n")).trimEnd(), wideStarted);
assert.ok(started.render(200)[0].startsWith("\x1b[35m\x1b[1m[agent]"));
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
assert.deepEqual(completed.render(200), []);
assert.deepEqual(completed.render(40), []);
completed.invalidate();
assert.deepEqual(completed.render(200), []);

const failed = tool.renderResult(
  { content: [{ type: "text", text: "Isolated Pi research failed\ninternal detail" }], details: {} },
  { expanded: false, isPartial: false }, theme as never,
  { args: { query: "Verify runtime behavior" }, toolCallId, isError: true } as never,
);
const failedLines = failed.render(200).map((line) => stripVTControlCharacters(line).trimEnd());
assert.deepEqual(failedLines, ["Isolated Pi research failed"]);
assert.ok(failed.render(200)[0].startsWith("\x1b[35m"));
console.log("Context rendering passed: only renderCall contributes the start row and failures remain visible.");
