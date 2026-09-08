import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { LeaderReport } from "../src/leader-reports.ts";
import { getState, getTeammate, resetState } from "../src/state.ts";
import { initTeamMachine, sendLeaderMessage, shutdownTeamMachine, shutdownTeammate, spawnTeammate } from "../src/team-machine.ts";

const provider = process.env.PI_PROVIDER;
const model = process.env.PI_MODEL;
assert.ok(provider && model, "Explicit PI_PROVIDER and PI_MODEL are required for this opt-in live test.");
const cwd = mkdtempSync(join(tmpdir(), "pi-live-reopen-"));
const name = "live-reopen-worker";
const tokens = ["FIRST_ASSIGNMENT_CONFIRMED", "SECOND_ASSIGNMENT_CONFIRMED"];
const assignmentIds: string[] = [];
let spawnId: string | undefined;
let accepted = 0;
const completed = Promise.withResolvers<void>();
const budget = setTimeout(() => completed.reject(new Error(`Live reopen test budget exceeded after ${accepted} accepted reports.`)), 120_000);
const prompt = (token: string) => `Your entire assignment: call send_message exactly once with to="leader", message="${token}", status="completed". Do not use any other tool or add prose. Then wait for explicit new assignment.`;

function onReport(report: LeaderReport): void {
  if (report.origin === "harness" || report.teammate !== name) return;
  try {
    assert.equal(report.status, "completed", "Expected a completed worker report");
    assert.equal(report.body.trim(), tokens[accepted]);
    assert.equal(report.spawnId, spawnId);
    const event = getState().leaderMailbox.find((item) => item.id === report.eventId);
    assert.ok(event?.assignmentId, "Accepted report must retain its assignment binding");
    assert.equal(event.assignmentId, assignmentIds[accepted]);
    accepted++;
    if (accepted === 2) {
      assert.notEqual(assignmentIds[0], assignmentIds[1]);
      completed.resolve();
      return;
    }
    const reopened = sendLeaderMessage(name, prompt(tokens[1]), { reopen: true });
    assert.ok(reopened.ok, "Runtime must accept explicit direct reopen");
    const secondId = getTeammate(name)?.assignment?.id;
    assert.ok(secondId);
    assignmentIds.push(secondId);
  } catch (error) {
    completed.reject(error);
  }
}

try {
  resetState();
  initTeamMachine({ cwd, sessionManager: { getSessionFile: () => join(cwd, "leader.jsonl") }, model: undefined, thinkingLevel: undefined }, { sendUpdate: onReport, notifyChange() {} });
  const started = spawnTeammate({ name, agent: name, model: `${provider}/${model}`, prompt: prompt(tokens[0]),
    definition: { description: "Live report-only lifecycle verification", tools: [], prompt: "Follow the exact report instruction for each explicit assignment. Use send_message to report completed and wait for a new assignment." },
  });
  assert.ok(started.ok, "Live resident must start");
  spawnId = started.teammate.spawnId;
  assert.ok(started.teammate.assignment?.id);
  assignmentIds.push(started.teammate.assignment.id);
  await completed.promise;
  console.log(JSON.stringify({ result: "LIVE_AGENT_REOPEN_OK", acceptedReports: accepted, distinctAssignments: assignmentIds[0] !== assignmentIds[1] }));
} finally {
  clearTimeout(budget);
  await shutdownTeammate(name);
  shutdownTeamMachine();
  resetState();
  rmSync(cwd, { recursive: true, force: true });
}
