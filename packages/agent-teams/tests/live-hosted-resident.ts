/** Drive the shipping host and public tool against one real RPC child. */
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import path from "node:path";
import { SessionManager } from "@earendil-works/pi-coding-agent";
import { executeChildIntent, type LeaderReport } from "@fradser/pi-subagents";
import { publishAgentHost } from "../src/agent-host.ts";
import { getAgent, resetState } from "../src/state.ts";
import { initTeamMachine, shutdownTeamMachine, teardownAgents } from "../src/team-machine.ts";

const root = process.env.PI_TEST_DIR!;
const config = process.env.PI_CODING_AGENT_DIR!;
const model = process.env.PI_TEST_MODEL!;
const mode = process.env.PI_TEST_MODE ?? "two-inputs";
assert.ok(root && config && model);
assert.ok(path.resolve(config).startsWith(path.resolve(root) + path.sep));
const reports: LeaderReport[] = [];
let waiter: ((report: LeaderReport) => void) | undefined;
const nextReport = () => new Promise<LeaderReport>(resolve => { waiter = resolve; });
const sessionManager = SessionManager.inMemory(root);
initTeamMachine({ cwd: root, sessionManager } as never, { notifyChange() {}, sendUpdate(report) {
  if (!report.finished) return;
  reports.push(report);
  waiter?.(report);
  waiter = undefined;
} });
publishAgentHost(sessionManager);
const timer = setTimeout(() => { throw new Error("Hosted native probe timed out"); }, 30_000);
try {
  const first = nextReport();
  const started = await executeChildIntent({ operation: "start", name: "hosted", model, tools: ["read"],
    description: "Native hosted probe", role_prompt: "PINNED_HOSTED_ROLE. Return the requested evidence without tools.",
    prompt: mode === "interrupt" ? "First input; wait for steering" : "First input" }, { cwd: root });
  assert.equal(started.details.ok, true, started.content[0].text);
  const session = String(started.details.session);
  const agent = getAgent("hosted")!;
  const pid = agent.pid;
  const spawnId = agent.spawnId;
  const firstAttempt = agent.assignment!.id;
  if (mode === "interrupt") {
    // The loopback server holds response bytes, but native prompt acceptance is
    // independently acknowledged. Steer therefore addresses an active sequence.
    const response = await fetch(process.env.PI_TEST_MODEL_CONTROL! + "/started");
    assert.equal(response.ok, true);
    assert.equal(agent.status, "working");
    const steered = await executeChildIntent({ operation: "input", delivery: "steer", session, prompt: "Keep the same sequence; return steered evidence" });
    assert.equal(steered.details.ok, true, steered.content[0].text);
    assert.equal(agent.assignment!.id, firstAttempt);
    assert.equal(agent.pid, pid);
    await fetch(process.env.PI_TEST_MODEL_CONTROL! + "/release", { method: "POST" });
    const result = await first;
    assert.equal(result.spawnId, spawnId);
    assert.equal(result.assignmentId, firstAttempt);
    assert.equal(result.body, "LIVE_TEAM_DATA_OK");
    assert.equal(reports.length, 1);
  } else {
    assert.equal((await first).body, "LIVE_TEAM_DATA_OK");
    assert.equal(agent.status, "idle");
    const second = nextReport();
    const sent = await executeChildIntent({ operation: "input", delivery: "next", session, prompt: "Second input" });
    assert.equal(sent.details.ok, true, sent.content[0].text);
    const result = await second;
    assert.equal(result.body, "LIVE_TEAM_DATA_OK");
    assert.notEqual(result.assignmentId, firstAttempt);
    assert.equal(result.spawnId, spawnId);
    assert.equal(agent.pid, pid, "send never replaces the process");
    assert.equal(sent.details.session, session);
    assert.equal(reports.length, 2, "one report for each settled input");
  }
  assert.equal(agent.status, "idle");
  const idleInterrupt = await executeChildIntent({ operation: "input", delivery: "steer", session, prompt: "No active sequence" });
  assert.equal(idleInterrupt.details.ok, false);
  const stopped = await executeChildIntent({ operation: "stop", session });
  assert.equal(stopped.details.ok, true, stopped.content[0].text);
  assert.equal(agent.status, "stopped");
  assert.equal((await executeChildIntent({ operation: "input", delivery: "next", session, prompt: "Closed" })).details.ok, false);
  assert.ok(!existsSync(path.join(config, "agents", "hosted")));
  console.log(JSON.stringify({ ok: true, mode, reports: reports.length, sameProcess: true, temporaryData: false }));
} finally {
  clearTimeout(timer);
  await teardownAgents();
  shutdownTeamMachine();
  resetState();
}
