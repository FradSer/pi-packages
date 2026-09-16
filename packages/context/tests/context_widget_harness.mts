import assert from "node:assert/strict";
import { stripVTControlCharacters } from "node:util";
import { Markdown, visibleWidth } from "@earendil-works/pi-tui";
import { getMarkdownTheme, initTheme } from "@earendil-works/pi-coding-agent";
import {
  clearResearchWidget,
  startResearchWidget,
  updateResearchWidget,
} from "../extensions/context-tools.ts";

initTheme("dark", false);

const theme = {
  fg: (_name: string, text: string) => text,
  bold: (text: string) => text,
};
const calls: Array<{ key: string; factory: unknown; options: unknown }> = [];
const cleared: string[] = [];
const ui = {
  setWidget: (key: string, factory: unknown, options?: unknown) => {
    if (factory === undefined) cleared.push(key);
    else calls.push({ key, factory, options });
  },
};
const ctx = { mode: "tui", ui };

const token = startResearchWidget(ctx as never);
assert.equal(calls.length, 1);
assert.equal(calls[0].key, "context-research");
assert.equal((calls[0].options as { placement?: string } | undefined)?.placement, "aboveEditor");

let renders = 0;
const tui = { requestRender: () => { renders++; } };
const widget = (calls[0].factory as (tui: unknown, theme: unknown) => {
  render(width: number): string[];
  invalidate(): void;
})(tui, theme);
const lines = widget.render(80);
assert.equal(lines.length, 1);
const plain = stripVTControlCharacters(lines[0]);
assert.match(plain, /^ . researcher · /);
assert.ok(!plain.includes("@"), plain);
assert.ok(plain.includes("Working..."), plain);
assert.ok(!plain.includes("inspect auth flow"), plain);

updateResearchWidget(token, "Inspecting auth flow");
assert.ok(renders > 0);
assert.ok(stripVTControlCharacters(widget.render(80)[0]).includes("Inspecting auth flow"));

updateResearchWidget(token, "bash: ls");
const latest = stripVTControlCharacters(widget.render(80)[0]);
assert.ok(latest.includes("bash: ls"), latest);
assert.ok(!latest.includes("Inspecting auth flow"), latest);

for (const [markdown, expected] of [
  ["Inspecting **auth flow**", "Inspecting auth flow"],
  ["Reading `context-tools.ts`", "Reading context-tools.ts"],
  ["## Research heading", "Research heading"],
  ["See [reference](https://example.com)", "See reference"],
]) {
  updateResearchWidget(token, markdown);
  const rendered = widget.render(160);
  assert.equal(rendered.length, 1);
  const plain = stripVTControlCharacters(rendered[0]);
  assert.ok(plain.includes(expected), plain);
  assert.ok(!plain.includes("**") && !plain.includes("`") && !plain.includes("##") && !plain.includes("[reference]"), plain);
  assert.match(plain, /^ . researcher · /);
}
updateResearchWidget(token, "**Inspecting** 中文 auth flow ".repeat(20) + "\u001b[2J");
for (const width of [0, 1, 2, 10, 40, 80, 160, 40]) {
  for (const line of widget.render(width)) {
    assert.ok(visibleWidth(line) <= width, `${width}: ${line}`);
    assert.ok(!line.includes("\u001b[2J"));
  }
}
updateResearchWidget(token, "**New activity**");
for (const name of ["dark", "light"]) {
  initTheme(name, false);
  widget.invalidate();
  const expected = new Markdown("**New activity**", 0, 0, getMarkdownTheme()).render(80)[0].trim();
  assert.ok(widget.render(80)[0].includes(expected), "native Markdown styling follows theme invalidation");
}

updateResearchWidget(token + 999, "stale detail");
assert.ok(!stripVTControlCharacters(widget.render(80)[0]).includes("stale detail"));
clearResearchWidget(ctx as never, token + 999);
assert.deepEqual(cleared, []);

clearResearchWidget(ctx as never, token);
assert.deepEqual(cleared, ["context-research"]);
assert.deepEqual(widget.render(80), []);

const before = calls.length;
const printToken = startResearchWidget({ mode: "print", ui } as never);
assert.equal(calls.length, before);
clearResearchWidget({ mode: "print", ui } as never, printToken);

console.log("Context widget passed: neutral worker label, latest live activity, stale-token guard, clear, non-tui guard.");
