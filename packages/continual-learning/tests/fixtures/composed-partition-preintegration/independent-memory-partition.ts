import {createHash} from "node:crypto";
import {citedMemoryEvidence, type JevCandidateReview, type JevMemoryRelationsReview} from "./jev-learning";
import {interpretMemoryPair} from "./jev-memory-relations";
import type {SelectedMemory} from "./incremental-learning";

/** Index selection only. Parent permission, persistence, validation and writes
 * remain mandatory; a diagnostic review is never a write capability. */
export function partitionReviewedNewMemory(
  evidence: unknown, candidates: readonly unknown[], existing: readonly SelectedMemory[],
  review: JevCandidateReview | undefined, relations: JevMemoryRelationsReview | undefined,
): {eligible: number[]; held: number[]; writeAuthorized: false} {
  const all = candidates.map((_, index) => index);
  const denied = () => ({eligible: [], held: all, writeAuthorized: false as const});
  const digest = (value: unknown) => createHash("sha256").update(JSON.stringify(value)).digest("hex");
  const prepared = citedMemoryEvidence(evidence, candidates);
  if (!prepared || typeof prepared === "string" || !review || !relations
    || review.version !== 1 || relations.version !== 1 || review.purpose !== "diagnostic-only" || relations.purpose !== "diagnostic-only"
    || review.complete !== true || relations.complete !== true || review.sameBatchIndependenceReviewed !== false
    || review.model !== "jev-1.13.0" || relations.model !== review.model
    || !Array.isArray(review.candidates) || review.candidates.length !== candidates.length
    || !Array.isArray(relations.pairs) || relations.pairs.length !== candidates.length * (candidates.length - 1) / 2) return denied();
  for (const proof of [review, relations]) {
    if (proof.evidenceDigest !== digest(evidence) || proof.existingDigest !== digest(existing)
      || proof.candidatesDigest !== digest(candidates)) return denied();
  }
  const eligible = new Set<number>();
  for (const [index, candidate] of candidates.entries()) {
    const observation = review.candidates[index];
    const expected = [`supported_${index}`, `supported_description_${index}`,
      ...(existing.length ? [`relation_${index}`, `relation_description_${index}`] : []),
      ...prepared.windows.flatMap((_, window) => [`counter_${index}_${window}`, `counter_description_${index}_${window}`])];
    if (!observation || !Array.isArray(observation.passedChecks) || !Array.isArray(observation.heldChecks)) return denied();
    const checks = [...observation.passedChecks, ...observation.heldChecks];
    if (observation.index !== index || observation.candidateDigest !== digest(candidate)
      || checks.length !== expected.length || new Set(checks).size !== checks.length
      || checks.some(key => !expected.includes(key))
      || observation.outcome !== (observation.heldChecks.length ? "held" : "passed")) return denied();
    if (observation.outcome === "passed") eligible.add(index);
  }
  const seen = new Set<string>();
  for (const pair of relations.pairs) {
    if (!pair || !Number.isSafeInteger(pair.a) || !Number.isSafeInteger(pair.b) || pair.a < 0 || pair.a >= pair.b || pair.b >= candidates.length
      || !Array.isArray(pair.candidateDigests) || pair.candidateDigests.length !== 2
      || pair.candidateDigests[0] !== digest(candidates[pair.a]) || pair.candidateDigests[1] !== digest(candidates[pair.b])) return denied();
    const key = `${pair.a}:${pair.b}`;
    if (seen.has(key)) return denied();
    seen.add(key);
    const observed = interpretMemoryPair(pair.answer);
    if (observed.status === "invalid-response" || pair.status !== observed.status || pair.relation !== observed.relation) return denied();
    if (!observed.independenceObserved) { eligible.delete(pair.a); eligible.delete(pair.b); }
  }
  return {eligible: all.filter(index => eligible.has(index)), held: all.filter(index => !eligible.has(index)), writeAuthorized: false};
}
