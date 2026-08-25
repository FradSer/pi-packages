/** Declarative guardrail policy shapes shared by config loading and the
 * evaluation engine. */

export interface Policy {
  /** Unique name; innermost layer wins on conflicts, disable lists target it. */
  name: string;
  /** Restrict to these tool names; undefined matches every tool. */
  tools?: string[];
  /** Dot path into the tool arguments tested against the pattern(s).
   * Defaults to the whole stringified argument object. */
  path?: string;
  /** Single regex source. */
  pattern?: string;
  /** Multiple regex sources; any match triggers the action. */
  patterns?: string[];
  /** AND-gate: must also match somewhere in the args before pattern(s) are
   * considered. Scopes a policy to a class of calls (e.g. only UI files). */
  require?: { path?: string; pattern: string };
  /** block (default) refuses the call with the reason; confirm asks the user. */
  action?: "block" | "confirm";
  /** The corrective guidance fed back to the model when the call is blocked. */
  reason: string;
  /** Layer that supplied this policy; set during merge, not authored. */
  source?: string;
}

export interface PolicyLayer {
  /** Human-readable origin, e.g. "~/.pi/agent/guardrails.json". */
  source: string;
  policies?: Array<Record<string, unknown>>;
  disabled?: string[];
  /** Non-fatal load problems (bad JSON shape) reported once. */
  errors?: string[];
}

export interface ResolvedConfig {
  policies: Array<Policy & { regexps: RegExp[] }>;
  errors: string[];
}
