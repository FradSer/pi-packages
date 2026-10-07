import { evaluateChecks } from "./checks.ts";
import { composeVerdict } from "./compose.ts";
import { thenClauses } from "./gherkin.ts";
import { buildRequest, clauseId } from "./questions.ts";
import { type ClientOptions, type ModelAnswer, systemOne, TypeSafeError } from "./typesafe.ts";
import type { ClauseResult, Evidence, Policy, Scenario, Verdict } from "./types.ts";

export const DEFAULT_POLICY: Policy = { clauseGate: 0.8, verdictGate: 0.6 };

export interface VerifyOptions {
  readonly scenario: Scenario;
  readonly evidence: Evidence;
  readonly policy?: Partial<Policy>;
  /** Skip the model call. Clauses without a check stay unjudged. */
  readonly offline?: boolean;
  readonly client?: ClientOptions;
  readonly signal?: AbortSignal;
}

export interface VerifyResult {
  readonly verdict: Verdict;
  /** Question ids the model was asked about. Empty in offline mode. */
  readonly asked: readonly string[];
  /** Set when the call was attempted and failed. The verdict stays offline. */
  readonly modelError?: string;
}

function unjudged(clause: { readonly index: number; readonly text: string }): ClauseResult {
  return {
    clause: clause.index,
    kind: "then",
    text: clause.text,
    status: "unjudged",
    source: "none",
    detail: "no check and no model answer cover this clause",
  };
}

/**
 * Runs the three layers in order: code decides every declared check, the model
 * answers only the remaining clauses, and the verdict is composed in code. A
 * model failure never turns a missing answer into a pass: the clauses stay
 * unjudged and the verdict becomes needs_review.
 */
export async function verifyScenario(options: VerifyOptions): Promise<VerifyResult> {
  const policy: Policy = { ...DEFAULT_POLICY, ...options.policy };
  const clauses = thenClauses(options.scenario);
  const deterministic = evaluateChecks(clauses, options.evidence);
  const pending = clauses.filter((clause) => !deterministic.has(clause.index)).map((clause) => clause.index);
  const results = new Map<number, ClauseResult>(deterministic);
  for (const clause of clauses) {
    if (!results.has(clause.index)) results.set(clause.index, unjudged(clause));
  }

  let answers: Record<string, ModelAnswer> = {};
  let model: string | undefined;
  let usage: Verdict["usage"];
  let modelError: string | undefined;
  const asked: string[] = [];

  if (pending.length > 0 && options.offline !== true) {
    const request = buildRequest(options.scenario, options.evidence, pending);
    asked.push(...Object.keys(request.questions));
    try {
      const response = await systemOne(
        { ...options.client, ...(options.signal === undefined ? {} : { signal: options.signal }) },
        request,
      );
      answers = { ...response.answers };
      model = response.model;
      usage = {
        ...(response.inputTokens === undefined ? {} : { inputTokens: response.inputTokens }),
        ...(response.outputTokens === undefined ? {} : { outputTokens: response.outputTokens }),
      };
      for (const clause of clauses) {
        if (deterministic.has(clause.index)) continue;
        const answer = answers[clauseId(clause.index)];
        if (answer?.type !== "noul") continue;
        const met = answer.noul >= policy.clauseGate;
        results.set(clause.index, {
          clause: clause.index,
          kind: "then",
          text: clause.text,
          status: met ? "met" : "unmet",
          source: "jev",
          score: answer.noul,
          ...(met ? {} : { detail: `noul ${answer.noul.toFixed(2)} is below the clause gate ${policy.clauseGate.toFixed(2)}` }),
        });
      }
    } catch (error) {
      modelError = error instanceof TypeSafeError ? `${error.code}: ${error.message}` : `PROVIDER_FAILED: ${(error as Error).message}`;
    }
  }

  const verdict = composeVerdict({
    scenario: options.scenario,
    clauses: clauses.map((clause) => results.get(clause.index) ?? unjudged(clause)),
    answers,
    policy,
    triage: options.evidence.triage ?? [],
    ...(model === undefined ? {} : { model }),
    ...(usage === undefined ? {} : { usage }),
  });
  return { verdict, asked, ...(modelError === undefined ? {} : { modelError }) };
}
