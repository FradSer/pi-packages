import fs from "node:fs/promises";
import {constants} from "node:fs";
import path from "node:path";
import {isMemoryFilename} from "./memory-files";
import {containsSensitiveMemoryMaterial, MAX_MEMORY_BYTES, MAX_SNAPSHOT_BYTES, normalizeSnapshotEvidence, sha256Digest, snapshotEditPatchText} from "./consolidation-run";
import {materializeMemoryKnowledge, resolveMemoryPlanCitations, memoryCitationDomain, memoryCitationReferenceMatches, memoryCitationReferenceCovers, MemoryCitationLocationError} from "./memory-citation-locations";
import {isObservedFunctionDeclaration, isCompleteOuterFunctionDeclaration} from "./memory-declaration-view";
import {MemoryRelationClosureError, declaredMemoryRelation, selectedMemoryRelationClosures, observedMemorySourceAliases, type MemoryRelationObligations, type SourceRoleRangeChoice} from "./memory-relation-closure";

type Row = Record<string, unknown>;
type Run = {manifest: {cwd: string}};
type Binding = {file: string; identity: string; digest: string};
type SelectedAtomicRelation = ReturnType<typeof declaredMemoryRelation>["relation"];
/** Only the parent collector can supply this grant; plan fields cannot. */
type AuditSources = {evidenceDigest: string; entryDigests: readonly string[]; requireAudit?: boolean};
const bindings = new WeakMap<Run, Binding[]>();
// Parent-only state through this run, including its admitted semantic correction.
const relationObligations = new WeakMap<Run, Map<string, MemoryRelationObligations>>();
const roleOnlyRejections = new WeakMap<Error, {run: Run; planDigest: string; snapshotDigest: string}>();
const record = (value: unknown): Row | undefined => value && typeof value === "object" && !Array.isArray(value) ? value as Row : undefined;
const message = (value: unknown) => record(record(value)?.message) ?? record(value);
function invalid(): never {throw new Error("Source excerpt is not bound to an eligible current project source observation");}

function excerptDescription(filename: string, quote: string): string {
  // These are literal text cues, never a declaration parse or API claim. Only inspect
  // the already source-bound excerpt; the complete record still needs review.
  const identifiers: string[] = [];
  const declarations = /^[ \t]*(?:export[ \t]+(?:default[ \t]+)?(?:declare[ \t]+)?)?(?:declare[ \t]+)?(?:async[ \t]+)?(?:function|class|interface|type|enum|const|let|var)[ \t]+([A-Za-z_$][\w$]*)(?=[\s(<:={;]|$)/gm;
  // A bounded excerpt is not a whole-language parse. Fall back to its filename
  // to avoid noisy cues from complete comments or multiline literals. Partial
  // citations can start inside such data; their cues only assert quoted text.
  const ambiguous = /\/\*|\*\/|`|\\\r?\n|'''|"""/.test(quote);
  for (const match of ambiguous ? [] : quote.matchAll(declarations)) {
    const name = match[1];
    if (name.length > 40 || identifiers.includes(name)) continue;
    if (`; text cues: ${[...identifiers, name].join(", ")}`.length > 60) continue;
    identifiers.push(name);
    if (identifiers.length === 3) break;
  }
  const prefix = "Observed source excerpt from ";
  const suffix = identifiers.length ? `; text cues: ${identifiers.join(", ")}` : "";
  const available = 120 - prefix.length - suffix.length;
  const location = filename.length <= available ? filename : `…${filename.slice(-(available - 1))}`;
  return `${prefix}${location}${suffix}`;
}

async function readSource(file: string): Promise<{text: string; binding: Binding}> {
  try {
    const before = await fs.lstat(file, {bigint: true});
    const identity = (stat: typeof before) => [stat.dev, stat.ino, stat.mode, stat.size, stat.mtimeNs, stat.ctimeNs].map(String).join(":");
    if (!before.isFile() || before.size > BigInt(MAX_SNAPSHOT_BYTES) || await fs.realpath(file) !== file) invalid();
    const handle = await fs.open(file, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
    try {
      if (identity(await handle.stat({bigint: true})) !== identity(before)) invalid();
      const buffer = Buffer.alloc(MAX_SNAPSHOT_BYTES + 1);
      let length = 0;
      while (length < buffer.length) {
        const {bytesRead} = await handle.read(buffer, length, buffer.length - length, null);
        if (!bytesRead) break;
        length += bytesRead;
      }
      if (length > MAX_SNAPSHOT_BYTES) invalid();
      const bytes = buffer.subarray(0, length);
      if (identity(await fs.lstat(file, {bigint: true})) !== identity(before) || await fs.realpath(file) !== file) invalid();
      const text = bytes.toString("utf8");
      if (!Buffer.from(text, "utf8").equals(bytes)) invalid();
      return {text, binding: {file, identity: identity(before), digest: sha256Digest(bytes)}};
    } finally {await handle.close();}
  } catch {return invalid();}
}

/** Source observations remain parent-bound even across a correction or subset.
 * Metadata detects permission/ABA changes; hashes bind complete source bytes. */
export async function assertSourceExcerptBindings(run: Run): Promise<void> {
  for (const expected of bindings.get(run) ?? []) {
    const {binding} = await readSource(expected.file);
    if (binding.identity !== expected.identity || binding.digest !== expected.digest) invalid();
  }
}

/** One provenance path for standalone excerpts and exact-source body units.
 * It returns data only; the outer transaction commits bindings after all units. */
async function resolveSourceSelection(run: Run, selection: unknown, rawEvidence: unknown, snapshot: unknown,
  audit?: AuditSources, completeDeclaration = false, sourceSpan?: {start: number; end: number}): Promise<{body: string; description: string; binding: Binding}> {
  const entries = record(snapshot)?.entries;
  if (!Array.isArray(entries)) invalid();
  const ref = record(selection);
  if (!ref || Object.keys(ref).some(key => !["ref", "endRef"].includes(key)) || typeof ref.ref !== "string") invalid();
  const selected = record(resolveMemoryPlanCitations({newMemories: [{evidence: [ref]}]}, snapshot))!;
  const selectedItem = (selected.newMemories as Row[])[0];
  const [citation] = normalizeSnapshotEvidence(selectedItem.evidence, snapshot);
  const resolved = record(resolveMemoryPlanCitations({newMemories: [{evidence: rawEvidence}]}, snapshot))!;
  const evidence = normalizeSnapshotEvidence((resolved.newMemories as Row[])[0].evidence, snapshot);
  if (!citation || !evidence.some(e => e.index === citation.index && e.quote.includes(citation.quote))) invalid();
  const result = message(entries[citation.index]);
  if (result?.role !== "toolResult" || !["read", "edit", "learning_read"].includes(String(result.toolName)) || result.isError !== false || typeof result.toolCallId !== "string") invalid();
  if (audit?.requireAudit && result.toolName !== "learning_read") invalid();
  const calls = entries.flatMap((entry, entryIndex) => {
    const row = message(entry);
    return row?.role === "assistant" && Array.isArray(row.content)
      ? row.content.flatMap(value => {const call = record(value);return call?.type === "toolCall" && call.id === result!.toolCallId ? [{call, entryIndex}] : [];}) : [];
  });
  const invocation = calls[0], args = record(invocation?.call.arguments);
  if (calls.length !== 1 || invocation.entryIndex >= citation.index || invocation.call.name !== result.toolName || typeof args?.path !== "string") invalid();
  if (entries.filter(entry => message(entry)?.role === "toolResult" && message(entry)?.toolCallId === result.toolCallId).length !== 1) invalid();
  if (result.toolName === "learning_read") {
    const details = record(result.details);
    if (!audit || audit.evidenceDigest !== sha256Digest(JSON.stringify(snapshot))
      || !audit.entryDigests.length || new Set(audit.entryDigests).size !== audit.entryDigests.length
      || audit.entryDigests.some(digest => entries.filter(entry => sha256Digest(JSON.stringify(entry)) === digest).length !== 1)
      || ![invocation.entryIndex, citation.index].every(index => audit.entryDigests.includes(sha256Digest(JSON.stringify(entries[index]))))
      || details?.readOnlyMaintenanceAudit !== true || details.sourcePath !== args!.path
      || typeof details.sourceSha256 !== "string" || !/^[a-f0-9]{64}$/.test(details.sourceSha256)) invalid();
  }
  let quote = citation.quote;
  if (result.toolName === "edit") {
    // Patch coordinates retain the original added-line markers as evidence.
    // Materialize only additions that the actual successful invocation supplied;
    // removals, headers and arbitrary result prose cannot become current source.
    const patch = snapshotEditPatchText(entries[citation.index]);
    const lines = quote.split("\n");
    if (!/^e\d+\.b0\.p\d+$/.test(ref.ref)
      || ref.endRef !== undefined && (typeof ref.endRef !== "string" || !/^e\d+\.b0\.p\d+$/.test(ref.endRef))
      || !patch?.includes(quote) || lines.some(line => !line.startsWith("+") || line.startsWith("+++"))) invalid();
    quote = lines.map(line => line.slice(1)).join("\n");
    if (!quote.trim() || !Array.isArray(args.edits)
      || !args.edits.some(value => {const edit = record(value);return typeof edit?.newText === "string" && edit.newText.includes(quote);})) invalid();
  } else if (/\.p\d+/.test(ref.ref)) invalid();
  const root = path.resolve(run.manifest.cwd), relative = path.relative(root, path.resolve(root, args!.path as string));
  if (!relative || path.isAbsolute(relative) || relative.split(path.sep).some(part => ["..", ".memory", ".pi", ".git"].includes(part.toLowerCase())) || /[\x00-\x1f\x7f`]/.test(relative)) invalid();
  const source = await readSource(path.join(await fs.realpath(root), relative));
  if (!source.text.includes(quote) || result.toolName === "learning_read"
    && record(result.details)?.sourceSha256 !== source.binding.digest) invalid();
  if (completeDeclaration) {
    const start = /^e\d+\.b0\.l(\d+)$/.exec(ref.ref);
    const end = /^e\d+\.b0\.l(\d+)$/.exec(String(ref.endRef ?? ref.ref));
    const offset = args.offset ?? 1;
    if (!/\.d\.(?:ts|mts|cts)$/.test(relative) || !start || !end || !Number.isSafeInteger(offset) || Number(offset) < 1
      || !isCompleteOuterFunctionDeclaration(source.text, quote, Number(offset) + Number(start[1]) - 1,
        Number(offset) + Number(end[1]) - 1)) invalid();
  }
  if (sourceSpan) {
    if (!Number.isSafeInteger(sourceSpan.start) || !Number.isSafeInteger(sourceSpan.end)
      || sourceSpan.start < 0 || sourceSpan.end <= sourceSpan.start || sourceSpan.end > source.text.length) invalid();
    const local = source.text.slice(sourceSpan.start, sourceSpan.end);
    if (!quote.includes(local)) invalid();
    quote = local;
  }
  const filename = relative.split(path.sep).join("/");
  const description = excerptDescription(filename, quote);
  const fence = "`".repeat(Math.max(3, ...[...quote.matchAll(/`+/g)].map(match => match[0].length + 1)));
  return {body: `Observed source excerpt from ${JSON.stringify(filename)}:\n\n${fence}text\n${quote}\n${fence}\n`,
    description, binding: source.binding};
}

function projectHeader(name: unknown, description: string): string {
  return `---\nname: ${JSON.stringify(name)}\ndescription: ${JSON.stringify(description)}\ntype: project\n---\n`;
}

function projectMetadataProblems(item: Row, position: string): Error[] {
  const errors: Error[] = [];
  if (item.classification !== "safe" && item.classification !== "private") errors.push(new Error(`${position}.classification must be safe or private`));
  if (Object.keys(item).some(key => !["name", "kind", "classification", "description", "knowledge"].includes(key))) errors.push(new Error(`${position} has unsupported project knowledge fields`));
  if (typeof item.description !== "string" || !item.description.trim() || item.description.length > 120 || /[\r\n]/.test(item.description)) {
    errors.push(new Error(`${position}.description must be a non-empty single-line string of 1..120 UTF-16 code units (actual=${typeof item.description === "string" ? item.description.length : "non-string"})`));
  }
  return errors;
}

/** Snapshot-only diagnostics before current-file reads or source bindings.
 * Original choices stay unchanged; closure obligations remain bound to the run. */
function preflightFreshMemoryPlan(run: Run, plan: Row, snapshot: unknown): void {
  const errors: Error[] = [];
  if (!Array.isArray(plan.newMemories) || plan.newMemories.length > 16) return;
  for (const [itemIndex, value] of plan.newMemories.entries()) {
    const item = record(value);
    if (item?.kind !== "project" || !Object.hasOwn(item, "knowledge")) continue;
    const position = `newMemories[${itemIndex}]`, knowledge = record(item.knowledge);
    errors.push(...projectMetadataProblems(item, position));
    const catalog = knowledge?.sourceCitations, units = knowledge?.units;
    const catalogBounded = Array.isArray(catalog) && catalog.length >= 1 && catalog.length <= 8;
    const unitsBounded = Array.isArray(units) && units.length >= 1 && units.length <= 32;
    if (!catalogBounded) errors.push(new Error(`${position}.knowledge.sourceCitations requires 1..8 citations`));
    if (!unitsBounded) errors.push(new Error(`${position}.knowledge.units requires 1..32 body units`));
    const selections: {position: string; value: unknown}[] = catalogBounded
      ? catalog.map((value, index) => ({position: `${position}.knowledge.sourceCitations[${index}]`, value})) : [];
    if (unitsBounded) for (const [index, value] of units.entries()) {
      const unit = record(value);
      if (unit?.kind !== "declared-api-relation") continue;
      // Legacy atomic input stays readable, while fresh producers use text.
      for (const role of ["factory", "owner", "member"]) selections.push({position: `${position}.knowledge.units[${index}].${role}`, value: unit[role]});
      try {declaredMemoryRelation(snapshot, unit, run.manifest.cwd);}
      catch (error) {errors.push(error instanceof MemoryRelationClosureError ? error : new Error(`${position}.knowledge has invalid declaration roles`));}
    }
    for (const selection of selections) {
      try {
        const resolved = record(resolveMemoryPlanCitations({newMemories: [{evidence: [selection.value]}]}, snapshot))!;
        normalizeSnapshotEvidence((resolved.newMemories as Row[])[0].evidence, snapshot);
      } catch (error) {
        errors.push(error instanceof MemoryCitationLocationError
          ? new MemoryCitationLocationError([`${selection.position}: ${error.message.replace("Memory citation locations are invalid: ", "")}`])
          : new Error(`${selection.position}: citation-gate-rejected`));
      }
    }
    if (catalogBounded && unitsBounded) {
      const name = String(item.name).toLowerCase();
      try {selectedMemoryRelationClosures(snapshot, knowledge, run.manifest.cwd, relationObligations.get(run)?.get(name), value => {
          if (!value.requirements.length) return;
          const retained = relationObligations.get(run) ?? new Map<string, MemoryRelationObligations>();
          retained.set(name, value);relationObligations.set(run, retained);
        });}
      catch (error) {
        if (error instanceof MemoryRelationClosureError) {
          if (error.obligations) {
            const retained = relationObligations.get(run) ?? new Map<string, MemoryRelationObligations>();
            retained.set(name, structuredClone(error.obligations));relationObligations.set(run, retained);
          }
          errors.push(error);
        } else errors.push(new Error(`${position}.knowledge: invalid source-role selection`));
      }
    }
  }
  if (!errors.length) return;
  if (errors.length === 1) {
    const error = errors[0];
    const manifest = record(run.manifest)!;
    const identityMatches = ["runId", "scopeKey", "scopeDigest", "snapshotDigest"].every(key =>
      typeof plan[key] === "string" && plan[key] === manifest[key]) && plan.artifactHash === manifest.snapshotDigest;
    if (identityMatches && error instanceof MemoryRelationClosureError && error.obligations?.requirements.length) {
      roleOnlyRejections.set(error, {run, planDigest: sha256Digest(JSON.stringify(plan)), snapshotDigest: sha256Digest(JSON.stringify(snapshot))});
    }
    throw error;
  }
  const message = "Fresh Memory proposal validation failed: " + errors.map(error => error.message).join("; ");
  if (Buffer.byteLength(message) > 32_000) throw new Error("Fresh Memory diagnostics exceed the unchanged 32KB metadata bound");
  const closure = errors.find(error => error instanceof MemoryRelationClosureError) as MemoryRelationClosureError | undefined;
  if (closure) throw new MemoryRelationClosureError(message, closure.snapshotProjectionDigest, closure.obligations);
  if (errors.every(error => error instanceof MemoryCitationLocationError)) throw new MemoryCitationLocationError(errors.map(error => error.message.replace("Memory citation locations are invalid: ", "")));
  throw new Error(message);
}

/** Only an actual sole source-role rejection can freeze one fresh text proposal. */
export function sourceRoleOnlyRepairAdmitted(run: Run, raw: unknown, snapshot: unknown, error: unknown): boolean {
  const admission = error instanceof Error ? roleOnlyRejections.get(error) : undefined;
  if (!admission) return false;
  if (admission.run !== run || admission.planDigest !== sha256Digest(JSON.stringify(raw))
    || admission.snapshotDigest !== sha256Digest(JSON.stringify(snapshot))) throw new Error("Bound source-role repair admission changed");
  const plan = record(raw), item = Array.isArray(plan?.newMemories) && plan.newMemories.length === 1 ? record(plan.newMemories[0]) : undefined;
  const knowledge = record(item?.knowledge), catalog = knowledge?.sourceCitations, units = knowledge?.units;
  if (plan?.kind !== "incremental-memory-plan" || plan.version !== 1 || plan.schemaVersion !== 1
    || Object.keys(plan).some(key => !["kind", "version", "schemaVersion", "runId", "scopeKey", "scopeDigest", "artifactHash", "snapshotDigest", "operations", "newMemories"].includes(key))
    || !Array.isArray(plan.operations) || plan.operations.length || !item || item.kind !== "project"
    || typeof item.name !== "string" || !isMemoryFilename(item.name) || projectMetadataProblems(item, "proposal").length
    || !Array.isArray(catalog) || !Array.isArray(units)
    || !relationObligations.get(run)?.has(item.name.toLowerCase())) return false;
  try {
    const materialized = materializeMemoryKnowledge(projectHeader(item.name, String(item.description)), knowledge, snapshot);
    if (Buffer.byteLength(materialized.content) > MAX_MEMORY_BYTES) return false;
  } catch {return false;}
  if (containsSensitiveMemoryMaterial(JSON.stringify(raw))) throw new Error("Sensitive source-role repair input");
  return true;
}

/** Frozen text keeps each original unit's supporting spans. Explicit larger
 * producer selections may cover them; another unit or equal text cannot. */
export function assertSourceRoleUnitSupport(original: unknown, corrected: unknown, snapshot: unknown, cwd: string): void {
  const before = record(original), after = record(corrected), entries = record(snapshot)?.entries;
  if (!before || !after || !Array.isArray(entries) || typeof cwd !== "string" || !cwd
    || !Array.isArray(before.sourceCitations) || !Array.isArray(after.sourceCitations)
    || !Array.isArray(before.units) || !Array.isArray(after.units) || before.units.length !== after.units.length) {
    throw new Error("Invalid source-role support context");
  }
  const originalRefs = before.sourceCitations, nextRefs = after.sourceCitations;
  for (const evidence of [originalRefs, nextRefs]) {
    const resolved = record(resolveMemoryPlanCitations({newMemories: [{evidence}]}, snapshot))!;
    normalizeSnapshotEvidence(record((resolved.newMemories as unknown[])[0])!.evidence, snapshot);
  }
  const indexes = (unit: unknown, length: number): number[] => {
    const value = record(unit)?.citationIndexes;
    if (!Array.isArray(value) || !value.length || value.length > 8
      || value.some(index => !Number.isSafeInteger(index) || index < 0 || index >= length)) throw new Error("Invalid source-role unit support references");
    return value as number[];
  };
  const observedIndices = [...new Set([...originalRefs, ...nextRefs].flatMap(value => {
    const ref = record(value)?.ref, index = typeof ref === "string" ? /^e(\d+)\.b0\.l/.exec(ref) : null;
    return index ? [Number(index[1])] : [];
  }))];
  let aliases: readonly (readonly number[])[] | undefined;
  const checked = new Map<string, boolean>();
  const covered = (outer: unknown, inner: unknown): boolean => {
    const key = JSON.stringify([outer, inner]);
    if (checked.has(key)) return checked.get(key)!;
    if (memoryCitationReferenceCovers(outer, inner, snapshot)) {checked.set(key, true);return true;}
    const selected = record(outer), prior = record(inner);
    const a = typeof selected?.ref === "string" ? /^e(\d+)\.b0\.l/.exec(selected.ref) : null;
    const b = typeof prior?.ref === "string" ? /^e(\d+)\.b0\.l/.exec(prior.ref) : null;
    if (!a || !b) {checked.set(key, false);return false;}
    aliases ??= observedMemorySourceAliases(snapshot, cwd, observedIndices);
    if (!aliases.some(group => group.includes(Number(a[1])) && group.includes(Number(b[1])))) {checked.set(key, false);return false;}
    const alias = {ref: String(prior!.ref).replace(/^e\d+/, `e${a[1]}`),
      ...(prior!.endRef === undefined ? {} : {endRef: String(prior!.endRef).replace(/^e\d+/, `e${a[1]}`)})};
    const result = memoryCitationReferenceCovers(selected, alias, snapshot);checked.set(key, result);return result;
  };
  for (const [index, unit] of before.units.entries()) {
    const used = indexes(after.units[index], nextRefs.length);
    if (!indexes(unit, originalRefs.length).every(prior => used.some(next => covered(nextRefs[next], originalRefs[prior])))) {
      throw new Error(`Source-role repair lost original unit support: unit:${index}`);
    }
  }
}

/** Initial project proposals select existing evidence rather than
 * regenerate technical claims. This materializes data, never write authority. */
export async function materializeSourceExcerptPlan(run: Run, raw: unknown, snapshot: unknown, audit?: AuditSources,
  options: {retainSelectedDeclarations?: true; priorContents?: ReadonlyMap<string, string>} = {}): Promise<unknown> {
  const plan = record(raw);
  const selected = (item: unknown) => ["sourceExcerpt", "knowledge"].some(key => Object.hasOwn(record(item) ?? {}, key));
  if (options.retainSelectedDeclarations && Array.isArray(plan?.newMemories)) {
    for (const value of plan.newMemories) {
      const item = record(value);
      if (relationObligations.get(run)?.has(String(item?.name).toLowerCase())
        && (item?.kind !== "project" || !record(item.knowledge))) {
        throw new Error("Retained API relation proposal requires project knowledge with explicitly selected source roles");
      }
    }
  }
  if (!plan || !Array.isArray(plan.newMemories) || !plan.newMemories.some(selected)) return raw;
  if (options.retainSelectedDeclarations) preflightFreshMemoryPlan(run, plan, snapshot);
  await assertSourceExcerptBindings(run);
  const pending: Binding[] = [];
  const newMemories = [];
  const fileRefs = options.retainSelectedDeclarations ? new Set(memoryCitationDomain(snapshot, {fileSourcesFromCwd: run.manifest.cwd}).fileRefs) : undefined;
  const fileSelection = (value: unknown, position: string): Row => {
    const fail = (category: string): never => {throw new Error(`Memory file-source selection is invalid: ${position}: ${category}`);};
    const ref = record(value);
    if (!ref || Object.keys(ref).some(key => !["ref", "endRef"].includes(key)) || typeof ref.ref !== "string") return fail("invalid-file-reference");
    if (!fileRefs?.has(ref.ref) || ref.endRef !== undefined && (typeof ref.endRef !== "string" || !fileRefs.has(ref.endRef))) return fail("ineligible-file-reference");
    return ref;
  };
  for (const [itemIndex, value] of plan.newMemories.entries()) {
    const item = record(value);
    if (!item || !selected(item)) {newMemories.push(value);continue;}
    if (Object.hasOwn(item, "content") || item.kind !== "project") invalid();
    let replacement: Row;
    if (Object.hasOwn(item, "knowledge")) {
      const metadataProblems = projectMetadataProblems(item, `newMemories[${itemIndex}]`);
      if (metadataProblems.length) throw metadataProblems[0];
      const originalKnowledge = record(item.knowledge);
      if (!originalKnowledge || !Array.isArray(originalKnowledge.units) || !Array.isArray(originalKnowledge.sourceCitations)) invalid();
      let knowledge = originalKnowledge as Row & {units: unknown[]; sourceCitations: unknown[]};
      const atomicRelations: SelectedAtomicRelation[] = [];
      if (options.retainSelectedDeclarations) {
        const catalog = [...knowledge.sourceCitations], normalized: unknown[] = [];
        for (const [unitIndex, value] of knowledge.units.entries()) {
          const unit = record(value);
          if (unit && (Object.hasOwn(unit, "sourceCitationIndex") || Object.hasOwn(unit, "fileSourceRef"))) {
            throw new Error(`Fresh Memory source units require text and citationIndexes: newMemories[${itemIndex}].knowledge.units[${unitIndex}]`);
          }
          if (unit?.kind !== "declared-api-relation") {normalized.push(value);continue;}
          const selected = declaredMemoryRelation(snapshot, unit, run.manifest.cwd);
          const name = String(item.name).toLowerCase();
          const retained = relationObligations.get(run) ?? new Map<string, MemoryRelationObligations>();
          const prior = retained.get(name);
          if (prior && prior.snapshotProjectionDigest !== selected.obligations.snapshotProjectionDigest) {
            throw new MemoryRelationClosureError("Selected API relation snapshot projection changed");
          }
          const requirements = [...(prior?.requirements ?? [])];
          for (const requirement of selected.obligations.requirements) {
            if (!requirements.some(value => value.sourcePath === requirement.sourcePath && value.sourceSha256 === requirement.sourceSha256
              && value.factory === requirement.factory && value.owner === requirement.owner && value.member === requirement.member)) {
              requirements.push(requirement);
            }
          }
          retained.set(name, {...selected.obligations, requirements});relationObligations.set(run, retained);
          const indexes = selected.refs.map(ref => {
            fileSelection(ref, "declared-api-relation");
            let index = catalog.findIndex(citation => memoryCitationReferenceMatches(citation, ref, snapshot));
            if (index < 0) {index = catalog.length;catalog.push(ref);}
            return index;
          });
          atomicRelations.push({...selected.relation, indexes});
          selected.refs.forEach((ref, at) => normalized.push({sourceCitationIndex: indexes[at], fileSourceRef: ref}));
        }
        knowledge = {...knowledge, sourceCitations: catalog, units: normalized};
      }
      const fileSelections = new Map<number, Row>();
      const units = knowledge.units.map((value, unitIndex) => {
        const unit = record(value);
        if (!unit || !Object.hasOwn(unit, "sourceCitationIndex")) return value;
        const index = unit.sourceCitationIndex;
        if (Object.keys(unit).some(key => !["sourceCitationIndex", ...(options.retainSelectedDeclarations ? ["fileSourceRef"] : [])].includes(key)) || !Number.isSafeInteger(index)
          || Number(index) < 0 || Number(index) >= (knowledge.sourceCitations as unknown[]).length) invalid();
        if (options.retainSelectedDeclarations) {
          const position = `newMemories[${itemIndex}].knowledge.units[${unitIndex}]`;
          const selection = fileSelection(unit.fileSourceRef, position);
          if (!memoryCitationReferenceMatches((knowledge.sourceCitations as unknown[])[Number(index)], selection, snapshot)) {
            throw new Error(`Memory file-source selection is invalid: ${position}: catalog-slot-does-not-match-selection`);
          }
          fileSelections.set(unitIndex, selection);
        }
        return {text: "Original source selection", citationIndexes: [index]};
      });
      const header = options.priorContents?.get(String(item.name)) ?? projectHeader(item.name, item.description as string);
      // Validate every unit and the complete catalog before reading current source.
      materializeMemoryKnowledge(header, {...knowledge, units}, snapshot);
      let relations: ReturnType<typeof selectedMemoryRelationClosures> = [];
      if (options.retainSelectedDeclarations) {
        const name = String(item.name).toLowerCase();
        try {relations = selectedMemoryRelationClosures(snapshot, knowledge, run.manifest.cwd, relationObligations.get(run)?.get(name), value => {
          if (!value.requirements.length) return;
          const retained = relationObligations.get(run) ?? new Map<string, MemoryRelationObligations>();
          retained.set(name, value);relationObligations.set(run, retained);
        });}
        catch (error) {
          if (error instanceof MemoryRelationClosureError && error.obligations) {
            const retained = relationObligations.get(run) ?? new Map<string, MemoryRelationObligations>();
            retained.set(name, structuredClone(error.obligations));relationObligations.set(run, retained);
          }
          throw error;
        }
      }
      for (const [index, value] of knowledge.units.entries()) {
        const unit = record(value)!;
        if (!Object.hasOwn(unit, "sourceCitationIndex")) continue;
        const citation = record(knowledge.sourceCitations[Number(unit.sourceCitationIndex)]);
        if (!citation) invalid();
        const {body, binding} = await resolveSourceSelection(run,
          fileSelections.get(index) ?? {ref: citation.ref, ...(citation.endRef === undefined ? {} : {endRef: citation.endRef})},
          knowledge.sourceCitations, snapshot, audit);
        units[index] = {text: body, citationIndexes: [unit.sourceCitationIndex]};
        pending.push(binding);
      }
      // The model already chose these references for its prose. Preserve only
      // complete observed declarations as neutral source data, never select facts.
      const explicit = new Set(knowledge.units.flatMap(value => {
        const unit = record(value);return unit && Object.hasOwn(unit, "sourceCitationIndex") ? [unit.sourceCitationIndex] : [];
      }));
      const used = new Set(knowledge.units.flatMap(value => {
        const unit = record(value);return unit && typeof unit.text === "string" && Array.isArray(unit.citationIndexes) ? unit.citationIndexes : [];
      }));
      const covers = (outer: unknown, inner: unknown) => {
        const a = record(outer), b = record(inner);
        const first = (value: unknown) => typeof value === "string" ? /^(e\d+\.b\d+\.l)(\d+)$/.exec(value) : null;
        const x = first(a?.ref), y = first(b?.ref), xe = first(a?.endRef ?? a?.ref), ye = first(b?.endRef ?? b?.ref);
        return !!x && !!y && !!xe && !!ye && x[1] === y[1] && xe[1] === x[1] && ye[1] === y[1]
          && Number(x[2]) <= Number(y[2]) && Number(xe[2]) >= Number(ye[2]);
      };
      const retained = [...explicit].map(index => (knowledge.sourceCitations as unknown[])[Number(index)]);
      const additions = options.retainSelectedDeclarations ? knowledge.sourceCitations.flatMap((citation, index) => {
        if (!used.has(index) || retained.some(prior => covers(prior, citation)) || !isObservedFunctionDeclaration(snapshot, citation)) return [];
        retained.push(citation);return [index];
      }) : [];
      if (units.length + additions.length > 32) throw new Error("Atomic Memory knowledge requires 1..32 cited body units including retained declarations");
      for (const index of additions) {
        const citation = record(knowledge.sourceCitations[index])!;
        const {body, binding} = await resolveSourceSelection(run,
          {ref: citation.ref, ...(citation.endRef === undefined ? {} : {endRef: citation.endRef})},
          knowledge.sourceCitations, snapshot, audit, true);
        units.push({text: body, citationIndexes: [index]});
        pending.push(binding);
      }
      // Successful closure already proves every source role was explicitly
      // selected and used. Normalize those same catalog indexes through the
      // atomic path without requiring a second producer spelling of the choice.
      const selectedRelations = [...atomicRelations];
      for (const relation of relations) {
        const selected = selectedRelations.find(selected => selected.sourcePath === relation.sourcePath && selected.factory === relation.factory && selected.owner === relation.owner && selected.member === relation.member);
        if (!selected) selectedRelations.push(relation);
        else if (relation.implementation) {
          if (selected.sourceSha256 !== relation.sourceSha256
            || selected.implementation && JSON.stringify(selected.implementation) !== JSON.stringify(relation.implementation)) invalid();
          selected.implementation = relation.implementation;
        }
      }
      const derivedCopies = new Set<string>();
      const retainRelationSources = async (relation: Pick<SelectedAtomicRelation, "indexes" | "sourceSelections" | "sourcePath" | "sourceSha256">) => {
        // Verify the complete original selections before projecting any derived
        // block. Narrowing must not conceal an oversized, stale or sensitive quote.
        if (relation.sourceSelections) for (const index of new Set(relation.indexes)) {
          const citation = record((knowledge.sourceCitations as unknown[])[index])!;
          const original = await resolveSourceSelection(run,
            {ref: citation.ref, ...(citation.endRef === undefined ? {} : {endRef: citation.endRef})},
            knowledge.sourceCitations, snapshot, audit);
          if (containsSensitiveMemoryMaterial(original.body)) invalid();
          pending.push(original.binding);
        }
        const selections: NonNullable<SelectedAtomicRelation["sourceSelections"]> = relation.sourceSelections ?? relation.indexes.map(index => {
          const citation = record((knowledge.sourceCitations as unknown[])[index])!;
          return {index, ref: citation.ref as string, ...(citation.endRef === undefined ? {} : {endRef: citation.endRef as string})};
        });
        for (const {index, sourceSpan, ...selection} of selections) {
          const key = `${index}:${selection.ref}:${selection.endRef ?? selection.ref}:${sourceSpan?.start ?? ""}:${sourceSpan?.end ?? ""}`;
          if (derivedCopies.has(key)
            || [...explicit].some(prior => covers((knowledge.sourceCitations as unknown[])[Number(prior)], selection))
            || additions.some(prior => covers((knowledge.sourceCitations as unknown[])[prior], selection))) continue;
          const {body, binding} = await resolveSourceSelection(run, selection, knowledge.sourceCitations, snapshot, audit, false, sourceSpan);
          units.push({text: body, citationIndexes: [index]});derivedCopies.add(key);pending.push(binding);
          if (!relation.sourceSelections) explicit.add(index);
        }
        const roleBindings = pending.filter(binding => binding.file === relation.sourcePath);
        if (!roleBindings.length || roleBindings.some(binding => binding.digest !== relation.sourceSha256)) invalid();
      };
      for (const relation of selectedRelations) {
        await retainRelationSources(relation);
        units.push({text: `Observed declaration syntax from ${JSON.stringify(relation.file)} (source observation only):\n\n` +
          `\`${relation.factory}\` has the named return type \`${relation.owner}\`.\n\n` +
          `\`${relation.owner}\` declares \`${relation.member}\`.`, citationIndexes: [...new Set(relation.indexes)]});
        if (relation.implementation) {
          const implementation = relation.implementation;
          await retainRelationSources(implementation);
          units.push({text: `Observed implementation syntax from ${JSON.stringify(implementation.file)} (source observation only):\n\n` +
            `\`${relation.factory}\` declares callable \`${implementation.owner}\`, contains \`Object.defineProperties(${implementation.owner}, …)\` with \`${relation.member}\`, and returns \`${implementation.owner}\`. ` +
            `This records source structure, not verified execution.`, citationIndexes: [...new Set(implementation.indexes)]});
        }
      }
      const materialized = materializeMemoryKnowledge(header, {...knowledge, units}, snapshot);
      replacement = {name: item.name, kind: item.kind, classification: item.classification, ...materialized};
    } else {
      if (options.retainSelectedDeclarations || item.classification !== "private") invalid();
      if (options.retainSelectedDeclarations) fileSelection(item.sourceExcerpt, `newMemories[${itemIndex}].sourceExcerpt`);
      const {body, description, binding} = await resolveSourceSelection(run, item.sourceExcerpt, item.evidence, snapshot, audit);
      const {sourceExcerpt: _selection, ...rest} = item;
      replacement = {...rest, content: projectHeader(item.name, description) + "\n" + body};
      pending.push(binding);
    }
    if (typeof replacement.content !== "string" || Buffer.byteLength(replacement.content, "utf8") > MAX_MEMORY_BYTES
      || containsSensitiveMemoryMaterial(replacement.content)) invalid();
    newMemories.push(replacement);
  }
  for (const expected of pending) {
    const {binding} = await readSource(expected.file);
    if (binding.identity !== expected.identity || binding.digest !== expected.digest) invalid();
  }
  bindings.set(run, [...(bindings.get(run) ?? []), ...pending]);
  // Weak parent state survives correction and is released with the run object.
  return {...plan, newMemories};
}

/** Parent DATA only; callers bind it to their existing run/snapshot identity. */
export function selectedProjectSourceObligations(run: Run): Record<string, MemoryRelationObligations> {
  return Object.fromEntries([...(relationObligations.get(run) ?? [])].map(([name, value]) => {
    const publicValue = structuredClone(value);
    for (const requirement of publicValue.requirements) {
      for (const reference of [...requirement.roles.flatMap(role => role.alternatives), ...(requirement.initiatingWrapperWitness?.alternatives ?? []),
        ...(requirement.implementation?.roles.flatMap(role => role.alternatives) ?? [])]) {
        delete reference.sourceSpan;
      }
    }
    return [name, publicValue];
  }));
}

/** Optional compact source coordinates for the same admitted role correction.
 * The producer still selects its own catalog; these ranges grant no evidence. */
export async function sourceRoleRangeChoices(run: Run, name: string, knowledge: unknown, snapshot: unknown): Promise<SourceRoleRangeChoice[]> {
  const obligation = relationObligations.get(run)?.get(name.toLowerCase()), value = record(knowledge);
  if (!obligation || !value || !Array.isArray(value.sourceCitations) || !Array.isArray(value.units)) return [];
  if (obligation.snapshotProjectionDigest !== sha256Digest(JSON.stringify(snapshot))) throw new Error("Source-role range snapshot changed");
  type Seed = {start: number; end: number; id: string};
  type Group = {sourcePath: string; sourceSha256: string; seeds: Seed[]};
  const groups = new Map<number, Group>();
  const add = (reference: unknown, id: string, source: Pick<Group, "sourcePath" | "sourceSha256">) => {
    const ref = record(reference), a = typeof ref?.ref === "string" ? /^e(\d+)\.b0\.l([1-9]\d*)$/.exec(ref.ref) : null;
    const b = typeof (ref?.endRef ?? ref?.ref) === "string" ? /^e(\d+)\.b0\.l([1-9]\d*)$/.exec(String(ref?.endRef ?? ref?.ref)) : null;
    if (!a || !b || a[1] !== b[1]) return;
    const index = Number(a[1]), start = Number(a[2]), end = Number(b[2]);
    if (![index, start, end].every(Number.isSafeInteger) || start > end) return;
    const group = groups.get(index);
    if (group && (group.sourcePath !== source.sourcePath || group.sourceSha256 !== source.sourceSha256)) throw new Error("Conflicting source-role range identity");
    const next = group ?? {...source, seeds: []};
    if (!next.seeds.some(seed => seed.id === id && seed.start === start && seed.end === end)) next.seeds.push({start, end, id});
    groups.set(index, next);
  };
  for (const [index, requirement] of obligation.requirements.entries()) {
    for (const role of requirement.roles) for (const ref of role.alternatives) add(ref, `role:${index}:${role.role}`, requirement);
    for (const ref of requirement.initiatingWrapperWitness?.alternatives ?? []) add(ref, `role:${index}:wrapper`, requirement);
    for (const role of requirement.implementation?.roles ?? []) for (const ref of role.alternatives) add(ref, `role:${index}:${role.role}`, requirement.implementation!);
  }
  for (const [unitIndex, item] of value.units.entries()) {
    const unit = record(item);
    if (!Array.isArray(unit?.citationIndexes)) continue;
    for (const index of unit.citationIndexes) {
      const ref = record(value.sourceCitations[Number(index)]), match = typeof ref?.ref === "string" ? /^e(\d+)\./.exec(ref.ref) : null;
      const group = match ? groups.get(Number(match[1])) : undefined;
      if (group) add(ref, `unit:${unitIndex}:source:${index}`, group);
    }
  }
  const candidates: (SourceRoleRangeChoice & {ids: string[]})[] = [], current = new Map<string, Awaited<ReturnType<typeof readSource>>>();
  const root = await fs.realpath(run.manifest.cwd);
  for (const [index, group] of groups) {
    if (group.seeds.length > 32) continue;
    const relative = path.relative(root, group.sourcePath);
    if (!relative || path.isAbsolute(relative) || relative.split(path.sep).some(part => ["..", ".memory", ".pi", ".git"].includes(part.toLowerCase()))) invalid();
    let source = current.get(group.sourcePath);
    if (!source) {source = await readSource(group.sourcePath);current.set(group.sourcePath, source);}
    if (source.binding.digest !== group.sourceSha256) throw new Error("Source-role range source changed");
    const lines = source.text.split("\n"), seeds = group.seeds.sort((a, b) => a.start - b.start || a.end - b.end || a.id.localeCompare(b.id));
    for (const left of seeds) {
      let best: (typeof candidates)[number] | undefined;
      for (const end of [...new Set(seeds.map(seed => seed.end))].sort((a, b) => a - b)) {
        if (end < left.start || end > lines.length) continue;
        const quote = lines.slice(left.start - 1, end).join("\n");
        if (quote.length > 2000) break;
        if (containsSensitiveMemoryMaterial(quote)) continue;
        const ids = [...new Set(seeds.filter(seed => seed.start >= left.start && seed.end <= end).map(seed => seed.id))];
        if (ids.length < 2 || seeds.some(seed => seed.start === left.start && seed.end === end)) continue;
        const ref = {ref: `e${index}.b0.l${left.start}`, ...(end === left.start ? {} : {endRef: `e${index}.b0.l${end}`})};
        const resolved = record(resolveMemoryPlanCitations({newMemories: [{evidence: [ref]}]}, snapshot))!;
        const [selected] = normalizeSnapshotEvidence(record((resolved.newMemories as unknown[])[0])!.evidence, snapshot);
        if (selected.quote !== quote) throw new Error("Source-role range does not match its complete observed source");
        best = {...ref, utf16Length: quote.length, coversRoles: ids.filter(id => id.startsWith("role:")),
          coversOriginalSupports: ids.filter(id => id.startsWith("unit:")), ids};
      }
      if (best && !candidates.some(candidate => candidate.ref === best!.ref && candidate.endRef === best!.endRef)) candidates.push(best);
    }
  }
  const covered = new Set<string>(), choices: SourceRoleRangeChoice[] = [];
  while (choices.length < 4) {
    const ranked = candidates.map(value => ({value, added: value.ids.filter(id => !covered.has(id)).length}))
      .filter(item => item.added >= 2).sort((a, b) => b.added - a.added || a.value.utf16Length - b.value.utf16Length
        || a.value.ref.localeCompare(b.value.ref) || String(a.value.endRef).localeCompare(String(b.value.endRef)));
    if (!ranked.length) break;
    const {ids, ...choice} = ranked[0].value;ids.forEach(id => covered.add(id));choices.push(choice);
  }
  return choices;
}

/** Same source materializer, with the exact existing frontmatter rather than a new header. */
export async function materializeSemanticProjectKnowledge(run: Run, name: string, prior: string, knowledge: unknown,
  snapshot: unknown, audit?: AuditSources): Promise<{content: string; evidence: ReturnType<typeof normalizeSnapshotEvidence>}> {
  const result = record(await materializeSourceExcerptPlan(run, {operations: [], newMemories: [{name, kind: "project",
    classification: "private", description: "Source-bound correction.", knowledge}]}, snapshot, audit,
    {retainSelectedDeclarations: true, priorContents: new Map([[name, prior]])}))!;
  const item = record((result.newMemories as unknown[])[0])!;
  return {content: item.content as string, evidence: item.evidence as ReturnType<typeof normalizeSnapshotEvidence>};
}

/** Retain original parent-selected relation requirements, including an incomplete initial selection. */
export function retainProjectSourceObligations(run: Run, name: string, knowledge: unknown, snapshot: unknown): void {
  const key = name.toLowerCase();
  const capture = (value: MemoryRelationObligations) => {
    if (!value.requirements.length) return;
    const retained = relationObligations.get(run) ?? new Map<string, MemoryRelationObligations>();
    retained.set(key, value);relationObligations.set(run, retained);
  };
  try {selectedMemoryRelationClosures(snapshot, knowledge, run.manifest.cwd, relationObligations.get(run)?.get(key), capture);}
  catch (error) {if (!(error instanceof MemoryRelationClosureError && error.obligations)) throw error;}
}
