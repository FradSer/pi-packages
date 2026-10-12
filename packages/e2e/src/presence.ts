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
  "Use e2e_verify for requested acceptance/E2E checks or changed .feature scenarios. Read the feature and authorized .e2e/runner.json first; do not create or alter integration without authorization.",
  "Plan verification early: after a coherent implementation increment, run the relevant configured adapter through e2e_verify, leaving budget for failure diagnosis, repairs and a fresh retry. Do not postpone the first verification until the final response.",
  "The tool runs tests itself. Avoid running the same suite separately immediately before verification; use focused checks for diagnosis, then fresh adapter verification after repairs. If the configured suite cannot fit the remaining budget, report that blocker; do not silently weaken coverage or extend authorization.",
  "Only completed fresh runner evidence clears a checkpoint. A started call, interrupted run, supplied evidence or stale pass is not verified acceptance. Never invent observations.",
  "Before verification, map each public requirement to an observable scenario/check; mark uncovered requirements explicitly. When authorized to author integration, add focused behavior checks for gaps. A feature containing only a regression-command exit check is not a complete acceptance plan.",
  "For full feature coverage use allScenarios:true with the authorized runner. Legacy calls without scenario verify only the first scenario. Read coverage.remaining and every scenario result. Follow nextAction: collect_evidence for missing observations or uncertainty; repair_code for fresh concrete mismatches; resolve_blocker for execution/provider errors. Preserve checks and expected behavior.",
  "Report the covered scenarios and remaining requirements separately: a passing regression command does not prove full request acceptance. Do not change expected behavior or assertions merely to get a pass.",
  "Code checks exact values with veto authority; Jev judges only remaining semantic clauses. Missing evidence or runner/provider failure needs observations or blocker resolution, not speculative implementation changes.",
  "If repeated inspections or unchanged reruns yield no new evidence, stop that loop and report the concrete blocker or uncovered requirement. An unchanged patch is acceptable when coverage is sufficient; do not make cosmetic edits to appear productive. Reserve time for verification of the final changed code and a concise completion report.",
  "After repairs, call e2e_verify again with fresh tests. Automatic checkpoint continuations are bounded; they do not limit tool calls. Respect explicit execution opt-outs.",
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
