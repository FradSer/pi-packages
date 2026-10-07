import { SEVERITY_LEVELS, triageId } from "./questions.ts";
import type {
  ClauseResult,
  ModelVerdict,
  Policy,
  Scenario,
  Severity,
  TriageItem,
  TriageResult,
  Usage,
  Verdict,
  VerdictStatus,
} from "./types.ts";
import type { ChoiceAnswer, ModelAnswer, ScoreAnswer } from "./typesafe.ts";

export interface ComposeInput {
  readonly scenario: Scenario;
  readonly clauses: readonly ClauseResult[];
  readonly answers: Readonly<Record<string, ModelAnswer>>;
  readonly policy: Policy;
  readonly triage: readonly TriageItem[];
  readonly model?: string;
  readonly usage?: Usage;
}

interface Composed {
  readonly status: VerdictStatus;
  readonly reason: string;
  readonly modelVerdict?: ModelVerdict;
  readonly severity?: Severity;
}

const EXIT: Record<VerdictStatus, 0 | 1 | 2> = {
  fulfilled: 0,
  partially_fulfilled: 1,
  not_fulfilled: 1,
  needs_review: 2,
};

function numbers(clauses: readonly ClauseResult[], predicate: (clause: ClauseResult) => boolean): number[] {
  return clauses.filter(predicate).map((clause) => clause.clause);
}

function readChoice(answers: Readonly<Record<string, ModelAnswer>>, id: string): ChoiceAnswer | undefined {
  const answer = answers[id];
  return answer?.type === "choice" ? answer : undefined;
}

function readSeverity(answers: Readonly<Record<string, ModelAnswer>>): Severity | undefined {
  const answer = answers["severity"];
  if (answer?.type !== "score") return undefined;
  const score: ScoreAnswer = answer;
  const level = Math.min(SEVERITY_LEVELS.length - 1, Math.max(0, Math.round(score.score)));
  return {
    score: score.score,
    level,
    label: score.legend[String(level)] ?? SEVERITY_LEVELS[level] ?? "",
  };
}

/**
 * The verdict is composed here, in code, from the clause results and the
 * answers. A deterministic check is authoritative: its failure ends the
 * scenario. Everything the model could not settle above a gate, and any answer
 * whose probability stays under the gate, becomes a review instead of a claim.
 */
function decide(input: ComposeInput): Composed {
  const { clauses, policy, answers } = input;
  const choice = readChoice(answers, "verdict");
  const probability = choice === undefined ? undefined : (choice.probabilities[choice.choice] ?? 0);
  const modelVerdict =
    choice === undefined
      ? undefined
      : { choice: choice.choice, probability: probability ?? 0, confidence: choice.confidence };
  const severity = readSeverity(answers);
  const base = { ...(modelVerdict === undefined ? {} : { modelVerdict }), ...(severity === undefined ? {} : { severity }) };

  const failed = numbers(clauses, (clause) => clause.status === "unmet" && clause.source === "deterministic");
  if (failed.length > 0) {
    return { ...base, status: "not_fulfilled", reason: `deterministic check failed for clause ${failed.join(", ")}` };
  }

  const allDeterministicMet = clauses.length > 0 && clauses.every((c) => c.status === "met" && c.source === "deterministic");
  if (allDeterministicMet) {
    return { ...base, status: "fulfilled", reason: "every Then clause confirmed by deterministic checks" };
  }

  const modelFailed = choice !== undefined && (choice.choice === "not_fulfilled" || choice.choice === "partially_fulfilled");
  const unsettled = [
    ...numbers(clauses, (clause) => clause.status === "unjudged"),
    ...numbers(clauses, (clause) => clause.status === "unmet" && clause.source === "jev"),
  ];
  if (probability === undefined) {
    // No verdict answer at all: an offline run or a failed call. Name the
    // clauses that carry no evidence, because that is the actionable part.
    return unsettled.length > 0
      ? { ...base, status: "needs_review", reason: `no settled evidence for clause ${unsettled.join(", ")}` }
      : { ...base, status: "needs_review", reason: "no model verdict answer for this run" };
  }
  if (probability < policy.verdictGate) {
    return {
      ...base,
      status: "needs_review",
      reason: `verdict probability ${probability.toFixed(2)} is below the verdict gate ${policy.verdictGate.toFixed(2)}`,
    };
  }

  if (choice !== undefined && policy.minConfidence !== undefined && choice.confidence < policy.minConfidence) {
    return {
      ...base,
      status: "needs_review",
      reason: `verdict confidence ${choice.confidence.toFixed(2)} is below the confidence gate ${policy.minConfidence.toFixed(2)}`,
    };
  }

  if (unsettled.length > 0 && !modelFailed) {
    return { ...base, status: "needs_review", reason: `no settled evidence for clause ${unsettled.join(", ")}` };
  }
  if (unsettled.length > 0) {
    const unjudgedList = numbers(clauses, (c) => c.status === "unjudged");
    const unmetList = numbers(clauses, (c) => c.status === "unmet");
    const reasons: string[] = [];
    if (unmetList.length > 0) reasons.push(`clauses failed: ${unmetList.join(", ")}`);
    if (unjudgedList.length > 0) reasons.push(`no evidence for clause ${unjudgedList.join(", ")}`);
    const status: VerdictStatus = choice?.choice === "partially_fulfilled" ? "partially_fulfilled" : "not_fulfilled";
    return { ...base, status, reason: reasons.join("; ") || `the run contradicts the scenario` };
  }

  switch (choice?.choice) {
    case "fulfilled":
      return { ...base, status: "fulfilled", reason: `every Then clause holds (verdict ${probability.toFixed(2)})` };
    case "not_fulfilled":
      return { ...base, status: "not_fulfilled", reason: `the run contradicts the scenario (verdict ${probability.toFixed(2)})` };
    case "partially_fulfilled":
      return {
        ...base,
        status: "partially_fulfilled",
        reason: `some clauses hold and one or more do not (verdict ${probability.toFixed(2)})`,
      };
    default:
      return { ...base, status: "needs_review", reason: `the run produced no evidence for the scenario (verdict ${probability.toFixed(2)})` };
  }
}

/** Applies the policy to the clause results and the model answers. */
export function composeVerdict(input: ComposeInput): Verdict {
  if (!Number.isFinite(input.policy.clauseGate) || input.policy.clauseGate < 0 || input.policy.clauseGate > 1) {
    throw new Error(`policy.clauseGate must be a number between 0 and 1, received ${input.policy.clauseGate}`);
  }
  if (!Number.isFinite(input.policy.verdictGate) || input.policy.verdictGate < 0 || input.policy.verdictGate > 1) {
    throw new Error(`policy.verdictGate must be a number between 0 and 1, received ${input.policy.verdictGate}`);
  }
  if (input.policy.minConfidence !== undefined) {
    if (!Number.isFinite(input.policy.minConfidence) || input.policy.minConfidence < 0 || input.policy.minConfidence > 1) {
      throw new Error(`policy.minConfidence must be a number between 0 and 1, received ${input.policy.minConfidence}`);
    }
  }
  const composed = decide(input);
  const triage: TriageResult[] = [];
  for (const item of input.triage) {
    const answer = input.answers[triageId(item)];
    if (answer?.type === "noul") triage.push({ id: item.id, noul: answer.noul });
  }
  const unjudged = input.clauses.filter((clause) => clause.status === "unjudged").length;
  return {
    feature: input.scenario.feature,
    scenario: input.scenario.name,
    status: composed.status,
    exitCode: EXIT[composed.status],
    reason: composed.reason,
    policy: input.policy,
    clauses: [...input.clauses],
    unjudged,
    ...(composed.modelVerdict === undefined ? {} : { modelVerdict: composed.modelVerdict }),
    ...(composed.severity === undefined ? {} : { severity: composed.severity }),
    triage,
    ...(input.model === undefined ? {} : { model: input.model }),
    ...(input.usage === undefined ? {} : { usage: input.usage }),
  };
}
