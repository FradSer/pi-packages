/** Guardrails and rules configuration discovery and loading. Layers resolve as
 * built-in < user shared (~/.pi/agent/harness.json) < project shared
 * (<cwd>/.pi/harness.json) < project personal (.local). JSON is used instead
 * of TOML to keep the package dependency-free. */

import fs from "node:fs";
import path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { DEFAULT_POLICIES, DEFAULT_RULES, mergeLayers } from "./guardrail-engine.ts";
import type { ResolvedHarnessConfig, RuleLayer } from "./guardrail-types.ts";

export interface ConfigPaths {
  user: string;
  project: string;
  projectLocal: string;
}

export interface ResolvedHarnessConfigWithPaths {
  config: ResolvedHarnessConfig;
  paths: ConfigPaths;
}

export function configPaths(cwd: string, agentDir?: string): ConfigPaths {
  const base = agentDir ?? getAgentDir();
  const projectDir = path.join(cwd, ".pi");
  return {
    user: path.join(base, "harness.json"),
    project: path.join(projectDir, "harness.json"),
    projectLocal: path.join(projectDir, "harness.local.json"),
  };
}

export function assertHarnessConfigContainers(value: unknown): asserts value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("harness config must be an object");
  }
  const config = value as Record<string, unknown>;
  if (Object.hasOwn(config, "rules") && !Array.isArray(config.rules)) {
    throw new Error("rules must be an array");
  }
  for (const name of ["policies", "disabled"] as const) {
    if (Object.hasOwn(config, name) && !Array.isArray(config[name])) {
      throw new Error(`${name} must be an array`);
    }
  }
  if (
    Object.hasOwn(config, "skillPrompts") &&
    (!config.skillPrompts || typeof config.skillPrompts !== "object" || Array.isArray(config.skillPrompts))
  ) {
    throw new Error("skillPrompts must be an object");
  }
}

/** Last structurally-valid parse per file, used only when a later read/parse of
 * the SAME file fails. A structurally-invalid parse never overwrites it. */
const lastValidLayerSnapshots = new Map<string, RuleLayer>();

/** True when the parsed root is an object and its `rules` field (if present)
 * is an array — the minimum for a trustworthy snapshot. Per-rule validity is
 * the engine's job, not this structural gate. */
function isStructurallyValid(parsed: unknown): parsed is Record<string, unknown> {
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return false;
  const root = parsed as Record<string, unknown>;
  if (root.rules !== undefined && !Array.isArray(root.rules)) return false;
  if (root.policies !== undefined && !Array.isArray(root.policies)) return false;
  if (root.disabled !== undefined && !Array.isArray(root.disabled)) return false;
  if (
    root.skillPrompts !== undefined &&
    (!root.skillPrompts || typeof root.skillPrompts !== "object" || Array.isArray(root.skillPrompts))
  ) {
    return false;
  }
  return true;
}

function staleFallback(source: string, filePath: string, reason: string): RuleLayer {
  const snapshot = lastValidLayerSnapshots.get(filePath);
  return {
    source,
    stale: true,
    ...(snapshot
      ? { rules: snapshot.rules, policies: snapshot.policies, skillPrompts: snapshot.skillPrompts, disabled: snapshot.disabled }
      : {}),
    errors: [`${reason}${snapshot ? " (using previous valid snapshot)" : " (no previous valid snapshot; layer treated as empty)"}`],
  };
}

function readLayer(source: string, filePath: string): RuleLayer | undefined {
  let raw: string;
  try {
    raw = fs.readFileSync(filePath, "utf8");
  } catch (err) {
    // Only a missing file means "layer absent". Any other read failure is an
    // explicit diagnostic, never silently treated as absence.
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    return staleFallback(source, filePath, `could not read harness file: ${(err as Error).message}`);
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    return staleFallback(source, filePath, `invalid JSON: ${(err as Error).message}`);
  }

  if (!isStructurallyValid(parsed)) {
    return staleFallback(source, filePath, "harness config root or a top-level container is malformed");
  }

  const layer: RuleLayer = { source };
  if (Array.isArray(parsed.rules)) layer.rules = parsed.rules as Array<Record<string, unknown>>;
  if (Array.isArray(parsed.policies)) layer.policies = parsed.policies as Array<Record<string, unknown>>;
  if (parsed.skillPrompts && typeof parsed.skillPrompts === "object" && !Array.isArray(parsed.skillPrompts)) {
    layer.skillPrompts = parsed.skillPrompts as Record<string, unknown>;
  }
  if (Array.isArray(parsed.disabled)) layer.disabled = parsed.disabled.map(String);

  if (
    !Array.isArray(parsed.rules) &&
    (parsed.policies !== undefined || parsed.skillPrompts !== undefined || parsed.disabled !== undefined)
  ) {
    layer.errors = [
      'legacy harness format detected ("policies"/"disabled"/"skillPrompts"); migrate to the "rules" array for the flat-rule behavior',
    ];
  }

  // Structurally valid: safe to remember as the fallback snapshot.
  lastValidLayerSnapshots.set(filePath, { ...layer });
  return layer;
}

/** Load every existing layer in innermost-last order. */
export function loadLayers(cwd: string, agentDir?: string): RuleLayer[] {
  const paths = configPaths(cwd, agentDir);
  const layers: RuleLayer[] = [];
  const userLayer = readLayer("user", paths.user);
  if (userLayer) layers.push(userLayer);
  const projLayer = readLayer("project", paths.project);
  if (projLayer) layers.push(projLayer);
  const projLocalLayer = readLayer("project.local", paths.projectLocal);
  if (projLocalLayer) layers.push(projLocalLayer);
  return layers;
}

let cached: { key: string; value: ResolvedHarnessConfigWithPaths } | undefined;

function defaultLayer(): RuleLayer {
  return {
    source: "built-in defaults",
    rules: DEFAULT_RULES as unknown as Array<Record<string, unknown>>,
    policies: DEFAULT_POLICIES as unknown as Array<Record<string, unknown>>,
  };
}

/** Resolve the same immutable config view for every harness surface. The cache
 * key includes every layer's mtime so a lower-layer edit is observed even when
 * an inner layer still masks it. */
export function resolveHarnessConfig(
  cwd: string,
  agentDir?: string,
  availableSkills?: ReadonlySet<string>,
): ResolvedHarnessConfigWithPaths {
  const paths = configPaths(cwd, agentDir);
  let cacheKey = JSON.stringify(availableSkills ? [...availableSkills].sort() : null);
  for (const file of Object.values(paths)) {
    try {
      cacheKey += `${file}:${fs.statSync(file).mtimeMs};`;
    } catch {
      cacheKey += `${file}:-;`;
    }
  }
  if (cached && cached.key === cacheKey) return cached.value;
  const config = mergeLayers([defaultLayer(), ...loadLayers(cwd, agentDir)], availableSkills);
  cached = { key: cacheKey, value: { config, paths } };
  return cached.value;
}
