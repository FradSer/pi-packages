import { realpathSync, lstatSync, mkdirSync, openSync, readSync, writeFileSync, closeSync, fstatSync, fsyncSync, constants } from "node:fs";
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

/** A readable legacy key is not an identity: punctuation can collide. Bind
 * it to the canonical path before any scoped data is read. The marker lives
 * outside entry roots, whose regular Markdown-only contract is unchanged. */
export function assertProjectScopeOwner(cwd: string, agentDir = getAgentDir()): void {
  const canonical = canonicalProjectCwd(cwd);
  const root = canonicalProjectCwd(agentDir);
  mkdirSync(root, { recursive: true, mode: 0o700 });
  const directory = path.join(root, "memory", "scopes");
  // Agent root is trusted configuration; newly introduced child directories
  // may never redirect ownership checks through symbolic links.
  for (const child of [path.join(root, "memory"), directory]) {
    try { mkdirSync(child, { mode: 0o700 }); }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error; }
    const stat = lstatSync(child);
    if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error(`Unsafe project scope registry: ${child}`);
  }
  const marker = path.join(directory, `${escapedProjectPath(canonical)}.json`);
  let handle: number | undefined;
  try {
    handle = openSync(marker, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
    writeFileSync(handle, JSON.stringify({ version: 1, cwd: canonical }));
    fsyncSync(handle); closeSync(handle); handle = undefined;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
  } finally { if (handle !== undefined) closeSync(handle); }
  const stat = lstatSync(marker);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 16_384) throw new Error(`Unsafe project scope binding: ${marker}`);
  handle = openSync(marker, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const opened = fstatSync(handle);
    if (!opened.isFile() || opened.size > 16_384 || opened.dev !== stat.dev || opened.ino !== stat.ino) throw new Error(`Project scope binding changed: ${marker}`);
    const bytes = Buffer.alloc(opened.size);
    const count = readSync(handle, bytes, 0, bytes.length, 0);
    const after = fstatSync(handle);
    const named = lstatSync(marker);
    if (count !== bytes.length || after.size !== opened.size || after.mtimeMs !== opened.mtimeMs || after.ctimeMs !== opened.ctimeMs || named.dev !== opened.dev || named.ino !== opened.ino || named.isSymbolicLink()) throw new Error(`Project scope binding changed: ${marker}`);
    const binding: unknown = JSON.parse(bytes.toString("utf8"));
    if (!binding || typeof binding !== "object" || !("version" in binding) || binding.version !== 1 || !("cwd" in binding) || binding.cwd !== canonical) {
      throw new Error(`Project scope collision: ${canonical} does not own ${marker}; existing data was preserved`);
    }
  } finally { closeSync(handle); }
}

export function resolveMemoryPaths(cwd: string, agentDir = getAgentDir()): MemoryPaths {
  const canonicalCwd = canonicalProjectCwd(cwd);
  const scopeKey = projectScopeKey(canonicalCwd);
  const root = canonicalProjectCwd(agentDir);
  assertProjectScopeOwner(canonicalCwd, root);
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
