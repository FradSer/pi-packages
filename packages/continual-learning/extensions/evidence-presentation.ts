/** Model-facing labels only. Validation and digests use the untouched snapshot. */
export function indexedMemoryEvidence(value: unknown): unknown {
  if (!value || typeof value !== "object" || Array.isArray(value)) return value;
  const record = value as Record<string, unknown>;
  if (record.kind === "incremental-learning-dossier") {
    return { ...record, taskSlice: indexedMemoryEvidence(record.taskSlice) };
  }
  if (!Array.isArray(record.entries)) return value;
  return {
    ...record,
    entries: record.entries.map((entry, snapshotIndex) => ({ snapshotIndex, entry })),
  };
}
