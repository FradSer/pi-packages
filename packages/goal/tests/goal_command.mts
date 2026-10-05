/**
 * The /goal command handler, driven directly through a minimal host double.
 *
 * It lives apart from goal_session.mts on purpose: that harness owns a real
 * session and its state is not safe to perturb mid-run. The busy-window contract
 * is a property of this handler, so it is pinned here.
 */
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readFileSync } from "node:fs";

import { registerGoalCommands } from "../src/commands.ts";
import type { GoalCore } from "../src/core.ts";
import type { GoalRecord } from "../src/record.ts";
import { GoalStore, newGoalId } from "../src/store.ts";
import { goalPromptPath } from "../src/paths.ts";

const root = mkdtempSync(join(tmpdir(), "goal-command-"));
const results: string[] = [];
async function scenario(name: string, body: () => Promise<void> | void): Promise<void> {
  try {
    await body();
    results.push(`ok ${name}`);
  } catch (error) {
    results.push(`FAIL ${name}: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}

/** Run the handler with `busy` deciding what `ctx` reports. */
async function runCommand(objective: string, status: GoalRecord["status"], busy: boolean): Promise<{
  notifications: string[];
  goal: GoalRecord | undefined;
  projectRoot: string;
  id: string;
}> {
  const store = new GoalStore({ projectRoot: root });
  const id = newGoalId();
  const created = store.create({ objective: "Export the reports page as CSV.", owner: "session-a", id });
  assert.ok(created.ok, created.ok ? "" : created.message);
  const armed = store.apply({
    expectedGoalId: id,
    mutate: (draft) => ({
      ...draft,
      status,
      autoContinue: status === "active",
      // Two refusals under the old requirement, and evidence from before it, so
      // a revision that does not reset them is visible.
      completionFailures: 2,
      evidenceSince: "2020-01-01T00:00:00.000Z",
      scheduler: draft.scheduler ? { ...draft.scheduler, phase: "running" } : undefined,
    }),
  });
  assert.ok(armed.ok, JSON.stringify(armed));
  const goal = store.readGoal(id);
  assert.ok(goal, "the goal is readable");

  let handler: ((args: string, ctx: unknown) => Promise<void>) | undefined;
  const notifications: string[] = [];
  const core = {
    pi: {
      registerCommand: (_name: string, spec: { handler: typeof handler }) => { handler = spec.handler; },
    },
    bindUi: () => {},
    cancelGoalActivation: () => {},
    abortCheck: () => {},
    goal,
    store,
  };
  registerGoalCommands(core as unknown as GoalCore);
  assert.ok(handler, "the /goal command is registered");
  await handler!(objective, {
    mode: "print",
    isIdle: () => !busy,
    hasPendingMessages: () => busy,
    ui: { notify: (line: string) => notifications.push(line) },
  });
  return { notifications, goal: store.readGoal(id), projectRoot: root, id };
}

await scenario("a /goal objective revises a goal that is being pursued", async () => {
  const outcome = await runCommand("Export as PDF instead, with one test per format.", "active", true);
  assert.match(
    outcome.goal?.objective ?? "",
    /PDF/,
    `the new objective must replace the old one: ${outcome.goal?.objective}`,
  );
  assert.ok(
    outcome.notifications.some((line) => line.includes("Goal updated")),
    `the user must be told it continued: ${JSON.stringify(outcome.notifications)}`,
  );
  assert.ok(
    !outcome.notifications.some((line) => line.includes("processing another request")),
    `work already under way must not be rejected: ${JSON.stringify(outcome.notifications)}`,
  );

  // A revision is three fields or none. Writing only the objective leaves the
  // prose, the evidence window and the refusal count describing the old
  // requirement, which is what the reviewer proved this path did.
  const prose = readFileSync(goalPromptPath(outcome.projectRoot, outcome.id), "utf-8");
  assert.match(prose, /PDF/, `prompt.md must carry the new objective: ${prose.slice(0, 120)}`);
  assert.notEqual(
    outcome.goal?.evidenceSince,
    "2020-01-01T00:00:00.000Z",
    "a revised requirement must exclude evidence collected under the old one",
  );
  assert.equal(outcome.goal?.completionFailures, 0, "a revised requirement must reset the refusal count");
});

await scenario("a /goal objective on a paused goal is still rejected while busy", async () => {
  const outcome = await runCommand("This must not silently rewrite a paused goal.", "paused", true);
  assert.match(
    outcome.goal?.objective ?? "",
    /CSV/,
    "a paused goal has no work running, so the command must not rewrite it",
  );
  assert.ok(
    outcome.notifications.some((line) => line.includes("processing another request")),
    `and it must say why: ${JSON.stringify(outcome.notifications)}`,
  );
});

rmSync(root, { recursive: true, force: true });
process.stdout.write(`${JSON.stringify(results)}\n`);