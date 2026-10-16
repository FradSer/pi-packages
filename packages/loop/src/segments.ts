/**
 * Deterministic segmentation of a free request.
 *
 * The decision service selects among these candidates; it never invents text.
 * Code owns the split so the candidate set is reproducible and bounded.
 */

const BOUNDARY = /(?<=[.。！？!?;；,，\n])/;
const TRAILING = /[.。！？!?;；,，\s]+$/;
const LEADING = /^[.。！？!?;；,，\s]+/;

/**
 * Split a request into trimmed, distinct candidate segments.
 * Return at most `limit` segments so a long request stays within one bounded
 * decision request.
 */
export function segmentRequest(request: string, limit = 12): string[] {
  const segments: string[] = [];
  const seen = new Set<string>();
  for (const raw of request.split(BOUNDARY)) {
    const text = raw.replace(TRAILING, "").replace(LEADING, "").trim();
    if (!text || seen.has(text)) continue;
    seen.add(text);
    segments.push(text);
    if (segments.length >= limit) break;
  }
  return segments;
}
