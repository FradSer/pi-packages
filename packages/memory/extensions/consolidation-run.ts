import * as crypto from "node:crypto";
import * as fsp from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import type { ChildProcess } from "node:child_process";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { terminateChildProcess } from "@fradser/pi-kit";
import { resolveMemoryPaths, type MemoryPaths } from "./memory-paths";
import { isMemoryFilename } from "./memory-files";

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

export interface ConsolidationSnapshot {
  schemaVersion: typeof CONSOLIDATION_SCHEMA_VERSION;
  runId: string;
  scopeKey: string;
  capturedAt: string;
  source: SnapshotSource;
  contextEnabled: boolean;
  entries: unknown[];
  branchEntries?: unknown[];
  contextEntries?: unknown[];
}

export interface ContextManifest {
  schemaVersion: typeof CONSOLIDATION_SCHEMA_VERSION;
  runId: string;
  scopeKey: string;
  contextEnabled: boolean;
  mode: "snapshot" | "no-context";
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
  publicDir: string;
  runDir: string;
  contextEnabled: boolean;
  contextMode: "snapshot" | "no-context";
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

async function readBoundedRegularFile(filePath: string, maxBytes: number): Promise<Buffer> {
  let handle: fsp.FileHandle | undefined;
  try {
    handle = await fsp.open(filePath, fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW ?? 0));
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
    handle = await fsp.open(filePath, fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW ?? 0));
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
    await fsp.rename(temporary, filePath);
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
  };
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

export async function writeNoContextManifest(paths: ConsolidationRunPaths, reason = "no-context"): Promise<ContextManifest> {
  await ensureConsolidationRunDir(paths);
  const manifest: ContextManifest = {
    schemaVersion: CONSOLIDATION_SCHEMA_VERSION, runId: paths.runId, scopeKey: paths.memory.scopeKey,
    contextEnabled: false, mode: "no-context", entryCount: 0, createdAt: new Date().toISOString(), reason,
  };
  await writeJsonAtomic(paths.contextManifestFile, manifest);
  return manifest;
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
  const harnessStat = await fsp.lstat(memory.harnessDir).then(
    () => true,
    (error: unknown) => {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      return false;
    },
  );
  const harnessFiles = await listMemoryRootFiles(memory.harnessDir);
  const publicFiles = await listMemoryRootFiles(memory.publicDir);
  if (!harnessStat && harnessFiles.size === 0) {
    // No canonical root yet: import the public mirror instead of deleting it.
    if (publicFiles.size === 0) return { repaired: [], removed: [] };
    await ensureMemoryRoot(memory.harnessDir);
    for (const [, publicName] of [...publicFiles].sort(([a], [b]) => a.localeCompare(b))) {
      const content = (await readBoundedRegularFile(path.join(memory.publicDir, publicName), MAX_MEMORY_BYTES)).toString("utf8");
      await writeMemoryFile(path.join(memory.harnessDir, publicName), content);
    }
    await updateMemoryIndex(memory.harnessDir, new Set());
    await updateMemoryIndex(memory.publicDir, new Set());
    return {
      repaired: [...publicFiles.values()].sort().map((name) => ({ name, direction: "public-to-harness" as const })),
      removed: [],
    };
  }
  const removed = new Set<string>();
  const repairLog = new Map<string, MirrorRepair>();
  const privateNames = await readPrivateIndexNames(memory.harnessDir);
  const copyBytes = async (direction: MirrorRepair["direction"], name: string, source: string, target: string): Promise<void> => {
    const content = (await readBoundedRegularFile(source, MAX_MEMORY_BYTES)).toString("utf8");
    await writeMemoryFile(target, content);
    repairLog.set(name, { name, direction });
  };
  // Newer mtime wins for drifted pairs; ties fall back to the harness copy.
  const copyNewer = async (harnessName: string, publicName: string): Promise<void> => {
    const harnessFile = path.join(memory.harnessDir, harnessName);
    const publicFile = path.join(memory.publicDir, publicName);
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
      await fsp.rm(path.join(memory.publicDir, publicName), { force: true });
      removed.add(publicName);
      continue;
    }
    const harnessHash = await sha256File(path.join(memory.harnessDir, harnessName), MAX_MEMORY_BYTES);
    const publicHash = await sha256File(path.join(memory.publicDir, publicName), MAX_MEMORY_BYTES);
    if (harnessHash === publicHash) continue;
    await copyNewer(harnessName, publicName);
  }
  for (const [key, harnessName] of [...harnessFiles].sort(([a], [b]) => a.localeCompare(b))) {
    if (privateNames.has(key) || publicFiles.has(key)) continue;
    await copyBytes("harness-to-public", harnessName, path.join(memory.harnessDir, harnessName), path.join(memory.publicDir, harnessName));
  }
  if (removed.size > 0 || repairLog.size > 0 || harnessFiles.size > 0 || publicFiles.size > 0) {
    await ensureMemoryRoot(memory.harnessDir);
    await ensureMemoryRoot(memory.publicDir);
    await updateMemoryIndex(memory.harnessDir, privateNames);
    await updateMemoryIndex(memory.publicDir, new Set());
  }
  return { repaired: [...repairLog.values()].sort((left, right) => left.name.localeCompare(right.name)), removed: [...removed].sort() };
}

export async function createConsolidationRun(ctx: ExtensionContext, cwd: string, noContext = false): Promise<ConsolidationRun> {
  const paths = resolveConsolidationRunPaths(cwd);
  const lock = await acquireConsolidationLock(paths, { runId: paths.runId, cwd });
  try {
    await ensureConsolidationRunDir(paths);
    const normalization = await normalizeMirrorDrift(paths.memory);
    const captured = noContext ? undefined : await captureConsolidationSnapshot(ctx, paths);
    const contextManifest = captured?.manifest ?? await writeNoContextManifest(paths);
    const snapshot = captured?.snapshot ?? {
      schemaVersion: CONSOLIDATION_SCHEMA_VERSION, runId: paths.runId, scopeKey: paths.memory.scopeKey,
      capturedAt: contextManifest.createdAt, source: "empty" as const, contextEnabled: false, entries: [],
    } satisfies ConsolidationSnapshot;
    let snapshotDigest: string;
    if (captured) {
      snapshotDigest = captured.digest;
    } else {
      const snapshotText = jsonText(snapshot);
      await writeFileAtomic(paths.snapshotFile, snapshotText);
      snapshotDigest = sha256Digest(snapshotText);
    }
    const manifest: ConsolidationManifest = {
      schemaVersion: CONSOLIDATION_SCHEMA_VERSION, runId: paths.runId, cwd: paths.memory.cwd,
      scopeKey: paths.memory.scopeKey,
      scopeDigest: digest({ runId: paths.runId, scopeKey: paths.memory.scopeKey, snapshotDigest, contextEnabled: !noContext }),
      harnessDir: paths.memory.harnessDir, publicDir: paths.memory.publicDir, runDir: paths.runDir,
      contextEnabled: !noContext, contextMode: noContext ? "no-context" : "snapshot", snapshotPath: paths.snapshotFile,
      snapshotDigest, createdAt: contextManifest.createdAt,
      sourceHashes: { harness: await hashMemoryRoot(paths.memory.harnessDir), public: await hashMemoryRoot(paths.memory.publicDir) },
    };
    await writeJsonAtomic(paths.manifestFile, manifest);
    return { manifest, paths, lockPath: paths.lockFile, lock, released: false, normalization };
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

export class BoundedTextBuffer {
  private readonly chunks: Buffer[] = [];
  private used = 0;
  private didTruncate = false;
  private readonly maxBytes: number;
  constructor(maxBytes: number) {
    if (!Number.isSafeInteger(maxBytes) || maxBytes < 0) throw new Error("maxBytes must be a non-negative integer.");
    this.maxBytes = maxBytes;
  }
  append(value: string | Uint8Array): void {
    if (this.didTruncate || this.used >= this.maxBytes) { this.didTruncate = true; return; }
    const remaining = this.maxBytes - this.used;
    const bytes = typeof value === "string" ? boundedStringBytes(value, remaining) : Buffer.from(value.buffer, value.byteOffset, Math.min(value.byteLength, remaining));
    if (bytes.length) { this.chunks.push(bytes); this.used += bytes.length; }
    if (typeof value === "string" ? Buffer.byteLength(value, "utf8") > bytes.length : value.byteLength > bytes.length) this.didTruncate = true;
  }
  get text(): string { return Buffer.concat(this.chunks).toString("utf8"); }
  get bytes(): number { return this.used; }
  get truncated(): boolean { return this.didTruncate; }
  result(): BoundedText { return { text: this.text, bytes: this.used, truncated: this.didTruncate }; }
}

export interface PlanIdentity { runId: string; scopeDigest: string; artifactHash?: string }
export interface PlanIdentityExpectation { runId: string; scopeDigest: string; artifactHash: string }
function planIdentity(plan: unknown): PlanIdentity | undefined {
  if (!plan || typeof plan !== "object" || Array.isArray(plan)) return undefined;
  const value = plan as Record<string, unknown>;
  if (typeof value.runId !== "string" || typeof value.scopeDigest !== "string") return undefined;
  return { runId: value.runId, scopeDigest: value.scopeDigest, ...(typeof value.artifactHash === "string" ? { artifactHash: value.artifactHash } : {}) };
}
export function extractPlanIdentity(plan: unknown): PlanIdentity | undefined { return planIdentity(plan); }
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
export type ChildPlanExtractionResult<T = unknown> = { ok: true; plan: T; line: number } | { ok: false; error: string };
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
function parseJsonCandidate(text: string): unknown | undefined {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
  } catch {
    const match = /^```(?:json)?\s*([\s\S]*?)\s*```$/i.exec(trimmed);
    if (match) {
      try {
        const parsed = JSON.parse(match[1].trim()) as unknown;
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
      } catch {
        return undefined;
      }
    }
  }
  return undefined;
}

function candidateFromEvent(event: unknown): unknown | undefined {
  if (!event || typeof event !== "object" || Array.isArray(event)) return undefined;
  const value = event as Record<string, unknown>;
  if (value.type === "consolidation_plan") {
    return value.plan && typeof value.plan === "object" && !Array.isArray(value.plan) ? value.plan : undefined;
  }
  if (value.type === "memory-consolidation-plan" || value.kind === "memory-consolidation-plan") return value;
  if (value.type !== "message_end" || !value.message || typeof value.message !== "object") return undefined;
  const message = value.message as Record<string, unknown>;
  if (message.role !== "assistant") return undefined;
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
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index]; if (!line.trim()) continue;
    if (Buffer.byteLength(line, "utf8") > (options.maxLineBytes ?? MAX_JSONL_LINE_BYTES)) return { ok: false, error: `child JSONL line ${index + 1} exceeded the byte bound` };
    let event: unknown; try { event = JSON.parse(line); } catch { continue; }
    const plan = candidateFromEvent(event); if (plan === undefined) continue;
    if (Buffer.byteLength(jsonText(plan), "utf8") > (options.maxPlanBytes ?? MAX_PLAN_BYTES)) return { ok: false, error: "consolidation plan exceeded the byte bound" };
    candidates.push({ plan, line: index + 1 });
  }
  if (!candidates.length) return { ok: false, error: "child output did not contain a structured consolidation plan" };
  if (options.expectedIdentity && candidates.some(({ plan }) => !validatePlanIdentityResult(plan, options.expectedIdentity!).ok)) return { ok: false, error: "child consolidation plan identity mismatch" };
  const matching = options.expectedIdentity ? candidates.filter(({ plan }) => validatePlanIdentityResult(plan, options.expectedIdentity!).ok) : candidates;
  if (matching.length !== 1) return { ok: false, error: `expected one structured consolidation plan, found ${matching.length}` };
  if (options.validatePlan && !options.validatePlan(matching[0].plan)) return { ok: false, error: "structured consolidation plan failed schema validation" };
  return { ok: true, plan: matching[0].plan as T, line: matching[0].line };
}
export function extractFinalPlan(stdout: string): unknown { const result = extractChildPlan(stdout); return result.ok ? result.plan : undefined; }

export interface FinalHashes { harness: Record<string, string>; public: Record<string, string> }
const SHA256_RE = /^(?:sha256:)?[0-9a-f]{64}$/i;
export interface ReceiptBindingInput { runId: string; scopeDigest: string; artifactHash: string; selected: readonly string[]; finalHashes?: FinalHashes; sourceHashes?: FinalHashes; planDigest?: string }
export interface ConsolidationReceipt {
  kind: "memory-consolidation-receipt";
  version: typeof CONSOLIDATION_SCHEMA_VERSION;
  schemaVersion: typeof CONSOLIDATION_SCHEMA_VERSION;
  phase: "pre" | "post";
  runId: string;
  scopeDigest: string;
  artifactHash: string;
  selected: string[];
  finalHashes?: FinalHashes;
  sourceHashes?: FinalHashes;
  planDigest?: string;
  finalDigest?: string;
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
    ...(input.finalHashes ? { finalHashes: { harness: sortedHashes(input.finalHashes.harness), public: sortedHashes(input.finalHashes.public) } } : {}),
    ...(input.sourceHashes ? { sourceHashes: { harness: sortedHashes(input.sourceHashes.harness), public: sortedHashes(input.sourceHashes.public) } } : {}),
    ...(input.planDigest ? { planDigest: input.planDigest } : {}),
    createdAt: new Date().toISOString(),
  };
}
export function createPreApplyReceipt(input: ReceiptBindingInput): ConsolidationReceipt { return createReceiptBinding("pre", input); }
export function createPostApplyReceipt(input: ReceiptBindingInput): ConsolidationReceipt { return createReceiptBinding("post", input); }
export function createConsolidationReceipt(manifest: ConsolidationManifest, selected: string[], finalState: unknown, planDigest: string): ConsolidationReceipt {
  const hashes = finalState && typeof finalState === "object" && !Array.isArray(finalState) ? finalState as FinalHashes : { harness: {}, public: {} };
  return createPostApplyReceipt({ runId: manifest.runId, scopeDigest: manifest.scopeDigest, artifactHash: manifest.snapshotDigest, selected, finalHashes: hashes, sourceHashes: manifest.sourceHashes, planDigest });
}
export interface ReceiptBindingExpectation { runId?: string; scopeDigest?: string; artifactHash?: string; selected?: readonly string[]; phase?: "pre" | "post" }
export function validateReceiptBinding(receipt: unknown, expected: ReceiptBindingExpectation = {}): { ok: true; receipt: ConsolidationReceipt } | { ok: false; error: string } {
  if (!receipt || typeof receipt !== "object" || Array.isArray(receipt)) return { ok: false, error: "receipt is not an object" };
  const value = receipt as Partial<ConsolidationReceipt>;
  if (value.kind !== "memory-consolidation-receipt" || value.version !== CONSOLIDATION_SCHEMA_VERSION || value.schemaVersion !== CONSOLIDATION_SCHEMA_VERSION) return { ok: false, error: "receipt kind or schema version mismatch" };
  if (typeof value.runId !== "string" || typeof value.scopeDigest !== "string" || typeof value.artifactHash !== "string" || !Array.isArray(value.selected)) return { ok: false, error: "receipt identity or selected scope is invalid" };
  if (value.phase !== "pre" && value.phase !== "post") return { ok: false, error: "receipt phase is required and invalid" };
  try {
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
    return { ok: true, receipt: { ...value, selected } as ConsolidationReceipt };
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
export function boundedStderr(value: string | Uint8Array): BoundedText { return boundText(value, MAX_STDERR_BYTES); }
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

async function hashMemoryRoot(root: string): Promise<MemoryHashes> {
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
  const lines = ["# Memory Index", ""];
  for (const name of names) lines.push(`- [${name}](${name})${privateNames.has(name.toLowerCase()) ? " (harness only)" : ""}`);
  await assertMemoryRootStable(root, rootIdentity);
  isActive?.();
  await writeMemoryFile(path.join(root, "MEMORY.md"), `${lines.join("\n")}\n`);
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
      if (snapshot.existed) {
        await writeFileAtomic(snapshot.file, snapshot.content!, snapshot.mode ?? 0o600);
      } else {
        await fsp.rm(snapshot.file, { force: true });
      }
    } catch (error) {
      errors.push(error as Error);
    }
  }
  if (errors.length) throw new Error(errors.map((error) => error.message).join("; "));
}

const PRIVATE_MARKER_RE = /\(\s*harness[\s_-]+only\s*\)/i;
const INDEX_FILENAME_RE = /[A-Za-z0-9][A-Za-z0-9_.-]*\.md\b/gi;

async function readPrivateIndexNames(root: string): Promise<Set<string>> {
  const index = path.join(root, "MEMORY.md");
  let text: string;
  try {
    text = (await readBoundedRegularFile(index, MAX_MEMORY_BYTES)).toString("utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return new Set();
    throw error;
  }
  const privateNames = new Set<string>();
  for (const line of text.split(/\r?\n/)) {
    const matches = [...line.matchAll(INDEX_FILENAME_RE)];
    const name = matches.map((match) => match[0]).find((candidate) => candidate.toLowerCase() !== "memory.md");
    if (PRIVATE_MARKER_RE.test(line)) {
      if (!name || !isMemoryFilename(name)) throw new Error(`Memory index has a private marker without a valid memory filename: ${root}`);
      const key = name.toLowerCase();
      if (privateNames.has(key)) throw new Error(`Memory index contains duplicate private memory names: ${name}`);
      privateNames.add(key);
    }
  }
  return privateNames;
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
        await fsp.rm(state.root, { force: true });
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
  await fsp.rm(memoryFilePath(root, name), { force: true });
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

export async function applyConsolidationPlan(
  run: ConsolidationRun,
  plan: unknown,
  isActive?: () => boolean,
): Promise<{ selected: string[]; finalState: { harness: MemoryHashes; public: MemoryHashes } }> {
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

  const roots = [run.manifest.harnessDir, run.manifest.publicDir];
  const rootStates = await Promise.all(roots.map(captureRootState));
  const currentSourceHashes = { harness: await hashMemoryRoot(run.manifest.harnessDir), public: await hashMemoryRoot(run.manifest.publicDir) };
  if (digest(currentSourceHashes) !== digest(run.manifest.sourceHashes)) throw new Error("Memory sources changed after the consolidation snapshot; refusing stale apply.");
  await ensureMemoryRoot(run.manifest.harnessDir);
  await ensureMemoryRoot(run.manifest.publicDir);
  const privateNames = await readPrivateIndexNames(run.manifest.harnessDir);
  const publicPrivateNames = await readPrivateIndexNames(run.manifest.publicDir);
  if (publicPrivateNames.size > 0) throw new Error("Public memory index contains harness-only entries.");
  const transactionFiles = [...new Set([
    ...selected.flatMap((name) => [memoryFilePath(run.manifest.harnessDir, name), memoryFilePath(run.manifest.publicDir, name)]),
    path.join(run.manifest.harnessDir, "MEMORY.md"),
    path.join(run.manifest.publicDir, "MEMORY.md"),
  ])];
  const snapshots = await captureMemoryFiles(transactionFiles);
  const snapshotSourceHashes = { harness: await hashMemoryRoot(run.manifest.harnessDir), public: await hashMemoryRoot(run.manifest.publicDir) };
  if (digest(snapshotSourceHashes) !== digest(run.manifest.sourceHashes)) throw new Error("Memory sources changed while capturing the consolidation transaction; refusing stale apply.");
  try {
    ensureActive();
    if (selected.length === 0) {
      await ensureMemoryIndex(run.manifest.harnessDir, privateNames);
      ensureActive();
      await ensureMemoryIndex(run.manifest.publicDir, new Set());
    } else {
      for (const operation of normalizedOperations) {
        ensureActive();
        if (operation.kind === "delete") {
          await removeMemoryFile(run.manifest.harnessDir, operation.name);
          privateNames.delete(operation.name.toLowerCase());
          ensureActive();
          await removeMemoryFile(run.manifest.publicDir, operation.name);
        } else {
          await writeMemoryFileInRoot(run.manifest.harnessDir, operation.name, operation.content!);
          ensureActive();
          if (operation.classification === "safe") {
            privateNames.delete(operation.name.toLowerCase());
            await writeMemoryFileInRoot(run.manifest.publicDir, operation.name, operation.content!);
          } else {
            privateNames.add(operation.name.toLowerCase());
            await removeMemoryFile(run.manifest.publicDir, operation.name);
          }
        }
      }
      ensureActive();
      await updateMemoryIndex(run.manifest.harnessDir, privateNames, ensureActive);
      ensureActive();
      await updateMemoryIndex(run.manifest.publicDir, new Set(), ensureActive);
    }
    ensureActive();
    return {
      selected: [...selected].sort(),
      finalState: { harness: await hashMemoryRoot(run.manifest.harnessDir), public: await hashMemoryRoot(run.manifest.publicDir) },
    };
  } catch (error) {
    try {
      await restoreMemoryFiles(snapshots);
      await removeNewEmptyRoots(rootStates);
    } catch (rollbackError) {
      throw new Error(`${(error as Error).message}; memory rollback failed: ${(rollbackError as Error).message}`);
    }
    throw error;
  }
}

