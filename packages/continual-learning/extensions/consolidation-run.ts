import { memoryReferenceResults } from "./memory-evidence-provenance";
import { assertTransactionPredecessor, prepareTransactionWrite, recordTransactionWrite, removeTransactionFile, restoreOwnedFile, withOwnedFileTransaction } from "./file-transaction";
import * as crypto from "node:crypto";
import * as fsp from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import type { ChildProcess } from "node:child_process";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { terminateChildProcess } from "@fradser/pi-kit";
import { resolveMemoryPaths, type MemoryPaths } from "./memory-paths";
import { buildMemoryIndexContent, isMemoryFilename } from "./memory-files";

export const CONSOLIDATION_SCHEMA_VERSION = 1;
export const MAX_PLAN_BYTES = 512_000;
export const MAX_STDOUT_BYTES = 16 * 1024 * 1024;
export const MAX_STDERR_BYTES = 64_000;
export const MAX_JSONL_LINES = 65_536;
export const MAX_JSONL_LINE_BYTES = 1024 * 1024;
export const MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024;
export const MAX_MEMORY_FILES = 4_096;
export const MAX_MEMORY_BYTES = 64_000;
export const MAX_SNAPSHOT_DEPTH = 128;
/** New context-derived files are bounded independently of the existing scope. */
export const MAX_NEW_MEMORY_PROPOSALS = 16;
export const MAX_NEW_MEMORY_NAME_CHARS = 96;
export const MAX_NEW_MEMORY_EVIDENCE = 8;
export const MAX_NEW_MEMORY_QUOTE_CHARS = 2_000;
export const MAX_NEW_MEMORY_TOTAL_BYTES = 256_000;

export interface ConsolidationRunPaths {
  memory: MemoryPaths;
  runId: string;
  runDir: string;
  lockFile: string;
  manifestFile: string;
  contextManifestFile: string;
  snapshotFile: string;
  planFile: string;
  stdoutFile: string;
  stderrFile: string;
  preReceiptFile: string;
  postReceiptFile: string;
  activitySummaryFile: string;
}

const RUN_ID_RE = /^run_[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function createConsolidationRunId(now = Date.now()): string {
  return `run_${now.toString(36)}_${crypto.randomBytes(8).toString("hex")}`;
}

export function isConsolidationRunId(value: string): boolean {
  return RUN_ID_RE.test(value) && !value.includes("..") && !value.includes("/") && !value.includes("\\");
}

export function resolveConsolidationRunPaths(cwd: string, runId = createConsolidationRunId(), agentDir?: string): ConsolidationRunPaths {
  if (!isConsolidationRunId(runId)) throw new Error(`Invalid consolidation run id: ${runId}`);
  const memory = resolveMemoryPaths(cwd, agentDir);
  const runDir = path.join(memory.runsDir, runId);
  return {
    memory,
    runId,
    runDir,
    lockFile: memory.lockFile,
    manifestFile: path.join(runDir, "manifest.json"),
    contextManifestFile: path.join(runDir, "context-manifest.json"),
    snapshotFile: path.join(runDir, "snapshot.json"),
    planFile: path.join(runDir, "plan.json"),
    stdoutFile: path.join(runDir, "stdout.jsonl"),
    stderrFile: path.join(runDir, "stderr.txt"),
    preReceiptFile: path.join(runDir, "pre-receipt.json"),
    postReceiptFile: path.join(runDir, "post-receipt.json"),
    activitySummaryFile: path.join(runDir, "activity-summary.json"),
  };
}

async function ensureSecureDirectory(target: string, mode = 0o700): Promise<void> {
  const resolved = path.resolve(target);
  const root = path.parse(resolved).root;
  const components = resolved.slice(root.length).split(path.sep).filter(Boolean);
  let current = root;
  for (let index = 0; index < components.length; index += 1) {
    current = path.join(current, components[index]);
    const isTarget = index === components.length - 1;
    let created = false;
    try {
      const stat = await fsp.lstat(current);
      if (stat.isSymbolicLink()) {
        if (isTarget) throw new Error(`Consolidation path is not a regular directory: ${current}`);
        const followed = await fsp.stat(current);
        if (!followed.isDirectory()) throw new Error(`Consolidation path is not a directory: ${current}`);
        continue;
      }
      if (!stat.isDirectory()) throw new Error(`Consolidation path is not a regular directory: ${current}`);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      try {
        await fsp.mkdir(current, { mode });
        created = true;
      } catch (mkdirError) {
        if ((mkdirError as NodeJS.ErrnoException).code !== "EEXIST") throw mkdirError;
      }
      const createdStat = await fsp.lstat(current);
      if (createdStat.isSymbolicLink() || !createdStat.isDirectory()) {
        throw new Error(`Consolidation path is not a regular directory: ${current}`);
      }
    }
    if (created) await fsp.chmod(current, mode);
  }
}

function assertWithin(parent: string, child: string): void {
  const relative = path.relative(path.resolve(parent), path.resolve(child));
  if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error(`Consolidation path escapes configured agent directory: ${child}`);
  }
}

async function assertCanonicalWithin(parent: string, child: string): Promise<void> {
  const childStat = await fsp.lstat(child);
  if (childStat.isSymbolicLink() || !childStat.isDirectory()) {
    throw new Error(`Consolidation path must be a regular directory: ${child}`);
  }
  const canonicalParent = await fsp.realpath(parent);
  const canonicalChild = await fsp.realpath(child);
  const relative = path.relative(canonicalParent, canonicalChild);
  if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error(`Consolidation path escapes configured agent directory: ${child}`);
  }
}

export async function ensureConsolidationRunDir(paths: ConsolidationRunPaths): Promise<void> {
  assertWithin(paths.memory.agentDir, paths.memory.runsDir);
  assertWithin(paths.memory.runsDir, paths.runDir);
  await ensureSecureDirectory(paths.memory.agentDir);
  await assertCanonicalWithin(paths.memory.agentDir, paths.memory.agentDir);
  await ensureSecureDirectory(paths.memory.runsDir);
  await assertCanonicalWithin(paths.memory.agentDir, paths.memory.runsDir);
  await ensureSecureDirectory(paths.runDir);
  await assertCanonicalWithin(paths.memory.runsDir, paths.runDir);
}

export async function removeConsolidationRunDir(paths: ConsolidationRunPaths): Promise<void> {
  assertWithin(paths.memory.agentDir, paths.memory.runsDir);
  assertWithin(paths.memory.runsDir, paths.runDir);
  try {
    const stat = await fsp.lstat(paths.runDir);
    if (stat.isSymbolicLink()) {
      await fsp.rm(paths.runDir, { force: true });
      return;
    }
    if (stat.isDirectory()) await fsp.rm(paths.runDir, { recursive: true, force: true });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
}

export interface ConsolidationLockOwner {
  runId: string;
  scopeKey: string;
  cwd: string;
  pid: number;
  hostname: string;
  acquiredAt: string;
  nonce: string;
}

export interface ConsolidationLockHandle {
  path: string;
  owner: ConsolidationLockOwner;
  release: () => Promise<boolean>;
}

export class ConsolidationLockContentionError extends Error {
  readonly lockPath: string;
  readonly owner?: ConsolidationLockOwner;

  constructor(lockPath: string, owner?: ConsolidationLockOwner) {
    super(owner
      ? `Memory consolidation is already running for ${owner.cwd} (run ${owner.runId}, pid ${owner.pid}).`
      : `Memory consolidation lock is already held: ${lockPath}`);
    this.name = "ConsolidationLockContentionError";
    this.lockPath = lockPath;
    this.owner = owner;
  }
}

function parseLockOwner(raw: string): ConsolidationLockOwner | undefined {
  try {
    const value = JSON.parse(raw) as Partial<ConsolidationLockOwner>;
    if (
      typeof value.runId !== "string" || typeof value.scopeKey !== "string" || typeof value.cwd !== "string" ||
      typeof value.pid !== "number" || typeof value.hostname !== "string" || typeof value.acquiredAt !== "string" ||
      typeof value.nonce !== "string"
    ) return undefined;
    return value as ConsolidationLockOwner;
  } catch {
    return undefined;
  }
}

export async function readConsolidationLock(lockPath: string): Promise<ConsolidationLockOwner | undefined> {
  try { return parseLockOwner(await fsp.readFile(lockPath, "utf8")); } catch { return undefined; }
}

function isProcessAlive(pid: number): boolean {
  try { process.kill(pid, 0); return true; } catch (error: unknown) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

/**
 * Quarantine the inspected dead-owner lock atomically: rename it aside, verify
 * the bytes still describe the dead owner we inspected, and only then discard.
 * A concurrent acquirer therefore either finds no lock to reclaim or contends
 * on the replacement — a live lock is restored rather than deleted.
 */
async function quarantineDeadOwnerLock(paths: ConsolidationRunPaths, deadOwner: ConsolidationLockOwner): Promise<boolean> {
  const quarantine = `${paths.lockFile}.${crypto.randomBytes(6).toString("hex")}.reclaim`;
  try {
    await fsp.rename(paths.lockFile, quarantine);
  } catch (error: unknown) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
  try {
    const quarantined = await readConsolidationLock(quarantine);
    if (
      !quarantined || quarantined.nonce !== deadOwner.nonce ||
      quarantined.hostname !== os.hostname() || isProcessAlive(quarantined.pid)
    ) {
      // The lock changed between inspection and quarantine. Restore it unless
      // another owner already replaced it at the canonical path.
      try {
        await fsp.lstat(paths.lockFile);
        await fsp.rm(quarantine, { force: true });
      } catch {
        await fsp.rename(quarantine, paths.lockFile).catch(() => fsp.rm(quarantine, { force: true }));
      }
      return false;
    }
    await fsp.rm(quarantine, { force: true });
    return true;
  } catch (error) {
    await fsp.rm(quarantine, { force: true }).catch(() => {});
    throw error;
  }
}

export async function acquireConsolidationLock(paths: ConsolidationRunPaths, owner: Partial<Pick<ConsolidationLockOwner, "runId" | "cwd">> = {}): Promise<ConsolidationLockHandle> {
  await ensureSecureDirectory(paths.memory.agentDir);
  await ensureSecureDirectory(path.dirname(paths.lockFile));
  for (let attempt = 0; ; attempt += 1) {
    const lockOwner: ConsolidationLockOwner = {
      runId: owner.runId ?? paths.runId,
      scopeKey: paths.memory.scopeKey,
      cwd: owner.cwd ?? paths.memory.cwd,
      pid: process.pid,
      hostname: os.hostname(),
      acquiredAt: new Date().toISOString(),
      nonce: crypto.randomBytes(16).toString("hex"),
    };
    let handle: fsp.FileHandle | undefined;
    let created = false;
    try {
      handle = await fsp.open(paths.lockFile, "wx", 0o600);
      created = true;
      await handle.writeFile(`${JSON.stringify(lockOwner)}\n`, "utf8");
      await handle.sync();
      await handle.close();
      handle = undefined;
    } catch (error: unknown) {
      await handle?.close().catch(() => {});
      if (created) await fsp.rm(paths.lockFile, { force: true }).catch(() => {});
      const code = error && typeof error === "object" && "code" in error ? (error as NodeJS.ErrnoException).code : undefined;
      if (code === "EEXIST") {
        // One bounded reclaim attempt: only a same-host dead owner qualifies.
        const currentOwner = attempt === 0 ? await readConsolidationLock(paths.lockFile) : undefined;
        const reclaimable = Boolean(
          currentOwner && currentOwner.hostname === os.hostname() && !isProcessAlive(currentOwner.pid) &&
          await quarantineDeadOwnerLock(paths, currentOwner),
        );
        if (!reclaimable) throw new ConsolidationLockContentionError(paths.lockFile, await readConsolidationLock(paths.lockFile));
        continue;
      }
      throw error;
    }
    let released = false;
    const release = async (): Promise<boolean> => {
      if (released) return false;
      const current = await readConsolidationLock(paths.lockFile);
      if (!current || current.nonce !== lockOwner.nonce) { released = true; return false; }
      try {
        await fsp.rm(paths.lockFile, { force: true });
        released = true;
        return true;
      } catch {
        return false;
      }
    };
  return { path: paths.lockFile, owner: lockOwner, release };
  }
}

export interface SnapshotSessionManager {
  getBranch?: () => readonly unknown[];
  buildContextEntries?: (...args: unknown[]) => readonly unknown[];
  getSessionFile?: () => string | undefined;
}

function normalizeSnapshotEntries(value: unknown): unknown[] {
  if (!Array.isArray(value)) return [];
  return value.map((entry) => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) return entry;
    const record = entry as Record<string, unknown>;
    const message = record.message;
    if (!message || typeof message !== "object" || Array.isArray(message)) return entry;
    const messageRecord = message as Record<string, unknown>;
    const content = messageRecord.content;
    if (!Array.isArray(content)) return entry;
    return { ...record, message: { ...messageRecord, content: content.map((block) => cloneJson(block)) } };
  });
}

export interface ConsolidationSnapshotContext { cwd?: string; sessionManager?: SnapshotSessionManager }
export type SnapshotSource = "context" | "branch" | "empty";

/** Captured only by the current command handler, never from source entries. */
export interface MaintenanceCommandInvocation {
  kind: "user-maintenance-command";
  version: 1;
  command: "consolidate";
  arguments: string;
  action: "current-task" | "full-corpus" | "backfill";
  invocationId: string;
  capturedAt: string;
  scopeKey: string;
  sessionId?: string;
}
export interface BoundMaintenanceCommand extends MaintenanceCommandInvocation {
  runId: string;
  sourceEntriesDigest: string;
}

/** Keep the exact current input; a procedure invocation is not knowledge or a policy correction. */
export function captureMaintenanceCommand(ctx: ExtensionContext, args: string): MaintenanceCommandInvocation {
  const action = args.trim() === "" ? "current-task" : args.trim() === "full" ? "full-corpus"
    : args.trim() === "backfill" ? "backfill" : undefined;
  if (!action) throw new Error("Invalid maintenance command");
  const sessionId = ctx.sessionManager.getSessionId?.();
  const command: MaintenanceCommandInvocation = {kind: "user-maintenance-command", version: 1, command: "consolidate", arguments: args,
    action, invocationId: crypto.randomUUID(), capturedAt: new Date().toISOString(),
    scopeKey: resolveMemoryPaths(ctx.cwd || process.cwd()).scopeKey,
    ...(sessionId ? {sessionId} : {})};
  cloneJson(command, MAX_SNAPSHOT_BYTES);
  return Object.freeze(command);
}

/** Validate the separate current namespace; quoted or historical copies are not current permission. */
export function readCurrentMaintenanceCommand(snapshot: unknown): BoundMaintenanceCommand | undefined {
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)) return undefined;
  const state = snapshot as Record<string, unknown>;
  if (state.currentMaintenanceRequest === undefined) return undefined;
  const value = state.currentMaintenanceRequest;
  const invalid = () => { throw new Error("Invalid current maintenance command binding"); };
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  const command = value as Record<string, unknown>;
  const keys = ["kind", "version", "command", "arguments", "action", "invocationId", "capturedAt", "scopeKey", "sessionId", "runId", "sourceEntriesDigest"];
  if (Object.keys(command).some(key => !keys.includes(key)) || command.kind !== "user-maintenance-command"
    || command.version !== 1 || command.command !== "consolidate" || typeof command.arguments !== "string"
    || typeof command.invocationId !== "string" || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u.test(command.invocationId)
    || typeof command.capturedAt !== "string" || !Number.isFinite(Date.parse(command.capturedAt))
    || typeof command.scopeKey !== "string" || !command.scopeKey || command.scopeKey !== state.scopeKey
    || typeof command.runId !== "string" || !command.runId || command.runId !== state.runId
    || command.sessionId !== undefined && (typeof command.sessionId !== "string" || !command.sessionId)
    || state.contextEnabled !== true || !Array.isArray(state.entries)
    || command.sourceEntriesDigest !== sha256Digest(JSON.stringify(state.entries))) return invalid();
  const action = command.arguments.trim() === "" ? "current-task" : command.arguments.trim() === "full" ? "full-corpus"
    : command.arguments.trim() === "backfill" ? "backfill" : undefined;
  if (!action || command.action !== action) return invalid();
  return command as unknown as BoundMaintenanceCommand;
}

export interface ConsolidationSnapshot {
  schemaVersion: typeof CONSOLIDATION_SCHEMA_VERSION;
  runId: string;
  scopeKey: string;
  capturedAt: string;
  source: SnapshotSource;
  contextEnabled: boolean;
  entries: unknown[];
  currentMaintenanceRequest?: BoundMaintenanceCommand;
  branchEntries?: unknown[];
  contextEntries?: unknown[];
}

export interface ContextManifest {
  schemaVersion: typeof CONSOLIDATION_SCHEMA_VERSION;
  runId: string;
  scopeKey: string;
  contextEnabled: boolean;
  mode: "snapshot";
  snapshotFile?: string;
  snapshotDigest?: string;
  entryCount: number;
  createdAt: string;
  reason?: string;
}

export interface ConsolidationManifest {
  schemaVersion: typeof CONSOLIDATION_SCHEMA_VERSION;
  runId: string;
  cwd: string;
  scopeKey: string;
  scopeDigest: string;
  harnessDir: string;
  publicDir?: string;
  runDir: string;
  contextEnabled: boolean;
  contextMode: "snapshot";
  snapshotPath: string;
  snapshotDigest: string;
  createdAt: string;
  sourceHashes: { harness: Record<string, string>; public: Record<string, string> };
}

export interface ConsolidationRun {
  manifest: ConsolidationManifest;
  paths: ConsolidationRunPaths;
  lockPath: string;
  lock?: ConsolidationLockHandle;
  released: boolean;
  normalization: MirrorNormalization;
}

class SnapshotLimitError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SnapshotLimitError";
  }
}

function estimateJsonBytes(value: unknown, maxBytes: number, depth = 0, seen = new WeakSet<object>()): number {
  if (depth > MAX_SNAPSHOT_DEPTH) throw new SnapshotLimitError("Consolidation snapshot exceeds the maximum nesting depth.");
  if (value === null) return 4;
  switch (typeof value) {
    case "string": return Buffer.byteLength(JSON.stringify(value), "utf8");
    case "number":
    case "boolean": return Buffer.byteLength(String(value), "utf8");
    case "undefined":
    case "function":
    case "symbol": return 0;
    case "bigint": throw new Error("Consolidation snapshot is not JSON-serializable.");
  }
  if (seen.has(value)) throw new Error("Cannot snapshot a cyclic value.");
  seen.add(value);
  let bytes = Array.isArray(value) ? 2 : 2;
  if (Array.isArray(value)) {
    if (value.length > MAX_MEMORY_FILES * 16) throw new SnapshotLimitError("Consolidation snapshot has too many entries.");
    for (const item of value) {
      bytes += estimateJsonBytes(item, maxBytes, depth + 1, seen) + 1;
      if (bytes > maxBytes) throw new SnapshotLimitError(`Consolidation snapshot exceeds ${maxBytes} bytes.`);
    }
  } else {
    const keys = Object.keys(value as Record<string, unknown>);
    if (keys.length > MAX_MEMORY_FILES * 16) throw new SnapshotLimitError("Consolidation snapshot has too many fields.");
    for (const key of keys) {
      bytes += Buffer.byteLength(JSON.stringify(key), "utf8") + 1;
      bytes += estimateJsonBytes((value as Record<string, unknown>)[key], maxBytes, depth + 1, seen) + 1;
      if (bytes > maxBytes) throw new SnapshotLimitError(`Consolidation snapshot exceeds ${maxBytes} bytes.`);
    }
  }
  seen.delete(value);
  return bytes;
}

function cloneJson(value: unknown, maxBytes = MAX_SNAPSHOT_BYTES): unknown {
  estimateJsonBytes(value, maxBytes);
  const encoded = JSON.stringify(value);
  if (encoded === undefined) throw new Error("Consolidation snapshot is not JSON-serializable.");
  if (Buffer.byteLength(encoded, "utf8") > maxBytes) throw new SnapshotLimitError(`Consolidation snapshot exceeds ${maxBytes} bytes.`);
  return JSON.parse(encoded) as unknown;
}

function freezeJson(value: unknown): unknown {
  if (!value || typeof value !== "object") return value;
  for (const child of Object.values(value as Record<string, unknown>)) freezeJson(child);
  return Object.freeze(value);
}

/**
 * Capture the session reads used by later consolidation phases once. The
 * returned context keeps the original context surface, while branch/context
 * readers return bounded frozen clones and all other manager methods retain
 * their original receiver.
 */
export function snapshotSessionContext(ctx: ExtensionContext, taskEntries?: readonly unknown[]): ExtensionContext {
  const manager = ctx.sessionManager;
  const cwd = ctx.cwd;
  const hasGetCwd = typeof manager.getCwd === "function";
  const hasGetSessionId = typeof manager.getSessionId === "function";
  const hasGetSessionFile = typeof manager.getSessionFile === "function";
  const hasGetHeader = typeof manager.getHeader === "function";
  const sessionCwd = hasGetCwd ? manager.getCwd() : undefined;
  const sessionId = hasGetSessionId ? manager.getSessionId() : undefined;
  const sessionFile = hasGetSessionFile ? manager.getSessionFile() : undefined;
  const header = hasGetHeader ? freezeJson(cloneJson(manager.getHeader(), MAX_SNAPSHOT_BYTES)) : undefined;
  const frozenBranch = taskEntries !== undefined
    ? freezeJson(cloneJson(taskEntries, MAX_SNAPSHOT_BYTES))
    : manager.getBranch
      ? freezeJson(cloneJson(manager.getBranch(), MAX_SNAPSHOT_BYTES))
      : undefined;
  const frozenContext = taskEntries !== undefined
    ? freezeJson(cloneJson(taskEntries, MAX_SNAPSHOT_BYTES))
    : manager.buildContextEntries
      ? freezeJson(cloneJson(manager.buildContextEntries(), MAX_SNAPSHOT_BYTES))
      : undefined;
  const frozenManager = new Proxy(manager, {
    get(target, property, receiver) {
      if (property === "getBranch" && frozenBranch !== undefined) return () => frozenBranch;
      if (property === "buildContextEntries" && frozenContext !== undefined) return () => frozenContext;
      if (property === "getCwd" && hasGetCwd) return () => sessionCwd;
      if (property === "getSessionId" && hasGetSessionId) return () => sessionId;
      if (property === "getSessionFile" && hasGetSessionFile) return () => sessionFile;
      if (property === "getHeader" && hasGetHeader) return () => header;
      const member = Reflect.get(target, property, receiver);
      return typeof member === "function" ? member.bind(target) : member;
    },
  });
  return new Proxy(ctx, {
    get(target, property, receiver) {
      if (property === "sessionManager") return frozenManager;
      if (property === "cwd") return cwd;
      const member = Reflect.get(target, property, receiver);
      return typeof member === "function" ? member.bind(target) : member;
    },
  });
}

function jsonText(value: unknown): string {
  const encoded = JSON.stringify(value, null, 2);
  if (encoded === undefined) throw new Error("Value is not JSON-serializable.");
  return `${encoded}\n`;
}

function stableJson(value: unknown, seen = new WeakSet<object>()): string {
  if (!value || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (seen.has(value)) throw new Error("Cannot digest a cyclic value.");
  seen.add(value);
  const result = Array.isArray(value)
    ? `[${value.map((item) => stableJson(item, seen)).join(",")}]`
    : `{${Object.keys(value as Record<string, unknown>).sort().map((key) => `${JSON.stringify(key)}:${stableJson((value as Record<string, unknown>)[key], seen)}`).join(",")}}`;
  seen.delete(value);
  return result;
}

export function digest(value: unknown): string { return crypto.createHash("sha256").update(stableJson(value), "utf8").digest("hex"); }
export function sha256Digest(value: string | Uint8Array): string { return crypto.createHash("sha256").update(value).digest("hex"); }

export async function readBoundedRegularFile(filePath: string, maxBytes: number): Promise<Buffer> {
  let handle: fsp.FileHandle | undefined;
  try {
    handle = await fsp.open(filePath, fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW ?? 0) | (fsConstants.O_NONBLOCK ?? 0));
    const stat = await handle.stat();
    if (!stat.isFile()) throw new Error(`Consolidation file is not regular: ${filePath}`);
    if (stat.size > maxBytes) throw new Error(`Consolidation file exceeds ${maxBytes} bytes: ${filePath}`);
    const chunks: Buffer[] = [];
    let total = 0;
    while (total < stat.size) {
      const chunk = Buffer.allocUnsafe(Math.min(64 * 1024, stat.size - total));
      const result = await handle.read(chunk, 0, chunk.byteLength, total);
      if (result.bytesRead === 0) break;
      chunks.push(chunk.subarray(0, result.bytesRead));
      total += result.bytesRead;
    }
    if (total !== stat.size) throw new Error(`Consolidation file changed while being read: ${filePath}`);
    return Buffer.concat(chunks, total);
  } finally {
    await handle?.close().catch(() => {});
  }
}

export async function sha256File(filePath: string, maxBytes = MAX_SNAPSHOT_BYTES): Promise<string> {
  let handle: fsp.FileHandle | undefined;
  try {
    handle = await fsp.open(filePath, fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW ?? 0) | (fsConstants.O_NONBLOCK ?? 0));
    const stat = await handle.stat();
    if (!stat.isFile()) throw new Error(`Consolidation file is not regular: ${filePath}`);
    if (stat.size > maxBytes) throw new Error(`Consolidation file exceeds ${maxBytes} bytes: ${filePath}`);
    const hash = crypto.createHash("sha256");
    const buffer = Buffer.allocUnsafe(Math.min(64 * 1024, maxBytes));
    let offset = 0;
    while (offset < stat.size) {
      const result = await handle.read(buffer, 0, Math.min(buffer.byteLength, stat.size - offset), offset);
      if (result.bytesRead === 0) break;
      hash.update(buffer.subarray(0, result.bytesRead));
      offset += result.bytesRead;
    }
    if (offset !== stat.size) throw new Error(`Consolidation file changed while being hashed: ${filePath}`);
    return hash.digest("hex");
  } finally {
    await handle?.close().catch(() => {});
  }
}

export async function writeFileAtomic(filePath: string, data: string | Uint8Array, mode = 0o600): Promise<void> {
  await ensureSecureDirectory(path.dirname(filePath), 0o700);
  const temporary = `${filePath}.${process.pid}.${crypto.randomBytes(8).toString("hex")}.tmp`;
  let handle: fsp.FileHandle | undefined;
  try {
    handle = await fsp.open(temporary, "wx", mode);
    await handle.writeFile(data);
    await handle.sync();
    await handle.close();
    handle = undefined;
    await prepareTransactionWrite(filePath, Buffer.from(data));
    await fsp.rename(temporary, filePath);
    recordTransactionWrite(filePath, Buffer.from(data));
    await fsp.chmod(filePath, mode);
  } finally {
    await handle?.close().catch(() => {});
    await fsp.rm(temporary, { force: true }).catch(() => {});
  }
}

export async function writeJsonAtomic(filePath: string, value: unknown, mode = 0o600): Promise<void> { await writeFileAtomic(filePath, jsonText(value), mode); }

export async function captureConsolidationSnapshot(
  ctx: ConsolidationSnapshotContext,
  paths: ConsolidationRunPaths,
  maxBytes = MAX_SNAPSHOT_BYTES,
  maintenanceCommand?: MaintenanceCommandInvocation,
): Promise<{ snapshot: ConsolidationSnapshot; manifest: ContextManifest; digest: string }> {
  await ensureConsolidationRunDir(paths);
  const manager = ctx.sessionManager;
  const branch = manager?.getBranch ? normalizeSnapshotEntries(cloneJson(manager.getBranch(), maxBytes)) : undefined;
  let contextEntries: unknown[] | undefined;
  if (manager?.buildContextEntries) {
    try {
      contextEntries = normalizeSnapshotEntries(cloneJson(manager.buildContextEntries(), maxBytes));
    } catch (error) {
      if (error instanceof SnapshotLimitError) throw error;
      contextEntries = undefined;
    }
  }
  const entries = contextEntries ?? branch ?? [];
  const source: SnapshotSource = contextEntries ? "context" : branch ? "branch" : "empty";
  const snapshot: ConsolidationSnapshot = {
    schemaVersion: CONSOLIDATION_SCHEMA_VERSION,
    runId: paths.runId,
    scopeKey: paths.memory.scopeKey,
    capturedAt: new Date().toISOString(),
    source,
    contextEnabled: true,
    entries,
    ...(maintenanceCommand ? {currentMaintenanceRequest: {...maintenanceCommand,
      runId: paths.runId, sourceEntriesDigest: sha256Digest(JSON.stringify(entries))}} : {}),
  };
  readCurrentMaintenanceCommand(snapshot);
  const encoded = jsonText(snapshot);
  if (Buffer.byteLength(encoded, "utf8") > maxBytes) throw new Error(`Consolidation snapshot exceeds ${maxBytes} bytes.`);
  await writeFileAtomic(paths.snapshotFile, encoded);
  const snapshotDigest = sha256Digest(encoded);
  const manifest: ContextManifest = {
    schemaVersion: CONSOLIDATION_SCHEMA_VERSION,
    runId: paths.runId,
    scopeKey: paths.memory.scopeKey,
    contextEnabled: true,
    mode: "snapshot",
    snapshotFile: path.basename(paths.snapshotFile),
    snapshotDigest,
    entryCount: entries.length,
    createdAt: snapshot.capturedAt,
  };
  await writeJsonAtomic(paths.contextManifestFile, manifest);
  return { snapshot, manifest, digest: snapshotDigest };
}

export interface MirrorRepair {
  name: string;
  direction: "harness-to-public" | "public-to-harness";
}

export interface MirrorNormalization {
  /** Safe files whose drifted or missing copy was rewritten from the newer side. */
  repaired: MirrorRepair[];
  /** Public files removed: private-marked, or orphaned without a harness copy. */
  removed: string[];
}

async function listMemoryRootFiles(root: string): Promise<Map<string, string>> {
  const files = new Map<string, string>();
  let rootStat: Awaited<ReturnType<typeof fsp.lstat>>;
  try {
    rootStat = await fsp.lstat(root);
  } catch (error: unknown) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return files;
    throw error;
  }
  // A project mirror is a privacy boundary. Never let normalization follow a
  // replaced root into an arbitrary directory: the loader and apply path both
  // enforce the same regular-directory contract.
  if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) {
    throw new Error(`Memory root is not a regular directory: ${root}`);
  }
  let names: string[];
  try {
    names = await fsp.readdir(root);
  } catch (error: unknown) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return files;
    throw error;
  }
  for (const name of names.sort()) {
    if (name.toLowerCase() === "memory.md" || !isMemoryFilename(name)) continue;
    const stat = await fsp.lstat(path.join(root, name));
    if (!stat.isFile()) throw new Error(`Memory entry is not a regular file: ${path.join(root, name)}`);
    files.set(name.toLowerCase(), name);
  }
  return files;
}

/**
 * Make the two memory roots satisfy the validator's mirror contract before the
 * run snapshots them: safe files are byte-identical mirrors, private files
 * never appear publicly, and both indexes are exact. Drift direction is decided
 * by the newer mtime — sessions write the harness first, while memory updates
 * arriving through the git-tracked mirror land in public — so either side can
 * be the fresh one. Without this, any pre-existing drift fails post-apply validation and every
 * full-scope consolidation becomes unrunnable until manual repair.
 */
export async function normalizeMirrorDrift(memory: MemoryPaths): Promise<MirrorNormalization> {
  const publicDir = memory.publicDir;
  if (!publicDir) return { repaired: [], removed: [] };
  const harnessStat = await fsp.lstat(memory.harnessDir).then(
    () => true,
    (error: unknown) => {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      return false;
    },
  );
  const harnessFiles = await listMemoryRootFiles(memory.harnessDir);
  const publicFiles = await listMemoryRootFiles(publicDir);
  if (!harnessStat && harnessFiles.size === 0) {
    // No canonical root yet: import the public mirror instead of deleting it.
    if (publicFiles.size === 0) return { repaired: [], removed: [] };
    await ensureMemoryRoot(memory.harnessDir);
    for (const [, publicName] of [...publicFiles].sort(([a], [b]) => a.localeCompare(b))) {
      const content = (await readBoundedRegularFile(path.join(publicDir, publicName), MAX_MEMORY_BYTES)).toString("utf8");
      await writeMemoryFile(path.join(memory.harnessDir, publicName), content);
    }
    await updateMemoryIndex(memory.harnessDir, new Set());
    await updateMemoryIndex(publicDir, new Set());
    return {
      repaired: [...publicFiles.values()].sort().map((name) => ({ name, direction: "public-to-harness" as const })),
      removed: [],
    };
  }
  const removed = new Set<string>();
  const repairLog = new Map<string, MirrorRepair>();
  const privateNames = await readPrivateIndexNames(memory.harnessDir);
  for (const key of privateNames) {
    if (!harnessFiles.has(key)) throw new Error(`Memory index marks a missing private file: ${harnessFiles.get(key) ?? key}`);
  }
  const copyBytes = async (direction: MirrorRepair["direction"], name: string, source: string, target: string): Promise<void> => {
    const content = (await readBoundedRegularFile(source, MAX_MEMORY_BYTES)).toString("utf8");
    await writeMemoryFile(target, content);
    repairLog.set(name, { name, direction });
  };
  // Newer mtime wins for drifted pairs; ties fall back to the harness copy.
  const copyNewer = async (harnessName: string, publicName: string): Promise<void> => {
    const harnessFile = path.join(memory.harnessDir, harnessName);
    const publicFile = path.join(publicDir, publicName);
    const [harnessStat, publicStat] = await Promise.all([fsp.lstat(harnessFile), fsp.lstat(publicFile)]);
    const fromHarness = harnessStat.mtimeMs >= publicStat.mtimeMs;
    await copyBytes(
      fromHarness ? "harness-to-public" : "public-to-harness",
      harnessName,
      fromHarness ? harnessFile : publicFile,
      fromHarness ? publicFile : harnessFile,
    );
  };
  for (const [key, publicName] of [...publicFiles].sort(([a], [b]) => a.localeCompare(b))) {
    const harnessName = harnessFiles.get(key);
    if (!harnessName || privateNames.has(key)) {
      await fsp.rm(path.join(publicDir, publicName), { force: true });
      removed.add(publicName);
      continue;
    }
    const harnessHash = await sha256File(path.join(memory.harnessDir, harnessName), MAX_MEMORY_BYTES);
    const publicHash = await sha256File(path.join(publicDir, publicName), MAX_MEMORY_BYTES);
    if (harnessHash === publicHash) continue;
    await copyNewer(harnessName, publicName);
  }
  for (const [key, harnessName] of [...harnessFiles].sort(([a], [b]) => a.localeCompare(b))) {
    if (privateNames.has(key) || publicFiles.has(key)) continue;
    await copyBytes("harness-to-public", harnessName, path.join(memory.harnessDir, harnessName), path.join(publicDir, harnessName));
  }
  if (removed.size > 0 || repairLog.size > 0 || harnessFiles.size > 0 || publicFiles.size > 0) {
    await ensureMemoryRoot(memory.harnessDir);
    await ensureMemoryRoot(publicDir);
    await updateMemoryIndex(memory.harnessDir, privateNames);
    await updateMemoryIndex(publicDir, new Set());
  }
  return { repaired: [...repairLog.values()].sort((left, right) => left.name.localeCompare(right.name)), removed: [...removed].sort() };
}

export async function createConsolidationRun(ctx: ExtensionContext, cwd: string, normalization: typeof normalizeMirrorDrift | false = normalizeMirrorDrift, maintenanceCommand?: MaintenanceCommandInvocation): Promise<ConsolidationRun> {
  const paths = resolveConsolidationRunPaths(cwd);
  if (maintenanceCommand && maintenanceCommand.scopeKey !== paths.memory.scopeKey) throw new Error("Maintenance command belongs to a different project");
  const lock = await acquireConsolidationLock(paths, { runId: paths.runId, cwd });
  try {
    await ensureConsolidationRunDir(paths);
    const normalized = normalization ? await normalization(paths.memory) : { repaired: [], removed: [] };
    // Every run carries a frozen snapshot. The former no-context mode skipped it
    // and had the planners work from an unfrozen context, which left
    // "evidence" ungroundable and made a proposal's provenance unverifiable.
    const captured = await captureConsolidationSnapshot(ctx, paths, MAX_SNAPSHOT_BYTES, maintenanceCommand);
    const contextManifest = captured.manifest;
    const snapshotDigest = captured.digest;
    const manifest: ConsolidationManifest = {
      schemaVersion: CONSOLIDATION_SCHEMA_VERSION, runId: paths.runId, cwd: paths.memory.cwd,
      scopeKey: paths.memory.scopeKey,
      scopeDigest: digest({ runId: paths.runId, scopeKey: paths.memory.scopeKey, snapshotDigest, contextEnabled: true }),
      harnessDir: paths.memory.harnessDir, publicDir: paths.memory.publicDir, runDir: paths.runDir,
      contextEnabled: true, contextMode: "snapshot", snapshotPath: paths.snapshotFile,
      snapshotDigest, createdAt: contextManifest.createdAt,
      sourceHashes: { harness: await hashMemoryRoot(paths.memory.harnessDir), public: paths.memory.publicDir ? await hashMemoryRoot(paths.memory.publicDir) : {} },
    };
    await writeJsonAtomic(paths.manifestFile, manifest);
    return { manifest, paths, lockPath: paths.lockFile, lock, released: false, normalization: normalized };
  } catch (error) {
    await lock.release(); await removeConsolidationRunDir(paths); throw error;
  }
}

export async function releaseConsolidationRun(run: ConsolidationRun, options: { keepArtifacts?: boolean } = {}): Promise<void> {
  if (run.released) return;
  try {
    if (!options.keepArtifacts) await removeConsolidationRunDir(run.paths);
  } finally {
    try {
      if (run.lock) await run.lock.release();
      else {
        const owner = await readConsolidationLock(run.lockPath);
        if (owner?.runId === run.manifest.runId && owner.pid === process.pid) await fsp.rm(run.lockPath, { force: true });
      }
    } finally {
      run.released = true;
    }
  }
}

export interface BoundedText { text: string; bytes: number; truncated: boolean }
function boundedStringBytes(value: string, maxBytes: number): Buffer {
  if (maxBytes <= 0 || value.length === 0) return Buffer.alloc(0);
  let prefix = value.slice(0, maxBytes);
  let bytes = Buffer.from(prefix, "utf8");
  while (bytes.byteLength > maxBytes && prefix.length > 0) {
    prefix = prefix.slice(0, Math.max(0, prefix.length - Math.ceil((bytes.byteLength - maxBytes) / 2)));
    bytes = Buffer.from(prefix, "utf8");
  }
  return bytes;
}

export function boundText(value: string | Uint8Array, maxBytes: number): BoundedText {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 0) throw new Error("maxBytes must be a non-negative integer.");
  if (typeof value === "string") {
    const bytes = boundedStringBytes(value, maxBytes);
    const exactLength = Buffer.byteLength(value, "utf8");
    return { text: bytes.toString("utf8"), bytes: bytes.length, truncated: exactLength > maxBytes };
  }
  if (value.byteLength <= maxBytes) return { text: Buffer.from(value).toString("utf8"), bytes: value.byteLength, truncated: false };
  return { text: Buffer.from(value.buffer, value.byteOffset, maxBytes).toString("utf8"), bytes: maxBytes, truncated: true };
}

export interface PlanIdentity { runId: string; scopeDigest: string; artifactHash?: string }
export interface PlanIdentityExpectation { runId: string; scopeDigest: string; artifactHash: string }
function planIdentity(plan: unknown): PlanIdentity | undefined {
  if (!plan || typeof plan !== "object" || Array.isArray(plan)) return undefined;
  const value = plan as Record<string, unknown>;
  if (typeof value.runId !== "string" || typeof value.scopeDigest !== "string") return undefined;
  return { runId: value.runId, scopeDigest: value.scopeDigest, ...(typeof value.artifactHash === "string" ? { artifactHash: value.artifactHash } : {}) };
}
export function validatePlanIdentityResult(plan: unknown, expected: PlanIdentityExpectation): { ok: true } | { ok: false; error: string } {
  const identity = planIdentity(plan);
  if (!identity) return { ok: false, error: "plan is missing runId and scopeDigest" };
  if (identity.runId !== expected.runId) return { ok: false, error: "plan run id mismatch" };
  if (identity.scopeDigest !== expected.scopeDigest) return { ok: false, error: "plan scope digest mismatch" };
  if (identity.artifactHash !== expected.artifactHash) return { ok: false, error: "plan artifact hash mismatch" };
  return { ok: true };
}
export function validatePlanIdentity(plan: unknown, expected: ConsolidationManifest | PlanIdentityExpectation): string[] {
  if (!plan || typeof plan !== "object" || Array.isArray(plan)) return ["plan is not an object"];
  const value = plan as Record<string, unknown>;
  if (!("artifactHash" in expected)) {
    const errors: string[] = [];
    if (value.runId !== expected.runId) errors.push("plan run id mismatch");
    if (value.scopeDigest !== expected.scopeDigest) errors.push("plan scope digest mismatch");
    if (value.artifactHash !== expected.snapshotDigest) errors.push("plan artifact hash mismatch");
    return errors;
  }
  const result = validatePlanIdentityResult(plan, expected);
  if (!result.ok) return [result.error];
  const errors: string[] = [];
  const expectedScopeKey = "scopeKey" in expected ? expected.scopeKey : undefined;
  if (value.scopeKey !== undefined && expectedScopeKey !== undefined && value.scopeKey !== expectedScopeKey) errors.push("plan scope key mismatch");
  if (value.snapshotDigest !== undefined && value.snapshotDigest !== value.artifactHash) errors.push("plan snapshot digest alias mismatch");
  if (value.kind === "memory-consolidation-plan" && expectedScopeKey !== undefined && value.scopeKey !== expectedScopeKey) errors.push("plan scope key is required");
  return errors;
}

export interface ChildPlanExtractionOptions<T = unknown> {
  expectedIdentity?: PlanIdentityExpectation;
  maxOutputBytes?: number;
  maxLines?: number;
  maxLineBytes?: number;
  maxPlanBytes?: number;
  validatePlan?: (value: unknown) => value is T;
}
export type ChildPlanExtractionResult<T = unknown> = { ok: true; plan: T; line: number } | { ok: false; error: string; failure?: "model-error" | "cancelled" };
function messageText(value: unknown): string {
  if (typeof value === "string") return value;
  if (!Array.isArray(value)) return "";
  return value.map((part) => {
    if (typeof part === "string") return part;
    if (!part || typeof part !== "object") return "";
    const record = part as Record<string, unknown>;
    return typeof record.text === "string" && (record.type === undefined || record.type === "text") ? record.text : "";
  }).join("");
}
function parsedObject(text: string): unknown | undefined {
  try {
    const parsed = JSON.parse(text) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : undefined;
  } catch {
    return undefined;
  }
}

function balancedJsonObjects(text: string): string[] {
  const objects: string[] = [];
  let start = -1;
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') inString = false;
      continue;
    }
    if (char === '"') {
      inString = true;
      continue;
    }
    if (char === "{") {
      if (depth === 0) start = index;
      depth += 1;
      continue;
    }
    if (char !== "}") continue;
    if (depth === 0) return [];
    depth -= 1;
    if (depth === 0 && start >= 0) {
      objects.push(text.slice(start, index + 1));
      start = -1;
    }
  }
  // A complete old draft cannot mask a truncated or unmatched later object.
  return depth === 0 && !inString ? objects : [];
}

function parseJsonCandidate(text: string): unknown | undefined {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  const direct = parsedObject(trimmed);
  if (direct) return direct;
  const fenced = /^```(?:json)?\s*([\s\S]*?)\s*```$/i.exec(trimmed);
  if (fenced) return parsedObject(fenced[1].trim());
  const objects = balancedJsonObjects(trimmed).map(parsedObject);
  // A damaged object cannot be discarded to select an earlier draft. Preserve
  // established compatibility with valid JSON metadata beside one unique plan.
  if (objects.some(value => !value)) return undefined;
  const candidates = objects.filter((value): value is Record<string, unknown> => Boolean(value))
    .filter(value => ["memory-consolidation-plan", "incremental-memory-plan", "harness-consolidation-plan", "agents-md-consolidation-plan"].includes(String(value.kind ?? value.type)));
  return candidates.length === 1 ? candidates[0] : undefined;
}

function candidateFromEvent(event: unknown): unknown | undefined {
  if (!event || typeof event !== "object" || Array.isArray(event)) return undefined;
  const value = event as Record<string, unknown>;
  if (value.type === "consolidation_plan") {
    return value.plan && typeof value.plan === "object" && !Array.isArray(value.plan) ? value.plan : undefined;
  }
  if (value.type === "memory-consolidation-plan" || value.kind === "memory-consolidation-plan" || value.kind === "incremental-memory-plan") return value;
  if (value.type !== "message_end" || !value.message || typeof value.message !== "object") return undefined;
  const message = value.message as Record<string, unknown>;
  if (message.role !== "assistant" || message.stopReason === "error" || message.stopReason === "aborted") return undefined;
  const text = messageText(message.content).trim();
  if (!text || text.length > MAX_PLAN_BYTES) return undefined;
  return parseJsonCandidate(text);
}
export function extractChildPlan<T = unknown>(stdout: string | Uint8Array, options: ChildPlanExtractionOptions<T> = {}): ChildPlanExtractionResult<T> {
  const output = boundText(stdout, options.maxOutputBytes ?? MAX_STDOUT_BYTES);
  if (output.truncated) return { ok: false, error: "child stdout exceeded the configured bound" };
  const splitLines = output.text.split(/\r?\n/);
  const lines = splitLines.at(-1) === "" ? splitLines.slice(0, -1) : splitLines;
  if (lines.length > (options.maxLines ?? MAX_JSONL_LINES)) return { ok: false, error: "child JSONL exceeded the line bound" };
  const candidates: Array<{ plan: unknown; line: number }> = [];
  let terminalFailure: "model-error" | "cancelled" | undefined;
  const maxLineBytes = options.maxLineBytes ?? MAX_JSONL_LINE_BYTES;
  const maxPlanBytes = options.maxPlanBytes ?? MAX_PLAN_BYTES;
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index]; if (!line.trim()) continue;
    const overlong = Buffer.byteLength(line, "utf8") > maxLineBytes;
    let event: unknown; try { event = JSON.parse(line); } catch { continue; }
    if (event && typeof event === "object" && !Array.isArray(event)) {
      const record = event as Record<string, unknown>;
      const message = record.message && typeof record.message === "object" && !Array.isArray(record.message)
        ? record.message as Record<string, unknown> : undefined;
      if (record.type === "message_end" && message?.role === "assistant") {
        if (message.stopReason === "error" || message.stopReason === "aborted") {
          terminalFailure = message.stopReason === "aborted" ? "cancelled" : "model-error";
          candidates.length = 0;
        } else if (["stop", "length", "toolUse"].includes(String(message.stopReason))) {
          terminalFailure = undefined;
        }
      } else if (record.type === "auto_retry_end") {
        if (record.success === false) {
          if (terminalFailure !== "cancelled") terminalFailure = "model-error";
          candidates.length = 0;
        }
      }
    }
    if (terminalFailure) continue;
    const plan = candidateFromEvent(event);
    // Streaming telemetry (thinking/tool deltas) can legitimately be larger
    // than one JSONL line bound. It is not a plan, so ignore it and continue
    // looking for the final assistant plan. A line that does contain a plan
    // still fails closed at the line boundary.
    if (overlong && plan === undefined) continue;
    if (overlong) return { ok: false, error: `child JSONL line ${index + 1} exceeded the byte bound` };
    if (plan === undefined) continue;
    if (Buffer.byteLength(jsonText(plan), "utf8") > maxPlanBytes) return { ok: false, error: "consolidation plan exceeded the byte bound" };
    candidates.push({ plan, line: index + 1 });
  }
  if (terminalFailure) return { ok: false, failure: terminalFailure, error: terminalFailure === "cancelled"
    ? "child planner cancelled before successful completion" : "child planner model failed before successful completion" };
  if (!candidates.length) return { ok: false, error: "child output did not contain a structured consolidation plan" };
  if (options.expectedIdentity && candidates.some(({ plan }) => !validatePlanIdentityResult(plan, options.expectedIdentity!).ok)) return { ok: false, error: "child consolidation plan identity mismatch" };
  const matching = options.expectedIdentity ? candidates.filter(({ plan }) => validatePlanIdentityResult(plan, options.expectedIdentity!).ok) : candidates;
  if (matching.length !== 1) return { ok: false, error: `expected one structured consolidation plan, found ${matching.length}` };
  if (options.validatePlan && !options.validatePlan(matching[0].plan)) return { ok: false, error: "structured consolidation plan failed schema validation" };
  return { ok: true, plan: matching[0].plan as T, line: matching[0].line };
}

export interface FinalHashes { harness: Record<string, string>; public: Record<string, string> }
const SHA256_RE = /^(?:sha256:)?[0-9a-f]{64}$/i;
export interface ReceiptBindingInput { runId: string; scopeDigest: string; artifactHash: string; selected: readonly string[]; created?: readonly string[]; finalHashes?: FinalHashes; sourceHashes?: FinalHashes; planDigest?: string; changes?: MemoryChangeSummary }
export interface MemoryChangeSummary {
  created: number;
  rewritten: number;
  deleted: number;
  sharedToPrivate: number;
  unpreservedDeletes: number;
}

export function summarizeMemoryChanges(plan: unknown): MemoryChangeSummary {
  const value = plan && typeof plan === "object" && !Array.isArray(plan) ? plan as Record<string, unknown> : {};
  const operations = Array.isArray(value.operations) ? value.operations.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && !Array.isArray(item))) : [];
  const created = Array.isArray(value.newMemories) ? value.newMemories.length : 0;
  return {
    created,
    rewritten: operations.filter((operation) => operation.kind === "rewrite" || operation.kind === "create").length,
    deleted: operations.filter((operation) => operation.kind === "delete").length,
    sharedToPrivate: operations.filter((operation) => operation.kind !== "delete" && operation.classification === "private").length,
    unpreservedDeletes: operations.filter((operation) => operation.kind === "delete" && (!Array.isArray(operation.preservedIn) || operation.preservedIn.length === 0)).length,
  };
}

export interface ConsolidationReceipt {
  kind: "memory-consolidation-receipt";
  version: typeof CONSOLIDATION_SCHEMA_VERSION;
  schemaVersion: typeof CONSOLIDATION_SCHEMA_VERSION;
  phase: "pre" | "post";
  runId: string;
  scopeDigest: string;
  artifactHash: string;
  selected: string[];
  created?: string[];
  finalHashes?: FinalHashes;
  sourceHashes?: FinalHashes;
  planDigest?: string;
  finalDigest?: string;
  changes?: MemoryChangeSummary;
  createdAt: string;
}
function sortedFiles(files: readonly string[]): string[] {
  const result = [...files];
  for (const file of result) assertMemoryName(file);
  const keys = result.map((file) => file.toLowerCase());
  if (new Set(keys).size !== keys.length) throw new Error("Receipt selected files contain duplicates.");
  return result.sort((left, right) => left.localeCompare(right));
}
function sortedHashes(value: Record<string, string>): Record<string, string> {
  for (const [name, hash] of Object.entries(value)) {
    if (name.toLowerCase() !== "memory.md") assertMemoryName(name);
    if (!/^(?:sha256:)?[0-9a-f]{64}$/i.test(hash)) throw new Error(`Invalid receipt hash for ${name}`);
  }
  const keys = Object.keys(value).map((name) => name.toLowerCase());
  if (new Set(keys).size !== keys.length) throw new Error("Receipt hash map contains duplicate files.");
  return Object.fromEntries(Object.entries(value).sort(([left], [right]) => left.localeCompare(right)));
}
export function createReceiptBinding(phase: "pre" | "post", input: ReceiptBindingInput): ConsolidationReceipt {
  return {
    kind: "memory-consolidation-receipt", version: CONSOLIDATION_SCHEMA_VERSION, schemaVersion: CONSOLIDATION_SCHEMA_VERSION, phase, runId: input.runId,
    scopeDigest: input.scopeDigest, artifactHash: input.artifactHash, selected: sortedFiles(input.selected),
    ...(input.created ? { created: sortedFiles(input.created) } : {}),
    ...(input.finalHashes ? { finalHashes: { harness: sortedHashes(input.finalHashes.harness), public: sortedHashes(input.finalHashes.public) } } : {}),
    ...(input.sourceHashes ? { sourceHashes: { harness: sortedHashes(input.sourceHashes.harness), public: sortedHashes(input.sourceHashes.public) } } : {}),
    ...(input.planDigest ? { planDigest: input.planDigest } : {}),
    ...(input.changes ? { changes: input.changes } : {}),
    createdAt: new Date().toISOString(),
  };
}
export function createPreApplyReceipt(input: ReceiptBindingInput): ConsolidationReceipt { return createReceiptBinding("pre", input); }
export function createPostApplyReceipt(input: ReceiptBindingInput): ConsolidationReceipt { return createReceiptBinding("post", input); }
export function createConsolidationReceipt(manifest: ConsolidationManifest, selected: string[], finalState: unknown, planDigest: string, created: readonly string[] = [], changes?: MemoryChangeSummary): ConsolidationReceipt {
  const hashes = finalState && typeof finalState === "object" && !Array.isArray(finalState) ? finalState as FinalHashes : { harness: {}, public: {} };
  return createPostApplyReceipt({ runId: manifest.runId, scopeDigest: manifest.scopeDigest, artifactHash: manifest.snapshotDigest, selected, created, finalHashes: hashes, sourceHashes: manifest.sourceHashes, planDigest, changes });
}
export interface ReceiptBindingExpectation { runId?: string; scopeDigest?: string; artifactHash?: string; selected?: readonly string[]; created?: readonly string[]; phase?: "pre" | "post" }
export function validateReceiptBinding(receipt: unknown, expected: ReceiptBindingExpectation = {}): { ok: true; receipt: ConsolidationReceipt } | { ok: false; error: string } {
  if (!receipt || typeof receipt !== "object" || Array.isArray(receipt)) return { ok: false, error: "receipt is not an object" };
  const value = receipt as Partial<ConsolidationReceipt>;
  if (value.kind !== "memory-consolidation-receipt" || value.version !== CONSOLIDATION_SCHEMA_VERSION || value.schemaVersion !== CONSOLIDATION_SCHEMA_VERSION) return { ok: false, error: "receipt kind or schema version mismatch" };
  if (typeof value.runId !== "string" || typeof value.scopeDigest !== "string" || typeof value.artifactHash !== "string" || !Array.isArray(value.selected)) return { ok: false, error: "receipt identity or selected scope is invalid" };
  if (value.phase !== "pre" && value.phase !== "post") return { ok: false, error: "receipt phase is required and invalid" };
  try {
    if (value.created !== undefined) sortedFiles(value.created);
    if (value.finalHashes) {
      if (!value.finalHashes || typeof value.finalHashes !== "object") return { ok: false, error: "receipt final hashes are invalid" };
      sortedHashes(value.finalHashes.harness);
      sortedHashes(value.finalHashes.public);
    }
    if (value.sourceHashes) {
      if (!value.sourceHashes || typeof value.sourceHashes !== "object") return { ok: false, error: "receipt source hashes are invalid" };
      sortedHashes(value.sourceHashes.harness);
      sortedHashes(value.sourceHashes.public);
    }
    if (value.phase === "pre" && !value.sourceHashes) return { ok: false, error: "pre receipt source hashes are required" };
    if (value.phase === "post" && !value.finalHashes) return { ok: false, error: "post receipt final hashes are required" };
    if (value.planDigest !== undefined && (typeof value.planDigest !== "string" || !SHA256_RE.test(value.planDigest))) {
      return { ok: false, error: "receipt plan digest is invalid" };
    }
    if (value.phase === "post" && !value.planDigest) return { ok: false, error: "post receipt plan digest is required" };
  } catch (error) {
    return { ok: false, error: (error as Error).message };
  }
  if (expected.runId && expected.runId !== value.runId) return { ok: false, error: "receipt run id mismatch" };
  if (expected.scopeDigest && expected.scopeDigest !== value.scopeDigest) return { ok: false, error: "receipt scope digest mismatch" };
  if (expected.artifactHash && expected.artifactHash !== value.artifactHash) return { ok: false, error: "receipt artifact hash mismatch" };
  if (expected.phase && expected.phase !== value.phase) return { ok: false, error: "receipt phase mismatch" };
  try {
    const selected = sortedFiles(value.selected.filter((item): item is string => typeof item === "string"));
    if (selected.length !== value.selected.length) return { ok: false, error: "receipt selected scope is invalid" };
    if (expected.selected && JSON.stringify(selected) !== JSON.stringify(sortedFiles(expected.selected))) return { ok: false, error: "receipt selected scope mismatch" };
    const created = value.created === undefined ? undefined : sortedFiles(value.created.filter((item): item is string => typeof item === "string"));
    if (value.created !== undefined && created!.length !== value.created.length) return { ok: false, error: "receipt created scope is invalid" };
    if (expected.created && JSON.stringify(created ?? []) !== JSON.stringify(sortedFiles(expected.created))) return { ok: false, error: "receipt created scope mismatch" };
    return { ok: true, receipt: { ...value, selected, ...(created === undefined ? {} : { created }) } as ConsolidationReceipt };
  } catch (error) { return { ok: false, error: (error as Error).message }; }
}
export async function writeConsolidationReceipt(run: ConsolidationRun, receipt: ConsolidationReceipt, phase: "pre" | "post" = "post"): Promise<string> {
  const validation = validateReceiptBinding(receipt, { phase });
  if (!validation.ok) throw new Error(`Invalid ${phase} consolidation receipt: ${validation.error}`);
  const file = phase === "pre" ? run.paths.preReceiptFile : run.paths.postReceiptFile;
  await writeJsonAtomic(file, validation.receipt);
  return file;
}

export interface CloseObservedResult { closeObserved: boolean; code: number | null; signal: NodeJS.Signals | null }
function childAlreadyClosed(child: ChildProcess): boolean { return child.exitCode !== null || child.signalCode !== null; }
function observeClose(child: ChildProcess): Promise<CloseObservedResult> { if (childAlreadyClosed(child)) return Promise.resolve({ closeObserved: true, code: child.exitCode, signal: child.signalCode }); return new Promise((resolve) => child.once("close", (code: number | null, signal: NodeJS.Signals | null) => resolve({ closeObserved: true, code, signal }))); }
export async function cancelChildWithClose(child: ChildProcess, graceMs?: number): Promise<CloseObservedResult> {
  const close = observeClose(child);
  if (!childAlreadyClosed(child)) {
    try { await terminateChildProcess(child, graceMs); } catch { /* close remains the completion signal */ }
  }
  return close;
}
export async function terminateConsolidationChild(child: ChildProcess, graceMs = 5_000): Promise<boolean> { return (await cancelChildWithClose(child, graceMs)).closeObserved; }
export function boundedStdout(value: string | Uint8Array): BoundedText { return boundText(value, MAX_STDOUT_BYTES); }

type MemoryHashes = Record<string, string>;

function assertMemoryName(value: unknown): asserts value is string {
  if (typeof value !== "string" || !isMemoryFilename(value)) {
    throw new Error("Consolidation plan contains an invalid memory filename");
  }
}

interface DirectoryIdentity { dev: number; ino: number }

async function openMemoryRoot(root: string): Promise<{ handle: fsp.FileHandle; identity: DirectoryIdentity } | undefined> {
  try {
    const handle = await fsp.open(root, fsConstants.O_RDONLY | (fsConstants.O_DIRECTORY ?? 0) | (fsConstants.O_NOFOLLOW ?? 0));
    const stat = await handle.stat();
    if (!stat.isDirectory()) {
      await handle.close();
      throw new Error(`Memory root is not a regular directory: ${root}`);
    }
    return { handle, identity: { dev: stat.dev, ino: stat.ino } };
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
}

async function assertMemoryRootStable(root: string, expected?: DirectoryIdentity): Promise<DirectoryIdentity> {
  const stat = await fsp.lstat(root);
  if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error(`Memory root is not a regular directory: ${root}`);
  const identity = { dev: stat.dev, ino: stat.ino };
  if (expected && (expected.dev !== identity.dev || expected.ino !== identity.ino)) {
    throw new Error(`Memory root changed while consolidation was running: ${root}`);
  }
  return identity;
}

async function ensureMemoryRoot(root: string): Promise<void> {
  await ensureSecureDirectory(root, 0o700);
  await assertMemoryRootStable(root);
}

export async function hashMemoryRoot(root: string): Promise<MemoryHashes> {
  const result: MemoryHashes = {};
  const opened = await openMemoryRoot(root);
  if (!opened) return result;
  try {
    await assertMemoryRootStable(root, opened.identity);
    const canonicalRoot = await fsp.realpath(root);
    let count = 0;
    for await (const entry of await fsp.opendir(canonicalRoot)) {
      count += 1;
      if (count > MAX_MEMORY_FILES) throw new Error(`Memory root contains more than ${MAX_MEMORY_FILES} entries: ${root}`);
      await assertMemoryRootStable(root, opened.identity);
      if (entry.isSymbolicLink()) throw new Error(`Memory entry is a symlink: ${path.join(root, entry.name)}`);
      if (!entry.isFile()) continue;
      if (entry.name.toLowerCase() !== "memory.md" && !isMemoryFilename(entry.name)) continue;
      const file = path.join(canonicalRoot, entry.name);
      const key = entry.name.toLowerCase() === "memory.md" ? "MEMORY.md" : entry.name;
      if (Object.keys(result).some((name) => name.toLowerCase() === key.toLowerCase())) {
        throw new Error(`Memory root contains duplicate case-insensitive names: ${file}`);
      }
      result[key] = await sha256File(file, MAX_MEMORY_BYTES);
    }
    await assertMemoryRootStable(root, opened.identity);
    return result;
  } finally {
    await opened.handle.close().catch(() => {});
  }
}

async function writeMemoryFile(file: string, content: string): Promise<void> {
  if (Buffer.byteLength(content, "utf8") > MAX_MEMORY_BYTES) throw new Error(`Memory file is larger than ${MAX_MEMORY_BYTES} bytes`);
  await assertTransactionPredecessor(file);
  try {
    const before = await fsp.lstat(file, {bigint: true});
    const bytes = await readBoundedRegularFile(file, MAX_MEMORY_BYTES);
    const after = await fsp.lstat(file, {bigint: true});
    if (before.dev !== after.dev || before.ino !== after.ino || before.size !== after.size
      || before.mtimeNs !== after.mtimeNs || before.ctimeNs !== after.ctimeNs) {
      throw new Error(`Memory file changed before write: ${file}`);
    }
    if ((after.mode & 0o777n) === 0o600n && bytes.equals(Buffer.from(content, "utf8"))) {
      await assertTransactionPredecessor(file);
      const final = await fsp.lstat(file, {bigint: true});
      if (after.dev !== final.dev || after.ino !== final.ino || after.size !== final.size
        || after.mtimeNs !== final.mtimeNs || after.ctimeNs !== final.ctimeNs || after.mode !== final.mode) {
        throw new Error(`Memory file changed before unchanged write: ${file}`);
      }
      return;
    }
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  await writeFileAtomic(file, content, 0o600);
}

async function updateMemoryIndex(root: string, privateNames: Set<string>, isActive?: () => void): Promise<void> {
  const rootIdentity = await assertMemoryRootStable(root);
  const hashes = await hashMemoryRoot(root);
  const names = Object.keys(hashes).filter((name) => name.toLowerCase() !== "memory.md").sort((a, b) => a.localeCompare(b));
  const nameKeys = new Set(names.map((name) => name.toLowerCase()));
  for (const name of privateNames) {
    if (!nameKeys.has(name.toLowerCase())) throw new Error(`Memory index marks a missing private file: ${name}`);
  }
  const content = await buildMemoryIndexContent(root, privateNames);
  await assertMemoryRootStable(root, rootIdentity);
  isActive?.();
  await writeMemoryFile(path.join(root, "MEMORY.md"), content);
  await assertMemoryRootStable(root, rootIdentity);
  const indexed = await readPrivateIndexNames(root);
  if (indexed.size !== privateNames.size || [...indexed].some((name) => !privateNames.has(name))) {
    throw new Error(`Memory index private classification drifted: ${root}`);
  }
}

async function ensureMemoryIndex(root: string, privateNames: Set<string>): Promise<void> {
  const index = path.join(root, "MEMORY.md");
  await assertMemoryRootStable(root);
  try {
    const stat = await fsp.lstat(index);
    if (!stat.isFile() || stat.isSymbolicLink()) throw new Error(`Memory index is not a regular file: ${index}`);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    await updateMemoryIndex(root, privateNames);
  }
}

interface MemoryFileSnapshot {
  file: string;
  existed: boolean;
  content?: Buffer;
  mode?: number;
}

async function captureMemoryFiles(files: readonly string[]): Promise<MemoryFileSnapshot[]> {
  const snapshots: MemoryFileSnapshot[] = [];
  for (const file of files) {
    try {
      const stat = await fsp.lstat(file);
      if (!stat.isFile() || stat.isSymbolicLink()) throw new Error(`Memory transaction target is not a regular file: ${file}`);
      snapshots.push({ file, existed: true, content: await readBoundedRegularFile(file, MAX_MEMORY_BYTES), mode: stat.mode & 0o777 });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      snapshots.push({ file, existed: false });
    }
  }
  return snapshots;
}

async function restoreMemoryFiles(snapshots: readonly MemoryFileSnapshot[]): Promise<void> {
  const errors: Error[] = [];
  for (const snapshot of [...snapshots].reverse()) {
    try {
      await restoreOwnedFile(snapshot.file, async () => {
        if (snapshot.existed) await writeFileAtomic(snapshot.file, snapshot.content!, snapshot.mode ?? 0o600);
        else await fsp.rm(snapshot.file, { force: true });
      });
    } catch (error) {
      errors.push(error as Error);
    }
  }
  if (errors.length) throw new Error(errors.map((error) => error.message).join("; "));
}

const PRIVATE_MARKER_RE = /\(\s*harness[\s_-]+only\s*\)/i;
const INDEX_LINK_RE = /\[[^\]]*\]\(([^)]+)\)/g;
const INDEX_BARE_RE = /^\s*(?:[-*+]\s+)?([A-Za-z0-9][A-Za-z0-9_-]*\.md)\b/i;

export function parseMemoryIndexLine(line: string): string | undefined {
  // A display label is untrusted metadata: when a Markdown link is present,
  // only its target names the entry. Fall back to the established bare-row
  // grammar, which prevents prose descriptions containing "*.md" from being
  // treated as new index entries.
  for (const match of line.matchAll(INDEX_LINK_RE)) {
    if (isMemoryFilename(match[1])) return match[1];
  }
  return line.match(INDEX_BARE_RE)?.[1];
}

/** Parse both Markdown-linked and bare filenames from a Memory index. */
export function parseMemoryIndexNames(text: string): Set<string> {
  const names = new Set<string>();
  for (const line of text.split(/\r?\n/)) {
    const name = parseMemoryIndexLine(line);
    if (name) names.add(name.toLowerCase());
  }
  return names;
}

export function parsePrivateIndexNames(text: string, root = "Memory index"): Set<string> {
  const privateNames = new Set<string>();
  for (const line of text.split(/\r?\n/)) {
    const name = parseMemoryIndexLine(line);
    if (PRIVATE_MARKER_RE.test(line)) {
      if (!name || !isMemoryFilename(name)) throw new Error(`Memory index has a private marker without a valid memory filename: ${root}`);
      const key = name.toLowerCase();
      if (privateNames.has(key)) throw new Error(`Memory index contains duplicate private memory names: ${name}`);
      privateNames.add(key);
    }
  }
  return privateNames;
}

export async function readPrivateIndexNames(root: string): Promise<Set<string>> {
  const index = path.join(root, "MEMORY.md");
  let text: string;
  try {
    text = (await readBoundedRegularFile(index, MAX_MEMORY_BYTES)).toString("utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return new Set();
    throw error;
  }
  return parsePrivateIndexNames(text, root);
}

interface NormalizedMemoryOperation {
  name: string;
  kind: "create" | "rewrite" | "delete";
  classification: "safe" | "private";
  content?: string;
}

interface MemoryRootSnapshot { root: string; existed: boolean }

async function captureRootState(root: string): Promise<MemoryRootSnapshot> {
  try {
    const stat = await fsp.lstat(root);
    if (stat.isSymbolicLink() || !stat.isDirectory()) throw new Error(`Memory root is not a regular directory: ${root}`);
    return { root, existed: true };
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return { root, existed: false };
    throw error;
  }
}

async function removeNewEmptyRoots(states: readonly MemoryRootSnapshot[]): Promise<void> {
  for (const state of [...states].reverse()) {
    if (state.existed) continue;
    try {
      const identity = await assertMemoryRootStable(state.root);
      const entries = await fsp.readdir(state.root);
      if (entries.length === 0) {
        // rmdir removes only an empty directory; rm without recursive rejects
        // directories, while recursive removal could delete a concurrent file.
        await fsp.rmdir(state.root);
        try { await assertMemoryRootStable(state.root, identity); } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
        }
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
  }
}

function memoryFilePath(root: string, name: string): string {
  assertMemoryName(name);
  const file = path.join(root, name);
  assertWithin(root, file);
  return file;
}

async function removeMemoryFile(root: string, name: string): Promise<void> {
  const identity = await assertMemoryRootStable(root);
  await removeTransactionFile(memoryFilePath(root, name));
  await assertMemoryRootStable(root, identity);
}

async function writeMemoryFileInRoot(root: string, name: string, content: string): Promise<void> {
  const identity = await assertMemoryRootStable(root);
  await writeMemoryFile(memoryFilePath(root, name), content);
  await assertMemoryRootStable(root, identity);
}

function scopeEntries(raw: unknown, label: string): { name: string; classification?: "safe" | "private" }[] {
  if (!Array.isArray(raw) || raw.length > 256) throw new Error(`Consolidation plan has an invalid ${label}`);
  return raw.map((entry) => {
    const item = typeof entry === "object" && entry !== null && !Array.isArray(entry) ? entry as Record<string, unknown> : undefined;
    const name = typeof entry === "string" ? entry : item?.name ?? item?.file ?? item?.filename;
    assertMemoryName(name);
    const classification = item?.classification ?? item?.visibility ?? item?.privacy;
    if (classification !== undefined && classification !== "safe" && classification !== "private") {
      throw new Error(`Invalid inventory classification for ${name}`);
    }
    return { name, ...(classification === undefined ? {} : { classification }) };
  });
}

export type NewMemoryKind = "preference" | "project";
export type NewMemoryClassification = "safe" | "private";

export interface NewMemoryEvidence {
  index: number;
  quote: string;
  role: "user" | "toolResult";
}

export interface NewMemoryProposal {
  name: string;
  kind: NewMemoryKind;
  classification: NewMemoryClassification;
  content: string;
  evidence: NewMemoryEvidence[];
}

const SENSITIVE_MEMORY_PATTERNS: readonly RegExp[] = [
  /-----BEGIN [^-\r\n]*PRIVATE KEY-----/i,
  // Provider formats keep their own separator and a body ordinary identifiers
  // never reach, so names like skills-host-agnostic or gh-pages stay ordinary.
  /\bsk-[A-Za-z0-9_-]{16,}\b/i,
  /\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{16,}\b/i,
  /\bxox[abprs]-[A-Za-z0-9-]{10,}\b/i,
  /\bAIza[0-9A-Za-z_-]{20,}\b/i,
  /\bnpm_[A-Za-z0-9]{30,}\b/i,
  /\bpypi-[A-Za-z0-9_-]{20,}\b/i,
  /\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{10,}\b/i,
  /\bbearer\s+[A-Za-z0-9._~+/=-]{16,}\b/i,
  /\bAKIA[0-9A-Z]{16}\b/i,
];

/** An assigned value must be long enough to be a credential: prose ("token is
 * short-lived") assigns nothing. A credential-named assignment has no URL
 * exemption: a URL under such a key can itself be the credential. */
const ASSIGNED_CREDENTIAL_PATTERN = /(?<![A-Za-z])(?<key>["']?(?:api[_ -]?(?:key|token|secret)|access[_ -]?token|auth(?:orization)?|bearer|client[_ -]?secret|credential|password|passwd|secret|token)["']?)\s*(?::|=)\s*(?<value>[^\s,;]{8,})/gi;

/** A delimited value hides punctuation the plain pattern stops at, so a quoted
 * value under either a quoted or an unquoted credential key is matched here
 * with a quote-aware value class and judged by the same placeholder rule. The
 * value admits the other quote type and backslash escapes, so a secret containing
 * `,`, `;`, `?`, `'` or `//` cannot stop matching early and be allowed. There is
 * no URL exemption; the placeholder rule is the only exemption. */
const QUOTED_ASSIGNED_CREDENTIAL_PATTERN = /(?<![A-Za-z])(?<key>["']?(?:api[_ -]?(?:key|token|secret)|access[_ -]?token|auth(?:orization)?|bearer|client[_ -]?secret|credential|password|passwd|secret|token)["']?)\s*(?::|=)\s*(?<value>"(?:[^"\\\r\n]|\\.){7,}"|'(?:[^'\\\r\n]|\\.){7,}')/gi;

/** A credential-named key with an assigned value has no URL exemption. A URL
 * under such a key can itself be the credential (a webhook, a connection string,
 * a token-bearing link), and no shape test separates that from an ordinary URL:
 * every scheme list and userinfo test was bypassed in review. The documented
 * placeholder rule stays the only exemption, and it covers code, env and
 * expression references. */

/** A credential-named structured key with an assigned value is refused without
 * the documentation-placeholder exemption that applies to prose text. A parsed
 * object member is not a tracked-source sample, and it is exactly where an
 * assigned secret travels. Shared by the Memory guard and the Jev preflight so
 * both detectors classify one object identically. */
const CREDENTIAL_KEY_PATTERN = /^(?:api(?:key|token|secret)|accesstoken|auth(?:orization)?|bearer|clientsecret|credentials?|password|passwd|secret|token)$/i;
export function credentialNamedKeyAssignsValue(key: string, assigned: string): boolean {
  const text = assigned.trim();
  return text.length >= 8 && CREDENTIAL_KEY_PATTERN.test(key.replace(/[_ -]/g, ""));
}

/** Documentation-style placeholders, so a tracked source sample or doc snippet
 * does not refuse a whole review. A realistic assigned value stays sensitive. */
const PLACEHOLDER_CREDENTIAL_VALUES = new Set([
  "password", "passwd", "pass", "secret", "token", "credential", "credentials", "apikey", "apitoken",
  "accesstoken", "clientsecret", "example", "dummy", "placeholder", "changeme", "redacted", "yourpassword",
  "yourtoken", "notasecret", "string", "value", "none", "null", "undefined",
  "fixture", "mock", "fake", "stub", "default",
]);

/** A code, env or expression reference, never a literal secret. The expression
 * clause requires whitespace around its operator so a password that merely
 * contains `?` or `&&` is not read as an expression; failing closed here only
 * refuses more, never less. */
const CODE_OR_ENV_PATTERN = /^(?:\(?\s*(?:process\.env|os\.environ|System\.getenv|Deno\.env|\$[A-Z_]+|\$\{[A-Z_]+\})|(?:config|options|opts|params|props|settings|this|self|ctx)\.[A-Za-z0-9_]+|\(|.*\s(?:\?|\|\||&&|\+(?=\s*["'])))/i;

/** Documentation-style placeholders are not credentials: a tracked source
 * sample, doc snippet or JSON config sample must not refuse a whole review, while
 * a realistic assigned value stays sensitive. Both the Memory guard and the Jev
 * preflight call this rule so the same text cannot be refused by one detector and
 * allowed by the other. Quoted JSON keys and values are accepted, and quotes are
 * stripped before the placeholder comparison. */
export function placeholderCredentialValue(key: string, assigned: string): boolean {
  const trimmed = assigned.trim();
  if (CODE_OR_ENV_PATTERN.test(trimmed)) return true;
  const unquoted = trimmed.replace(/^["'`\\]+|["'`\\]+$/g, "");
  const value = unquoted.toLowerCase().replace(/[^a-z0-9]/g, "");
  if (!value) return true;
  if (PLACEHOLDER_CREDENTIAL_VALUES.has(value)) return true;
  if (new Set(value).size === 1) return true;
  if (/^(?:fixture|mock|fake|stub|test|dummy|example|sample)[0-9a-z_]*$/.test(value)) return true;
  const keyWord = key.toLowerCase().replace(/[^a-z0-9]/g, "");
  return value.startsWith(keyWord) && /^[0-9]*(?:value|string|here|example|placeholder)?$/.test(value.slice(keyWord.length));
}

/** A credential-named key that assigns a structured literal assigns a
 * configuration snippet, not a credential: `apiKey:{source:"file"}` names no
 * secret. Judge the snippet's own members instead, so a secret inside it stays
 * refused. A document can wrap a long line, so an unbalanced literal counts as
 * a snippet as well. */
const STRUCTURED_LITERAL_OPENERS = new Set(["{", "["]);
const MAX_CREDENTIAL_LITERAL_DEPTH = 4;
const MAX_CREDENTIAL_LITERAL_CHARS = 4_096;

function snippetOf(text: string, start: number): string {
  return text.slice(start, start + MAX_CREDENTIAL_LITERAL_CHARS);
}

function containsAssignedCredentialMaterial(value: string, depth = 0): boolean {
  for (const match of value.matchAll(ASSIGNED_CREDENTIAL_PATTERN)) {
    const assigned = match.groups?.value ?? "";
    if (STRUCTURED_LITERAL_OPENERS.has(assigned.charAt(0))) {
      const start = (match.index ?? 0) + match[0].length - assigned.length;
      if (depth < MAX_CREDENTIAL_LITERAL_DEPTH && containsAssignedCredentialMaterial(snippetOf(value, start), depth + 1)) return true;
      continue;
    }
    if (!placeholderCredentialValue(match.groups?.key ?? "", assigned)) return true;
  }
  for (const match of value.matchAll(QUOTED_ASSIGNED_CREDENTIAL_PATTERN)) {
    if (!placeholderCredentialValue(match.groups?.key ?? "", match.groups?.value ?? "")) return true;
  }
  return false;
}

export function containsSensitiveMemoryMaterial(value: string): boolean {
  // Judge decoded values, not JSON escape sequences adjoining a code/env
  // reference. Encoding must neither invent a secret nor hide a real one.
  let decoded: unknown;
  try { decoded = JSON.parse(value); } catch { /* ordinary source/prose */ }
  if (decoded !== undefined) {
    if (typeof decoded === "string") return containsSensitiveMemoryMaterial(decoded);
    if (decoded && typeof decoded === "object") {
      const pending: unknown[] = [decoded];
      while (pending.length) {
        const current = pending.pop();
        if (typeof current === "string" && containsSensitiveMemoryMaterial(current)) return true;
        if (!current || typeof current !== "object") continue;
        for (const [key, child] of Object.entries(current)) {
          if (containsSensitiveMemoryMaterial(key)) return true;
          // A parsed member with a credential-named key is judged strictly, like
          // the preflight's structured-key rule; prose text keeps the placeholder
          // rule on the string path.
          if (typeof child === "string" && credentialNamedKeyAssignsValue(key, child)) return true;
          pending.push(child);
        }
      }
      return false;
    }
    return false;
  }
  return SENSITIVE_MEMORY_PATTERNS.some((pattern) => pattern.test(value)) || containsAssignedCredentialMaterial(value);
}

function normalizeEvidenceText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function snapshotEntryRecord(entry: unknown): Record<string, unknown> | undefined {
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return undefined;
  const record = entry as Record<string, unknown>;
  if (record.message && typeof record.message === "object" && !Array.isArray(record.message)) {
    return record.message as Record<string, unknown>;
  }
  return record;
}

export function snapshotEntryRole(entry: unknown): string | undefined {
  return snapshotEntryRecord(entry)?.role as string | undefined;
}

/** Original tool-produced diff, not assistant arguments or a reconstructed file.
 * It describes this successful edit only; later evidence and semantic review
 * still determine whether a claim describes the current source. */
export function snapshotEditPatchText(entry: unknown): string | undefined {
  const source = snapshotEntryRecord(entry);
  if (source?.role !== "toolResult" || source.toolName !== "edit" || source.isError !== false) return;
  const details = source.details;
  if (!details || typeof details !== "object" || Array.isArray(details)) return;
  const patch = (details as Record<string, unknown>).patch;
  return typeof patch === "string" ? patch : undefined;
}

function snapshotEntryText(entry: unknown): string {
  const record = snapshotEntryRecord(entry);
  const content = record?.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content.map((part) => {
      if (typeof part === "string") return part;
      if (!part || typeof part !== "object" || Array.isArray(part)) return JSON.stringify(part) ?? "";
      const text = (part as Record<string, unknown>).text;
      return typeof text === "string" ? text : JSON.stringify(part) ?? "";
    }).join("\n");
  }
  return JSON.stringify(entry) ?? "";
}

function snapshotContainsQuote(entry: unknown, quote: string): boolean {
  // Diff markers and whitespace are evidence. Never normalize them into a
  // quotation of the resulting file, or concatenate across result fields.
  if (snapshotEditPatchText(entry)?.includes(quote)) return true;
  const normalizedQuote = normalizeEvidenceText(quote);
  if (!normalizedQuote) return false;
  const text = normalizeEvidenceText(snapshotEntryText(entry));
  if (text.includes(normalizedQuote)) return true;
  const encoded = JSON.stringify(quote);
  return typeof encoded === "string" && text.includes(normalizeEvidenceText(encoded.slice(1, -1)));
}

function snapshotEntries(snapshot: unknown): unknown[] {
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)) return [];
  const entries = (snapshot as Record<string, unknown>).entries;
  return Array.isArray(entries) ? entries : [];
}

function newMemoryRawValue(plan: Record<string, unknown>): unknown {
  return plan.newMemories;
}

function newMemoryName(value: unknown, label: string): string {
  const name = value;
  assertMemoryName(name);
  if (name.length > MAX_NEW_MEMORY_NAME_CHARS) throw new Error(`${label} exceeds ${MAX_NEW_MEMORY_NAME_CHARS} characters`);
  return name;
}

function newMemoryKind(value: unknown, label: string): NewMemoryKind {
  if (value === "preference") return value;
  if (value === "project") return value;
  throw new Error(`${label} must be preference or project`);
}

/**
 * First-person preference stated as such.
 *
 * The parent already refuses a plan that declares `preference` with a `safe`
 * classification, so a declared contradiction cannot leak. What it could not
 * catch was a *mislabel*: the planner declaring `project` and `safe` for
 * something the user stated as a personal preference. The live smoke
 * reproduced this three runs in a row — a preference reached the project
 * surface — because a guard on the declared kind is only as strong as the
 * planner's honesty about it.
 *
 * This is a surface pattern, in the same idiom the package already uses to
 * decide which phases to run (`DURABLE_USER_PATTERN` in learning-efficiency).
 * It only ever *demotes* safe to private, so a false positive costs
 * collaboration and never costs privacy. The failure mode of getting this
 * wrong is one direction only.
 */
const STATED_PREFERENCE_PATTERN =
  /\b(?:i|we)\s+(?:prefer|want|like|hate|dislike|always want|always prefer)\b|(?:i['’]m|i am)\s+(?:not\s+)?(?:a\s+)?fan\b|(?:the\s+)?user\s+(?:prefers|wants|likes|hates|dislikes|asks for)\b|我(?:更)?(?:喜欢|不喜欢|想要|不想|偏好|希望)|我(?:不喜欢|讨厌)/iu;

export function statesPreferenceAsSuch(text: string): boolean {
  return STATED_PREFERENCE_PATTERN.test(text);
}

function newMemoryClassification(value: unknown, kind: NewMemoryKind, label: string, statements: readonly string[] = []): NewMemoryClassification {
  if (value === undefined) return kind === "preference" ? "private" : "safe";
  if (value !== "safe" && value !== "private") throw new Error(`${label} must be safe or private`);
  // Both a declared contradiction and a stated preference resolve the same way:
  // the knowledge is kept and made private.
  //
  // This used to reject a plan declaring `preference` with `safe`, on the
  // reasoning that the planner had not thought. But the knowledge was never in
  // doubt — the user did state a preference — so rejecting threw away real
  // learning over a label error and aborted the phase. With no external
  // judgment surface to reconcile it, the parent has to: the planner is
  // inconsistent about labels far more reliably than it is about knowledge.
  if (value === "safe" && (kind === "preference" || statements.some(statesPreferenceAsSuch))) return "private";
  return value;
}

function evidenceIndex(value: Record<string, unknown>, label: string): number {
  const raw = value.index;
  if (typeof raw !== "number" || !Number.isSafeInteger(raw) || raw < 0) throw new Error(`${label} must be a non-negative snapshot entry index`);
  return raw;
}

function normalizeNewMemoryEvidence(raw: unknown, entries: readonly unknown[], label: string): NewMemoryEvidence[] {
  if (!Array.isArray(raw) || raw.length === 0 || raw.length > MAX_NEW_MEMORY_EVIDENCE) {
    throw new Error(`${label} must contain 1..${MAX_NEW_MEMORY_EVIDENCE} entries`);
  }
  const memoryReferences = memoryReferenceResults(entries);
  return raw.map((value, index) => {
    const itemLabel = `${label}[${index}]`;
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${itemLabel} must be an object`);
    const item = value as Record<string, unknown>;
    const entryIndex = evidenceIndex(item, itemLabel);
    const entry = entries[entryIndex];
    if (entry === undefined) throw new Error(`${itemLabel} points outside the immutable snapshot`);
    const quote = item.quote;
    if (typeof quote !== "string" || quote.trim().length === 0 || quote.length > MAX_NEW_MEMORY_QUOTE_CHARS) {
      throw new Error(`${itemLabel}.quote must be 1..${MAX_NEW_MEMORY_QUOTE_CHARS} characters`);
    }
    if (containsSensitiveMemoryMaterial(quote)) throw new Error(`${itemLabel}.quote contains sensitive material`);
    const role = snapshotEntryRole(entry);
    if (role !== "user" && role !== "toolResult") throw new Error(`${itemLabel} must cite a user or tool result snapshot entry`);
    if (memoryReferences.has(entryIndex)) throw new Error(`${itemLabel}: Memory readback is context, not independent evidence`);
    if (!snapshotContainsQuote(entry, quote)) throw new Error(`${itemLabel}.quote is not present in the cited snapshot entry`);
    if (item.role !== undefined && item.role !== role) throw new Error(`${itemLabel}.role does not match the cited snapshot entry`);
    return { index: entryIndex, quote, role };
  });
}

/** Shared exact-quote/role check for semantic evidence preparation. No writes
 * or permission inference; mutation callers still validate their complete plan. */
export function normalizeSnapshotEvidence(raw: unknown, snapshot: unknown): NewMemoryEvidence[] {
  return normalizeNewMemoryEvidence(raw, snapshotEntries(snapshot), "semantic evidence");
}

/** Discovery metadata cannot replace the knowledge delivered by an entry read.
 * Legacy plain bodies remain valid; existing files are not migrated here.
 */
export function assertMemoryBodyContent(content: string, label: string): void {
  const document = content.replace(/^\uFEFF+/, "");
  const frontmatter = /^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/.exec(document);
  const body = frontmatter ? document.slice(frontmatter[0].length) : document;
  if (!body.trim()) throw new Error(`${label} requires a non-empty Memory body; discovery metadata is not a knowledge body`);
}

/** Validate and normalize context-derived files before any filesystem mutation. */
export function normalizeNewMemoryProposals(
  plan: unknown,
  snapshot: unknown,
  selected: readonly string[] = [],
): NewMemoryProposal[] {
  if (!plan || typeof plan !== "object" || Array.isArray(plan)) throw new Error("Consolidation plan must be an object");
  const rawValue = newMemoryRawValue(plan as Record<string, unknown>);
  const raw = rawValue === undefined ? [] : rawValue;
  if (!Array.isArray(raw)) throw new Error("newMemories must be an array");
  if (raw.length > MAX_NEW_MEMORY_PROPOSALS) throw new Error(`newMemories exceeds the maximum of ${MAX_NEW_MEMORY_PROPOSALS}`);
  if (raw.length === 0) return [];
  const entries = snapshotEntries(snapshot);
  if (!snapshot || typeof snapshot !== "object" || (snapshot as Record<string, unknown>).contextEnabled !== true) {
    throw new Error("newMemories require an enabled immutable context snapshot");
  }
  if (entries.length === 0) throw new Error("newMemories require at least one immutable context entry");
  const selectedNames = new Set(selected.map((name) => name.toLowerCase()));
  const names = new Set<string>();
  let totalBytes = 0;
  return raw.map((value, index) => {
    const label = `newMemories[${index}]`;
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label} must be an object`);
    const item = value as Record<string, unknown>;
    const name = newMemoryName(item.name, `${label}.name`);
    const key = name.toLowerCase();
    if (selectedNames.has(key)) throw new Error(`${label}: new memory name overlaps selected scope: ${name}`);
    if (names.has(key)) throw new Error(`${label}: duplicate new memory name: ${name}`);
    names.add(key);
    const kind = newMemoryKind(item.kind, `${label}.kind`);
    const content = item.content;
    if (typeof content !== "string" || content.length === 0) throw new Error(`${label}.content must be a non-empty string`);
    assertMemoryBodyContent(content, `${label}.content`);
    const contentBytes = Buffer.byteLength(content, "utf8");
    if (contentBytes > MAX_MEMORY_BYTES) throw new Error(`${label}.content exceeds ${MAX_MEMORY_BYTES} bytes`);
    if (containsSensitiveMemoryMaterial(content)) throw new Error(`${label}.content contains sensitive material`);
    totalBytes += contentBytes;
    if (totalBytes > MAX_NEW_MEMORY_TOTAL_BYTES) throw new Error(`newMemories content exceeds ${MAX_NEW_MEMORY_TOTAL_BYTES} bytes`);
    const evidence = normalizeNewMemoryEvidence(item.evidence, entries, `${label}.evidence`);
    // Classification is resolved after the evidence, because the demotion reads
    // the proposal's own wording as well as the quotes it rests on.
    const classification = newMemoryClassification(
      item.classification,
      kind,
      `${label}.classification`,
      [String(content), ...evidence.map((entry) => String(entry.quote ?? ""))],
    );
    return { name, kind, classification, content, evidence };
  });
}

function newMemoryNames(value: readonly NewMemoryProposal[]): string[] {
  return value.map((proposal) => proposal.name).sort((left, right) => left.localeCompare(right));
}

export interface AppliedMemoryResult {
  selected: string[];
  created: string[];
  changed: string[];
  finalState: { harness: MemoryHashes; public: MemoryHashes };
}

export async function applyConsolidationPlan(
  run: ConsolidationRun,
  plan: unknown,
  isActive?: () => boolean,
  verifyApplied?: (applied: AppliedMemoryResult) => Promise<void>,
): Promise<AppliedMemoryResult> {
  const ensureActive = (): void => {
    if (isActive && !isActive()) throw new Error("Memory consolidation was cancelled before apply completed.");
  };
  const identityErrors = validatePlanIdentity(plan, run.manifest);
  if (identityErrors.length) throw new Error(identityErrors.join("; "));
  if (!plan || typeof plan !== "object" || Array.isArray(plan)) throw new Error("Consolidation plan must be an object");
  const value = plan as Record<string, unknown>;
  const artifacts = value.artifacts && typeof value.artifacts === "object" && !Array.isArray(value.artifacts) ? value.artifacts as Record<string, unknown> : undefined;
  const rawInventory = value.inventory ?? artifacts?.inventory;
  const hasInventory = rawInventory !== undefined;
  const inventoryEntries = hasInventory ? scopeEntries(rawInventory, "inventory") : undefined;
  const rawSelected = value.selected;
  if (hasInventory && rawSelected === undefined) throw new Error("Consolidation plan has no parent-bound selected scope");
  if (!hasInventory && Array.isArray(rawSelected) && rawSelected.length > 0) {
    throw new Error("Consolidation plan must bind selected scope to inventory");
  }
  const selectedEntries = rawSelected === undefined ? inventoryEntries ?? [] : scopeEntries(rawSelected, "selected scope");
  const selectedByKey = new Map<string, string>();
  for (const entry of selectedEntries) {
    const key = entry.name.toLowerCase();
    if (selectedByKey.has(key)) throw new Error("Consolidation plan selects duplicate memory names");
    selectedByKey.set(key, entry.name);
  }
  if (inventoryEntries) {
    const inventoryByKey = new Map<string, { name: string; classification?: "safe" | "private" }>();
    for (const entry of inventoryEntries) {
      const key = entry.name.toLowerCase();
      if (inventoryByKey.has(key)) throw new Error("Consolidation inventory contains duplicate memory names");
      inventoryByKey.set(key, entry);
    }
    if (inventoryByKey.size !== selectedByKey.size || [...inventoryByKey].some(([key, entry]) => selectedByKey.get(key) !== entry.name)) {
      throw new Error("Consolidation selected scope does not match parent-derived inventory");
    }
  }
  const selected = [...selectedByKey.values()];
  let newProposals: NewMemoryProposal[] = [];
  if (newMemoryRawValue(value) !== undefined) {
    const snapshotPath = run.paths.snapshotFile;
    if (!snapshotPath) throw new Error("newMemories require the immutable snapshot path");
    const snapshotBytes = await readBoundedRegularFile(snapshotPath, MAX_SNAPSHOT_BYTES);
    if (sha256Digest(snapshotBytes) !== run.manifest.snapshotDigest) {
      throw new Error("newMemories snapshot digest does not match the consolidation run");
    }
    let snapshot: unknown;
    try {
      snapshot = JSON.parse(snapshotBytes.toString("utf8")) as unknown;
    } catch {
      throw new Error("newMemories snapshot is not valid JSON");
    }
    if (
      !snapshot || typeof snapshot !== "object" || Array.isArray(snapshot) ||
      (snapshot as Record<string, unknown>).schemaVersion !== CONSOLIDATION_SCHEMA_VERSION ||
      (snapshot as Record<string, unknown>).runId !== run.manifest.runId ||
      (snapshot as Record<string, unknown>).scopeKey !== run.manifest.scopeKey
    ) {
      throw new Error("newMemories snapshot identity does not match the consolidation run");
    }
    newProposals = normalizeNewMemoryProposals(value, snapshot, selected);
  }
  const operations = value.operations ?? [];
  if (!Array.isArray(operations) || operations.length > selected.length) throw new Error("Consolidation plan has invalid operations");
  const operationKeys = new Set<string>();
  const normalizedOperations: NormalizedMemoryOperation[] = operations.map((operation) => {
    if (!operation || typeof operation !== "object" || Array.isArray(operation)) throw new Error("Consolidation operation must be an object");
    const item = operation as Record<string, unknown>;
    const operationName = item.name ?? item.filename ?? item.targetName;
    assertMemoryName(operationName);
    const key = operationName.toLowerCase();
    const selectedName = selectedByKey.get(key);
    if (!selectedName || selectedName !== operationName) throw new Error(`Operation is outside selected scope: ${operationName}`);
    if (operationKeys.has(key)) throw new Error(`Consolidation operation is duplicated: ${operationName}`);
    operationKeys.add(key);
    const kind = item.kind;
    const classification = item.classification;
    if (kind !== "create" && kind !== "rewrite" && kind !== "delete") throw new Error(`Invalid operation kind for ${operationName}`);
    if (classification !== "safe" && classification !== "private") throw new Error(`Invalid classification for ${operationName}`);
    const inventoryEntry = inventoryEntries?.find((entry) => entry.name.toLowerCase() === key);
    if (inventoryEntry?.classification !== undefined && inventoryEntry.classification !== classification) {
      throw new Error(`Operation classification disagrees with inventory for ${operationName}`);
    }
    if (kind !== "delete" && typeof item.content !== "string") throw new Error(`Missing content for ${operationName}`);
    return { name: operationName, kind, classification, ...(kind !== "delete" ? { content: item.content as string } : {}) };
  });

  const publicDir = run.manifest.publicDir;
  const roots = [run.manifest.harnessDir, ...(publicDir ? [publicDir] : [])];
  const rootStates = await Promise.all(roots.map(captureRootState));
  const currentSourceHashes = { harness: await hashMemoryRoot(run.manifest.harnessDir), public: publicDir ? await hashMemoryRoot(publicDir) : {} };
  if (digest(currentSourceHashes) !== digest(run.manifest.sourceHashes)) throw new Error("Memory sources changed after the consolidation snapshot; refusing stale apply.");
  const sourceNames = new Set([
    ...Object.keys(currentSourceHashes.harness),
    ...Object.keys(currentSourceHashes.public),
  ].map((name) => name.toLowerCase()));
  for (const proposal of newProposals) {
    if (sourceNames.has(proposal.name.toLowerCase())) {
      throw new Error(`newMemories proposal would overwrite an existing memory: ${proposal.name}`);
    }
  }
  await ensureMemoryRoot(run.manifest.harnessDir);
  if (publicDir) await ensureMemoryRoot(publicDir);
  const privateNames = await readPrivateIndexNames(run.manifest.harnessDir);
  const publicPrivateNames = publicDir ? await readPrivateIndexNames(publicDir) : new Set<string>();
  if (publicPrivateNames.size > 0) throw new Error("Public memory index contains harness-only entries.");
  const transactionFiles = [...new Set([
    ...selected.flatMap((name) => [memoryFilePath(run.manifest.harnessDir, name), ...(publicDir ? [memoryFilePath(publicDir, name)] : [])]),
    ...newProposals.flatMap((proposal) => [memoryFilePath(run.manifest.harnessDir, proposal.name), ...(publicDir ? [memoryFilePath(publicDir, proposal.name)] : [])]),
    path.join(run.manifest.harnessDir, "MEMORY.md"),
    ...(publicDir ? [path.join(publicDir, "MEMORY.md")] : []),
  ])];
  const snapshots = await captureMemoryFiles(transactionFiles);
  const snapshotSourceHashes = { harness: await hashMemoryRoot(run.manifest.harnessDir), public: publicDir ? await hashMemoryRoot(publicDir) : {} };
  if (digest(snapshotSourceHashes) !== digest(run.manifest.sourceHashes)) throw new Error("Memory sources changed while capturing the consolidation transaction; refusing stale apply.");
  for (const proposal of newProposals) {
    const key = proposal.name.toLowerCase();
    const existed = snapshots.some((snapshot) => snapshot.existed && path.basename(snapshot.file).toLowerCase() === key);
    if (existed) throw new Error(`newMemories proposal would overwrite an existing memory: ${proposal.name}`);
  }
  return withOwnedFileTransaction(snapshots, async () => {
  try {
    ensureActive();
    if (selected.length === 0 && newProposals.length === 0) {
      await ensureMemoryIndex(run.manifest.harnessDir, privateNames);
      ensureActive();
      if (publicDir) await ensureMemoryIndex(publicDir, new Set());
    } else {
      for (const operation of normalizedOperations) {
        ensureActive();
        if (operation.kind === "delete") {
          await removeMemoryFile(run.manifest.harnessDir, operation.name);
          privateNames.delete(operation.name.toLowerCase());
          ensureActive();
          if (publicDir) await removeMemoryFile(publicDir, operation.name);
        } else {
          await writeMemoryFileInRoot(run.manifest.harnessDir, operation.name, operation.content!);
          ensureActive();
          if (operation.classification === "safe") {
            privateNames.delete(operation.name.toLowerCase());
            if (publicDir) await writeMemoryFileInRoot(publicDir, operation.name, operation.content!);
          } else {
            privateNames.add(operation.name.toLowerCase());
            if (publicDir) await removeMemoryFile(publicDir, operation.name);
          }
        }
      }
      for (const proposal of newProposals) {
        ensureActive();
        await writeMemoryFileInRoot(run.manifest.harnessDir, proposal.name, proposal.content);
        ensureActive();
        if (proposal.classification === "safe") {
          privateNames.delete(proposal.name.toLowerCase());
          if (publicDir) await writeMemoryFileInRoot(publicDir, proposal.name, proposal.content);
        } else {
          privateNames.add(proposal.name.toLowerCase());
          if (publicDir) await removeMemoryFile(publicDir, proposal.name);
        }
      }
      ensureActive();
      await updateMemoryIndex(run.manifest.harnessDir, privateNames, ensureActive);
      ensureActive();
      if (publicDir) await updateMemoryIndex(publicDir, new Set(), ensureActive);
    }
    ensureActive();
    const afterFiles = await captureMemoryFiles(transactionFiles);
    const changed = new Set(afterFiles.filter((after, index) => {
      const before = snapshots[index];
      return before.existed !== after.existed || before.mode !== after.mode || (before.existed && !before.content!.equals(after.content!));
    }).map(file => path.basename(file.file)).filter(name => name !== "MEMORY.md"));
    const applied: AppliedMemoryResult = {
      selected: [...selected].sort(),
      created: newMemoryNames(newProposals),
      changed: [...changed].sort(),
      finalState: { harness: await hashMemoryRoot(run.manifest.harnessDir), public: publicDir ? await hashMemoryRoot(publicDir) : {} },
    };
    // Keep final parent verification inside the existing rollback boundary.
    ensureActive();
    await verifyApplied?.(applied);
    ensureActive();
    return applied;
  } catch (error) {
    try {
      await restoreMemoryFiles(snapshots);
      await removeNewEmptyRoots(rootStates);
    } catch (rollbackError) {
      throw new Error(`${(error as Error).message}; memory rollback failed: ${(rollbackError as Error).message}`);
    }
    throw error;
  }
  });
}

/** Diagnostic retention must inspect damaged inner JSON too, before a later
 * privacy gate can reject the candidate. Unknown deep encoding stays hash-only. */
export function childOutputContainsSensitiveMaterial(stdout: string, plan: unknown): boolean {
  const pending: unknown[] = [plan];
  for (const line of stdout.split(/\r?\n/)) {
    if (!line.trim()) continue;
    pending.push(line);
    try { pending.push(JSON.parse(line)); } catch { /* scan damaged raw text */ }
  }
  while (pending.length) {
    const value = pending.pop();
    if (typeof value === "string") {
      let decoded = value;
      for (let round = 0; round < 5; round++) {
        try { if (containsSensitiveMemoryMaterial(decoded)) return true; }
        catch { return true; }
        const next = decoded.replace(/\\(?:u[0-9a-f]{4}|["\\/bfnrt])/gi, match => {
          try { return JSON.parse(`"${match}"`) as string; } catch { return match; }
        });
        if (next === decoded) break;
        if (round === 4) return true;
        decoded = next;
      }
    } else if (value && typeof value === "object") {
      for (const [key, child] of Object.entries(value)) pending.push(key, child);
    }
  }
  return false;
}
