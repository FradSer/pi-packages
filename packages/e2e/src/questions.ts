import { setupClauses, thenClauses } from "./gherkin.ts";
import type { Evidence, Scenario, TriageItem } from "./types.ts";

export interface Question {
  readonly type: "noul" | "choice" | "score";
  readonly instructions: unknown;
  readonly criteria?: unknown;
}

export interface SystemOneRequest {
  readonly state: Record<string, unknown>;
  readonly questions: Record<string, Question>;
}

/** The question id for one Then clause. */
export const clauseId = (index: number): string => `clause_${index}`;

/** The question id for one triage cause. */
export const triageId = (item: TriageItem): string => `triage_${item.id}`;

/** Verdict options. Code maps them onto the exit status; the model picks one. */
export const VERDICT_CRITERIA = {
  fulfilled: "Every Then clause has direct supporting evidence and nothing in the run contradicts it.",
  partially_fulfilled: "Some Then clauses are supported and at least one is contradicted.",
  not_fulfilled: "The main outcome of the When steps is contradicted by the evidence.",
  unverified: "The run produced no evidence for one or more Then clauses.",
} as const;

/** Business harm levels for the severity score. */
export const SEVERITY_LEVELS = [
  "No business harm. The run matches the scenario.",
  "Billing or access is wrong, but the customer is neither charged nor blocked.",
  "The customer is overcharged, loses paid access, or a paid seat is removed.",
] as const;

/** The state both the model and the report read: scenario text plus run evidence. */
export function buildState(scenario: Scenario, evidence: Evidence): Record<string, unknown> {
  return {
    scenario: {
      feature: scenario.feature,
      name: scenario.name,
      given: setupClauses(scenario).map((clause) => clause.text),
      then: thenClauses(scenario).map((clause) => ({ clause: clause.index, text: clause.text })),
    },
    run: evidence.run,
  };
}

/**
 * Builds the one request the model sees. Only clauses without a deterministic
 * check become Nouls, so the model never re-judges what code already decided.
 * The verdict choice and the severity score ride in the same request, and each
 * triage cause becomes its own question: one narrow question per judgment.
 */
export function buildRequest(
  scenario: Scenario,
  evidence: Evidence,
  pendingClauses: readonly number[],
): SystemOneRequest {
  const thenByIndex = new Map(thenClauses(scenario).map((clause) => [clause.index, clause.text]));
  const questions: Record<string, Question> = {};
  for (const index of pendingClauses) {
    const text = thenByIndex.get(index);
    if (text === undefined) continue;
    questions[clauseId(index)] = {
      type: "noul",
      instructions: {
        clause: `\`scenario.then[${index - 1}].text\``,
        evidence: "The run evidence under `run` is the only source. Step results and the observed API, database, and page values must agree before the clause counts as met.",
        question: `Is the clause "${text}" met by this run?`,
      },
      criteria: {
        true: "The evidence directly shows the condition in the clause holds after the When steps.",
        false: "The evidence directly shows the condition does not hold, or shows a contradicting value.",
      },
    };
  }
  questions.verdict = {
    type: "choice",
    instructions: {
      task: "Decide the business outcome of `scenario.name` for this run, using `run` as the only evidence.",
      question: "Did this run fulfill every Then clause of the scenario?",
    },
    criteria: { ...VERDICT_CRITERIA },
  };
  questions.severity = {
    type: "score",
    instructions: "How much business harm does the gap between `scenario.name` and this run cause the customer?",
    criteria: [...SEVERITY_LEVELS],
  };
  for (const item of evidence.triage ?? []) {
    questions[triageId(item)] = {
      type: "noul",
      instructions: {
        cause: item.description,
        evidence: "The run evidence under `run` is the only source.",
        question: `Does the run show this cause for the unmet clauses: ${item.description}?`,
      },
      criteria: {
        true: "The run evidence shows this cause.",
        false: "The run evidence does not show this cause.",
      },
    };
  }
  return { state: buildState(scenario, evidence), questions };
}
