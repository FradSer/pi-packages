/**
 * Declarative harness rule shapes and resolved configuration.
 * Domain layer: zero external imports — pure interfaces and value objects only.
 */

export interface SkillRule {
  id: string;
  enabled?: boolean;
  skill: string;
  instructions: string;
  source?: string;
}

export interface BashRule {
  id: string;
  enabled?: boolean;
  bash: string;
  action?: "confirm" | "block";
  message: string;
  source?: string;
  regexp?: RegExp;
}

export interface TextRule {
  id: string;
  enabled?: boolean;
  text: string;
  instructions: string;
  source?: string;
  regexp?: RegExp;
}

export interface DisabledRule {
  id: string;
  enabled: false;
  skill?: string;
  bash?: string;
  text?: string;
  instructions?: string;
  message?: string;
  action?: "confirm" | "block";
  source?: string;
}

export type Rule = SkillRule | BashRule | TextRule | DisabledRule;

/** A declaration that won an id but failed validation. Its selector scope
 * decides whether Bash evaluation is incomplete: a bash-scoped or ambiguous
 * (no single valid selector) invalid rule blocks Bash; a clearly skill- or
 * text-scoped one does not. */
export interface InvalidRuleInfo {
  id: string;
  source: string;
  errors: string[];
  hasBash: boolean;
  hasSkill: boolean;
  hasText: boolean;
  /** No single valid selector could be determined (e.g. duplicate id, missing
   * selector, or multiple selectors). Treated conservatively as bash-affecting. */
  ambiguous: boolean;
}

export interface RuleLayer {
  /** Human-readable origin, e.g. "~/.pi/agent/harness.json". */
  source: string;
  rules?: Array<Record<string, unknown>>;
  /** Obsolete format containers retained for diagnostic detection */
  policies?: Array<Record<string, unknown>>;
  skillPrompts?: Record<string, unknown>;
  disabled?: string[];
  errors?: string[];
  /** True when this layer's bytes could not be read/parsed and a stale
   * snapshot (or nothing) is standing in. Consumers must not treat a rule that
   * vanished under a stale layer as a deliberate removal. */
  stale?: boolean;
}

export type PolicyLayer = RuleLayer;

export interface BashEvaluationResult {
  decision: "execute" | "confirm" | "block" | "incomplete";
  messages: string[];
  matchedRules: BashRule[];
  reason?: string;
  /** Rule ids whose invalid declarations made Bash evaluation incomplete. */
  incompleteRuleIds?: string[];
}

export interface ResolvedHarnessConfig {
  rules: Rule[];
  errors: string[];
  /** Structured invalid-declaration records, keyed by winning id. */
  invalidRules: InvalidRuleInfo[];
  /** False when any invalid winning rule is bash-scoped or ambiguous, meaning
   * Bash coverage is incomplete and Bash calls must not be silently executed. */
  bashEvaluationComplete: boolean;
  /** True when any layer fell back to a stale snapshot or failed to read, so a
   * missing rule is indeterminate rather than a confirmed removal. */
  configReadIncomplete: boolean;
  /** Legacy views for transitional callers and existing user files. */
  policies: Array<Policy & { regexps: RegExp[] }>;
  skillPrompts: Record<string, SkillPrompt>;
}

export type ResolvedConfig = ResolvedHarnessConfig;

export type PolicyPhase = "tool-call" | "output" | "artifact";

export interface Policy {
  name: string;
  phase?: PolicyPhase;
  tools?: string[];
  paths?: string[];
  artifactPaths?: string[];
  pattern?: string;
  patterns?: string[];
  require?: { path?: string; pattern: string };
  action?: "block" | "confirm" | "observe";
  reason: string;
  source?: string;
}

export interface SkillPrompt {
  prompt: string;
  target: "system" | "user";
  userMessagePattern?: string;
  source?: string;
}
