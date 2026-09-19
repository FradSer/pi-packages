import assert from "node:assert/strict";
import { stripVTControlCharacters } from "node:util";
import { visibleWidth } from "@earendil-works/pi-tui";
import { initTheme } from "@earendil-works/pi-coding-agent";import {
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
// A streamed fragment that carries line structure or a raw CR must not move the
// cursor inside the widget row.
updateResearchWidget(token, "safe\rOVERWRITE\nnext");
for (const line of widget.render(160)) {
  assert.ok(!line.includes("\r") && !line.includes("\n"), JSON.stringify(line));
  assert.ok(stripVTControlCharacters(line).includes("safe OVERWRITE next"), line);
}
// Markdown activity is rendered by pi-kit from the theme pi injects into the
// widget factory, so markdown elements carry that theme's native tokens.
updateResearchWidget(token, "**New activity**");
const tokenColors: Record<string, string> = { muted: "2", mdCode: "36", mdHeading: "35", mdLink: "34", mdLinkUrl: "90", mdQuote: "33", mdListBullet: "31", mdHr: "32", mdCodeBlock: "36", mdCodeBlockBorder: "90", mdQuoteBorder: "90", accent: "94", borderAccent: "95" };
const coloredTheme = {
  fg: (color: string, text: string) => `\u001b[${tokenColors[color] ?? "0"}m${text}\u001b[39m`,
  bold: (text: string) => `\u001b[1m${text}\u001b[22m`,
};
const coloredFactory = calls[0].factory as (tui: unknown, theme: unknown) => { render(width: number): string[]; invalidate(): void };
const coloredWidget = coloredFactory(tui, coloredTheme);
const coloredRow = coloredWidget.render(160)[0];
assert.ok(coloredRow.includes(`\u001b[1m\u001b[2mNew activity`), coloredRow);
assert.ok(!coloredRow.includes("**"), coloredRow);
coloredWidget.invalidate();
updateResearchWidget(token, "Reading `context-tools.ts`");
assert.ok(coloredWidget.render(160)[0].includes(`\u001b[36mcontext-tools.ts\u001b[39m`), coloredWidget.render(160)[0]);
// Pi hands the widget a live theme proxy: the row must read the theme on each
// render, so a theme switch recolors without a remount.
const liveTheme = { mdCode: "36" };
const proxyTheme = {
  fg: (color: string, text: string) => `\u001b[${color === "mdCode" ? liveTheme.mdCode : "2"}m${text}\u001b[39m`,
  bold: (text: string) => `\u001b[1m${text}\u001b[22m`,
};
const proxyWidget = coloredFactory(tui, proxyTheme);
assert.ok(proxyWidget.render(160)[0].includes(`\u001b[36mcontext-tools.ts\u001b[39m`), proxyWidget.render(160)[0]);
liveTheme.mdCode = "35";
assert.ok(proxyWidget.render(160)[0].includes(`\u001b[35mcontext-tools.ts\u001b[39m`), proxyWidget.render(160)[0]);
// Activity without visible width leaves an identity-only row instead of a
// dangling separator.
updateResearchWidget(token, "\u200b");
assert.equal(stripVTControlCharacters(proxyWidget.render(160)[0]).trimEnd(), " ⠋ researcher");

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
