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
    if (!has("content") && has("knowledge") && !has("evidence") && !has("sourceExcerpt")) {
      const knowledge = item.knowledge as Record<string, unknown> | undefined;
      if (Array.isArray(knowledge?.units)) knowledge.units.forEach((value, unitIndex) => {
        const unit = value && typeof value === "object" ? value as Record<string, unknown> : undefined;
        if (unit && (Object.hasOwn(unit, "sourceCitationIndex") || Object.hasOwn(unit, "fileSourceRef"))) {
          throw new Error(`Fresh Memory project output is invalid: newMemories[${index}].knowledge.units[${unitIndex}] requires an atomic declared-api-relation or cited text`);
        }
      });
      return;
    }

    throw new Error(`Fresh Memory project output is invalid: newMemories[${index}] requires knowledge`);
  });
}
/** Fresh file witness and its catalog are one repairable generation value. */
export function hasTypedMemorySourceUnits(value: unknown): boolean {
  const items = value && typeof value === "object" ? (value as Record<string, unknown>).newMemories : undefined;
  return Array.isArray(items) && items.some(value => {
    const item = value && typeof value === "object" ? value as Record<string, unknown> : undefined;
    const knowledge = item?.knowledge as Record<string, unknown> | undefined;
    return item?.kind === "project" && Array.isArray(knowledge?.units) && knowledge.units.some(unit =>
      unit && typeof unit === "object" && (Object.hasOwn(unit, "fileSourceRef") || (unit as Record<string, unknown>).kind === "declared-api-relation"));
  });
}

const string: Schema = {type: "string"};
const integer = (minimum: number): Schema => ({type: "integer", minimum});
const object = (properties: Record<string, Schema>, required: string[]): Schema => ({type: "object", properties, required, additionalProperties: false});
const array = (items: Schema, minimum?: number, maximum?: number): Schema => ({type: "array", items,
  ...(minimum !== undefined ? {minItems: minimum} : {}), ...(maximum !== undefined ? {maxItems: maximum} : {})});
const role: Schema = {type: "string", enum: ["user", "toolResult"]};
export interface MemoryCitationDomain {indices: number[]; refs: string[]; fileRefs?: string[]}
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
const memoryDescription: Schema = {type: "string", minLength: 1, maxLength: 120,
  description: "Non-empty single-line discovery claim; the parent also enforces the exact 120 UTF-16 code-unit bound"};
const knowledgeSchema = (evidence: Schema): Schema => {
  const text = object({text: {type: "string", minLength: 1}, citationIndexes: array({type: "integer", minimum: 0, maximum: 7}, 1, 8)},
    ["text", "citationIndexes"]);
  return object({sourceCitations: evidence, units: array(text, 1, 32)}, ["sourceCitations", "units"]);
};
const operationSchema = (evidence: Schema, retainedBodyReuse = false, atomicKnowledge = false): Schema => {
const common = {name: string, classification, evidence, observations};
return {anyOf: [
  object({...common, kind: {type: "string", const: "rewrite"}, content: memoryDocument, contentSha256: string}, ["name", "kind", "classification", ...(retainedBodyReuse ? [] : ["content"]), "evidence"]),
  object({...common, kind: {type: "string", const: "delete"}, verdict: {type: "string", enum: ["CONTRADICTED", "SUPERSEDED", "SUBSUMED"]}, preservedIn: array(string, 1)}, ["name", "kind", "classification", "verdict", "preservedIn", "evidence"]),
  ...(atomicKnowledge ? [object({name: string, classification, kind: {type: "string", const: "rewrite"},
    knowledge: knowledgeSchema(evidence), description: memoryDescription}, ["name", "kind", "classification", "knowledge"])] : []),
]};
};
const identity = {runId: string, scopeKey: string, scopeDigest: string, artifactHash: string, snapshotDigest: string};

export function learningOutputSchema(kind: unknown, domain?: MemoryCitationDomain, candidateIds?: readonly string[], bodyCount?: number,
  withdrawalCandidateIds?: readonly string[], bodyReferences = false, atomicKnowledge = false, requestedUserEntryIndices?: readonly number[]): Schema | undefined {
  if (kind === "memory-coverage-review") {
    if (!Number.isSafeInteger(bodyCount) || bodyCount! < 0 || bodyCount! > 32) throw new Error("Invalid complete Memory coverage count");
    const native = requestedUserEntryIndices !== undefined;
    if (native && (!bodyReferences || !Array.isArray(requestedUserEntryIndices)
      || requestedUserEntryIndices.some(index => !Number.isSafeInteger(index) || index < 0)
      || new Set(requestedUserEntryIndices).size !== requestedUserEntryIndices.length
      || Buffer.byteLength(JSON.stringify({userEntryIndices: requestedUserEntryIndices})) > 16_000)) throw new Error("Invalid native Memory coverage user domain");
    const text = {type: "string", minLength: 1, maxLength: 2000};
    const witnessRef = {type: "string", pattern: "^[mp][0-9]+\\.b0\\.l[1-9][0-9]*(?:\\.c[0-9]+-[1-9][0-9]*)?$"};
    const range = (ref: Schema): Schema => native ? {anyOf: [object({ref}, ["ref"]), object({ref, endRef: ref}, ["ref", "endRef"])]}
      : object({ref, endRef: ref}, ["ref"]);
    const witness = bodyReferences ? range(witnessRef) : text;
    const sourceRef = bodyReferences ? {type: "string", maxLength: 128,
      pattern: "^e(?:0|[1-9][0-9]*)\\.b(?:0|[1-9][0-9]*)\\.[lp][1-9][0-9]*(?:\\.c(?:0|[1-9][0-9]*)-[1-9][0-9]*)?$"} : string;
    const sourceSelection = range(sourceRef);
    const refs = array(sourceSelection, 1, 8);
    const requestedRefs = native ? array(range({$ref: "#/$defs/requestedUserSourceReference"}), 1, 8) : refs;
    const fact = {statement: text, evidence: refs};
    const condition = {...fact, bodyQuote: {anyOf: [witness, {type: "null"}]}};
    const judgment = object({
      scope: {anyOf: [
        ...(native ? [
          ...(requestedUserEntryIndices.length ? [object({basis: {type: "string", enum: ["requested"]}, statement: text, evidence: requestedRefs}, ["basis", "statement", "evidence"])] : []),
          object({basis: {type: "string", enum: ["optional"]}, statement: text, evidence: refs}, ["basis", "statement", "evidence"]),
        ] : [object({basis: {type: "string", enum: ["requested", "optional"]}, statement: text, evidence: refs}, ["basis", "statement", "evidence"])]),
        object({basis: native ? {type: "string", enum: ["predecessor"]} : {type: "string", const: "predecessor"}, statement: text, predecessorQuote: witness,
          evidence: array(sourceSelection, 0, 8)},
          ["basis", "statement", "predecessorQuote", "evidence"]),
      ]},
      claims: array(object({...condition, conditions: array(object(condition, Object.keys(condition)), 0, 16)},
        [...Object.keys(condition), "conditions"]), 1, 16),
      uncovered: array(object(fact, Object.keys(fact)), 0, 16),
      verdict: {type: "string", enum: ["covered", "incomplete", "uncertain"]},
    }, ["scope", "claims", "uncovered", "verdict"]);
    const location = object({targetIndex: native && bodyCount! > 0 ? {...integer(0), maximum: bodyCount! - 1} : integer(0), bodyQuote: witness}, ["targetIndex", "bodyQuote"]);
    const obligation = {statement: text, coveredBy: array(location, 0, native && bodyCount === 0 ? 0 : 8),
      status: {type: "string", enum: ["covered", "missing", "uncertain"]}};
    const plan = object({verdict: {type: "string", enum: ["covered", "incomplete", "uncertain"]},
      obligations: array({anyOf: [
        ...(!native || requestedUserEntryIndices.length ? [object({...obligation, basis: native ? {type: "string", enum: ["requested"]} : {type: "string", const: "requested"}, evidence: requestedRefs},
          [...Object.keys(obligation), "basis", "evidence"])] : []),
        object({...obligation, basis: native ? {type: "string", enum: ["predecessor"]} : {type: "string", const: "predecessor"}, predecessorName: string, predecessorQuote: witness,
          evidence: array(sourceSelection, 0, 8)},
          [...Object.keys(obligation), "basis", "predecessorName", "predecessorQuote", "evidence"]),
      ]}, 0, 32)}, ["verdict", "obligations"]);
    const slots = Object.fromEntries(Array.from({length: bodyCount!}, (_, index) => [String(index), native ? {$ref: "#/$defs/coverageJudgment"} : judgment]));
    const schema = object({plan, reviews: object(slots, Object.keys(slots))}, ["plan", "reviews"]);
    return native ? {...schema, $defs: {coverageJudgment: judgment,
      ...(requestedUserEntryIndices.length ? {requestedUserSourceReference: {...sourceRef,
        pattern: `^e(?:${requestedUserEntryIndices.join("|")})\\.b(?:0|[1-9][0-9]*)\\.[lp][1-9][0-9]*(?:\\.c(?:0|[1-9][0-9]*)-[1-9][0-9]*)?$`}} : {})}} : schema;
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
      ...(kind !== "memory-delta" ? [object({name: string, kind: {type: "string", const: "project"}, classification: {type: "string", const: "private"}, sourceExcerpt: object({ref: reference, endRef: reference}, ["ref"]), evidence}, ["name", "kind", "classification", "sourceExcerpt", "evidence"])] : []),
      ...(kind === "memory-delta" ? [object({name: string, kind: {type: "string", const: "project"}, classification,
        description: memoryDescription, knowledge: knowledgeSchema(evidence)},
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
        (patch.properties as Record<string, Schema>).description = memoryDescription;
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

export type MemoryOutputIdentity = {runId: string; scopeKey: string; scopeDigest: string; artifactHash: string; snapshotDigest: string};

/** Entry roles only, not an enumerated citation catalog or mutation authority. */
export type NativeMemoryCoverageBinding = {userEntryIndices: readonly number[]};
export function nativeMemoryCoverageSchema(binding: NativeMemoryCoverageBinding, count: number): Schema {
  if (!binding || typeof binding !== "object" || Array.isArray(binding)
    || Object.keys(binding).join(",") !== "userEntryIndices" || !Array.isArray(binding.userEntryIndices)
    || Buffer.byteLength(JSON.stringify(binding)) > 16_000) throw new Error("Invalid native Memory coverage binding");
  const schema = learningOutputSchema("memory-coverage-review", undefined, undefined, count, undefined, true, false, binding.userEntryIndices)!;
  if (Buffer.byteLength(JSON.stringify(schema)) > 32_000) throw new Error("Native Memory coverage schema exceeds metadata bound");
  return schema;
}
export type NativeMemoryRepairBinding = {requiredTopLevelValues: MemoryOutputIdentity & {kind: "incremental-memory-amendment"; version: 1}; descriptionCandidateIds: readonly string[]; requiredDescriptionCandidateIds?: readonly string[]; sourceRoleUnitIds?: readonly string[]};

/** Narrow Responses profile for already admitted atomic semantic body repairs.
 * Source membership stays in complete task data and parent validation, rather
 * than a truncated/oversized service enum. This schema grants no write authority. */
export function nativeMemoryBodyRepairSchema(binding: NativeMemoryRepairBinding, candidateIds: readonly string[]): Schema {
  const fail = (): never => {throw new Error("Invalid parent-bound native Memory repair contract");};
  if (!binding || typeof binding !== "object" || Array.isArray(binding)
    || !["descriptionCandidateIds,requiredTopLevelValues", "descriptionCandidateIds,requiredDescriptionCandidateIds,requiredTopLevelValues", "descriptionCandidateIds,requiredTopLevelValues,sourceRoleUnitIds"].includes(Object.keys(binding).sort().join(","))
    || !binding.requiredTopLevelValues || typeof binding.requiredTopLevelValues !== "object" || Array.isArray(binding.requiredTopLevelValues)
    || Object.keys(binding.requiredTopLevelValues).sort().join(",") !== [...Object.keys(identity), "kind", "version"].sort().join(",")
    || binding.requiredTopLevelValues.kind !== "incremental-memory-amendment" || binding.requiredTopLevelValues.version !== 1
    || Object.keys(identity).some(key => {const value = (binding.requiredTopLevelValues as unknown as Record<string, unknown>)[key];return typeof value !== "string" || !value || Buffer.byteLength(value) > 512;})
    || !Array.isArray(candidateIds) || !candidateIds.length || candidateIds.length > 32
    || new Set(candidateIds).size !== candidateIds.length
    || candidateIds.some(id => typeof id !== "string" || !/^(?:operations|newMemories):(0|[1-9][0-9]*):[a-f0-9]{64}$/.test(id))
    || !Array.isArray(binding.descriptionCandidateIds) || new Set(binding.descriptionCandidateIds).size !== binding.descriptionCandidateIds.length
    || binding.descriptionCandidateIds.some(id => !candidateIds.includes(id))
    || binding.requiredDescriptionCandidateIds !== undefined && (!Array.isArray(binding.requiredDescriptionCandidateIds)
      || new Set(binding.requiredDescriptionCandidateIds).size !== binding.requiredDescriptionCandidateIds.length
      || binding.requiredDescriptionCandidateIds.some(id => !binding.descriptionCandidateIds.includes(id)))) return fail();
  const refs = candidateIds.map(id => id.slice(0, id.lastIndexOf(":")));
  if (new Set(refs).size !== refs.length) return fail();
  const sourceRef: Schema = {type: "string", minLength: 1, maxLength: 128,
    pattern: "^e(?:0|[1-9][0-9]*)\\.b(?:0|[1-9][0-9]*)\\.[lp][1-9][0-9]*(?:\\.c(?:0|[1-9][0-9]*)-[1-9][0-9]*)?$"};
  const selection: Schema = {anyOf: [object({ref: sourceRef}, ["ref"]), object({ref: sourceRef, endRef: sourceRef}, ["ref", "endRef"])]};
  if (binding.sourceRoleUnitIds !== undefined) {
    const ids = binding.sourceRoleUnitIds;
    if (candidateIds.length !== 1 || !candidateIds[0].startsWith("newMemories:0:") || binding.descriptionCandidateIds.length
      || binding.requiredDescriptionCandidateIds !== undefined || !Array.isArray(ids) || !ids.length || ids.length > 32
      || ids.some((id, index) => id !== `unit:${index}`)) return fail();
    const roleSelection: Schema = {anyOf: [selection, object({ref: sourceRef, role}, ["ref", "role"]),
      object({ref: sourceRef, endRef: sourceRef, role}, ["ref", "endRef", "role"])]};
    const replacement = object({candidateId: {type: "string", enum: [...candidateIds]}, evidence: array(roleSelection, 1, 8),
      units: array(object({unitId: {type: "string", enum: [...ids]}, citationIndexes: array({type: "integer", minimum: 0, maximum: 7}, 1, 8)},
        ["unitId", "citationIndexes"]), ids.length, ids.length)}, ["candidateId", "evidence", "units"]);
    return object({...Object.fromEntries(Object.entries(binding.requiredTopLevelValues).map(([key, value]) =>
      [key, {type: typeof value === "number" ? "integer" : "string", enum: [value]}])), replacements: array(replacement, 0, 1)},
      [...Object.keys(binding.requiredTopLevelValues), "replacements"]);
  }
  const knowledge = object({sourceCitations: array(selection, 1, 8), units: array(object({
    text: {type: "string", minLength: 1}, citationIndexes: array({type: "integer", minimum: 0, maximum: 7}, 1, 8),
  }, ["text", "citationIndexes"]), 1, 32)}, ["sourceCitations", "units"]);
  const candidateRef: Schema = {type: "string", enum: refs};
  const optional = candidateIds.filter(id => !binding.requiredDescriptionCandidateIds?.includes(id)).map(id => id.slice(0, id.lastIndexOf(":")));
  const patches: Schema[] = optional.length ? [object({candidateRef: {...candidateRef, enum: optional}, knowledge}, ["candidateRef", "knowledge"])] : [];
  if (binding.descriptionCandidateIds.length) patches.push(object({
    candidateRef: {type: "string", enum: binding.descriptionCandidateIds.map(id => id.slice(0, id.lastIndexOf(":")))},
    knowledge, description: {type: "string", minLength: 1, maxLength: 120},
  }, ["candidateRef", "knowledge", "description"]));
  return object({...Object.fromEntries(Object.entries(binding.requiredTopLevelValues).map(([key, value]) => [key, {type: typeof value === "number" ? "integer" : "string", enum: [value]}])),
    replacements: array({anyOf: patches}, 0, 32),
  }, [...Object.keys(binding.requiredTopLevelValues), "replacements"]);
}

export type NativeFreshMemoryBinding = {requiredTopLevelValues: MemoryOutputIdentity & {
  kind: "incremental-memory-plan"; version: 1; schemaVersion: 1;
}; selectedNames: readonly string[]};

/** Fresh empty-selection generation only. Complete source choices remain in
 * task DATA; the unchanged parent validates membership, source truth and intent. */
export function nativeFreshMemorySchema(binding: NativeFreshMemoryBinding): Schema {
  const fail = (): never => {throw new Error("Invalid parent-bound native fresh Memory contract");};
  const top = binding?.requiredTopLevelValues;
  if (!binding || typeof binding !== "object" || Array.isArray(binding)
    || Object.keys(binding).sort().join(",") !== "requiredTopLevelValues,selectedNames"
    || !top || typeof top !== "object" || Array.isArray(top)
    || Object.keys(top).sort().join(",") !== [...Object.keys(identity), "kind", "version", "schemaVersion"].sort().join(",")
    || top.kind !== "incremental-memory-plan" || top.version !== 1 || top.schemaVersion !== 1
    || Object.keys(identity).some(key => {const value = (top as unknown as Record<string, unknown>)[key];return typeof value !== "string" || !value || Buffer.byteLength(value) > 512;})
    || !Array.isArray(binding.selectedNames) || binding.selectedNames.length !== 0) return fail();
  const ref: Schema = {type: "string", minLength: 1, maxLength: 128,
    pattern: "^e(?:0|[1-9][0-9]*)\\.b(?:0|[1-9][0-9]*)\\.[lp][1-9][0-9]*(?:\\.c(?:0|[1-9][0-9]*)-[1-9][0-9]*)?$"};
  // Optional source role and range use strict, fully required alternatives;
  // null is never a substitute for an omitted field in the parent contract.
  const selection: Schema = {anyOf: [object({ref}, ["ref"]), object({ref, endRef: ref}, ["ref", "endRef"]),
    object({ref, role}, ["ref", "role"]), object({ref, endRef: ref, role}, ["ref", "endRef", "role"])]};
  const evidence = array(selection, 1, 8);
  const project = object({name: string, kind: {type: "string", enum: ["project"]}, classification,
    description: memoryDescription, knowledge: knowledgeSchema(evidence)}, ["name", "kind", "classification", "description", "knowledge"]);
  const preference = {name: string, kind: {type: "string", enum: ["preference"]}, content: memoryDocument, evidence};
  const proposals: Schema = {anyOf: [project, object(preference, Object.keys(preference)),
    object({...preference, classification}, [...Object.keys(preference), "classification"])]};
  return object({...Object.fromEntries(Object.entries(top).map(([key, value]) =>
    [key, {type: typeof value === "number" ? "integer" : "string", enum: [value]}])),
    operations: array({type: "null"}, 0, 0), newMemories: array(proposals, 0, 16),
  }, [...Object.keys(top), "operations", "newMemories"]);
}
