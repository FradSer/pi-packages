import assert from "node:assert/strict";
import { registerLeaderTools } from "../src/tools.ts";
import { initTeamMachine, shutdownTeamMachine } from "../src/team-machine.ts";
import { listTasks, livingTeammates, resetState } from "../src/state.ts";

const tools = new Map();
registerLeaderTools({
  registerTool(tool) { tools.set(tool.name, tool); },
  getActiveTools: () => [],
  setActiveTools() {},
});

const work = tools.get("work");
assert.ok(work, "work must be registered for the leader");
const variants = work.parameters.anyOf ?? work.parameters.anyOf ?? [];
assert.deepEqual(variants.map((variant) => variant.properties.action.const).sort(), ["assign", "create", "list", "release", "reopen", "supersede"]);
const createSchema = variants.find((variant) => variant.properties.action.const === "create");
assert.equal("supersedes" in createSchema.properties, false);
assert.equal(createSchema.additionalProperties, false);
const listSchema = variants.find((variant) => variant.properties.action.const === "list");
assert.equal(listSchema.additionalProperties, false);
const assignSchema = variants.find((variant) => variant.properties.action.const === "assign");
assert.equal(assignSchema.additionalProperties, false);
const releaseSchema = variants.find((variant) => variant.properties.action.const === "release");
assert.equal(releaseSchema.additionalProperties, false);
const reopenSchema = variants.find((variant) => variant.properties.action.const === "reopen");
assert.equal(reopenSchema.additionalProperties, false);
const supersedeSchema = variants.find((variant) => variant.properties.action.const === "supersede");
assert.equal(supersedeSchema.additionalProperties, false);
assert.equal(supersedeSchema.required.includes("supersedes"), true);

const root = process.env.PI_TEST_DIR;
assert.ok(root, "PI_TEST_DIR is required");
resetState();
initTeamMachine(
  { sessionManager: { getSessionFile: () => undefined }, cwd: root, model: undefined },
  { sendUpdate() {}, notifyChange() {} },
);

const context = { cwd: root };
const prerequisite = await work.execute("prerequisite", { action: "create", subject: "Review auth" }, undefined, undefined, context);
const prerequisiteId = prerequisite.details.work.id;

const created = await work.execute("create", {
  action: "create",
  subject: "Fix auth",
  description: "Apply the accepted findings",
  dependsOn: [prerequisiteId],
  resources: ["/src/auth/", "src/auth"],
  verify: "Auth scenarios pass",
}, undefined, undefined, context);

assert.equal(created.details.action, "create");
assert.equal(created.details.outcome, "created");
assert.equal(created.details.state, "pending");
assert.equal(created.details.work.subject, "Fix auth");
assert.deepEqual(created.details.work.dependsOn, [prerequisiteId]);
assert.deepEqual(created.details.work.resources, ["src/auth"]);
assert.equal(created.details.work.verify, "Auth scenarios pass");
assert.equal(created.details.notifiedTeammates.length, 0);
assert.equal(livingTeammates().length, 0);
assert.match(created.content[0].text, /^WORK · current session\nCREATED · /);
assert.doesNotMatch(created.content[0].text, /BOARD|TASKS|task_claim|teammate_spawn/);

const listed = await work.execute("list", { action: "list" }, undefined, undefined, context);
assert.equal(listed.details.action, "list");
assert.equal(listed.details.outcome, "listed");
assert.match(listed.content[0].text, /^WORK · current session\n/);
assert.doesNotMatch(listed.content[0].text, /BOARD|TASKS|task_claim|teammate_spawn/);
const listedWork = listed.details.works.find((entry) => entry.id === created.details.work.id);
assert.deepEqual(listedWork, {
  id: created.details.work.id,
  subject: "Fix auth",
  description: "Apply the accepted findings",
  dependsOn: [prerequisiteId],
  resources: ["src/auth"],
  verify: "Auth scenarios pass",
  state: "pending",
});

const beforeInvalid = listTasks().map((task) => task.id);
await assert.rejects(
  work.execute("invalid", {
    action: "create",
    subject: "Broken work",
    dependsOn: ["missing-work"],
  }, undefined, undefined, context),
  /Unknown work id/i,
);
assert.deepEqual(listTasks().map((task) => task.id), beforeInvalid);

shutdownTeamMachine();
console.log("UNIFIED_WORK_INTERFACE_OK");
