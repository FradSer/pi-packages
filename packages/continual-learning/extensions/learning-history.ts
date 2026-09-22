import fs from "node:fs/promises";
import { constants } from "node:fs";
import path from "node:path";
import { randomBytes } from "node:crypto";
import { getAgentDir, withFileMutationQueue } from "@earendil-works/pi-coding-agent";
import { acquireConsolidationLock, containsSensitiveMemoryMaterial, hashMemoryRoot, normalizeMirrorDrift, resolveConsolidationRunPaths, sha256Digest, writeFileAtomic } from "./consolidation-run";
import { isMemoryFilename } from "./memory-files";
import { canonicalProjectCwd, resolveMemoryPaths, type MemoryPaths } from "./memory-paths";
import type { LearningSurface } from "./learning-controls";

const MAX_FILE_BYTES = 1_000_000;
const MAX_HISTORY_BYTES = 32 * 1024 * 1024;
const ID = /^change_[a-z0-9]+_[a-f0-9]{16}$/;
type Target = { root: "private" | "public" | "project"; name: string };
type FileState = { bytes: string; mode: number; digest: string } | null;
interface Change { target: Target; before: FileState; after: FileState }
export interface LearningHistory {
  version: 1;
  id: string;
  cwd: string;
  agentDir: string;
  phase: LearningSurface;
  createdAt: string;
  status: "pending" | "applied" | "proposed" | "undoing" | "undone" | "abandoned";
  changes: Change[];
  proposal?: unknown;
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
    const bytes = await readLearningFile(file, MAX_FILE_BYTES);
    return { bytes: bytes.toString("base64"), mode: (await fs.lstat(file)).mode & 0o777, digest: sha256Digest(bytes) };
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
  return { version: 1, id: `change_${Date.now().toString(36)}_${randomBytes(8).toString("hex")}`, cwd: paths.cwd, agentDir: paths.agentDir, phase, createdAt: new Date().toISOString(), status, changes: [] };
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
  assertNoSensitiveHistory(record.proposal);
  for (const change of record.changes) for (const state of [change.before, change.after]) {
    if (state) assertNoSensitiveHistory(Buffer.from(state.bytes, "base64").toString("utf8"));
  }
}

async function save(cwd: string, record: LearningHistory): Promise<void> {
  assertSafeRecord(record);
  const bytes = JSON.stringify(record, null, 2) + "\n";
  if (Buffer.byteLength(bytes) > MAX_HISTORY_BYTES) throw new Error("Learning history exceeds its byte limit");
  await writeFileAtomic(await historyPath(cwd, record.id), bytes, 0o600);
}

/** Call while holding the existing consolidation lock, immediately around mutation. */
export async function recordLearningMutation<T>(cwd: string, phase: LearningSurface, files: readonly string[], mutate: () => Promise<T>, plan?: unknown): Promise<T> {
  assertNoSensitiveHistory(plan);
  const record = await newRecord(cwd, phase, "pending");
  for (const file of [...new Set(files)].sort()) {
    const target = targetFor(cwd, file);
    const before = await stateOf(cwd, target);
    record.changes.push({ target, before, after: before });
  }
  await save(cwd, record);
  let succeeded = false;
  try {
    const result = await mutate();
    succeeded = !(result && typeof result === "object" && "outcome" in result && result.outcome !== "applied");
    return result;
  }
  finally {
    for (const change of record.changes) change.after = await stateOf(cwd, change.target);
    record.changes = record.changes.filter(change => !same(change.before, change.after));
    if (record.changes.length) { record.status = succeeded ? "applied" : "pending"; await save(cwd, record); }
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
  const privateNames = index.split(/\r?\n/).filter(line => /\(\s*harness[\s_-]+only\s*\)/i.test(line)).flatMap(line => [...line.matchAll(/\]\(([A-Za-z0-9][A-Za-z0-9_-]*\.md)\)/g)].map(match => match[1]));
  const names = new Set(["MEMORY.md", ...Object.keys({ ...canonical, ...shared }).filter(name => canonical[name] !== shared[name]), ...privateNames.filter(name => shared[name])]);
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
  const bytes = Buffer.from(state.bytes, "base64");
  return bytes.length <= MAX_FILE_BYTES && bytes.toString("base64") === state.bytes && sha256Digest(bytes) === state.digest;
}

export async function readLearningHistory(cwd: string, id: string): Promise<LearningHistory> {
  const raw: unknown = JSON.parse((await readLearningFile(await historyPath(cwd, id))).toString("utf8"));
  if (!raw || typeof raw !== "object") throw new Error("Invalid history record");
  const record = raw as LearningHistory;
  const paths = resolveMemoryPaths(cwd);
  if (record.version !== 1 || record.id !== id || record.cwd !== paths.cwd || record.agentDir !== paths.agentDir || !["memory", "harness", "agents"].includes(record.phase) || !["pending", "applied", "proposed", "undoing", "undone", "abandoned"].includes(record.status) || !Array.isArray(record.changes) || record.changes.length > 8194) throw new Error("Invalid or foreign history record");
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
  const privateNames = new Set(indexText.split(/\r?\n/).filter(line => /\(\s*harness[\s_-]+only\s*\)/i.test(line))
    .flatMap(line => [...line.matchAll(/\]\(([A-Za-z0-9][A-Za-z0-9_-]*\.md)\)/g)].map(match => match[1].toLowerCase())));
  const publicIndex = await desired({ root: "public", name: "MEMORY.md" });
  const publicText = publicIndex ? Buffer.from(publicIndex.bytes, "base64").toString("utf8") : "";
  if (/\(\s*harness[\s_-]+only\s*\)/i.test(publicText) || [...publicText.matchAll(/\]\(([A-Za-z0-9][A-Za-z0-9_-]*\.md)\)/g)].some(match => privateNames.has(match[1].toLowerCase()))) throw new Error("Undo would expose private Memory index metadata");
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
