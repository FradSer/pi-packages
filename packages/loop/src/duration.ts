/**
 * Deterministic duration parsing and formatting.
 *
 * A tick interval is arithmetic, not judgment: the user writes the cadence or
 * the request names it, and this module resolves it. The bounds exist so that a
 * malformed or hostile request cannot flood the session with turns.
 */

/** The shortest permitted interval: one second. */
export const MIN_INTERVAL_MS = 1000;
/** The longest permitted interval: one day. */
export const MAX_INTERVAL_MS = 86400000;

const UNIT_MS = { ms: 1, s: 1000, m: 60000, h: 3600000, d: 86400000 } as const;

type Unit = keyof typeof UNIT_MS;

function bounded(ms: number): number | undefined {
  if (!Number.isFinite(ms)) return undefined;
  if (ms < MIN_INTERVAL_MS || ms > MAX_INTERVAL_MS) return undefined;
  return ms;
}

/**
 * Parse a duration text such as "30s", "5m", "1h30m", "2d" or "90".
 * A bare number counts as seconds; one minute is "1m". Return undefined for
 * any other text, for a gap that is not whitespace, and for a value that falls
 * outside the permitted bounds.
 */
export function parseDuration(input: string): number | undefined {
  const text = input.trim().toLowerCase();
  if (!text) return undefined;
  if (/^[0-9]+$/.test(text)) return bounded(Number(text) * 1000);

  const pattern = /([0-9]+)\s*(ms|s|m|h|d)/g;
  let total = 0;
  let consumed = 0;
  for (let match = pattern.exec(text); match !== null; match = pattern.exec(text)) {
    if (text.slice(consumed, match.index).trim() !== "") return undefined;
    const amount = match[1];
    const unit = match[2] as Unit | undefined;
    if (amount === undefined || unit === undefined) return undefined;
    total += Number(amount) * UNIT_MS[unit];
    consumed = pattern.lastIndex;
  }
  if (consumed === 0 || consumed !== text.length) return undefined;
  return bounded(total);
}

/** Format milliseconds with at most two units, for notices and status rows. */
export function formatDuration(ms: number): string {
  const units: readonly [string, number][] = [["d", 86400000], ["h", 3600000], ["m", 60000], ["s", 1000]];
  const parts: string[] = [];
  let rest = ms;
  for (const [suffix, size] of units) {
    const count = Math.floor(rest / size);
    if (count === 0) continue;
    parts.push(count + suffix);
    rest -= count * size;
    if (parts.length === 2) break;
  }
  if (parts.length === 0) return ms + "ms";
  return parts.join("");
}
