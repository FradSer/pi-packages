import assert from "node:assert/strict";
import { stripVTControlCharacters } from "node:util";
import {
  clearResearchWidget,
  startResearchWidget,
  updateResearchWidget,
} from "../extensions/context-tools.ts";

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

const token = startResearchWidget(ctx as never, "context-a1b2c3d4e5f6");
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
assert.ok(plain.includes("@context-a1b2c3d4e5f6"), plain);
assert.ok(plain.includes("Working..."), plain);
assert.ok(!plain.includes("inspect auth flow"), plain);

updateResearchWidget(token, "Inspecting auth flow");
assert.ok(renders > 0);
assert.ok(stripVTControlCharacters(widget.render(80)[0]).includes("Inspecting auth flow"));

updateResearchWidget(token, "bash: ls");
const latest = stripVTControlCharacters(widget.render(80)[0]);
assert.ok(latest.includes("bash: ls"), latest);
assert.ok(!latest.includes("Inspecting auth flow"), latest);

updateResearchWidget(token + 999, "stale detail");
assert.ok(!stripVTControlCharacters(widget.render(80)[0]).includes("stale detail"));
clearResearchWidget(ctx as never, token + 999);
assert.deepEqual(cleared, []);

clearResearchWidget(ctx as never, token);
assert.deepEqual(cleared, ["context-research"]);
assert.deepEqual(widget.render(80), []);

const before = calls.length;
const printToken = startResearchWidget({ mode: "print", ui } as never, "context-print");
assert.equal(calls.length, before);
clearResearchWidget({ mode: "print", ui } as never, printToken);

console.log("Context widget passed: unique @context identity, latest live activity, stale-token guard, clear, non-tui guard.");
