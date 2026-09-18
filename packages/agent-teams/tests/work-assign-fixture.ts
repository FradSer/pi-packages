import assert from "node:assert/strict";
import childProcess from "node:child_process";
import { EventEmitter } from "node:events";
import { syncBuiltinESMExports } from "node:module";
import { PassThrough, Writable } from "node:stream";
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

const { spawnResident } = await import("../src/spawner.ts");
const { registerLeaderTools } = await import("../src/tools.ts");
const { initTeamMachine, shutdownTeamMachine } = await import("../src/team-machine.ts");
const { registerSessionAgent } = await import("../src/agents.ts");
const { getState, registerTeammate, resetState } = await import("../src/state.ts");
const { WorkToolParams } = await import("../src/types.ts");
const { readRoster, rosterPath, stateFilePath } = await import("../src/statefile.ts");

const root = process.env.PI_TEST_DIR;
assert.ok(root, "PI_TEST_DIR is required");
resetState();
initTeamMachine({ sessionManager: undefined, cwd: root }, { sendUpdate() {}, notifyChange() {} });
registerSessionAgent({ name: "reviewer", description: "Review", prompt: "Review thoroughly", tools: [] });

const tools = new Map();
registerLeaderTools({ registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools: () => [], setActiveTools() {} });
const work = tools.get("work");
assert.ok(work, "work must be registered");
const assignSchema = work.parameters.anyOf.find((variant) => variant.properties.action.const === "assign");
assert.equal(Value.Check(WorkToolParams, { action: "assign", id: "work", target: { session: "session:resident:s1" } }), true);
assert.equal(Value.Check(WorkToolParams, { action: "assign", id: "work", target: { agent: "reviewer" } }), false);

const create = await work.execute("create", { action: "create", subject: "Fix storage", resources: ["firmware/storage"] }, undefined, undefined, { cwd: root });
const workId = create.details.work.id;
spawnResident({ workerName: "resident", onUpdate() {}, onExit() {} });
registerTeammate({ name: "resident", agent: "reviewer", spawnId: "s1", pid: 1, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 });

const assigned = await work.execute("assign", { action: "assign", id: workId, target: { session: "session:resident:s1" } }, undefined, undefined, { cwd: root });
assert.equal(assigned.details.action, "assign");
assert.equal(assigned.details.outcome, "assigned");
assert.equal(assigned.details.work.id, workId);
assert.equal(assigned.details.work.state, "claimed");
assert.equal(assigned.details.work.claimedBy, "resident");
assert.deepEqual(getState().teammates.resident.assignment?.resources, ["firmware/storage"]);
assert.equal(getState().teammates.resident.currentTaskId, workId);
const published = readRoster(rosterPath(stateFilePath(undefined, root))).find((entry) => entry.name === "resident");
assert.equal(published?.assignment?.id, assigned.details.assignment.id, "Assignment binding must be published before the new session can read its prompt");
assert.equal(published?.currentTaskId, workId);
child.stdout.write(JSON.stringify({ type: "agent_settled" }) + "\n");
await new Promise((resolve) => setImmediate(resolve));
const reset = commands.find((command) => command.type === "new_session");
assert.ok(reset, "assignment must request a fresh Pi session");
child.stdout.write(JSON.stringify({ id: reset.id, type: "response", command: "new_session", success: true, data: { cancelled: false } }) + "\n");
await new Promise((resolve) => setImmediate(resolve));
assert.ok(commands.some((command) => command.type === "prompt" && command.message?.includes("Fix storage")));

const second = await work.execute("create", { action: "create", subject: "Conflicting work", resources: ["firmware/storage/cache"] }, undefined, undefined, { cwd: root });
registerTeammate({ name: "other", agent: "reviewer", spawnId: "s2", pid: 2, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 });
spawnResident({ workerName: "other", onUpdate() {}, onExit() {} });
await assert.rejects(
  work.execute("conflict", { action: "assign", id: second.details.work.id, target: { session: "session:other:s2" } }, undefined, undefined, { cwd: root }),
  /conflicts with active Work resources/i,
);
assert.equal(getState().tasks[second.details.work.id]?.status, "pending");


shutdownTeamMachine();
child.emit("close", 0, null);
mock.restoreAll();
console.log("WORK_ASSIGN_OK");
