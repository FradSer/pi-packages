/**
 * The decision surface: every judgment the /loop feature needs, in one place.
 *
 * Questions are closed (noul, choice, score) because they travel through the
 * shared pi-kit decision client. Code assembles candidates; the decision
 * service selects among them. No step asks a model to write the message.
 *
 * No request carries an abort signal, because none reaches this code: Pi 1.2.0
 * reports `ctx.signal` to a hook that runs inside a turn, but `undefined` inside
 * an extension command and at the settle boundary. Each request is bounded by
 * the client's own timeout instead. Read @../AGENTS.md before adding a signal.
 */

import { askSystemOne, DecisionServiceError, type SystemOneAnswer, type SystemOneQuestion } from "@fradser/pi-kit";
import {
  INTERVAL_OPTIONS,
  RUN_LIMIT_OPTIONS,
  isRunCountSegment,
  messageCandidates,
  type TextCandidate,
} from "./candidates.ts";
import type { DecisionConfig } from "./config.ts";
import { DEFAULT_COUNT_INTERVAL_MS } from "./duration.ts";
import { segmentRequest } from "./segments.ts";
import { templateClock } from "./template.ts";
import type { DecisionAnswer, DecisionReport, LoopPlan, ResolvedLoop } from "./types.ts";

/** A decision that did not produce a usable plan, reported as a value. */
export class PlanDecisionError extends Error {
  readonly failure: string;

  constructor(failure: string, message: string) {
    super(message);
    this.name = "PlanDecisionError";
    this.failure = failure;
  }
}

export interface DecisionDeps {
  config: DecisionConfig;
  now?: Date;
}

const STOP_QUESTION = "met";

function wrap(error: unknown): PlanDecisionError {
  if (error instanceof PlanDecisionError) return error;
  if (error instanceof DecisionServiceError) return new PlanDecisionError(error.failure, error.message);
  return new PlanDecisionError("unreachable", error instanceof Error ? error.message : String(error));
}

function choiceAnswer(answer: SystemOneAnswer | undefined, allowed: readonly string[], id: string): DecisionAnswer {
  if (answer === undefined || answer.type !== "choice") {
    throw new PlanDecisionError("malformed", "The decision service returned no choice for " + id + ".");
  }
  if (!allowed.includes(answer.choice)) {
    throw new PlanDecisionError("malformed", "The decision service chose an unknown " + id + ": " + answer.choice);
  }
  return { key: answer.choice, confidence: answer.confidence };
}

function requireConfidence(answer: DecisionAnswer, minimum: number, id: string): void {
  if (answer.confidence >= minimum) return;
  throw new PlanDecisionError(
    "low-confidence",
    "The decision service was not confident about " + id + " (" + answer.confidence.toFixed(2)
      + " < " + minimum.toFixed(2) + "). State the value with flags instead.",
  );
}

function intervalCriteria(): Record<string, string | null> {
  const criteria: Record<string, string | null> = {
    unspecified: "The request names no cadence, so no listed interval is close.",
  };
  for (const option of INTERVAL_OPTIONS) criteria[option.key] = "Repeat about every " + option.key + ".";
  return criteria;
}

function runLimitCriteria(): Record<string, string | null> {
  const criteria: Record<string, string | null> = {
    unbounded: "The request names no count, so the loop repeats until the user stops it.",
  };
  for (const key of RUN_LIMIT_OPTIONS) {
    if (key === "unbounded") continue;
    criteria[key] = key === "1" ? "Inject once." : "Inject " + key + " times.";
  }
  return criteria;
}

/**
 * Criteria for the stopping-condition question. Keys index `state.segments`, so a
 * skipped entry leaves a gap: the model answers with the key it can see in state,
 * and renumbering the remainder made that key denote a different text and got a
 * correct answer rejected as unknown.
 */
function stopCriteria(segments: readonly string[], skip: (text: string) => boolean): Record<string, string | null> {
  const criteria: Record<string, string | null> = {
    none: "No candidate segment states a stopping condition.",
  };
  for (const [index, text] of segments.entries()) {
    if (skip(text)) continue;
    criteria["segment_" + index] = "This segment states the stopping condition: " + text;
  }
  return criteria;
}

function segmentFor(key: string, segments: readonly string[]): string | undefined {
  const index = Number(key.replace("segment_", ""));
  return Number.isInteger(index) ? segments[index] : undefined;
}

/**
 * Resolve a free natural-language request into a loop plan.
 *
 * The first request asks three independent questions about the same state: the
 * cadence, the run limit, and which candidate segment states the stopping
 * condition. The second request runs only when the message has more than one
 * distinct candidate, because a single candidate is not a judgment.
 *
 * An `unspecified` cadence is decided when a run count bounds the loop, and the
 * plan takes the default cadence. A request that names neither a cadence nor a
 * count is refused.
 */
export async function resolveSemanticPlan(request: string, deps: DecisionDeps): Promise<ResolvedLoop> {
  const segments = segmentRequest(request);
  if (segments.length === 0) throw new PlanDecisionError("rejected", "The request carries no text.");
  const clock = templateClock(deps.now ?? new Date());
  const state = {
    request,
    local_time: clock.date + " " + clock.time,
    segments: segments.map((text, index) => ({ key: "segment_" + index, text })),
    listed_intervals: INTERVAL_OPTIONS.map((option) => ({ key: option.key, seconds: option.ms / 1000 })),
    listed_run_limits: RUN_LIMIT_OPTIONS.map((key) => ({ key })),
  };

  // The criteria objects are the single source of truth for both the
  // question and the validation of its answer, so a declared option can
  // never be rejected as unknown. A count-only segment is the run limit, which
  // the `runs` question already reads, so it is not offered as a stopping
  // condition and is stripped from the message instead.
  const intervalKeys = intervalCriteria();
  const runKeys = runLimitCriteria();
  const counted = segments.filter(isRunCountSegment);
  const stopKeys = stopCriteria(segments, isRunCountSegment);

  const questions: Record<string, SystemOneQuestion> = {
    interval: {
      type: "choice",
      instructions:
        "A user asks Pi to repeat one message on a schedule. Choose the listed interval closest to the requested cadence. Choose unspecified when the request names no cadence. Judge the cadence only, never the content of the message.",
      criteria: intervalKeys,
    },
    runs: {
      type: "choice",
      instructions:
        "Choose how many times the loop injects the message before it stops by itself. Choose unbounded when the request names no count. A stopping condition is not a count.",
      criteria: runKeys,
    },
    stop: {
      type: "choice",
      instructions:
        "Choose the candidate segment that states a condition which must end the loop. Choose none when no segment states a stopping condition. A repeated instruction is not a stopping condition. A segment that states only how many repetitions to run is not a stopping condition either: that count is the run limit.",
      criteria: stopKeys,
    },
  };

  let first: Awaited<ReturnType<typeof askSystemOne>>;
  try {
    first = await askSystemOne({
      baseUrl: deps.config.baseUrl,
      apiKey: deps.config.apiKey,
      model: deps.config.model,
      state,
      questions,
    });
  } catch (error) {
    throw wrap(error);
  }

  const interval = choiceAnswer(first.answers.interval, Object.keys(intervalKeys), "the interval");
  const runs = choiceAnswer(first.answers.runs, Object.keys(runKeys), "the run limit");
  const stop = choiceAnswer(first.answers.stop, Object.keys(stopKeys), "the stopping condition");
  requireConfidence(interval, deps.config.minChoiceConfidence, "the interval");
  requireConfidence(runs, deps.config.minChoiceConfidence, "the run limit");
  requireConfidence(stop, deps.config.minChoiceConfidence, "the stopping condition");
  // A run count bounds the loop, so an unnamed cadence is decided rather than
  // refused. Without a count, nothing bounds it: a guessed cadence could repeat
  // an unbounded loop for as long as the session lives.
  const bounded = runs.key !== "unbounded";
  const intervalAssumed = interval.key === "unspecified";
  if (intervalAssumed && !bounded) {
    throw new PlanDecisionError(
      "rejected",
      "The request names no cadence and no run count. Add --every, name a cadence, or state how many times to repeat, for example \"3 times\".",
    );
  }

  const stopSegment = stop.key === "none" ? undefined : segmentFor(stop.key, segments);
  const candidates: TextCandidate[] = messageCandidates(request, stopSegment, counted);
  const fallback = candidates[0]?.text ?? request.trim();
  let message = fallback;
  let messageAnswer: DecisionAnswer | undefined;
  let inputTokens = first.usage.inputTokens ?? 0;
  let model = first.model;

  if (candidates.length >= 2) {
    const criteria: Record<string, string | null> = {};
    for (const candidate of candidates) criteria[candidate.key] = candidate.text;
    let second: Awaited<ReturnType<typeof askSystemOne>>;
    try {
      second = await askSystemOne({
        baseUrl: deps.config.baseUrl,
        apiKey: deps.config.apiKey,
        model: deps.config.model,
        state: {
          request,
          stop_condition: stopSegment ?? null,
          candidates: candidates.map((candidate) => ({ key: candidate.key, text: candidate.text })),
        },
        questions: {
          message: {
            type: "choice",
            instructions:
              "Choose the candidate text that Pi injects as the message on every repetition. Keep the task. Drop scheduling metadata and the stopping condition.",
            criteria,
          },
        },
      });
    } catch (error) {
      throw wrap(error);
    }
    const selected = choiceAnswer(second.answers.message, candidates.map((candidate) => candidate.key), "the message");
    requireConfidence(selected, deps.config.minChoiceConfidence, "the message");
    message = candidates.find((candidate) => candidate.key === selected.key)?.text ?? fallback;
    messageAnswer = selected;
    inputTokens += second.usage.inputTokens ?? 0;
    model = second.model;
  }

  const intervalMs = intervalAssumed
    ? DEFAULT_COUNT_INTERVAL_MS
    : INTERVAL_OPTIONS.find((option) => option.key === interval.key)?.ms;
  if (intervalMs === undefined) throw new PlanDecisionError("malformed", "The selected interval is not listed.");

  const plan: LoopPlan = { message, intervalMs };
  if (runs.key !== "unbounded") plan.maxRuns = Number(runs.key);
  if (stopSegment !== undefined) plan.until = stopSegment;

  const report: DecisionReport = { interval, runs, stop, model, inputTokens };
  if (messageAnswer !== undefined) report.message = messageAnswer;
  return intervalAssumed
    ? { plan, mode: "semantic", report, intervalAssumed }
    : { plan, mode: "semantic", report };
}

/**
 * Judge whether a settled turn satisfies a natural-language stop condition.
 *
 * A near-half probability means the two outcomes are about equally likely, so
 * the loop keeps running: an unfinished task is the common case, and stopping
 * early would abandon it.
 */
export async function judgeStopCondition(options: {
  config: DecisionConfig;
  condition: string;
  lastAssistantMessage: string;
}): Promise<{ met: boolean; probability: number }> {
  let result: Awaited<ReturnType<typeof askSystemOne>>;
  try {
    result = await askSystemOne({
      baseUrl: options.config.baseUrl,
      apiKey: options.config.apiKey,
      model: options.config.model,
      state: { condition: options.condition, last_assistant_message: options.lastAssistantMessage },
      questions: {
        [STOP_QUESTION]: {
          type: "noul",
          instructions:
            "Decide whether the assistant's most recent message establishes that the stopping condition is satisfied. Judge the condition against that message only. An unfinished task, a plan to check later, or an unanswered question is not satisfied.",
          criteria: {
            true: "The message establishes that the condition is satisfied.",
            false: "The message does not establish it, or the task is unfinished.",
          },
        },
      },
    });
  } catch (error) {
    throw wrap(error);
  }
  const answer = result.answers[STOP_QUESTION];
  if (answer === undefined || answer.type !== "noul") {
    throw new PlanDecisionError("malformed", "The stopping judgment returned no probability.");
  }
  return { met: answer.noul >= options.config.stopThreshold, probability: answer.noul };
}
