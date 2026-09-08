import assert from "node:assert/strict";
import childProcess from "node:child_process";
import { EventEmitter } from "node:events";
import { mkdtempSync, rmSync } from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PassThrough, Writable } from "node:stream";
import { mock } from "node:test";

const launches: string[][] = [];
const children: Array<EventEmitter & { stdin: Writable; stdout: PassThrough; stderr: PassThrough; pid: number; commands: Array<{ message?: string }> }> = [];
mock.method(childProcess, "spawn", (_command, args) => {
  launches.push(args);
  const child = Object.assign(new EventEmitter(), {
    pid: 100 + children.length,
    stdin: new Writable(), stdout: new PassThrough(), stderr: new PassThrough(),
    commands: [] as Array<{ message?: string }>,
  });
  child.stdin = new Writable({ write(chunk, _encoding, done) { child.commands.push(JSON.parse(String(chunk))); done(); } });
  children.push(child);
  return child;
});
syncBuiltinESMExports();
const { SessionManager } = await import("@earendil-works/pi-coding-agent");
const { registerLeaderTools } = await import("../src/tools.ts");
const { registerSessionAgent, clearSessionAgents } = await import("../src/agents.ts");
const { resetState, getState } = await import("../src/state.ts");
const { initTeamMachine, shutdownTeamMachine, removeRuntimeDir, drainTeammateOutboxes, markTeammateFinished, hasAnnouncedFinish } = await import("../src/team-machine.ts");
const { appendWorkerEvent, stateFilePath, workerOutboxPath } = await import("../src/statefile.ts");
const cwd = mkdtempSync(join(tmpdir(), "independent-work-"));
const context = { cwd, mode: "print", hasUI: false, sessionManager: SessionManager.inMemory(cwd) };
const tools = new Map();
try {
  resetState();
  clearSessionAgents();
  const reports: Array<{ assignmentId?: string; finished?: boolean; teammate?: string; spawnId?: string }> = [];
  initTeamMachine(context, { sendUpdate(report) { reports.push(report); }, notifyChange() {} });
  registerSessionAgent({ name: "reviewer", description: "Audit", prompt: "Read only", tools: ["read"] });
  registerLeaderTools({ registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools() { return []; }, setActiveTools() {} });
  const call = (name, params) => tools.get(name).execute("call", params, undefined, undefined, context);
  const first = await call("agent", { name: "reviewer", prompt: "Audit authentication" });
  const second = await call("agent", { name: "reviewer", prompt: "Audit authorization" });
  assert.equal(children.length, 2, "Each prompt without work must create an independent Work Session");
  assert.notEqual(first.details.workId, second.details.workId);
  assert.notEqual(first.details.route, second.details.route);
  assert.match(children[0].commands[0].message ?? "", /Audit authentication/);
  assert.match(children[1].commands[0].message ?? "", /Audit authorization/);
  assert.equal(children[0].commands.length, 1, "New work must not steer an existing assignment");
  const presence = await call("agent", { name: "reviewer" });
  assert.equal(children.length, 2);
  assert.equal(presence.details.sessions.length, 2);
  assert.deepEqual(new Set(presence.details.sessions.map((session) => session.workId)), new Set([first.details.workId, second.details.workId]));
  await call("agent", { name: "reviewer", work: first.details.workId, prompt: "Include edge cases" });
  assert.equal(children[0].commands.length, 2);
  assert.equal(children[1].commands.length, 1);
  await assert.rejects(call("agent", { name: "another-agent", work: first.details.workId, prompt: "Wrong owner" }), /work/i);
  await assert.rejects(call("agent", { name: "reviewer", work: "missing", prompt: "Wrong work" }), /work/i);
  assert.equal(Object.keys(getState().teammates).length, 2);
  await assert.rejects(call("agent_event", { to: "reviewer", message: "Which audit?" }), /ambiguous.*route/i);
  const routed = await call("agent_event", { to: second.details.route, message: "Check the deny policy" });
  assert.equal(routed.details.outcome, "steered");
  assert.equal(children[0].commands.length, 2);
  assert.equal(children[1].commands.length, 2);
  assert.match(children[1].commands.at(-1)?.message ?? "", /Check the deny policy/);
  const worker = Object.values(getState().teammates).find((entry) => entry.workId === first.details.workId)!;
  const firstAttempt = worker.assignment.id;
  const outbox = workerOutboxPath(stateFilePath(undefined, cwd), worker.name, worker.spawnId);
  const terminal = (id, assignmentId) => appendWorkerEvent(outbox, {
    id, assignmentId, type: "message", worker: worker.name, spawnId: worker.spawnId, body: "Verified outcome", status: "completed",
  });
  terminal("first-result", firstAttempt);
  drainTeammateOutboxes();
  assert.equal(markTeammateFinished(reports.at(-1)), true);
  assert.equal(hasAnnouncedFinish(worker.name), true);
  const reopened = await call("agent", { name: "reviewer", work: first.details.workId, prompt: "Check another case" });
  assert.equal(reopened.details.workId, first.details.workId, "The Work Item handle remains stable across attempts");
  assert.notEqual(worker.assignment.id, firstAttempt);
  assert.equal(hasAnnouncedFinish(worker.name), false, "The new attempt cannot inherit a finished announcement");
  const reportCount = reports.length;
  terminal("stale-result", firstAttempt);
  drainTeammateOutboxes();
  assert.equal(reports.length, reportCount);
  assert.notEqual(worker.assignment.closed, true);
  terminal("second-result", worker.assignment.id);
  drainTeammateOutboxes();
  assert.equal(markTeammateFinished(reports.at(-1)), true, "Each new attempt must announce its own completion");
  assert.equal(markTeammateFinished(reports.at(-1)), false);
  const beforeFork = children.length;
  const reopenWorker = Object.values(getState().teammates).find((entry) => entry.workId === second.details.workId)!;
  const pendingOutbox = workerOutboxPath(stateFilePath(undefined, cwd), reopenWorker.name, reopenWorker.spawnId);
  for (let index = 0; index < 6; index++) appendWorkerEvent(pendingOutbox, {
    id: `backlog-${index}`, type: "message", assignmentId: reopenWorker.assignment.id,
    worker: reopenWorker.name, spawnId: reopenWorker.spawnId, body: "x".repeat(60000), status: "in_progress",
  });
  appendWorkerEvent(pendingOutbox, { id: "pending-terminal", type: "message", assignmentId: reopenWorker.assignment.id,
    worker: reopenWorker.name, spawnId: reopenWorker.spawnId, body: "Ready for next work", status: "completed" });
  const previousAttempt = reopenWorker.assignment.id;
  const immediateReopen = await call("agent", { name: "reviewer", work: second.details.workId, prompt: "Distinct next request" });
  assert.equal(immediateReopen.details.outcome, "steered", "Explicit work controls must drain pending terminal evidence before selecting reopen");
  assert.notEqual(reopenWorker.assignment.id, previousAttempt);
  for (const params of [
    { name: "reviewer", fork: true },
    { name: "reviewer", work: first.details.workId, prompt: "Cannot replace context", fork: true },
    { name: "reviewer", work: first.details.workId, prompt: "Cannot reset context", fork: false },
  ]) await assert.rejects(call("agent", params), /fork/i);
  assert.equal(children.length, beforeFork);
  await assert.rejects(tools.get("agent").execute("missing-context", { name: "reviewer", prompt: "Fork", fork: true }, undefined, undefined, { cwd }), /context unavailable/i);
  assert.equal(children.length, beforeFork);
  assert.equal(tools.get("agent").parameters.properties.fork.type, "boolean");
  context.sessionManager.appendMessage({ role: "user", content: "Parent-only investigation marker", timestamp: 1 });
  const parentBefore = JSON.stringify(context.sessionManager.getEntries());
  const forked = await call("agent", { name: "reviewer", prompt: "Use the investigation", fork: true });
  assert.equal(children.length, beforeFork + 1);
  assert.equal(forked.details.context, "fork");
  const args = launches.at(-1);
  assert.ok(args.includes("--session"), "Fork launches against an independent seeded session");
  const forkFile = args[args.indexOf("--session") + 1];
  const forkContext = SessionManager.open(forkFile).buildSessionContext();
  assert.ok(JSON.stringify(forkContext.messages).includes("Parent-only investigation marker"));
  assert.equal(JSON.stringify(context.sessionManager.getEntries()), parentBefore);
  assert.equal(first.details.context, "fresh");
  assert.ok(launches[0].includes("--no-session"));
  await call("teammate_spawn", { name: "reviewer", agent: "reviewer", prompt: "Independent resident task" });
  await assert.rejects(call("agent_event", { to: "reviewer", message: "Ambiguous mixed roster" }), /ambiguous.*session:reviewer/i);
  const exactResident = await call("agent_event", { to: "session:reviewer", message: "Resident only" });
  assert.equal(exactResident.details.outcome, "steered");
  assert.match(children.at(-1).commands.at(-1).message, /Resident only/);
  assert.equal(first.details.route.startsWith("session:"), true);
  await assert.rejects(call("send_message", { to: "reviewer", message: "Ambiguous legacy message" }), /ambiguous/i);
  const residentMessage = await call("send_message", { to: "session:reviewer", message: "Precise legacy message" });
  assert.equal(residentMessage.details.outcome, "steered");
  const residentPresence = await call("agent", { name: "reviewer" });
  const residentWork = residentPresence.details.sessions.find((entry) => entry.route === "session:reviewer").workId;
  const resident = getState().teammates.reviewer;
  appendWorkerEvent(workerOutboxPath(stateFilePath(undefined, cwd), resident.name, resident.spawnId), {
    id: "resident-terminal", type: "message", assignmentId: resident.assignment.id,
    worker: resident.name, spawnId: resident.spawnId, body: "Resident complete", status: "completed",
  });
  const residentReopen = await call("agent", { name: "reviewer", work: residentWork, prompt: "Next resident attempt" });
  assert.equal(residentReopen.details.workId, residentWork, "Resident-origin work handles must stay stable across reopen");
  await call("agent", { name: "reviewer", work: residentWork, prompt: "Further guidance" });
  const residentOutbox = workerOutboxPath(stateFilePath(undefined, cwd), resident.name, resident.spawnId);
  for (let index = 0; index < 6; index++) appendWorkerEvent(residentOutbox, {
    id: `settled-backlog-${index}`, type: "message", assignmentId: resident.assignment.id,
    worker: resident.name, spawnId: resident.spawnId, body: "x".repeat(60000), status: "in_progress",
  });
  appendWorkerEvent(residentOutbox, { id: "settled-terminal", type: "message", assignmentId: resident.assignment.id,
    worker: resident.name, spawnId: resident.spawnId, body: "Automatic settled result", status: "completed" });
  children.at(-1).stdout.write(JSON.stringify({ type: "agent_settled" }) + "\n");
  assert.equal(resident.assignment.closed, true, "Settlement must apply all already-written final evidence before reminder logic");
  console.log("INDEPENDENT_WORK_OK");
} finally {
  for (const child of children) child.emit("close", 0, null);
  await new Promise((resolve) => setImmediate(resolve));
  shutdownTeamMachine();
  removeRuntimeDir(context);
  clearSessionAgents();
  resetState();
  mock.restoreAll();
  syncBuiltinESMExports();
  rmSync(cwd, { recursive: true, force: true });
}
