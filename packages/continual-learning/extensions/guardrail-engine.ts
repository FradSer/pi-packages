/** Flat rule validation, identity resolution and pure selector evaluation.
 * No command execution or Pi imports. */
import { createHash } from "node:crypto";
import { LEGACY_FIELDS, legacyContainerErrors, resolveLegacy } from "./legacy-harness.ts";
import type { BashEvaluationResult, BashRule, InvalidRuleInfo, ResolvedHarnessConfig, Rule, RuleLayer, SkillRule, TextRule } from "./guardrail-types.ts";

export const DEFAULT_RULES: Rule[] = [
  {
    id: "no-bulk-memory-deletion",
    bash: "(?:\\brm\\b|\\bgit\\s+rm\\b|\\bunlink\\b|\\brsync\\b[^\\n]*--delete|\\b(?:python|python3|node|bun)\\b[^\\n]*(?:rmtree|rmSync|unlinkSync))[^\\n]*(?:\\.memory|\\.pi[/\\\\]agent[/\\\\]memory)|\\bfind\\b[^\\n]*(?:\\.memory|\\.pi[/\\\\]agent[/\\\\]memory)[^\\n]*-delete",
    action: "block",
    message: "Project memory must not be bulk-deleted through generated shell commands. Use the parent-owned /consolidate flow so preservation, privacy, rollback, and receipts are verified.",
  },
  {
    id: "no-interactive-auth-automation",
    bash: "\\b(npm|pnpm|yarn|bun)\\s+(login|adduser|logout|whoami\\s*--interactive)\\b",
    action: "block",
    message: "Interactive authentication cannot be automated from this session (no TTY, invisible browser). Ask the user to run the login command in their own terminal and confirm when done.",
  },
  {
    id: "no-otp-in-chat",
    bash: "\\b(otp|one[- ]time (password|code))\\b.*[>|>>]|printf[^|]*\\b(otp|verification code)\\b.*>\\s*/tmp",
    action: "block",
    message: "Never route OTP codes through files or chat. Interactive OTP prompts must be answered by the user in their own terminal; ask them to run the command and report the result.",
  },
];

function compile(pattern: string): RegExp | undefined {
  try { return new RegExp(pattern); } catch { return undefined; }
}

const RULE_FIELDS = ["id", "enabled", "skill", "instructions", "bash", "action", "message", "text"] as const;

/** Parent provenance hashes declarations, not layer sources or compiled regexes.
 * Field order and omitted enabled:true do not imply a different rule revision. */
export function ruleRevision(rule: Rule | Record<string, unknown>): string {
  const raw = rule as unknown as Record<string, unknown>;
  return createHash("sha256").update(JSON.stringify(Object.fromEntries(
    RULE_FIELDS.map(field => [field, field === "enabled" ? raw.enabled !== false : raw[field]])
      .filter(([, value]) => value !== undefined),
  ))).digest("hex");
}

/** Structural errors cannot establish unambiguous identities. Per-rule errors
 * with a recognizable id remain entries and shadow their outer definitions. */
export function validateRuleContainer(value: unknown): string[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) return ["harness config must be an object"];
  const root = value as Record<string, unknown>;
  const errors: string[] = [];
  errors.push(...legacyContainerErrors(root));
  const unknown = Object.keys(root).filter(field => field !== "rules" && field !== "learnedRules" && !(LEGACY_FIELDS as readonly string[]).includes(field));
  if (unknown.length) errors.push(`unsupported top-level field(s): ${unknown.join(", ")}`);
  if (Object.hasOwn(root, "rules") && !Array.isArray(root.rules)) errors.push("rules must be an array");
  else if (Array.isArray(root.rules)) {
    const seen = new Set<string>();
    root.rules.forEach((raw, index) => {
      if (!raw || typeof raw !== "object" || Array.isArray(raw) || typeof raw.id !== "string" || !raw.id.trim()) {
        errors.push(`rules[${index}] must be an object with a non-empty id`);
      } else if (seen.has(raw.id)) {
        errors.push(`duplicate rule id "${raw.id}" in same layer`);
      } else seen.add(raw.id);
    });
  }
  if (root.learnedRules !== undefined && (!root.learnedRules || typeof root.learnedRules !== "object" || Array.isArray(root.learnedRules))) {
    errors.push("learnedRules must be an object containing parent-owned provenance");
  }
  return errors;
}

export function validateRuleDeclaration(raw: unknown, availableSkills?: ReadonlySet<string>): string[] {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return ["rule must be an object"];
  const d = raw as Record<string, unknown>;
  const errors: string[] = [];
  const unsupported = Object.keys(d).filter(key => !(RULE_FIELDS as readonly string[]).includes(key));
  if (unsupported.length) errors.push(`unsupported field(s): ${unsupported.join(", ")}; supported fields are ${RULE_FIELDS.join(", ")}`);
  if (typeof d.id !== "string" || !d.id.trim()) errors.push("id must be a non-empty string");
  if (d.enabled !== undefined && typeof d.enabled !== "boolean") errors.push("enabled must be a boolean");
  const selectors = ["skill", "bash", "text"].filter(key => d[key] !== undefined);
  if (d.enabled === false && selectors.length === 0) {
    if (Object.keys(d).some(key => key !== "id" && key !== "enabled")) errors.push("minimal disabled declaration supports only id and enabled");
    return errors;
  }
  if (selectors.length !== 1) errors.push("rule must specify exactly one selector: skill, bash, or text");
  for (const selector of selectors) {
    const value = d[selector];
    if (typeof value !== "string" || !value.trim()) errors.push(`${selector} must be a non-empty ${selector === "skill" ? "exact skill name" : "regular expression string"}`);
    else if (selector === "skill") {
      if (availableSkills && !availableSkills.has(value)) errors.push(`skill "${value}" is not an available registered skill`);
    } else if (!compile(value)) errors.push(`${selector} regular expression is invalid: ${JSON.stringify(value)}`);
    if (selector === "bash") {
      if (typeof d.message !== "string" || !d.message.trim()) errors.push("bash rule requires a non-empty message");
      if (d.action !== undefined && d.action !== "confirm" && d.action !== "block") errors.push('action must be "confirm" or "block" when specified; omit action to execute with a message');
      if (d.instructions !== undefined) errors.push("instructions is not valid for bash rules; use message");
    } else {
      if (typeof d.instructions !== "string" || !d.instructions.trim()) errors.push(`${selector} rule requires non-empty instructions`);
      if (d.action !== undefined) errors.push("action is only valid for bash rules");
      if (d.message !== undefined) errors.push(`message is only valid for bash rules; ${selector} rules use instructions`);
    }
  }
  return errors;
}

function invalidInfo(id: string, source: string, errors: string[], d: Record<string, unknown>): InvalidRuleInfo {
  const hasBash = d.bash !== undefined;
  const hasSkill = d.skill !== undefined;
  const hasText = d.text !== undefined;
  return { id, source, errors, hasBash, hasSkill, hasText, ambiguous: Number(hasBash) + Number(hasSkill) + Number(hasText) !== 1 };
}

function normalizeRule(d: Record<string, unknown>, source: string): Rule {
  const id = d.id as string;
  const enabled = d.enabled !== false;
  if (!enabled && !["skill", "bash", "text"].some(key => d[key] !== undefined)) return { id, enabled: false, source };
  if (typeof d.skill === "string") return { id, enabled, skill: d.skill, instructions: d.instructions as string, source };
  if (typeof d.bash === "string") return {
    id, enabled, bash: d.bash, message: d.message as string, source, regexp: compile(d.bash),
    ...(d.action === "confirm" || d.action === "block" ? { action: d.action } : {}),
  };
  return { id, enabled, text: d.text as string, instructions: d.instructions as string, source, regexp: compile(d.text as string) };
}

/** The nearest declaration owns an id before validation. No legacy fallback. */
export function mergeLayers(layers: RuleLayer[], availableSkills?: ReadonlySet<string>): ResolvedHarnessConfig {
  const byId = new Map<string, { rule?: Rule; invalid?: InvalidRuleInfo }>();
  const errors: string[] = [];
  let configReadIncomplete = false;
  let unavailable = false;
  const readableLayers: RuleLayer[] = [];
  for (const layer of layers) {
    if (layer.stale) configReadIncomplete = true;
    if (layer.unavailable) unavailable = true;
    for (const error of layer.errors ?? []) errors.push(`${layer.source}: ${error}`);
    const raw = layer as unknown as Record<string, unknown>;
    const container = Object.fromEntries(Object.entries(raw).filter(([key]) => !["source", "errors", "stale", "unavailable"].includes(key)));
    if (layer.rules === undefined && layer.stale && !Object.keys(container).length) continue;
    const structure = validateRuleContainer(container);
    if (structure.length) {
      errors.push(...structure.map(error => `${layer.source}: ${error}`));
      configReadIncomplete = true;
      unavailable = true;
      continue;
    }
    readableLayers.push(layer);
    for (const d of layer.rules ?? []) {
      const id = d.id as string;
      const invalid = validateRuleDeclaration(d, availableSkills);
      if (invalid.length) {
        errors.push(`${layer.source}: rule "${id}" is invalid: ${invalid.join("; ")}`);
        byId.set(id, { invalid: invalidInfo(id, layer.source, invalid, d) });
      } else byId.set(id, { rule: normalizeRule(d, layer.source) });
    }
  }
  const { legacy, errors: legacyErrors, notices } = resolveLegacy(readableLayers, availableSkills);
  legacy.unavailable ||= unavailable;
  errors.push(...legacyErrors);
  // Installed disabled lists historically suppress same-ID flat rules too.
  // Policy overrides replace only deliberately equivalent built-in defaults;
  // a manually authored flat definition otherwise remains independent.
  for (const name of legacy.disabled) {
    const entry = byId.get(name);
    if (entry?.rule) entry.rule = { ...entry.rule, enabled: false };
  }
  for (const name of [...legacy.policies.map(policy => policy.name), ...legacy.invalidPolicies.map(policy => policy.name)]) {
    const entry = byId.get(name);
    if (entry?.rule?.source === "built-in defaults") entry.rule = { ...entry.rule, enabled: false };
  }
  const ordered = [...byId].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([, entry]) => entry);
  const rules = ordered.flatMap(entry => entry.rule ? [entry.rule] : []);
  const invalidRules = ordered.flatMap(entry => entry.invalid ? [entry.invalid] : []);
  return { rules, errors, notices, legacy, invalidRules, bashEvaluationComplete: !unavailable && !invalidRules.some(info => info.hasBash || info.ambiguous), configReadIncomplete };
}

export function evaluateBash(config: ResolvedHarnessConfig, command: string): BashEvaluationResult {
  if (!config.bashEvaluationComplete) return {
    decision: "incomplete", messages: [], matchedRules: [],
    incompleteRuleIds: config.invalidRules.filter(info => info.hasBash || info.ambiguous).map(info => info.id),
    reason: "Bash evaluation is incomplete: repair invalid rule declarations or unavailable configuration before executing Bash calls.",
  };
  const matchedRules = config.rules.filter((rule): rule is BashRule => rule.enabled !== false && "bash" in rule && !!(rule.regexp ?? compile(rule.bash))?.test(command));
  const messages = matchedRules.map(rule => rule.message);
  const blocking = matchedRules.find(rule => rule.action === "block");
  const confirming = matchedRules.find(rule => rule.action === "confirm");
  return { decision: blocking ? "block" : confirming ? "confirm" : "execute", messages, matchedRules, ...(blocking || confirming ? { reason: (blocking ?? confirming)?.message } : {}) };
}

export function evaluateSkill(config: ResolvedHarnessConfig, skillName: string): SkillRule[] {
  return config.rules.filter((rule): rule is SkillRule => rule.enabled !== false && "skill" in rule && rule.skill === skillName);
}

/** Volume bounds report incomplete, never a successful no-match. Synchronous
 * JavaScript regexes cannot be preempted; pathological patterns remain a known
 * evaluator limitation, not a guarantee supplied by these volume bounds. */
export function evaluateText(config: ResolvedHarnessConfig, texts: string[], budget: { maxSegments?: number; maxChars?: number } = {}): { matches: TextRule[]; incomplete: boolean } {
  const maxSegments = budget.maxSegments ?? 4000;
  const maxChars = budget.maxChars ?? 2_000_000;
  const rules = config.rules.filter((rule): rule is TextRule => rule.enabled !== false && "text" in rule);
  if (!rules.length) return { matches: [], incomplete: false };
  const matched = new Map<string, TextRule>();
  let chars = 0;
  for (const [index, segment] of texts.entries()) {
    if (index >= maxSegments || chars + segment.length > maxChars) return { matches: [...matched.values()], incomplete: true };
    chars += segment.length;
    for (const rule of rules) if (!matched.has(rule.id) && (rule.regexp ?? compile(rule.text))?.test(segment)) matched.set(rule.id, rule);
  }
  return { matches: [...matched.values()], incomplete: false };
}
