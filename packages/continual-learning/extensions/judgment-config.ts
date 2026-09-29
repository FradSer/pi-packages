/**
 * Judgment activation.
 *
 * Judgment is opt-in. With no resolved API key it is inactive, and an inactive
 * run is indistinguishable from a run without the feature: no request, no
 * record, no diagnostic that changes what the parent does. Every other
 * condition — an unreadable file, malformed JSON, an unsupported field, a
 * configuration without a key — fails closed to inactive with a reason, because
 * a configuration fault must never change learning behavior.
 */

import { lstatSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";

/** A versioned model id, never a moving alias: a threshold tuned against one
 *  release must not be silently applied to another. */
export const DEFAULT_JUDGMENT_MODEL = "jev-1.13.0";
export const DEFAULT_JUDGMENT_BASE_URL = "https://api.typesafe.ai";

const MAX_CONFIG_BYTES = 8_192;
const API_FIELDS = new Set(["apiKey", "model", "baseUrl"]);

export interface JudgmentConfigInput {
  env?: Record<string, string | undefined>;
  agentDir?: string;
}

export interface JudgmentApiConfig {
  active: true;
  apiKey: string;
  model: string;
  baseUrl: string;
}

export interface JudgmentInactiveConfig {
  active: false;
  reason: string;
}

export type JudgmentConfig = JudgmentApiConfig | JudgmentInactiveConfig;

export function judgmentConfigPath(agentDir = getAgentDir()): string {
  return join(resolve(agentDir), "continual-learning.json");
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

interface ApiFile {
  apiKey?: string;
  model?: string;
  baseUrl?: string;
}

/**
 * Read the persisted API block. Every rejection is a reason, never a throw:
 * a caller that could not read its configuration must still be able to run.
 */
function readApiFile(agentDir: string): { api?: ApiFile; reason?: string } {
  const file = judgmentConfigPath(agentDir);
  let stat: ReturnType<typeof lstatSync>;
  try {
    stat = lstatSync(file);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return {};
    return { reason: "continual-learning.json could not be read safely" };
  }
  if (stat.isSymbolicLink() || !stat.isFile()) {
    return { reason: "continual-learning.json is not a regular file" };
  }
  if (stat.size > MAX_CONFIG_BYTES) {
    return { reason: `continual-learning.json exceeds ${MAX_CONFIG_BYTES} bytes` };
  }
  let raw: string;
  try {
    raw = readFileSync(file, "utf-8");
    if (Buffer.byteLength(raw, "utf-8") > MAX_CONFIG_BYTES) {
      return { reason: `continual-learning.json exceeds ${MAX_CONFIG_BYTES} bytes` };
    }
  } catch {
    return { reason: "continual-learning.json could not be read safely" };
  }
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return { reason: "continual-learning.json is not valid JSON" };
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { reason: "continual-learning.json must contain an object" };
  }
  const record = value as Record<string, unknown>;
  // `judgment` is a sibling block in the same file, not an unknown field. It is
  // read separately, because a malformed authority block must never be blamed on
  // the credential block — but its presence here is not a schema violation.
  const unsupportedRoot = Object.keys(record).find((key) => key !== "api" && key !== "judgment");
  if (unsupportedRoot) return { reason: `continual-learning.json contains unsupported field ${unsupportedRoot}` };
  if (record.api === undefined) return {};
  if (!record.api || typeof record.api !== "object" || Array.isArray(record.api)) {
    return { reason: "continual-learning.json api must be an object" };
  }
  const api = record.api as Record<string, unknown>;
  const unsupported = Object.keys(api).find((key) => !API_FIELDS.has(key));
  if (unsupported) return { reason: `continual-learning.json api contains unsupported field ${unsupported}` };
  return {
    api: {
      ...(text(api.apiKey) ? { apiKey: text(api.apiKey)! } : {}),
      ...(text(api.model) ? { model: text(api.model)! } : {}),
      ...(text(api.baseUrl) ? { baseUrl: text(api.baseUrl)! } : {}),
    },
  };
}

/**
 * Resolve Judgment's activation. The environment wins over persisted state so a
 * single run can be pointed at a different account without editing a file.
 */
export function resolveJudgmentConfig(input: JudgmentConfigInput = {}): JudgmentConfig {
  const env = input.env ?? process.env;
  const file = readApiFile(input.agentDir ?? getAgentDir());
  if (file.reason) return { active: false, reason: file.reason };

  const api = file.api ?? {};
  const apiKey = text(env.TYPESAFE_API_KEY) ?? api.apiKey;
  if (!apiKey) {
    return {
      active: false,
      reason: "Judgment needs an API key in TYPESAFE_API_KEY or continual-learning.json",
    };
  }
  return {
    active: true,
    apiKey,
    model: text(env.TYPESAFE_MODEL) ?? api.model ?? DEFAULT_JUDGMENT_MODEL,
    baseUrl: text(env.TYPESAFE_BASE_URL) ?? api.baseUrl ?? DEFAULT_JUDGMENT_BASE_URL,
  };
}

// ── Authority ───────────────────────────────────────────────────────────

/**
 * Which surfaces a decision surface is allowed to decide, and on what terms.
 *
 * Promotion is a configuration change, never a code change. A threshold
 * compiled into the package would mean enabling it required a release, and
 * disabling it required a second one — a rollback cost high enough that nobody
 * would turn it on. Reading it from the same file as the credential keeps the
 * whole switch, and the kill, in one place.
 *
 * Only `proposals` is implemented. The other four surfaces are measured and
 * reported but expose no switch, because a switch that does nothing is worse
 * than no switch: it would read as "authoritative" while changing nothing.
 */
export type JudgmentSurface = "proposals" | "memory-operations" | "harness-operations" | "agents-operations" | "selector";
export type SurfaceMode = "shadow" | "authoritative";

/** Surfaces whose authoritative behavior is actually implemented. */
export const IMPLEMENTED_AUTHORITY: ReadonlySet<JudgmentSurface> = new Set<JudgmentSurface>(["proposals"]);

export const DEFAULT_DURABILITY_THRESHOLD = 0.5;
export const DEFAULT_GENERALITY_THRESHOLD = 1;
/** Generality is scored on four levels, so its threshold is an index. */
export const MAX_GENERALITY_LEVEL = 3;

export interface JudgmentAuthority {
  mode: SurfaceMode;
  /** A proposal is judged durable at or above this. */
  durability: number;
  /** A proposal is judged general at or above this. */
  generality: number;
}

export interface ResolvedJudgmentAuthority {
  /** Per surface. Unlisted surfaces are shadow. */
  surfaces: Record<string, SurfaceMode>;
  thresholds: { durability: number; generality: number };
  /** A configuration fault, reported rather than thrown. */
  invalid?: string;
}

/** Durability is a noul, so it is a probability. Generality is a score over
 *  four levels, so it is an index. Validating both against 0..1 was wrong: it
 *  made the one threshold that decides reusable-versus-noise unrepresentable. */
const DURABILITY_RANGE = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
const GENERALITY_RANGE = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= MAX_GENERALITY_LEVEL;

export function resolveJudgmentAuthority(
  input: JudgmentConfigInput = {},
): ResolvedJudgmentAuthority {
  const file = readApiFile(input.agentDir ?? getAgentDir());
  const base: ResolvedJudgmentAuthority = {
    surfaces: {},
    thresholds: { durability: DEFAULT_DURABILITY_THRESHOLD, generality: DEFAULT_GENERALITY_THRESHOLD },
  };
  if (file.reason) return base;
  const judgment = readJudgmentBlock(input.agentDir ?? getAgentDir());
  if (!judgment) return base;
  const { surfaces, thresholds, invalid } = judgment;
  return { ...base, surfaces, thresholds, ...(invalid ? { invalid } : {}) };
}

/**
 * Read the `judgment` block. Its own file read, because it is optional
 * configuration for a feature that may be entirely absent, and a malformed
 * block must never be attributed to the credential block that shares the file.
 */
function readJudgmentBlock(agentDir: string): ResolvedJudgmentAuthority | undefined {
  const file = judgmentConfigPath(agentDir);
  let stat: ReturnType<typeof lstatSync>;
  try {
    stat = lstatSync(file);
  } catch {
    return undefined;
  }
  if (stat.isSymbolicLink() || !stat.isFile() || stat.size > MAX_CONFIG_BYTES) return undefined;
  let value: unknown;
  try {
    value = JSON.parse(readFileSync(file, "utf-8"));
  } catch {
    return undefined;
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const block = (value as Record<string, unknown>).judgment;
  if (block === undefined) return undefined;
  const resolved: ResolvedJudgmentAuthority = {
    surfaces: {},
    thresholds: { durability: DEFAULT_DURABILITY_THRESHOLD, generality: DEFAULT_GENERALITY_THRESHOLD },
  };
  if (!block || typeof block !== "object" || Array.isArray(block)) {
    return { ...resolved, invalid: "continual-learning.json judgment must be an object" };
  }
  const source = block as Record<string, unknown>;
  const declared = source.surfaces;
  if (declared !== undefined) {
    if (!declared || typeof declared !== "object" || Array.isArray(declared)) {
      return { ...resolved, invalid: "continual-learning.json judgment.surfaces must be an object" };
    }
    for (const [name, mode] of Object.entries(declared as Record<string, unknown>)) {
      if (mode !== "shadow" && mode !== "authoritative") {
        return { ...resolved, invalid: `judgment.surfaces.${name} must be shadow or authoritative` };
      }
      // An unimplemented surface is refused rather than accepted silently.
      if (mode === "authoritative" && !IMPLEMENTED_AUTHORITY.has(name as JudgmentSurface)) {
        return { ...resolved, invalid: `judgment.surfaces.${name} is not implemented; its authoritative behavior would change nothing` };
      }
      resolved.surfaces[name] = mode;
    }
  }
  const declaredThresholds = source.thresholds;
  if (declaredThresholds !== undefined) {
    if (!declaredThresholds || typeof declaredThresholds !== "object" || Array.isArray(declaredThresholds)) {
      return { ...resolved, invalid: "continual-learning.json judgment.thresholds must be an object" };
    }
    for (const [name, bound] of Object.entries(declaredThresholds as Record<string, unknown>)) {
      if (name !== "durability" && name !== "generality") {
        return { ...resolved, invalid: `judgment.thresholds.${name} is not a known threshold` };
      }
      const acceptable = name === "durability" ? DURABILITY_RANGE : GENERALITY_RANGE;
      if (!acceptable(bound)) {
        const range = name === "durability" ? "a probability between 0 and 1" : `a level between 0 and ${MAX_GENERALITY_LEVEL}`;
        return { ...resolved, invalid: `judgment.thresholds.${name} must be ${range}` };
      }
      resolved.thresholds[name] = bound;
    }
  }
  return resolved;
}

/** Whether one surface may decide. Unknown surfaces are shadow. */
export function surfaceMode(authority: ResolvedJudgmentAuthority, surface: JudgmentSurface): SurfaceMode {
  return authority.surfaces[surface] === "authoritative" ? "authoritative" : "shadow";
}
