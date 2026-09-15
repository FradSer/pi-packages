/** Guardrails configuration discovery and loading. Layers resolve as
 * user shared (~/.pi/agent/harness.json) < project shared
 * (<cwd>/.pi/harness.json) < project personal (.local). JSON is used instead
 * of TOML to keep the package dependency-free. */

import fs from "node:fs";
import path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { DEFAULT_POLICIES, mergeLayers } from "./guardrail-engine.ts";
import type { PolicyLayer } from "./guardrail-types.ts";
import type { ResolvedConfig } from "./guardrail-types.ts";

export interface ConfigPaths {
  user: string;
  project: string;
  projectLocal: string;
}

export interface ResolvedHarnessConfig {
  config: ResolvedConfig;
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

function readLayer(source: string, filePath: string): PolicyLayer | undefined {
  let raw: string;
  try {
    raw = fs.readFileSync(filePath, "utf8");
  } catch {
    return undefined; // missing file = layer absent, not an error
  }
  const layer: PolicyLayer = { source };
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (Array.isArray(parsed.policies)) {
      layer.policies = parsed.policies as Array<Record<string, unknown>>;
    } else if (parsed.policies !== undefined) {
      layer.errors = [`"policies" must be an array`];
    }
    if (parsed.skillPrompts !== undefined) {
      if (parsed.skillPrompts && typeof parsed.skillPrompts === "object" && !Array.isArray(parsed.skillPrompts)) {
        layer.skillPrompts = parsed.skillPrompts as Record<string, unknown>;
      } else {
        layer.errors = [...(layer.errors ?? []), `"skillPrompts" must be an object`];
      }
    }
    if (Array.isArray(parsed.disabled)) {
      layer.disabled = parsed.disabled.map(String);
    }
    return layer;
  } catch (err) {
    return { source, errors: [`invalid JSON: ${(err as Error).message}`] };
  }
}

/** Load every existing layer in innermost-last order. */
export function loadLayers(cwd: string, agentDir?: string): PolicyLayer[] {
  const paths = configPaths(cwd, agentDir);
  const layers: PolicyLayer[] = [];

  const userLayer = readLayer("user", paths.user);
  if (userLayer) layers.push(userLayer);

  const projLayer = readLayer("project", paths.project);
  if (projLayer) layers.push(projLayer);

  const projLocalLayer = readLayer("project.local", paths.projectLocal);
  if (projLocalLayer) layers.push(projLocalLayer);

  return layers;
}

let cached: { key: string; value: ResolvedHarnessConfig } | undefined;

function defaultLayer(): PolicyLayer {
  return {
    source: "built-in defaults",
    policies: DEFAULT_POLICIES as unknown as Array<Record<string, unknown>>,
  };
}

/** Resolve the same immutable config view for every harness surface. The
 * cache key includes every layer's mtime so a lower layer edit is observed
 * even when an inner layer still masks it. */
export function resolveHarnessConfig(cwd: string, agentDir?: string): ResolvedHarnessConfig {
  const paths = configPaths(cwd, agentDir);
  let cacheKey = "";
  for (const file of Object.values(paths)) {
    try {
      cacheKey += `${file}:${fs.statSync(file).mtimeMs};`;
    } catch {
      cacheKey += `${file}:-;`;
    }
  }
  if (cached && cached.key === cacheKey) return cached.value;
  const config = mergeLayers([defaultLayer(), ...loadLayers(cwd, agentDir)]);
  cached = { key: cacheKey, value: { config, paths } };
  return cached.value;
}
