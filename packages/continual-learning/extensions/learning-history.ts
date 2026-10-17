import fs from "node:fs/promises";
import { AsyncLocalStorage } from "node:async_hooks";
import { constants, type BigIntStats } from "node:fs";
import path from "node:path";
import { randomBytes } from "node:crypto";
import { getAgentDir, withFileMutationQueue } from "@earendil-works/pi-coding-agent";
import { acquireConsolidationLock, containsSensitiveMemoryMaterial, digest, hashMemoryRoot, isConsolidationRunId, normalizeMirrorDrift, parseMemoryIndexNames, parsePrivateIndexNames, resolveConsolidationRunPaths, sha256Digest, normalizeSnapshotEvidence, validateReceiptBinding, writeFileAtomic, type ConsolidationRun } from "./consolidation-run";
import { isMemoryFilename } from "./memory-files";
import { canonicalProjectCwd, resolveMemoryPaths, type MemoryPaths } from "./memory-paths";
import type { LearningSurface } from "./learning-controls";

const MAX_FILE_BYTES = 1_000_000;
const MAX_HISTORY_BYTES = 32 * 1024 * 1024;
const ID = /^change_[a-z0-9]+_[a-f0-9]{16}$/;
const BATCH_ID = /^batch_[a-f0-9]{32}$/;
const learningBatch = new AsyncLocalStorage<string>();

export function currentLearningBatch(): string | undefined {
  return learningBatch.getStore();
}

/** Presentation identity only; undo remains bound to one validated change. */
export function withLearningBatch<T>(work: () => Promise<T>): Promise<T> {
  return learningBatch.run(`batch_${randomBytes(16).toString("hex")}`, work);
}

type Target = { root: "private" | "public" | "project"; name: string };
type FileState = { bytes: string; mode: number; digest: string; revision?: string } | null;
interface Change { target: Target; before: FileState; after: FileState }
const ORIGIN_FILES = ["manifest.json", "snapshot.json", "context-manifest.json", "plan.json", "pre-receipt.json", "post-receipt.json"] as const;
export type MemoryOrigin = {version: 1; status: "unavailable"; reason: "unverifiable"} | {
  version: 1; status: "available"; runId: string;
  artifactHashes: Record<string, string>;
  targets: Array<{root: "private" | "public"; name: string; digest: string; revision: string}>;
};
/** Parent-owned transaction only. This is not a planner-selected origin path. */
export interface MemoryOriginInput {run: ConsolidationRun; planPath: string; planDigest: string}
export interface LearningHistory {
  version: 1;
  batchId?: string;
  id: string;
  cwd: string;
  agentDir: string;
  phase: LearningSurface;
  createdAt: string;
  status: "pending" | "applied" | "proposed" | "undoing" | "undone" | "abandoned";
  changes: Change[];
  proposal?: unknown;
  /** Historical interpretation context only; never source or mutation authority. */
  origin?: MemoryOrigin;
}

function missing(error: unknown): boolean {
  return Boolean(error && typeof error === "object" && "code" in error && error.code === "ENOENT");
}

/** Reject symlink components, including a missing target beneath a symlink. */
async function safePath(root: string, name: string): Promise<string> {
  const relative = path.relative(root, path.resolve(root, name));
  if (!relative || relative.startsWith(`..${path.sep}`) || relative === ".." || path.isAbsolute(relative)) throw new Error("History path escapes its root");
  let current = root;
  for (const part of ["", ...relative.split(path.sep)]) {
    if (part) current = path.join(current, part);
    try {
      const stat = await fs.lstat(current);
      if (stat.isSymbolicLink() || (current !== path.join(root, relative) && !stat.isDirectory())) throw new Error("History path contains a symlink or non-directory");
    } catch (error) { if (!missing(error)) throw error; }
  }
  return path.join(root, relative);
}

export async function readLearningFile(file: string, limit = MAX_HISTORY_BYTES): Promise<Buffer> {
  const handle = await fs.open(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const before = await handle.stat();
    if (!before.isFile() || before.size > limit) throw new Error("Learning file is not a bounded regular file");
    const bytes = Buffer.alloc(before.size);
    let offset = 0;
    while (offset < bytes.length) {
      const read = await handle.read(bytes, offset, bytes.length - offset, offset);
      if (read.bytesRead === 0) break;
      offset += read.bytesRead;
    }
    const after = await fs.lstat(file);
    if (offset !== before.size || after.isSymbolicLink() || before.dev !== after.dev || before.ino !== after.ino || before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ctimeMs !== after.ctimeMs) throw new Error("Learning file changed during read");
    return bytes;
  } finally { await handle.close(); }
}

function targetFor(cwd: string, file: string): Target {
  const paths = resolveMemoryPaths(cwd);
  let absolute = path.resolve(file);
  // An agent root created after run-path resolution can acquire its canonical
  // spelling (notably /var -> /private/var on macOS). Preserve the same scope.
  const agentRelative = path.relative(path.resolve(getAgentDir()), absolute);
  if (agentRelative && agentRelative !== ".." && !agentRelative.startsWith(`..${path.sep}`) && !path.isAbsolute(agentRelative)) absolute = path.join(paths.agentDir, agentRelative);
  for (const name of ["AGENTS.md", path.join(".pi", "harness.json")]) {
    if (!absolute.endsWith(path.sep + name)) continue;
    const project = absolute.slice(0, -name.length - 1) || path.parse(absolute).root;
    // Canonicalize only the project root. The surface's own components must
    // still pass targetPath's no-symlink checks, even when the file is absent.
    if (paths.cwd !== paths.agentDir && canonicalProjectCwd(project) === paths.cwd) return { root: "project", name };
  }
  for (const [root, directory] of [["private", paths.harnessDir], ["public", paths.publicDir]] as const) {
    if (!directory) continue;
    const name = path.relative(directory, absolute);
    if (name === "MEMORY.md" || isMemoryFilename(name)) return { root, name };
  }
  throw new Error("History target is outside the learned project surfaces");
}

async function targetPath(cwd: string, target: Target): Promise<string> {
  const paths = resolveMemoryPaths(cwd);
  if (!target || typeof target.name !== "string") throw new Error("Invalid history target");
  if (target.root === "project" && paths.cwd !== paths.agentDir && ["AGENTS.md", path.join(".pi", "harness.json")].includes(target.name)) return safePath(paths.cwd, target.name);
  if ((target.root === "private" || target.root === "public") && (target.name === "MEMORY.md" || isMemoryFilename(target.name))) {
    const directory = target.root === "private" ? paths.harnessDir : paths.publicDir;
    if (directory) {
      const base = target.root === "private" ? paths.agentDir : paths.cwd;
      return safePath(base, path.relative(base, path.join(directory, target.name)));
    }
  }
  throw new Error("Invalid history target scope");
}

async function stateOf(cwd: string, target: Target): Promise<FileState> {
  const file = await targetPath(cwd, target);
  try {
    const before = await fs.lstat(file, {bigint: true});
    const bytes = await readLearningFile(file, MAX_FILE_BYTES);
    await targetPath(cwd, target);
    const after = await fs.lstat(file, {bigint: true});
    if (revision(before) !== revision(after)) throw new Error("Learning history target changed during read");
    return { bytes: bytes.toString("base64"), mode: Number(after.mode & 0o777n), digest: sha256Digest(bytes), revision: revision(after) };
  } catch (error) { if (missing(error)) return null; throw error; }
}

function same(left: FileState, right: FileState): boolean {
  return left === null || right === null ? left === right : left.digest === right.digest && left.mode === right.mode;
}

async function historyPath(cwd: string, id: string): Promise<string> {
  if (!ID.test(id)) throw new Error("Invalid learning history id");
  const paths = resolveMemoryPaths(cwd);
  return safePath(paths.agentDir, path.join("memory", "history", paths.scopeKey, `${id}.json`));
}

async function newRecord(cwd: string, phase: LearningSurface, status: LearningHistory["status"]): Promise<LearningHistory> {
  // Stabilize canonical spelling before binding a first record to its scope.
  await fs.mkdir(resolveMemoryPaths(cwd).agentDir, { recursive: true, mode: 0o700 });
  const paths = resolveMemoryPaths(cwd);
  return { version: 1, ...(currentLearningBatch() ? { batchId: currentLearningBatch() } : {}), id: `change_${Date.now().toString(36)}_${randomBytes(8).toString("hex")}`, cwd: paths.cwd, agentDir: paths.agentDir, phase, createdAt: new Date().toISOString(), status, changes: [] };
}

function assertNoSensitiveHistory(value: unknown, depth = 0): void {
  if (depth > 128) throw new Error("Learning history nesting exceeds its limit");
  if (typeof value === "string") {
    if (containsSensitiveMemoryMaterial(value)) throw new Error("Learning history refuses sensitive material");
    // Configuration files can contain quoted JSON credential keys.
    if (/^\s*[\[{]/.test(value)) {
      let parsed: unknown;
      try { parsed = JSON.parse(value); } catch { return; }
      assertNoSensitiveHistory(parsed, depth + 1);
    }
  } else if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      if ((typeof item === "string" || typeof item === "number") && containsSensitiveMemoryMaterial(`${key}: ${item}`)) throw new Error("Learning history refuses sensitive material");
      assertNoSensitiveHistory(item, depth + 1);
    }
  }
}

function assertSafeRecord(record: LearningHistory): void {
  if (record.origin !== undefined && (record.phase !== "memory" || !validOrigin(record.origin))) throw new Error("Invalid Memory origin binding");
  assertNoSensitiveHistory(record.proposal);
  for (const change of record.changes) for (const state of [change.before, change.after]) {
    if (!state) continue;
    try {
      assertNoSensitiveHistory(Buffer.from(state.bytes, "base64").toString("utf8"));
    } catch (error) {
      // Name the surface without echoing the matched bytes: the user still needs
      // to know which file to clean before learning can record an undo path.
      const reason = error instanceof Error ? error.message : "Learning history refuses sensitive material";
      throw new Error(`${reason} in ${change.target.root}/${change.target.name}. Remove the credential from that file before learning resumes.`);
    }
  }
}

async function save(cwd: string, record: LearningHistory): Promise<void> {
  assertSafeRecord(record);
  const bytes = JSON.stringify(record, null, 2) + "\n";
  if (Buffer.byteLength(bytes) > MAX_HISTORY_BYTES) throw new Error("Learning history exceeds its byte limit");
  await writeFileAtomic(await historyPath(cwd, record.id), bytes, 0o600);
}

const row = (value: unknown): Record<string, unknown> | undefined => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
const revision = (stat: BigIntStats) => [stat.dev, stat.ino, stat.size, stat.mtimeNs, stat.ctimeNs].map(String).join(":");

async function originArtifact(cwd: string, runId: string, name: string, maximum = MAX_HISTORY_BYTES): Promise<Buffer> {
  const paths = resolveConsolidationRunPaths(cwd, runId);
  const relative = path.relative(paths.memory.agentDir, path.join(paths.runDir, name));
  const file = await safePath(paths.memory.agentDir, relative);
  const before = await fs.lstat(file, {bigint: true});
  const bytes = await readLearningFile(file, Math.min(maximum, name === "snapshot.json" || name === "plan.json" ? MAX_HISTORY_BYTES : MAX_FILE_BYTES));
  await safePath(paths.memory.agentDir, relative);
  if (revision(before) !== revision(await fs.lstat(file, {bigint: true}))) throw new Error("Origin artifact changed");
  return bytes;
}

function validateOriginInputs(cwd: string, runId: string, bytes: Record<string, Buffer>) {
  const paths = resolveConsolidationRunPaths(cwd, runId);
  const rawManifest = row(JSON.parse(bytes["manifest.json"].toString("utf8")));
  const snapshot = row(JSON.parse(bytes["snapshot.json"].toString("utf8")));
  const context = row(JSON.parse(bytes["context-manifest.json"].toString("utf8")));
  const value = row(JSON.parse(bytes["plan.json"].toString("utf8")));
  if (!rawManifest || rawManifest.schemaVersion !== 1 || rawManifest.runId !== runId
    || rawManifest.cwd !== paths.memory.cwd || rawManifest.scopeKey !== paths.memory.scopeKey
    || rawManifest.runDir !== paths.runDir || rawManifest.snapshotPath !== paths.snapshotFile
    || rawManifest.harnessDir !== paths.memory.harnessDir || rawManifest.publicDir !== paths.memory.publicDir
    || typeof rawManifest.scopeDigest !== "string" || typeof rawManifest.snapshotDigest !== "string"
    || rawManifest.contextEnabled !== true || rawManifest.contextMode !== "snapshot"
    || sha256Digest(bytes["snapshot.json"]) !== rawManifest.snapshotDigest
    || snapshot?.schemaVersion !== 1 || snapshot.runId !== runId || snapshot.scopeKey !== paths.memory.scopeKey || snapshot.contextEnabled !== true || !Array.isArray(snapshot.entries)
    || context?.schemaVersion !== 1 || context.runId !== runId || context.scopeKey !== paths.memory.scopeKey || context.snapshotDigest !== rawManifest.snapshotDigest
    || context.contextEnabled !== true || context.mode !== "snapshot" || context.entryCount !== snapshot.entries.length || context.snapshotFile !== "snapshot.json"
    || value?.runId !== runId || value.scopeKey !== paths.memory.scopeKey || value.scopeDigest !== rawManifest.scopeDigest
    || value.artifactHash !== rawManifest.snapshotDigest || value.snapshotDigest !== rawManifest.snapshotDigest
    || !Array.isArray(value.selected) || !value.selected.every((name): name is string => typeof name === "string")) throw new Error("Origin identity mismatch");
  const planDigest = sha256Digest(bytes["plan.json"]);
  const expected = {runId, scopeDigest: rawManifest.scopeDigest, artifactHash: rawManifest.snapshotDigest, selected: value.selected};
  const pre = validateReceiptBinding(JSON.parse(bytes["pre-receipt.json"].toString("utf8")), {...expected, phase: "pre"});
  if (!pre.ok || !pre.receipt.sourceHashes || pre.receipt.planDigest !== planDigest || digest(pre.receipt.sourceHashes) !== digest(rawManifest.sourceHashes)) throw new Error("Origin pre receipt mismatch");
  const created = (Array.isArray(value.newMemories) ? value.newMemories : []).map(item => row(item)?.name);
  if (!created.every((name): name is string => typeof name === "string" && isMemoryFilename(name))) throw new Error("Origin creation names invalid");
  return {manifest: {runId, scopeDigest: rawManifest.scopeDigest, snapshotDigest: rawManifest.snapshotDigest, sourceHashes: pre.receipt.sourceHashes, publicDir: paths.memory.publicDir},
    rawManifest, snapshot, plan: value, planDigest, expected, created,
    artifactHashes: Object.fromEntries(Object.entries(bytes).map(([name, value]) => [name, sha256Digest(value)]))};
}

async function prepareMemoryOrigin(cwd: string, input: MemoryOriginInput, plan: unknown) {
  const manifest = structuredClone(input.run.manifest), planDigest = input.planDigest;
  const paths = resolveConsolidationRunPaths(cwd, manifest.runId);
  if (input.planPath !== paths.planFile || input.run.paths.runDir !== paths.runDir) throw new Error("Foreign origin scope");
  const files = ORIGIN_FILES.filter(name => name !== "post-receipt.json");
  const bytes = Object.fromEntries(await Promise.all(files.map(async name => [name, await originArtifact(cwd, manifest.runId, name)] as const)));
  const validated = validateOriginInputs(cwd, manifest.runId, bytes);
  if (digest(validated.rawManifest) !== digest(JSON.parse(JSON.stringify(manifest)))
    || validated.planDigest !== planDigest || digest(validated.plan) !== digest(plan)) throw new Error("Origin parent mismatch");
  return validated;
}

async function finishMemoryOrigin(cwd: string, prepared: Awaited<ReturnType<typeof prepareMemoryOrigin>>, changes: readonly Change[]): Promise<MemoryOrigin> {
  const {manifest, expected, planDigest} = prepared;
  const postBytes = await originArtifact(cwd, manifest.runId, "post-receipt.json");
  const post = validateReceiptBinding(JSON.parse(postBytes.toString("utf8")), {...expected, created: prepared.created, phase: "post"});
  if (!post.ok || post.receipt.planDigest !== planDigest || digest(post.receipt.sourceHashes) !== digest(manifest.sourceHashes)) throw new Error("Origin post receipt mismatch");
  const candidates = [...(Array.isArray(prepared.plan.operations) ? prepared.plan.operations : []), ...(Array.isArray(prepared.plan.newMemories) ? prepared.plan.newMemories : [])].map(row);
  const targets: Extract<MemoryOrigin, {status: "available"}>["targets"] = [];
  for (const change of changes) {
    if (change.target.root !== "private" || change.target.name === "MEMORY.md" || !change.after) continue;
    const candidate = candidates.filter(item => item?.name === change.target.name);
    if (candidate.length !== 1 || typeof candidate[0]?.content !== "string" || sha256Digest(candidate[0].content) !== change.after.digest) throw new Error("Origin target mismatch");
    const name = change.target.name, classification = candidate[0].classification;
    const sharedTarget = classification === "safe" && manifest.publicDir !== undefined;
    if (!["safe", "private"].includes(String(classification)) || post.receipt.finalHashes?.harness[name] !== change.after.digest
      || (sharedTarget ? post.receipt.finalHashes?.public[name] !== change.after.digest : post.receipt.finalHashes?.public[name] !== undefined)) throw new Error("Origin mirror mismatch");
    const shared = manifest.publicDir ? await stateOf(cwd, {root: "public", name}) : null;
    if (sharedTarget ? shared?.digest !== change.after.digest : shared !== null) throw new Error("Origin current mirror mismatch");
    for (const target of [{root: "private", name}, ...(sharedTarget ? [{root: "public" as const, name}] : [])] as const) {
      const file = await targetPath(cwd, target), before = await fs.lstat(file, {bigint: true});
      const bytes = await readLearningFile(file, MAX_FILE_BYTES);
      await targetPath(cwd, target);
      const after = await fs.lstat(file, {bigint: true});
      const observed = changes.find(change => change.target.root === target.root && change.target.name === name)?.after;
      if (revision(before) !== revision(after) || sha256Digest(bytes) !== change.after.digest
        || observed && observed.revision !== revision(after)) throw new Error("Origin target revision changed");
      targets.push({...target, digest: change.after.digest, revision: revision(after)});
    }
  }
  if (!targets.length) throw new Error("Origin has no changed knowledge target");
  for (const [name, hash] of Object.entries(prepared.artifactHashes)) if (sha256Digest(await originArtifact(cwd, manifest.runId, name)) !== hash) throw new Error("Origin inputs changed");
  return {version: 1, status: "available", runId: manifest.runId,
    artifactHashes: {...prepared.artifactHashes, "post-receipt.json": sha256Digest(postBytes)}, targets};
}

/** Call while holding the existing consolidation lock, immediately around mutation. */
export interface LearningPendingMutation { id: string; digest: string }

export async function recordLearningMutation<T>(cwd: string, phase: LearningSurface, files: readonly string[], mutate: (pending: LearningPendingMutation) => Promise<T>, plan?: unknown, origin?: MemoryOriginInput): Promise<T> {
  assertNoSensitiveHistory(plan);
  const record = await newRecord(cwd, phase, "pending");
  let prepared: Awaited<ReturnType<typeof prepareMemoryOrigin>> | undefined;
  if (phase === "memory" && origin) {
    try { prepared = await prepareMemoryOrigin(cwd, origin, plan); } catch { /* Optional provenance cannot change mutation authority. */ }
  }
  for (const file of [...new Set(files)].sort()) {
    const target = targetFor(cwd, file);
    const before = await stateOf(cwd, target);
    record.changes.push({ target, before, after: before });
  }
  await save(cwd, record);
  let succeeded = false;
  try {
    const result = await mutate(Object.freeze({id: record.id, digest: sha256Digest(JSON.stringify(record, null, 2) + "\n")}));
    succeeded = !(result && typeof result === "object" && "outcome" in result && result.outcome !== "applied");
    return result;
  }
  finally {
    for (const change of record.changes) change.after = await stateOf(cwd, change.target);
    record.changes = record.changes.filter(change => !same(change.before, change.after));
    if (record.changes.length) {
      record.status = succeeded ? "applied" : "pending";
      if (succeeded && phase === "memory" && origin) {
        record.origin = {version: 1, status: "unavailable", reason: "unverifiable"};
        if (prepared) try { record.origin = await finishMemoryOrigin(cwd, prepared, record.changes); } catch { /* Keep the applied outcome and an explicit unavailable origin. */ }
      }
      await save(cwd, record);
    }
    else await fs.unlink(await historyPath(cwd, record.id));
  }
}

export async function recordLearningProposal(cwd: string, phase: LearningSurface, proposal: unknown): Promise<string> {
  const record = await newRecord(cwd, phase, "proposed");
  record.proposal = proposal;
  await save(cwd, record);
  return record.id;
}

export async function normalizeTrackedMemory(memory: MemoryPaths) {
  const canonical = await hashMemoryRoot(memory.harnessDir);
  const shared = memory.publicDir ? await hashMemoryRoot(memory.publicDir) : {};
  let index = "";
  if (canonical["MEMORY.md"]) index = (await readLearningFile(path.join(memory.harnessDir, "MEMORY.md"), MAX_FILE_BYTES)).toString("utf8");
  const privateNames = parsePrivateIndexNames(index);
  const names = new Set(["MEMORY.md", ...Object.keys({ ...canonical, ...shared }).filter(name => canonical[name] !== shared[name]), ...Object.keys(shared).filter(name => privateNames.has(name.toLowerCase()))]);
  const files = [...names].flatMap(name => [path.join(memory.harnessDir, name), ...(memory.publicDir ? [path.join(memory.publicDir, name)] : [])]);
  return recordLearningMutation(memory.cwd, "memory", files, () => normalizeMirrorDrift(memory));
}

export function memoryMutationFiles(cwd: string, names: readonly string[]): string[] {
  const memory = resolveMemoryPaths(cwd);
  return [...new Set(["MEMORY.md", ...names])].flatMap(name => {
    if (name !== "MEMORY.md" && !isMemoryFilename(name)) throw new Error("Invalid Memory mutation name");
    return [path.join(memory.harnessDir, name), ...(memory.publicDir ? [path.join(memory.publicDir, name)] : [])];
  });
}

function validState(value: unknown): value is FileState {
  if (value === null) return true;
  if (!value || typeof value !== "object") return false;
  const state = value as Exclude<FileState, null>;
  if (typeof state.bytes !== "string" || state.bytes.length > Math.ceil(MAX_FILE_BYTES / 3) * 4 || !Number.isInteger(state.mode) || state.mode < 0 || state.mode > 0o777) return false;
  if (state.revision !== undefined && (typeof state.revision !== "string" || !/^\d+:\d+:\d+:-?\d+:-?\d+$/.test(state.revision))) return false;
  const bytes = Buffer.from(state.bytes, "base64");
  return bytes.length <= MAX_FILE_BYTES && bytes.toString("base64") === state.bytes && sha256Digest(bytes) === state.digest;
}

function validOrigin(value: unknown): value is MemoryOrigin {
  const origin = row(value);
  if (!origin || origin.version !== 1) return false;
  if (origin.status === "unavailable") return origin.reason === "unverifiable"
    && Object.keys(origin).every(key => ["version", "status", "reason"].includes(key));
  const hashes = row(origin.artifactHashes);
  if (origin.status !== "available" || typeof origin.runId !== "string" || !isConsolidationRunId(origin.runId)
    || Object.keys(origin).some(key => !["version", "status", "runId", "artifactHashes", "targets"].includes(key))
    || !hashes || Object.keys(hashes).length !== ORIGIN_FILES.length
    || ORIGIN_FILES.some(name => typeof hashes[name] !== "string" || !/^[a-f0-9]{64}$/.test(hashes[name] as string))
    || !Array.isArray(origin.targets) || !origin.targets.length || origin.targets.length > 8192) return false;
  const seen = new Set<string>();
  for (const value of origin.targets) {
    const target = row(value);
    if (!target || !["private", "public"].includes(String(target.root)) || typeof target.name !== "string" || !isMemoryFilename(target.name)
      || typeof target.digest !== "string" || !/^[a-f0-9]{64}$/.test(target.digest)
      || typeof target.revision !== "string" || !/^\d+:\d+:\d+:-?\d+:-?\d+$/.test(target.revision)
      || Object.keys(target).some(key => !["root", "name", "digest", "revision"].includes(key))) return false;
    const key = `${target.root}/${String(target.name).toLowerCase()}`;
    if (seen.has(key)) return false;
    seen.add(key);
  }
  return true;
}

async function parseLearningHistory(cwd: string, id: string, raw: unknown): Promise<LearningHistory> {
  if (!raw || typeof raw !== "object") throw new Error("Invalid history record");
  const record = raw as LearningHistory;
  const paths = resolveMemoryPaths(cwd);
  if (record.version !== 1 || record.id !== id || record.cwd !== paths.cwd || record.agentDir !== paths.agentDir || !["memory", "harness", "agents"].includes(record.phase) || !["pending", "applied", "proposed", "undoing", "undone", "abandoned"].includes(record.status) || !Array.isArray(record.changes) || record.changes.length > 8194) throw new Error("Invalid or foreign history record");
  if (record.batchId !== undefined && (typeof record.batchId !== "string" || !BATCH_ID.test(record.batchId))) throw new Error("Invalid history batch identity");
  const seen = new Set<string>();
  for (const change of record.changes) {
    if (!change || !validState(change.before) || !validState(change.after)) throw new Error("Invalid history bytes");
    const file = await targetPath(cwd, change.target);
    if (seen.has(file)) throw new Error("Duplicate history target");
    seen.add(file);
  }
  assertSafeRecord(record);
  return record;
}

export async function readLearningHistory(cwd: string, id: string): Promise<LearningHistory> {
  return parseLearningHistory(cwd, id, JSON.parse((await readLearningFile(await historyPath(cwd, id))).toString("utf8")));
}

const ORIGIN_LIMITS = {entries: 8192, records: 4096, bytes: 128 * 1024 * 1024, artifactBytes: MAX_HISTORY_BYTES, depth: 128} as const;
type OriginReason = "missing" | "legacy" | "bounds-exceeded" | "ambiguous" | "chain-gap" | "changed" | "invalid" | "cancelled" | "unverifiable";
class OriginFailure extends Error { constructor(readonly reason: OriginReason) { super(reason); } }
export interface MemoryOriginContext {
  kind: "historical-memory-origin";
  version: 1;
  name: string;
  current: {digest: string; mode: number; revision: string};
  transactions: Array<{historyId: string; historyDigest: string; runId: string; artifactHashes: Record<string, string>;
    kind: "create" | "rewrite"; snapshot: Record<string, unknown>; candidate: Record<string, unknown>}>;
}

/** Caller holds the initialized project's consolidation lock. This function
 * acquires no lock and writes nothing. Its private historical data supplies no
 * current citations, source facts, permissions, or semantic approval. */
export async function readMemoryOriginContext(cwd: string, name: string, options: {
  signal?: AbortSignal; limits?: Partial<Record<keyof typeof ORIGIN_LIMITS, number>>;
} = {}): Promise<{status: "unavailable"; reason: OriginReason} | {
  status: "available"; context: MemoryOriginContext;
  assertUnchanged: (pending?: LearningPendingMutation) => Promise<void>;
  assertArtifactsUnchanged: (pending?: LearningPendingMutation) => Promise<void>;
}> {
  const fail = (reason: OriginReason): never => { throw new OriginFailure(reason); };
  try {
    if (!isMemoryFilename(name)) return fail("invalid");
    const limits = {...ORIGIN_LIMITS, ...options.limits};
    if (Object.keys(limits).some(key => !(key in ORIGIN_LIMITS))
      || Object.entries(limits).some(([key, value]) => !Number.isSafeInteger(value) || value < 1 || value > ORIGIN_LIMITS[key as keyof typeof ORIGIN_LIMITS])) return fail("bounds-exceeded");
    let used = 0;
    const check = () => { if (options.signal?.aborted) fail("cancelled"); };
    const consume = (bytes: number) => { check(); used += bytes; if (used > limits.bytes) fail("bounds-exceeded"); };
    const memory = resolveMemoryPaths(cwd);
    const directory = await safePath(memory.agentDir, path.join("memory", "history", memory.scopeKey));
    const inventory = async () => {
      check();
      const before = await fs.lstat(directory, {bigint: true});
      if (!before.isDirectory()) return fail("invalid");
      const names: string[] = [];
      const handle = await fs.opendir(directory);
      for await (const item of handle) {
        if (names.length >= limits.entries) return fail("bounds-exceeded");
        if (!item.isFile() || item.isSymbolicLink()) return fail("invalid");
        names.push(item.name);
      }
      await safePath(memory.agentDir, path.relative(memory.agentDir, directory));
      if (revision(before) !== revision(await fs.lstat(directory, {bigint: true}))) return fail("changed");
      const records = names.filter(file => ID.test(file.slice(0, -5)) && file.endsWith(".json"));
      if (records.length > limits.records) return fail("bounds-exceeded");
      if (names.some(file => file.endsWith(".json") && file !== "undo-pending.json" && !records.includes(file))) return fail("invalid");
      return names.sort();
    };
    const readRecordBytes = async (file: string) => {
      check();
      const target = await safePath(memory.agentDir, path.relative(memory.agentDir, path.join(directory, file)));
      const before = await fs.lstat(target, {bigint: true});
      if (before.size > BigInt(limits.bytes - used)) return fail("bounds-exceeded");
      const bytes = await readLearningFile(target, Math.min(MAX_HISTORY_BYTES, limits.bytes - used));
      await safePath(memory.agentDir, path.relative(memory.agentDir, target));
      if (revision(before) !== revision(await fs.lstat(target, {bigint: true}))) return fail("changed");
      consume(bytes.length); return bytes;
    };
    const readArtifact = async (runId: string, file: string) => {
      check();
      const paths = resolveConsolidationRunPaths(cwd, runId);
      const target = await safePath(memory.agentDir, path.relative(memory.agentDir, path.join(paths.runDir, file)));
      const size = (await fs.lstat(target, {bigint: true})).size;
      if (size > BigInt(Math.min(limits.artifactBytes, limits.bytes - used))) return fail("bounds-exceeded");
      const bytes = await originArtifact(cwd, runId, file, Math.min(limits.artifactBytes, limits.bytes - used));
      consume(bytes.length); return bytes;
    };
    const current = await stateOf(cwd, {root: "private", name});
    if (!current) return fail("missing");
    consume(Buffer.from(current.bytes, "base64").length);
    if (!current.revision) return fail("legacy");
    const names = await inventory();
    const captured: Array<{file: string; hash: string; record: LearningHistory}> = [];
    const relevant = (record: LearningHistory) => record.changes.some(change => change.target.root !== "project" && change.target.name.toLowerCase() === name.toLowerCase());
    for (const file of names.filter(file => file.endsWith(".json") && file !== "undo-pending.json")) {
      const bytes = await readRecordBytes(file);
      const record = await parseLearningHistory(cwd, file.slice(0, -5), JSON.parse(bytes.toString("utf8")));
      if (record.changes.some(change => change.target.root !== "project" && change.target.name.toLowerCase() === name.toLowerCase() && change.target.name !== name)) return fail("ambiguous");
      if (relevant(record) && (record.phase !== "memory" || ["pending", "undoing"].includes(record.status))) return fail("changed");
      captured.push({file, hash: sha256Digest(bytes), record});
    }
    let journalHash: string | undefined;
    if (names.includes("undo-pending.json")) {
      const bytes = await readRecordBytes("undo-pending.json"); journalHash = sha256Digest(bytes);
      const id = row(JSON.parse(bytes.toString("utf8")))?.id;
      const record = captured.find(item => item.record.id === id)?.record;
      if (!record) return fail("invalid");
      if (relevant(record)) return fail("changed");
    }
    const exact = (left: FileState, right: FileState) => !!left?.revision && !!right?.revision && same(left, right) && left.revision === right.revision;
    const transactions: MemoryOriginContext["transactions"] = [];
    const bindings: Array<{runId: string; hashes: Record<string, string>}> = [];
    const seen = new Set<string>();
    let state = current;
    let endpointShared: FileState;
    for (;;) {
      if (transactions.length >= limits.depth) return fail("bounds-exceeded");
      const matches = captured.flatMap(item => item.record.changes.filter(change => change.target.root === "private" && change.target.name === name && exact(change.after, state)).map(change => ({...item, change})));
      if (matches.length !== 1) return fail(matches.length ? "ambiguous" : "chain-gap");
      const {record, hash, change} = matches[0];
      if (seen.has(record.id)) return fail("ambiguous");
      seen.add(record.id);
      if (record.status !== "applied") return fail("changed");
      if (!record.origin) return fail("legacy");
      if (record.origin.status !== "available") return fail("unverifiable");
      const origin = record.origin;
      const bytes: Record<string, Buffer> = {};
      for (const file of ORIGIN_FILES) {
        bytes[file] = await readArtifact(origin.runId, file);
        if (sha256Digest(bytes[file]) !== origin.artifactHashes[file]) return fail("changed");
      }
      const input = validateOriginInputs(cwd, origin.runId, bytes);
      const post = validateReceiptBinding(JSON.parse(bytes["post-receipt.json"].toString("utf8")), {...input.expected, created: input.created, phase: "post"});
      if (!post.ok || post.receipt.planDigest !== input.planDigest || digest(post.receipt.sourceHashes) !== digest(input.manifest.sourceHashes)) return fail("invalid");
      if (!Array.isArray(input.plan.operations) || !Array.isArray(input.plan.newMemories)) return fail("invalid");
      const candidates = [...input.plan.operations, ...input.plan.newMemories].map(row);
      const candidate = candidates.filter(item => item?.name === name);
      if (candidate.length !== 1 || typeof candidate[0]?.content !== "string" || sha256Digest(candidate[0].content) !== state.digest) return fail("invalid");
      normalizeSnapshotEvidence(candidate[0].evidence, input.snapshot);
      const created = change.before === null;
      if (created ? !input.created.includes(name) || !input.plan.newMemories.some(item => row(item)?.name === name)
        : !input.expected.selected.includes(name) || !input.plan.operations.some(item => row(item)?.name === name && row(item)?.kind === "rewrite")) return fail("invalid");
      if (input.manifest.sourceHashes.harness[name] !== change.before?.digest) return fail("invalid");
      const shared = candidate[0].classification === "safe" && memory.publicDir !== undefined;
      if (!["safe", "private"].includes(String(candidate[0].classification)) || post.receipt.finalHashes?.harness[name] !== state.digest
        || (shared ? post.receipt.finalHashes?.public[name] !== state.digest : post.receipt.finalHashes?.public[name] !== undefined)) return fail("invalid");
      const targets = origin.targets.filter(target => target.name.toLowerCase() === name.toLowerCase());
      if (targets.length !== (shared ? 2 : 1) || targets.some(target => target.name !== name || target.digest !== state.digest)
        || !targets.some(target => target.root === "private" && target.revision === state.revision)) return fail("invalid");
      const mirrorChange = record.changes.find(item => item.target.root === "public" && item.target.name === name);
      if (mirrorChange && (mirrorChange.before?.digest !== input.manifest.sourceHashes.public[name]
        || mirrorChange.after?.digest !== post.receipt.finalHashes?.public[name])) return fail("invalid");
      if (shared && !targets.some(target => target.root === "public" && (!mirrorChange?.after || target.revision === mirrorChange.after.revision))) return fail("invalid");
      if (!transactions.length) {
        endpointShared = memory.publicDir ? await stateOf(cwd, {root: "public", name}) : null;
        if (shared ? !endpointShared || !targets.some(target => target.root === "public" && target.digest === endpointShared!.digest && target.revision === endpointShared!.revision) : endpointShared !== null) return fail("changed");
      }
      bindings.push({runId: origin.runId, hashes: {...origin.artifactHashes}});
      transactions.push({historyId: record.id, historyDigest: hash, runId: origin.runId, artifactHashes: {...origin.artifactHashes}, kind: created ? "create" : "rewrite", snapshot: input.snapshot, candidate: candidate[0]});
      if (created) break;
      if (!change.before?.revision) return fail("legacy");
      state = change.before;
    }
    const context: MemoryOriginContext = JSON.parse(JSON.stringify({kind: "historical-memory-origin", version: 1, name,
      current: {digest: current.digest, mode: current.mode, revision: current.revision}, transactions: transactions.reverse()}));
    const contextHash = sha256Digest(JSON.stringify(context));
    const assertArtifactsUnchanged = async (pending?: LearningPendingMutation) => {
      check();
      if (sha256Digest(JSON.stringify(context)) !== contextHash) return fail("changed");
      if (pending && (!ID.test(pending.id) || !/^[a-f0-9]{64}$/.test(pending.digest) || names.includes(pending.id + ".json"))) return fail("invalid");
      const expected = pending ? [...names, pending.id + ".json"].sort() : names;
      const assertInventory = async () => {
        if (JSON.stringify(await inventory()) !== JSON.stringify(expected)) return fail("changed");
        if (pending) {
          const bytes = await readRecordBytes(pending.id + ".json");
          if (sha256Digest(bytes) !== pending.digest) return fail("changed");
          const record = await parseLearningHistory(cwd, pending.id, JSON.parse(bytes.toString("utf8")));
          if (record.status !== "pending" || record.phase !== "memory"
            || record.changes.some(change => !same(change.before, change.after) || change.before?.revision !== change.after?.revision)) return fail("invalid");
        }
      };
      await assertInventory();
      for (const item of captured) if (sha256Digest(await readRecordBytes(item.file)) !== item.hash) return fail("changed");
      if (journalHash && sha256Digest(await readRecordBytes("undo-pending.json")) !== journalHash) return fail("changed");
      for (const binding of bindings) for (const file of ORIGIN_FILES) if (sha256Digest(await readArtifact(binding.runId, file)) !== binding.hashes[file]) return fail("changed");
      await assertInventory();
      if (sha256Digest(JSON.stringify(context)) !== contextHash) return fail("changed");
      check();
    };
    const assertUnchanged = async (pending?: LearningPendingMutation) => {
      await assertArtifactsUnchanged(pending);
      const latest = await stateOf(cwd, {root: "private", name});
      const shared = memory.publicDir ? await stateOf(cwd, {root: "public", name}) : null;
      if (!exact(latest, current) || (endpointShared ? !exact(shared, endpointShared) : shared !== null)) return fail("changed");
      if (sha256Digest(JSON.stringify(context)) !== contextHash) return fail("changed");
      check();
    };
    await assertUnchanged();
    check();
    return {status: "available", context, assertUnchanged, assertArtifactsUnchanged};
  } catch (error) {
    return {status: "unavailable", reason: error instanceof OriginFailure ? error.reason : missing(error) ? "missing" : "invalid"};
  }
}

/** An interrupted mutation cannot establish ownership of the current bytes. */
export async function checkPendingLearningMutations(cwd: string): Promise<void> {
  const lock = await acquireConsolidationLock(resolveConsolidationRunPaths(cwd));
  try {
    const paths = resolveMemoryPaths(cwd);
    const directory = await safePath(paths.agentDir, path.join("memory", "history", paths.scopeKey));
    let names: string[];
    try { names = await fs.readdir(directory); } catch (error) { if (missing(error)) return; throw error; }
    names = names.filter(name => name.endsWith(".json") && ID.test(name.slice(0, -5)));
    for (const name of names) {
      const record = await readLearningHistory(cwd, name.slice(0, -5));
      if (record.status !== "pending") continue;
      for (const change of record.changes) {
        if (!same(await stateOf(cwd, change.target), change.before)) throw new Error(`Unfinished learning ${record.id}: ${change.target.root}/${change.target.name} differs from its predecessor. Inspect /memory history ${record.id} and reconcile the files before learning resumes.`);
      }
      record.status = "abandoned";
      await save(cwd, record);
    }
  } finally { await lock.release(); }
}

export async function listLearningHistory(cwd: string): Promise<LearningHistory[]> {
  const paths = resolveMemoryPaths(cwd);
  const directory = await safePath(paths.agentDir, path.join("memory", "history", paths.scopeKey));
  let names: string[];
  try { names = await fs.readdir(directory); } catch (error) { if (missing(error)) return []; throw error; }
  const records: LearningHistory[] = [];
  let bytes = 0;
  for (const name of names.filter(name => name.endsWith(".json") && ID.test(name.slice(0, -5))).sort().reverse().slice(0, 50)) {
    const record = await readLearningHistory(cwd, name.slice(0, -5));
    bytes += Buffer.byteLength(JSON.stringify(record));
    if (bytes > MAX_HISTORY_BYTES) break;
    records.push(record);
  }
  return records;
}

export async function previewLearningUndo(cwd: string, id: string): Promise<{ record: LearningHistory; digest: string }> {
  const record = await readLearningHistory(cwd, id);
  if (record.status !== "applied" || !record.changes.length) throw new Error("Only a completed applied change can be undone");
  for (const change of record.changes) if (!same(await stateOf(cwd, change.target), change.after)) throw new Error(`Learning undo refused: ${change.target.name} changed after learning`);
  return { record, digest: sha256Digest(JSON.stringify(record)) };
}

async function restore(cwd: string, target: Target, state: FileState): Promise<void> {
  const file = await targetPath(cwd, target);
  if (state) await writeFileAtomic(file, Buffer.from(state.bytes, "base64"), state.mode);
  else { try { await fs.unlink(file); } catch (error) { if (!missing(error)) throw error; } }
}

async function assertUndoPrivacy(cwd: string, changes: Change[], direction: "before" | "after" = "before"): Promise<void> {
  const paths = resolveMemoryPaths(cwd);
  if (!paths.publicDir) return;
  const desired = async (target: Target): Promise<FileState> => {
    const change = changes.find(item => item.target.root === target.root && item.target.name === target.name);
    return change ? change[direction] : stateOf(cwd, target);
  };
  const index = await desired({ root: "private", name: "MEMORY.md" });
  const indexText = index ? Buffer.from(index.bytes, "base64").toString("utf8") : "";
  if (!changes.some(change => change.target.root !== "project")) return;
  const privateNames = parsePrivateIndexNames(indexText);
  const publicIndex = await desired({ root: "public", name: "MEMORY.md" });
  const publicText = publicIndex ? Buffer.from(publicIndex.bytes, "base64").toString("utf8") : "";
  if (/\(\s*harness[\s_-]+only\s*\)/i.test(publicText) || [...parseMemoryIndexNames(publicText)].some(name => privateNames.has(name))) throw new Error("Undo would expose private Memory index metadata");
  const names = new Set([...Object.keys(await hashMemoryRoot(paths.harnessDir)), ...Object.keys(await hashMemoryRoot(paths.publicDir)), ...changes.filter(item => item.target.root !== "project").map(item => item.target.name)]);
  names.delete("MEMORY.md");
  for (const name of names) {
    const privateOnly = privateNames.has(name.toLowerCase());
    const canonical = await desired({ root: "private", name });
    const shared = await desired({ root: "public", name });
    if (privateOnly ? shared !== null : canonical?.digest !== shared?.digest) throw new Error("Undo would violate Memory privacy or mirror equality");
  }
}

async function pendingUndoPath(cwd: string): Promise<string> {
  const paths = resolveMemoryPaths(cwd);
  return safePath(paths.agentDir, path.join("memory", "history", paths.scopeKey, "undo-pending.json"));
}

/** Recover a stopped undo by restoring the known successors; never infer ownership of a later edit. */
export async function recoverLearningUndo(cwd: string): Promise<void> {
  const lock = await acquireConsolidationLock(resolveConsolidationRunPaths(cwd));
  try {
    const pending = await pendingUndoPath(cwd);
    let id: unknown;
    try { id = JSON.parse((await readLearningFile(pending, 4096)).toString("utf8")).id; }
    catch (error) { if (missing(error)) return; throw error; }
    if (typeof id !== "string") throw new Error("Invalid interrupted undo journal");
    const recoveryId = id;
    await withFileMutationQueue(path.join(resolveMemoryPaths(cwd).cwd, ".pi", "harness.json"), async () => {
      const record = await readLearningHistory(cwd, recoveryId);
      if (record.status === "undoing") {
        await assertUndoPrivacy(cwd, record.changes, "after");
        for (const change of record.changes) {
          const current = await stateOf(cwd, change.target);
          if (!same(current, change.before) && !same(current, change.after)) throw new Error("Interrupted undo conflicts with a later edit; inspect learning history before continuing");
        }
        for (const change of [...record.changes].reverse()) {
          const current = await stateOf(cwd, change.target);
          if (same(current, change.after)) continue;
          if (!same(current, change.before)) throw new Error("Interrupted undo target changed during recovery");
          await restore(cwd, change.target, change.after);
        }
        await assertUndoPrivacy(cwd, record.changes, "after");
        record.status = "applied";
        await save(cwd, record);
      } else if (record.status !== "applied" && record.status !== "undone") throw new Error("Interrupted undo journal does not name an applied change");
      await fs.unlink(pending);
    });
  } finally { await lock.release(); }
}

export async function undoLearningChange(cwd: string, id: string, approvedDigest: string): Promise<void> {
  const lock = await acquireConsolidationLock(resolveConsolidationRunPaths(cwd));
  try {
    await withFileMutationQueue(path.join(resolveMemoryPaths(cwd).cwd, ".pi", "harness.json"), async () => {
      const journal = await pendingUndoPath(cwd);
      let interrupted = false;
      try { await fs.lstat(journal); interrupted = true; } catch (error) { if (!missing(error)) throw error; }
      if (interrupted) throw new Error("Resolve the interrupted learning undo before starting another undo");
      const { record, digest } = await previewLearningUndo(cwd, id);
      if (digest !== approvedDigest) throw new Error("Learning undo record changed after preview");
      await assertUndoPrivacy(cwd, record.changes);
      await writeFileAtomic(journal, JSON.stringify({ id: record.id }), 0o600);
      record.status = "undoing";
      await save(cwd, record);
      const restored: Change[] = [];
      try {
        for (const change of record.changes) {
          if (!same(await stateOf(cwd, change.target), change.after)) throw new Error("Learning undo target changed during restoration");
          restored.push(change);
          await restore(cwd, change.target, change.before);
        }
        record.status = "undone";
        await save(cwd, record);
        await fs.unlink(journal);
      } catch (error) {
        for (const change of restored.reverse()) {
          const current = await stateOf(cwd, change.target);
          if (same(current, change.after)) continue;
          if (!same(current, change.before)) throw new Error("Undo rollback refused to overwrite a concurrent edit");
          await restore(cwd, change.target, change.after);
        }
        record.status = "applied";
        await save(cwd, record);
        await fs.unlink(journal);
        throw error;
      }
    });
  } finally { await lock.release(); }
}
