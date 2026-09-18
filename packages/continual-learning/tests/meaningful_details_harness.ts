/** Registration-only renderer fixtures: no event hooks, tools or model calls run. */
import assert from "node:assert/strict";
import { stripVTControlCharacters } from "node:util";
import { initTheme, type EntryRenderer, type ExtensionAPI, type Theme } from "@earendil-works/pi-coding-agent";
import { visibleWidth } from "@earendil-works/pi-tui";
import registerGuardrails from "../extensions/guardrails.ts";
import registerOutputChecks, { type CheckStatus } from "../extensions/output-checks.ts";
import registerContextGuidance from "../extensions/context-guidance.ts";

initTheme("dark");
const renderers = new Map<string, EntryRenderer>();
// Partial registration-only fake: the factories must not use runtime APIs here.
const pi = {
  on() {},
  registerCommand() {},
  registerEntryRenderer: (name: string, renderer: EntryRenderer) => renderers.set(name, renderer),
} as unknown as ExtensionAPI;
registerGuardrails(pi);
registerOutputChecks(pi);
registerContextGuidance(pi);
const theme = {
  fg: (_color: string, text: string) => text,
  bg: (_color: string, text: string) => text,
  bold: (text: string) => text,
} as Theme;

const policy = {
  kind: "policy-matched",
  policy: "protect-report",
  action: "block",
  tool: "write",
  reason: "Preserve the approved report.",
  outcome: "blocked by rule",
  source: "project.local",
  file: "/fixture/.pi/harness.local.json",
};
const check = {
  kind: "harness-check",
  phase: "artifact",
  status: "violated",
  detail: "The final artifact contains a prohibited value.",
  policy: "artifact-evidence",
  path: "reports/final.txt",
};
const guidance = {
  kind: "skill-rule",
  skill: "review",
  ruleId: "review-checklist",
  source: "project",
  file: "/fixture/.pi/harness.json",
  prompt: "Apply review guidance only to the selected task.\nRetain every approval reference.",
};
const longReason = "Preserve the approved report while checking every documented release constraint and retaining the original evidence. Final reason marker.";
const longPrompt = Array.from({ length: 65 }, (_, index) =>
  `guidance-${String(index + 1).padStart(3, "0")} Keep the independently meaningful evidence for this exact task.`,
).join("\n");
const fixtures: Array<{ name: string; customType: string; data: unknown }> = [
  { name: "policy-blocked", customType: "harness-event", data: policy },
  { name: "policy-allowed", customType: "harness-event", data: { ...policy, action: "confirm", outcome: "allowed once" } },
  { name: "policy-observed", customType: "harness-event", data: { ...policy, action: "observe", outcome: "observed" } },
  { name: "policy-long", customType: "harness-event", data: { ...policy, reason: longReason } },
  ...(["checked", "observed", "violated", "unsupported", "repair-exhausted"] satisfies CheckStatus[]).map((status) => ({
    name: `check-${status}`, customType: "harness-check", data: { ...check, status },
  })),
  { name: "check-output", customType: "harness-check", data: { ...check, phase: "output", path: undefined } },
  { name: "check-long", customType: "harness-check", data: { ...check, detail: longReason } },
  { name: "skill-rule", customType: "context-guidance-event", data: guidance },
  { name: "skill-prompt", customType: "context-guidance-event", data: { ...guidance, kind: "skill-prompt", ruleId: undefined, target: "system" } },
  { name: "text-rule", customType: "context-guidance-event", data: { ...guidance, kind: "text-rule", skill: undefined, ruleId: "project-a-guidance" } },
  { name: "text-incomplete", customType: "context-guidance-event", data: { ...guidance, kind: "text-incomplete", skill: undefined, ruleId: undefined } },
  { name: "guidance-long", customType: "context-guidance-event", data: { ...guidance, skill: "review-with-the-complete-applicable-release-checklist-and-approval-evidence" } },
  { name: "guidance-full-prompt", customType: "context-guidance-event", data: { ...guidance, prompt: longPrompt } },
];
const output = Object.fromEntries(fixtures.map(({ name, customType, data }) => {
  const renderer = renderers.get(customType);
  assert.ok(renderer, `${customType} entry renderer was registered`);
  const entry = { type: "custom" as const, id: "display-fixture", parentId: null, timestamp: "2026-01-01T00:00:00.000Z", customType, data };
  const before = JSON.stringify(entry);
  const views = Object.fromEntries([240, 48].map((width) => {
    const states = Object.fromEntries([false, true].map((expanded) => {
      const component = renderer(entry, { expanded }, theme);
      assert.ok(component, `${customType} returned a component`);
      const raw = component.render(width);
      assert.ok(raw.every((line) => visibleWidth(line) <= width), `${name} exceeds ${width} columns`);
      return [expanded ? "expanded" : "collapsed", raw.map((line) => stripVTControlCharacters(line).trim()).filter(Boolean)];
    }));
    return [String(width), states];
  }));
  assert.equal(JSON.stringify(entry), before, `${name} renderer mutated the stored entry`);
  return [name, { data, views }];
}));
console.log(JSON.stringify(output));
