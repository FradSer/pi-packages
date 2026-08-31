/**
 * Pure guardrail policy engine: layered config types, merging, and
 * tool-call evaluation. No Pi imports — everything here is testable
 * without a session.
 */

import type { Policy, PolicyLayer, ResolvedConfig } from "./guardrail-types.ts";

export const USER_CONFIG_DIR = ["agent"] as const;

/** Built-in policies for known-futile automation attempts. Each reason is the
 * "more correct prompt" fed back to the model when the call is blocked. */
export const DEFAULT_POLICIES: Policy[] = [
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

const POLICY_FIELDS = ["name", "tools", "paths", "pattern", "patterns", "require", "action", "reason"] as const;
const POLICY_FIELD_LIST = "name, tools, paths, pattern, patterns, require, action, and reason";

/** Validate the authored declaration before it reaches normalization. Keeping
 * this contract shared with consolidation prevents a planner or direct caller
 * from writing a policy the runtime would silently ignore. */
export function validatePolicyDeclaration(raw: unknown): string[] {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return ["must be an object"];
  const declaration = raw as Record<string, unknown>;
  const errors: string[] = [];
  const unsupported = Object.keys(declaration).filter((key) => !(POLICY_FIELDS as readonly string[]).includes(key));
  if (unsupported.length) {
    errors.push(
      `unsupported field(s): ${unsupported.join(", ")}; supported declaration fields are ${POLICY_FIELD_LIST}`,
    );
  }

  if (typeof declaration.name !== "string" || !declaration.name.trim()) {
    errors.push("name must be a non-empty string");
  }

  for (const field of ["tools", "paths"] as const) {
    if (declaration[field] !== undefined && !stringArray(declaration[field])) {
      errors.push(`${field} must be an array of strings`);
    }
  }

  const hasPattern = declaration.pattern !== undefined;
  const hasPatterns = declaration.patterns !== undefined;
  if (hasPattern && hasPatterns) {
    errors.push("use pattern or patterns, not both");
  }
  if (!hasPattern && !hasPatterns) {
    errors.push("requires a non-empty pattern or patterns declaration");
  } else if (hasPattern) {
    if (typeof declaration.pattern !== "string" || !declaration.pattern.trim()) {
      errors.push("pattern must be a non-empty regular expression string");
    }
  } else {
    const patternList = stringArray(declaration.patterns);
    if (!patternList || patternList.length === 0) {
      errors.push("patterns must be a non-empty array of regular expression strings");
    } else if (patternList.some((pattern) => !pattern.trim())) {
      errors.push("patterns must not contain empty regular expressions");
    }
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
      if (typeof gate.pattern !== "string" || !gate.pattern.trim()) {
        errors.push("require.pattern must be a non-empty regular expression string");
      }
    }
  }
  if (
    declaration.action !== undefined &&
    declaration.action !== "block" &&
    declaration.action !== "confirm" &&
    declaration.action !== "observe"
  ) {
    errors.push('action must be "block", "confirm", or "observe"');
  }
  if (declaration.reason !== undefined && (typeof declaration.reason !== "string" || !declaration.reason.trim())) {
    errors.push("reason must be a non-empty string when provided");
  }

  const regexSources = [
    ...(typeof declaration.pattern === "string" ? [declaration.pattern] : []),
    ...(stringArray(declaration.patterns) ?? []),
    ...(
      declaration.require && typeof declaration.require === "object" && !Array.isArray(declaration.require)
        ? [((declaration.require as Record<string, unknown>).pattern)]
        : []
    ),
  ];
  for (const source of regexSources) {
    if (typeof source === "string" && source.trim() && !compile(source)) {
      errors.push(`invalid regex ${JSON.stringify(source)}`);
    }
  }
  return errors;
}

/** Merge layers innermost-last: user < project, shared < .local. A policy
 * name defined in several layers resolves to the definition of the
 * innermost layer that declares it; disabled names are collected from every
 * layer and remove matching policies everywhere. */
export function mergeLayers(layers: PolicyLayer[]): ResolvedConfig {
  const byName = new Map<string, { policy: Policy; broken?: string }>();
  const skillPrompts = new Map<string, { prompt: string; target: "system" | "user"; source: string }>();
  const disabled = new Set<string>();
  const errors: string[] = [];

  for (const layer of layers) {
    for (const name of layer.disabled ?? []) disabled.add(name);
    for (const [name, raw] of Object.entries(layer.skillPrompts ?? {})) {
      if (
        name.length === 0 ||
        name.length > 64 ||
        !/^[a-z0-9-]+$/.test(name) ||
        name.startsWith("-") ||
        name.endsWith("-") ||
        name.includes("--")
      ) {
        errors.push(`${layer.source}: skill prompt name "${name}" violates the Pi skill-name rules and was skipped`);
        continue;
      }
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
        errors.push(`${layer.source}: skill prompt "${name}" must be an object and was skipped`);
        continue;
      }
      const entry = raw as Record<string, unknown>;
      if (typeof entry.prompt !== "string" || !entry.prompt.trim()) {
        errors.push(`${layer.source}: skill prompt "${name}" needs a non-empty string prompt and was skipped`);
        continue;
      }
      if (entry.target !== "system" && entry.target !== "user") {
        errors.push(`${layer.source}: skill prompt "${name}" target must be system or user and was skipped`);
        continue;
      }
      if (entry.userMessagePattern !== undefined) {
        if (typeof entry.userMessagePattern !== "string" || !entry.userMessagePattern.trim()) {
          errors.push(`${layer.source}: skill prompt "${name}" userMessagePattern must be a non-empty regular expression string and was skipped`);
          continue;
        }
        if (!compile(entry.userMessagePattern)) {
          errors.push(`${layer.source}: skill prompt "${name}" userMessagePattern is an invalid regex and was skipped`);
          continue;
        }
      }
      skillPrompts.set(name, {
        prompt: entry.prompt,
        target: entry.target,
        ...(typeof entry.userMessagePattern === "string" ? { userMessagePattern: entry.userMessagePattern } : {}),
        source: layer.source,
      });
    }
    for (const raw of layer.policies ?? []) {
      const declarationErrors = validatePolicyDeclaration(raw);
      const name =
        raw && typeof raw === "object" && !Array.isArray(raw) && typeof (raw as Record<string, unknown>).name === "string"
          ? (raw as Record<string, unknown>).name
          : undefined;
      if (declarationErrors.length) {
        errors.push(
          `${layer.source}: policy${name ? ` "${name}"` : ""} was skipped: ${declarationErrors.join("; ")}`,
        );
        continue;
      }
      const declaration = raw as Record<string, unknown>;
      const tools = declaration.tools === undefined ? undefined : stringArray(declaration.tools);
      const paths = declaration.paths === undefined ? undefined : stringArray(declaration.paths);
      const patterns = declaration.patterns === undefined ? undefined : stringArray(declaration.patterns);
      byName.set(name as string, { policy: normalizePolicy(declaration, layer.source, tools, paths, patterns) });
    }
    for (const err of layer.errors ?? []) errors.push(`${layer.source}: ${err}`);
  }

  const policies: Array<Policy & { regexps: RegExp[] }> = [];
  for (const [name, entry] of byName) {
    if (disabled.has(name)) continue;
    const patterns =
      entry.policy.patterns ??
      (entry.policy.pattern ? [entry.policy.pattern] : []);
    const regexps: RegExp[] = [];
    for (const p of patterns) {
      const re = compile(p);
      if (re) regexps.push(re);
    }
    policies.push({ ...entry.policy, regexps });
  }
  return {
    policies,
    skillPrompts: Object.fromEntries(skillPrompts),
    errors,
  };
}

function normalizePolicy(
  raw: Record<string, unknown>,
  source: string,
  tools: string[] | undefined,
  paths: string[] | undefined,
  patterns: string[] | undefined,
): Policy {
  const requirement = raw.require as Record<string, unknown> | undefined;
  return {
    name: String(raw.name),
    tools,
    paths,
    pattern: typeof raw.pattern === "string" ? raw.pattern : undefined,
    patterns,
    require:
      requirement && typeof requirement.pattern === "string"
        ? {
            path: typeof requirement.path === "string" ? requirement.path : undefined,
            pattern: requirement.pattern,
          }
        : undefined,
    action: raw.action === "confirm" || raw.action === "observe" ? raw.action : "block",
    reason:
      typeof raw.reason === "string" && raw.reason.trim()
        ? raw.reason
        : "Blocked by guardrails policy.",
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

function valueAtPath(args: Record<string, unknown>, path?: string): string[] {
  if (!path) return [JSON.stringify(args)];
  return collectLeaves(args, path.split("."));
}

/** Collect string values reachable via dot segments; arrays fan out so
 * "edits.newText" scans every edit's replacement text. */
function collectLeaves(value: unknown, segs: string[]): string[] {
  if (segs.length === 0) {
    if (typeof value === "string") return [value];
    if (value !== undefined && value !== null) return [JSON.stringify(value)];
    return [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => collectLeaves(item, segs));
  }
  if (value !== null && typeof value === "object") {
    const next = (value as Record<string, unknown>)[segs[0]];
    return next === undefined ? [] : collectLeaves(next, segs.slice(1));
  }
  return [];
}

/**
 * Evaluate one tool call against resolved policies. Returns a decision for
 * the first matching policy (config order), or null when nothing matches.
 */
export function evaluate(config: ResolvedConfig, call: ToolCallInput): Decision | null {
  for (const policy of config.policies) {
    if (policy.tools && !policy.tools.includes(call.toolName)) continue;
    // Optional require gate: every listed condition must ALSO match (AND).
    // This lets one policy combine "touches UI files" with "contains a
    // violation" instead of firing on unrelated calls.
    if (policy.require) {
      const gateSubject = valueAtPath(call.args, policy.require.path);
      const gateRe = compile(policy.require.pattern);
      if (!gateRe || !gateSubject.some((leaf) => gateRe.test(leaf))) continue;
    }
    const subjects = policy.paths
      ? policy.paths.flatMap((p) => valueAtPath(call.args, p))
      : valueAtPath(call.args);
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
