/** Standalone meaning is diagnostic: support, privacy, pairs and parent permission remain mandatory. */
export interface JevMemoryReadinessReview {
  version: 1;
  purpose: "diagnostic-only";
  complete: true;
  evidenceDigest: string;
  existingDigest: string;
  candidatesDigest: string;
  model: string;
  candidates: {index: number; candidateDigest: string; answer: unknown}[];
}

const LABELS = ['selfContained', 'needsOther', 'unresolved'] as const;
type Label = typeof LABELS[number];
export function interpretStandaloneMemory(answer: unknown): {
  status: 'decided' | 'uncertain' | 'invalid-response';
  relation: Label | null;
  standaloneObserved: boolean;
  writeAuthorized: false;
  confidence?: number;
  probabilities?: Record<Label, number>;
} {
  const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
  const probability = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
  const denied = {status: 'invalid-response' as const, relation: null, standaloneObserved: false, writeAuthorized: false as const};
  if (!record(answer) || answer.type !== 'choice' || !LABELS.includes(answer.choice as Label)
    || !probability(answer.confidence) || !record(answer.probabilities)) return denied;
  const raw = answer.probabilities;
  if (Object.keys(raw).length !== LABELS.length || !LABELS.every(key => probability(raw[key]))
    || Math.abs(LABELS.reduce((total, key) => total + (raw[key] as number), 0) - 1) >= .02) return denied;
  const relation = answer.choice as Label;
  const probabilities = Object.fromEntries(LABELS.map(key => [key, raw[key]])) as Record<Label, number>;
  const decided = relation !== 'unresolved' && answer.confidence >= .8 && probabilities[relation] >= .9;
  return {status: decided ? 'decided' : 'uncertain', relation, standaloneObserved: decided && relation === 'selfContained',
    writeAuthorized: false, confidence: answer.confidence, probabilities};
}
