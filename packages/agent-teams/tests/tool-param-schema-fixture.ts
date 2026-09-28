import assert from "node:assert/strict";
import { Value } from "typebox/value";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { AGENT_TOOL_PARAMS, executeAgentAction, registerAgentTool } from "@fradser/pi-subagents";
import { TASK_TOOL_PARAMS, executeTaskTool, registerTaskTool } from "@fradser/pi-tasks";
import { registerLeaderTools } from "../src/tools.ts";
import { WorkerWorkToolParams, normalizeCoordinationParams } from "../src/types.ts";
import { registerWorkerCapabilities } from "../src/worker.ts";

type SchemaLike = Record<string, unknown> & { properties?: Record<string, any> };

// The property this file exists to protect: a harness that delivers a nested
// structure as a JSON string must not have its call rejected by schema
// validation, and the handler must receive the parsed value.
//
// It used to cover `agent.definition` and `task.target.session`. Both are gone
// because both tools are now flat — `agent` has no nested parameter at all, and
// the board has no target because it names no participant. The one nesting that
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

const agentProps = (AGENT_TOOL_PARAMS as SchemaLike).properties!;
const taskProps = (TASK_TOOL_PARAMS as SchemaLike).properties!;

// Flat by construction: the agent tool has no object-valued parameter, which is
// what removed the tolerance layer from every consumer.
const nestedAgentParams = Object.entries(agentProps).filter(([, prop]) => acceptsJsonType(prop, "object"));
assert.deepEqual(nestedAgentParams.map(([name]) => name), [],
  `agent must stay flat; these parameters nest: ${nestedAgentParams.map(([n]) => n).join(", ")}`);

// The board's only nested parameter is `context`, and it takes an object.
assert.ok(acceptsJsonType(taskProps.context, "object"), "task context must accept an object");
assert.equal(acceptsJsonType(taskProps.context, "string"), false,
  "task context is object-only; a string branch needs a parse in the handler to match");
for (const arrayParam of ["dependsOn", "supersedes", "resources", "status_filter"]) {
  assert.ok(acceptsJsonType(taskProps[arrayParam], "array"), `task ${arrayParam} must accept an array`);
}

const started = {
  action: "start",
  name: "reviewer",
  prompt: "Review the diff",
  description: "Read-only reviewer",
  role_prompt: "Read evidence and report",
  tools: ["read"],
};
if (!Value.Check(AGENT_TOOL_PARAMS, started)) {
  throw new Error(`start payload rejected: ${JSON.stringify([...Value.Errors(AGENT_TOOL_PARAMS, started)])}`);
}
// Unknown properties are refused rather than dropped: a silently dropped field
// teaches the model that the parameter exists.
if (Value.Check(AGENT_TOOL_PARAMS, { ...started, bogus: 1 })) {
  throw new Error("agent payload with unknown extra property accepted");
}
// The flat spelling is what a model must produce; the old nested one is not a
// second accepted form.
if (Value.Check(AGENT_TOOL_PARAMS, { action: "start", name: "r", definition: { description: "d" } })) {
  throw new Error("agent payload with a nested definition accepted");
}
// Inspect and stop address one incarnation, so a session handle is required —
// but the schema is a single flat object with one shared `required`, so it
// cannot express per-action requirements. The handler carries them instead, and
// the guarantee is asserted there. This is the price of flattening: a union
// schema could encode it, at the cost of a tolerance layer in every consumer.
if (!Value.Check(AGENT_TOOL_PARAMS, { action: "inspect", name: "reviewer" })) {
  throw new Error("the flat schema accepts an inspect payload; per-action requirements are the handler's job");
}
const missingSession = await executeAgentAction({ action: "inspect", name: "reviewer" });
if (missingSession.details.ok !== false) {
  throw new Error("inspect without a session handle must be refused by the handler");
}
if (!/exact session handle/.test(missingSession.content[0].text)) {
  throw new Error(`inspect refusal must name what is missing: ${missingSession.content[0].text}`);
}
const unknownAction = await executeAgentAction({ action: "teleport", name: "reviewer" });
if (unknownAction.details.ok !== false || !/start, inspect, list, or stop/.test(unknownAction.content[0].text)) {
  throw new Error("an unknown action must be refused with the valid set");
}

if (!Value.Check(TASK_TOOL_PARAMS, { action: "create", subject: "Ship", dependsOn: ["w0"], context: { handoff: "prior brief" } })) {
  throw new Error("task create payload rejected");
}
if (!Value.Check(TASK_TOOL_PARAMS, { action: "update", id: "w1", status: "in_progress" })) {
  throw new Error("task take payload rejected");
}
if (!Value.Check(TASK_TOOL_PARAMS, { action: "complete", id: "w1", outcome: "failed", result: "blocked" })) {
  throw new Error("task complete payload rejected");
}
// Completion is terminal, so an outcome is not optional — enforced by the
// handler, like every other per-action requirement of a flat schema.
if (!Value.Check(TASK_TOOL_PARAMS, { action: "complete", id: "w1" })) {
  throw new Error("the flat schema accepts a completion payload; the handler requires the outcome");
}
const noOutcome = await executeTaskTool({ action: "complete", id: "w1" });
if (noOutcome.details.ok !== false) throw new Error("complete without an outcome must be refused");
if (!/outcome is required/.test(noOutcome.content[0].text)) {
  throw new Error(`the refusal must name what is missing: ${noOutcome.content[0].text}`);
}
// `supersede` and `reopen` are gone as verbs; a payload naming one must not
// validate against a schema that has no such action.
if (Value.Check(TASK_TOOL_PARAMS, { action: "supersede", subject: "s", supersedes: ["w1"] })) {
  throw new Error("removed supersede verb accepted");
}
if (Value.Check(TASK_TOOL_PARAMS, { action: "assign", id: "w1", target: { session: "s1" } })) {
  throw new Error("removed assign verb accepted");
}

if (Value.Check(TASK_TOOL_PARAMS, { action: "update", id: "w1", context: "not an object" })) {
  throw new Error("task payload with a non-object context accepted");
}

const normalized = normalizeCoordinationParams(
  { action: "update", id: "w1", context: JSON.stringify({ handoff: "prior brief" }), dependsOn: JSON.stringify(["w0"]) } as Record<string, unknown>,
  ["context", "dependsOn"],
);
// The normalizer still exists for the worker's intent path, where a harness
// stringifies arrays. It is not wired to the leader-side board tool, so a
// stringified context stays a string here and is refused by the schema — which
// is the honest outcome, not a silent half-parse.
if (!Array.isArray(normalized.dependsOn)) throw new Error("stringified dependsOn not parsed");
if (typeof normalized.context !== "object" || normalized.context === null) {
  throw new Error("stringified context not parsed by the normalizer");
}

// Two layers, asserted separately above and here: the normalizer can parse a
// stringified structure, but the leader-side board schema does not *accept* one,
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
registerAgentTool(pi);
registerTaskTool(pi);
const leaderTools = registered.splice(0);
registerWorkerCapabilities(pi);
const workerTools = registered.splice(0);

// Each tool has exactly one registrant per process. Two is a collision or a
// silent drop depending on load order, and neither failure names the cause.
for (const [tools, role] of [[leaderTools, "leader"], [workerTools, "worker"]] as const) {
  for (const name of ["agent", "task", "message"]) {
    const matches = tools.filter((tool) => tool.name === name);
    const expected = role === "worker" && name === "agent" ? 0 : 1;
    assert.equal(matches.length, expected,
      `${role} must register exactly ${expected} ${name} tool(s), found ${matches.length}`);
  }
}
for (const tool of registered) {
  const schema = tool.parameters;
  assert.equal(typeof schema, "object", `${tool.name} has no parameter schema`);
  assert.ok(schema && !Array.isArray(schema) && typeof (schema as Record<string, unknown>).type === "string",
    `${tool.name} parameter root is not a typed object`);
}
assert.ok(workerTools.some((tool) => tool.name === "task"), "the child keeps its board slice");
assert.equal(workerTools.find((tool) => tool.name === "task")?.parameters, WorkerWorkToolParams as unknown,
  "the child's board slice is the worker schema, not the leader's");

console.log("TOOL_PARAM_SCHEMA_OK");
