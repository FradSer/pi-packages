/**
 * Shared /loop types.
 *
 * The split is deliberate: a plan is data, and every judgment that produced it
 * is recorded beside it, so a reader can audit the decision instead of the prose.
 */

/** How a loop plan was produced. */
export type LoopMode = "parameterized" | "semantic";

/** One resolved loop: what to inject, how often, and when to stop. */
export interface LoopPlan {
  /** Message text injected on each tick, before placeholder expansion. */
  message: string;
  /** Milliseconds between ticks. */
  intervalMs: number;
  /** Total injection count. Undefined means the loop runs until it is stopped. */
  maxRuns?: number;
  /** Natural-language stopping condition, judged after each settled turn. */
  until?: string;
}

/** One decision answer with the service-reported confidence. */
export interface DecisionAnswer {
  /** The criteria key the decision service selected. */
  key: string;
  /** Service-reported confidence in the selection. */
  confidence: number;
}

/** What the decision service chose, kept for the start notice and for audits. */
export interface DecisionReport {
  interval: DecisionAnswer;
  runs: DecisionAnswer;
  stop: DecisionAnswer;
  message?: DecisionAnswer;
  /** The versioned model that answered, reported by the service. */
  model: string;
  /** Total input tokens reported by the service, when it reports them. */
  inputTokens: number;
}

/** A resolved plan together with how it was resolved. */
export interface ResolvedLoop {
  plan: LoopPlan;
  mode: LoopMode;
  report?: DecisionReport;
  /** True when the request named no cadence, so the default cadence applies. */
  intervalAssumed?: boolean;
}

/** An opaque timer identity. */
export interface TimerHandle {
  readonly id: number;
}

/** Injectable timer surface, so scheduling is testable without real time. */
export interface TimerApi {
  set(callback: () => void, ms: number): TimerHandle;
  clear(handle: TimerHandle): void;
}
