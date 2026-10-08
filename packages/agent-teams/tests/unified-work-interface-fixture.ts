import assert from "node:assert/strict";
import { registerLeaderTools } from "../src/tools.ts";
import { registerTaskTools } from "@fradser/pi-tasks";
import { initTeamMachine, shutdownTeamMachine } from "../src/team-machine.ts";
import { listTasks, livingAgents, resetState } from "../src/state.ts";

const tools = new Map();
const host = {
  registerTool(tool) { tools.set(tool.name, tool); },
  getActiveTools: () => [],
  setActiveTools() {},
};
registerLeaderTools(host);
// The tasks tool is registered by its own package, never by this one.
registerTaskTools(host);

// Four tools, one per operation, as @fradser/pi-tasks registers them.
const create = tools.get("create_task")!;
const list = tools.get("list_tasks")!;
const update = tools.get("update_task")!;
assert.ok(create && list && update, "the task tools must be registered, by @fradser/pi-tasks");


// One flat schema per tool, no union root. The old tool nested `target.session`
// inside an object, which some harnesses deliver as a JSON string; a union root
// then forced a tolerance layer into every consumer.
const properties = update.parameters.properties;
assert.equal(update.parameters.additionalProperties, false);
assert.equal(create.parameters.additionalProperties, false);
assert.equal(list.parameters.additionalProperties, false);
// The id is the only required field on an update; the create requires a subject.
assert.deepEqual(update.parameters.required, ["id"]);
assert.deepEqual(create.parameters.required, ["subject"]);
// Nothing here names a participant to dispatch to, or a verify gate for a task
// that does not exist yet.
for (const banned of ["assign", "assignee", "owner", "target", "agent", "agent", "spawnId"]) {
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
const prerequisite = await create.execute("prerequisite", { subject: "Review auth" }, undefined, undefined, context);
const prerequisiteId = prerequisite.details.id;

const created = await create.execute("create", {
  subject: "Fix auth",
  description: "Apply the accepted findings",
  dependsOn: [prerequisiteId],
  verify: "Auth scenarios pass",
}, undefined, undefined, context);

assert.equal(created.details.tool, "create_task");
assert.equal(created.details.status, "pending");
assert.equal(created.details.task.subject, "Fix auth");
assert.deepEqual(created.details.task.dependsOn, [prerequisiteId]);
// Resources left the model-facing surface with the retirement. The record and
// the library still carry them for existing data and known consumers, so the
// projection is where their absence is worth pinning.
assert.equal(created.details.task.resources, undefined, "create_task no longer accepts resources");
assert.equal(created.details.task.verify, "Auth scenarios pass");
assert.equal(livingAgents().length, 0);
assert.match(created.content[0].text, /^TASK · /);
// Replacement is a field on create, not a second verb.
assert.deepEqual(created.details.replaced, []);

const listed = await list.execute("list", {}, undefined, undefined, context);
assert.equal(listed.details.count, 2);
const listedTask = listed.details.tasks.find((entry) => entry.id === created.details.id);
assert.deepEqual(listedTask, {
  id: created.details.id,
  subject: "Fix auth",
  status: "pending",
  dependsOn: [prerequisiteId],
  // The prerequisite is still pending here, so the projection names it as the
  // unfinished edge. That is the whole point of the field: the two lists are
  // otherwise compared by hand.
  blockedBy: [prerequisiteId],
});
// A list is bounded, so it leaves the body and the gate out rather than paying
// for them twice. `get_task` is what reads them, and the fixture reads the body
// through the create result above.
assert.equal(listedTask.description, undefined, "a list omits the description");
assert.equal(listedTask.verify, undefined, "a list omits the completion gate");
// The leader is a participant like any other: it takes by naming the task, not
// by being assigned it.
const taken = await update.execute("take", { id: prerequisiteId, status: "in_progress" }, undefined, undefined, context);
assert.equal(taken.details.status, "in_progress");
assert.equal(taken.details.task.holder, "main");

// Unmet dependencies are refused, which is what makes the graph a graph.
const blocked = await update.execute("blocked", { id: created.details.id, status: "in_progress" }, undefined, undefined, context);
assert.equal(blocked.details.ok, false);
assert.match(blocked.content[0].text, /depends on .*which is not completed/);

// A failure is a recorded outcome, not prose.
const failed = await update.execute("fail", { id: prerequisiteId, status: "completed", outcome: "failed", result: "no reviewer available" }, undefined, undefined, context);
assert.equal(failed.details.status, "blocked");
assert.equal(failed.details.task.status, "blocked");
assert.equal(failed.details.task.result, "no reviewer available");

// The recovery hold withholds the task until somebody says why.
const silent = await update.execute("silent", { id: prerequisiteId, status: "in_progress" }, undefined, undefined, context);
assert.equal(silent.details.ok, false);
assert.match(silent.content[0].text, /reason/);
const spoken = await update.execute("spoken", { id: prerequisiteId, status: "in_progress", reason: "self-review this time" }, undefined, undefined, context);
assert.equal(spoken.details.status, "in_progress");
assert.equal(spoken.details.task.recoveryNote, "self-review this time");

const beforeInvalid = listTasks().map((entry) => entry.id);
const invalid = await create.execute("invalid", {
  subject: "Broken task",
  dependsOn: ["missing-task"],
}, undefined, undefined, context);
assert.equal(invalid.details.ok, false);
assert.match(invalid.content[0].text, /Unknown task id/);
assert.deepEqual(listTasks().map((entry) => entry.id), beforeInvalid);

// No verb dispatches work to a named participant, and none releases a lease on
// demand. A status outside the three routes is refused with the valid set named,
// so a model that remembers an older verb learns the current one.
for (const removed of ["assign", "claim", "release", "submit", "supersede", "reclaim", "abandon"]) {
  const refusal = await update.execute(removed, { id: created.details.id, status: removed }, undefined, undefined, context);
  assert.equal(refusal.details.ok, false, `${removed} must be refused`);
  assert.match(refusal.content[0].text, new RegExp(removed));
}
const duplicateTask = await create.execute("dupe", { subject: "Fix auth" }, undefined, undefined, context);
assert.equal(duplicateTask.details.ok, true);
// A repeated subject gets a distinct id rather than colliding or overwriting, so
// two records about auth coexist and the tasks stays addressable by id.
const sameSubject = listTasks().filter((entry) => entry.subject === "Fix auth");
assert.equal(sameSubject.length, 2);
assert.notEqual(sameSubject[0].id, sameSubject[1].id);

// Replacement survives as a field on create rather than a second verb, and it
// still parks a holder so its cancellation can be acknowledged.
const delivered = await update.execute("deliver", { id: prerequisiteId, status: "completed", outcome: "success", result: "auth reviewed" }, undefined, undefined, context);
assert.equal(delivered.details.status, "completed");
// Superseding a completed task is refused outright: a delivered result is
// evidence, and silently replacing it would erase the record of what was done.
const replaceCompleted = await create.execute("replace-completed", {
  subject: "Review auth once more",
  supersedes: [prerequisiteId],
}, undefined, undefined, context);
assert.equal(replaceCompleted.details.ok, false);
assert.match(replaceCompleted.content[0].text, /cannot supersede completed/i);
// The still-pending one is what replacement is for.
const replacement = await create.execute("replace", {
  subject: "Review auth again",
  supersedes: [created.details.id],
}, undefined, undefined, context);
assert.equal(replacement.details.ok, true);
assert.deepEqual(replacement.details.replaced, [created.details.id]);
assert.equal(listTasks().find((entry) => entry.id === created.details.id).status, "pending");
assert.equal(listTasks().find((entry) => entry.id === created.details.id).supersededBy, replacement.details.id);
// Reopening a superseded task is refused: the successor already replaced it.
const reopenSuperseded = await update.execute("reopen-superseded", { id: created.details.id, status: "pending" }, undefined, undefined, context);
assert.equal(reopenSuperseded.details.ok, false);
assert.match(reopenSuperseded.content[0].text, /replaced/);

shutdownTeamMachine();
console.log("UNIFIED_WORK_INTERFACE_OK");
