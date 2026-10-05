import type { JevTelemetry } from "../extensions/jev-learning";

interface PlanVerdict { decision: "allow" | "propose"; telemetry: JevTelemetry }
interface PairedPlan { expectedAllow: boolean; before: PlanVerdict; after: PlanVerdict }
const SEMANTIC_REASONS = new Set(["supported", "uncertain", "unsupported", "duplicate", "conflict", "scope-expansion"]);

/** Availability holds are not evidence of semantic correctness. */
export function pairedPlanMetrics(rows: readonly PairedPlan[], label: "before" | "after") {
  const evaluated = rows.filter(row => row[label].telemetry.model === "jev-1.13.0" && SEMANTIC_REASONS.has(row[label].telemetry.reason)
    && row[label].telemetry.inputTokens !== undefined && row[label].telemetry.outputTokens !== undefined);
  return {
    evaluatedPlans: evaluated.length,
    skippedIncompletePlans: rows.length - evaluated.length,
    falseAccepts: evaluated.filter(row => !row.expectedAllow && row[label].decision === "allow").length,
    falseHolds: evaluated.filter(row => row.expectedAllow && row[label].decision !== "allow").length,
  };
}

export function pairedPlansComplete(rows: readonly PairedPlan[]): boolean {
  return rows.length > 0 && (["before", "after"] as const).every(label =>
    pairedPlanMetrics(rows, label).skippedIncompletePlans === 0);
}
