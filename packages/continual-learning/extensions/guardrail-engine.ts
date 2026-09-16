/**
 * Pure guardrail policy and rules engine: layered config types, merging,
 * and tool-call/skill/text evaluation. No Pi imports — everything here is testable
 * without a session.
 */

import type {
  BashEvaluationResult,
  BashRule,
  InvalidRuleInfo,
  Policy,
  PolicyPhase,
  ResolvedConfig,
  ResolvedHarnessConfig,
  Rule,
  RuleLayer,
  SkillRule,
  TextRule,
} from "./guardrail-types.ts";

export const USER_CONFIG_DIR = ["agent"] as const;

export const DEFAULT_RULES: Rule[] = [
  {
    id: "no-bulk-memory-deletion",
    bash: "(?:\\brm\\b|\\bgit\\s+rm\\b|\\bunlink\\b|\\brsync\\b[^\\n]*--delete|\\b(?:python|python3|node|bun)\\b[^\\n]*(?:rmtree|rmSync|unlinkSync))[^\\n]*(?:\\.memory|\\.pi[/\\\\]agent[/\\\\]memory)|\\bfind\\b[^\\n]*(?:\\.memory|\\.pi[/\\\\]agent[/\\\\]memory)[^\\n]*-delete",
    action: "block",
    message:
      "Project memory must not be bulk-deleted through generated shell commands. Use the parent-owned /consolidate flow so preservation, privacy, rollback, and receipts are verified.",
  },
  {
    id: "no-interactive-auth-automation",
    bash: "\\b(npm|pnpm|yarn|bun)\\s+(login|adduser|logout|whoami\\s*--interactive)\\b",
    action: "block",
    message:
      "Interactive authentication cannot be automated from this session (no TTY, invisible browser). " +
      "Ask the user to run the login command in their own terminal and confirm when done.",
  },
  {
    id: "no-otp-in-chat",
    bash: "\\b(otp|one[- ]time (password|code))\\b.*[>|>>]|printf[^|]*\\b(otp|verification code)\\b.*>\\s*/tmp",
    action: "block",
    message:
      "Never route OTP codes through files or chat. Interactive OTP prompts must be answered by the " +
      "user in their own terminal; ask them to run the command and report the result.",
  },
];

/** Built-in policies mirror DEFAULT_RULES for the legacy evaluate() path so
 * existing user files and the consolidation subsystem keep working during the
 * format migration. New bash rules are NOT bridged here (that produced phantom
 * observe decisions); they are evaluated by evaluateBash. */
export const DEFAULT_POLICIES: Policy[] = [
  {
    name: "no-bulk-memory-deletion",
    tools: ["bash"],
    paths: ["command"],
    patterns: [
      "(?:\\brm\\b|\\bgit\\s+rm\\b|\\bunlink\\b|\\brsync\\b[^\\n]*--delete|\\b(?:python|python3|node|bun)\\b[^\\n]*(?:rmtree|rmSync|unlinkSync))[^\\n]*(?:\\.memory|\\.pi[/\\\\]agent[/\\\\]memory)",
      "\\bfind\\b[^\\n]*(?:\\.memory|\\.pi[/\\\\]agent[/\\\\]memory)[^\\n]*-delete",
    ],
    action: "block",
    reason:
      "Project memory must not be bulk-deleted through generated shell commands. Use the parent-owned /consolidate flow so preservation, privacy, rollback, and receipts are verified.",
  },
  {
    name: "no-interactive-auth-automation",
    tools: ["bash"],
    paths: ["command"],
    pattern: "\\b(npm|pnpm|yarn|bun)\\s+(login|adduser|logout|whoami\\s*--interactive)\\b",
    action: "block",
    reason:
      "Interactive authentication cannot be automated from this session (no TTY, invisible browser). " +
      "Ask the user to run the login command in their own terminal and confirm when done.",
  },
  {
    name: "no-otp-in-chat",
    tools: ["bash"],
    paths: ["command"],
    pattern: "\\b(otp|one[- ]time (password|code))\\b.*[>|>>]|printf[^|]*\\b(otp|verification code)\\b.*>\\s*/tmp",
    action: "block",
    reason:
      "Never route OTP codes through files or chat. Interactive OTP prompts must be answered by the " +
      "user in their own terminal; ask them to run the command and report the result.",
  },
];

function compile(pattern: string): RegExp | undefined {
  try {
    return new RegExp(pattern);
  } catch {
    return undefined;
  }
}

function stringArray(value: unknown): string[] | undefined {
  return Array.isArray(value) && value.every((entry) => typeof entry === "string")
    ? value
    : undefined;
}

const SUPPORTED_RULE_FIELDS = [
  "id",
  "enabled",
  "skill",
  "instructions",
  "bash",
  "action",
  "message",
  "text",
] as const;

/**
 * Validate a single rule declaration.
 * Every rule must have a non-empty `id` and exactly one selector: `skill`, `bash`, or `text`,
 * or be a disabled declaration with `enabled: false`.
 */
export function validateRuleDeclaration(raw: unknown, availableSkills?: ReadonlySet<string>): string[] {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return ["rule must be an object"];
  }
  const declaration = raw as Record<string, unknown>;
  const errors: string[] = [];

  const unsupported = Object.keys(declaration).filter(
    (key) => !(SUPPORTED_RULE_FIELDS as readonly string[]).includes(key as (typeof SUPPORTED_RULE_FIELDS)[number]),
  );
  if (unsupported.length > 0) {
    errors.push(`unsupported field(s): ${unsupported.join(", ")}; supported fields are ${SUPPORTED_RULE_FIELDS.join(", ")}`);
  }

  if (typeof declaration.id !== "string" || !declaration.id.trim()) {
    errors.push("id must be a non-empty string");
  }

  if (declaration.enabled !== undefined && typeof declaration.enabled !== "boolean") {
    errors.push("enabled must be a boolean");
  }

  const hasSkill = declaration.skill !== undefined;
  const hasBash = declaration.bash !== undefined;
  const hasText = declaration.text !== undefined;
  const selectorCount = (hasSkill ? 1 : 0) + (hasBash ? 1 : 0) + (hasText ? 1 : 0);

  // Minimal disabled declaration: { id: "...", enabled: false }
  if (declaration.enabled === false && selectorCount === 0) {
    return errors;
  }

  if (selectorCount === 0) {
    errors.push("rule must specify exactly one selector: skill, bash, or text");
    return errors;
  }

  if (selectorCount > 1) {
    errors.push("rule must specify only one selector: choose from skill, bash, or text");
  }

  if (hasSkill) {
    if (typeof declaration.skill !== "string" || !declaration.skill.trim()) {
      errors.push("skill must be a non-empty exact skill name");
    } else if (availableSkills && !availableSkills.has(declaration.skill)) {
      errors.push(`skill "${declaration.skill}" is not an available registered skill`);
    }
    if (typeof declaration.instructions !== "string" || !declaration.instructions.trim()) {
      errors.push("skill rule requires non-empty instructions");
    }
    if (declaration.action !== undefined) {
      errors.push("action is only valid for bash rules");
    }
    if (declaration.message !== undefined) {
      errors.push("message is only valid for bash rules; skill rules use instructions");
    }
  }

  if (hasBash) {
    if (typeof declaration.bash !== "string" || !declaration.bash.trim()) {
      errors.push("bash must be a non-empty regular expression string");
    } else if (!compile(declaration.bash)) {
      errors.push(`bash regular expression is invalid: ${JSON.stringify(declaration.bash)}`);
    }
    if (typeof declaration.message !== "string" || !declaration.message.trim()) {
      errors.push("bash rule requires a non-empty message");
    }
    if (declaration.action !== undefined && declaration.action !== "confirm" && declaration.action !== "block") {
      errors.push('action must be "confirm" or "block" when specified; omit action to execute with a message');
    }
    if (declaration.instructions !== undefined) {
      errors.push("instructions is not valid for bash rules; use message");
    }
  }

  if (hasText) {
    if (typeof declaration.text !== "string" || !declaration.text.trim()) {
      errors.push("text must be a non-empty regular expression string");
    } else if (!compile(declaration.text)) {
      errors.push(`text regular expression is invalid: ${JSON.stringify(declaration.text)}`);
    }
    if (typeof declaration.instructions !== "string" || !declaration.instructions.trim()) {
      errors.push("text rule requires non-empty instructions");
    }
    if (declaration.action !== undefined) {
      errors.push("action is only valid for bash rules");
    }
    if (declaration.message !== undefined) {
      errors.push("message is only valid for bash rules; text rules use instructions");
    }
  }

  return errors;
}

interface StoredRuleEntry {
  id: string;
  rule?: Rule;
  invalid?: InvalidRuleInfo;
  source: string;
}

function invalidInfo(
  id: string,
  source: string,
  errors: string[],
  declaration: Record<string, unknown> | undefined,
): InvalidRuleInfo {
  const hasBash = declaration?.bash !== undefined;
  const hasSkill = declaration?.skill !== undefined;
  const hasText = declaration?.text !== undefined;
  const selectorCount = (hasBash ? 1 : 0) + (hasSkill ? 1 : 0) + (hasText ? 1 : 0);
  return {
    id,
    source,
    errors,
    hasBash,
    hasSkill,
    hasText,
    // No single valid selector → conservative: treat as bash-affecting.
    ambiguous: selectorCount !== 1,
  };
}

/**
 * Merge layers innermost-last: built-in < user < project < project.local.
 * The nearest declaration of an id completely replaces the outer one; distinct
 * ids inherit independently. Invalid winning declarations shadow without
 * substituting the outer definition and are reported structurally.
 */
export function mergeLayers(layers: RuleLayer[], availableSkills?: ReadonlySet<string>): ResolvedHarnessConfig {
  const byId = new Map<string, StoredRuleEntry>();
  const errors: string[] = [];
  let configReadIncomplete = false;

  // Legacy containers (existing user files + built-in defaults during migration)
  const legacyPolicies = new Map<string, { policy: Policy }>();
  const legacySkillPrompts = new Map<string, { prompt: string; target: "system" | "user"; userMessagePattern?: string; source: string }>();
  const legacyDisabled = new Set<string>();

  for (const layer of layers) {
    if (layer.stale) configReadIncomplete = true;
    for (const err of layer.errors ?? []) {
      errors.push(`${layer.source}: ${err}`);
    }

    if (Array.isArray(layer.rules)) {
      const seenInLayer = new Set<string>();
      for (const raw of layer.rules) {
        if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
          errors.push(`${layer.source}: rule entry must be an object`);
          configReadIncomplete = true;
          continue;
        }
        const declaration = raw as Record<string, unknown>;
        const id =
          typeof declaration.id === "string" && declaration.id.trim() ? declaration.id.trim() : undefined;

        if (!id) {
          // Cannot key an id-less entry; conservative structural failure.
          errors.push(`${layer.source}: rule entry is missing id`);
          byId.set(`(missing-id@${layer.source})`, {
            id: "(missing-id)",
            source: layer.source,
            invalid: invalidInfo("(missing-id)", layer.source, ["rule entry is missing id"], declaration),
          });
          continue;
        }

        if (seenInLayer.has(id)) {
          // Duplicate identity in one layer: structural error, no positional winner.
          errors.push(`${layer.source}: duplicate rule id "${id}" in same layer`);
          byId.set(id, {
            id,
            source: layer.source,
            invalid: invalidInfo(id, layer.source, [`duplicate rule id "${id}" in same layer`], undefined),
          });
          continue;
        }
        seenInLayer.add(id);

        const declErrors = validateRuleDeclaration(declaration, availableSkills);
        if (declErrors.length > 0) {
          errors.push(`${layer.source}: rule "${id}" is invalid: ${declErrors.join("; ")}`);
          byId.set(id, { id, source: layer.source, invalid: invalidInfo(id, layer.source, declErrors, declaration) });
          continue;
        }

        byId.set(id, { id, rule: normalizeRule(declaration, layer.source), source: layer.source });
      }
    }

    // Legacy format (only when this layer carries no new rules array)
    if (!Array.isArray(layer.rules)) {
      for (const name of layer.disabled ?? []) legacyDisabled.add(name);
      for (const [name, raw] of Object.entries(layer.skillPrompts ?? {})) {
        const declarationErrors = validateSkillPromptDeclaration(name, raw, availableSkills);
        if (declarationErrors.length) {
          errors.push(`${layer.source}: skill prompt "${name}" was skipped: ${declarationErrors.join("; ")}`);
          continue;
        }
        const entry = raw as Record<string, unknown>;
        const prompt = entry.prompt;
        const target = entry.target;
        if (typeof prompt !== "string" || (target !== "system" && target !== "user")) continue;
        legacySkillPrompts.set(name, {
          prompt,
          target,
          ...(typeof entry.userMessagePattern === "string" ? { userMessagePattern: entry.userMessagePattern } : {}),
          source: layer.source,
        });
      }
      for (const raw of layer.policies ?? []) {
        const declarationErrors = validatePolicyDeclaration(raw);
        const name =
          raw && typeof raw === "object" && !Array.isArray(raw) && typeof (raw as Record<string, unknown>).name === "string"
            ? ((raw as Record<string, unknown>).name as string)
            : undefined;
        if (declarationErrors.length) {
          errors.push(`${layer.source}: policy${name ? ` "${name}"` : ""} was skipped: ${declarationErrors.join("; ")}`);
          continue;
        }
        const declaration = raw as Record<string, unknown>;
        legacyPolicies.set(name as string, {
          policy: normalizePolicy(
            declaration,
            layer.source,
            declaration.tools === undefined ? undefined : stringArray(declaration.tools),
            declaration.paths === undefined ? undefined : stringArray(declaration.paths),
            declaration.artifactPaths === undefined ? undefined : stringArray(declaration.artifactPaths),
            declaration.patterns === undefined ? undefined : stringArray(declaration.patterns),
          ),
        });
      }
    }
  }

  // Legacy `disabled` names also disable a same-id new rule (migration affordance).
  for (const name of legacyDisabled) {
    const entry = byId.get(name);
    if (entry?.rule) entry.rule = { ...entry.rule, enabled: false } as Rule;
  }

  const rules: Rule[] = [];
  const invalidRules: InvalidRuleInfo[] = [];
  for (const entry of byId.values()) {
    if (entry.invalid) {
      invalidRules.push(entry.invalid);
      continue;
    }
    if (entry.rule) rules.push(entry.rule);
  }

  // Bash coverage is incomplete when any invalid winning rule is bash-scoped or ambiguous.
  const bashEvaluationComplete = !invalidRules.some((info) => info.hasBash || info.ambiguous);

  const finalLegacyPolicies: Array<Policy & { regexps: RegExp[] }> = [];
  for (const [name, entry] of legacyPolicies) {
    if (legacyDisabled.has(name)) continue;
    const patterns = entry.policy.patterns ?? (entry.policy.pattern ? [entry.policy.pattern] : []);
    const regexps: RegExp[] = [];
    for (const p of patterns) {
      const re = compile(p);
      if (re) regexps.push(re);
    }
    finalLegacyPolicies.push({ ...entry.policy, regexps });
  }

  return {
    rules,
    errors,
    invalidRules,
    bashEvaluationComplete,
    configReadIncomplete,
    policies: finalLegacyPolicies,
    skillPrompts: Object.fromEntries(legacySkillPrompts),
  };
}

function normalizeRule(declaration: Record<string, unknown>, source: string): Rule {
  const id = String(declaration.id).trim();
  const enabled = declaration.enabled !== false;

  if (!enabled) {
    return { id, enabled: false, source };
  }

  if (typeof declaration.skill === "string") {
    return { id, enabled: true, skill: declaration.skill, instructions: String(declaration.instructions), source };
  }

  if (typeof declaration.bash === "string") {
    return {
      id,
      enabled: true,
      bash: declaration.bash,
      ...(declaration.action === "confirm" || declaration.action === "block" ? { action: declaration.action } : {}),
      message: String(declaration.message),
      source,
      regexp: compile(declaration.bash),
    };
  }

  return {
    id,
    enabled: true,
    text: String(declaration.text),
    instructions: String(declaration.instructions),
    source,
    regexp: compile(String(declaration.text)),
  };
}

/**
 * Evaluate a Bash command against effective resolved rules. Every matched rule
 * contributes its message; the single call decision is block > confirm > execute,
 * independent of rule order. When Bash coverage is incomplete (an invalid
 * bash-scoped or ambiguous winning rule), the call is not silently executed.
 */
export function evaluateBash(config: ResolvedHarnessConfig, command: string): BashEvaluationResult {
  if (!config.bashEvaluationComplete) {
    const ids = config.invalidRules.filter((i) => i.hasBash || i.ambiguous).map((i) => i.id);
    return {
      decision: "incomplete",
      messages: [],
      matchedRules: [],
      incompleteRuleIds: ids,
      reason: `Bash evaluation is incomplete: invalid rule declaration(s) ${ids.join(", ") || "(unidentified)"} must be repaired. Matching Bash calls are held until the configuration is valid.`,
    };
  }

  const matchedRules: BashRule[] = [];
  for (const rule of config.rules) {
    if (rule.enabled === false) continue;
    if (!("bash" in rule)) continue;
    const re = rule.regexp ?? compile(rule.bash);
    if (re && re.test(command)) matchedRules.push(rule);
  }

  if (matchedRules.length === 0) {
    return { decision: "execute", messages: [], matchedRules: [] };
  }

  const messages = matchedRules.map((r) => r.message);
  const blockRule = matchedRules.find((r) => r.action === "block");
  if (blockRule) {
    return { decision: "block", messages, matchedRules, reason: blockRule.message };
  }
  const confirmRule = matchedRules.find((r) => r.action === "confirm");
  if (confirmRule) {
    return { decision: "confirm", messages, matchedRules, reason: confirmRule.message };
  }
  return { decision: "execute", messages, matchedRules };
}

/** All matching enabled skill rules for an exact expanded skill name. */
export function evaluateSkill(config: ResolvedHarnessConfig, skillName: string): SkillRule[] {
  const matches: SkillRule[] = [];
  for (const rule of config.rules) {
    if (rule.enabled === false) continue;
    if ("skill" in rule && rule.skill === skillName) matches.push(rule);
  }
  return matches;
}

/**
 * All matching enabled text rules across independently-evaluated text segments.
 * Bounded by maxSegments/maxChars so a large conversation reports incomplete
 * rather than hanging; incomplete results must not be read as "no match".
 */
export function evaluateText(
  config: ResolvedHarnessConfig,
  texts: string[],
  budget: { maxSegments?: number; maxChars?: number } = {},
): { matches: TextRule[]; incomplete: boolean } {
  const maxSegments = budget.maxSegments ?? 4000;
  const maxChars = budget.maxChars ?? 2_000_000;
  const matched = new Map<string, TextRule>();
  const textRules = config.rules.filter((r): r is TextRule => r.enabled !== false && "text" in r);
  if (textRules.length === 0) return { matches: [], incomplete: false };

  let segments = 0;
  let chars = 0;
  let incomplete = false;
  for (const segment of texts) {
    if (segments >= maxSegments || chars >= maxChars) {
      incomplete = true;
      break;
    }
    segments += 1;
    chars += segment.length;
    for (const rule of textRules) {
      if (matched.has(rule.id)) continue;
      const re = rule.regexp ?? compile(rule.text);
      if (re && re.test(segment)) matched.set(rule.id, rule);
    }
  }
  return { matches: [...matched.values()], incomplete };
}

// ---------------------------------------------------------------------------
// Legacy policy engine helpers (existing user files + consolidation subsystem)
// ---------------------------------------------------------------------------

const POLICY_FIELDS = ["name", "phase", "tools", "paths", "artifactPaths", "pattern", "patterns", "require", "action", "reason"] as const;
const POLICY_FIELD_LIST = "name, phase, tools, paths, pattern, patterns, artifactPaths, require, action, and reason";
const SKILL_PROMPT_FIELDS = ["prompt", "target", "userMessagePattern"] as const;
const POLICY_PHASES = ["tool-call", "output", "artifact"] as const satisfies readonly PolicyPhase[];

export function validateSkillPromptDeclaration(
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

export function validatePolicyDeclaration(raw: unknown): string[] {
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

export interface ToolCallInput {
  toolName: string;
  args: Record<string, unknown>;
}

export interface Decision {
  policyName: string;
  action: "block" | "confirm" | "observe";
  reason: string;
  cleanReason?: string;
  source?: string;
}

export interface PhaseCheckInput {
  phase: Exclude<PolicyPhase, "tool-call">;
  text: string;
  toolName?: string;
  policyName?: string;
  ignoreTools?: boolean;
}

function valueAtPath(args: Record<string, unknown>, path?: string): string[] {
  if (!path) return [JSON.stringify(args)];
  return collectLeaves(args, path.split("."));
}

function collectLeaves(value: unknown, segs: string[]): string[] {
  if (segs.length === 0) {
    if (typeof value === "string") return [value];
    if (value !== undefined && value !== null) return [JSON.stringify(value)];
    return [];
  }
  if (Array.isArray(value)) return value.flatMap((item) => collectLeaves(item, segs));
  if (value !== null && typeof value === "object") {
    const next = (value as Record<string, unknown>)[segs[0]];
    return next === undefined ? [] : collectLeaves(next, segs.slice(1));
  }
  return [];
}

export function evaluate(config: ResolvedConfig, call: ToolCallInput): Decision | null {
  for (const policy of config.policies ?? []) {
    if ((policy.phase ?? "tool-call") !== "tool-call") continue;
    if (policy.tools && !policy.tools.includes(call.toolName)) continue;
    if (policy.require) {
      const gateSubject = valueAtPath(call.args, policy.require.path);
      const gateRe = compile(policy.require.pattern);
      if (!gateRe || !gateSubject.some((leaf) => gateRe.test(leaf))) continue;
    }
    const subjects = policy.paths ? policy.paths.flatMap((p) => valueAtPath(call.args, p)) : valueAtPath(call.args);
    if (policy.regexps.some((re) => subjects.some((leaf) => re.test(leaf)))) {
      return {
        policyName: policy.name,
        action: policy.action ?? "block",
        reason: `[guardrails:${policy.name}] ${policy.reason}`,
        cleanReason: policy.reason,
        source: policy.source,
      };
    }
  }
  return null;
}

export function evaluatePhase(config: ResolvedConfig, input: PhaseCheckInput): Decision | null {
  for (const policy of config.policies ?? []) {
    if ((policy.phase ?? "tool-call") !== input.phase) continue;
    if (input.policyName && policy.name !== input.policyName) continue;
    if (!input.ignoreTools && policy.tools && (!input.toolName || !policy.tools.includes(input.toolName))) continue;
    if (policy.require) {
      const gateRe = compile(policy.require.pattern);
      if (!gateRe || !gateRe.test(input.text)) continue;
    }
    if (!policy.regexps.some((re) => re.test(input.text))) continue;
    return {
      policyName: policy.name,
      action: policy.action ?? "block",
      reason: `[guardrails:${policy.name}] ${policy.reason}`,
      cleanReason: policy.reason,
      source: policy.source,
    };
  }
  return null;
}
