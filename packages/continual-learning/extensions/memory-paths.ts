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

/**
 * `git rev-parse` spawns a process (measured ~6 ms) and memory paths are resolved
 * on every user turn, so the probe is memoized per canonical project path for a
 * bounded window. The window keeps a repository created mid-session visible
 * without paying a subprocess spawn on every turn.
 */
const GIT_ROOT_CACHE_LIMIT = 64;
const GIT_ROOT_TTL_MS = 60_000;
const gitRootCache = new Map<string, { root: string | undefined; checkedAt: number }>();

function gitRootFor(cwd: string): string | undefined {
  const now = Date.now();
  const cached = gitRootCache.get(cwd);
  if (cached && now - cached.checkedAt < GIT_ROOT_TTL_MS) return cached.root;
  let root: string | undefined;
  try {
    root = canonicalProjectCwd(execFileSync("git", ["-C", cwd, "rev-parse", "--show-toplevel"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim());
  } catch {
    root = undefined;
  }
  if (!gitRootCache.has(cwd) && gitRootCache.size >= GIT_ROOT_CACHE_LIMIT) {
    const oldest = gitRootCache.keys().next();
    if (!oldest.done) gitRootCache.delete(oldest.value);
  }
  gitRootCache.set(cwd, { root, checkedAt: now });
  return root;
}

function resolvePublicMemoryDir(cwd: string, agentDir: string): string | undefined {
  if (cwd === agentDir) return undefined;
  return gitRootFor(cwd) === cwd ? path.join(cwd, ".memory") : undefined;
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
