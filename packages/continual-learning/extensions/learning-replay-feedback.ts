/** Rejected proposals are correction context, never knowledge or permission. */
import path from "node:path";
import fs from "node:fs/promises";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { containsSensitiveMemoryMaterial, normalizeNewMemoryProposals, normalizeSnapshotEvidence, sha256Digest } from "./consolidation-run";
import {prepareMemoryCoverageJudgment, type MemoryCoverageContext, type MemoryCoverageQuestion} from "./memory-knowledge-coverage";
import { readBoundedBacklogFile, safeBacklogStorage } from "./learning-backlog";
import { readLearningHistory, type LearningHistory } from "./learning-history";
import { resolveMemoryPaths } from "./memory-paths";
import type { LearningAttempt, LearningPipelineReceipt } from "./learning-efficiency";

const MAX_REPLAY_FEEDBACK_BYTES = 128_000;
const MAX_REPLAY_HISTORY_BYTES = 32 * 1024 * 1024;

function record(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

type CoverageArtifact = NonNullable<LearningAttempt["coverageReviewArtifact"]>;
export interface RejectedCoverageQuestions {
  purpose: "rejected-questions-only";
  runId: string;
  sourceSnapshotDigest: string;
  reviewedPlanDigest: string;
  artifact: CoverageArtifact;
  rejectedPlan: MemoryCoverageContext["plan"];
  /** Complete rejected diagnostics, not source facts or required answers.
   * Optional only for feedback retained before these relationships were copied. */
  planAccount?: MemoryCoverageContext["review"]["plan"];
  recordAccounts?: MemoryCoverageContext["review"]["accounts"];
  priorRejectedPlan?: MemoryCoverageContext["plan"];
  priorTargets?: unknown[];
  /** Reuse the complete earlier plan, targets and accounts in this same version list. */
  priorAccountArtifact?: CoverageArtifact;
  priorPlanAccount?: MemoryCoverageContext["review"]["plan"];
  priorRecordAccounts?: MemoryCoverageContext["review"]["accounts"];
  questions: MemoryCoverageQuestion[];
  occurrences: unknown[];
  targets: unknown[];
  checks: unknown[];
}

function coverageArtifact(value: unknown): value is CoverageArtifact {
  return record(value) && Object.keys(value).length === 3
    && typeof value.file === "string" && /^memory-coverage-semantic-[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}\.json$/.test(value.file)
    && typeof value.sha256 === "string" && /^[a-f0-9]{64}$/.test(value.sha256)
    && typeof value.reviewedPlanDigest === "string" && /^[a-f0-9]{64}$/.test(value.reviewedPlanDigest);
}

/** Only receipt-authenticated parent bytes reach this shape check. The coverage
 * preparer below independently rechecks the source, plan, bodies and accounts. */
function parentCoverageContext(value: unknown, prior = false): value is MemoryCoverageContext {
  return record(value) && value.protocol === "memory-knowledge-coverage-v2"
    && (value.questionContractVersion === undefined || value.questionContractVersion === 2) && record(value.plan)
    && typeof value.expectedReviewDigest === "string" && record(value.review)
    && value.review.status === "reviewed" && Array.isArray(value.review.targets)
    && Array.isArray(value.review.accounts) && record(value.review.plan)
    && (value.prior === undefined || !prior && parentCoverageContext({protocol: value.protocol,
      ...(record(value.prior) ? value.prior : {})}, true));
}

function rejectedCoverageQuestions(input: {
  receipt: LearningPipelineReceipt; proposal: Record<string, unknown>; plan: Record<string, unknown>;
  snapshot: Record<string, unknown>; snapshotDigest: string;
  artifacts?: readonly {file: string; text: string}[];
}): RejectedCoverageQuestions[] | undefined {
  const refs = input.proposal.rejectedCoverageReviews;
  const receiptRefs = input.receipt.attempts.flatMap(attempt => attempt.coverageReviewArtifact ? [attempt.coverageReviewArtifact] : []);
  if (refs === undefined && !receiptRefs.length) return undefined;
  if (input.proposal.kind !== "independent-memory-review"
    || input.proposal.reviewedPlanDigest !== sha256Digest(JSON.stringify(input.plan))
    || !Array.isArray(refs) || !refs.length || refs.length > 4 || !refs.every(coverageArtifact)
    || JSON.stringify(refs) !== JSON.stringify(receiptRefs)
    || new Set(refs.map(ref => ref.file)).size !== refs.length
    || !input.artifacts || input.artifacts.length !== refs.length) throw new Error("Invalid rejected coverage references");
  const number = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
  const priorAccountArtifacts = new Map<string, CoverageArtifact>();
  return refs.map(ref => {
    const files = input.artifacts!.filter(item => item.file === ref.file);
    if (files.length !== 1 || sha256Digest(files[0].text) !== ref.sha256) throw new Error("Rejected coverage artifact changed");
    const value: unknown = JSON.parse(files[0].text);
    if (!record(value) || value.version !== 1 || value.runId !== input.plan.runId
      || value.snapshotDigest !== input.snapshotDigest || value.planDigest !== ref.reviewedPlanDigest
      || value.proofAvailable !== true || value.writeAuthorized !== false
      || !parentCoverageContext(value.coverageContext) || !Array.isArray(value.existingMemories)
      || !value.existingMemories.every((item): item is {name: string; content: string} => record(item)
        && typeof item.name === "string" && typeof item.content === "string")
      || !record(value.reviewed) || !record(value.reviewed.coverageReview)) throw new Error("Invalid rejected coverage artifact");
    const context = value.coverageContext, plan = context.plan;
    if (!record(plan) || !Array.isArray(plan.operations) || !Array.isArray(plan.selected)
      || !plan.selected.every((name): name is string => typeof name === "string")
      || ["runId", "scopeKey", "scopeDigest", "artifactHash", "snapshotDigest"].some(key => plan[key] !== input.plan[key])
      || JSON.stringify(plan.selected) !== JSON.stringify(input.plan.selected)
      || sha256Digest(JSON.stringify(plan)) !== ref.reviewedPlanDigest) throw new Error("Rejected coverage plan changed");
    const candidates = [...plan.operations, ...normalizeNewMemoryProposals(plan, input.snapshot, plan.selected)];
    const prepared = prepareMemoryCoverageJudgment(input.snapshot, candidates, value.existingMemories, context);
    for (const review of [context.review, ...(context.prior ? [context.prior.review] : [])]) {
      const facts = [...review.plan!.obligations, ...review.accounts.flatMap(account =>
        [account.scope, ...account.uncovered, ...account.claims.flatMap(claim => [claim, ...claim.conditions])])];
      for (const fact of facts) {
        if (typeof fact.statement !== "string" || !fact.statement.trim() || fact.statement.length > 2000
          || containsSensitiveMemoryMaterial(fact.statement) || !Array.isArray(fact.evidence)
          || fact.evidence.length > 8 || "basis" in fact && fact.basis === "requested"
            && fact.evidence.some(item => item.role !== "user")) {
          throw new Error("Invalid rejected coverage fact");
        }
        if (!fact.evidence.length && "basis" in fact && fact.basis === "predecessor") continue;
        if (JSON.stringify(normalizeSnapshotEvidence(fact.evidence, input.snapshot)) !== JSON.stringify(fact.evidence)) {
          throw new Error("Rejected coverage quote or role changed");
        }
      }
    }
    const proof = value.reviewed.coverageReview;
    const own = input.receipt.attempts.filter(attempt => attempt.coverageReviewArtifact?.file === ref.file);
    if (own.length !== 1 || own[0].phase !== "memory" || own[0].operations !== 0 || own[0].usageComplete !== true
      || own[0].usageLedgerId !== context.review.usageLedgerId
      || JSON.stringify(own[0].usage) !== JSON.stringify(context.review.usage)
      || value.expectedAccountDigest !== context.expectedReviewDigest
      || value.expectedContextDigest !== prepared.contextDigest || proof.contextDigest !== prepared.contextDigest
      || proof.protocol !== "memory-knowledge-coverage-v2" || proof.complete !== true
      || proof.evidenceDigest !== sha256Digest(JSON.stringify(input.snapshot))
      || proof.candidatesDigest !== sha256Digest(JSON.stringify(candidates))
      || proof.existingDigest !== sha256Digest(JSON.stringify(value.existingMemories))
      || JSON.stringify(value.coverageQuestions) !== JSON.stringify(prepared.questions)
      || !record(prepared.state) || !Array.isArray(prepared.state.namedIssueBindings)
      || JSON.stringify(value.coverageIssueBindings) !== JSON.stringify(prepared.state.namedIssueBindings)
      || !Array.isArray(proof.checks) || proof.checks.length !== prepared.questions.length) throw new Error("Rejected coverage receipt or question binding changed");
    const checks = proof.checks.map((check, index) => {
      const question = prepared.questions[index];
      const probabilities = record(check) && record(check.probabilities) ? check.probabilities : undefined;
      if (!record(check) || check.key !== question.key || check.candidateIndex !== question.candidateIndex
        || check.retainedIndex !== question.retainedIndex || typeof check.choice !== "string"
        || !Object.hasOwn(question.criteria, check.choice) || !number(check.probability) || !number(check.confidence)
        || !probabilities || Object.keys(probabilities).length !== Object.keys(question.criteria).length
        || Object.keys(question.criteria).some(label => !number(probabilities[label]))
        || probabilities[check.choice] !== check.probability) throw new Error("Invalid rejected coverage answer");
      return {...check};
    });
    const priorAccountArtifact = context.prior && priorAccountArtifacts.get(context.prior.expectedReviewDigest);
    const result: RejectedCoverageQuestions = {purpose: "rejected-questions-only", runId: String(input.plan.runId),
      sourceSnapshotDigest: input.snapshotDigest, reviewedPlanDigest: ref.reviewedPlanDigest, artifact: ref,
      questions: prepared.questions, occurrences: prepared.state.namedIssueBindings,
      rejectedPlan: context.plan, targets: context.review.targets,
      planAccount: context.review.plan, recordAccounts: context.review.accounts, checks,
      ...(context.prior ? priorAccountArtifact ? {priorAccountArtifact: {...priorAccountArtifact}}
        : {priorRejectedPlan: context.prior.plan, priorTargets: context.prior.review.targets,
          priorPlanAccount: context.prior.review.plan, priorRecordAccounts: context.prior.review.accounts} : {})};
    if (containsSensitiveMemoryMaterial(JSON.stringify(result))) throw new Error("Unsafe rejected coverage question");
    priorAccountArtifacts.set(context.expectedReviewDigest, {...ref});
    return result;
  });
}

export interface MemoryReplayFeedback {
  kind: "memory-replay-feedback";
  version: 1;
  priorReceiptDigest: string;
  priorPlanDigest: string;
  sourceSnapshotDigest: string;
  sourceEntryCount: number;
  reviewEntryCount?: number;
  diagnosticsStatus: "bound" | "unavailable";
  candidates: unknown[];
  eligibleIndexes: number[];
  heldIndexes: number[];
  failures: Array<{ candidateIndex: number; dimension: string; field?: "description"; reason: string }>;
  rejectedCoverageQuestions?: RejectedCoverageQuestions[];
}

function previousPlan(proposal: Record<string, unknown>): Record<string, unknown> | null {
  if (proposal.version !== 1) return null;
  if (proposal.kind === "memory-consolidation-plan") return proposal;
  return proposal.kind === "independent-memory-review" && record(proposal.originalPlan) ? proposal.originalPlan : null;
}

/** Historical parent source reads bind correction context only. Their bodies
 * never become fresh replay evidence or mutation authority. The complete
 * snapshot hash and original run manifest still authenticate the reviewed set. */
export function reviewedSourceExtension(snapshot: Record<string, unknown>, plan: Record<string, unknown>,
  entries: readonly unknown[], manifest: unknown, audit: unknown, receipt: LearningPipelineReceipt): boolean {
  if (!record(manifest) || manifest.schemaVersion !== 1 || manifest.contextEnabled !== true
    || manifest.runId !== plan.runId || manifest.scopeKey !== plan.scopeKey || manifest.scopeDigest !== plan.scopeDigest
    || manifest.snapshotDigest !== plan.snapshotDigest || plan.artifactHash !== manifest.snapshotDigest
    || typeof manifest.cwd !== "string" || !path.isAbsolute(manifest.cwd)
    || snapshot.contextEnabled !== true || !Array.isArray(snapshot.entries)
    || JSON.stringify(snapshot.entries.slice(0, entries.length)) !== JSON.stringify(entries)) return false;
  const extension = snapshot.entries.slice(entries.length);
  if (!extension.length || extension.length > 36 || extension.length % 2) return false;
  if (!record(audit) || !record(audit.receipt) || !Array.isArray(audit.observations)
    || audit.observations.length > 18) return false;
  const sourceReceipt = audit.receipt;
  if (sourceReceipt.version !== 1 || sourceReceipt.outcome !== "observed"
    || !["verified-observations", "verified-prefix"].includes(String(sourceReceipt.sourceEvidenceStatus))
    || sourceReceipt.mutationAuthorized !== false || sourceReceipt.remoteSourceCalls !== 0
    || sourceReceipt.observedSourceEntries !== extension.length || !record(sourceReceipt.sourceHashes)
    || typeof sourceReceipt.usageLedgerId !== "string"
    || receipt.attempts.filter(attempt => attempt.phase === "memory" && attempt.attempt === 0
      && attempt.operations === 0 && attempt.usageLedgerId === sourceReceipt.usageLedgerId).length !== 1) return false;
  const reads: Array<{observation: Record<string, unknown>; ordinal: number}> = [];
  for (const [ordinal, observation] of audit.observations.entries()) {
    if (!record(observation)) return false;
    if (observation.error === "Scoped source path missing") continue;
    if (observation.error || typeof observation.path !== "string" || typeof observation.result !== "string"
      || typeof observation.sha256 !== "string" || sourceReceipt.sourceHashes[observation.path] !== observation.sha256) return false;
    reads.push({observation, ordinal});
  }
  if (reads.length * 2 !== extension.length
    || new Set(reads.map(read => read.observation.path)).size !== Object.keys(sourceReceipt.sourceHashes).length) return false;
  const message = (entry: unknown): Record<string, unknown> | undefined =>
    record(entry) && record(entry.message) ? entry.message : undefined;
  const ids = new Set<string>();
  for (const entry of entries) {
    const row = message(entry) ?? (record(entry) ? entry : undefined);
    if (Array.isArray(row?.content)) for (const part of row.content) {
      if (record(part) && part.type === "toolCall" && typeof part.id === "string") ids.add(part.id);
    }
    if (typeof row?.toolCallId === "string") ids.add(row.toolCallId);
  }
  let sourceIdPrefix: string | undefined;
  for (let index = 0; index < extension.length; index += 2) {
    const callRow = message(extension[index]), result = message(extension[index + 1]);
    if (callRow?.role !== "assistant" || !Array.isArray(callRow.content) || callRow.content.length !== 1) return false;
    const call = callRow.content[0];
    if (!record(call) || call.type !== "toolCall" || call.name !== "learning_read" || typeof call.id !== "string"
      || !/^maintenance-source-(?:[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}-)?[0-9]+$/.test(call.id)
      || ids.has(call.id) || !record(call.arguments) || typeof call.arguments.path !== "string"
      || !path.isAbsolute(call.arguments.path) || !Number.isSafeInteger(call.arguments.offset)
      || Number(call.arguments.offset) < 1 || !Number.isSafeInteger(call.arguments.limit)
      || Number(call.arguments.limit) < 1 || Number(call.arguments.limit) > 2000) return false;
    const {observation: read, ordinal} = reads[index / 2];
    const prefix = call.id.slice(0, call.id.lastIndexOf("-") + 1);
    if (call.id !== `${prefix}${ordinal}` || sourceIdPrefix !== undefined && prefix !== sourceIdPrefix) return false;
    sourceIdPrefix = prefix;
    if (call.arguments.path !== read.path || call.arguments.offset !== read.offset
      || call.arguments.limit !== read.limit) return false;
    ids.add(call.id);
    const relative = path.relative(manifest.cwd, call.arguments.path);
    if (!relative || path.isAbsolute(relative) || relative.split(/[\\/]/).some(part =>
      part === ".." || [".memory", ".pi", ".git", "node_modules"].includes(part.toLowerCase()))) return false;
    if (result?.role !== "toolResult" || result.toolName !== "learning_read" || result.toolCallId !== call.id
      || result.isError !== false || !record(result.details) || result.details.readOnlyMaintenanceAudit !== true
      || result.details.sourcePath !== call.arguments.path || typeof result.details.sourceSha256 !== "string"
      || !/^[a-f0-9]{64}$/.test(result.details.sourceSha256) || !Array.isArray(result.content)
      || result.content.length !== 1 || !record(result.content[0]) || result.content[0].type !== "text"
      || typeof result.content[0].text !== "string" || !result.content[0].text
      || result.content[0].text !== read.result || result.details.sourceSha256 !== read.sha256) return false;
  }
  return true;
}

export function buildMemoryReplayFeedback(input: {
  receipt: LearningPipelineReceipt; backlogId: string; entries: readonly unknown[];
  proposal: unknown; snapshotText: string; reviewManifest?: unknown; sourceAudit?: unknown;
  rejectedCoverageArtifacts?: readonly {file: string; text: string}[];
}): MemoryReplayFeedback | null {
  const { receipt, proposal } = input;
  if (receipt.input?.backlogId !== input.backlogId || !record(proposal)) return null;
  const plan = previousPlan(proposal);
  if (!plan) return null;
  if (!Array.isArray(plan.operations) || !Array.isArray(plan.newMemories) || typeof plan.snapshotDigest !== "string"
    || sha256Digest(input.snapshotText) !== plan.snapshotDigest) return null;
  let snapshot: unknown;
  try { snapshot = JSON.parse(input.snapshotText); } catch { return null; }
  if (!record(snapshot) || snapshot.runId !== plan.runId || snapshot.scopeKey !== plan.scopeKey) return null;
  const extended = JSON.stringify(snapshot.entries) !== JSON.stringify(input.entries);
  if (extended && !reviewedSourceExtension(snapshot, plan, input.entries, input.reviewManifest, input.sourceAudit, receipt)) return null;
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
  const dimensions = ["support", "authority", "explanation", "scope", "relationship", "counterevidence", "preservation"];
  const reasons = ["uncertain", "unsupported", "scope-expansion", "duplicate", "conflict"];
  const failures: MemoryReplayFeedback["failures"] = [];
  for (const failure of candidateFailures) {
    if (!record(failure) || !Number.isSafeInteger(failure.candidateIndex) || !heldIndexes.includes(failure.candidateIndex as number)
      || typeof failure.dimension !== "string" || typeof failure.reason !== "string"
      || !dimensions.includes(failure.dimension) || !reasons.includes(failure.reason)) return null;
    failures.push({ candidateIndex: failure.candidateIndex as number, dimension: failure.dimension,
      ...(failure.field === "description" ? { field: "description" as const } : {}), reason: failure.reason });
  }
  let coverageQuestions: RejectedCoverageQuestions[] | undefined;
  try { coverageQuestions = rejectedCoverageQuestions({receipt, proposal, plan, snapshot,
    snapshotDigest: plan.snapshotDigest, artifacts: input.rejectedCoverageArtifacts}); }
  catch { return null; }
  const feedback: MemoryReplayFeedback = { kind: "memory-replay-feedback", version: 1,
    priorReceiptDigest: sha256Digest(JSON.stringify(receipt)), priorPlanDigest: sha256Digest(JSON.stringify(plan)),
    sourceSnapshotDigest: plan.snapshotDigest, sourceEntryCount: input.entries.length,
    ...(extended ? {reviewEntryCount: (snapshot.entries as unknown[]).length} : {}),
    diagnosticsStatus: bound ? "bound" : "unavailable", candidates,
    eligibleIndexes, heldIndexes, failures, ...(coverageQuestions ? {rejectedCoverageQuestions: coverageQuestions} : {}) };
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
  let reviewManifest: unknown;
  let sourceAudit: unknown;
  const snapshot: unknown = JSON.parse(snapshotText);
  if (record(snapshot) && JSON.stringify(snapshot.entries) !== JSON.stringify(input.entries)) {
    const manifestFile = path.join(paths.runsDir, plan.runId, "manifest.json");
    safeBacklogStorage(manifestFile, paths.agentDir);
    reviewManifest = JSON.parse(readBoundedBacklogFile(manifestFile, 1_048_576));
    if (!record(reviewManifest) || reviewManifest.cwd !== paths.cwd || reviewManifest.snapshotPath !== file
      || reviewManifest.runDir !== path.dirname(file) || reviewManifest.harnessDir !== paths.harnessDir) {
      throw new Error("Previous Memory source extension has an invalid parent run binding");
    }
    const ledgers = new Set(input.receipt.attempts.filter(attempt => attempt.phase === "memory"
      && attempt.attempt === 0 && attempt.operations === 0 && attempt.usageLedgerId).map(attempt => attempt.usageLedgerId));
    const auditNames = (await fs.readdir(paths.runsDir)).filter(name => /^maintenance-audit-[A-Za-z0-9]+$/.test(name));
    if (auditNames.length > 16_384) throw new Error("Replay source audit exceeds its entry budget");
    let auditBytes = 0;
    for (const name of auditNames) {
      const auditReceiptFile = path.join(paths.runsDir, name, "receipt.json");
      safeBacklogStorage(auditReceiptFile, paths.agentDir);
      let auditReceipt: unknown;
      try {
        const text = readBoundedBacklogFile(auditReceiptFile, 1_048_576);
        auditBytes += Buffer.byteLength(text);
        if (auditBytes > MAX_REPLAY_HISTORY_BYTES) throw new Error("Replay source audit exceeds its byte budget");
        auditReceipt = JSON.parse(text);
      }
      catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") continue; throw error; }
      if (!record(auditReceipt) || typeof auditReceipt.usageLedgerId !== "string" || !ledgers.has(auditReceipt.usageLedgerId)) continue;
      if (sourceAudit) throw new Error("Ambiguous previous Memory source audit");
      const observationsFile = path.join(paths.runsDir, name, "observations.jsonl");
      safeBacklogStorage(observationsFile, paths.agentDir);
      const observations = readBoundedBacklogFile(observationsFile, 512_000).split("\n").filter(Boolean).map(line => JSON.parse(line));
      sourceAudit = {receipt: auditReceipt, observations};
    }
  }
  let rejectedCoverageArtifacts: {file: string; text: string}[] | undefined;
  if (record(proposal) && proposal.rejectedCoverageReviews !== undefined) {
    const refs = proposal.rejectedCoverageReviews;
    if (!Array.isArray(refs) || !refs.length || refs.length > 4 || !refs.every(coverageArtifact)
      || new Set(refs.map(ref => ref.file)).size !== refs.length) throw new Error("Invalid rejected coverage file binding");
    rejectedCoverageArtifacts = [];
    let artifactBytes = 0;
    for (const ref of refs) {
      const artifactFile = path.join(paths.runsDir, plan.runId, ref.file);
      safeBacklogStorage(artifactFile, paths.agentDir);
      const text = readBoundedBacklogFile(artifactFile, MAX_REPLAY_HISTORY_BYTES);
      artifactBytes += Buffer.byteLength(text);
      if (artifactBytes > MAX_REPLAY_HISTORY_BYTES) throw new Error("Rejected coverage artifacts exceed their byte budget");
      rejectedCoverageArtifacts.push({file: ref.file, text});
    }
  }
  const feedback = buildMemoryReplayFeedback({ receipt: input.receipt, backlogId: input.backlogId,
    entries: input.entries, proposal, snapshotText, ...(reviewManifest ? {reviewManifest, sourceAudit} : {}),
    ...(rejectedCoverageArtifacts ? {rejectedCoverageArtifacts} : {}) });
  if (!feedback) throw new Error("Previous Memory failure cannot be safely bound to replay evidence");
  return feedback;
}
