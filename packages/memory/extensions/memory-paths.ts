import * as crypto from "node:crypto";
import { realpathSync } from "node:fs";
import * as path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";

export interface MemoryPaths {
  cwd: string;
  agentDir: string;
  scopeKey: string;
  harnessDir: string;
  publicDir: string;
  settingsFile: string;
  lockFile: string;
  runsDir: string;
  userInstructionsFile: string;
}

export function canonicalProjectCwd(cwd: string): string {
  const resolved = path.resolve(cwd);
  try {
    return realpathSync(resolved);
  } catch {
    return resolved;
  }
}

/** A stable, non-reversible project key that cannot collide on path punctuation. */
export function projectScopeKey(cwd: string): string {
  return crypto.createHash("sha256").update(canonicalProjectCwd(cwd)).digest("hex");
}

export function resolveMemoryPaths(cwd: string, agentDir = getAgentDir()): MemoryPaths {
  const canonicalCwd = canonicalProjectCwd(cwd);
  const scopeKey = projectScopeKey(canonicalCwd);
  const root = path.resolve(agentDir);
  const harnessDir = path.join(root, "memory", scopeKey);
  return {
    cwd: canonicalCwd,
    agentDir: root,
    scopeKey,
    harnessDir,
    publicDir: path.join(canonicalCwd, ".memory"),
    settingsFile: path.join(root, "memory", "settings.json"),
    lockFile: path.join(root, "memory", `${scopeKey}.lock`),
    runsDir: path.join(root, "memory", "runs", scopeKey),
    userInstructionsFile: path.join(root, "AGENTS.md"),
  };
}
