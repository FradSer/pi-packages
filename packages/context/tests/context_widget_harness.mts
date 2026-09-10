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

const token = startResearchWidget(ctx as never, "inspect auth flow");
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
assert.ok(plain.includes("[context] researching"), plain);
assert.ok(plain.includes("inspect auth flow"), plain);

updateResearchWidget(token, "bash: ls");
assert.ok(renders > 0);
assert.ok(stripVTControlCharacters(widget.render(80)[0]).includes("bash: ls"));

updateResearchWidget(token + 999, "stale detail");
assert.ok(!stripVTControlCharacters(widget.render(80)[0]).includes("stale detail"));
clearResearchWidget(ctx as never, token + 999);
assert.deepEqual(cleared, []);

clearResearchWidget(ctx as never, token);
assert.deepEqual(cleared, ["context-research"]);
assert.deepEqual(widget.render(80), []);

const before = calls.length;
const printToken = startResearchWidget({ mode: "print", ui } as never, "background query");
assert.equal(calls.length, before);
clearResearchWidget({ mode: "print", ui } as never, printToken);

console.log("Context widget passed: aboveEditor placement, live activity, stale-token guard, clear, non-tui guard.");
