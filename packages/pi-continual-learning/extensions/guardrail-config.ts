/** Guardrails configuration discovery and loading. Layers resolve as
 * user (~/.pi/agent) < project (<cwd>/.pi), shared < .local, mirroring the
 * manifest/config pair conventions used across pi packages. JSON is used
 * instead of TOML to keep the package dependency-free. */

import fs from "node:fs";
import path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import type { PolicyLayer } from "./guardrail-types.ts";

export interface ConfigPaths {
  user: string;
  userLocal: string;
  project: string;
  projectLocal: string;
}

export function configPaths(cwd: string, agentDir?: string): ConfigPaths {
  // Shared with the absorbed memory surface: honors PI_CODING_AGENT_DIR.
  const base = agentDir ?? getAgentDir();
  return {
    user: path.join(base, "harness.json"),
    userLocal: path.join(base, "harness.local.json"),
    project: path.join(cwd, ".pi", "harness.json"),
    projectLocal: path.join(cwd, ".pi", "harness.local.json"),
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
  for (const [source, file] of [
    ["user", paths.user],
    ["user.local", paths.userLocal],
    ["project", paths.project],
    ["project.local", paths.projectLocal],
  ] as const) {
    const layer = readLayer(source, file);
    if (layer) layers.push(layer);
  }
  return layers;
}
