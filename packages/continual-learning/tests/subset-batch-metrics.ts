/** Metrics for fixed labels; not permission or a claim of learning superiority. */
interface Batch {eligible: readonly boolean[]; whole: readonly number[]; subset: readonly number[]}
export function subsetBatchMetrics(batches: readonly Batch[]) {
  const whole = {validAccepted: 0, erroneousAccepted: 0, validHeld: 0};
  const subset = {validAccepted: 0, erroneousAccepted: 0, validHeld: 0};
  let newErroneousAccepted = 0, newValidHolds = 0, recoveredValid = 0;
  for (const batch of batches) {
    for (const indexes of [batch.whole, batch.subset]) {
      if (new Set(indexes).size !== indexes.length || indexes.some(i => !Number.isSafeInteger(i) || i < 0 || i >= batch.eligible.length)) throw new Error('Invalid metric indexes');
    }
    for (const [index, valid] of batch.eligible.entries()) {
      const before = batch.whole.includes(index), after = batch.subset.includes(index);
      for (const [metrics, accepted] of [[whole, before], [subset, after]] as const) {
        if (accepted) metrics[valid ? 'validAccepted' : 'erroneousAccepted']++;
        else if (valid) metrics.validHeld++;
      }
      if (!valid && after && !before) newErroneousAccepted++;
      if (valid && before && !after) newValidHolds++;
      if (valid && !before && after) recoveredValid++;
    }
  }
  return {whole, subset, newErroneousAccepted, newValidHolds, recoveredValid};
}
