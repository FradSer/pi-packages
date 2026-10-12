import { normalizeSnapshotEvidence, snapshotEditPatchText } from "./consolidation-run";

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
function lineView(text: string, block: number): RecordValue {
  return {block, lines: text.split("\n").map((text, index) => ({line: index + 1, text}))};
}
function projectEntry(entry: unknown): unknown {
  if (!eligible(entry)) return entry;
  const original = message(entry)!;
  const content = original.content;
  const projected = typeof content === "string" ? {citationLines: lineView(content, 0)}
    : Array.isArray(content) ? content.map((part, block) => {
      const text = textBlock(entry, block);
      if (text === undefined) return part;
      if (typeof part === "string") return {citationLines: lineView(text, block)};
      const {text: _text, ...metadata} = record(part)!;
      return {...metadata, citationLines: lineView(text, block)};
    }) : content;
  const patch = snapshotEditPatchText(entry);
  const updated = {...original, content: projected,
    ...(patch !== undefined ? {details: {...record(original.details),
      patch: {citationLines: {...lineView(patch, 0), source: "patch"}}}} : {})};
  return record(record(entry)?.message) ? {...record(entry), message: updated} : updated;
}

/** Lossless model-only projection. Every original text character remains in a
 * numbered line; raw snapshots, digests and semantic review inputs stay intact. */
export function locatedMemoryEvidence(value: unknown): unknown {
  const outer = record(value);
  if (!outer) return value;
  if (outer.kind === "incremental-learning-dossier") return {...outer, taskSlice: locatedMemoryEvidence(outer.taskSlice)};
  if (!Array.isArray(outer.entries)) return value;
  return {...outer, entries: outer.entries.map((entry, snapshotIndex) => ({snapshotIndex, entry: projectEntry(entry)}))};
}

/** Parent-controlled positions and categories only; source and model strings
 * never enter a repair diagnostic. One correction can address all bad refs. */
export class MemoryCitationLocationError extends Error {
  constructor(diagnostics: readonly string[]) {
    super(`Memory citation locations are invalid: ${diagnostics.join("; ")}`);
    this.name = "MemoryCitationLocationError";
  }
}

/** Resolve only explicit coordinates, never search/fix a mismatched legacy quote.
 * The ordinary citation gate still owns role, privacy and exact-quote limits. */
export function resolveMemoryPlanCitations(raw: unknown, snapshot: unknown): unknown {
  const plan = record(raw), entries = record(snapshot)?.entries;
  if (!plan) return raw;
  let changed = false;
  const diagnostics: string[] = [];
  const result = {...plan};
  for (const field of ["operations", "newMemories"] as const) {
    if (!Array.isArray(plan[field])) continue;
    result[field] = plan[field].map((candidate, candidateIndex) => {
      const item = record(candidate);
      if (!Array.isArray(item?.evidence)) return candidate;
      return {...item, evidence: item.evidence.map((value, citationIndex) => {
        const ref = record(value);
        if (!ref || !("lines" in ref)) return value;
        if (diagnostics.length >= 8) return value;
        const fail = (reason: string): never => {throw new MemoryCitationLocationError([reason]);};
        try {
        if (Object.keys(ref).some(key => !["index", "role", "quote", "lines"].includes(key))) fail("invalid-reference-fields");
        const range = record(ref.lines);
        if (!range || Object.keys(range).some(key => !["block", "start", "end", "source"].includes(key))
          || range.source !== undefined && range.source !== "patch") fail("invalid-range-fields");
        if (!Array.isArray(entries) || !Number.isSafeInteger(ref.index) || (ref.index as number) < 0) fail("invalid-snapshot-index");
        const entry = Array.isArray(entries) ? entries[ref.index as number] : undefined;
        if (!eligible(entry)) fail("ineligible-source");
        const {block, start, end} = range!;
        if (![block, start, end].every(Number.isSafeInteger)
          || (block as number) < 0 || (start as number) < 1 || (end as number) < (start as number)) fail("invalid-range-coordinates");
        const text = range!.source === "patch"
          ? block === 0 ? snapshotEditPatchText(entry) : undefined
          : textBlock(entry, block as number);
        if (text === undefined) fail("source-unavailable");
        const lines = text!.split("\n");
        if ((end as number) > lines.length) fail(`line-range-out-of-bounds (availableLines=${lines.length})`);
        const quote = lines.slice((start as number) - 1, end as number).join("\n");
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

export const MEMORY_LOCATION_GUIDANCE = `Prefer evidence locations over retyping quotations. Each eligible original content block is shown as citationLines: {block, lines: [{line, text}]}. Cite {index: snapshotIndex, lines: {block, start, end}} with integer 1-based inclusive line numbers inside that one block; block is the original zero-based content slot (0 for a string). Select a contiguous complete statement, retaining conditions, exceptions, indentation and tool-output prefixes. Never count JSON display lines or cross blocks. The parent extracts the exact original substring and applies unchanged quote/role/privacy/semantic checks. Positions do not prove a claim or grant authority. Do not supply quote with lines unless byte-for-byte identical. Successful edit results with an original details.patch also expose details.patch.citationLines with source: "patch". Cite those lines using {index: snapshotIndex, lines: {source: "patch", block: 0, start, end}}. Preserve + and - markers: removed lines describe the prior source, added lines describe this edit; neither proves runtime behavior or that no later change occurred. Assistant tool arguments and failed edits are not eligible patch sources. Legacy exact quote citations remain supported. Bounds remain 8 items and 2,000 extracted characters per quote. If one source line exceeds 2,000 characters, use a legacy exact quote of a complete relevant statement within that line under the same bound; do not select the oversized whole line or omit a material condition. Inspect every original entry, including later corrections; this projection omits no evidence.`;

export function hasMemoryCitationLocations(raw: unknown): boolean {
  const plan = record(raw);
  return [plan?.operations, plan?.newMemories].some(items => Array.isArray(items)
    && items.some(item => {const evidence = record(item)?.evidence;
      return Array.isArray(evidence) && evidence.some(ref => !!record(ref) && "lines" in record(ref)!);
    }));
}
