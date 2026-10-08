/**
 * The note that says when the e2e capability is worth reaching for.
 *
 * Like pi-tasks and pi-goal, the package injects one bounded, stable system note
 * directly after the leading system message (index 1) via `context_with_system`.
 *
 * Three deliberate properties:
 * 1. Identical on every turn: keeps prefix caching 100% matched across turns.
 * 2. System message role: reads as harness context, never attributable to the user.
 * 3. Concise and actionable: teaches the model when to verify acceptance criteria,
 *    and reminds it that code decides exact values while Jev evaluates business semantics.
 */

export const E2E_CAPABILITY_NOTE = [
  "[pi-e2e capability]",
  "e2e verifies whether business acceptance criteria and user flows in Gherkin .feature scenarios or test specs are fulfilled.",
  "When working on features, bug fixes, or acceptance verification: run e2e tests or use the e2e_verify tool to judge scenarios against run evidence.",
  "When a .feature file changes, the harness adds a bounded acceptance checkpoint before settlement; inspect project tests, run them, call e2e_verify with runner; the adapter writes fresh Evidence JSON to PI_E2E_EVIDENCE_PATH.",
  "Only successful fresh runner evidence can clear checkpoints; inline and existing-file verdicts remain unverified. Never invent observations; report a blocker or needs_review when real run evidence is unavailable.",
  "You may call e2e_verify repeatedly in one turn after repairing implementation, tests or an authorized adapter. Each attempt must run fresh tests; automatic continuation limits do not limit tool calls.",
  "Code decides exact values through deterministic checks with veto authority; e2e_verify evaluates semantic business clauses with calibrated probabilities.",
  "Do not guess whether acceptance criteria hold. If behavior checks fail, fix the behavior. If evidence is missing or the runner/provider fails, collect observations or resolve that blocker before retrying; unchanged missing evidence is not an implementation failure.",
].join("\n");

const NOTE_ROLE = "system";

/**
 * Inserts the capability note into the transcript directly after the leading system prompt.
 */
export function injectE2ECapabilityNote<T>(messages: readonly T[]): T[] {
  // Idempotent: do not inject if already present in messages
  const alreadyInjected = messages.some(
    (m) => typeof m === "object" && m !== null && (m as { content?: unknown }).content === E2E_CAPABILITY_NOTE,
  );
  if (alreadyInjected) return [...messages];

  const out = [...messages];
  const first = out[0] as { role?: unknown } | undefined;
  const index = first && typeof first === "object" && first.role === "system" ? 1 : 0;
  out.splice(index, 0, { role: NOTE_ROLE, content: E2E_CAPABILITY_NOTE, timestamp: 0 } as T);
  return out;
}
