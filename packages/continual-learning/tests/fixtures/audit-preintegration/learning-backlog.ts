/** Private references to skipped tasks. Inspection never replays model calls. */
import fs from "node:fs";
import path from "node:path";
import { randomBytes } from "node:crypto";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { canonicalProjectCwd, resolveMemoryPaths } from "./memory-paths";

export const MAX_BACKLOG_BYTES = 4 * 1024 * 1024;
const MAX_BACKLOG_RECORD_BYTES = 4_096;
export type BacklogReason = "auto-memory-off" | "screen-found-nothing" | "no-session-reference";
export interface BacklogEntry {
  version: 1;
  sessionFile: string;
  from: number;
  to: number;
  digest: string;
  reason: BacklogReason;
  queuedAt: string;
  /** Absent in older records; bind those only through a session header. */
  scopeKey?: string;
}

export function backlogFile(cwd: string, agentDir = getAgentDir()): string {
  return path.join(resolveMemoryPaths(cwd, agentDir).agentDir, "learning", "backlog.jsonl");
}

function missing(error: unknown): boolean {
  return Boolean(error && typeof error === "object" && "code" in error && error.code === "ENOENT");
}

function safeStorage(file: string, root: string, create = false): void {
  const relative = path.relative(root, file);
  if (!relative || relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) throw new Error("Backlog path escapes its root");
  if (create) fs.mkdirSync(root, { recursive: true, mode: 0o700 });
  let current = root;
  for (const part of ["", ...relative.split(path.sep)]) {
    if (part) current = path.join(current, part);
    const target = current === file;
    try {
      const stat = fs.lstatSync(current);
      if (stat.isSymbolicLink() || (target ? !stat.isFile() : !stat.isDirectory())) throw new Error("Backlog path is not a regular file or directory");
    } catch (error) {
      if (!missing(error)) throw error;
      if (create && !target) fs.mkdirSync(current, { mode: 0o700 });
    }
  }
}

function readBounded(file: string, limit: number): string {
  const fd = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
  try {
    const before = fs.fstatSync(fd);
    if (!before.isFile() || before.size > limit) throw new Error("Backlog file exceeds its regular-file or byte limit");
    const bytes = Buffer.alloc(before.size);
    let offset = 0;
    while (offset < bytes.length) {
      const count = fs.readSync(fd, bytes, offset, bytes.length - offset, offset);
      if (!count) break;
      offset += count;
    }
    const after = fs.lstatSync(file);
    if (offset !== before.size || after.isSymbolicLink() || before.dev !== after.dev || before.ino !== after.ino || before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ctimeMs !== after.ctimeMs) throw new Error("Backlog changed during read");
    return bytes.toString("utf8");
  } finally { fs.closeSync(fd); }
}

/** Serialize the shared capacity check and all scoped cursor updates. */
function withBacklogLock<T>(cwd: string, agentDir: string | undefined, operation: () => T): T {
  const paths = resolveMemoryPaths(cwd, agentDir);
  const file = path.join(paths.agentDir, "learning", "backlog.lock");
  safeStorage(file, paths.agentDir, true);
  let fd: number;
  try { fd = fs.openSync(file, "wx", 0o600); }
  catch (error) {
    if (!error || typeof error !== "object" || !("code" in error) || error.code !== "EEXIST") throw error;
    const stale = fs.lstatSync(file);
    const owner: unknown = JSON.parse(readBounded(file, MAX_BACKLOG_RECORD_BYTES));
    if (!owner || typeof owner !== "object" || !("pid" in owner) || !Number.isSafeInteger(owner.pid) || Number(owner.pid) <= 0) throw new Error("Invalid backlog lock");
    try { process.kill(Number(owner.pid), 0); throw new Error("Backlog is busy"); }
    catch (ownerError) {
      if (!ownerError || typeof ownerError !== "object" || !("code" in ownerError) || ownerError.code !== "ESRCH") throw ownerError;
    }
    // Only one stale-lock reclaimer may compare and remove the predecessor.
    // A normal acquirer can win the new lock after removal; never delete it.
    const recoveryFile = `${file}.reclaim`;
    safeStorage(recoveryFile, paths.agentDir);
    const recovery = fs.openSync(recoveryFile, "wx", 0o600);
    const recoveryIdentity = fs.fstatSync(recovery);
    try {
      const current = fs.lstatSync(file);
      if (current.dev !== stale.dev || current.ino !== stale.ino || current.mtimeMs !== stale.mtimeMs || current.ctimeMs !== stale.ctimeMs) throw new Error("Backlog lock changed");
      fs.unlinkSync(file);
      fd = fs.openSync(file, "wx", 0o600);
    } finally {
      fs.closeSync(recovery);
      safeStorage(recoveryFile, paths.agentDir);
      const current = fs.lstatSync(recoveryFile);
      if (current.dev === recoveryIdentity.dev && current.ino === recoveryIdentity.ino) fs.unlinkSync(recoveryFile);
    }
  }
  const identity = fs.fstatSync(fd);
  try {
    fs.writeFileSync(fd, JSON.stringify({ pid: process.pid }));
    return operation();
  } finally {
    fs.closeSync(fd);
    safeStorage(file, paths.agentDir);
    const current = fs.lstatSync(file);
    if (current.dev === identity.dev && current.ino === identity.ino) fs.unlinkSync(file);
  }
}

function validEntry(value: unknown): value is BacklogEntry {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const entry = value as BacklogEntry;
  return entry.version === 1 && typeof entry.sessionFile === "string" && path.isAbsolute(entry.sessionFile)
    && Number.isSafeInteger(entry.from) && entry.from >= 0 && Number.isSafeInteger(entry.to) && entry.to >= entry.from
    && typeof entry.digest === "string" && entry.digest.length > 0 && entry.digest.length <= 128
    && ["auto-memory-off", "screen-found-nothing", "no-session-reference"].includes(entry.reason)
    && typeof entry.queuedAt === "string" && Number.isFinite(Date.parse(entry.queuedAt))
    && (entry.scopeKey === undefined || (typeof entry.scopeKey === "string" && Buffer.byteLength(entry.scopeKey) <= 240))
    && Object.keys(entry).every(key => ["version", "sessionFile", "from", "to", "digest", "reason", "queuedAt", "scopeKey"].includes(key));
}

/** pi-kit appendJsonlLine has no descriptor-bound no-follow or corpus cap. */
export function enqueueBacklog(input: {
  cwd: string; sessionFile?: string; from: number; to: number; digest: string; reason: BacklogReason; agentDir?: string;
}): boolean {
  if (!input.sessionFile) return false;
  try { return withBacklogLock(input.cwd, input.agentDir, () => appendBacklog(input)); }
  catch { return false; }
}

function appendBacklog(input: {
  cwd: string; sessionFile?: string; from: number; to: number; digest: string; reason: BacklogReason; agentDir?: string;
}): boolean {
  if (!input.sessionFile) return false;
  let fd: number | undefined;
  try {
    const paths = resolveMemoryPaths(input.cwd, input.agentDir);
    const entry: BacklogEntry = {
      version: 1, sessionFile: input.sessionFile, from: input.from, to: input.to,
      digest: input.digest, reason: input.reason, queuedAt: new Date().toISOString(), scopeKey: paths.scopeKey,
    };
    if (!validEntry(entry)) return false;
    const bytes = Buffer.from(`${JSON.stringify(entry)}\n`);
    if (bytes.length > MAX_BACKLOG_RECORD_BYTES) return false;
    const file = backlogFile(input.cwd, input.agentDir);
    safeStorage(file, paths.agentDir, true);
    fd = fs.openSync(file, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_APPEND | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK, 0o600);
    const stat = fs.fstatSync(fd);
    if (!stat.isFile() || stat.size + bytes.length > MAX_BACKLOG_BYTES) return false;
    safeStorage(file, paths.agentDir);
    const current = fs.lstatSync(file);
    if (stat.dev !== current.dev || stat.ino !== current.ino) return false;
    fs.fchmodSync(fd, 0o600);
    const written = fs.writeSync(fd, bytes);
    fs.fsyncSync(fd);
    return written === bytes.length;
  } catch { return false; }
  finally { if (fd !== undefined) fs.closeSync(fd); }
}

function readableSession(file: string): boolean {
  try { const stat = fs.lstatSync(file); return !stat.isSymbolicLink() && stat.isFile(); }
  catch { return false; }
}

/** Older references remain untouched. Only a bounded session header binds scope. */
function legacyScope(entry: BacklogEntry): string | undefined {
  let fd: number | undefined;
  try {
    fd = fs.openSync(entry.sessionFile, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
    if (!fs.fstatSync(fd).isFile()) return undefined;
    const bytes = Buffer.alloc(MAX_BACKLOG_RECORD_BYTES);
    const length = fs.readSync(fd, bytes, 0, bytes.length, 0);
    const newline = bytes.subarray(0, length).indexOf(10);
    if (newline < 0) return undefined;
    const header = JSON.parse(bytes.subarray(0, newline).toString("utf8"));
    if (header.type !== "session" || typeof header.cwd !== "string" || !path.isAbsolute(header.cwd)) return undefined;
    return resolveMemoryPaths(canonicalProjectCwd(header.cwd)).scopeKey;
  } catch { return undefined; }
  finally { if (fd !== undefined) fs.closeSync(fd); }
}

export interface BacklogRead {
  entries: BacklogEntry[];
  unlearnable: BacklogEntry[];
  malformed: number;
  /** Cursor addresses the original record order, including missing sessions. */
  consumed: number;
  pending: number;
  unscoped: number;
  error?: string;
}

export function readBacklog(cwd: string, agentDir = getAgentDir()): BacklogRead {
  const result: BacklogRead = { entries: [], unlearnable: [], malformed: 0, consumed: 0, pending: 0, unscoped: 0 };
  try {
    const paths = resolveMemoryPaths(cwd, agentDir), file = backlogFile(cwd, agentDir);
    safeStorage(file, paths.agentDir);
    result.consumed = readCursor(cwd, agentDir);
    const legacyConsumed = readStoredCursor(path.join(path.dirname(file), CURSOR_FILE), paths.agentDir);
    const raw = readBounded(file, MAX_BACKLOG_BYTES);
    let ordinal = 0;
    for (const line of raw.split("\n")) {
      if (!line) continue;
      const position = ordinal++;
      try {
        if (Buffer.byteLength(line) > MAX_BACKLOG_RECORD_BYTES) throw new Error("Oversized record");
        const entry: unknown = JSON.parse(line);
        if (!validEntry(entry)) throw new Error("Invalid reference");
        const scope = entry.scopeKey ?? legacyScope(entry);
        if (!scope) { result.unscoped += 1; continue; }
        if (scope !== paths.scopeKey) continue;
        if (readableSession(entry.sessionFile)) {
          result.entries.push(entry);
          const consumed = entry.scopeKey === undefined ? Math.max(result.consumed, legacyConsumed) : result.consumed;
          if (position >= consumed) result.pending += 1;
        } else result.unlearnable.push(entry);
      } catch { result.malformed += 1; }
    }
    return result;
  } catch (error) {
    if (!missing(error)) result.error = "Backlog could not be read safely";
    return result;
  }
}

const CURSOR_FILE = "learning-backlog.cursor.json";
function cursorPath(cwd: string, agentDir: string): string {
  const paths = resolveMemoryPaths(cwd, agentDir);
  return path.join(paths.agentDir, "learning", paths.scopeKey, CURSOR_FILE);
}

export function readCursor(cwd: string, agentDir = getAgentDir()): number {
  const paths = resolveMemoryPaths(cwd, agentDir);
  return readStoredCursor(cursorPath(cwd, agentDir), paths.agentDir);
}

function readStoredCursor(file: string, root: string): number {
  try {
    safeStorage(file, root);
    const value = JSON.parse(readBounded(file, MAX_BACKLOG_RECORD_BYTES));
    if (!value || !Number.isSafeInteger(value.consumed) || value.consumed < 0) throw new Error("Invalid backlog cursor");
    return value.consumed;
  } catch (error) { if (missing(error)) return 0; throw error; }
}

export function advanceCursor(cwd: string, consumed: number, agentDir = getAgentDir()): boolean {
  if (!Number.isSafeInteger(consumed) || consumed < 0) return false;
  try { return withBacklogLock(cwd, agentDir, () => writeCursor(cwd, consumed, agentDir)); }
  catch { return false; }
}

function writeCursor(cwd: string, consumed: number, agentDir: string): boolean {
  let temporary: string | undefined;
  try {
    const paths = resolveMemoryPaths(cwd, agentDir), file = cursorPath(cwd, agentDir);
    safeStorage(file, paths.agentDir, true);
    if (consumed < readCursor(cwd, agentDir)) return false;
    temporary = `${file}.${process.pid}.${randomBytes(8).toString("hex")}.tmp`;
    fs.writeFileSync(temporary, `${JSON.stringify({ consumed })}\n`, { mode: 0o600, flag: "wx" });
    safeStorage(file, paths.agentDir);
    fs.renameSync(temporary, file);
    return true;
  } catch { return false; }
  finally { if (temporary) { try { fs.unlinkSync(temporary); } catch { /* Already renamed. */ } } }
}

export function backlogStatus(cwd: string, agentDir = getAgentDir()) {
  const read = readBacklog(cwd, agentDir);
  return {
    pending: read.pending, unlearnable: read.unlearnable.length, malformed: read.malformed,
    consumed: read.consumed, unscoped: read.unscoped, ...(read.error ? { error: read.error } : {}),
    reason: read.error ? "unavailable" : read.pending > 0 ? "ready" : read.unlearnable.length ? "unlearnable-only" : "empty",
  };
}
