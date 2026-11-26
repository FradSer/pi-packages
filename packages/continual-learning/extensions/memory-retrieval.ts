import { createHash } from "node:crypto";
import path from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";
import type { MemoryEntry } from "./memory-files";

const MEMORY_REFERENCE_CUSTOM_TYPE = "continual-learning-memory-reference";

/** This extension injects its own Memory reference and learning result. That
 * text indexes the records a review judges, so it routes and revisits knowledge
 * but is never factual support for a claim about those same records. */
export function selfInjectedContextEntry(entry: unknown): boolean {
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return false;
  const row = entry as { message?: unknown; customType?: unknown; role?: unknown };
  const message = row.message && typeof row.message === "object" && !Array.isArray(row.message)
    ? row.message as { customType?: unknown; role?: unknown } : row;
  if (row.role === "user" || row.role === "toolResult" || message.role === "user" || message.role === "toolResult") return false;
  const customType = row.customType ?? message.customType;
  return customType === MEMORY_REFERENCE_CUSTOM_TYPE || customType === "continual-learning-result"
    || customType === "memory-use-observation" || customType === "harness-behavior-observation";
}

/** Pi 1.0 does not publicly export its read resolver. Match its lexical
 * aliases only; do not probe paths or follow symlinks to infer read success. */
function observedReadPath(input: string, cwd: string): string | undefined {
  let normalized = input.replace(/[\u00A0\u2000-\u200A\u202F\u205F\u3000]/g, " ");
  if (normalized.startsWith("@")) normalized = normalized.slice(1);
  if (process.platform === "win32" && normalized.startsWith("/") && !normalized.startsWith("//") && !normalized.includes("\\")) {
    const drive = normalized.match(/^\/(?:mnt\/|cygdrive\/)?([a-z])(?:\/(.*))?$/i);
    if (drive) normalized = `${drive[1].toUpperCase()}:\\${drive[2]?.replaceAll("/", "\\") ?? ""}`;
  }
  if (normalized === "~") normalized = homedir();
  else if (normalized.startsWith("~/") || (process.platform === "win32" && normalized.startsWith("~\\"))) normalized = path.join(homedir(), normalized.slice(2));
  if (normalized.startsWith("file://")) {
    try { normalized = fileURLToPath(normalized); } catch { return undefined; }
  }
  return path.resolve(cwd, normalized);
}

/** A successful read nominates existing knowledge for review, never for mutation
 * or factual support. Pair frozen session records, not filenames mentioned in
 * prose; a failed, pending or ambiguous invocation proves no exposure. */
export function observedMemoryReadNames(
  entries: readonly unknown[],
  cwd: string,
  indexed: readonly { name: string; file: string }[],
): string[] {
  const files = new Map(indexed.map(entry => [path.resolve(entry.file), entry.name]));
  const calls = new Map<string, { name?: string; file?: string; position: number }[]>();
  const results = new Map<string, { message: Record<string, unknown>; position: number }[]>();
  entries.forEach((entry, position) => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) return;
    const row = entry as Record<string, unknown>;
    const message = row.message && typeof row.message === "object" && !Array.isArray(row.message)
      ? row.message as Record<string, unknown> : row;
    if (message.role === "assistant" && Array.isArray(message.content)) {
      for (const block of message.content) {
        if (!block || typeof block !== "object" || block.type !== "toolCall" || typeof block.id !== "string") continue;
        const args = block.arguments;
        const file = args && typeof args === "object" && !Array.isArray(args) && typeof args.path === "string"
          ? observedReadPath(args.path, cwd) : undefined;
        const previous = calls.get(block.id) ?? [];
        previous.push({ name: block.name, file, position });
        calls.set(block.id, previous);
      }
    }
    if (message.role === "toolResult" && typeof message.toolCallId === "string") {
      const previous = results.get(message.toolCallId) ?? [];
      previous.push({ message, position });
      results.set(message.toolCallId, previous);
    }
  });
  const observed: Array<{ name: string; position: number }> = [];
  for (const [id, invocations] of calls) {
    const outcomes = results.get(id);
    if (invocations.length !== 1 || outcomes?.length !== 1) continue;
    const call = invocations[0], result = outcomes[0];
    if (call.name !== "read" || !call.file || call.position >= result.position || result.message.toolName !== "read" || result.message.isError !== false) continue;
    const name = files.get(call.file);
    const content = result.message.content;
    if (name && Array.isArray(content) && content.some(block => block && typeof block === "object" && block.type === "text" && typeof block.text === "string" && block.text.trim())) {
      observed.push({ name, position: result.position });
    }
  }
  return [...new Set(observed.sort((a, b) => b.position - a.position).map(entry => entry.name))];
}

export interface MemoryUseScope {
  sessionId: string;
  cwd: string;
  parentEntryId: string | null;
}

type ObservationEmitter = (data: Record<string, unknown>) => string | undefined;
type NativeReadEnd = {toolName: string; toolCallId: string; result: unknown; isError: boolean; durationMs?: number};
const useHash = (text: string): string => createHash("sha256").update(text).digest("hex");
const useValueHash = (value: unknown): string => useHash(JSON.stringify(value));
function recordValue(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}
function exactText(content: unknown): string | undefined {
  if (!Array.isArray(content) || content.length !== 1 || !recordValue(content[0])
    || content[0].type !== "text" || typeof content[0].text !== "string") return;
  return content[0].text;
}

/** Local observations only. A matching persisted result proves neither model
 * attention nor correct knowledge, current file identity, or a useful lesson. */
export class MemoryUseTracker {
  private prepared?: {scope: MemoryUseScope; id: string; dataDigest: string;
    entries: Array<{file: string; fileDigest: string; revision: string; listed: boolean}>};
  private starts = new Map<string, {preparationId: string; inputDigest: string}>();
  private pending = new Map<string, {preparationId: string; inputDigest: string; revision: string; durationMs: number}>();
  private seen = new Set<string>();

  reset(): void { this.prepared = undefined; this.starts.clear(); this.pending.clear(); }
  private sameScope(scope: MemoryUseScope): boolean {
    return this.prepared?.scope.sessionId === scope.sessionId && this.prepared.scope.cwd === scope.cwd;
  }
  private emit(data: Record<string, unknown>, emit: ObservationEmitter): string | undefined {
    try { return emit(data); } catch { return undefined; }
  }

  prepare(scope: MemoryUseScope, entries: readonly MemoryEntry[], reference: string, section: string, emit: ObservationEmitter): void {
    this.reset();
    if (!scope.sessionId || !path.isAbsolute(scope.cwd) || !reference || !section) return;
    const lines = new Set(reference.split("\n").map(line => /^- ([A-Za-z0-9][A-Za-z0-9_-]*\.md)(?:\s|$)/.exec(line)?.[1]).filter(Boolean));
    const snapshots = entries.slice(0, 128).filter((entry): entry is MemoryEntry & {fileRevision: string} => entry.contentTruncated === false && entry.content.length <= 64_000
      && typeof entry.fileRevision === "string" && /^[a-f0-9]{64}$/.test(entry.fileRevision)
      && useHash(entry.content) === entry.fileRevision && path.isAbsolute(entry.readPath));
    const data = {version: 1, phase: "section-prepared", sessionId: scope.sessionId, parentEntryId: scope.parentEntryId,
      projectDigest: useValueHash(scope.cwd), sectionDigest: useHash(section),
      entries: entries.slice(0, 128).map(entry => ({fileDigest: useValueHash(entry.readPath),
        nameDigest: useValueHash(entry.filename), listed: lines.has(entry.filename),
        completeSnapshot: snapshots.some(snapshot => snapshot === entry), revision: snapshots.some(snapshot => snapshot === entry) ? entry.fileRevision : null})),
      omittedSnapshots: Math.max(0, entries.length - 128), wireDelivery: "unverified", modelConsumption: "unverified", effect: "cannot-attribute"};
    const dataDigest = useValueHash(data), id = this.emit(data, emit);
    if (!id || id === scope.parentEntryId) return;
    this.prepared = {scope: {...scope}, id, dataDigest, entries: snapshots.map(entry => ({file: path.resolve(entry.readPath),
      fileDigest: useValueHash(entry.readPath), revision: entry.fileRevision, listed: lines.has(entry.filename)}))};
  }

  nativeStart(scope: MemoryUseScope | undefined, event: {toolName: string; toolCallId: string; args: unknown}): void {
    if (event.toolName !== "read" || !event.toolCallId) return;
    if (this.seen.has(event.toolCallId)) { this.starts.delete(event.toolCallId); this.pending.delete(event.toolCallId); return; }
    if (this.seen.size >= 4096) return;
    this.seen.add(event.toolCallId);
    if (!scope || !this.sameScope(scope) || !this.prepared || this.starts.size >= 256) return;
    this.starts.set(event.toolCallId, {preparationId: this.prepared.id, inputDigest: useValueHash(event.args)});
  }

  nativeEnd(scope: MemoryUseScope, event: NativeReadEnd): void {
    if (event.toolName !== "read" || !this.sameScope(scope) || !event.toolCallId) return;
    if (this.pending.has(event.toolCallId)) { this.pending.delete(event.toolCallId); return; }
    const start = this.starts.get(event.toolCallId);
    this.starts.delete(event.toolCallId);
    if (!start || start.preparationId !== this.prepared?.id) return;
    if (this.pending.size >= 256 || event.isError !== false || typeof event.durationMs !== "number"
      || !Number.isFinite(event.durationMs) || event.durationMs < 0 || !recordValue(event.result)) return;
    const text = exactText(event.result.content);
    if (text === undefined || text.length > 64_000) return;
    const revision = useHash(text);
    if (this.prepared?.entries.filter(entry => entry.revision === revision).length !== 1) return;
    this.pending.set(event.toolCallId, {...start, revision, durationMs: event.durationMs});
  }

  settle(scope: MemoryUseScope, branch: readonly unknown[], emit: ObservationEmitter): void {
    const prepared = this.prepared;
    if (!prepared || !this.sameScope(scope)) { this.reset(); return; }
    if (!this.pending.size) { this.starts.clear(); return; }
    try {
      if (branch.length > 10_000) return;
      const rows = branch.filter(recordValue);
      if (rows.length !== branch.length || new Set(rows.map(row => row.id)).size !== rows.length) return;
      const start = rows.findIndex(row => row.id === prepared.id);
      if (start < 0 || rows[start].customType !== "memory-use-observation" || useValueHash(rows[start].data) !== prepared.dataDigest) return;
      for (let i = start; i < rows.length; i++) {
        if (typeof rows[i].id !== "string" || rows[i].parentId !== (i === start ? prepared.scope.parentEntryId : rows[i - 1].id)) return;
      }
      const calls = new Map<string, Array<{row: Record<string, unknown>; index: number; call: Record<string, unknown>}>>();
      const results = new Map<string, Array<{row: Record<string, unknown>; index: number; message: Record<string, unknown>}>>();
      rows.forEach((row, index) => {
        const message = row.message;
        if (!recordValue(message)) return;
        if (message.role === "assistant" && Array.isArray(message.content)) for (const call of message.content) {
          if (!recordValue(call) || call.type !== "toolCall" || typeof call.id !== "string" || !this.pending.has(call.id)) continue;
          const previous = calls.get(call.id) ?? [];
          if (previous.length < 2) calls.set(call.id, [...previous, {row, index, call}]);
        }
        if (message.role === "toolResult" && typeof message.toolCallId === "string" && this.pending.has(message.toolCallId)) {
          const previous = results.get(message.toolCallId) ?? [];
          if (previous.length < 2) results.set(message.toolCallId, [...previous, {row, index, message}]);
        }
      });
      for (const [id, pending] of this.pending) {
        const invocations = calls.get(id), outcomes = results.get(id);
        if (invocations?.length !== 1 || outcomes?.length !== 1) continue;
        const invocation = invocations[0], outcome = outcomes[0], args = invocation.call.arguments;
        if (pending.preparationId !== prepared.id || useValueHash(args) !== pending.inputDigest
          || invocation.index <= start || outcome.index <= invocation.index || invocation.call.name !== "read"
          || outcome.message.toolName !== "read" || outcome.message.isError !== false || !recordValue(args) || typeof args.path !== "string") continue;
        const file = observedReadPath(args.path, scope.cwd), text = exactText(outcome.message.content);
        const candidates = prepared.entries.filter(entry => entry.file === file && entry.revision === pending.revision);
        if (candidates.length !== 1 || text === undefined || useHash(text) !== pending.revision) continue;
        this.emit({version: 1, phase: "full-body-result-observed", sessionId: scope.sessionId,
          preparationEntryId: prepared.id, callEntryId: invocation.row.id, resultEntryId: outcome.row.id,
          toolCallIdDigest: useValueHash(id), fileDigest: candidates[0].fileDigest,
          revision: pending.revision, listed: candidates[0].listed, durationMs: pending.durationMs,
          resultDigest: useValueHash(outcome.message.content), physicalOrigin: "unverified", wireDelivery: "unverified",
          modelConsumption: "unverified", taskOutcome: "unverified", effect: "cannot-attribute"}, emit);
      }
    } finally { this.starts.clear(); this.pending.clear(); }
  }
}
