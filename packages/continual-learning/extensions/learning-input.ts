/** Parent-owned, bounded fallback for an explicitly requested full run. */
import fs from "node:fs/promises";
import { constants } from "node:fs";
import path from "node:path";
import * as piSdk from "@earendil-works/pi-coding-agent";
import { buildContextEntries, parseSessionEntries, type SessionEntry } from "@earendil-works/pi-coding-agent";
import { canonicalProjectCwd } from "./memory-paths";
import { hasLearningInput } from "./learning-efficiency";
import { currentTaskRange, currentTaskSlice, requestedMemoryTaskSlice, type TaskSlice } from "./incremental-learning";
import { validManualMemoryReference, type BacklogEntry } from "./learning-backlog";
import { sha256Digest, captureMemoryCommandPhase, type MemoryCommandPhaseInvocation } from "./consolidation-run";

const MAX_SESSION_BYTES = 8 * 1024 * 1024;
const MAX_SESSION_FILES = 512;
const MAX_RECENT_CANDIDATES = 12;
const MAX_SESSION_ENTRIES = 8_192;
const RECENT_AGE_MS = 7 * 24 * 60 * 60 * 1000;

export interface RecentLearningInput {
  entries: unknown[];
  sessionId: string;
  sourceDigest: string;
  contextEntries?: unknown[];
  nativeEntries?: SessionEntry[];
}

export const MANUAL_MEMORY_REQUEST_ENTRY = "continual-learning-memory-request";
export interface ManualMemoryRequestMarker {
  version: 1;
  invocationId: string;
  scopeKey: string;
  sessionId: string;
  request: string;
  prefixCount: number;
  prefixDigest: string;
  range: {from: number; to: number} | null;
  taskDigest: string;
  projectedDigest: string;
}

/** Preserve the native prefix separately; bookkeeping rows supply no source facts. */
export function manualMemoryTaskSlice(request: string, prefix: readonly unknown[]): TaskSlice {
  return requestedMemoryTaskSlice(request, prefix.filter(row => !row || typeof row !== "object"
    || !("type" in row) || row.type !== "custom" || !("customType" in row) || row.customType !== MANUAL_MEMORY_REQUEST_ENTRY));
}

/** Reconstruct only a parent-persisted request; a custom row is not task evidence. */
export function resolveManualMemoryRequest(source: RecentLearningInput, entry: BacklogEntry,
  scopeKey: string): {request: string; taskSlice: TaskSlice; commandPhase: MemoryCommandPhaseInvocation} | undefined {
  const reference = entry.manualRequest;
  if (!validManualMemoryReference(reference) || !source.nativeEntries) return;
  const markers = source.nativeEntries.filter(row => row.type === "custom" && row.customType === MANUAL_MEMORY_REQUEST_ENTRY
    && row.data && typeof row.data === "object" && (row.data as ManualMemoryRequestMarker).invocationId === reference.invocationId);
  if (markers.length !== 1 || markers[0].id !== reference.entryId) return;
  const marker = markers[0];
  if (marker.type !== "custom") return;
  // Follow the native retained leaf, including entries hidden by compaction.
  // A historical branch or a superseded request is not current authority.
  const byId = new Map(source.nativeEntries.map(row => [row.id,row]));
  const visited = new Set<string>();
  let descendant = source.nativeEntries.at(-1);
  while (descendant && descendant.id !== marker.id) {
    if (visited.has(descendant.id) || descendant.type === "message" && descendant.message.role === "user"
      || descendant.type === "custom" && descendant.customType === MANUAL_MEMORY_REQUEST_ENTRY) return;
    visited.add(descendant.id);
    descendant = descendant.parentId === null ? undefined : byId.get(descendant.parentId);
  }
  if (!descendant) return;
  const data = marker.data as ManualMemoryRequestMarker;
  if (!data || Object.keys(data).length !== 10 || data.version !== 1 || data.scopeKey !== scopeKey
    || data.sessionId !== source.sessionId || typeof data.request !== "string" || !data.request.trim()
    || sha256Digest(data.request) !== reference.requestDigest || !Number.isSafeInteger(data.prefixCount) || data.prefixCount < 0) return;
  const prefix = marker.parentId === null ? [] : buildContextEntries(source.nativeEntries, marker.parentId);
  if (prefix.length !== data.prefixCount || sha256Digest(JSON.stringify(prefix)) !== data.prefixDigest) return;
  const range = currentTaskRange(prefix) ?? null;
  if (JSON.stringify(range) !== JSON.stringify(data.range)) return;
  const task = currentTaskSlice(prefix);
  if (sha256Digest(JSON.stringify(task)) !== data.taskDigest || entry.digest !== data.taskDigest
    || entry.from !== (range?.from ?? data.prefixCount) || entry.to !== (range?.to ?? data.prefixCount)) return;
  const taskSlice = manualMemoryTaskSlice(data.request, prefix);
  if (sha256Digest(JSON.stringify(taskSlice)) !== data.projectedDigest) return;
  const commandPhase = captureMemoryCommandPhase({}, data.request, taskSlice,
    {invocationId: data.invocationId, sessionId: data.sessionId, scopeKey});
  return {request:data.request, taskSlice, commandPhase};
}

function inside(root: string, file: string): boolean {
  const relative = path.relative(root, file);
  return Boolean(relative) && relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

/** Pi session logs are append-only: every parent must precede its child. */
function validEntryGraph(entries: readonly SessionEntry[]): boolean {
  if (entries.length > MAX_SESSION_ENTRIES) return false;
  const ids = new Set<string>();
  for (const entry of entries) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)
      || typeof entry.id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(entry.id)
      || ids.has(entry.id) || (entry.parentId !== null && !ids.has(entry.parentId))) return false;
    ids.add(entry.id);
  }
  return true;
}

/** Pi retry can delete an empty failed assistant reply. It removed no learning
 * content, but its error metadata must still stay out of returned replay data.
 * Every meaningful edit remains refused for exact historical replay. */
function emptyRetryRemovals(entries: readonly SessionEntry[]): Set<string> | undefined {
  const previous = new Map<string, SessionEntry>(), removed = new Set<string>();
  const validTimestamp = (value: unknown): boolean => typeof value === "string"
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value) && Number.isFinite(Date.parse(value));
  for (const entry of entries) {
    if (entry.type === "context_edit") {
      const target = previous.get(entry.targetId);
      if (entry.replacement !== null || removed.has(entry.targetId) || !validTimestamp(entry.timestamp)
        || Object.keys(entry).some(key => !["type", "id", "parentId", "timestamp", "targetId", "replacement"].includes(key))
        || target?.type !== "message" || target.message.role !== "assistant"
        || !validTimestamp(target.timestamp) || target.message.stopReason !== "error" || !Array.isArray(target.message.content) || target.message.content.length !== 0
        || Object.keys(target).some(key => !["type", "id", "parentId", "timestamp", "message"].includes(key))
        || typeof target.message.timestamp !== "number" || !Number.isFinite(target.message.timestamp)) return undefined;
      removed.add(entry.targetId);
    }
    previous.set(entry.id, entry);
  }
  return removed;
}

/** Never open a SessionManager: opening can migrate/write the source log. */
export async function recentProjectLearningInput(input: {
  cwd: string;
  agentDir: string;
  sessionDir?: string;
  currentSessionFile?: string;
  signal?: AbortSignal;
  /** Exact backlog reference; no age-based or unrelated-session fallback. */
  requestedSessionFile?: string;
}): Promise<RecentLearningInput | undefined> {
  if (!input.sessionDir || input.signal?.aborted) return undefined;
  const sessionsRoot = path.join(canonicalProjectCwd(input.agentDir), "sessions");
  let directory: string;
  try {
    const rootStat = await fs.lstat(sessionsRoot);
    const dirStat = await fs.lstat(input.sessionDir);
    if (!rootStat.isDirectory() || rootStat.isSymbolicLink() || !dirStat.isDirectory() || dirStat.isSymbolicLink()) return undefined;
    directory = await fs.realpath(input.sessionDir);
    if (!inside(sessionsRoot, directory)) return undefined;
    let current = sessionsRoot;
    for (const part of path.relative(sessionsRoot, directory).split(path.sep)) {
      current = path.join(current, part);
      const stat = await fs.lstat(current);
      if (!stat.isDirectory() || stat.isSymbolicLink()) return undefined;
    }
  } catch { return undefined; }
  const rootIdentity = await fs.lstat(sessionsRoot);
  const directoryIdentity = await fs.lstat(directory);
  const stableDirectory = async (): Promise<boolean> => {
    const root = await fs.lstat(sessionsRoot);
    if (root.isSymbolicLink() || !root.isDirectory() || root.dev !== rootIdentity.dev || root.ino !== rootIdentity.ino
      || await fs.realpath(directory) !== directory) return false;
    const stat = await fs.lstat(directory);
    return !stat.isSymbolicLink() && stat.isDirectory()
      && stat.dev === directoryIdentity.dev && stat.ino === directoryIdentity.ino;
  };
  const candidates: Array<{ file: string; modified: number }> = [];
  if (input.requestedSessionFile) {
    // Exact references do not depend on the number or age of unrelated logs.
    const file = path.resolve(input.requestedSessionFile);
    if (canonicalProjectCwd(path.dirname(file)) !== directory) return undefined;
    try {
      const stat = await fs.lstat(file);
      if (!stat.isFile() || stat.isSymbolicLink() || stat.size > MAX_SESSION_BYTES || stat.size === 0) return undefined;
      candidates.push({file, modified:stat.mtimeMs});
    } catch { return undefined; }
  } else {
  let count = 0;
  for await (const entry of await fs.opendir(directory)) {
    if (input.signal?.aborted || ++count > MAX_SESSION_FILES) return undefined;
    if (!entry.isFile() || entry.isSymbolicLink() || !entry.name.endsWith(".jsonl")) continue;
    const file = path.join(directory, entry.name);
    if (!input.requestedSessionFile && input.currentSessionFile && canonicalProjectCwd(file) === canonicalProjectCwd(input.currentSessionFile)) continue;
    const stat = await fs.lstat(file);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.size > MAX_SESSION_BYTES || stat.size === 0) continue;
    if (!input.requestedSessionFile && Date.now() - stat.mtimeMs > RECENT_AGE_MS) continue;
    candidates.push({ file, modified: stat.mtimeMs });
  }
  }
  candidates.sort((left, right) => right.modified - left.modified || right.file.localeCompare(left.file));
  for (const candidate of candidates.slice(0, MAX_RECENT_CANDIDATES)) {
    if (input.signal?.aborted || !await stableDirectory()) return undefined;
    let handle: fs.FileHandle | undefined;
    try {
      handle = await fs.open(candidate.file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
      const before = await handle.stat();
      if (!before.isFile() || before.size > MAX_SESSION_BYTES) continue;
      const bytes = Buffer.alloc(before.size);
      let offset = 0;
      while (offset < bytes.length) {
        const read = await handle.read(bytes, offset, bytes.length - offset, offset);
        if (!read.bytesRead || input.signal?.aborted) break;
        offset += read.bytesRead;
      }
      const after = await fs.lstat(candidate.file);
      if (offset !== before.size || after.isSymbolicLink() || before.dev !== after.dev || before.ino !== after.ino
        || before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ctimeMs !== after.ctimeMs
        || !await stableDirectory()) continue;
      const text = bytes.toString("utf8");
      // Pi's parser tolerates bad lines; learning must not silently hide missing evidence.
      for (const line of text.split("\n")) if (line.trim()) JSON.parse(line);
      const parsed = parseSessionEntries(text);
      const header = parsed[0];
      if (!header || header.type !== "session" || typeof header.cwd !== "string"
        || canonicalProjectCwd(header.cwd) !== canonicalProjectCwd(input.cwd)
        || typeof header.id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(header.id)) continue;
      const sessionEntries = parsed.filter((entry): entry is SessionEntry => entry.type !== "session");
      if (parsed.slice(1).some(entry => entry.type === "session") || !validEntryGraph(sessionEntries)) continue;
      // An older pointer must never resurrect a meaningful later redaction.
      // Only Pi's null-removal of a content-free assistant failure is eligible;
      // sanitize its raw metadata too while preserving indexed backlog slots.
      const removedErrors = input.requestedSessionFile ? emptyRetryRemovals(sessionEntries) : undefined;
      if (input.requestedSessionFile && !removedErrors) continue;
      // Wildcard peers can resolve to an older SDK locally. Such SDKs cannot
      // project Pi v1 context edits: decline that source instead of reviving it.
      const projectionApi = piSdk as typeof piSdk & { buildSessionProjection?: (entries: SessionEntry[]) => {
        entries: Array<{ sourceEntry: SessionEntry; messages: unknown[] }>;
      } };
      let entries: unknown[];
      if (projectionApi.buildSessionProjection) {
        const projected = projectionApi.buildSessionProjection(sessionEntries).entries;
        if (removedErrors?.size && [...removedErrors].some(id =>
          !projected.some(row => row.sourceEntry.id === id && row.messages.length === 0))) continue;
        entries = projected.flatMap<unknown>(({ sourceEntry, messages }) => {
          // Summaries and extension rows are not raw human/tool evidence;
          // retaining their originals could revive edited-away private text.
          if (sourceEntry.type !== "message") return [];
          return messages.map(message => ({ ...sourceEntry, message }));
        });
      } else {
        if (parsed.some(entry => (entry as { type: string }).type === "context_edit")) continue;
        entries = buildContextEntries(sessionEntries).filter(entry => entry.type === "message");
      }
      if ((!hasLearningInput(entries) && !(input.requestedSessionFile && sessionEntries.some(row => row.type === "custom" && row.customType === MANUAL_MEMORY_REQUEST_ENTRY))) || input.signal?.aborted) continue;
      return { entries, sessionId: header.id, sourceDigest: sha256Digest(bytes),
        ...(input.requestedSessionFile ? {nativeEntries:sessionEntries, contextEntries:buildContextEntries(sessionEntries).map(entry => {
          if (!removedErrors?.has(entry.id) || entry.type !== "message" || entry.message.role !== "assistant") return entry;
          // currentTaskSlice already projects these exact empty message fields.
          // This skeleton retains its digest and raw range indexes without
          // exposing a removed errorMessage, provider, model or usage payload.
          return {type: "message", id: entry.id, parentId: entry.parentId, timestamp: entry.timestamp,
            message: {role: "assistant", content: [], timestamp: entry.message.timestamp}};
        })} : {}) };
    } catch {
      // An unreadable, changing, malformed or unrelated candidate is not authority.
    } finally { await handle?.close().catch(() => {}); }
  }
  return undefined;
}
