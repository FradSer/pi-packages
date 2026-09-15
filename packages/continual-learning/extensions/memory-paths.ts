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

/** Stable opaque key for operational locks and run directories only. */
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

const PRIVATE_DIR_MAX_BYTES = 240;

export function escapedProjectPath(cwd: string): string {
  const readable = canonicalProjectCwd(cwd)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[\\/\s]+/g, "-")
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .replace(/-+/g, "-");
  const name = readable || "project";
  if (Buffer.byteLength(name, "utf8") > PRIVATE_DIR_MAX_BYTES) {
    throw new Error(`Escaped project path exceeds the ${PRIVATE_DIR_MAX_BYTES}-byte portable component limit`);
  }
  return name;
}

export function resolveMemoryPaths(cwd: string, agentDir = getAgentDir()): MemoryPaths {
  const canonicalCwd = canonicalProjectCwd(cwd);
  const scopeKey = projectScopeKey(canonicalCwd);
  const root = canonicalProjectCwd(agentDir);
  const harnessDir = path.join(root, "memory", escapedProjectPath(canonicalCwd));
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
