/** Read-only compatibility boundary for already-installed Harness declarations.
 * New planners/writers author flat rules; no conversion or filesystem mutation
 * belongs here. Match semantics retain phase, argument leaves and requirements. */
import type { RuleLayer } from "./guardrail-types.ts";

export const LEGACY_FIELDS = ["policies", "disabled", "skillPrompts", "learnedPolicies"] as const;
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
export interface LegacyContainers {
  policies?: unknown[];
  disabled?: string[];
  skillPrompts?: Record<string, unknown>;
  learnedPolicies?: Record<string, unknown>;
}
export interface InvalidLegacyPolicy {
  name: string;
  source: string;
  errors: string[];
  /** Each scope retains its phase/tool relationship. Undefined means unknown,
   * not empty. Duplicates union scopes rather than choosing the last or taking
   * a cross-product that incorrectly globalizes unrelated postgeneration rules. */
  scopes: Array<{ tools?: string[]; phase?: PolicyPhase }>;
}
export interface LegacyConfig {
  policies: Array<Policy & { regexps: RegExp[] }>;
  skillPrompts: Record<string, SkillPrompt>;
  invalidPolicies: InvalidLegacyPolicy[];
  disabled: string[];
  unavailable: boolean;
}
function compile(pattern: string): RegExp | undefined {
  try { return new RegExp(pattern); } catch { return undefined; }
}
function stringArray(value: unknown): string[] | undefined {
  return Array.isArray(value) && value.every(entry => typeof entry === "string") ? value : undefined;
}
export function legacyContainerErrors(root: Record<string, unknown>): string[] {
  const errors: string[] = [];
  if (root.policies !== undefined && !Array.isArray(root.policies)) errors.push("policies must be an array");
  if (root.disabled !== undefined && !stringArray(root.disabled)) errors.push("disabled must be an array of strings");
  for (const field of ["skillPrompts", "learnedPolicies"]) {
    if (Object.hasOwn(root, field) && (!root[field] || typeof root[field] !== "object" || Array.isArray(root[field]))) errors.push(`${field} must be an object`);
  }
  return errors;
}

const POLICY_FIELDS = ["name", "phase", "tools", "paths", "artifactPaths", "pattern", "patterns", "require", "action", "reason"] as const;
const POLICY_FIELD_LIST = "name, phase, tools, paths, pattern, patterns, artifactPaths, require, action, and reason";
const SKILL_PROMPT_FIELDS = ["prompt", "target", "userMessagePattern"] as const;
const POLICY_PHASES = ["tool-call", "output", "artifact"] as const satisfies readonly PolicyPhase[];

function validateSkillPromptDeclaration(
  name: unknown,
  raw: unknown,
  availableSkills?: ReadonlySet<string>,
): string[] {
  const errors: string[] = [];
  if (typeof name !== "string" || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name) || name.length > 64) {
    errors.push("skill prompt name must be an exact valid skill key");
  } else if (availableSkills && !availableSkills.has(name)) {
    errors.push(`skill prompt \"${name}\" is not an available registered skill`);
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    errors.push("skill prompt must be an object");
    return errors;
  }
  const entry = raw as Record<string, unknown>;
  const unsupported = Object.keys(entry).filter((key) => !(SKILL_PROMPT_FIELDS as readonly string[]).includes(key));
  if (unsupported.length) errors.push(`skill prompt has unsupported field(s): ${unsupported.join(", ")}; supported fields are prompt, target, and userMessagePattern`);
  if (typeof entry.prompt !== "string" || !entry.prompt.trim()) errors.push("skill prompt needs a non-empty prompt string");
  if (entry.target !== "system" && entry.target !== "user") errors.push("skill prompt target must be system or user");
  if (entry.userMessagePattern !== undefined) {
    if (typeof entry.userMessagePattern !== "string" || !entry.userMessagePattern.trim()) {
      errors.push("skill prompt userMessagePattern must be a non-empty regular expression string");
    } else if (!compile(entry.userMessagePattern)) {
      errors.push("skill prompt userMessagePattern is an invalid regex");
    }
  }
  return errors;
}

function validatePolicyDeclaration(raw: unknown): string[] {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return ["must be an object"];
  const declaration = raw as Record<string, unknown>;
  const errors: string[] = [];
  const unsupported = Object.keys(declaration).filter((key) => !(POLICY_FIELDS as readonly string[]).includes(key));
  if (unsupported.length) {
    errors.push(`unsupported field(s): ${unsupported.join(", ")}; supported declaration fields are ${POLICY_FIELD_LIST}`);
  }
  if (typeof declaration.name !== "string" || !declaration.name.trim()) {
    errors.push("name must be a non-empty string");
  }
  if (declaration.phase !== undefined && !POLICY_PHASES.includes(declaration.phase as PolicyPhase)) {
    errors.push('phase must be "tool-call", "output", or "artifact"');
  }
  const phase = POLICY_PHASES.includes(declaration.phase as PolicyPhase) ? (declaration.phase as PolicyPhase) : "tool-call";
  for (const field of ["tools", "paths", "artifactPaths"] as const) {
    if (declaration[field] !== undefined && !stringArray(declaration[field])) {
      errors.push(`${field} must be an array of strings`);
    }
  }
  if (phase !== "tool-call" && declaration.paths !== undefined) errors.push("paths is only supported in the tool-call phase");
  if (phase === "output" && declaration.tools !== undefined) errors.push("tools is only supported in the tool-call or artifact phase");
  if (phase !== "artifact" && declaration.artifactPaths !== undefined) errors.push("artifactPaths is only supported in the artifact phase");

  const hasPattern = declaration.pattern !== undefined;
  const hasPatterns = declaration.patterns !== undefined;
  if (hasPattern && hasPatterns) errors.push("use pattern or patterns, not both");
  if (!hasPattern && !hasPatterns) {
    errors.push("requires a non-empty pattern or patterns declaration");
  } else if (hasPattern) {
    if (typeof declaration.pattern !== "string" || !declaration.pattern.trim()) errors.push("pattern must be a non-empty regular expression string");
  } else {
    const patternList = stringArray(declaration.patterns);
    if (!patternList || patternList.length === 0) errors.push("patterns must be a non-empty array of regular expression strings");
    else if (patternList.some((pattern) => !pattern.trim())) errors.push("patterns must not contain empty regular expressions");
  }

  if (declaration.require !== undefined) {
    const requirement = declaration.require;
    if (!requirement || typeof requirement !== "object" || Array.isArray(requirement)) {
      errors.push("require must be an object");
    } else {
      const gate = requirement as Record<string, unknown>;
      const unsupportedGate = Object.keys(gate).filter((key) => key !== "path" && key !== "pattern");
      if (unsupportedGate.length) errors.push(`require has unsupported field(s): ${unsupportedGate.join(", ")}`);
      if (gate.path !== undefined && typeof gate.path !== "string") errors.push("require.path must be a string");
      if (phase !== "tool-call" && gate.path !== undefined) errors.push("require.path is only supported in the tool-call phase");
      if (typeof gate.pattern !== "string" || !gate.pattern.trim()) errors.push("require.pattern must be a non-empty regular expression string");
    }
  }
  if (declaration.action !== undefined && declaration.action !== "block" && declaration.action !== "confirm" && declaration.action !== "observe") {
    errors.push('action must be "block", "confirm", or "observe"');
  }
  if (phase !== "tool-call" && declaration.action === "confirm") {
    errors.push("confirm action is unavailable after generation; use block for bounded repair or observe");
  }
  if (declaration.reason !== undefined && (typeof declaration.reason !== "string" || !declaration.reason.trim())) {
    errors.push("reason must be a non-empty string when provided");
  }

  const regexSources = [
    ...(typeof declaration.pattern === "string" ? [declaration.pattern] : []),
    ...(stringArray(declaration.patterns) ?? []),
    ...(declaration.require && typeof declaration.require === "object" && !Array.isArray(declaration.require)
      ? [(declaration.require as Record<string, unknown>).pattern]
      : []),
  ];
  for (const source of regexSources) {
    if (typeof source === "string" && source.trim() && !compile(source)) {
      errors.push(`invalid regex ${JSON.stringify(source)}`);
    }
  }
  return errors;
}

function normalizePolicy(
  raw: Record<string, unknown>,
  source: string,
  tools: string[] | undefined,
  paths: string[] | undefined,
  artifactPaths: string[] | undefined,
  patterns: string[] | undefined,
): Policy {
  const requirement = raw.require as Record<string, unknown> | undefined;
  return {
    name: String(raw.name),
    phase: POLICY_PHASES.includes(raw.phase as PolicyPhase) ? (raw.phase as PolicyPhase) : "tool-call",
    tools,
    paths,
    artifactPaths,
    pattern: typeof raw.pattern === "string" ? raw.pattern : undefined,
    patterns,
    require:
      requirement && typeof requirement.pattern === "string"
        ? { path: typeof requirement.path === "string" ? requirement.path : undefined, pattern: requirement.pattern }
        : undefined,
    action: raw.action === "confirm" || raw.action === "observe" ? raw.action : "block",
    reason: typeof raw.reason === "string" && raw.reason.trim() ? raw.reason : "Blocked by guardrails policy.",
    source,
  };
}

/** Winning invalid declarations shadow outer definitions. Their trustworthy
 * tool scope is retained even when a regex, action, identity or payload fails. */
export function resolveLegacy(layers: readonly RuleLayer[], availableSkills?: ReadonlySet<string>): { legacy: LegacyConfig; errors: string[]; notices: string[] } {
  const policies = new Map<string, { policy?: Policy & { regexps: RegExp[] }; invalid?: InvalidLegacyPolicy }>();
  const prompts = new Map<string, SkillPrompt>();
  const disabled = new Set<string>();
  const errors: string[] = [];
  const notices: string[] = [];
  for (const layer of layers) {
    if (LEGACY_FIELDS.some(field => Object.hasOwn(layer, field))) notices.push(`${layer.source}: compatible legacy harness configuration is active read-only; new authoring uses flat rules; existing bytes are unchanged`);
    for (const name of layer.disabled ?? []) disabled.add(name);
    const seen = new Set<string>();
    for (const [index, raw] of (layer.policies ?? []).entries()) {
      const d = raw && typeof raw === "object" && !Array.isArray(raw) ? raw as Record<string, unknown> : {};
      const name = typeof d.name === "string" && d.name.trim() ? d.name : `(missing-name@${layer.source}:${index})`;
      const invalid = validatePolicyDeclaration(raw);
      if (seen.has(name)) invalid.push(`duplicate legacy policy name "${name}" in same layer`);
      seen.add(name);
      if (invalid.length) {
        const prior = policies.get(name);
        const tools = stringArray(d.tools);
        policies.set(name, { invalid: {
          name, source: layer.source, errors: invalid,
          scopes: [
            ...(invalid.some(error => error.startsWith("duplicate"))
              ? prior?.invalid?.scopes ?? (prior?.policy ? [{ tools: prior.policy.tools, phase: prior.policy.phase }] : []) : []),
            { tools, phase: d.phase === undefined ? "tool-call" : POLICY_PHASES.includes(d.phase as PolicyPhase) ? d.phase as PolicyPhase : undefined },
          ],
        } });
      } else {
        const policy = normalizePolicy(d, layer.source, stringArray(d.tools), stringArray(d.paths), stringArray(d.artifactPaths), stringArray(d.patterns));
        policies.set(name, { policy: { ...policy, regexps: (policy.patterns ?? [policy.pattern!]).map(pattern => new RegExp(pattern)) } });
      }
    }
    for (const [name, raw] of Object.entries(layer.skillPrompts ?? {})) {
      prompts.delete(name);
      const invalid = validateSkillPromptDeclaration(name, raw, availableSkills);
      if (invalid.length) { errors.push(`${layer.source}: legacy skill prompt "${name}" is invalid: ${invalid.join("; ")}`); continue; }
      prompts.set(name, { ...(raw as SkillPrompt), source: layer.source });
    }
  }
  const active = [...policies].filter(([name]) => !disabled.has(name)).map(([, entry]) => entry);
  const invalidPolicies = active.flatMap(entry => entry.invalid ? [entry.invalid] : []);
  errors.push(...invalidPolicies.map(entry => `${entry.source}: legacy policy "${entry.name}" is invalid: ${entry.errors.join("; ")}`));
  return { legacy: {
    policies: active.flatMap(entry => entry.policy ? [entry.policy] : []),
    invalidPolicies, skillPrompts: Object.fromEntries(prompts), disabled: [...disabled],
    unavailable: layers.some(layer => layer.unavailable),
  }, errors, notices };
}

function collectLeaves(value: unknown, segments: string[]): string[] {
  if (!segments.length) {
    if (typeof value === "string") return [value];
    return value == null ? [] : [JSON.stringify(value)];
  }
  if (Array.isArray(value)) return value.flatMap(item => collectLeaves(item, segments));
  if (value && typeof value === "object") return collectLeaves((value as Record<string, unknown>)[segments[0]], segments.slice(1));
  return [];
}
function valueAtPath(args: Record<string, unknown>, field?: string, toolName?: string): string[] {
  if (!field) return [JSON.stringify(args)];
  const leaves = collectLeaves(args, field.split("."));
  // Pi's edit API now batches edits. A stored newText selector must keep
  // protecting inserted replacements, without ever scanning deleted oldText.
  if (toolName === "edit" && (field === "newText" || field === "oldText")) leaves.push(...collectLeaves(args, ["edits", field]));
  return leaves;
}
export interface LegacyDecision {
  policyName: string;
  action: "block" | "confirm" | "observe";
  reason: string;
  cleanReason: string;
  source?: string;
}
function decision(policy: Policy): LegacyDecision {
  return { policyName: policy.name, action: policy.action ?? "block", reason: `[guardrails:${policy.name}] ${policy.reason}`, cleanReason: policy.reason, source: policy.source };
}
export function invalidLegacyAffects(policy: InvalidLegacyPolicy, phase: PolicyPhase, toolName?: string): boolean {
  return policy.scopes.some(scope => (!scope.phase || scope.phase === phase) && (!toolName || !scope.tools || scope.tools.includes(toolName)));
}
export function evaluateLegacyTools(legacy: LegacyConfig, toolName: string, args: Record<string, unknown>): { matches: LegacyDecision[]; incomplete: string[] } {
  const incomplete = legacy.invalidPolicies.filter(policy => invalidLegacyAffects(policy, "tool-call", toolName)).map(policy => policy.name);
  if (legacy.unavailable) incomplete.push("unreadable configuration");
  const matches = legacy.policies.filter(policy => {
    if (policy.phase !== "tool-call" || policy.tools && !policy.tools.includes(toolName)) return false;
    if (policy.require && !valueAtPath(args, policy.require.path, toolName).some(subject => new RegExp(policy.require!.pattern).test(subject))) return false;
    const subjects = policy.paths ? policy.paths.flatMap(field => valueAtPath(args, field, toolName)) : valueAtPath(args);
    return policy.regexps.some(regexp => subjects.some(subject => regexp.test(subject)));
  }).map(decision);
  return { matches, incomplete };
}
export function evaluateLegacyPhase(legacy: LegacyConfig, input: { phase: "output" | "artifact"; text: string; toolName?: string; policyName?: string; ignoreTools?: boolean }): LegacyDecision | null {
  for (const policy of legacy.policies) {
    if (policy.phase !== input.phase || input.policyName && policy.name !== input.policyName) continue;
    if (!input.ignoreTools && policy.tools && (!input.toolName || !policy.tools.includes(input.toolName))) continue;
    if (policy.require && !new RegExp(policy.require.pattern).test(input.text)) continue;
    if (policy.regexps.some(regexp => regexp.test(input.text))) return decision(policy);
  }
  return null;
}

/** Names reserved by compatibility sources, including disabled/invalid entries.
 * Used only for automatic ownership checks, never to translate declarations. */
export function legacyReservedNames(layer: LegacyContainers): string[] {
  return [...(layer.disabled ?? []), ...Object.keys(layer.skillPrompts ?? {}), ...(layer.policies ?? []).flatMap(raw =>
    raw && typeof raw === "object" && "name" in raw && typeof raw.name === "string" ? [raw.name] : []), ...Object.keys(layer.learnedPolicies ?? {})];
}
