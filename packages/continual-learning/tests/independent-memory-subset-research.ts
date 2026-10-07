/** Research simulation only. Never returns a plan, permission or write operation. */
import {createHash} from 'node:crypto';
import {normalizeNewMemoryProposals} from '../extensions/consolidation-run';
import type {SelectedMemory} from '../extensions/incremental-learning';
import {createJevJudge, type JevCandidateReview} from '../extensions/jev-learning';
import {interpretMemoryPair} from './jev-memory-pair-judgment';

interface PairObservation {
  a: number;
  b: number;
  model: string;
  evidenceDigest: string;
  existingDigest: string;
  candidatesDigest: string;
  candidateDigests: readonly string[];
  answer: unknown;
}
interface SubsetInput {
  evidence: unknown;
  candidates: readonly unknown[];
  existing: readonly SelectedMemory[];
  operations: readonly unknown[];
  review?: JevCandidateReview;
  pairs: readonly PairObservation[];
  windows: number;
  allowPrivateMemory?: boolean;
}
interface SubsetSimulation {
  purpose: 'research-only';
  writeAuthorized: false;
  recoverable: number[];
  held: number[];
  reason: 'invalid-proof' | 'independent-subset' | 'no-independent-subset';
}
const digest = (value: unknown): string => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);

export async function simulateIndependentMemorySubset(input: SubsetInput): Promise<SubsetSimulation> {
  const initialDigest = digest(input);
  const indexes = input.candidates.map((_, index) => index);
  const denied = (): SubsetSimulation => ({purpose: 'research-only', writeAuthorized: false, recoverable: [], held: indexes, reason: 'invalid-proof'});
  const {review, candidates, existing, pairs, windows} = input;
  if (!review || review.version !== 1 || review.purpose !== 'diagnostic-only' || review.complete !== true
    || review.sameBatchIndependenceReviewed !== false || review.model !== 'jev-1.13.0'
    || !Number.isSafeInteger(windows) || windows < 1 || windows > 8 || input.operations.length
    || !Array.isArray(review.candidates)
    || !record(input.evidence) || input.evidence.contextEnabled !== true || !Array.isArray(input.evidence.entries)
    || candidates.some(candidate => !record(candidate) || candidate.op !== undefined
      || !['project', 'preference'].includes(String(candidate.kind)))) return denied();
  try {
    const normalized = normalizeNewMemoryProposals({newMemories: candidates}, input.evidence, existing.map(item => item.name));
    if (normalized.some((candidate, index) => candidate.classification !== (candidates[index] as Record<string, unknown>).classification)) return denied();
  } catch { return denied(); }
  if (digest(input.evidence) !== review.evidenceDigest || digest(existing) !== review.existingDigest
    || digest(candidates) !== review.candidatesDigest || review.candidates.length !== candidates.length) return denied();

  const eligible = new Set<number>();
  for (const [index, candidate] of candidates.entries()) {
    const observation = review.candidates[index];
    const expected = [`supported_${index}`, `supported_description_${index}`,
      ...(existing.length ? [`relation_${index}`, `relation_description_${index}`] : []),
      ...Array.from({length: windows}, (_, window) => [`counter_${index}_${window}`, `counter_description_${index}_${window}`]).flat()];
    if (!record(observation) || !Array.isArray(observation.passedChecks) || !Array.isArray(observation.heldChecks)) return denied();
    const checks = [...observation.passedChecks, ...observation.heldChecks];
    if (observation.index !== index || observation.candidateDigest !== digest(candidate)
      || checks.length !== expected.length || new Set(checks).size !== checks.length
      || checks.some(check => !expected.includes(check))
      || observation.outcome !== (observation.heldChecks.length ? 'held' : 'passed')) return denied();
    if (observation.outcome === 'passed') eligible.add(index);
  }

  // Every unordered original pair must be present exactly once, even when a
  // candidate was already held. A held record can qualify or contradict another.
  if (pairs.length !== candidates.length * (candidates.length - 1) / 2) return denied();
  const seen = new Set<string>();
  for (const pair of pairs) {
    if (!record(pair) || !Array.isArray(pair.candidateDigests) || !Number.isSafeInteger(pair.a) || !Number.isSafeInteger(pair.b) || pair.a < 0
      || pair.a >= pair.b || pair.b >= candidates.length || pair.model !== review.model
      || pair.evidenceDigest !== review.evidenceDigest || pair.existingDigest !== review.existingDigest
      || pair.candidatesDigest !== review.candidatesDigest || pair.candidateDigests.length !== 2
      || pair.candidateDigests[0] !== digest(candidates[pair.a]) || pair.candidateDigests[1] !== digest(candidates[pair.b])) return denied();
    const identity = `${pair.a}:${pair.b}`;
    if (seen.has(identity)) return denied();
    seen.add(identity);
    const relation = interpretMemoryPair(pair.answer);
    if (relation.status === 'invalid-response') return denied();
    if (!relation.independenceObserved) {
      eligible.delete(pair.a);
      eligible.delete(pair.b);
    }
  }
  // Reuse production's full privacy/bounds and window construction with an
  // intentionally failing local transport. Reaching it is preflight evidence,
  // never inference or semantic support; it cannot forward external requests.
  let localRequests = 0;
  const preflight = createJevJudge({enabled: true, apiKey: 'fixture-only', defaultModel: 'jev-1.13.0',
    scopes: ['memory'], allowPrivateMemory: input.allowPrivateMemory === true,
    fetch: async () => { localRequests++; throw new Error('Offline subset preflight'); }});
  const eligibility = await preflight.validate('memory', input.evidence, candidates, existing);
  if (!localRequests || eligibility.telemetry.evidenceWindows !== windows
    || eligibility.telemetry.evidenceEntries !== input.evidence.entries.length
    || digest(input) !== initialDigest) return denied();
  const recoverable = indexes.filter(index => eligible.has(index));
  return {purpose: 'research-only', writeAuthorized: false, recoverable,
    held: indexes.filter(index => !eligible.has(index)), reason: recoverable.length ? 'independent-subset' : 'no-independent-subset'};
}
