/** Research-only parent protocol. Not imported by the extension or packed.
 * Jev proof supplies indexes; trusted parent callbacks own permission,
 * validation, proposal persistence and the existing rollback-backed writer.
 */
import {createHash} from 'node:crypto';
import {simulateIndependentMemorySubset} from './independent-memory-subset-research';

type SubsetInput = Parameters<typeof simulateIndependentMemorySubset>[0];
interface OriginalPlan {
  newMemories: readonly unknown[];
  operations?: readonly unknown[];
  [key: string]: unknown;
}
interface Parent {
  applyChanges: boolean;
  persistOriginal(plan: OriginalPlan): Promise<string>;
  validateSubset(plan: OriginalPlan): Promise<void>;
  applySubset(plan: OriginalPlan): Promise<unknown>;
}
interface TransactionResult {
  purpose: 'research-only';
  outcome: 'proposed' | 'applied';
  proposalId: string;
  appliedIndexes: number[];
  heldIndexes: number[];
  applied?: unknown;
}
const digest = (value: unknown): string => createHash('sha256').update(JSON.stringify(value)).digest('hex');
function immutableCopy<T>(value: T): T {
  const copy: T = structuredClone(value);
  const freeze = (item: unknown): void => {
    if (!item || typeof item !== 'object') return;
    for (const nested of Object.values(item)) freeze(nested);
    Object.freeze(item);
  };
  freeze(copy);
  return copy;
}

export async function runSubsetParentTransactionResearch(
  original: OriginalPlan, input: SubsetInput, parent: Parent,
): Promise<TransactionResult> {
  if (!Array.isArray(original.newMemories) || (original.operations !== undefined
    && (!Array.isArray(original.operations) || original.operations.length))
    || digest(original.newMemories) !== digest(input.candidates)) {
    throw new Error('Subset parent plan does not match original new-Memory candidates');
  }
  const initial = digest({original, input});
  const assertFrozen = (): void => {
    if (digest({original, input}) !== initial) throw new Error('Subset parent frozen inputs changed');
  };
  const full = immutableCopy(original);
  const all = input.candidates.map((_, index) => index);
  const simulation = await simulateIndependentMemorySubset(input);
  assertFrozen();
  // Preserve all original intent even when permission/proof is absent. A
  // research diagnosis must never turn a held explicit request into silence.
  const proposalId = await parent.persistOriginal(full);
  assertFrozen();
  if (!proposalId) throw new Error('Subset parent proposal preservation not confirmed');
  const proposed = (): TransactionResult => ({purpose: 'research-only', outcome: 'proposed',
    proposalId, appliedIndexes: [], heldIndexes: all});
  if (!parent.applyChanges || simulation.reason !== 'independent-subset') return proposed();
  const subset = immutableCopy({...full,
    newMemories: simulation.recoverable.map(index => full.newMemories[index])});
  await parent.validateSubset(subset);
  assertFrozen();
  if (!parent.applyChanges) return proposed();
  // The parent writer must own its lock, original source hashes, cancellation
  // checks and rollback. No research result supplies write authorization.
  const applied = await parent.applySubset(subset);
  const result = applied && typeof applied === 'object' && !Array.isArray(applied)
    ? applied as Record<string, unknown> : undefined;
  const expectedNames = subset.newMemories.map(item => (item as {name: string}).name).sort();
  if (!result || !Array.isArray(result.created)
    || result.created.some(name => typeof name !== 'string')
    || digest([...result.created].sort()) !== digest(expectedNames)
    || (result.outcome !== undefined && result.outcome !== 'applied')) {
    throw new Error('Subset parent writer did not confirm the exact applied records');
  }
  return {purpose: 'research-only', outcome: 'applied', proposalId,
    appliedIndexes: simulation.recoverable, heldIndexes: simulation.held, applied};
}
