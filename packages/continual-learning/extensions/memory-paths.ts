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

/** Readable flat identity shared by private Memory, locks, and run directories. */
export function projectScopeKey(cwd: string): string {
  return escapedProjectPath(cwd);
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

const PRIVATE_DIR_MAX_BYTES = 240;

export function escapedProjectPath(cwd: string): string {
  const canonical = canonicalProjectCwd(cwd);
  const raw = canonical.replace(/^[/\\]/, "").replace(/[/\\:]/g, "-");
  const safePath = `--${raw}--`;
  if (Buffer.byteLength(safePath, "utf8") > PRIVATE_DIR_MAX_BYTES) {
    throw new Error(`Readable project scope exceeds ${PRIVATE_DIR_MAX_BYTES} bytes; use a shorter canonical project path`);
  }
  return safePath;
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
    lockFile: path.join(root, "memory", "locks", `${scopeKey}.lock`),
    runsDir: path.join(root, "memory", "runs", scopeKey),
    userInstructionsFile: path.join(root, "AGENTS.md"),
  };
}
