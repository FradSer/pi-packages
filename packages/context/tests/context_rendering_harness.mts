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
const prefix = "[context] started · ";
const queries = [
  `Verify ${"/workspace/project/".repeat(9)}runtime`,
  `验证 ${"终端显示宽度".repeat(14)} end`,
];
for (const query of queries) {
  const component = tool.renderCall({ query }, theme as never, {} as never);
  for (const width of [40, 80, 160, 400, 40, 400, 0, 1, 10]) {
    const lines = component.render(width);
    assert.ok(lines.every((line) => visibleWidth(line) <= width), `row exceeds ${width} display columns`);
    const plain = lines.map((line) => stripVTControlCharacters(line).trimEnd()).join("");
    if (width >= 2) {
      assert.equal(plain.replace(/\s/g, ""), (prefix + query).replace(/\s/g, ""));
      assert.ok(!plain.includes("…"));
    }
    if (width >= prefix.length) assert.ok(plain.startsWith(prefix.trimEnd()));
    if (width >= prefix.length) assert.ok(lines[0].includes("\x1b[1m"));
  }
  color = 36;
  component.invalidate();
  assert.ok(component.render(400)[0].includes("\x1b[36m"));
  color = 35;

  assert.ok(tool.renderResult);
  const result = tool.renderResult(
    { content: [{ type: "text", text: "Evidence" }], details: {} },
    { expanded: false, isPartial: false }, theme as never, { args: { query } } as never,
  );
  assert.ok(stripVTControlCharacters(result.render(500).join("\n")).includes(query));
  for (const width of [40, 80, 160]) {
    assert.ok(result.render(width).every((line) => visibleWidth(line) <= width));
  }
}
const sanitized = tool.renderCall(
  { query: "  Verify\n\t\x1b[31m路径\x1b[0m\x07  output  " }, theme as never, {} as never,
).render(80);
assert.equal(sanitized.length, 2);
assert.equal(stripVTControlCharacters(sanitized[0]).trimEnd(), `${prefix}Verify 路径 output`);
assert.equal(stripVTControlCharacters(sanitized[1]).trim(), "");
assert.ok(!sanitized[0].includes("\x1b[31m"));
assert.equal(stripVTControlCharacters(tool.renderCall({}, theme as never, {} as never).render(80)[0]).trimEnd(), `${prefix}research`);
console.log("Context rendering passed: complete wrapped queries at widths 40/80/160, wide-narrow-wide, CJK/ANSI, theme invalidation, result width.");
