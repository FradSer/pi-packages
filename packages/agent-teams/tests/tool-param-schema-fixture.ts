/** Schema-root contract for union-root coordination tools.
 *
 * Harnesses that parse tool parameters per name infer JSON parsing from the
 * root schema `properties`; a bare anyOf union leaves object/array parameters
 * as unparsed strings and every branch fails validation. This fixture pins the
 * root property mirror, the strict per-action contracts, and the stringified
 * parameter normalization fallback.
 */
import { Value } from "typebox/value";
import {
  AgentActionParams,
  WorkToolParams,
  WorkerWorkToolParams,
  normalizeCoordinationParams,
} from "../src/types.ts";

type SchemaLike = { properties?: Record<string, any>; anyOf?: unknown[] };

const expectations: Array<[string, SchemaLike, string[]]> = [
  ["agent", AgentActionParams as SchemaLike, ["action", "name", "prompt", "definition", "resources", "verify", "model", "fork", "session"]],
  ["work", WorkToolParams as SchemaLike, ["action", "subject", "description", "dependsOn", "verify", "resources", "id", "target", "reason", "supersedes"]],
  ["worker work", WorkerWorkToolParams as SchemaLike, ["action", "id", "result", "outcome"]],
];

for (const [name, schema, keys] of expectations) {
  if (!schema.properties) {
    throw new Error(`${name} root schema lacks properties; callers cannot infer parameter types (keys: ${JSON.stringify(Object.keys(schema))})`);
  }
  for (const key of keys) {
    if (!(key in schema.properties)) throw new Error(`${name} root properties missing "${key}"`);
  }
}

function acceptsJsonType(prop: any, type: string): boolean {
  if (!prop) return false;
  if (prop.type === type) return true;
  return Array.isArray(prop.anyOf) && prop.anyOf.some((entry: any) => entry.type === type);
}

const agentProps = (AgentActionParams as SchemaLike).properties!;
const workProps = (WorkToolParams as SchemaLike).properties!;
if (!acceptsJsonType(agentProps.definition, "object")) throw new Error("agent root definition does not accept objects");
if (!acceptsJsonType(workProps.target, "object")) throw new Error("work root target does not accept objects");
if (!acceptsJsonType(workProps.dependsOn, "array")) throw new Error("work root dependsOn does not accept arrays");
if (!acceptsJsonType(workProps.supersedes, "array")) throw new Error("work root supersedes does not accept arrays");
// String-tolerant edge: harnesses that deliver JSON strings must pass validation
// and reach the handler normalization instead of dying in schema validation.
if (!acceptsJsonType(agentProps.definition, "string")) throw new Error("agent root definition does not tolerate JSON strings");
if (!acceptsJsonType(workProps.target, "string")) throw new Error("work root target does not tolerate JSON strings");

const delegate = {
  action: "delegate",
  name: "reviewer",
  prompt: "Review the diff",
  definition: { description: "Read-only reviewer", prompt: "Read evidence and report", tools: ["read"] },
};
if (!Value.Check(AgentActionParams, delegate)) {
  throw new Error(`delegate payload with object definition rejected: ${JSON.stringify([...Value.Errors(AgentActionParams, delegate)])}`);
}
if (Value.Check(AgentActionParams, { action: "delegate", name: "reviewer", prompt: "p", bogus: 1 })) {
  throw new Error("delegate payload with unknown extra property accepted");
}
if (Value.Check(AgentActionParams, { action: "inspect", name: "reviewer" })) {
  throw new Error("inspect payload without session accepted");
}
if (!Value.Check(WorkToolParams, { action: "assign", id: "w1", target: { session: "s1" } })) {
  throw new Error("work assign payload with object target rejected");
}
if (!Value.Check(AgentActionParams, { action: "delegate", name: "reviewer", prompt: "p", definition: JSON.stringify(delegate.definition) })) {
  throw new Error("delegate payload with stringified definition rejected by validation");
}
if (!Value.Check(WorkToolParams, { action: "assign", id: "w1", target: JSON.stringify({ session: "s1" }) })) {
  throw new Error("work assign payload with stringified target rejected by validation");
}

const normalizedAgent = normalizeCoordinationParams(
  { action: "delegate", name: "reviewer", prompt: "p", definition: JSON.stringify(delegate.definition), resources: JSON.stringify(["board"]) } as Record<string, unknown>,
  ["definition", "resources"],
);
if (typeof normalizedAgent.definition !== "object" || normalizedAgent.definition === null) throw new Error("stringified definition not parsed");
if (!Array.isArray(normalizedAgent.resources)) throw new Error("stringified resources not parsed");

const normalizedWork = normalizeCoordinationParams(
  { action: "assign", id: "w1", target: JSON.stringify({ session: "s1" }), dependsOn: JSON.stringify(["w0"]), supersedes: JSON.stringify(["w9"]) } as Record<string, unknown>,
  ["target", "dependsOn", "supersedes"],
);
if (typeof normalizedWork.target !== "object" || normalizedWork.target === null) throw new Error("stringified target not parsed");
if (!Array.isArray(normalizedWork.dependsOn) || !Array.isArray(normalizedWork.supersedes)) throw new Error("stringified work arrays not parsed");

const plain = normalizeCoordinationParams({ verify: "run tests", prompt: "not json" } as Record<string, unknown>, ["verify", "prompt", "definition"]);
if (plain.verify !== "run tests" || plain.prompt !== "not json" || "definition" in plain) {
  throw new Error("plain string parameters mutated or absent keys invented");
}

console.log("TOOL_PARAM_SCHEMA_OK");
