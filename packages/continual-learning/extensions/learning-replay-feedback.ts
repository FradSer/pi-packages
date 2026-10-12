/** Rejected proposals are correction context, never knowledge or permission. */
import path from "node:path";
import fs from "node:fs/promises";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { sha256Digest } from "./consolidation-run";
import { readBoundedBacklogFile, safeBacklogStorage } from "./learning-backlog";
import { readLearningHistory, type LearningHistory } from "./learning-history";
import { resolveMemoryPaths } from "./memory-paths";
import type { LearningPipelineReceipt } from "./learning-efficiency";

const MAX_REPLAY_FEEDBACK_BYTES = 128_000;
const MAX_REPLAY_HISTORY_BYTES = 32 * 1024 * 1024;

function record(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

export interface MemoryReplayFeedback {
  kind: "memory-replay-feedback";
  version: 1;
  priorReceiptDigest: string;
  priorPlanDigest: string;
  sourceSnapshotDigest: string;
  sourceEntryCount: number;
  diagnosticsStatus: "bound" | "unavailable";
  candidates: unknown[];
  eligibleIndexes: number[];
  heldIndexes: number[];
  failures: Array<{ candidateIndex: number; dimension: string; field?: "description"; reason: string }>;
}

function previousPlan(proposal: Record<string, unknown>): Record<string, unknown> | null {
  if (proposal.version !== 1) return null;
  if (proposal.kind === "memory-consolidation-plan") return proposal;
  return proposal.kind === "independent-memory-review" && record(proposal.originalPlan) ? proposal.originalPlan : null;
}

export function buildMemoryReplayFeedback(input: {
  receipt: LearningPipelineReceipt; backlogId: string; entries: readonly unknown[];
  proposal: unknown; snapshotText: string;
}): MemoryReplayFeedback | null {
  const { receipt, proposal } = input;
  if (receipt.input?.backlogId !== input.backlogId || !record(proposal)) return null;
  const plan = previousPlan(proposal);
  if (!plan) return null;
  if (!Array.isArray(plan.operations) || !Array.isArray(plan.newMemories) || typeof plan.snapshotDigest !== "string"
    || sha256Digest(input.snapshotText) !== plan.snapshotDigest) return null;
  let snapshot: unknown;
  try { snapshot = JSON.parse(input.snapshotText); } catch { return null; }
  if (!record(snapshot) || snapshot.runId !== plan.runId || snapshot.scopeKey !== plan.scopeKey
    || JSON.stringify(snapshot.entries) !== JSON.stringify(input.entries)) return null;
  const candidates = [...plan.operations, ...plan.newMemories];
  // An unpartitioned zero-write maintenance rejection holds the entire plan.
  // It conveys no independently eligible subset or permission to apply one.
  const eligibleIndexes = proposal.kind === "memory-consolidation-plan" ? [] : proposal.eligibleIndexes;
  const heldIndexes = proposal.kind === "memory-consolidation-plan" ? candidates.map((_, index) => index) : proposal.heldIndexes;
  const indexes = (value: unknown): value is number[] => Array.isArray(value)
    && value.every(index => Number.isSafeInteger(index) && index >= 0 && index < candidates.length)
    && new Set(value).size === value.length;
  if (!indexes(eligibleIndexes) || !indexes(heldIndexes)
    || !heldIndexes.length || new Set([...eligibleIndexes, ...heldIndexes]).size !== candidates.length
    || eligibleIndexes.length + heldIndexes.length !== candidates.length) return null;
  // A receipt may include a later repair with a different candidate ordering.
  // Legacy proposals have no proof tying those indexes to this retained plan.
  const bound = proposal.reviewedPlanDigest !== undefined;
  if (bound && (proposal.reviewedPlanDigest !== sha256Digest(JSON.stringify(plan))
    || !Array.isArray(proposal.candidateFailures))) return null;
  const candidateFailures = bound ? proposal.candidateFailures as unknown[] : [];
  const dimensions = ["support", "authority", "explanation", "scope", "relationship", "counterevidence"];
  const reasons = ["uncertain", "unsupported", "scope-expansion", "duplicate", "conflict"];
  const failures: MemoryReplayFeedback["failures"] = [];
  for (const failure of candidateFailures) {
    if (!record(failure) || !Number.isSafeInteger(failure.candidateIndex) || !heldIndexes.includes(failure.candidateIndex as number)
      || typeof failure.dimension !== "string" || typeof failure.reason !== "string"
      || !dimensions.includes(failure.dimension) || !reasons.includes(failure.reason)) return null;
    failures.push({ candidateIndex: failure.candidateIndex as number, dimension: failure.dimension,
      ...(failure.field === "description" ? { field: "description" as const } : {}), reason: failure.reason });
  }
  const feedback: MemoryReplayFeedback = { kind: "memory-replay-feedback", version: 1,
    priorReceiptDigest: sha256Digest(JSON.stringify(receipt)), priorPlanDigest: sha256Digest(JSON.stringify(plan)),
    sourceSnapshotDigest: plan.snapshotDigest, sourceEntryCount: input.entries.length,
    diagnosticsStatus: bound ? "bound" : "unavailable", candidates,
    eligibleIndexes, heldIndexes, failures };
  return Buffer.byteLength(JSON.stringify(feedback)) <= MAX_REPLAY_FEEDBACK_BYTES ? feedback : null;
}

/** Only the validated history batch and its immutable original snapshot qualify.
 * Legacy/no-proposal failures still replay normally; no diagnostic text is used. */
export async function readMemoryReplayFeedback(input: {
  cwd: string; agentDir: string; backlogId: string; entries: readonly unknown[]; receipt?: LearningPipelineReceipt;
}): Promise<MemoryReplayFeedback | null> {
  if (!input.receipt?.batchId || path.resolve(input.agentDir) !== path.resolve(getAgentDir())) return null;
  const paths = resolveMemoryPaths(input.cwd, input.agentDir);
  const directory = path.join(paths.agentDir, "memory", "history", paths.scopeKey);
  safeBacklogStorage(path.join(directory, "replay-history-probe"), paths.agentDir);
  let names: string[];
  try { names = await fs.readdir(directory); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return null; throw error; }
  if (names.length > 16_384) throw new Error("Replay history exceeds its entry budget");
  const matches: LearningHistory[] = [];
  let bytes = 0;
  // This is a batch lookup, not the UI's most-recent-50 presentation window.
  // Exceeding the complete scan budget stops replay rather than hiding records.
  for (const name of names.filter(name => /^change_[a-z0-9]+_[a-f0-9]{16}\.json$/.test(name))) {
    const item = await readLearningHistory(input.cwd, name.slice(0, -5));
    bytes += Buffer.byteLength(JSON.stringify(item));
    if (bytes > MAX_REPLAY_HISTORY_BYTES) throw new Error("Replay history exceeds its byte budget");
    if (item.batchId === input.receipt.batchId && item.phase === "memory" && item.status === "proposed"
      && record(item.proposal) && ["independent-memory-review", "memory-consolidation-plan"].includes(String(item.proposal.kind))) matches.push(item);
  }
  if (!matches.length) return null;
  if (matches.length !== 1) throw new Error("Ambiguous previous Memory failure history");
  const proposal = matches[0].proposal;
  const plan = record(proposal) ? previousPlan(proposal) : null;
  if (!plan) {
    throw new Error("Previous Memory failure has no bound independent proposal");
  }
  if (typeof plan.runId !== "string" || !/^run_[a-z0-9]+_[a-f0-9]{16}$/.test(plan.runId)
    || plan.scopeKey !== paths.scopeKey) throw new Error("Previous Memory failure has an invalid run binding");
  const file = path.join(paths.runsDir, plan.runId, "snapshot.json");
  safeBacklogStorage(file, paths.agentDir);
  const snapshotText = readBoundedBacklogFile(file, 1_048_576);
  const feedback = buildMemoryReplayFeedback({ receipt: input.receipt, backlogId: input.backlogId,
    entries: input.entries, proposal, snapshotText });
  if (!feedback) throw new Error("Previous Memory failure cannot be safely bound to replay evidence");
  return feedback;
}
