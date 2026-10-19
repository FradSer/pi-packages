import {independentMemoryRoles} from "./jev-memory-predecessors";
import {interpretStandaloneMemory} from "./jev-memory-readiness";
import {createHash} from "node:crypto";
import {jevModelMatchesRequest, reviewedMemoryEvidence, independentMemoryChecks, type JevCandidateReview, type JevMemoryRelationsReview} from "./jev-learning";
import {interpretMemoryPair} from "./jev-memory-relations";
import type {SelectedMemory} from "./incremental-learning";

/** Index selection only. Parent permission, persistence, validation and writes
 * remain mandatory; a diagnostic review is never a write capability. The pair
 * gate is strict: any non-independent pair holds both members. Only the composed
 * proof of self-containment can recover a proven candidate afterwards. */
export function partitionReviewedNewMemory(
  evidence: unknown, candidates: readonly unknown[], existing: readonly SelectedMemory[],
  review: JevCandidateReview | undefined, relations: JevMemoryRelationsReview | undefined,
  readiness?: unknown, requestedModel = "jev-1.13.0", options?: {allowFrozenNoopComparators?: boolean},
): {eligible: number[]; held: number[]; writeAuthorized: false} {
  const all = candidates.map((_, index) => index);
  const denied = () => ({eligible: [], held: all, writeAuthorized: false as const});
  const digest = (value: unknown) => createHash("sha256").update(JSON.stringify(value)).digest("hex");
  const roles = independentMemoryRoles(candidates, existing, options?.allowFrozenNoopComparators === true);
  if (!roles) return denied();
  const mixed = roles.includes("frozen-noop");
  const prepared = reviewedMemoryEvidence(evidence, candidates, review, mixed ? existing : undefined);
  if (!prepared || typeof prepared === "string" || !review || !relations
    || review.version !== 1 || relations.version !== 1 || review.purpose !== "diagnostic-only" || relations.purpose !== "diagnostic-only"
    || review.complete !== true || relations.complete !== true || review.sameBatchIndependenceReviewed !== false
    || !jevModelMatchesRequest(requestedModel, review.model) || relations.model !== review.model
    || !Array.isArray(review.candidates) || review.candidates.length !== candidates.length
    || !Array.isArray(relations.pairs) || relations.pairs.length !== candidates.length * (candidates.length - 1) / 2) return denied();
  for (const proof of [review, relations]) {
    if (proof.evidenceDigest !== digest(evidence) || proof.existingDigest !== digest(existing)
      || proof.candidatesDigest !== digest(candidates)) return denied();
  }
  const eligible = new Set<number>();
  for (const [index, candidate] of candidates.entries()) {
    const observation = review.candidates[index];
    const expected = independentMemoryChecks(candidate, index, existing, prepared.windows);
    if (!observation || !Array.isArray(observation.passedChecks) || !Array.isArray(observation.heldChecks)) return denied();
    const checks = [...observation.passedChecks, ...observation.heldChecks];
    if (observation.index !== index || observation.candidateDigest !== digest(candidate)
      || checks.length !== expected.length || new Set(checks).size !== checks.length
      || checks.some(key => !expected.includes(key))
      || observation.outcome !== (observation.heldChecks.length ? "held" : "passed")) return denied();
    if (observation.outcome === "passed" && roles[index] === "new") eligible.add(index);
  }
  const supported = new Set(eligible);
  const seen = new Set<string>();
  const persistedPairHolds = new Set<number>();
  for (const pair of relations.pairs) {
    if (!pair || !Number.isSafeInteger(pair.a) || !Number.isSafeInteger(pair.b) || pair.a < 0 || pair.a >= pair.b || pair.b >= candidates.length
      || !Array.isArray(pair.candidateDigests) || pair.candidateDigests.length !== 2
      || pair.candidateDigests[0] !== digest(candidates[pair.a]) || pair.candidateDigests[1] !== digest(candidates[pair.b])) return denied();
    const key = `${pair.a}:${pair.b}`;
    if (seen.has(key)) return denied();
    seen.add(key);
    const observed = interpretMemoryPair(pair.answer);
    if (observed.status === "invalid-response" || pair.status !== observed.status || pair.relation !== observed.relation) return denied();
    if (!observed.independenceObserved) {
      eligible.delete(pair.a); eligible.delete(pair.b);
      if (roles[pair.a] === "frozen-noop") persistedPairHolds.add(pair.b);
      if (roles[pair.b] === "frozen-noop") persistedPairHolds.add(pair.a);
    }
  }
  const result = (selected: Set<number>) => ({eligible: all.filter(index => selected.has(index)),
    held: all.filter(index => !selected.has(index)), writeAuthorized: false as const});
  // Additional observations are optional. Invalid or unavailable observations
  // preserve the original selection, never erase a previous successful review.
  const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
  if (!record(readiness) || readiness.version !== 1 || readiness.purpose !== "diagnostic-only"
    || readiness.complete !== true || readiness.model !== review.model
    || readiness.evidenceDigest !== review.evidenceDigest || readiness.existingDigest !== review.existingDigest
    || readiness.candidatesDigest !== review.candidatesDigest || !Array.isArray(readiness.candidates)
    || readiness.candidates.length !== candidates.length) return mixed ? denied() : result(eligible);
  const tentative = new Set(mixed ? [] : eligible);
  for (const [index, candidate] of candidates.entries()) {
    const observation: unknown = readiness.candidates[index];
    if (!record(observation) || observation.index !== index || observation.candidateDigest !== digest(candidate)) return mixed ? denied() : result(eligible);
    const interpreted = interpretStandaloneMemory(observation.answer);
    if (interpreted.status === "invalid-response") return mixed ? denied() : result(eligible);
    if (supported.has(index) && !persistedPairHolds.has(index) && interpreted.standaloneObserved) tentative.add(index);
  }
  const composed = new Set(tentative);
  // Use the initial tentative set for every obligation: removing one member
  // must not make a later conflicting or dependent pair disappear.
  for (const pair of relations.pairs) {
    if (tentative.has(pair.a) && tentative.has(pair.b) && !interpretMemoryPair(pair.answer).independenceObserved) {
      composed.delete(pair.a); composed.delete(pair.b);
    }
  }
  return result(composed);
}
