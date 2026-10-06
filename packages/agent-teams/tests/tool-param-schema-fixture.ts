import assert from "node:assert/strict";
import { Value } from "typebox/value";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { INTENT_TOOL_NAMES, INTENT_TOOL_SCHEMAS, CHILD_OPERATIONS, executeChildIntent, registerIntentTools } from "@fradser/pi-subagents";
import {
  TASK_CREATE_PARAMS,
  TASK_GET_PARAMS,
  TASK_LIST_PARAMS,
  TASK_UPDATE_PARAMS,
  TASK_CAPABILITY_TOOLS,
  executeTaskUpdate,
  registerTaskTools,
} from "@fradser/pi-tasks";
import { registerLeaderTools } from "../src/tools.ts";
import { WorkerWorkToolParams, normalizeCoordinationParams } from "../src/types.ts";
import { registerChildCapabilities } from "../src/worker.ts";

type SchemaLike = Record<string, unknown> & { properties?: Record<string, any> };

// The property this file exists to protect: a harness that delivers a nested
// structure as a JSON string must not have its call rejected by schema
// validation, and the handler must receive the parsed value.
//
// It used to cover `agent.definition` and `task.target.session`. Both are gone
// because both tools are now flat — `agent` has no nested parameter at all, and
// the task store has no target because it names no participant. The one nesting that
// survives is `task.context`, and it is object-only: `stringTolerant` existed for
// two parameters, both of which are gone, so keeping a union branch for a
// parameter no harness has ever stringified would be machinery for a case that
// has not happened. If `context` is ever observed arriving as a string, the fix is
// a tolerance branch here plus a parse in the handler — and this assertion is
// what must change with it.
function acceptsJsonType(prop: any, type: string): boolean {
  if (!prop) return false;
  if (prop.type === type) return true;
  return Array.isArray(prop.anyOf) && prop.anyOf.some((entry: any) => entry.type === type);
}

const teammateProps = (INTENT_TOOL_SCHEMAS.agent_start as SchemaLike).properties!;
// The four task tools, each with its own flat parameter object. `context` is the
// only nested parameter across all of them, and it lives on update_task.
const createProps = (TASK_CREATE_PARAMS as SchemaLike).properties!;
const listProps = (TASK_LIST_PARAMS as SchemaLike).properties!;
const updateProps = (TASK_UPDATE_PARAMS as SchemaLike).properties!;
const taskProps = updateProps;

// Flat by construction: the agent tool has no object-valued parameter, which is
// what removed the tolerance layer from every consumer.
const nestedAgentParams = Object.entries(teammateProps).filter(([, prop]) => acceptsJsonType(prop, "object"));
assert.deepEqual(nestedAgentParams.map(([name]) => name), [],
  `agent_start must stay flat; these parameters nest: ${nestedAgentParams.map(([n]) => n).join(", ")}`);

// The tasks's only nested parameter is `context`, and it takes an object.
assert.ok(acceptsJsonType(taskProps.context, "object"), "task context must accept an object");
assert.equal(acceptsJsonType(taskProps.context, "string"), false,
  "task context is object-only; a string branch needs a parse in the handler to match");
for (const arrayParam of ["dependsOn", "supersedes"]) {
  assert.ok(acceptsJsonType(createProps[arrayParam], "array"), `create_task ${arrayParam} must accept an array`);
}
// Resources stay on the record and in the library for existing data and known
// consumers, but the retirement took them off the model-facing surface. The
// schema must stay silent about them, so neither tool declares the parameter.
assert.equal(createProps.resources, undefined, "create_task must not accept resources");
assert.equal(updateProps.resources, undefined, "update_task must not accept resources");
assert.ok(acceptsJsonType(listProps.statusFilter, "array"), "list_tasks statusFilter must accept an array");
// The four names are the contract a spawner grants against, so they are pinned
// here rather than left to a caller's assumption.
assert.deepEqual([...TASK_CAPABILITY_TOOLS], ["create_task", "get_task", "list_tasks", "update_task"]);

const started = {
  prompt: "Review the diff",
  label: "reviewer",
  tools: ["read"],
};
if (!Value.Check(INTENT_TOOL_SCHEMAS.agent_start, started)) {
  throw new Error(`start payload rejected: ${JSON.stringify([...Value.Errors(INTENT_TOOL_SCHEMAS.agent_start, started)])}`);
}
// Unknown properties are refused rather than dropped: a silently dropped field
// teaches the model that the parameter exists.
if (Value.Check(INTENT_TOOL_SCHEMAS.agent_start, { ...started, bogus: 1 })) {
  throw new Error("agent_start payload with unknown extra property accepted");
}
// The flat spelling is what a model must produce; the old nested one is not a
// second accepted form.
if (Value.Check(INTENT_TOOL_SCHEMAS.agent_start, { prompt: "Run", definition: { description: "d" } })) {
  throw new Error("agent_start payload with a nested definition accepted");
}
// Stop and input address one incarnation, so their schemas require the copied
// handle and the handler refuses the same call when the handle is malformed.
for (const tool of ["agent_stop", "agent_input"] as const) {
  const schema = INTENT_TOOL_SCHEMAS[tool] as SchemaLike;
  assert.ok((schema.required as string[]).includes("session"), `${tool} must require the exact handle`);
  if (Value.Check(schema, { name: "reviewer" })) {
    throw new Error(`${tool} accepts a name-only payload; the exact handle is required`);
  }
}
const missingSession = await executeChildIntent({ operation: "stop", name: "reviewer" });
if (missingSession.details.ok !== false) {
  throw new Error("a control without a session handle must be refused by the handler");
}
if (!/session:<name>:<incarnation>/.test(missingSession.content[0].text)) {
  throw new Error(`the refusal must name what is missing: ${missingSession.content[0].text}`);
}
const unknownAction = await executeChildIntent({ operation: "teleport", name: "reviewer" });
// Read the valid set from the package rather than repeating it here: a hardcoded
// list went stale the moment the resident operations were named apart, and the
// assertion below is about the refusal naming them, not about their order.
const unnamedVerbs = CHILD_OPERATIONS.filter((verb: string) => !unknownAction.content[0].text.includes(verb));
if (unknownAction.details.ok !== false || unnamedVerbs.length > 0) {
  throw new Error(`an unknown operation must be refused with the valid set; unnamed: ${unnamedVerbs.join(", ")}`);
}

if (!Value.Check(TASK_CREATE_PARAMS, { subject: "Ship", dependsOn: ["w0"] })) {
  throw new Error("task create payload rejected");
}
if (!Value.Check(TASK_CREATE_PARAMS, { subject: "Ship", supersedes: ["w0"] })) {
  throw new Error("task supersede payload rejected");
}
if (!Value.Check(TASK_GET_PARAMS, { id: "w0" })) {
  throw new Error("task get payload rejected");
}
// get_task takes an id and nothing else: a read that accepted anything else
// would be a write wearing a read's name.
assert.deepEqual(Object.keys((TASK_GET_PARAMS as SchemaLike).properties!), ["id"]);
if (!Value.Check(TASK_LIST_PARAMS, { statusFilter: ["pending"], claimable: true, limit: 5 })) {
  throw new Error("task list payload rejected");
}
// `context` is a declared object, so the shapes inside it are declared too. A
// handoff spelled as a string used to validate against a bare `object` and was
// then stored verbatim: a brief no reader could read and no budget accounted for.
if (Value.Check(TASK_UPDATE_PARAMS, { id: "w1", context: { handoff: "prior brief" } })) {
  throw new Error("task payload with a string handoff accepted");
}
if (Value.Check(TASK_UPDATE_PARAMS, { id: "w1", context: { handOff: { delta: "x" } } })) {
  throw new Error("task payload with a misspelled handoff accepted");
}
if (!Value.Check(TASK_UPDATE_PARAMS, { id: "w1", status: "in_progress" })) {
  throw new Error("task take payload rejected");
}
if (!Value.Check(TASK_UPDATE_PARAMS, { id: "w1", status: "completed", outcome: "failed", result: "blocked" })) {
  throw new Error("task complete payload rejected");
}
// `status: "pending"` is how a completed task is reopened. There is no separate
// verb for it, so the position is reachable exactly one way.
if (!Value.Check(TASK_UPDATE_PARAMS, { id: "w1", status: "pending" })) {
  throw new Error("task reopen payload rejected");
}
// Completion is terminal, so an outcome is not optional — enforced by the
// handler, like every other per-action requirement of a flat schema.
if (!Value.Check(TASK_UPDATE_PARAMS, { id: "w1", status: "completed" })) {
  throw new Error("the flat schema accepts a completion payload; the handler requires the outcome");
}
const noOutcome = await executeTaskUpdate({ id: "w1", status: "completed" });
if (noOutcome.details.ok !== false) throw new Error("complete without an outcome must be refused");
if (!/outcome is required/.test(noOutcome.content[0].text)) {
  throw new Error(`the refusal must name what is missing: ${noOutcome.content[0].text}`);
}
// `supersede` and `reopen` are gone as verbs; a payload naming one must not
// validate against a schema that has no such action.
// A dispatch verb is not a thing any of the four take: supersession is a
// parameter of create_task, and naming a participant is not expressible anywhere.
for (const params of [TASK_CREATE_PARAMS, TASK_GET_PARAMS, TASK_LIST_PARAMS, TASK_UPDATE_PARAMS]) {
  if (Value.Check(params, { assign: "someone" } as never)) {
    throw new Error("a removed assign field accepted");
  }
  if (Value.Check(params, { participant: "someone" } as never)) {
    throw new Error("a participant field accepted");
  }
}

if (Value.Check(TASK_UPDATE_PARAMS, { id: "w1", context: "not an object" })) {
  throw new Error("task payload with a non-object context accepted");
}

const normalized = normalizeCoordinationParams(
  { context: JSON.stringify({ handoff: { delta: "prior brief" } }), dependsOn: JSON.stringify(["w0"]) } as Record<string, unknown>,
  ["context", "dependsOn"],
);
// The normalizer still exists for the agent's intent path, where a harness
// stringifies arrays. It is not wired to the leader-side tasks tool, so a
// stringified context stays a string here and is refused by the schema — which
// is the honest outcome, not a silent half-parse.
if (!Array.isArray(normalized.dependsOn)) throw new Error("stringified dependsOn not parsed");
if (typeof normalized.context !== "object" || normalized.context === null) {
  throw new Error("stringified context not parsed by the normalizer");
}

// Two layers, asserted separately above and here: the normalizer can parse a
// stringified structure, but the leader-side tasks schema does not *accept* one,
// so such a call never reaches the handler. Keeping both true is what stops a
// half-tolerated parameter from appearing later.
const plain = normalizeCoordinationParams({ verify: "run tests", prompt: "not json" } as Record<string, unknown>, ["verify", "prompt", "context"]);
if (plain.verify !== "run tests" || plain.prompt !== "not json" || "context" in plain) {
  throw new Error("plain string parameters mutated or absent keys invented");
}

// The exported constants above are only half the contract: what reaches a
// provider is the schema each tool registers. Sweep the registered surface so a
// tool definition cannot reintroduce a root that declares `properties` without an
// object type, which providers with strict object typing reject outright.
const registered: Array<{ name: string; parameters?: SchemaLike }> = [];
const pi = {
  registerTool: (tool: { name: string; parameters?: SchemaLike }) => {
    registered.push(tool);
  },
  registerCommand: () => undefined,
  getActiveTools: () => [],
  setActiveTools: () => undefined,
  on: () => undefined,
  events: { emit: () => undefined, on: () => undefined },
} as unknown as ExtensionAPI; // stub of the harness interface: the registration functions touch only these members

registerLeaderTools(pi);
registerIntentTools(pi);
registerTaskTools(pi);
const leaderTools = registered.splice(0);
registerChildCapabilities(pi);
const teammateTools = registered.splice(0);

// Each tool has exactly one registrant per process. Two is a collision or a
// silent drop depending on load order, and neither failure names the cause.
const TASK_TOOL_NAMES = [...TASK_CAPABILITY_TOOLS];
const count = (tools: Array<{ name: string }>, name: string) => tools.filter((tool) => tool.name === name).length;

// The leader gets the four task tools and exactly one registrant each. Two is a
// collision; zero is a silent drop, and neither failure names its own cause.
for (const name of TASK_TOOL_NAMES) {
  assert.equal(count(leaderTools, name), 1, `leader must register exactly one ${name}, found ${count(leaderTools, name)}`);
}
for (const name of INTENT_TOOL_NAMES) {
  assert.equal(count(leaderTools, name), 1, `the leader must register exactly one ${name}`);
}
assert.equal(count(leaderTools, "agent"), 0, "the leader must not still register the retired `agent` tool");
assert.equal(count(leaderTools, "message"), 1, "the leader registers the message capability");
// The removed single `task` name must not keep working: a spawner granting a
// capability would otherwise believe it granted something that no longer exists.
assert.equal(count(leaderTools, "task"), 0, "leader must not still register the removed single \"task\" tool");

// The child's `task` is a different tool in this package — its own Work-Item
// slice — so it is asserted as what it is rather than folded into the four. The
// child gets no `agent` capability and none of the four: it is handed one slice
// of work, not the whole surface.
assert.equal(count(teammateTools, "message"), 1, "the child registers the message capability");
assert.equal(count(teammateTools, "agent"), 0, "the child is not granted a child tool");
assert.equal(count(teammateTools, "task"), 1, "the child keeps its own Work-Item slice");
for (const name of TASK_TOOL_NAMES) {
  assert.equal(count(teammateTools, name), 0,
    `the child must not also register ${name}; it has its own slice, and two of one operation is a collision`);
}
for (const tool of registered) {
  const schema = tool.parameters;
  assert.equal(typeof schema, "object", `${tool.name} has no parameter schema`);
  assert.ok(schema && !Array.isArray(schema) && typeof (schema as Record<string, unknown>).type === "string",
    `${tool.name} parameter root is not a typed object`);
}
assert.equal(teammateTools.find((tool) => tool.name === "task")?.parameters, WorkerWorkToolParams as unknown,
  "the child's work slice is the agent schema, not one of the four task schemas");
// A spawner grants capabilities by name, so the four names and the removed one
// are the whole grantable surface on the leader side. Read from the exported
// list rather than restated, so it cannot go stale here.
assert.ok(TASK_CAPABILITY_TOOLS.every((name) => !name.includes(" ")), "capability names carry no arguments");

console.log("TOOL_PARAM_SCHEMA_OK");
