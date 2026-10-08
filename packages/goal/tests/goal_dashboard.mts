/** The status row and the elapsed figure it reports. */

import { observedAssert as assert, observeScenario, observedScenarios } from "../../../tests/e2e/support/assertion-observer.ts";
import { writeFileSync as writeObservationFile } from "node:fs";
import { clearDashboard, refreshDashboard } from "../src/dashboard.ts";
import { formatElapsed, type GoalRecord } from "../src/record.ts";

const results: string[] = [];
async function scenario(name: string, body: () => Promise<void> | void): Promise<void> {
  try {
    await observeScenario(name, body);
    results.push(`ok ${name}`);
  } catch (error) {
    results.push(`FAIL ${name}: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}


await scenario("elapsed time is the progress the surface reports", async () => {
  // A goal is not partway through a list, so there is no fraction to show. Time
  // is the one figure that is both honest and useful, and it scales with the run.
  const cases: [number, string][] = [
    [0, "0m"], [45, "0m"], [59, "0m"], [60, "1m"],
    [3_599, "59m"], [3_600, "1h 0m"], [3_725, "1h 2m"], [5_400, "1h 30m"],
    [86_399, "23h 59m"], [86_400, "1d 0h"], [90_000, "1d 1h"], [176_400, "2d 1h"],
  ];
  for (const [seconds, expected] of cases) {
    assert.equal(formatElapsed(seconds), expected, `${seconds}s should read as ${expected}`);
  }
});
function goalWith(extra: Partial<GoalRecord> = {}): GoalRecord {
  return {
    id: "goal_test",
    objective: "Export the reports page as CSV.",
    status: "active",
    autoContinue: true,
    usage: { tokensUsed: 0, activeSeconds: 0 },
    createdAt: new Date(0).toISOString(),
    updatedAt: new Date(0).toISOString(),
    revision: 0,
    ...extra,
  };
}

await scenario("the status row never carries the goal tag", () => {
  const theme = { fg: (_: string, text: string) => text, bg: (_: string, text: string) => text, bold: (text: string) => text };
  const row = (goal: GoalRecord): string => {
    let lines: string[] = [];
    const ctx = { mode: "tui", ui: { setWidget: (_key: string, factory: Function | undefined) => {
      if (!factory) return;
      lines = factory({ requestRender() {} }, theme).render(120);
    } } };
    refreshDashboard({ goal, scheduler: {isRunning:()=>goal.status === "active" && goal.autoContinue,isArmed:()=>false}, checkProgress: undefined } as never, ctx as never);
    return lines.join("\n");
  };
  // No state tags the row. Every verb already names the goal, so the tag would
  // repeat it on every line below the editor. The transcript rows keep the tag,
  // because there it says which work belongs to the goal.
  const cases: [GoalRecord, string][] = [
    [goalWith(), "Pursuing goal"],
    [goalWith({ autoContinue: false }), "Goal waiting"],
    [goalWith({ status: "paused", autoContinue: false }), "Goal paused"],
    [goalWith({ status: "blocked", autoContinue: false }), "Goal blocked"],
    [goalWith({ status: "budget_limited", autoContinue: false }), "Goal budget limited"],
  ];
  for (const [goal, expected] of cases) {
    const text = row(goal);
    assert.match(text, new RegExp(expected), `${expected} expected in: ${text}`);
    assert.doesNotMatch(text, /\[goal\]/, `no state tags the status row: ${text}`);
    assert.doesNotMatch(text, /goal_[a-z0-9]/, "the internal goal id must not be shown: " + text);
    for (const glyph of ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏", "○", "✓", "✗"]) {
      assert.ok(!text.includes(glyph), `the row must not carry the marker ${glyph}: ${text}`);
    }
  }
  // The check replaces the goal status with a two-line, passive activity row.
  let checking: string[] = [];
  const ctx = { mode: "tui", ui: { setWidget: (_key: string, factory: Function | undefined) => {
    if (!factory) return;
    checking = factory({ requestRender() {} }, theme).render(120);
  } } };
  refreshDashboard({ goal: goalWith(), checkProgress: { label: "[goal] checking...", detail: "Evaluating the objective and recorded evidence..." } } as never, ctx as never);
  assert.match(checking[0] ?? "", /\[goal\] checking\.\.\./, `the check row has its lifecycle label: ${checking}`);
  assert.match(checking.join("\n"), /Evaluating the objective and recorded evidence\.\.\./, `the neutral activity text appears beneath the title: ${checking}`);
  assert.doesNotMatch(checking.join("\n"), /NOT MET|MET|private checker output/, `the checker result is not exposed while in flight: ${checking}`);
});

await scenario("the shared passive widget mounts below the editor and starts at zero minutes", () => {
  let placement: string | undefined;
  let lines: string[] = [];
  const theme = { fg: (_: string, text: string) => text, bg: (_: string, text: string) => text, bold: (text: string) => text };
  const ctx = { mode: "tui", ui: { setWidget: (_key: string, factory: Function | undefined, options?: { placement?: string }) => {
    if (!factory) return;
    placement = options?.placement;
    const component = factory({ requestRender() {} }, theme);
    lines = component.render(120);
  } } };
  const core = { goal: goalWith({ usage: { tokensUsed: 0, activeSeconds: 45 } }) };
  try {
    refreshDashboard(core as never, ctx as never);
    assert.equal(placement, "belowEditor");
    assert.ok(lines.every(line => !/^\s/.test(line)), "status rows align with the native footer without indentation");
    assert.match(lines.join("\n"), /0m/);
    assert.ok(!lines.join("\n").includes("45s"));
  } finally { clearDashboard(ctx as never); }
});

await scenario("status refresh reuses the widget and still reads fresh state", () => {
  let mounts = 0, renders = 0;
  let component: { render(width: number): string[] } | undefined;
  const core = { goal: goalWith() };
  const ctx = { mode: "tui", ui: { setWidget: (_key: string, factory: Function | undefined) => {
    mounts++;
    if (factory) component = factory({ requestRender() { renders++; } });
  } } };
  refreshDashboard(core as never, ctx as never);
  refreshDashboard(core as never, ctx as never);
  assert.equal(mounts, 1);
  assert.equal(renders, 1);
  core.goal = goalWith({ status: "paused", autoContinue: false });
  refreshDashboard(core as never, ctx as never);
  assert.equal(mounts, 1);
  assert.match(component!.render(80).join("\n"), /Goal paused/);
  clearDashboard(ctx as never);
  refreshDashboard(core as never, ctx as never);
  assert.equal(mounts, 3, "clearing resets the mount cache");
});

await scenario("narrow status widgets wrap instead of dropping their ending", () => {
  let component: { render(width: number): string[] } | undefined;
  const ctx = { mode: "tui", ui: { setWidget: (_key: string, factory: Function | undefined) => {
    if (factory) component = factory({ requestRender() {} });
  } } };
  refreshDashboard({ goal: goalWith({ status: "budget_limited" }) } as never, ctx as never);
  const text = component!.render(10).join("\n");
  assert.equal(text.replace(/\s/g, ""), "Goalbudgetlimited·0m");
  assert.doesNotMatch(text, /…/);
});

process.stdout.write(`${JSON.stringify(results)}\n`);

if (process.env.PI_E2E_ASSERTION_PATH) writeObservationFile(process.env.PI_E2E_ASSERTION_PATH, JSON.stringify(observedScenarios()));
