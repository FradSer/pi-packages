import * as crypto from "node:crypto";
import { realpathSync } from "node:fs";
import { execFileSync } from "node:child_process";
import * as path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";

export interface MemoryPaths {
  cwd: string;
  agentDir: string;
  scopeKey: string;
  harnessDir: string;
  publicDir?: string;
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

function resolvePublicMemoryDir(cwd: string, agentDir: string): string | undefined {
  if (cwd === agentDir) return undefined;
  try {
    const gitRoot = canonicalProjectCwd(execFileSync("git", ["-C", cwd, "rev-parse", "--show-toplevel"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim());
    return gitRoot === cwd ? path.join(cwd, ".memory") : undefined;
  } catch {
    return undefined;
  }
}

export function resolveMemoryPaths(cwd: string, agentDir = getAgentDir()): MemoryPaths {
  const canonicalCwd = canonicalProjectCwd(cwd);
  const scopeKey = projectScopeKey(canonicalCwd);
  const root = canonicalProjectCwd(agentDir);
  const harnessDir = path.join(root, "memory", scopeKey);
  return {
    cwd: canonicalCwd,
    agentDir: root,
    scopeKey,
    harnessDir,
    publicDir: resolvePublicMemoryDir(canonicalCwd, root),
    settingsFile: path.join(root, "memory", "settings.json"),
    lockFile: path.join(root, "memory", `${scopeKey}.lock`),
    runsDir: path.join(root, "memory", "runs", scopeKey),
    userInstructionsFile: path.join(root, "AGENTS.md"),
  };
}
