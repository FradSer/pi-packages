/** Declarative guardrail policy shapes shared by config loading and the
 * evaluation engine. */

/** Point in the agent lifecycle where a policy is evaluated. Existing rules
 * default to tool-call so older configuration remains a pre-execution gate. */
export type PolicyPhase = "tool-call" | "output" | "artifact";

export interface Policy {
  /** Unique name; innermost layer wins on conflicts, disable lists target it. */
  name: string;
  /** Evaluation phase. Omitted declarations normalize to tool-call. */
  phase?: PolicyPhase;
  /** Restrict to these tool names; undefined matches every tool. */
  tools?: string[];
  /** Dot paths into the tool arguments whose string values are tested
   * against the pattern(s). Segments traverse arrays ("edits.newText" scans
   * every edit). Prefer explicit content paths — the default scans the whole
   * argument JSON, which also matches replaced source quoted in edit inputs. */
  paths?: string[];
  /** Workspace-relative files to inspect after any matching tool result.
   * This is required when an artifact is produced by a command tool such as
   * bash, whose result does not carry a canonical file path. */
  artifactPaths?: string[];
  /** Single regex source. */
  pattern?: string;
  /** Multiple regex sources; any match triggers the action. */
  patterns?: string[];
  /** AND-gate: must also match somewhere in the args before pattern(s) are
   * considered. Scopes a policy to a class of calls (e.g. only UI files). */
  require?: { path?: string; pattern: string };
  /** block (default) refuses the call; confirm asks the user; observe reports and proceeds. */
  action?: "block" | "confirm" | "observe";
  /** The corrective guidance fed back to the model when the call is blocked. */
  reason: string;
  /** Layer that supplied this policy; set during merge, not authored. */
  source?: string;
}

export interface SkillPrompt {
  /** Literal guidance to add when the named skill is expanded by Pi. */
  prompt: string;
  /** Where Pi should receive the guidance. */
  target: "system" | "user";
  /** Optional regex that must match the expanded skill's user message. */
  userMessagePattern?: string;
  /** Configuration layer that supplied this prompt; assigned during merge. */
  source?: string;
}

export interface PolicyLayer {
  /** Human-readable origin, e.g. "~/.pi/agent/harness.json". */
  source: string;
  policies?: Array<Record<string, unknown>>;
  /** Per-skill guidance, resolved by skill name with innermost precedence. */
  skillPrompts?: Record<string, unknown>;
  disabled?: string[];
  /** Non-fatal load problems (bad JSON shape) reported once. */
  errors?: string[];
}

export interface ResolvedConfig {
  policies: Array<Policy & { regexps: RegExp[] }>;
  skillPrompts: Record<string, SkillPrompt>;
  errors: string[];
}
