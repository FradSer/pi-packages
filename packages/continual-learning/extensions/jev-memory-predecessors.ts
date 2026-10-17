import {createHash} from "node:crypto";

const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

export const predecessorReferenceInstruction = " An existingMemories contentReference is a lossless pointer to its complete predecessor body in this same state: follow statePath, read the UTF-16 substring [start,end) as content. It is the exact original predecessor, not proof of source truth or mutation authority; do not infer that missing inline content means no knowledge to preserve.";

/** Compact only a second, exact copy; never change original review evidence. */
export function compactMemoryPredecessors(state: Record<string, unknown>): Record<string, unknown> {
  if (!Array.isArray(state.existingMemories) || !record(state.reviewEvidence)
    || !Array.isArray(state.reviewEvidence.entries)) return state;
  const texts: {text: string; path: (string | number)[]}[] = [];
  for (const [index, item] of state.reviewEvidence.entries.entries()) {
    if (!record(item) || !record(item.entry)) continue;
    const entry = item.entry;
    const message = record(entry.message) ? entry.message : entry;
    const path: (string | number)[] = ["reviewEvidence", "entries", index, "entry", ...(message === entry ? [] : ["message"]), "content"];
    if (typeof message.content === "string") texts.push({text: message.content, path});
    else if (Array.isArray(message.content)) for (const [blockIndex, block] of message.content.entries()) {
      if (record(block) && block.type === "text" && typeof block.text === "string")
        texts.push({text: block.text, path: [...path, blockIndex, "text"]});
    }
  }
  let changed = false;
  const existingMemories = state.existingMemories.map(memory => {
    if (!record(memory) || typeof memory.content !== "string" || !memory.content.length) return memory;
    const content = memory.content;
    const source = texts.find(item => item.text.includes(content));
    if (!source) return memory;
    const {content: _content, ...metadata} = memory;
    const start = source.text.indexOf(content);
    const replacement = {...metadata, contentReference: {statePath: source.path, start,
      end: start + content.length, units: "UTF-16", sha256: createHash("sha256").update(content).digest("hex")}};
    // Tiny records can grow when referenced. Keep them inline in that case.
    if (Buffer.byteLength(JSON.stringify(replacement)) >= Buffer.byteLength(JSON.stringify(memory))) return memory;
    changed = true;
    return replacement;
  });
  return changed ? {...state, existingMemories} : state;
}

export const citationReferenceInstruction = " An originalCitationsByCandidate quoteReference is a lossless pointer to the exact original quote in frozenEvidence in this same state. Follow statePath and read the UTF-16 substring [start,end) as quote. Its SHA256 binds the quoted text, not source truth, durability or mutation authority. Read the complete original source entry for context.";

/** Reference only duplicated exact quotes in their indexed, same-role source. */
export function compactMemorySupportCitations(state: Record<string, unknown>): Record<string, unknown> {
  if (!record(state.frozenEvidence) || !Array.isArray(state.frozenEvidence.entries)
    || !record(state.originalCitationsByCandidate)) return state;
  const texts: {index: number; role: unknown; text: string; path: (string | number)[]}[] = [];
  for (const [position, item] of state.frozenEvidence.entries.entries()) {
    if (!record(item) || typeof item.index !== "number" || !record(item.entry)) continue;
    const message = record(item.entry.message) ? item.entry.message : item.entry;
    const path: (string | number)[] = ["frozenEvidence", "entries", position, "entry",
      ...(message === item.entry ? [] : ["message"]), "content"];
    if (typeof message.content === "string") texts.push({index: item.index, role: message.role, text: message.content, path});
    else if (Array.isArray(message.content)) for (const [block, value] of message.content.entries()) {
      if (record(value) && value.type === "text" && typeof value.text === "string")
        texts.push({index: item.index, role: message.role, text: value.text, path: [...path, block, "text"]});
    }
  }
  let changed = false;
  const originalCitationsByCandidate = Object.fromEntries(Object.entries(state.originalCitationsByCandidate).map(([key, value]) => [
    key, Array.isArray(value) ? value.map(citation => {
      if (!record(citation) || typeof citation.quote !== "string" || !citation.quote.length) return citation;
      const source = texts.find(text => text.index === citation.index
        && (citation.role === undefined || citation.role === text.role) && text.text.includes(citation.quote as string));
      if (!source) return citation;
      const quote = citation.quote, start = source.text.indexOf(quote);
      const {quote: _quote, ...metadata} = citation;
      const replacement = {...metadata, quoteReference: {statePath: source.path, start, end: start + quote.length,
        units: "UTF-16", sha256: createHash("sha256").update(quote).digest("hex")}};
      if (Buffer.byteLength(JSON.stringify(replacement)) >= Buffer.byteLength(JSON.stringify(citation))) return citation;
      changed = true;
      return replacement;
    }) : value,
  ]));
  return changed ? {...state, originalCitationsByCandidate} : state;
}

/** Exact line-occurrence comparison only. Full records remain in review state. */
export function memoryRewriteTextComparisons(existing: readonly unknown[], operations: readonly unknown[]): Record<string, unknown> | undefined {
  const observations = operations.flatMap(operation => {
    if (!record(operation) || (operation.op ?? operation.kind) !== "rewrite"
      || typeof operation.name !== "string" || typeof operation.content !== "string"
      || !Number.isSafeInteger(operation.candidateIndex) || Number(operation.candidateIndex) < 0) return [];
    const name = operation.name.toLowerCase();
    const matches = existing.filter(item => record(item) && typeof item.name === "string" && item.name.toLowerCase() === name);
    if (matches.length !== 1 || !record(matches[0]) || typeof matches[0].content !== "string") return [];
    const predecessor = matches[0].content, replacement = operation.content;
    // Keep CRLF, LF, final newline presence and duplicate occurrences exact.
    const lines = (text: string): string[] => text.match(/[^\n]*\n|[^\n]+$/g) ?? [];
    const oldLines = lines(predecessor), newLines = lines(replacement);
    const unmatched = (source: string[], target: string[]) => {
      const available = new Map<string, number>();
      for (const text of target) available.set(text, (available.get(text) ?? 0) + 1);
      return source.flatMap((text, index) => {
        const count = available.get(text) ?? 0;
        if (count > 0) { available.set(text, count - 1); return []; }
        return [{line: index + 1, text}];
      });
    };
    const unmatchedPredecessorLines = unmatched(oldLines, newLines);
    return [{candidateIndex: operation.candidateIndex, name: operation.name,
      predecessorSha256: createHash("sha256").update(predecessor).digest("hex"),
      replacementSha256: createHash("sha256").update(replacement).digest("hex"),
      equalLineOccurrences: oldLines.length - unmatchedPredecessorLines.length,
      unmatchedPredecessorLines, unmatchedReplacementLines: unmatched(newLines, oldLines)}];
  });
  return observations.length ? {writeAuthorized: false,
    meaning: "Parent-computed exact line-occurrence comparison of complete predecessor and replacement Markdown. Equal occurrences are counted once each; unmatched lines retain their exact text, endings and one-based original line numbers. This comparison ignores order. Equal line counts, or no unmatched predecessor lines, do not prove semantic preservation: reordered text or surrounding conditions can change meaning. Changed text is not proof of lost knowledge or supersession. Read complete records and original evidence; these facts grant no source truth, permission or mutation authority.",
    observations} : undefined;
}
