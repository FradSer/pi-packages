import assert from "node:assert/strict";
import { registerLeaderTools } from "../src/tools.ts";
import { registerTaskTool } from "@fradser/pi-tasks";
import { initTeamMachine, shutdownTeamMachine } from "../src/team-machine.ts";
import { listTasks, livingTeammates, resetState } from "../src/state.ts";

const tools = new Map();
const host = {
  registerTool(tool) { tools.set(tool.name, tool); },
  getActiveTools: () => [],
  setActiveTools() {},
};
registerLeaderTools(host);
// The board tool is registered by its own package, never by this one.
registerTaskTool(host);

const task = tools.get("task");
assert.ok(task, "the task tool must be registered, by @fradser/pi-tasks");

// One flat schema, one action enum, no union root. The old tool nested
// `target.session` inside an object, which some harnesses deliver as a JSON
// string; a union root then forced a tolerance layer into every consumer.
const properties = task.parameters.properties;
assert.deepEqual(properties.action.enum, ["create", "list", "update", "complete", "reopen"]);
assert.equal(task.parameters.additionalProperties, false);
assert.deepEqual(task.parameters.required, ["action"]);
// Nothing here names a participant to dispatch to, or a verify gate for a task
// that does not exist yet.
for (const banned of ["assign", "assignee", "owner", "target", "worker", "agent", "spawnId"]) {
  assert.equal(banned in properties, false, `${banned} must not be a parameter`);
}

const root = process.env.PI_TEST_DIR;
assert.ok(root, "PI_TEST_DIR is required");
resetState();
initTeamMachine(
  { sessionManager: { getSessionFile: () => undefined }, cwd: root, model: undefined },
  { sendUpdate() {}, notifyChange() {} },
);

const context = { cwd: root };
const prerequisite = await task.execute("prerequisite", { action: "create", subject: "Review auth" }, undefined, undefined, context);
const prerequisiteId = prerequisite.details.id;

const created = await task.execute("create", {
  action: "create",
  subject: "Fix auth",
  description: "Apply the accepted findings",
  dependsOn: [prerequisiteId],
  resources: ["/src/auth/", "src/auth"],
  verify: "Auth scenarios pass",
}, undefined, undefined, context);

assert.equal(created.details.action, "create");
assert.equal(created.details.status, "pending");
assert.equal(created.details.task.subject, "Fix auth");
assert.deepEqual(created.details.task.dependsOn, [prerequisiteId]);
assert.deepEqual(created.details.task.resources, ["src/auth"]);
assert.equal(created.details.task.verify, "Auth scenarios pass");
assert.equal(livingTeammates().length, 0);
assert.match(created.content[0].text, /^TASK · /);
// Replacement is a field on create, not a second verb.
assert.deepEqual(created.details.replaced, []);

const listed = await task.execute("list", { action: "list" }, undefined, undefined, context);
assert.equal(listed.details.count, 2);
const listedTask = listed.details.tasks.find((entry) => entry.id === created.details.id);
assert.deepEqual(listedTask, {
  id: created.details.id,
  subject: "Fix auth",
  description: "Apply the accepted findings",
  status: "pending",
  dependsOn: [prerequisiteId],
  verify: "Auth scenarios pass",
  resources: ["src/auth"],
});

// The leader is a participant like any other: it takes by naming the task, not
// by being assigned it.
const taken = await task.execute("take", { action: "update", id: prerequisiteId, status: "in_progress" }, undefined, undefined, context);
assert.equal(taken.details.status, "in_progress");
assert.equal(taken.details.task.holder, "main");

// Unmet dependencies are refused, which is what makes the graph a graph.
const blocked = await task.execute("blocked", { action: "update", id: created.details.id, status: "in_progress" }, undefined, undefined, context);
assert.equal(blocked.details.ok, false);
assert.match(blocked.content[0].text, /unmet dependencies/);

// A failure is a recorded outcome, not prose.
const failed = await task.execute("fail", { action: "complete", id: prerequisiteId, outcome: "failed", result: "no reviewer available" }, undefined, undefined, context);
assert.equal(failed.details.status, "pending");
assert.equal(failed.details.task.recoveryRequired, true);
assert.equal(failed.details.task.result, "no reviewer available");

// The recovery hold withholds the task until somebody says why.
const silent = await task.execute("silent", { action: "update", id: prerequisiteId, status: "in_progress" }, undefined, undefined, context);
assert.equal(silent.details.ok, false);
assert.match(silent.content[0].text, /reason/);
const spoken = await task.execute("spoken", { action: "update", id: prerequisiteId, status: "in_progress", reason: "self-review this time" }, undefined, undefined, context);
assert.equal(spoken.details.status, "in_progress");
assert.equal(spoken.details.task.recoveryNote, "self-review this time");

const beforeInvalid = listTasks().map((entry) => entry.id);
const invalid = await task.execute("invalid", {
  action: "create",
  subject: "Broken task",
  dependsOn: ["missing-task"],
}, undefined, undefined, context);
assert.equal(invalid.details.ok, false);
assert.match(invalid.content[0].text, /Unknown task id/);
assert.deepEqual(listTasks().map((entry) => entry.id), beforeInvalid);

// The whole vocabulary, and nothing else. Each removed verb is refused with the
// replacement named, so a model that remembers one learns the current one.
for (const removed of ["assign", "claim", "release", "submit", "supersede", "reopen", "reclaim", "abandon", "get"]) {
  const refusal = await task.execute(removed, { action: removed, id: created.details.id }, undefined, undefined, context);
  assert.equal(refusal.details.ok, false, `${removed} must be refused`);
}
const duplicateTask = await task.execute("dupe", { action: "create", subject: "Fix auth" }, undefined, undefined, context);
assert.equal(duplicateTask.details.ok, true);
// A repeated subject gets a distinct id rather than colliding or overwriting, so
// two records about auth coexist and the board stays addressable by id.
const sameSubject = listTasks().filter((entry) => entry.subject === "Fix auth");
assert.equal(sameSubject.length, 2);
assert.notEqual(sameSubject[0].id, sameSubject[1].id);

// Replacement survives as a field on create rather than a second verb, and it
// still parks a holder so its cancellation can be acknowledged.
const delivered = await task.execute("deliver", { action: "complete", id: prerequisiteId, outcome: "success", result: "auth reviewed" }, undefined, undefined, context);
assert.equal(delivered.details.status, "completed");
// Superseding a completed task is refused outright: a delivered result is
// evidence, and silently replacing it would erase the record of what was done.
const replaceCompleted = await task.execute("replace-completed", {
  action: "create",
  subject: "Review auth once more",
  supersedes: [prerequisiteId],
}, undefined, undefined, context);
assert.equal(replaceCompleted.details.ok, false);
assert.match(replaceCompleted.content[0].text, /cannot supersede completed/i);
// The still-pending one is what replacement is for.
const replacement = await task.execute("replace", {
  action: "create",
  subject: "Review auth again",
  supersedes: [created.details.id],
}, undefined, undefined, context);
assert.equal(replacement.details.ok, true);
assert.deepEqual(replacement.details.replaced, [created.details.id]);
assert.equal(listTasks().find((entry) => entry.id === created.details.id).status, "superseded");
// Reopening a superseded task is refused: the successor already replaced it.
const reopenSuperseded = await task.execute("reopen-superseded", { action: "reopen", id: created.details.id }, undefined, undefined, context);
assert.equal(reopenSuperseded.details.ok, false);
assert.match(reopenSuperseded.content[0].text, /not completed/);

shutdownTeamMachine();
console.log("UNIFIED_WORK_INTERFACE_OK");
