import assert from "node:assert/strict";
import { Value } from "typebox/value";
import { registerLeaderTools } from "../src/tools.ts";
import { initTeamMachine, shutdownTeamMachine } from "../src/team-machine.ts";
import { createTask, getState, resetState } from "../src/state.ts";
import { WorkToolParams } from "../src/types.ts";

const root = process.env.PI_TEST_DIR;
assert.ok(root, "PI_TEST_DIR is required");
resetState();
initTeamMachine({ sessionManager: undefined, cwd: root }, { sendUpdate() {}, notifyChange() {} });
const tools = new Map();
registerLeaderTools({ registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools: () => [], setActiveTools() {} });
const work = tools.get("work");
assert.ok(work, "work must be registered");
assert.equal(Value.Check(WorkToolParams, { action: "reopen", id: "completed", reason: "Needs another pass" }), true);
assert.equal(Value.Check(WorkToolParams, { action: "reopen", id: "completed", target: { session: "session:worker" } }), false);

const completed = createTask({ subject: "Completed work", resources: ["firmware/storage"] }).task;
Object.assign(getState().tasks[completed.id], { status: "completed", result: "old evidence", errorMessage: "old error", completedAt: 1, deferredMessages: [{ from: "peer", subject: "later", body: "later", timestamp: 1 }] });
const reopened = await work.execute("reopen", { action: "reopen", id: completed.id, reason: "Review changed" });
assert.equal(reopened.details.action, "reopen");
assert.equal(reopened.details.outcome, "reopened");
assert.equal(getState().tasks[completed.id]?.status, "pending");
assert.equal(getState().tasks[completed.id]?.result, undefined);
assert.equal(getState().tasks[completed.id]?.errorMessage, undefined);
assert.equal(getState().tasks[completed.id]?.completedAt, undefined);
assert.equal(getState().tasks[completed.id]?.deferredMessages, undefined);

const activeDependent = createTask({ subject: "Active dependent", dependsOn: [completed.id] }).task;
getState().tasks[activeDependent.id].status = "claimed";
await assert.rejects(work.execute("blocked", { action: "reopen", id: completed.id, reason: "again" }), /not completed/i);
getState().tasks[completed.id].status = "completed";
await assert.rejects(work.execute("dependent", { action: "reopen", id: completed.id, reason: "blocked" }), /active dependent Work/i);
assert.equal(getState().tasks[completed.id]?.status, "completed");
assert.equal(getState().tasks[activeDependent.id]?.status, "claimed");

const pending = createTask({ subject: "Pending work" }).task;
await assert.rejects(work.execute("pending", { action: "reopen", id: pending.id, reason: "not terminal" }), /not completed/i);
const superseded = createTask({ subject: "Superseded work" }).task;
getState().tasks[superseded.id].status = "superseded";
await assert.rejects(work.execute("superseded", { action: "reopen", id: superseded.id, reason: "not terminal" }), /not completed/i);

shutdownTeamMachine();
console.log("WORK_REOPEN_OK");
