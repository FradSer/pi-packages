/** Keep only the trusted question IDs/labels and finite numeric judgments. */
export function controlledJevAnswers(raw: unknown, questions: unknown): Record<string, unknown> {
  const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
  const probability = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
  if (!record(raw) || !record(raw.answers) || !record(questions)) return {};
  const out: Record<string, unknown> = {};
  for (const [key, question] of Object.entries(questions)) {
    if (!/^(?:supported|authority|explanation|family|expands|counter)_\d+(?:_\d+)?$/.test(key) || !record(question)) continue;
    const answer = raw.answers[key];
    if (!record(answer) || answer.type !== "choice" || question.type !== "choice" || !record(question.criteria)
      || typeof answer.choice !== "string" || !Object.hasOwn(question.criteria, answer.choice)
      || !probability(answer.confidence) || !record(answer.probabilities)) continue;
    const labels = Object.keys(question.criteria);
    if (Object.keys(answer.probabilities).length !== labels.length || !labels.every(label => probability((answer.probabilities as Record<string, unknown>)[label]))) continue;
    out[key] = { choice: answer.choice, confidence: answer.confidence,
      probabilities: Object.fromEntries(labels.map(label => [label, (answer.probabilities as Record<string, unknown>)[label]])) };
  }
  return out;
}
