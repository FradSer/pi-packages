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
  readonly onProgress?: (phase: string) => void;
}

export interface VerifyResult {
  /** Bounded fresh adapter output for diagnosing an unmet verification. */
  readonly runnerOutput?: string;
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
  options.signal?.throwIfAborted();
  if (typeof options.evidence?.run?.observations !== "object" || options.evidence.run.observations === null || Array.isArray(options.evidence.run.observations)) {
    throw new Error("Evidence run.observations must be an object");
  }
  const policy: Policy = { ...DEFAULT_POLICY, ...options.policy };
  for (const [name, value] of Object.entries(policy)) {
    if (value !== undefined && (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1)) throw new Error(`policy.${name} must be a number between 0 and 1`);
  }
  const clauses = thenClauses(options.scenario);
  if (clauses.length === 0) throw new Error("Scenario needs a Then clause");
  options.onProgress?.("Checking deterministic clauses");
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
    options.onProgress?.("Evaluating semantic clauses with Jev");
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
      options.signal?.throwIfAborted();
      modelError = error instanceof TypeSafeError ? `${error.code}: ${error.message}` : `PROVIDER_FAILED: ${(error as Error).message}`;
    }
  }

  options.signal?.throwIfAborted();
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
