/** Research-only ablation: Memory counterevidence checks content, not write metadata. */
export function contentOnlyShadow(init: RequestInit | undefined): RequestInit | undefined {
  const request = JSON.parse(String(init?.body));
  for (const [key, question] of Object.entries(request.questions)) {
    if (!key.startsWith("counter_")) continue;
    const raw = question as { instructions: { candidate?: { content?: unknown } } };
    if (typeof raw.instructions.candidate?.content === "string") {
      raw.instructions.candidate = { content: raw.instructions.candidate.content };
    }
  }
  return { ...init, body: JSON.stringify(request) };
}
