/** Flat harness declarations and evaluator results. No runtime dependencies. */
import type { LegacyConfig, LegacyContainers } from "./legacy-harness.ts";
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

export interface InvalidRuleInfo {
  id: string;
  source: string;
  errors: string[];
  hasBash: boolean;
  hasSkill: boolean;
  hasText: boolean;
  /** An unidentified/ambiguous selector conservatively affects Bash coverage. */
  ambiguous: boolean;
}

export interface RuleLayer extends LegacyContainers {
  source: string;
  rules?: Array<Record<string, unknown>>;
  errors?: string[];
  /** The current file could not be interpreted. Any supplied rules belong to
   * the last identity-unambiguous snapshot, not the current file. */
  stale?: boolean;
  /** No trustworthy snapshot is available: Bash must remain unexecuted. */
  unavailable?: boolean;
}

export interface BashEvaluationResult {
  decision: "execute" | "confirm" | "block" | "incomplete";
  messages: string[];
  matchedRules: BashRule[];
  reason?: string;
  incompleteRuleIds?: string[];
}

export interface ResolvedHarnessConfig {
  rules: Rule[];
  errors: string[];
  /** Compatibility information is not a validation failure. */
  notices: string[];
  legacy: LegacyConfig;
  invalidRules: InvalidRuleInfo[];
  bashEvaluationComplete: boolean;
  configReadIncomplete: boolean;
}
