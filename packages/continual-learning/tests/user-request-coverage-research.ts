/** Research only: exhaustive text spans are not extracted durable requirements. */
import type {FrozenRequirement} from './request-completeness-research.ts';

type Coverage = {
  status: 'covered' | 'unavailable';
  reason?: 'invalid-source' | 'empty-source' | 'capacity';
  requirements: FrozenRequirement[];
  scope: 'text-coverage-only';
  writeAuthorized: false;
};
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);

export function enumerateUserRequestCoverage(snapshot: unknown, selectedEntryIndices: readonly number[]): Coverage {
  const unavailable = (reason: NonNullable<Coverage['reason']>): Coverage => ({
    status:'unavailable', reason, requirements:[], scope:'text-coverage-only', writeAuthorized:false,
  });
  if (!record(snapshot) || snapshot.contextEnabled !== true || !Array.isArray(snapshot.entries)
    || !Array.isArray(selectedEntryIndices) || selectedEntryIndices.length < 1
    || new Set(selectedEntryIndices).size !== selectedEntryIndices.length) return unavailable('invalid-source');
  const requirements: FrozenRequirement[] = [];
  // Sentence boundaries are hints for focused questions, never a semantic relevance filter.
  const segmenter = new Intl.Segmenter('und', {granularity:'sentence'});
  for (const index of selectedEntryIndices) {
    if (!Number.isSafeInteger(index) || index < 0) return unavailable('invalid-source');
    const entry = snapshot.entries[index];
    if (!record(entry) || entry.role !== 'user' || typeof entry.content !== 'string') return unavailable('invalid-source');
    const content = entry.content;
    if (!content.trim()) return unavailable('empty-source');
    const protectedRanges: [number, number][] = [];
    for (const match of content.matchAll(/`+/g)) {
      const start = match.index;
      if (protectedRanges.some(([from,to]) => start >= from && start < to)) continue;
      const closing = [...content.slice(start + match[0].length).matchAll(/`+/g)]
        .find(candidate => candidate[0].length === match[0].length);
      const end = closing ? start + match[0].length + closing.index + closing[0].length : content.length;
      protectedRanges.push([start,end]);
    }
    const boundaries = new Set<number>([content.length]);
    for (const sentence of segmenter.segment(content)) boundaries.add(sentence.index + sentence.segment.length);
    for (const match of content.matchAll(/[;；\n]/g)) boundaries.add(match.index + match[0].length);
    let start = 0;
    for (const end of [...boundaries].sort((a,b) => a-b)) {
      if (protectedRanges.some(([from,to]) => end > from && end < to)) continue;
      if (!content.slice(start,end).trim()) continue;
      requirements.push({index,start,end,quote:content.slice(start,end)});
      start = end;
    }
    // Keep trailing whitespace in the last span so coverage is exact, including UTF-16 offsets.
    if (start < content.length) {
      const last = requirements[requirements.length-1];
      last.end = content.length;
      last.quote = content.slice(last.start,last.end);
    }
    if (requirements.length > 31) return unavailable('capacity');
  }
  return {status:'covered',requirements,scope:'text-coverage-only',writeAuthorized:false};
}
