/** Wire structure only. Parent validators remain the authority for all values. */
type Schema = Record<string, unknown>;
export type LearningOutputKind = "memory-selector" | "memory-delta" | "memory-amendment" | "memory-semantic-amendment" | "memory-combined-amendment" | "memory-retained-amendment" | "memory-body-review" | "memory-coverage-review";
/** Fresh producer format only; legacy readers and materialized plans stay compatible. */
export function assertFreshMemoryProjectOutput(value: unknown): void {
  if (!value || typeof value !== "object" || Array.isArray(value)) return;
  const items = (value as Record<string, unknown>).newMemories;
  if (!Array.isArray(items)) return;
  items.forEach((value, index) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return;
    const item = value as Record<string, unknown>;
    if (item.kind !== "project") return;
    const has = (key: string) => Object.hasOwn(item, key);
    if (!has("content") && (has("knowledge") && !has("evidence") && !has("sourceExcerpt")
      || has("sourceExcerpt") && item.classification === "private" && !has("knowledge"))) return;
    throw new Error(`Fresh Memory project output is invalid: newMemories[${index}] requires knowledge or a private sourceExcerpt`);
  });
}
const string: Schema = {type: "string"};
const integer = (minimum: number): Schema => ({type: "integer", minimum});
const object = (properties: Record<string, Schema>, required: string[]): Schema => ({type: "object", properties, required, additionalProperties: false});
const array = (items: Schema, minimum?: number, maximum?: number): Schema => ({type: "array", items,
  ...(minimum !== undefined ? {minItems: minimum} : {}), ...(maximum !== undefined ? {maxItems: maximum} : {})});
const role: Schema = {type: "string", enum: ["user", "toolResult"]};
export interface MemoryCitationDomain {indices: number[]; refs: string[]}
const citationSchema = (domain?: MemoryCitationDomain, referenceOverride?: Schema): Schema => {
  const reference: Schema = domain ? referenceOverride ?? {type: "string", enum: domain.refs} : string;
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
const memoryDocument: Schema = {...string, description: "Complete Markdown including name/description/type frontmatter and a non-empty grounded knowledge body; discovery metadata alone is not a body", pattern: "^---\\r?\\n[\\s\\S]*?\\r?\\n---\\r?\\n[\\s\\S]*\\S[\\s\\S]*$"};
const knowledgeSchema = (evidence: Schema, sourceSelection = false): Schema => {
  const text = object({text: {type: "string", minLength: 1}, citationIndexes: array({type: "integer", minimum: 0, maximum: 7}, 1, 8)},
    ["text", "citationIndexes"]);
  return object({sourceCitations: evidence, units: array(sourceSelection ? {anyOf: [text,
    object({sourceCitationIndex: {type: "integer", minimum: 0, maximum: 7}}, ["sourceCitationIndex"])]} : text, 1, 32)},
  ["sourceCitations", "units"]);
};
const operationSchema = (evidence: Schema, retainedBodyReuse = false, atomicKnowledge = false): Schema => {
const common = {name: string, classification, evidence, observations};
return {anyOf: [
  object({...common, kind: {type: "string", const: "rewrite"}, content: memoryDocument, contentSha256: string}, ["name", "kind", "classification", ...(retainedBodyReuse ? [] : ["content"]), "evidence"]),
  object({...common, kind: {type: "string", const: "delete"}, verdict: {type: "string", enum: ["CONTRADICTED", "SUPERSEDED", "SUBSUMED"]}, preservedIn: array(string, 1)}, ["name", "kind", "classification", "verdict", "preservedIn", "evidence"]),
  ...(atomicKnowledge ? [object({name: string, classification, kind: {type: "string", const: "rewrite"},
    knowledge: knowledgeSchema(evidence), description: string}, ["name", "kind", "classification", "knowledge"])] : []),
]};
};
const identity = {runId: string, scopeKey: string, scopeDigest: string, artifactHash: string, snapshotDigest: string};

export function learningOutputSchema(kind: unknown, domain?: MemoryCitationDomain, candidateIds?: readonly string[], bodyCount?: number,
  withdrawalCandidateIds?: readonly string[], bodyReferences = false, atomicKnowledge = false): Schema | undefined {
  if (kind === "memory-coverage-review") {
    if (!Number.isSafeInteger(bodyCount) || bodyCount! < 0 || bodyCount! > 32) throw new Error("Invalid complete Memory coverage count");
    const text = {type: "string", minLength: 1, maxLength: 2000};
    const witnessRef = {type: "string", pattern: "^[mp][0-9]+\\.b0\\.l[1-9][0-9]*(?:\\.c[0-9]+-[1-9][0-9]*)?$"};
    const witness = bodyReferences ? object({ref: witnessRef, endRef: witnessRef}, ["ref"]) : text;
    const sourceRef = bodyReferences ? {type: "string", maxLength: 128,
      pattern: "^e(?:0|[1-9][0-9]*)\\.b(?:0|[1-9][0-9]*)\\.[lp][1-9][0-9]*(?:\\.c(?:0|[1-9][0-9]*)-[1-9][0-9]*)?$"} : string;
    const sourceSelection = object({ref: sourceRef, endRef: sourceRef}, ["ref"]);
    const refs = array(sourceSelection, 1, 8);
    const fact = {statement: text, evidence: refs};
    const condition = {...fact, bodyQuote: {anyOf: [witness, {type: "null"}]}};
    const judgment = object({
      scope: {anyOf: [
        object({basis: {type: "string", enum: ["requested", "optional"]}, statement: text, evidence: refs},
          ["basis", "statement", "evidence"]),
        object({basis: {type: "string", const: "predecessor"}, statement: text, predecessorQuote: witness,
          evidence: array(sourceSelection, 0, 8)},
          ["basis", "statement", "predecessorQuote", "evidence"]),
      ]},
      claims: array(object({...condition, conditions: array(object(condition, Object.keys(condition)), 0, 16)},
        [...Object.keys(condition), "conditions"]), 1, 16),
      uncovered: array(object(fact, Object.keys(fact)), 0, 16),
      verdict: {type: "string", enum: ["covered", "incomplete", "uncertain"]},
    }, ["scope", "claims", "uncovered", "verdict"]);
    const location = object({targetIndex: integer(0), bodyQuote: witness}, ["targetIndex", "bodyQuote"]);
    const obligation = {statement: text, coveredBy: array(location, 0, 8),
      status: {type: "string", enum: ["covered", "missing", "uncertain"]}};
    const plan = object({verdict: {type: "string", enum: ["covered", "incomplete", "uncertain"]},
      obligations: array({anyOf: [
        object({...obligation, basis: {type: "string", const: "requested"}, evidence: refs},
          [...Object.keys(obligation), "basis", "evidence"]),
        object({...obligation, basis: {type: "string", const: "predecessor"}, predecessorName: string, predecessorQuote: witness,
          evidence: array(sourceSelection, 0, 8)},
          [...Object.keys(obligation), "basis", "predecessorName", "predecessorQuote", "evidence"]),
      ]}, 0, 32)}, ["verdict", "obligations"]);
    const slots = Object.fromEntries(Array.from({length: bodyCount!}, (_, index) => [String(index), judgment]));
    return object({plan, reviews: object(slots, Object.keys(slots))}, ["plan", "reviews"]);
  }
  if (kind === "memory-body-review") {
    if (!Number.isSafeInteger(bodyCount) || bodyCount! < 1 || bodyCount! > 32) throw new Error("Invalid complete Memory body count");
    const judgment = object({verdict: {type: "string", enum: ["consistent", "contradictory", "uncertain"]},
      conflictingQuotes: array({type: "string", minLength: 1, maxLength: 2000}, 0, 8), reason: string},
    ["verdict", "conflictingQuotes", "reason"]);
    const slots = Object.fromEntries(Array.from({length: bodyCount!}, (_, index) => [String(index), judgment]));
    return object({reviews: object(slots, Object.keys(slots))}, ["reviews"]);
  }
  const empty = domain !== undefined && !domain.indices.length && !domain.refs.length;
  // The complete catalog was repeated ten times in a real delta request.
  // Local references preserve every choice and constraint without duplicating it.
  const reference: Schema = domain?.refs.length ? {$ref: "#/$defs/memorySourceReference"}
    : domain ? {type: "string", enum: domain.refs} : string;
  const withReference = (schema: Schema): Schema => domain?.refs.length
    ? {...schema, $defs: {memorySourceReference: {type: "string", enum: domain.refs}}} : schema;
  const evidence = array(citationSchema(empty ? undefined : domain, reference), 1, 8);
  const operation = operationSchema(evidence, kind === "memory-retained-amendment" || kind === "memory-combined-amendment", atomicKnowledge);
  if (kind === "memory-selector") return object({
    selectedIndices: array(integer(0)), memory: {type: "boolean"}, harness: {type: "boolean"}, agents: {type: "boolean"}, reason: string,
  }, ["selectedIndices", "memory", "harness", "agents", "reason"]);
  if (kind === "memory-delta" || kind === "memory-retained-amendment") return withReference(object({kind: {type: "string", const: "incremental-memory-plan"}, version: {type: "integer", const: 1}, schemaVersion: {type: "integer", const: 1}, ...identity,
    operations: array(operation, undefined, empty ? 0 : undefined), newMemories: array({anyOf: [object({name: string, kind: {type: "string", enum: kind === "memory-delta" ? ["preference"] : ["project", "preference"]}, classification, content: memoryDocument, evidence}, ["name", "kind", "content", "evidence"]),
      object({name: string, kind: {type: "string", const: "project"}, classification: {type: "string", const: "private"}, sourceExcerpt: object({ref: reference, endRef: reference}, ["ref"]), evidence}, ["name", "kind", "classification", "sourceExcerpt", "evidence"]),
      ...(kind === "memory-delta" ? [object({name: string, kind: {type: "string", const: "project"}, classification,
        description: {type: "string", minLength: 1, maxLength: 120}, knowledge: knowledgeSchema(evidence, true)},
      ["name", "kind", "classification", "description", "knowledge"])] : [])]}, undefined, empty ? 0 : undefined),
  }, ["kind", "version", "schemaVersion", ...Object.keys(identity), "operations", "newMemories"]));
  // The producer must include knowledge after metadata. Parent validation also
  // checks the first frontmatter block, intent, citations and full source truth.
  if (kind === "memory-amendment" || kind === "memory-semantic-amendment" || kind === "memory-combined-amendment") {
    const inheritedSources = kind !== "memory-amendment";
    const candidateId = candidateIds?.length ? {type: "string", enum: candidateIds} : string;
    const patch = object({candidateId, content: memoryDocument, evidence}, ["candidateId", ...(inheritedSources ? [] : ["evidence"])]);
    if (inheritedSources) {
      if (candidateIds?.length && candidateIds.every(id => /^(operations|newMemories):\d+:[a-f0-9]{64}$/.test(id))) {
        (patch.properties as Record<string, Schema>).candidateRef = {type: "string", enum: candidateIds.map(id => id.slice(0, id.lastIndexOf(":")))};
        patch.required = [];
        patch.allOf = [{anyOf: [
          {required: ["candidateId"], not: {required: ["candidateRef"]}},
          {required: ["candidateRef"], not: {required: ["candidateId"]}},
        ]}];
      }
      (patch.properties as Record<string, Schema>).sourceExcerpt = object({ref: reference, endRef: reference}, ["ref"]);
      // Parent admission remains candidate-specific. Citation-only contracts do
      // not offer this alternative; semantic workers must explicitly select it.
      patch.anyOf = [
        {required: ["content"], not: {required: ["sourceExcerpt"]}},
        {required: ["evidence"], not: {required: ["sourceExcerpt"]}},
        {required: ["sourceExcerpt", "evidence"], not: {required: ["content"]}},
      ];
      if (atomicKnowledge) {
        (patch.properties as Record<string, Schema>).knowledge = knowledgeSchema(evidence);
        (patch.properties as Record<string, Schema>).description = string;
        patch.anyOf = [...(patch.anyOf as Schema[]).map(branch => ({...branch, not: {anyOf: [branch.not, {required: ["knowledge"]}]}})),
          {required: ["knowledge"], not: {anyOf: [{required: ["content"]}, {required: ["sourceExcerpt"]}, {required: ["evidence"]}]}}];
      }
    }
    const withdrawalIds = withdrawalCandidateIds ?? [];
    if (withdrawalIds.length && (!inheritedSources || new Set(withdrawalIds).size !== withdrawalIds.length
      || withdrawalIds.some(id => !/^newMemories:\d+:[a-f0-9]{64}$/.test(id) || !candidateIds?.includes(id)))) {
      throw new Error("Invalid parent Memory withdrawal domain");
    }
    const withdrawal = object({candidateId: {type: "string", enum: withdrawalIds},
      candidateRef: {type: "string", enum: withdrawalIds.map(id => id.slice(0, id.lastIndexOf(":")))},
      reason: {type: "string", enum: ["insufficient-evidence", "not-reusable"]}}, ["reason"]);
    withdrawal.anyOf = [{required: ["candidateId"], not: {required: ["candidateRef"]}},
      {required: ["candidateRef"], not: {required: ["candidateId"]}}];
    const schema = object({kind: {type: "string", const: "incremental-memory-amendment"}, version: {type: "integer", const: 1}, ...identity,
      replacements: array(patch, undefined, empty || candidateIds?.length === 0 ? 0 : undefined),
      ...(withdrawalIds.length ? {withdrawals: array(withdrawal, 0, 32)} : {}),
      ...(kind === "memory-combined-amendment" ? {operations: array(operation, undefined, empty ? 0 : undefined)} : {}),
    }, ["kind", "version", ...Object.keys(identity), "replacements", ...(kind === "memory-combined-amendment" ? ["operations"] : [])]);
    // Combined patches cover both sets, or explicitly decline all correction.
    // Shape cannot prove complete names/IDs or source support; the parent does.
    if (kind === "memory-combined-amendment") schema.anyOf = [
      {properties: {replacements: {minItems: 1}, operations: {minItems: 1}}},
      {properties: {replacements: {maxItems: 0}, operations: {maxItems: 0}, ...(withdrawalIds.length ? {withdrawals: {maxItems: 0}} : {})}},
      ...(withdrawalIds.length ? [{required: ["withdrawals"], properties: {withdrawals: {minItems: 1}, operations: {minItems: 1}}}] : []),
    ];
    return withReference(schema);
  }
  return undefined;
}
