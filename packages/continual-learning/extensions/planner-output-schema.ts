/** Wire structure only. Parent validators remain the authority for all values. */
type Schema = Record<string, unknown>;
export type LearningOutputKind = "memory-selector" | "memory-delta" | "memory-amendment" | "memory-combined-amendment" | "memory-body-review";
const string: Schema = {type: "string"};
const integer = (minimum: number): Schema => ({type: "integer", minimum});
const object = (properties: Record<string, Schema>, required: string[]): Schema => ({type: "object", properties, required, additionalProperties: false});
const array = (items: Schema, minimum?: number, maximum?: number): Schema => ({type: "array", items,
  ...(minimum !== undefined ? {minItems: minimum} : {}), ...(maximum !== undefined ? {maxItems: maximum} : {})});
const role: Schema = {type: "string", enum: ["user", "toolResult"]};
export interface MemoryCitationDomain {indices: number[]; refs: string[]}
const citationSchema = (domain?: MemoryCitationDomain): Schema => {
  const reference: Schema = domain ? {type: "string", enum: domain.refs} : string;
  // A complete parent catalog makes generation a typed position selection.
  // Legacy coordinate/quote inputs remain supported when no catalog is supplied.
  if (domain) return object({ref: reference, endRef: reference, role}, ["ref"]);
  const index: Schema = integer(0);
  return {anyOf: [
  object({ref: reference, endRef: reference, role}, ["ref"]),
  object({index, quote: {type: "string", minLength: 1, maxLength: 2000}, role}, ["index", "quote"]),
  object({index, role, quote: string, lines: object({
    block: integer(0), start: integer(1), end: integer(1), source: {type: "string", enum: ["patch"]},
    characters: object({start: integer(0), end: integer(1)}, ["start", "end"]),
  }, ["block", "start", "end"])}, ["index", "lines"]),
]};
};
const classification: Schema = {type: "string", enum: ["safe", "private"]};
const observations = array(object({path: string, status: {type: "string", enum: ["found", "missing", "updated"]}}, ["path", "status"]), 1, 32);
const operationSchema = (evidence: Schema): Schema => {
const common = {name: string, classification, evidence, observations};
return {anyOf: [
  object({...common, kind: {type: "string", const: "rewrite"}, content: string, contentSha256: string}, ["name", "kind", "classification", "content", "evidence"]),
  object({...common, kind: {type: "string", const: "delete"}, verdict: {type: "string", enum: ["CONTRADICTED", "SUPERSEDED", "SUBSUMED"]}, preservedIn: array(string, 1)}, ["name", "kind", "classification", "verdict", "preservedIn", "evidence"]),
]};
};
const identity = {runId: string, scopeKey: string, scopeDigest: string, artifactHash: string, snapshotDigest: string};

export function learningOutputSchema(kind: unknown, domain?: MemoryCitationDomain, candidateIds?: readonly string[], bodyCount?: number): Schema | undefined {
  if (kind === "memory-body-review") {
    if (!Number.isSafeInteger(bodyCount) || bodyCount! < 1 || bodyCount! > 32) throw new Error("Invalid complete Memory body count");
    const judgment = object({verdict: {type: "string", enum: ["consistent", "contradictory", "uncertain"]},
      conflictingQuotes: array({type: "string", minLength: 1, maxLength: 2000}, 0, 8), reason: string},
    ["verdict", "conflictingQuotes", "reason"]);
    const slots = Object.fromEntries(Array.from({length: bodyCount!}, (_, index) => [String(index), judgment]));
    return object({reviews: object(slots, Object.keys(slots))}, ["reviews"]);
  }
  const empty = domain !== undefined && !domain.indices.length && !domain.refs.length;
  const evidence = array(citationSchema(empty ? undefined : domain), 1, 8);
  const operation = operationSchema(evidence);
  if (kind === "memory-selector") return object({
    selectedIndices: array(integer(0)), memory: {type: "boolean"}, harness: {type: "boolean"}, agents: {type: "boolean"}, reason: string,
  }, ["selectedIndices", "memory", "harness", "agents", "reason"]);
  if (kind === "memory-delta") return object({kind: {type: "string", const: "incremental-memory-plan"}, version: {type: "integer", const: 1}, schemaVersion: {type: "integer", const: 1}, ...identity,
    operations: array(operation, undefined, empty ? 0 : undefined), newMemories: array(object({name: string, kind: {type: "string", enum: ["project", "preference"]}, classification, content: string, evidence}, ["name", "kind", "content", "evidence"]), undefined, empty ? 0 : undefined),
  }, ["kind", "version", "schemaVersion", ...Object.keys(identity), "operations", "newMemories"]);
  if (kind === "memory-amendment" || kind === "memory-combined-amendment") return object({kind: {type: "string", const: "incremental-memory-amendment"}, version: {type: "integer", const: 1}, ...identity,
    replacements: array(object({candidateId: candidateIds?.length ? {type: "string", enum: candidateIds} : string, content: string, evidence}, ["candidateId", "evidence"]), undefined, empty || candidateIds?.length === 0 ? 0 : undefined),
    ...(kind === "memory-combined-amendment" ? {operations: array(operation, undefined, empty ? 0 : undefined)} : {}),
  }, ["kind", "version", ...Object.keys(identity), "replacements", ...(kind === "memory-combined-amendment" ? ["operations"] : [])]);
  return undefined;
}
