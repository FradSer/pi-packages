/**
 * Decision-service configuration and the explicit probability thresholds.
 *
 * A missing credential is not a default: semantic mode fails closed instead of
 * guessing an interval, and --until fails closed instead of never stopping.
 */

export const DEFAULT_DECISION_BASE_URL = "https://api.typesafe.ai";
/** A pinned version, because an alias silently changes every tuned answer. */
export const DEFAULT_DECISION_MODEL = "jev-1.13.0";
/** Probability above which a met stopping condition ends the loop. */
export const DEFAULT_STOP_THRESHOLD = 0.8;
/** Minimum choice confidence accepted for a plan selection. */
export const DEFAULT_MIN_CHOICE_CONFIDENCE = 0.3;

export interface DecisionConfig {
  baseUrl: string;
  apiKey: string;
  model: string;
  stopThreshold: number;
  minChoiceConfidence: number;
}

type Env = Record<string, string | undefined>;

function unitInterval(value: string | undefined, fallback: number): number {
  if (value === undefined || value.trim() === "") return fallback;
  const parsed = Number(value.trim());
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 1 ? parsed : fallback;
}

/**
 * Read the decision configuration, or undefined when no credential is present.
 * The credential is never logged and never written into a message.
 */
export function readDecisionConfig(env: Env = process.env): DecisionConfig | undefined {
  const apiKey = env.TYPESAFE_API_KEY?.trim();
  if (!apiKey) return undefined;
  return {
    apiKey,
    baseUrl: env.TYPESAFE_BASE_URL?.trim() || DEFAULT_DECISION_BASE_URL,
    model: env.TYPESAFE_MODEL?.trim() || DEFAULT_DECISION_MODEL,
    stopThreshold: unitInterval(env.LOOP_STOP_THRESHOLD, DEFAULT_STOP_THRESHOLD),
    minChoiceConfidence: unitInterval(env.LOOP_MIN_CHOICE_CONFIDENCE, DEFAULT_MIN_CHOICE_CONFIDENCE),
  };
}
