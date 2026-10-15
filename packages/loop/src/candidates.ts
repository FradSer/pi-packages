/**
 * Candidate sets for the decision questions, and deterministic text assembly.
 *
 * The decision service chooses a candidate key. Code then builds the final
 * message from the selected pieces. A value the model cannot see is a value it
 * cannot choose, so these lists define its reachable answers.
 */

export interface IntervalOption {
  key: string;
  ms: number;
}

export interface TextCandidate {
  key: string;
  text: string;
}

/** The listed repeating intervals a semantic request can select. */
export const INTERVAL_OPTIONS: readonly IntervalOption[] = [
  { key: "30s", ms: 30000 },
  { key: "1m", ms: 60000 },
  { key: "5m", ms: 300000 },
  { key: "15m", ms: 900000 },
  { key: "30m", ms: 1800000 },
  { key: "1h", ms: 3600000 },
  { key: "1d", ms: 86400000 },
];

/** The listed run limits a semantic request can select. */
export const RUN_LIMIT_OPTIONS: readonly string[] = ["unbounded", "1", "3", "5", "10", "20"];

function schedulePattern(): RegExp {
  return new RegExp(
    [
      "\\bevery\\s+(?:[0-9]+|a|an|half\\s+an)\\s*(?:ms|milliseconds?|s|secs?|seconds?|m|mins?|minutes?|h|hrs?|hours?|d|days?)\\b",
      "\\bevery\\s+(?:second|minute|hour|day)\\b",
      "\\bonce\\s+(?:a|per)\\s+(?:second|minute|hour|day)\\b",
      "\\bevery\\s+[a-z-]+\\s+(?:seconds?|minutes?|hours?|days?)\\b",
      "每\\s*(?:[0-9]+|[零一二三四五六七八九十百]+|半)\\s*(?:毫秒|秒钟|秒|分钟|分|小时|钟头|天)",
      "(?:每小时|每分钟|每天|每秒)",
    ].join("|"),
    "gi",
  );
}

const EDGE = /^[\s,.;:，。；：、]+|[\s,.;:，。；：、]+$/g;
const LEADING_CONNECTOR = /^(?:and|then|also)\s+/i;
const LEADING_PARTICLE = /^(?:然后|就|再|并且|而且)/;

function tidy(text: string): string {
  return text
    .replace(/\s{2,}/g, " ")
    .replace(EDGE, "")
    .replace(LEADING_CONNECTOR, "")
    .replace(LEADING_PARTICLE, "")
    .trim();
}

/**
 * Remove a recognised scheduling phrase from a request.
 * Return undefined when the request carries no recognised phrase, so a caller
 * never treats an unchanged request as a stripped one.
 */
export function stripSchedulePhrase(request: string): string | undefined {
  if (!schedulePattern().test(request)) return undefined;
  const stripped = tidy(request.replace(schedulePattern(), " "));
  return stripped || undefined;
}

function stripSegment(request: string, segment: string): string | undefined {
  const at = request.indexOf(segment);
  if (at < 0) return undefined;
  const without = tidy(request.slice(0, at) + " " + request.slice(at + segment.length));
  return without || undefined;
}

/**
 * Build the candidate texts for the repeated instruction.
 * Candidates are deduplicated by text, so a selection is never a choice between
 * identical strings. A degenerate set of one candidate needs no judgment.
 */
export function messageCandidates(request: string, stopSegment?: string): TextCandidate[] {
  const full = request.trim();
  const withoutSchedule = stripSchedulePhrase(full);
  const withoutStop = stopSegment === undefined ? undefined : stripSegment(full, stopSegment);
  const withoutBoth = withoutStop === undefined ? undefined : stripSchedulePhrase(withoutStop);
  const candidates: TextCandidate[] = [];
  const push = (key: string, text: string | undefined): void => {
    if (text === undefined) return;
    const value = text.trim();
    if (!value || candidates.some((candidate) => candidate.text === value)) return;
    candidates.push({ key, text: value });
  };
  if (stopSegment === undefined) {
    push("without_schedule", withoutSchedule);
    push("full", full);
  } else {
    push("without_schedule_and_stop", withoutBoth);
    push("without_stop", withoutStop);
    push("full", full);
  }
  return candidates;
}
