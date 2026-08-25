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

/** Merge layers innermost-last: user < project, shared < .local. A policy
 * name defined in several layers resolves to the definition of the
 * innermost layer that declares it; disabled names are collected from every
 * layer and remove matching policies everywhere. */
export function mergeLayers(layers: PolicyLayer[]): ResolvedConfig {
  const byName = new Map<string, { policy: Policy; broken?: string }>();
  const disabled = new Set<string>();
  const errors: string[] = [];

  for (const layer of layers) {
    for (const name of layer.disabled ?? []) disabled.add(name);
    for (const raw of layer.policies ?? []) {
      if (!raw || typeof raw.name !== "string" || !raw.name.trim()) {
        errors.push(`${layer.source}: policy without a name was skipped`);
        continue;
      }
      const hasPattern = Array.isArray(raw.patterns) || typeof raw.pattern === "string";
      const requirement = raw.require as Record<string, unknown> | undefined;
      const hasValidRequire =
        !requirement ||
        (typeof requirement.pattern === "string" &&
          (typeof requirement.path === "string" || requirement.path === undefined));
      if (!hasPattern && !hasValidRequire) {
        errors.push(`${layer.source}: policy "${raw.name}" has neither pattern(s) nor a valid require gate and was skipped`);
        continue;
      }
      if (!hasValidRequire) {
        errors.push(`${layer.source}: policy "${raw.name}" has an invalid require gate (need string pattern, optional string path) and was skipped`);
        continue;
      }
      byName.set(raw.name, { policy: normalizePolicy(raw, layer.source) });
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
      else errors.push(`policy "${name}": invalid regex ${JSON.stringify(p)} — skipped pattern`);
    }
    if (regexps.length === 0 && patterns.length > 0) continue;
    policies.push({ ...entry.policy, regexps });
  }
  return { policies, errors };
}

function normalizePolicy(raw: Record<string, unknown>, source: string): Policy {
  const requirement = raw.require as Record<string, unknown> | undefined;
  return {
    name: String(raw.name),
    tools: Array.isArray(raw.tools) ? (raw.tools as string[]) : undefined,
    paths: Array.isArray(raw.paths) ? (raw.paths as string[]) : undefined,
    pattern: typeof raw.pattern === "string" ? raw.pattern : undefined,
    patterns: Array.isArray(raw.patterns) ? (raw.patterns as string[]) : undefined,
    require:
      requirement && typeof requirement.pattern === "string"
        ? {
            path: typeof requirement.path === "string" ? requirement.path : undefined,
            pattern: requirement.pattern,
          }
        : undefined,
    action: raw.action === "confirm" ? "confirm" : "block",
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
  action: "block" | "confirm";
  reason: string;
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
      : valueAtPath(call.args, policy.path);
    if (policy.regexps.some((re) => subjects.some((leaf) => re.test(leaf)))) {
      return {
        policyName: policy.name,
        action: policy.action ?? "block",
        reason: `[guardrails:${policy.name}] ${policy.reason}`,
      };
    }
  }
  return null;
}
