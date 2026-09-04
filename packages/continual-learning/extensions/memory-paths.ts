import * as crypto from "node:crypto";
import { realpathSync } from "node:fs";
import { execFileSync } from "node:child_process";
import * as path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";

export interface MemoryPaths {
  cwd: string;
  agentDir: string;
  scopeKey: string;
  userSharedDir: string;
  projectSharedDir?: string;
  projectPersonalDir?: string;
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

function resolveProjectRoot(cwd: string, agentDir: string): string | undefined {
  if (cwd === agentDir) return undefined;
  try {
    const gitRoot = canonicalProjectCwd(execFileSync("git", ["-C", cwd, "rev-parse", "--show-toplevel"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim());
    return gitRoot === cwd ? gitRoot : undefined;
  } catch {
    return undefined;
  }
}

export function resolveMemoryPaths(cwd: string, agentDir = getAgentDir()): MemoryPaths {
  const canonicalCwd = canonicalProjectCwd(cwd);
  const scopeKey = projectScopeKey(canonicalCwd);
  const root = canonicalProjectCwd(agentDir);
  const userSharedDir = path.join(root, "memory");
  const projectRoot = resolveProjectRoot(canonicalCwd, root);
  const projectSharedDir = projectRoot ? path.join(projectRoot, ".memory") : undefined;
  const projectPersonalDir = projectRoot ? path.join(projectRoot, ".memory.local") : undefined;
  return {
    cwd: canonicalCwd,
    agentDir: root,
    scopeKey,
    userSharedDir,
    projectSharedDir,
    projectPersonalDir,
    settingsFile: path.join(root, "memory", "settings.json"),
    lockFile: path.join(root, "memory", `${scopeKey}.lock`),
    runsDir: path.join(root, "memory", "runs", scopeKey),
    userInstructionsFile: path.join(root, "AGENTS.md"),
  };
}
