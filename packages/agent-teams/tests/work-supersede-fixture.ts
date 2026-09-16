import assert from "node:assert/strict";
import { registerLeaderTools } from "../src/tools.ts";
import { initTeamMachine, shutdownTeamMachine } from "../src/team-machine.ts";
import { createTask, getState, resetState } from "../src/state.ts";

const root = process.env.PI_TEST_DIR;
assert.ok(root, "PI_TEST_DIR is required");
resetState();
initTeamMachine({ sessionManager: undefined, cwd: root }, { sendUpdate() {}, notifyChange() {} });
const tools = new Map();
registerLeaderTools({ registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools: () => [], setActiveTools() {} });
const work = tools.get("work");
assert.ok(work, "work must be registered");

const original = createTask({ subject: "Original Work", resources: ["firmware/storage"] }).task;
const dependent = createTask({ subject: "Dependent Work", dependsOn: [original.id] }).task;
const replacement = await work.execute("supersede", {
  action: "supersede",
  subject: "Replacement Work",
  description: "Replacement implementation",
  resources: ["firmware/storage"],
  verify: "replacement passes",
  supersedes: [original.id],
});
assert.equal(replacement.details.action, "supersede");
assert.equal(replacement.details.outcome, "superseded");
assert.deepEqual(replacement.details.supersededWorkIds, [original.id]);
assert.equal(getState().tasks[original.id]?.status, "superseded");
assert.equal(getState().tasks[original.id]?.supersededBy, replacement.details.work.id);
assert.deepEqual(getState().tasks[dependent.id]?.dependsOn, [replacement.details.work.id]);
assert.equal(getState().tasks[replacement.details.work.id]?.status, "pending");

const completed = createTask({ subject: "Completed Work" }).task;
getState().tasks[completed.id].status = "completed";
const countBefore = Object.keys(getState().tasks).length;
await assert.rejects(work.execute("completed", { action: "supersede", subject: "No replacement", supersedes: [completed.id] }), /cannot supersede completed/i);
assert.equal(Object.keys(getState().tasks).length, countBefore);
await assert.rejects(work.execute("unknown", { action: "supersede", subject: "Unknown replacement", supersedes: ["missing"] }), /Unknown work id/i);

shutdownTeamMachine();
console.log("WORK_SUPERSEDE_OK");
