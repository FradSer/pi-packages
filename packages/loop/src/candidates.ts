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

/**
 * The listed repeating intervals a semantic request can select.
 *
 * The interval question answers with the closest listed cadence, so the set must not
 * leave a gap that a stated cadence falls into: with only 1h and 1d listed, the
 * request "每 2 个小时" resolved to 1h, half the cadence the user asked for. The hour
 * steps here stay within a factor of two of each other. The sub-hour steps allow up
 * to five, which bounds the whole set.
 */
export const INTERVAL_OPTIONS: readonly IntervalOption[] = [
  { key: "30s", ms: 30000 },
  { key: "1m", ms: 60000 },
  { key: "5m", ms: 300000 },
  { key: "15m", ms: 900000 },
  { key: "30m", ms: 1800000 },
  { key: "1h", ms: 3600000 },
  { key: "2h", ms: 7200000 },
  { key: "4h", ms: 14400000 },
  { key: "6h", ms: 21600000 },
  { key: "8h", ms: 28800000 },
  { key: "12h", ms: 43200000 },
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
      // The measure word is optional and common: "每 2 个小时" is the same cadence
      // as "每 2 小时", and "每隔2个小时" is the same cadence again. A pattern that
      // required the unit to follow the number matched none of them, so the
      // cadence stayed inside the repeated message.
      "每(?:隔)?\\s*(?:[0-9]+|[零一二三四五六七八九十百两]+|半)\\s*(?:个|個)?\\s*(?:毫秒|秒钟|秒|分钟|分|小时|钟头|天)",
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

/**
 * A count phrase: a number with a unit ("3 times", "10 次"), or a multiplier
 * prefix ("* 3", "x3", "× 3"). The multiplier form is the shape a user reaches
 * for when they mean "say this N times".
 */
function countPhrase(): string {
  return "(?:[0-9]+|(?:" + COUNT_WORDS + "))\\s*(?:" + COUNT_UNITS + ")"
    + "|(?:" + COUNT_CHINESE + ")\\s*(?:" + COUNT_UNITS + ")"
    + "|[*×]\\s*(?:[0-9]+|(?:" + COUNT_CHINESE + "))";
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
 *
 * The service's own answer is the only text-shaping judgment: the segment it named
 * as the stopping condition. A dropped count segment and a schedule phrase are
 * metadata this module matched itself, so when the service named no stopping
 * condition the metadata-free text is the message and no question is asked.
 */
export function messageCandidates(
  request: string,
  stopSegment?: string,
  dropSegments: readonly string[] = [],
): TextCandidate[] {
  const full = request.trim();
  /** The request without the segments code matched as a run count. */
  let withoutCounts = full;
  for (const segment of dropSegments) {
    withoutCounts = stripSegment(withoutCounts, segment) ?? withoutCounts;
  }
  const candidates: TextCandidate[] = [];
  const push = (key: string, text: string | undefined): void => {
    if (text === undefined) return;
    const value = text.trim();
    if (!value || candidates.some((candidate) => candidate.text === value)) return;
    candidates.push({ key, text: value });
  };
  if (stopSegment === undefined) {
    // Nothing the service answered shaped the text, so there is nothing to judge:
    // the metadata-free text is the message. Offering the request back asked the
    // service to repeat a decision code had already made, and a low-confidence
    // answer to that choice refused a command whose message was never in doubt:
    // "watch the logs every minute, 10 times" failed at 0.27 < 0.30 against the
    // live service (tests/real-jev-accuracy.ts).
    const reduced = reduceMetadata(withoutCounts);
    if (reduced === undefined) {
      push("full", full);
      return candidates;
    }
    push(withoutCounts !== full || reduced.count ? "without_count" : "without_schedule", reduced.text);
    return candidates;
  }
  // The service named the stopping-condition segment, so its own answer shaped the
  // text: the candidates differ in how much of the request they keep.
  const withoutStop = stripSegment(withoutCounts, stopSegment) ?? withoutCounts;
  const deep = reduceMetadata(withoutStop);
  push(deep?.count === true ? "without_count" : "without_schedule_and_stop", deep?.text);
  // The key names what happened: a request the answer did not change stays the full
  // text, so a degenerate candidate set is still reported as the request itself.
  push(withoutStop === full ? "full" : "without_stop", withoutStop);
  push("full", full);
  return candidates;
}
