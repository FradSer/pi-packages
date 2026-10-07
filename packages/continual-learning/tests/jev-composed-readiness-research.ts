/** Read-only research composition. Never returns a plan or write permission. */
import {createHash} from 'node:crypto';
import {simulateIndependentMemorySubset} from './independent-memory-subset-research';
import {interpretMemoryPair} from '../extensions/jev-memory-relations';
import {interpretStandaloneMemory} from './jev-standalone-memory-research';

type OriginalInput = Parameters<typeof simulateIndependentMemorySubset>[0];
const digest = (value: unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);

export async function simulateComposedMemoryReadiness(input: OriginalInput, standalone: unknown) {
  const initialDigest = digest(input);
  // Reuse every existing original checklist, citation/privacy/window and pair
  // binding check with locally disabled transport. It is not an inference call.
  const original = await simulateIndependentMemorySubset(input);
  if (original.reason === 'invalid-proof') return original;
  const fallback = () => ({...original, reason: 'fallback-original' as const});
  if (!record(standalone) || standalone.version !== 1 || standalone.purpose !== 'diagnostic-only'
    || standalone.complete !== true || standalone.model !== input.review?.model
    || standalone.evidenceDigest !== digest(input.evidence) || standalone.existingDigest !== digest(input.existing)
    || standalone.candidatesDigest !== digest(input.candidates) || !Array.isArray(standalone.candidates)
    || standalone.candidates.length !== input.candidates.length) return fallback();
  const ready = new Set(original.recoverable);
  for (const [index, candidate] of input.candidates.entries()) {
    const observation: unknown = standalone.candidates[index];
    if (!record(observation) || observation.index !== index || observation.candidateDigest !== digest(candidate)) return fallback();
    const result = interpretStandaloneMemory(observation.answer);
    if (result.status === 'invalid-response') return fallback();
    if (result.standaloneObserved && input.review!.candidates[index].outcome === 'passed') ready.add(index);
  }
  // Do not let deletion order change the tentative selected-pair obligation.
  // Every pair within the initial recoverable set must independently pass.
  const tentative = new Set(ready);
  for (const pair of input.pairs) {
    if (tentative.has(pair.a) && tentative.has(pair.b) && !interpretMemoryPair(pair.answer).independenceObserved) {
      ready.delete(pair.a);
      ready.delete(pair.b);
    }
  }
  if (digest(input) !== initialDigest) return {...original, recoverable: [], held: input.candidates.map((_, index) => index), reason: 'invalid-proof' as const};
  const recoverable = input.candidates.map((_, index) => index).filter(index => ready.has(index));
  return {purpose: 'research-only' as const, writeAuthorized: false as const, recoverable,
    held: input.candidates.map((_, index) => index).filter(index => !ready.has(index)),
    reason: recoverable.length ? 'composed-readiness' as const : 'no-composed-readiness' as const};
}
