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

const COUNT_WORDS = "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|several|a few";
// A digit may take an English or Chinese unit ("10 次"), a Chinese numeral its
// own, and "once"/"twice" carry the count without a unit at all.
const COUNT_UNITS = "times?|x|repetitions?|cycles?|rounds?|次|回|遍";
const COUNT_CHINESE = "[零一二三四五六七八九十百两]+|半";
const COUNT_ALONE = "once|twice";

/** A count phrase that carries a unit: "3 times", "five times", "10 次". */
function countPhrase(): string {
  return "(?:[0-9]+|(?:" + COUNT_WORDS + "))\\s*(?:" + COUNT_UNITS + ")"
    + "|(?:" + COUNT_CHINESE + ")\\s*(?:" + COUNT_UNITS + ")";
}

/**
 * Whether a segment states only how many repetitions to run.
 *
 * A count is the run limit, not a condition Pi can judge after a turn: a
 * measured run of the real service chose "3 times" as the stopping condition for
 * four count-only requests, which left the plan with an unjudgeable condition and
 * one extra decision request per settled turn. The `runs` question already reads
 * the count, so the segment is excluded from the stopping-condition candidates and
 * stripped from the message instead.
 */
export function isRunCountSegment(text: string): boolean {
  const trimmed = text.trim().toLowerCase();
  if (!trimmed) return false;
  return new RegExp("^(?:" + countPhrase() + ")$|^(?:" + COUNT_ALONE + ")$").test(trimmed);
}

/**
 * Remove a count phrase that sits inside a request, and return the remainder.
 *
 * The count is the run limit wherever it appears, so the message keeps the
 * user's own task words and drops the number: "输入3次Hi" repeats "输入Hi". A bare
 * "once" or "twice" is not removed here, because inside a sentence it is as
 * likely to be ordinary text as a run limit; a segment that is only "twice" is
 * still offered as a count by {@link isRunCountSegment}.
 *
 * Return undefined when nothing was removed, so a caller never treats an
 * unchanged text as a stripped one.
 */
export function stripRunCount(text: string): string | undefined {
  const stripped = tidy(text.replace(new RegExp(countPhrase(), "gi"), ""));
  return stripped && stripped !== tidy(text) ? stripped : undefined;
}

/**
 * Remove a schedule phrase, then a count phrase that sits inside the text.
 * Report which kind was removed, so the candidate key names it.
 */
function reduceMetadata(text: string): { text: string; count: boolean } | undefined {
  const scheduled = stripSchedulePhrase(text);
  const counted = stripRunCount(scheduled ?? text);
  const result = counted ?? scheduled;
  if (result === undefined || result === text) return undefined;
  return { text: result, count: counted !== undefined };
}

/**
 * Build the candidate texts for the repeated instruction.
 * Candidates are deduplicated by text, so a selection is never a choice between
 * identical strings. A degenerate set of one candidate needs no judgment. Every
 * schedule phrase, every run count and the segment that states the stopping
 * condition are removed, so the message repeats the task alone.
 */
export function messageCandidates(
  request: string,
  stopSegment?: string,
  dropSegments: readonly string[] = [],
): TextCandidate[] {
  const full = request.trim();
  let withoutStop = full;
  for (const segment of stopSegment === undefined ? [] : [stopSegment]) {
    withoutStop = stripSegment(withoutStop, segment) ?? withoutStop;
  }
  for (const segment of dropSegments) {
    withoutStop = stripSegment(withoutStop, segment) ?? withoutStop;
  }
  const stripped = withoutStop === full ? undefined : withoutStop;
  const candidates: TextCandidate[] = [];
  const push = (key: string, text: string | undefined): void => {
    if (text === undefined) return;
    const value = text.trim();
    if (!value || candidates.some((candidate) => candidate.text === value)) return;
    candidates.push({ key, text: value });
  };
  if (stripped === undefined) {
    // No segment was filtered, so only the text's own metadata can leave: the
    // deepest candidate goes first, and a skipped message question falls back to
    // the task without its scheduling metadata rather than to the whole request.
    const reduced = reduceMetadata(full);
    if (reduced !== undefined) push(reduced.count ? "without_count" : "without_schedule", reduced.text);
    push("full", full);
    return candidates;
  }
  const deep = reduceMetadata(stripped);
  push(deep?.count === true ? "without_count" : "without_schedule_and_stop", deep?.text);
  push("without_stop", stripped);
  push("full", full);
  return candidates;
}
