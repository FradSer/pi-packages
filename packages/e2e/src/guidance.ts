import type { CheckObservation, Verdict } from "./types.ts";

export type NextAction = "none" | "collect_evidence" | "repair_code" | "resolve_blocker";

export interface Finding {
  readonly scenario: string;
  readonly clause: number;
  readonly text: string;
  readonly action: NextAction;
  readonly reason: string;
  readonly check?: CheckObservation;
}

/** Only an actual fresh deterministic counterexample justifies code repair. */
export function findings(verdict: Verdict, fresh: boolean): Finding[] {
  const items = verdict.clauses.flatMap<Finding>(clause => {
    if (clause.status === "met") return [];
    const failed = clause.checks?.filter(check => check.failureKind !== undefined) ?? [];
    const base = { scenario: verdict.scenario, clause: clause.clause, text: clause.text };
    if (failed.length > 0) return failed.map(check => ({
      ...base, check,
      action: fresh && check.failureKind === "mismatch" ? "repair_code" as const : "collect_evidence" as const,
      reason: !fresh ? "Run the authorized adapter to confirm this supplied counterexample."
        : check.failureKind === "mismatch" ? "Fresh observed value contradicts the declared check; inspect the indicated behavior and test."
        : check.failureKind === "missing_observation" ? "Collect the missing observation before changing production code."
        : "Correct the adapter check before drawing a conclusion about production code.",
    }));
    return [{ ...base, action: "collect_evidence" as const, reason: clause.detail ?? "No settled observation proves this clause; collect evidence or review the semantic judgment." }];
  });
  if (items.length === 0 && verdict.status !== "fulfilled") items.push({ scenario: verdict.scenario, clause: 0,
    text: "Overall semantic verdict", action: "collect_evidence", reason: verdict.reason });
  return items;
}

export function nextAction(items: readonly Finding[], blocker = false, fresh = true): NextAction {
  if (blocker) return "resolve_blocker";
  if (items.some(item => item.action === "repair_code")) return "repair_code";
  return items.length > 0 || !fresh ? "collect_evidence" : "none";
}
