/** Private durable data homes. Scratch is an ordinary directory, never a
 * project checkout: children always launch in the original project cwd.
 * Provisioning is authorized by the caller's resolved disk identity and does
 * not synthesize an agent.md, run Git, preserve, release or remove output.
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { createExclusiveJsonFile, writeJsonAtomic } from "@fradser/pi-kit";

export interface AgentWorkspace {
  cwd: string;
  workspacePath: string;
  sessionDir: string;
  /** Whether the ordinary scratch directory existed before this provision. */
  reused: boolean;
}

export interface AgentHomeState {
  createdAt: string;
  lastProject: string;
  memoryEntryCount: number;
}

/** Identity names must map to a single unambiguous canonical directory. */
export function assertAgentName(name: string): void {
  if (!/^[a-z][a-z0-9._-]{0,63}$/i.test(name) || name.toLowerCase().endsWith(".local")) {
    throw new Error(`Invalid agent name "${name}". Use letters, digits, dots, dashes, underscores; .local is reserved for project overrides.`);
  }
}

/** Reject a lexical escape, symlink or non-directory ancestor beneath an
 * explicitly configured root. System aliases above the root (e.g. /var on
 * macOS) are not data symlinks. The root itself must not be a symlink.
 * Read-only: missing path components are permitted, never created.
 */
export function assertAgentStoragePath(root: string, candidate: string): void {
  const base = path.resolve(root);
  const target = path.resolve(candidate);
  const relative = path.relative(base, target);
  if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error(`Refusing a path outside the Agent storage root: ${candidate}`);
  }
  const parts = relative ? relative.split(path.sep) : [];
  let current = base;
  for (let index = 0; index <= parts.length; index++) {
    let stat: fs.Stats;
    try { stat = fs.lstatSync(current); } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
      throw error;
    }
    if (stat.isSymbolicLink()) throw new Error(`Refusing a symlink in Agent storage: ${current}`);
    if (index < parts.length && !stat.isDirectory()) throw new Error(`Expected an Agent storage directory: ${current}`);
    if (index < parts.length) current = path.join(current, parts[index]);
  }
}

/** Pi recent-session discovery follows file links. Reject them (including
 * hard links) before provisioning and again at the shared spawn boundary. */
export function assertPrivateSessionFiles(sessionDir: string): boolean {
  const root = path.resolve(sessionDir);
  assertAgentStoragePath(root, root);
  let entries: fs.Dirent[];
  try { entries = fs.readdirSync(root, { withFileTypes: true }); } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
  let found = false;
  for (const entry of entries) {
    if (!entry.name.endsWith(".jsonl")) continue;
    const file = path.join(root, entry.name);
    assertAgentStoragePath(root, file);
    const stat = fs.lstatSync(file);
    if (!stat.isFile() || stat.nlink !== 1) throw new Error(`Refusing linked or non-regular private history: ${file}`);
    const descriptor = fs.openSync(file, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0));
    try {
      const opened = fs.fstatSync(descriptor);
      if (!opened.isFile() || opened.nlink !== 1 || opened.dev !== stat.dev || opened.ino !== stat.ino) {
        throw new Error(`Private history changed during validation: ${file}`);
      }
    } finally { fs.closeSync(descriptor); }
    found = true;
  }
  return found;
}

export function agentHomePath(agentName: string): string {
  assertAgentName(agentName);
  return path.join(path.resolve(getAgentDir()), "agents", agentName);
}

export function agentWorkspacePath(agentName: string): string {
  return path.join(agentHomePath(agentName), "workspace");
}

function parentSessionSlug(parentSessionId: string): string {
  if (typeof parentSessionId !== "string" || parentSessionId.trim().length === 0) {
    throw new Error("Parent session ID must be a non-empty string.");
  }
  if (Buffer.byteLength(parentSessionId, "utf8") > 4096) {
    throw new Error("Parent session ID exceeds the 4 KiB limit.");
  }
  return `parent-${createHash("sha256").update(parentSessionId, "utf8").digest("hex")}`;
}

export function agentSessionPath(agentName: string, projectCwd: string, parentSessionId?: string): string {
  const projectPath = path.join(agentHomePath(agentName), "projects", projectSlug(projectCwd));
  if (parentSessionId === undefined) return path.join(projectPath, "session");
  return path.join(projectPath, "parents", parentSessionSlug(parentSessionId), "session");
}

/** Kept byte-for-byte equivalent to the legacy slug algorithm so private
 * histories keep their existing stable project keys during migration.
 */
export function projectSlug(cwd: string): string {
  const resolved = safeRealpath(cwd);
  const readable = resolved.replace(/^[/\\]/, "").replace(/[/\\:]+/g, "-")
    .replace(/[^A-Za-z0-9._-]+/g, "-").slice(-120);
  const digest = createHash("sha256").update(resolved).digest("hex").slice(0, 12);
  return `${readable || "project"}-${digest}`;
}

function safeRealpath(candidate: string): string {
  try { return fs.realpathSync(candidate); } catch { return path.resolve(candidate); }
}

function existingDirectory(candidate: string): boolean {
  try {
    if (!fs.lstatSync(candidate).isDirectory()) throw new Error(`Expected an Agent storage directory: ${candidate}`);
    return true;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
}

export type AgentMemoryState = AgentHomeState & Record<string, unknown>;

function isMemoryState(value: unknown): value is AgentMemoryState {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    && "createdAt" in value && typeof value.createdAt === "string" && Number.isFinite(Date.parse(value.createdAt))
    && "lastProject" in value && typeof value.lastProject === "string"
    && "memoryEntryCount" in value && typeof value.memoryEntryCount === "number"
    && Number.isSafeInteger(value.memoryEntryCount) && value.memoryEntryCount >= 0;
}

/** Read existing package-owned data, retaining unknown fields. No identity
 * declaration or missing state is created. Malformed/symlinked data fails. */
export function readAgentHomeState(agentName: string): AgentMemoryState | undefined {
  const file = path.join(agentHomePath(agentName), "state.json");
  assertAgentStoragePath(path.resolve(getAgentDir()), file);
  let raw: string;
  try {
    const stat = fs.lstatSync(file);
    if (!stat.isFile() || stat.nlink !== 1) throw new Error(`Refusing linked or non-regular Agent state file: ${file}`);
    raw = fs.readFileSync(file, "utf-8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
  let value: unknown;
  try { value = JSON.parse(raw); } catch { throw new Error(`Malformed Agent state: ${file}`); }
  if (!isMemoryState(value) || ("name" in value && value.name !== agentName)) {
    throw new Error(`Malformed Agent state: ${file}`);
  }
  return value;
}

/** Shared synchronous read-modify-write seam for provisioning and child Memory.
 * Every writer must use state.json.lock. A busy/crashed writer is not guessed
 * dead: bounded contention fails explicitly and its lock remains untouched. */
export function updateExistingAgentHomeState(
  agentName: string,
  update: (latest: AgentMemoryState) => AgentMemoryState,
): AgentMemoryState | undefined {
  const home = agentHomePath(agentName);
  const file = path.join(home, "state.json");
  if (!fs.existsSync(file)) return undefined;
  readAgentHomeState(agentName); // Refuse bad data before acquiring a lock.
  const lock = `${file}.lock`;
  assertAgentStoragePath(path.resolve(getAgentDir()), lock);
  const deadline = Date.now() + 1000;
  const pause = new Int32Array(new SharedArrayBuffer(4));
  let fd: number;
  for (;;) {
    try {
      fd = fs.openSync(lock, "wx", 0o600);
      break;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      if (Date.now() >= deadline) throw new Error(`Agent state update refused: lock is occupied at ${lock}.`);
      Atomics.wait(pause, 0, 0, 10);
    }
  }
  const ownedLock = fs.fstatSync(fd);
  const tmp = `${file}.${process.pid}.tmp`; // pi-kit's atomic replacement path.
  let createdTmp = false;
  try {
    const latest = readAgentHomeState(agentName);
    if (!latest) return undefined;
    const next = { ...latest, ...update({ ...latest }), createdAt: latest.createdAt };
    if (!isMemoryState(next)) throw new Error(`Malformed Agent state update: ${file}`);
    assertAgentStoragePath(path.resolve(getAgentDir()), tmp);
    // Exclusive reservation avoids deleting or following someone else's temp.
    fs.closeSync(fs.openSync(tmp, "wx", 0o600));
    createdTmp = true;
    writeJsonAtomic(file, next);
    return next;
  } finally {
    if (createdTmp) fs.rmSync(tmp, { force: true });
    fs.closeSync(fd);
    const current = fs.lstatSync(lock);
    if (current.dev === ownedLock.dev && current.ino === ownedLock.ino) fs.unlinkSync(lock);
  }
}

function memoryEntryCount(memoryPath: string): number {
  if (!fs.existsSync(memoryPath)) return 0;
  return fs.readdirSync(memoryPath, { withFileTypes: true })
    .filter(entry => {
      if (!entry.isFile() || entry.name === "MEMORY.md" || !entry.name.endsWith(".md")) return false;
      try { return fs.lstatSync(path.join(memoryPath, entry.name)).nlink === 1; } catch { return false; }
    }).length;
}

export function ensureAgentWorkspace(input: { agentName: string; cwd: string; parentSessionId?: string }): AgentWorkspace {
  const root = path.resolve(getAgentDir());
  const home = agentHomePath(input.agentName);
  const cwd = path.resolve(input.cwd);
  const workspacePath = agentWorkspacePath(input.agentName);
  const sessionDir = agentSessionPath(input.agentName, cwd, input.parentSessionId);
  const memoryPath = path.join(home, "memory");
  const indexFile = path.join(memoryPath, "MEMORY.md");
  const stateFile = path.join(home, "state.json");
  const directories = [home, memoryPath, path.join(memoryPath, "proposals"), workspacePath, sessionDir];
  // Preflight all destinations before creating any directory or replacing state.
  for (const directory of directories) {
    assertAgentStoragePath(root, directory);
    existingDirectory(directory);
  }
  for (const file of [indexFile, stateFile, `${stateFile}.${process.pid}.tmp`]) assertAgentStoragePath(root, file);
  if (fs.existsSync(indexFile)) {
    const indexStat = fs.lstatSync(indexFile);
    if (!indexStat.isFile() || indexStat.nlink !== 1) throw new Error(`Refusing linked or non-regular Memory index file: ${indexFile}`);
  }
  // .git may be a linked-worktree file, a directory, or a dangling symlink.
  try {
    fs.lstatSync(path.join(workspacePath, ".git"));
    throw new Error(`Refusing a Git workspace as ordinary scratch: ${workspacePath}; manual migration is required.`);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  assertPrivateSessionFiles(sessionDir);
  let state = readAgentHomeState(input.agentName);
  const reused = existingDirectory(workspacePath);
  const count = memoryEntryCount(memoryPath);
  for (const directory of directories) fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  assertAgentStoragePath(root, indexFile);
  try {
    fs.writeFileSync(indexFile, ["# Agent Memory Index", "", "Capability-focused methods, judgment criteria, and operating patterns.", ""].join("\n"),
      { encoding: "utf8", mode: 0o600, flag: "wx" });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
  }
  if (!state) {
    // Exclusive atomic initialization makes creation time agree across parent
    // processes; later state replacements use pi-kit's tmp+rename primitive.
    createExclusiveJsonFile(home, "state", { createdAt: new Date().toISOString(), lastProject: cwd, memoryEntryCount: count });
    assertAgentStoragePath(root, stateFile);
    state = readAgentHomeState(input.agentName);
    if (!state) throw new Error(`Agent state initialization was not observed: ${stateFile}`);
  }
  // Memory appends and provisioning share the same latest-state lock so an
  // earlier snapshot cannot erase fields or override another writer's count.
  updateExistingAgentHomeState(input.agentName, latest => ({
    ...latest, lastProject: cwd, memoryEntryCount: memoryEntryCount(memoryPath),
  }));
  return { cwd, workspacePath, sessionDir, reused };
}
