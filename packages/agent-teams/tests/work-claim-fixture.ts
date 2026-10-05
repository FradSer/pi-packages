import assert from "node:assert/strict";
import childProcess from "node:child_process";
import { EventEmitter } from "node:events";
import fs from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import { PassThrough, Writable } from "node:stream";
import path from "node:path";
import { mock } from "node:test";
import { Value } from "typebox/value";

const commands: Array<{ type: string; id?: string; message?: string }> = [];
const child = Object.assign(new EventEmitter(), {
  pid: 1,
  stdout: new PassThrough(),
  stderr: new PassThrough(),
  stdin: new Writable({ write(chunk, _encoding, done) { commands.push(JSON.parse(String(chunk))); done(); } }),
});
mock.method(childProcess, "spawn", () => child);
syncBuiltinESMExports();

const { spawnResident } = await import("@fradser/pi-subagents");
const { initTeamMachine, processTaskIntents, shutdownTeamMachine } = await import("../src/team-machine.ts");
const { createTask, getState, registerAgent, resetState } = await import("../src/state.ts");
const { registerChildCapabilities } = await import("../src/worker.ts");
const { inboxPath, rosterPath, stateFilePath, workerOutboxPath, writeRoster } = await import("../src/statefile.ts");
        const { tasksFilePath, claimsDir, submissionsDir, writeTasksFile } = await import("@fradser/pi-tasks");
const { WorkerWorkToolParams } = await import("../src/types.ts");

const root = process.env.PI_TEST_DIR;
assert.ok(root, "PI_TEST_DIR is required");
resetState();
initTeamMachine({ sessionManager: undefined, cwd: root }, { sendUpdate() {}, notifyChange() {} });
const stateFile = stateFilePath(undefined, root);
const tasksFile = tasksFilePath(undefined, root);
const tasksRoot = path.dirname(tasksFile);
fs.mkdirSync(claimsDir(tasksRoot), { recursive: true });
fs.mkdirSync(submissionsDir(tasksRoot), { recursive: true });
const agent = { name: "worker", role: "reviewer", spawnId: "s1", pid: 1, status: "idle" as const, createdAt: 1, updatedAt: 1 };
registerAgent(agent);
const task = createTask({ subject: "Claim storage", resources: ["firmware/storage"] }).task;
writeTasksFile(tasksFile, getState().tasks);
writeRoster(rosterPath(stateFile), [agent]);
spawnResident({ agentName: "worker", onUpdate() {}, onExit() {} });

Object.assign(process.env, {
  PI_TEAMMATE_WORKER_NAME: agent.name,
  PI_TEAMMATE_SPAWN_ID: agent.spawnId,
  PI_TEAMMATE_OUTBOX_FILE: workerOutboxPath(stateFile, agent.name, agent.spawnId),
  PI_TEAMMATE_INBOX_FILE: inboxPath(stateFile, agent.name),
  PI_TEAMMATE_ROSTER_FILE: rosterPath(stateFile),
  PI_TEAMMATE_TASKS_FILE: tasksFile,
  PI_TEAMMATE_CLAIMS_DIR: claimsDir(tasksRoot),
  PI_TEAMMATE_SUBMISSIONS_DIR: submissionsDir(tasksRoot),
});

const tools = new Map();
const disclosure = registerChildCapabilities({
  on(event, handler) {
    if (event === "message_start") tools.set("work_message", (message) => handler({ type: "message_start", message }, { isIdle: () => true }));
  },
  registerTool(tool) { tools.set(tool.name, tool); },
  getActiveTools: () => ["read", "work"],
  setActiveTools() {},
});
tools.set("work_disclosure", disclosure);
const work = tools.get("task");
assert.ok(work, "agent work must be registered");
assert.equal(Value.Check(WorkerWorkToolParams, { action: "claim", id: task.id }), true);
assert.equal(Value.Check(WorkerWorkToolParams, { action: "submit", outcome: "success", result: "done" }), true);
for (const invalid of [
  { action: "claim", taskId: task.id },
  { action: "claim", target: { session: "session:agent" } },
  { action: "submit", taskId: task.id, outcome: "success" },
  { action: "submit", status: "completed" },
  { action: "create", subject: "not agent work" },
]) assert.equal(Value.Check(WorkerWorkToolParams, invalid), false);

const queued = await work.execute("claim", { action: "claim", id: task.id });
assert.equal(queued.details.action, "claim");
assert.equal(queued.details.outcome, "queued");
assert.equal(getState().tasks[task.id]?.status, "pending");
assert.equal(getState().tasks[task.id]?.claimedBy, undefined);
processTaskIntents();
assert.equal(getState().tasks[task.id]?.status, "in_progress");
assert.equal(getState().tasks[task.id]?.claimedBy, agent.name);
child.stdout.write(JSON.stringify({ type: "agent_settled" }) + "\n");
await new Promise((resolve) => setImmediate(resolve));
const reset = commands.find((command) => command.type === "new_session");
assert.ok(reset, "claim acceptance must request a fresh Pi session");
child.stdout.write(JSON.stringify({ id: reset.id, type: "response", command: "new_session", success: true, data: { cancelled: false } }) + "\n");
await new Promise((resolve) => setImmediate(resolve));
assert.ok(commands.some((command) => command.type === "prompt" && command.message?.includes("Claim storage")));
const acceptedPrompt = commands.find((command) => command.type === "prompt" && command.message?.includes("Claim storage"))!.message!;
writeRoster(rosterPath(stateFile), [{ ...agent, status: "working", currentTaskId: task.id, assignment: getState().agents.worker.assignment }]);
tools.get("work_disclosure")?.update(acceptedPrompt);
await tools.get("work_message")?.({ role: "user", content: acceptedPrompt, timestamp: Date.now() });
const submitted = await work.execute("submit", { action: "submit", outcome: "success", result: "fixed" });
assert.equal(submitted.details.action, "submit");
assert.equal(submitted.details.outcome, "queued");
assert.equal(getState().tasks[task.id]?.status, "in_progress");
assert.equal(fs.readdirSync(submissionsDir(tasksRoot)).length, 1);

const directTask = createTask({ subject: "Direct owned Work" }).task;
getState().tasks[directTask.id].status = "in_progress";
getState().tasks[directTask.id].claimedBy = agent.name;
getState().agents.worker.assignment = { id: "direct:s1", kind: "direct", resources: [] };
getState().agents.worker.currentTaskId = directTask.id;
writeRoster(rosterPath(stateFile), [{ ...agent, status: "working", currentTaskId: directTask.id, assignment: getState().agents.worker.assignment }]);
const directPrompt = `[agent-teams-assignment:direct:s1]\nWork Item ${directTask.id}: ${directTask.subject}`;
tools.get("work_disclosure")?.update(directPrompt);
await tools.get("work_message")?.({ role: "user", content: directPrompt, timestamp: Date.now() + 10 });
const directSubmitted = await work.execute("direct-submit", { action: "submit", outcome: "failed", result: "direct failure" });
assert.equal(directSubmitted.details.action, "submit");
assert.equal(directSubmitted.details.outcome, "queued");
const markers = fs.readdirSync(submissionsDir(tasksRoot));
assert.equal(markers.length, 2);
const directMarker = JSON.parse(fs.readFileSync(path.join(submissionsDir(tasksRoot), `${encodeURIComponent(directTask.id)}.json`), "utf8"));
assert.deepEqual({ taskId: directMarker.taskId, status: directMarker.status, result: directMarker.result }, { taskId: directTask.id, status: "failed", result: "direct failure" });


shutdownTeamMachine();
child.emit("close", 0, null);
mock.restoreAll();
console.log("WORK_CLAIM_OK");
