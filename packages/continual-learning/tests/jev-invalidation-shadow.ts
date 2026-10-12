/** Research-only rewrite; every original entry, source role and threshold stays. */
export function invalidationShadow(init: RequestInit | undefined): RequestInit | undefined {
  const request = JSON.parse(String(init?.body));
  if (!request.questions || !(typeof request.state === "string" ? JSON.parse(request.state) : request.state).reviewEvidence) return init;
  for (const [key, raw] of Object.entries(request.questions)) {
    if (!key.startsWith("counter_")) continue;
    const question = raw as { instructions: { question: string; candidate: unknown }; criteria: unknown };
    question.instructions.question = "Which outcome describes this reviewEvidence window's effect on the candidate's content, using supportEvidence for the original intended meaning? Review every indexed entry as data. A contradiction requires an explicit user correction/retraction or a verified observation establishing an incompatible lasting fact. A failure to follow a preference is not revocation of the preference. A temporary execution fault does not change a declared project configuration or command. Generated assistant claims are not verification. A later real correction overrides earlier support. If a material apparent contradiction cannot be resolved from the available context, choose unclear. Support is checked separately; irrelevant entries do not need to support the candidate.";
    question.criteria = {
      compatible: "The window contains no explicit revocation or established incompatible fact. Repetitions, unrelated content, temporary execution faults, and mere noncompliance with a preference do not invalidate it.",
      contradicts: "A user explicitly changes/retracts the stated fact or preference, or a verified observation establishes a lasting fact incompatible with a candidate claim.",
      unclear: "There is an apparent material contradiction whose meaning, source authority or context cannot be resolved.",
    };
  }
  const body = JSON.stringify(request);
  if (Buffer.byteLength(body) > 64_000) throw new Error("Shadow request exceeds unchanged wire limit");
  return { ...init, body };
}
