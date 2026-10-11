/** Bounded, source-verified replay of learning, never replay of user task tools. */
import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { readBacklog, acknowledgeBacklog, backlogIdentity, safeBacklogStorage, readBoundedBacklogFile, withBacklogLock, type BacklogEntry } from "./learning-backlog";
import { recentProjectLearningInput } from "./learning-input";
import { currentTaskSlice } from "./incremental-learning";
import { sha256Digest, writeFileAtomic } from "./consolidation-run";
import { resolveMemoryPaths } from "./memory-paths";
import { isLearningPipelineReceipt, pendingLearningOperations, type LearningPipelineReceipt, type LearningInputSource } from "./learning-efficiency";

export function learningReceiptComplete(receipt: LearningPipelineReceipt): boolean {
  if (pendingLearningOperations(receipt) > 0) return false;
  const final = new Map(receipt.attempts.map(attempt => [attempt.phase, attempt.outcome]));
  if ([...final.values()].some(outcome => ["failed", "rejected", "cancelled", "proposed"].includes(outcome))) return false;
  return (["memory", "harness", "agents"] as const).every(phase => !receipt.screen[phase]
    || ["applied", "noop", "screened"].includes(final.get(phase) ?? ""));
}

interface ReplayAttempt { at: string; outcome: string; receipt?: LearningPipelineReceipt }
interface ReplayState { attempts: ReplayAttempt[]; nextAttemptAt: number }

function readReplayState(file: string): ReplayState {
  if (!fs.existsSync(file)) return {attempts:[], nextAttemptAt:0};
  const state: ReplayState = JSON.parse(readBoundedBacklogFile(file, 256_000));
  if (!Array.isArray(state.attempts) || !Number.isFinite(state.nextAttemptAt)
    || state.attempts.some(attempt => !attempt || typeof attempt.outcome !== "string" || (attempt.receipt !== undefined && !isLearningPipelineReceipt(attempt.receipt)))) throw new Error("Invalid replay state");
  return state;
}

/** Acknowledge siblings first and the receipt-owning reference last. A crash
 * leaves that owner pending, so recovery can repeat the same exact receipt proof
 * without another model call or duplicate cost-bearing ledger rows. */
function acknowledgeReplayCompletion(cwd: string, entry: BacklogEntry, receipt: LearningPipelineReceipt,
  backlog: ReturnType<typeof readBacklog>, agentDir: string): boolean {
  const paths = resolveMemoryPaths(cwd, agentDir);
  const id = backlogIdentity(paths.scopeKey, entry);
  const coverage = receipt.input?.backlogCoverage;
  const references = coverage ? coverage.map(item => backlog.entries.find(other =>
    backlogIdentity(paths.scopeKey, other) === item.id && other.sessionFile === entry.sessionFile
      && other.from === entry.from && other.from === item.from && other.to === item.to && other.digest === item.digest)) : [entry];
  if (coverage && (receipt.input?.backlogId !== id || !coverage.some(item => item.id === id))) return false;
  if (references.some(other => !other)) return false;
  const digest = sha256Digest(JSON.stringify(receipt));
  for (const other of references) if (other && backlogIdentity(paths.scopeKey, other) !== id
    && !acknowledgeBacklog(cwd, other, digest, agentDir)) return false;
  return acknowledgeBacklog(cwd, entry, digest, agentDir);
}

/** Write-ahead attempt marker. Caller must hold the project learning lease. */
export function beginBacklogAttempt(cwd: string, entry: BacklogEntry, agentDir = getAgentDir()): boolean {
  try {
    const paths = resolveMemoryPaths(cwd, agentDir);
    const id = backlogIdentity(paths.scopeKey, entry);
    const backlog = readBacklog(cwd, agentDir);
    if (backlog.error || backlog.malformed || !backlog.pendingEntries.some(({entry: pending}) => backlogIdentity(paths.scopeKey, pending) === id)) return false;
    const file = path.join(paths.agentDir, "learning", paths.scopeKey, `replay-${id}.json`);
    safeBacklogStorage(file, paths.agentDir, true);
    const state = readReplayState(file);
    const last = state.attempts.at(-1);
    if (last?.outcome === "completed" && last.receipt && learningReceiptComplete(last.receipt)) {
      acknowledgeReplayCompletion(cwd, entry, last.receipt, backlog, agentDir);
      return false;
    }
    if (state.attempts.length >= 16) return false;
    state.attempts.push({at:new Date().toISOString(), outcome:"running"});
    const text = JSON.stringify(state);
    if (Buffer.byteLength(text) > 256_000) return false;
    const temporary = `${file}.${randomUUID()}.tmp`;
    try {
      fs.writeFileSync(temporary, text, {flag:"wx",mode:0o600});
      safeBacklogStorage(file, paths.agentDir);
      fs.renameSync(temporary, file);
    } finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
    return true;
  } catch { return false; }
}

/** Record normal learning too: retries must include its failure and token cost. */
export function recordBacklogAttempt(cwd: string, entry: BacklogEntry, receipt: LearningPipelineReceipt, agentDir = getAgentDir()): boolean {
  // Caller holds the project learning lease; unrelated backlog writers cannot
  // contend with this per-project attempt ledger.
  try {
    if (!isLearningPipelineReceipt(receipt)) return false;
    const paths = resolveMemoryPaths(cwd, agentDir);
    const file = path.join(paths.agentDir, "learning", paths.scopeKey, `replay-${backlogIdentity(paths.scopeKey, entry)}.json`);
    safeBacklogStorage(file, paths.agentDir, true);
    const state = readReplayState(file);
    if (state.attempts.length >= 16 && state.attempts.at(-1)?.outcome !== "running") return false;
    const attempt = {at:new Date().toISOString(), outcome:learningReceiptComplete(receipt) ? "completed" : "failed", receipt};
    if (state.attempts.at(-1)?.outcome === "running") state.attempts[state.attempts.length - 1] = attempt;
    else state.attempts.push(attempt);
    state.nextAttemptAt = Date.now() + Math.min(24 * 60 * 60_000, 60_000 * 2 ** state.attempts.length);
    const text = JSON.stringify(state);
    if (Buffer.byteLength(text) > 256_000) return false;
    const temporary = `${file}.${randomUUID()}.tmp`;
    try {
      fs.writeFileSync(temporary, text, {flag:"wx",mode:0o600});
      safeBacklogStorage(file, paths.agentDir);
      fs.renameSync(temporary, file);
    } finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
    return true;
  } catch { return false; }
}

/** Shared project lease for normal learning and replay; one attempt ledger writer. */
export function claimLearningLease(cwd: string, agentDir = getAgentDir()): (() => void) | undefined {
  const paths = resolveMemoryPaths(cwd, agentDir);
  const directory = path.join(paths.agentDir, "learning", paths.scopeKey);
  const lease = path.join(directory, "replay.lock");
  const token = randomUUID();
  try {
    withBacklogLock(cwd, agentDir, () => {
      safeBacklogStorage(lease, paths.agentDir, true);
      if (fs.existsSync(lease)) {
        const owner: unknown = JSON.parse(readBoundedBacklogFile(lease, 4096));
        if (!owner || typeof owner !== "object" || !("pid" in owner) || !Number.isSafeInteger(owner.pid) || Number(owner.pid) <= 0) throw new Error("Invalid replay lease");
        try { process.kill(Number(owner.pid), 0); throw new Error("Replay is busy"); }
        catch (error) { if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error; }
        fs.unlinkSync(lease);
      }
      fs.writeFileSync(lease, JSON.stringify({pid:process.pid, token}), {flag:"wx", mode:0o600});
    });
  } catch { return undefined; }
  return () => {
    // Acquisition refuses to replace a live owner. Release needs no backlog lock:
    // unrelated queue writers must not strand this process's live lease.
    safeBacklogStorage(lease, paths.agentDir);
    const owner = JSON.parse(readBoundedBacklogFile(lease, 4096));
    if (owner.token === token) fs.unlinkSync(lease);
  };

}

export async function replayLearningBacklog(input: {
  cwd: string; agentDir?: string; force?: boolean; limit?: number; signal?: AbortSignal;
  learn: (input: { entries: unknown[]; id: string; sessionFile: string; sessionId: string; sourceDigest: string; backlogCoverage?: LearningInputSource["backlogCoverage"]; omittedEntries?: number; omittedEvidenceEntries?: number }) => Promise<LearningPipelineReceipt | undefined>;
}): Promise<{ outcomes: Array<{ id: string; outcome: string }>; busy?: boolean; error?: string }> {
  const agentDir = input.agentDir ?? getAgentDir();
  const paths = resolveMemoryPaths(input.cwd, agentDir);
  const directory = path.join(paths.agentDir, "learning", paths.scopeKey);
  const release = claimLearningLease(input.cwd, agentDir);
  if (!release) return {outcomes:[], busy:true};
  const outcomes: Array<{id:string; outcome:string}> = [];
  try {
    const backlog = readBacklog(input.cwd, agentDir);
    if (backlog.error || backlog.malformed) return {outcomes, error:backlog.error ?? "Malformed backlog requires review"};
    const limit = Math.min(3, Math.max(1, Math.floor(input.limit ?? 1)));
    let executed = 0;
    const attempted = new Set<string>();
    // Restore every durable completion before choosing new work. Otherwise an
    // older deferred sibling could re-include a newer completed slice and replace
    // its original receipt proof after a crash.
    for (const {entry} of backlog.pendingEntries) {
      if (input.signal?.aborted) break;
      const id = backlogIdentity(paths.scopeKey, entry);
      if (attempted.has(id)) continue;
      const file = path.join(directory, `replay-${id}.json`);
      safeBacklogStorage(file, paths.agentDir, true);
      const last = readReplayState(file).attempts.at(-1);
      if (last?.outcome !== "completed" || !last.receipt || !learningReceiptComplete(last.receipt)) continue;
      if (!acknowledgeReplayCompletion(input.cwd, entry, last.receipt, backlog, agentDir)) throw new Error("Could not acknowledge replay");
      (last.receipt.input?.backlogCoverage ?? [{id}]).forEach(row => attempted.add(row.id));
      outcomes.push({id,outcome:"completed"});
    }
    for (const {entry: queuedEntry} of backlog.pendingEntries) {
      let entry = queuedEntry;
      if (executed >= limit) break;
      if (input.signal?.aborted) break;
      let id = backlogIdentity(paths.scopeKey, entry);
      if (attempted.has(id)) continue;
      let file = path.join(directory, `replay-${id}.json`);
      safeBacklogStorage(file, paths.agentDir, true);
      let state = readReplayState(file);
      if (state.attempts.length >= 16 || (!input.force && (state.attempts.length >= 3 || state.nextAttemptAt > Date.now()))) {
        outcomes.push({id,outcome:"deferred"}); continue;
      }
      const source = await recentProjectLearningInput({cwd:input.cwd, agentDir, sessionDir:path.dirname(entry.sessionFile),
        requestedSessionFile:entry.sessionFile, signal:input.signal});
      const slice = source?.contextEntries && entry.to < source.contextEntries.length
        ? currentTaskSlice(source.contextEntries.slice(entry.from, entry.to + 1)) : undefined;
      if (!source || !slice || sha256Digest(JSON.stringify(slice)) !== entry.digest) {
        outcomes.push({id,outcome:"source-changed"}); continue;
      }
      // A later verifier observation can extend this same task. Verify every
      // queued digest independently, then keep the longest byte-identical prefix
      // extension; never substitute a new task, changed source or session.
      const verified = backlog.pendingEntries.flatMap(({entry: other}) => {
        if (other.sessionFile !== entry.sessionFile || other.from !== entry.from || other.to < entry.to
          || other.to >= source.contextEntries!.length || other.scopeKey !== entry.scopeKey) return [];
        const otherId = backlogIdentity(paths.scopeKey, other);
        if (attempted.has(otherId)) return [];
        const otherFile = path.join(directory, `replay-${otherId}.json`);
        safeBacklogStorage(otherFile, paths.agentDir, true);
        const otherState = readReplayState(otherFile);
        if (otherState.attempts.length >= 16 || (!input.force && (otherState.attempts.length >= 3 || otherState.nextAttemptAt > Date.now()))) return [];
        const candidate = currentTaskSlice(source.contextEntries!.slice(other.from, other.to + 1));
        if (slice.omittedEntries || candidate.omittedEntries || sha256Digest(JSON.stringify(candidate)) !== other.digest || candidate.entries.length < slice.entries.length
          || JSON.stringify(candidate.entries.slice(0, slice.entries.length)) !== JSON.stringify(slice.entries)) return [];
        return [{entry: other, slice: candidate}];
      });
      const longest = verified.reduce((best, row) => row.slice.entries.length > best.slice.entries.length ? row : best, {entry, slice});
      const covering = verified.filter(row => row.slice.entries.length <= longest.slice.entries.length
        && JSON.stringify(longest.slice.entries.slice(0, row.slice.entries.length)) === JSON.stringify(row.slice.entries));
      const covered = covering.length <= 32 || covering.slice(0, 32).includes(longest) ? covering.slice(0, 32)
        : [...covering.slice(0, 31), longest];
      const backlogCoverage = covered.length > 1 ? covered.map(row => ({id:backlogIdentity(paths.scopeKey, row.entry),
        from:row.entry.from, to:row.entry.to, digest:row.entry.digest})) : undefined;
      const entries = backlogCoverage ? longest.slice.entries : slice.entries;
      // The receipt owner is the exact newest learned slice, so its identity and
      // dossier digest bind the actual feedback task, not merely its older prefix.
      if (backlogCoverage) {
        entry = longest.entry;
        id = backlogIdentity(paths.scopeKey, entry);
        file = path.join(directory, `replay-${id}.json`);
        state = readReplayState(file);
      }
      (backlogCoverage ?? [{id}]).forEach(row => attempted.add(row.id));
      executed++;
      const attempt: ReplayAttempt = {at:new Date().toISOString(), outcome:"running"};
      state.attempts.push(attempt);
      const save = async () => {
        safeBacklogStorage(file, paths.agentDir);
        const text = JSON.stringify(state);
        if (Buffer.byteLength(text) > 256_000) throw new Error("Replay evidence exceeds its byte budget");
        await writeFileAtomic(file, text, 0o600);
      };
      await save();
      try {
        const receipt = await input.learn({entries, id, sessionFile:entry.sessionFile, sessionId:source.sessionId, sourceDigest:source.sourceDigest, ...(backlogCoverage ? {backlogCoverage} : {}),
          ...(!backlogCoverage && slice.omittedEntries ? {omittedEntries:slice.omittedEntries, omittedEvidenceEntries:slice.omittedEvidenceEntries ?? slice.omittedEntries} : {})});
        if (receipt && isLearningPipelineReceipt(receipt)) attempt.receipt = receipt;
        const boundCoverage = !backlogCoverage || attempt.receipt?.input?.source === "backlog-session"
          && attempt.receipt.input.backlogId === id && attempt.receipt.input.sourceDigest === source.sourceDigest
          && attempt.receipt.input.entryCount === entries.length
          && JSON.stringify(attempt.receipt.input.backlogCoverage) === JSON.stringify(backlogCoverage);
        attempt.outcome = attempt.receipt && !input.signal?.aborted && boundCoverage && learningReceiptComplete(attempt.receipt) ? "completed" : "failed";
      } catch { attempt.outcome = "failed"; }
      state.nextAttemptAt = Date.now() + Math.min(24 * 60 * 60_000, 60_000 * 2 ** state.attempts.length);
      await save();
      outcomes.push({id,outcome:attempt.outcome});
      if (attempt.outcome !== "completed") continue;
      if (!acknowledgeReplayCompletion(input.cwd, entry, attempt.receipt!, backlog, agentDir)) throw new Error("Could not acknowledge replay");
    }
    return {outcomes};
  } catch { return {outcomes,error:"Learning replay could not complete safely"}; }
  finally { release(); }
}
