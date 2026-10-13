import { memoryReferenceResults } from "./memory-evidence-provenance";
import { MAX_NEW_MEMORY_EVIDENCE, normalizeSnapshotEvidence, snapshotEditPatchText } from "./consolidation-run";

type RecordValue = Record<string, unknown>;
function record(value: unknown): RecordValue | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : undefined;
}
function message(entry: unknown): RecordValue | undefined {
  const outer = record(entry);
  return record(outer?.message) ?? outer;
}
function eligible(entry: unknown): boolean {
  const role = message(entry)?.role;
  return role === "user" || role === "toolResult";
}
function textBlock(entry: unknown, block: number): string | undefined {
  const content = message(entry)?.content;
  if (typeof content === "string") return block === 0 ? content : undefined;
  if (!Array.isArray(content)) return undefined;
  const part = content[block];
  if (typeof part === "string") return part;
  const object = record(part);
  // Non-text blocks are retained as context, never made into citation text.
  if (object?.type !== undefined && object.type !== "text") return undefined;
  return typeof object?.text === "string" ? object.text : undefined;
}
function characterBoundary(text: string, index: number): boolean {
  return !(index > 0 && index < text.length
    && text.charCodeAt(index - 1) >= 0xd800 && text.charCodeAt(index - 1) <= 0xdbff
    && text.charCodeAt(index) >= 0xdc00 && text.charCodeAt(index) <= 0xdfff);
}
function lineView(text: string, block: number, snapshotIndex: number, patch = false): RecordValue {
  return {block, lines: text.split("\n").map((text, index) => {
    const line = index + 1;
    const ref = `e${snapshotIndex}.b${block}.${patch ? "p" : "l"}${line}`;
    // Whitespace remains lossless context, but can never satisfy the parent's
    // non-empty quotation gate. Do not offer it as a generation choice.
    if (!text.trim()) return {line, text};
    if (text.length <= 2000) return {line, text, ref};
    const chunks = [];
    for (let start = 0; start < text.length;) {
      let end = Math.min(start + 512, text.length);
      if (!characterBoundary(text, end)) end--;
      const fragment = text.slice(start, end);
      chunks.push({start, end, text: fragment, ...(fragment.trim() ? {ref: `${ref}.c${start}-${end}`} : {})});
      start = end;
    }
    return {line: index + 1, chunks};
  })};
}
function projectEntry(entry: unknown, snapshotIndex: number): unknown {
  if (!eligible(entry)) return entry;
  const original = message(entry)!;
  const content = original.content;
  const projected = typeof content === "string" ? {citationLines: lineView(content, 0, snapshotIndex)}
    : Array.isArray(content) ? content.map((part, block) => {
      const text = textBlock(entry, block);
      if (text === undefined) return part;
      if (typeof part === "string") return {citationLines: lineView(text, block, snapshotIndex)};
      const {text: _text, ...metadata} = record(part)!;
      return {...metadata, citationLines: lineView(text, block, snapshotIndex)};
    }) : content;
  const patch = snapshotEditPatchText(entry);
  const updated = {...original, content: projected,
    ...(patch !== undefined ? {details: {...record(original.details),
      patch: {citationLines: {...lineView(patch, 0, snapshotIndex, true), source: "patch"}}}} : {})};
  return record(record(entry)?.message) ? {...record(entry), message: updated} : updated;
}

/** Lossless model-only projection. Every original text character remains in a
 * numbered line; raw snapshots, digests and semantic review inputs stay intact. */
export function locatedMemoryEvidence(value: unknown): unknown {
  const outer = record(value);
  if (!outer) return value;
  if (outer.kind === "incremental-learning-dossier") return {...outer, taskSlice: locatedMemoryEvidence(outer.taskSlice)};
  if (!Array.isArray(outer.entries)) return value;
  const memoryReferences = memoryReferenceResults(outer.entries);
  return {...outer, entries: outer.entries.map((entry, snapshotIndex) => ({snapshotIndex, citationEligible: eligible(entry) && !memoryReferences.has(snapshotIndex), entry: memoryReferences.has(snapshotIndex) ? entry : projectEntry(entry, snapshotIndex)}))};
}

/** Complete positional catalog, without source text or evidence selection. */
export function memoryCitationDomain(value: unknown): {indices: number[]; refs: string[]} {
  const outer = record(value);
  if (outer?.kind === "incremental-learning-dossier") return memoryCitationDomain(outer.taskSlice);
  if (!Array.isArray(outer?.entries)) throw new Error("Memory citation domain requires frozen entries");
  const memoryReferences = memoryReferenceResults(outer.entries);
  const indices: number[] = [], refs: string[] = [];
  const addText = (text: string, block: number, index: number, patch = false) => {
    for (const row of lineView(text, block, index, patch).lines as RecordValue[]) {
      if (typeof row.ref === "string") refs.push(row.ref);
      else for (const chunk of (row.chunks as RecordValue[] | undefined) ?? [])
        if (typeof chunk.ref === "string") refs.push(chunk.ref);
    }
  };
  outer.entries.forEach((entry, index) => {
    if (!eligible(entry) || memoryReferences.has(index)) return;
    const before = refs.length, content = message(entry)?.content;
    const count = Array.isArray(content) ? content.length : 1;
    for (let block = 0; block < count; block++) {
      const text = textBlock(entry, block);
      if (text !== undefined) addText(text, block, index);
    }
    const patch = snapshotEditPatchText(entry);
    if (patch !== undefined) addText(patch, 0, index, true);
    if (refs.length > before) indices.push(index);
  });
  return {indices, refs};
}

/** Parent-controlled positions and categories only; source and model strings
 * never enter a repair diagnostic. One correction can address all bad refs. */
export class MemoryCitationLocationError extends Error {
  constructor(diagnostics: readonly string[]) {
    super(`Memory citation locations are invalid: ${diagnostics.join("; ")}`);
    this.name = "MemoryCitationLocationError";
  }
}

/** References label positions; the owning run verifies the raw snapshot digest. */
function referencePosition(ref: unknown, entries: unknown[], memoryReferences: ReadonlySet<number>) {
  const fail = (): never => {throw new MemoryCitationLocationError(["unknown-source-reference"]);};
  if (typeof ref !== "string" || ref.length > 128) return fail();
  const match = /^e(0|[1-9]\d*)\.b(0|[1-9]\d*)\.([lp])([1-9]\d*)(?:\.c(0|[1-9]\d*)-([1-9]\d*))?$/.exec(ref);
  if (!match) return fail();
  const index = Number(match[1]), block = Number(match[2]), line = Number(match[4]);
  if (![index, block, line].every(Number.isSafeInteger)) return fail();
  const entry = entries[index], patch = match[3] === "p";
  if (!eligible(entry) || memoryReferences.has(index)) return fail();
  const text = patch ? block === 0 ? snapshotEditPatchText(entry) : undefined : textBlock(entry, block);
  if (text === undefined) return fail();
  const row = (lineView(text, block, index, patch).lines as RecordValue[])[line - 1];
  if (!row) return fail();
  if (match[5] === undefined) {
    // Older plans may use a whitespace endpoint in an otherwise non-empty
    // range. Preserve that position contract; standalone blanks still fail
    // ordinary extraction/quotation validation and are no longer advertised.
    const legacyWhitespace = typeof row.text === "string" && !row.text.trim()
      && ref === `e${index}.b${block}.${patch ? "p" : "l"}${line}`;
    if (row.ref !== ref && !legacyWhitespace) return fail();
    return {index, block, line, patch};
  }
  const chunk = (row.chunks as RecordValue[] | undefined)?.find(item => item.ref === ref
    || typeof item.text === "string" && !item.text.trim()
      && ref === `e${index}.b${block}.${patch ? "p" : "l"}${line}.c${item.start}-${item.end}`);
  if (!chunk) return fail();
  return {index, block, line, patch, start: chunk.start as number, end: chunk.end as number};
}

function expandReference(ref: RecordValue, entries: unknown[], memoryReferences: ReadonlySet<number>): RecordValue {
  if (Object.keys(ref).some(key => !["ref", "endRef", "role"].includes(key))) {
    throw new MemoryCitationLocationError(["invalid-reference-fields"]);
  }
  const first = referencePosition(ref.ref, entries, memoryReferences);
  const last = "endRef" in ref ? referencePosition(ref.endRef, entries, memoryReferences) : first;
  if (first.index !== last.index || first.block !== last.block || first.patch !== last.patch
    || first.line > last.line || (first.start === undefined) !== (last.start === undefined)
    || first.start !== undefined && (first.line !== last.line || first.start > last.start!)) {
    throw new MemoryCitationLocationError(["incompatible-source-reference-range"]);
  }
  return {index: first.index, ...(ref.role !== undefined ? {role: ref.role} : {}),
    lines: {block: first.block, start: first.line, end: last.line,
      ...(first.patch ? {source: "patch"} : {}),
      ...(first.start !== undefined ? {characters: {start: first.start, end: last.end}} : {})}};
}

/** Resolve only explicit coordinates, never search/fix a mismatched legacy quote.
 * The ordinary citation gate still owns role, privacy and exact-quote limits. */
export function resolveMemoryPlanCitations(raw: unknown, snapshot: unknown): unknown {
  const plan = record(raw), entries = record(snapshot)?.entries;
  if (!plan) return raw;
  const memoryReferences = memoryReferenceResults(Array.isArray(entries) ? entries : []);
  let changed = false;
  const diagnostics: string[] = [];
  const result = {...plan};
  for (const field of ["operations", "newMemories"] as const) {
    if (!Array.isArray(plan[field])) continue;
    result[field] = plan[field].map((candidate, candidateIndex) => {
      const item = record(candidate);
      if (!Array.isArray(item?.evidence)) return candidate;
      // Collect count errors alongside coordinate errors before the one repair
      // call; otherwise the first bad location hides an already invalid count.
      if (diagnostics.length < 8 && (item.evidence.length < 1 || item.evidence.length > MAX_NEW_MEMORY_EVIDENCE)) {
        diagnostics.push(`${field}[${candidateIndex}].evidence: item-count-out-of-bounds (required=1..${MAX_NEW_MEMORY_EVIDENCE}, actual=${item.evidence.length})`);
      }
      return {...item, evidence: item.evidence.map((value, citationIndex) => {
        let ref = record(value);
        if (!ref || !["lines", "ref", "endRef"].some(key => key in ref!)) return value;
        if (diagnostics.length >= 8) return value;
        const fail = (reason: string): never => {throw new MemoryCitationLocationError([reason]);};
        try {
        if ("ref" in ref || "endRef" in ref) {
          if (!Array.isArray(entries)) fail("invalid-snapshot-index");
          ref = expandReference(ref, entries as unknown[], memoryReferences);
        }
        if (Object.keys(ref).some(key => !["index", "role", "quote", "lines"].includes(key))) fail("invalid-reference-fields");
        const range = record(ref.lines);
        if (!range || Object.keys(range).some(key => !["block", "start", "end", "source", "characters"].includes(key))
          || range.source !== undefined && range.source !== "patch") fail("invalid-range-fields");
        if (!Array.isArray(entries) || !Number.isSafeInteger(ref.index) || (ref.index as number) < 0) fail("invalid-snapshot-index");
        const entry = Array.isArray(entries) ? entries[ref.index as number] : undefined;
        if (!eligible(entry)) fail("ineligible-source");
        if (memoryReferences.has(ref.index as number)) fail("memory-reference-not-independent");
        const {block, start, end} = range!;
        if (![block, start, end].every(Number.isSafeInteger)
          || (block as number) < 0 || (start as number) < 1 || (end as number) < (start as number)) fail("invalid-range-coordinates");
        const text = range!.source === "patch"
          ? block === 0 ? snapshotEditPatchText(entry) : undefined
          : textBlock(entry, block as number);
        if (text === undefined) fail("source-unavailable");
        const lines = text!.split("\n");
        if ((end as number) > lines.length) fail(`line-range-out-of-bounds (availableLines=${lines.length})`);
        let quote = lines.slice((start as number) - 1, end as number).join("\n");
        if ("characters" in range!) {
          const span = record(range!.characters);
          if (!span || Object.keys(span).some(key => !["start", "end"].includes(key))
            || start !== end || !Number.isSafeInteger(span.start) || !Number.isSafeInteger(span.end)
            || (span.start as number) < 0 || (span.end as number) <= (span.start as number)
            || (span.end as number) > quote.length
            || !characterBoundary(quote, span.start as number) || !characterBoundary(quote, span.end as number)) {
            fail("invalid-character-span");
          }
          quote = quote.slice(span!.start as number, span!.end as number);
        }
        if (quote.length < 1 || quote.length > 2000) fail("quote-length-out-of-bounds (maximumCharacters=2000)");
        if ("quote" in ref && ref.quote !== quote) fail("quote-mismatch");
        const resolved = {index: ref.index, quote, ...(ref.role !== undefined ? {role: ref.role} : {})};
        normalizeSnapshotEvidence([resolved], snapshot);
        changed = true;
        return resolved;
        } catch (error) {
          const reason = error instanceof MemoryCitationLocationError
            ? error.message.slice("Memory citation locations are invalid: ".length) : "citation-gate-rejected";
          diagnostics.push(`${field}[${candidateIndex}].evidence[${citationIndex}]: ${reason}`);
          return value;
        }
      })};
    });
  }
  if (diagnostics.length) throw new MemoryCitationLocationError(diagnostics);
  return changed ? result : raw;
}

export const MEMORY_LOCATION_GUIDANCE = `Generate citations using only parent-labelled source references. Each eligible short source line or long-line chunk has a ref. Cite {ref: "copy one exact displayed ref"}; for a contiguous range use {ref: "first displayed ref", endRef: "last displayed ref"}. Copy existing labels, never construct labels, calculate coordinates or retype quotations. Do not generate index, quote or lines fields. Every candidate needs its own non-empty evidence, at most eight items. The parent extracts exact original text and retains the same 2,000-character-per-item, role, privacy and semantic gates. Select the smallest complete statement that preserves its material conditions, exceptions, indentation and tool-output prefixes. Ranges must stay within one eligible original content block (or one patch), and chunk ranges within one original line. An individually bounded line/chunk does not make an arbitrary multi-line range bounded; use separate relevant references when a range would exceed the unchanged extraction limit. Long lines are shown losslessly as UTF-16 chunks; select their displayed refs rather than reconstructing character offsets. The parent never chooses a source or fixes an invalid citation for a candidate. References are positions in this run, not claim support, verified facts or mutation authority. Successful edit results with original details.patch expose patch refs: preserve + and - markers, since removed lines describe the prior state and added lines describe that edit. Neither proves runtime behavior or that no later change occurred. Assistant tool arguments and failed edits are not eligible patch sources. Legacy coordinate/quote input remains a parent compatibility concern, not a generation alternative. Inspect every original entry, including later corrections; the projection omits no evidence.`;

export function hasMemoryCitationLocations(raw: unknown): boolean {
  const plan = record(raw);
  return [plan?.operations, plan?.newMemories].some(items => Array.isArray(items)
    && items.some(item => {const evidence = record(item)?.evidence;
      return Array.isArray(evidence) && evidence.some(ref => !!record(ref)
        && ["lines", "ref", "endRef"].some(key => key in record(ref)!));
    }));
}
