/**
 * Shadow observation of the Memory Selector.
 *
 * Judgment observes; the selector decides. Nothing returned here reaches
 * Memory, Harness, or AGENTS.md, and no failure here — refused connection,
 * throttling, malformed answer, cancellation — changes what the run produces.
 * An observer failing must not stop the observed work.
 */

import { DecisionServiceError, askSystemOne } from "@fradser/pi-kit";
import { resolveJudgmentConfig, type JudgmentConfigInput } from "./judgment-config";
import {
  buildJudgmentProjection,
  collectJudgmentVerdicts,
  judgmentSelectedNames,
  type JudgmentProjectionInput,
} from "./judgment-projection";
import {
  buildProposalProjection,
  proposalsJudgmentWouldKeep,
  PROPOSAL_NO_MATCH,
  PROPOSAL_PREFIXES,
  type MemoryProposalProjectionInput,
} from "./judgment-proposals";
import { buildPlanProjection, type PlanProjectionInput, type Surface } from "./judgment-plans";
import { appendJudgmentObservation, type JudgmentObservation } from "./judgment-observations";

/**
 * Reporting-only threshold used to name what Judgment would have selected so a
 * shadow run can be compared with the selector. It is not a decision and not a
 * tuned constant; the promotion report is what says which value to use.
 */
export const REPORTING_THRESHOLD = 0.5;

/**
 * Generality level at or above which a proposal generalizes beyond the single
 * occurrence that produced it.
 *
 * This was first set to 2, "reusable in any project", which is wrong for this
 * package: its whole purpose is project-specific knowledge, and live runs score
 * exactly that at 1.0-1.3 while scoring genuine one-off noise at 0.09. At 2 the
 * kept list was structurally always empty, which reads as "the model thinks
 * nothing is worth keeping" — the opposite of what it measured.
 *
 * Level 1 is the meaningful cut for this corpus: reusable here versus a record
 * of one occurrence. Reporting only; no proposal is ever dropped on it.
 */
export const REPORTING_GENERALITY = 1;

export interface ObserveJudgmentInput {
  cwd: string;
  contextDigest: string;
  projection: JudgmentProjectionInput;
  selector: { selected: string[]; memory: boolean; harness: boolean; agents: boolean };
  signal?: AbortSignal;
  config?: JudgmentConfigInput;
  agentDir?: string;
}

function sameSelection(left: readonly string[], right: readonly string[]): boolean {
  if (left.length !== right.length) return false;
  const a = [...left].sort((x, y) => x.localeCompare(y));
  const b = [...right].sort((x, y) => x.localeCompare(y));
  return a.every((value, index) => value === b[index]);
}

function baseObservation(input: ObserveJudgmentInput): JudgmentObservation {
  return {
    version: 1,
    phase: "selector",
    contextDigest: input.contextDigest,
    model: null,
    outcome: "failed",
    judged: false,
    values: {},
    confidences: {},
    selectorSelected: input.selector.selected,
    selectorRouted: {
      memory: input.selector.memory,
      harness: input.selector.harness,
      agents: input.selector.agents,
    },
    judgmentSelected: [],
    agrees: false,
  };
}

function record(input: ObserveJudgmentInput, observation: JudgmentObservation): void {
  appendJudgmentObservation(input.cwd, observation, input.agentDir);
}

/**
 * Run one shadow observation and return the record that was written. The
 * selector's own selection is the answer the caller keeps; this exists only to
 * be comparable with it.
 */
export async function observeJudgmentShadow(input: ObserveJudgmentInput): Promise<JudgmentObservation> {
  const config = resolveJudgmentConfig(input.config ?? { agentDir: input.agentDir });
  if (!config.active) {
    // Inactive is not an observation: no request, no record, no trace.
    return baseObservation(input);
  }

  const projection = buildJudgmentProjection(input.projection);
  try {
    const result = await askSystemOne({
      baseUrl: config.baseUrl,
      apiKey: config.apiKey,
      model: config.model,
      state: projection.state,
      questions: projection.questions,
      ...(input.signal ? { signal: input.signal } : {}),
    });
    const { values, confidences } = collectJudgmentVerdicts(result.answers);
    const judgmentSelected = judgmentSelectedNames(values, projection, REPORTING_THRESHOLD);
    const observation: JudgmentObservation = {
      ...baseObservation(input),
      model: result.model,
      outcome: "observed",
      judged: true,
      values,
      confidences,
      judgmentSelected,
      agrees: sameSelection(judgmentSelected, input.selector.selected),
      ...(result.usage.inputTokens === undefined && result.usage.outputTokens === undefined
        ? {}
        : { usage: result.usage }),
    };
    record(input, observation);
    return observation;
  } catch (error) {
    const cancelled = error instanceof DecisionServiceError && error.failure === "cancelled";
    const observation: JudgmentObservation = {
      ...baseObservation(input),
      outcome: cancelled ? "cancelled" : "failed",
      reason: error instanceof Error ? error.message.slice(0, 200) : "judgment observation failed",
    };
    record(input, observation);
    return observation;
  }
}

// ── Memory proposals ────────────────────────────────────────────────────

/** A proposal observation. One record type covers both phases: a second type
 *  would not be writable without a cast. These three are required here because
 *  a proposal observation always sets them, and a reader of a proposal record
 *  should not have to re-check for their absence. */
export type MemoryProposalObservation = JudgmentObservation & {
  phase: "proposals";
  proposed: number;
  kept: string[];
  duplicates: string[];
};

export interface ObserveProposalsInput {
  cwd: string;
  contextDigest: string;
  projection: MemoryProposalProjectionInput;
  signal?: AbortSignal;
  config?: JudgmentConfigInput;
  agentDir?: string;
}

/**
 * Observe a validated Memory plan's proposals. **Nothing here changes what the
 * parent writes.** A plan with no proposals makes no request at all, so a run
 * that adds nothing costs nothing.
 */
export async function observeMemoryProposals(input: ObserveProposalsInput): Promise<MemoryProposalObservation> {
  const base: MemoryProposalObservation = {
    version: 1,
    phase: "proposals",
    selectorSelected: [],
    selectorRouted: { memory: false, harness: false, agents: false },
    judgmentSelected: [],
    // The parent applies every proposal, so there is no competing decision for
    // this record to agree or differ from.
    agrees: true,
    contextDigest: input.contextDigest,
    model: null,
    outcome: "failed",
    judged: false,
    values: {},
    confidences: {},
    proposed: input.projection.proposals.length,
    kept: [],
    duplicates: [],
  };
  const config = resolveJudgmentConfig(input.config ?? { agentDir: input.agentDir });
  if (!config.active || input.projection.proposals.length === 0) return base;

  const projection = buildProposalProjection(input.projection);
  try {
    const result = await askSystemOne({
      baseUrl: config.baseUrl,
      apiKey: config.apiKey,
      model: config.model,
      state: projection.state,
      questions: projection.questions,
      ...(input.signal ? { signal: input.signal } : {}),
    });
    const { values, confidences } = collectJudgmentVerdicts(result.answers);
    const duplicates = Object.entries(values)
      .filter(([id, value]) => id.startsWith(PROPOSAL_PREFIXES.duplicate) && typeof value === "string" && value !== PROPOSAL_NO_MATCH)
      .map(([id, value]) => `${id.slice(PROPOSAL_PREFIXES.duplicate.length)}=${String(value)}`);
    const observation: MemoryProposalObservation = {
      ...base,
      model: result.model,
      outcome: "observed",
      judged: true,
      values,
      // Generality and duplication are a score and a choice, so unlike every
      // selector question they do carry one. This is the first place the
      // confidence axis of the record has anything in it.
      confidences,
      kept: proposalsJudgmentWouldKeep(values, projection, REPORTING_GENERALITY),
      duplicates,
    };
    appendJudgmentObservation(input.cwd, observation, input.agentDir);
    return observation;
  } catch (error) {
    const cancelled = error instanceof DecisionServiceError && error.failure === "cancelled";
    const observation: MemoryProposalObservation = {
      ...base,
      outcome: cancelled ? "cancelled" : "failed",
      reason: error instanceof Error ? error.message.slice(0, 200) : "judgment observation failed",
    };
    appendJudgmentObservation(input.cwd, observation, input.agentDir);
    return observation;
  }
}

// ── Remaining plan surfaces ─────────────────────────────────────────────

export type PlanObservation = JudgmentObservation & {
  phase: "operations";
  surface: Surface;
  /** How many operations the plan carried, which the parent applied regardless. */
  operations: number;
  /** Closed-set answers worth surfacing, keyed `axis:id`. Never authoritative. */
  verdictsByAxis: Record<string, string>;
};

export interface ObservePlanInput {
  cwd: string;
  contextDigest: string;
  projection: PlanProjectionInput;
  signal?: AbortSignal;
  config?: JudgmentConfigInput;
  agentDir?: string;
}

/**
 * Observe one plan surface — Memory operations, Harness rules, or AGENTS.md
 * instructions. **The parent applies the plan exactly as it does today.**
 *
 * A surface with nothing to judge costs nothing: an empty operation list with no
 * selected entries produces no questions and therefore no request.
 */
export async function observePlanSurface(input: ObservePlanInput): Promise<PlanObservation> {
  const base: PlanObservation = {
    version: 1,
    phase: "operations",
    surface: input.projection.surface,
    contextDigest: input.contextDigest,
    model: null,
    outcome: "failed",
    judged: false,
    values: {},
    confidences: {},
    selectorSelected: [],
    selectorRouted: { memory: false, harness: false, agents: false },
    judgmentSelected: [],
    // Nothing competes with the parent here, so there is no disagreement to
    // report. This stays true rather than being read as a clean bill of health.
    agrees: true,
    operations: input.projection.operations.length,
    verdictsByAxis: {},
  };
  const config = resolveJudgmentConfig(input.config ?? { agentDir: input.agentDir });
  if (!config.active) return base;
  const projection = buildPlanProjection(input.projection);
  if (Object.keys(projection.questions).length === 0) return base;

  try {
    const result = await askSystemOne({
      baseUrl: config.baseUrl,
      apiKey: config.apiKey,
      model: config.model,
      state: projection.state,
      questions: projection.questions,
      ...(input.signal ? { signal: input.signal } : {}),
    });
    const { values, confidences } = collectJudgmentVerdicts(result.answers);
    const verdictsByAxis: Record<string, string> = {};
    for (const [id, value] of Object.entries(values)) {
      if (typeof value !== "string") continue;
      const separator = id.indexOf("::");
      if (separator <= 0) continue;
      verdictsByAxis[`${id.slice(0, separator)}:${id.slice(separator + 2)}`] = value;
    }
    const observation: PlanObservation = {
      ...base,
      model: result.model,
      outcome: "observed",
      judged: true,
      values,
      // The closed-set questions are choices and a score, so they carry a
      // confidence; only the noul axes do not.
      confidences,
      verdictsByAxis,
    };
    appendJudgmentObservation(input.cwd, observation, input.agentDir);
    return observation;
  } catch (error) {
    const cancelled = error instanceof DecisionServiceError && error.failure === "cancelled";
    const observation: PlanObservation = {
      ...base,
      outcome: cancelled ? "cancelled" : "failed",
      reason: error instanceof Error ? error.message.slice(0, 200) : "judgment observation failed",
    };
    appendJudgmentObservation(input.cwd, observation, input.agentDir);
    return observation;
  }
}
