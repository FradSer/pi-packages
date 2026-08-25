/** Guardrails configuration discovery and loading. Layers resolve as
 * user (~/.pi/agent) < project (<cwd>/.pi), shared < .local, mirroring the
 * manifest/config pair conventions used across pi packages. JSON is used
 * instead of TOML to keep the package dependency-free. */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import type { PolicyLayer } from "./guardrail-types.ts";

export interface ConfigPaths {
  user: string;
  userLocal: string;
  project: string;
  projectLocal: string;
}

export function configPaths(cwd: string, agentDir?: string): ConfigPaths {
  const base = agentDir ?? path.join(os.homedir(), ".pi", "agent");
  return {
    user: path.join(base, "guardrails.json"),
    userLocal: path.join(base, "guardrails.local.json"),
    project: path.join(cwd, ".pi", "guardrails.json"),
    projectLocal: path.join(cwd, ".pi", "guardrails.local.json"),
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
