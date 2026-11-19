import assert from "node:assert/strict";
import { Value } from "typebox/value";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { INTENT_TOOL_NAMES, INTENT_TOOL_SCHEMAS, CHILD_OPERATIONS, executeChildIntent, registerIntentTools } from "@fradser/pi-subagents";
import { registerLeaderTools } from "../src/tools.ts";
import { WorkerWorkToolParams, normalizeCoordinationParams } from "../src/types.ts";
import { registerChildCapabilities } from "../src/worker.ts";

type SchemaLike = Record<string, unknown> & { properties?: Record<string, any> };

// The agent family stays flat: a harness that stringifies a nested structure
// must not have its call rejected by schema validation before the handler can
// parse it. The child Work slice has its own schema and is checked below.
function acceptsJsonType(prop: any, type: string): boolean {
  if (!prop) return false;
  if (prop.type === type) return true;
  return Array.isArray(prop.anyOf) && prop.anyOf.some((entry: any) => entry.type === type);
}

const teammateProps = (INTENT_TOOL_SCHEMAS.agent_start as SchemaLike).properties!;
const nestedAgentParams = Object.entries(teammateProps).filter(([, prop]) => acceptsJsonType(prop, "object"));
assert.deepEqual(nestedAgentParams.map(([name]) => name), [],
  `agent_start must stay flat; these parameters nest: ${nestedAgentParams.map(([n]) => n).join(", ")}`);

const started = {
  prompt: "Review the diff",
  label: "reviewer",
  tools: ["read"],
};
if (!Value.Check(INTENT_TOOL_SCHEMAS.agent_start, started)) {
  throw new Error(`start payload rejected: ${JSON.stringify([...Value.Errors(INTENT_TOOL_SCHEMAS.agent_start, started)])}`);
}
if (Value.Check(INTENT_TOOL_SCHEMAS.agent_start, { ...started, bogus: 1 })) {
  throw new Error("agent_start payload with unknown extra property accepted");
}
if (Value.Check(INTENT_TOOL_SCHEMAS.agent_start, { prompt: "Run", definition: { description: "d" } })) {
  throw new Error("agent_start payload with a nested definition accepted");
}

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
const unnamedVerbs = CHILD_OPERATIONS.filter((verb: string) => !unknownAction.content[0].text.includes(verb));
if (unknownAction.details.ok !== false || unnamedVerbs.length > 0) {
  throw new Error(`an unknown operation must be refused with the valid set; unnamed: ${unnamedVerbs.join(", ")}`);
}

const normalized = normalizeCoordinationParams(
  { context: JSON.stringify({ handoff: { delta: "prior brief" } }), dependsOn: JSON.stringify(["w0"]) } as Record<string, unknown>,
  ["context", "dependsOn"],
);
if (!Array.isArray(normalized.dependsOn)) throw new Error("stringified dependsOn not parsed");
if (typeof normalized.context !== "object" || normalized.context === null) {
  throw new Error("stringified context not parsed by the normalizer");
}
const plain = normalizeCoordinationParams({ verify: "run tests", prompt: "not json" } as Record<string, unknown>, ["verify", "prompt", "context"]);
if (plain.verify !== "run tests" || plain.prompt !== "not json" || "context" in plain) {
  throw new Error("plain string parameters mutated or absent keys invented");
}

// The registered surface is the contract a host actually exposes. Task tools
// are retired: neither process registers create_task/get_task/list_tasks/
// update_task, and the child keeps only its own Work slice.
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
} as unknown as ExtensionAPI;

registerLeaderTools(pi);
registerIntentTools(pi);
const leaderTools = registered.splice(0);
registerChildCapabilities(pi);
const teammateTools = registered.splice(0);

const count = (tools: Array<{ name: string }>, name: string) => tools.filter((tool) => tool.name === name).length;
for (const name of INTENT_TOOL_NAMES) {
  assert.equal(count(leaderTools, name), 1, `the leader must register exactly one ${name}`);
}
assert.equal(count(leaderTools, "agent"), 0, "the leader must not still register the retired `agent` tool");
assert.equal(count(leaderTools, "message"), 1, "the leader registers the message capability");
for (const name of ["create_task", "get_task", "list_tasks", "update_task"]) {
  assert.equal(count(leaderTools, name), 0, `the leader must not register the retired ${name}`);
  assert.equal(count(teammateTools, name), 0, `the child must not register the retired ${name}`);
}
assert.equal(count(leaderTools, "task"), 0, "the leader must not register a task tool");
assert.equal(count(teammateTools, "message"), 1, "the child registers the message capability");
assert.equal(count(teammateTools, "agent"), 0, "the child is not granted a child tool");
assert.equal(count(teammateTools, "task"), 1, "the child keeps its own Work-Item slice");
for (const tool of registered) {
  const schema = tool.parameters;
  assert.equal(typeof schema, "object", `${tool.name} has no parameter schema`);
  assert.ok(schema && !Array.isArray(schema) && typeof (schema as Record<string, unknown>).type === "string",
    `${tool.name} parameter root is not a typed object`);
}
assert.equal(teammateTools.find((tool) => tool.name === "task")?.parameters, WorkerWorkToolParams as unknown,
  "the child's work slice uses the agent's own schema");

console.log("TOOL_PARAM_SCHEMA_OK");
