/** Shared types for the e2e core. No imports, so every module can use them. */

export type ClauseKind = "given" | "when" | "then";

/** One Gherkin step. `index` counts Then clauses from 1; other kinds keep 0. */
export interface Clause {
  readonly index: number;
  readonly kind: ClauseKind;
  readonly text: string;
}

export interface Scenario {
  readonly feature: string;
  readonly featureTags: readonly string[];
  readonly name: string;
  readonly rule?: string;
  readonly ruleTags: readonly string[];
  readonly tags: readonly string[];
  readonly background: readonly Clause[];
  readonly featureBackground: readonly Clause[];
  readonly ruleBackground: readonly Clause[];
  readonly clauses: readonly Clause[];
}

export interface RuleGroup {
  readonly name: string;
  readonly tags: readonly string[];
  readonly background: readonly Clause[];
  readonly scenarios: readonly Scenario[];
}

export interface FeatureSection {
  readonly name: string;
  readonly tags: readonly string[];
  readonly description: string;
  readonly background: readonly Clause[];
  readonly rules: readonly RuleGroup[];
  readonly scenarios: readonly Scenario[];
}

export interface FeatureFile {
  /** First Feature name, retained for single-Feature callers. */
  readonly feature: string;
  readonly description: string;
  readonly features: readonly FeatureSection[];
  readonly scenarios: readonly Scenario[];
}

export type CheckOp = "equals" | "notEquals" | "contains" | "matches" | "exists";

/** A check the caller decides in code, bound to one Then clause number. */
export interface DeterministicCheck {
  readonly clause: number;
  readonly op: CheckOp;
  readonly path: string;
  readonly value?: string | number | boolean;
  /** Optional adapter-owned step and source/test location for a counterexample. */
  readonly step?: string;
  readonly location?: string;
}

export interface CheckObservation {
  readonly path: string;
  readonly op: CheckOp;
  readonly expected: string;
  readonly observed: string;
  readonly failureKind?: "mismatch" | "missing_observation" | "invalid_check";
  readonly step?: string;
  readonly location?: string;
}

/** Run evidence as a runner would leave it. */
export interface RunEvidence {
  readonly suite?: string;
  readonly steps?: readonly unknown[];
  readonly observations: Readonly<Record<string, unknown>>;
}

/** One candidate cause, asked as its own question. */
export interface TriageItem {
  readonly id: string;
  readonly description: string;
}

export interface Evidence {
  readonly run: RunEvidence;
  readonly checks?: readonly DeterministicCheck[];
  readonly triage?: readonly TriageItem[];
}

export type ClauseStatus = "met" | "unmet" | "unjudged";
export type ClauseSource = "deterministic" | "jev" | "none";

export interface ClauseResult {
  readonly clause: number;
  readonly kind: ClauseKind;
  readonly text: string;
  readonly status: ClauseStatus;
  readonly source: ClauseSource;
  /** Noul value for a Jev clause. Absent for a deterministic or unjudged clause. */
  readonly score?: number;
  readonly detail?: string;
  readonly checks?: readonly CheckObservation[];
}

export type VerdictStatus = "fulfilled" | "partially_fulfilled" | "not_fulfilled" | "needs_review";

export interface Policy {
  /** Minimum Noul value for a Jev clause to count as met. */
  readonly clauseGate: number;
  /** Minimum model probability for the verdict choice to stand. */
  readonly verdictGate: number;
  /** Optional minimum model confidence for the verdict choice to stand. */
  readonly minConfidence?: number;
}

export interface ModelVerdict {
  readonly choice: string;
  readonly probability: number;
  readonly confidence: number;
}

export interface Severity {
  readonly score: number;
  readonly level: number;
  readonly label: string;
}

export interface TriageResult {
  readonly id: string;
  readonly noul: number;
}

export interface Usage {
  readonly inputTokens?: number;
  readonly outputTokens?: number;
}

export interface Verdict {
  readonly feature: string;
  readonly scenario: string;
  readonly status: VerdictStatus;
  /** 0 fulfilled, 1 unfulfilled, 2 needs review. */
  readonly exitCode: 0 | 1 | 2;
  readonly reason: string;
  readonly policy: Policy;
  readonly clauses: readonly ClauseResult[];
  readonly unjudged: number;
  readonly modelVerdict?: ModelVerdict;
  readonly severity?: Severity;
  readonly triage: readonly TriageResult[];
  readonly model?: string;
  readonly usage?: Usage;
}
