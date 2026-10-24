import fs from "node:fs/promises";
import {constants} from "node:fs";
import path from "node:path";
import {containsSensitiveMemoryMaterial, MAX_MEMORY_BYTES, MAX_SNAPSHOT_BYTES, normalizeSnapshotEvidence, sha256Digest, snapshotEditPatchText} from "./consolidation-run";
import {materializeMemoryKnowledge, resolveMemoryPlanCitations} from "./memory-citation-locations";

type Row = Record<string, unknown>;
type Run = {manifest: {cwd: string}};
type Binding = {file: string; identity: string; digest: string};
/** Only the parent collector can supply this grant; plan fields cannot. */
type AuditSources = {evidenceDigest: string; entryDigests: readonly string[]; requireAudit?: boolean};
const bindings = new WeakMap<Run, Binding[]>();
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
  audit?: AuditSources): Promise<{body: string; description: string; binding: Binding}> {
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
  const filename = relative.split(path.sep).join("/");
  const description = excerptDescription(filename, quote);
  const fence = "`".repeat(Math.max(3, ...[...quote.matchAll(/`+/g)].map(match => match[0].length + 1)));
  return {body: `Observed source excerpt from ${JSON.stringify(filename)}:\n\n${fence}text\n${quote}\n${fence}\n`,
    description, binding: source.binding};
}

function projectHeader(name: unknown, description: string): string {
  return `---\nname: ${JSON.stringify(name)}\ndescription: ${JSON.stringify(description)}\ntype: project\n---\n`;
}

/** Initial project proposals select existing evidence rather than
 * regenerate technical claims. This materializes data, never write authority. */
export async function materializeSourceExcerptPlan(run: Run, raw: unknown, snapshot: unknown, audit?: AuditSources): Promise<unknown> {
  const plan = record(raw);
  const selected = (item: unknown) => ["sourceExcerpt", "knowledge"].some(key => Object.hasOwn(record(item) ?? {}, key));
  if (!plan || !Array.isArray(plan.newMemories) || !plan.newMemories.some(selected)) return raw;
  await assertSourceExcerptBindings(run);
  const pending: Binding[] = [];
  const newMemories = [];
  for (const value of plan.newMemories) {
    const item = record(value);
    if (!item || !selected(item)) {newMemories.push(value);continue;}
    if (Object.hasOwn(item, "content") || item.kind !== "project") invalid();
    let replacement: Row;
    if (Object.hasOwn(item, "knowledge")) {
      if (item.classification !== "safe" && item.classification !== "private"
        || Object.keys(item).some(key => !["name", "kind", "classification", "description", "knowledge"].includes(key))
        || typeof item.description !== "string" || !item.description.trim() || item.description.length > 120
        || /[\r\n]/.test(item.description)) invalid();
      const knowledge = record(item.knowledge);
      if (!knowledge || !Array.isArray(knowledge.units) || !Array.isArray(knowledge.sourceCitations)) invalid();
      const units = knowledge.units.map(value => {
        const unit = record(value);
        if (!unit || !Object.hasOwn(unit, "sourceCitationIndex")) return value;
        const index = unit.sourceCitationIndex;
        if (Object.keys(unit).length !== 1 || !Number.isSafeInteger(index)
          || Number(index) < 0 || Number(index) >= (knowledge.sourceCitations as unknown[]).length) invalid();
        return {text: "Original source selection", citationIndexes: [index]};
      });
      const header = projectHeader(item.name, item.description);
      // Validate every unit and the complete catalog before reading current source.
      materializeMemoryKnowledge(header, {...knowledge, units}, snapshot);
      for (const [index, value] of knowledge.units.entries()) {
        const unit = record(value)!;
        if (!Object.hasOwn(unit, "sourceCitationIndex")) continue;
        const citation = record(knowledge.sourceCitations[Number(unit.sourceCitationIndex)]);
        if (!citation) invalid();
        const {body, binding} = await resolveSourceSelection(run,
          {ref: citation.ref, ...(citation.endRef === undefined ? {} : {endRef: citation.endRef})},
          knowledge.sourceCitations, snapshot, audit);
        units[index] = {text: body, citationIndexes: [unit.sourceCitationIndex]};
        pending.push(binding);
      }
      const materialized = materializeMemoryKnowledge(header, {...knowledge, units}, snapshot);
      replacement = {name: item.name, kind: item.kind, classification: item.classification, ...materialized};
    } else {
      if (item.classification !== "private") invalid();
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
  return {...plan, newMemories};
}
