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
const wideStarted = stripVTControlCharacters(started.render(200).join("\n")).trimEnd();
assert.match(wideStarted, /^\[agent\] @context-[a-f0-9]{12} started · agents\/context-researcher\.md$/);
assert.ok(started.render(200)[0].startsWith("\x1b[35m\x1b[1m[agent]"));
for (const width of [40, 80, 160, 200, 40, 200, 0, 1, 10]) {
  assert.ok(started.render(width).every((line) => visibleWidth(line) <= width), `started row exceeds ${width}`);
}
color = 36;
started.invalidate();
assert.ok(started.render(200)[0].includes("\x1b[36m"));
color = 35;

const queries = [
  `Verify ${"/workspace/project/".repeat(9)}runtime`,
  `验证 ${"终端显示宽度".repeat(14)} end`,
];
for (const query of queries) {
  assert.ok(tool.renderResult);
  const result = tool.renderResult(
    { content: [{ type: "text", text: "Evidence" }], details: {} },
    { expanded: false, isPartial: false }, theme as never, { args: { query }, toolCallId } as never,
  );
  assert.ok(stripVTControlCharacters(result.render(500).join("\n")).includes(query));
  for (const width of [40, 80, 160]) {
    assert.ok(result.render(width).every((line) => visibleWidth(line) <= width));
  }
}
const sanitized = tool.renderResult!(
  { content: [{ type: "text", text: "Evidence" }], details: {} },
  { expanded: false, isPartial: false }, theme as never,
  { args: { query: "  Verify\n\t\x1b[31m路径\x1b[0m\x07  output  " }, toolCallId } as never,
).render(80);
assert.ok(stripVTControlCharacters(sanitized.join("\n")).includes("Verify 路径 output"));
console.log("Context rendering passed: shared [agent] sub-agent start, stable identity, width bounds, result resize, CJK/ANSI sanitization.");
