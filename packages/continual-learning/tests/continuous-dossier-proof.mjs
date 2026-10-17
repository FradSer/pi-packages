import {createHash} from 'node:crypto';

export const dossierDigest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');

const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const observations = entries => entries.flatMap(entry => {
  const message = entry?.message ?? entry;
  if (message?.role !== 'toolResult' || message.toolName !== 'read' || message.isError !== false) return [];
  try {
    const value = JSON.parse(message.content.map(part => part.text ?? '').join(''));
    return record(value) && value.kind === 'actual-project-verification' ? [value] : [];
  } catch { return []; }
});
const ids = entries => entries.flatMap(entry => typeof entry?.id === 'string' ? [entry.id] : []);

/** Parent computes proofs from the complete retained dossier, never from a
 * model-supplied digest or a set of matching IDs. Appended observations stay
 * in full review; only exact original complete prefixes can prove processing. */
export function summarizeDossier(task, ranges) {
  if (!record(task) || task.kind !== 'learning-task-slice' || task.version !== 1 || !Array.isArray(task.entries)) {
    throw new Error('Invalid parent dossier task slice');
  }
  const taskSliceDigest = dossierDigest(task);
  const originalPrefixProofs = [];
  if (!task.omittedEntries && !task.omittedEvidenceEntries) {
    for (const range of ranges) {
      if (!Number.isSafeInteger(range.from) || !Number.isSafeInteger(range.to) || range.from < 0 || range.to < range.from) continue;
      const entryCount = range.to - range.from + 1;
      if (entryCount > task.entries.length) continue;
      const entries = task.entries.slice(0, entryCount);
      const digest = dossierDigest({...task, entries});
      if (digest !== range.digest) continue;
      originalPrefixProofs.push({from: range.from, to: range.to, entryCount, digest, reviewDigest: taskSliceDigest,
        entryIds: ids(entries), observations: observations(entries)});
    }
  }
  return {taskSliceDigest, entryIds: ids(task.entries), observations: observations(task.entries), originalPrefixProofs};
}
