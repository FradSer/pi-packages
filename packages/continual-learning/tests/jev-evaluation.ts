/** Fixed public examples only. No project/session/auth discovery and no writes.
 * --live invokes the paid service; run only after model/cost authorization.
 * Offline mode reports baseline labels only, never fabricated Jev answers. */
import type { JevJudge, JevTelemetry, JevSelection } from "../extensions/jev-learning";
import { normalizeNewMemoryProposals } from "../extensions/consolidation-run";
import { validateHarnessPlan } from "../extensions/harness-consolidation";
import { manualIncrementalScreen } from "../extensions/learning-efficiency";
import type { SelectedMemory } from "../extensions/incremental-learning";
export interface Sample {
  id: string; language: "en" | "zh"; evidence: string; memory: boolean; harness: boolean;
  memoryOnly?: boolean; stage: "memory" | "harness"; candidate: unknown; existing?: string; allow: boolean;
}

export type EvaluationMode = "offline-baseline-only" | "real-jev-inference" | "simulated-jev-inference";
interface After {
  selection: JevSelection | null; combinedMemory: boolean | null; combinedHarness: boolean | null;
  candidateAllowed: boolean | null; selectionTelemetry: JevTelemetry; validationTelemetry?: JevTelemetry;
}
interface Row {
  id: string; language: "en" | "zh"; stage: "memory" | "harness";
  expected: { memory: boolean; harness: boolean; candidateAllowed: boolean };
  codeValidation: string; baselineDurationMs: number;
  baseline: { memory: boolean; harness: boolean; candidateAllowed: boolean }; after: After | null;
}
function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}
function metrics(rows: Row[], after: boolean) {
  const directions = rows.filter(row => !after || (row.after?.combinedMemory !== null && row.after?.combinedMemory !== undefined
    && row.after?.combinedHarness !== null && row.after?.combinedHarness !== undefined));
  const candidates = rows.filter(row => !after || typeof row.after?.candidateAllowed === "boolean");
  let missedDirections = 0, extraDirections = 0;
  for (const row of directions) {
    for (const key of ["memory", "harness"] as const) {
      const value = after ? key === "memory" ? row.after!.combinedMemory : row.after!.combinedHarness : row.baseline[key];
      if (row.expected[key] && !value) missedDirections++;
      if (!row.expected[key] && value) extraDirections++;
    }
  }
  return { directionSamples: directions.length, candidateSamples: candidates.length,
    missedDirections: directions.length ? missedDirections : null, extraDirections: directions.length ? extraDirections : null,
    candidateFalseAccepts: candidates.length ? candidates.filter(row => !row.expected.candidateAllowed && (after ? row.after!.candidateAllowed : row.baseline.candidateAllowed)).length : null,
    supportedCandidatesHeld: candidates.length ? candidates.filter(row => row.expected.candidateAllowed && !(after ? row.after!.candidateAllowed : row.baseline.candidateAllowed)).length : null,
    memoryFalseAccepts: candidates.length ? candidates.filter(row => row.stage === "memory" && !row.expected.candidateAllowed && (after ? row.after!.candidateAllowed : row.baseline.candidateAllowed)).length : null,
    harnessFalseHolds: candidates.length ? candidates.filter(row => row.stage === "harness" && row.expected.candidateAllowed && !(after ? row.after!.candidateAllowed : row.baseline.candidateAllowed)).length : null,
    medianLatencyMs: median(after ? rows.flatMap(row => [row.after?.selectionTelemetry, row.after?.validationTelemetry].flatMap(t => t ? [t.durationMs] : [])) : rows.map(row => row.baselineDurationMs)),
    uncertainJudgments: after ? rows.flatMap(row => [row.after?.selectionTelemetry, row.after?.validationTelemetry]).filter(t => t?.reason === "uncertain").length : 0 };
}

export async function evaluateJevSamples(samples: readonly Sample[], mode: EvaluationMode, judge?: JevJudge) {
  if (mode !== "offline-baseline-only" && !judge) throw new Error("Inference mode requires an explicit judge");
  const rows: Row[] = [];
  let calls = 0, tokens = 0, estimatedCostUsd = 0;
  let costKnown = true;
  let usageKnown = true;
  let stopReason: string | undefined;
  function account(telemetry: JevTelemetry): boolean {
    if (telemetry.inputTokens === undefined) {
      costKnown = false;
      usageKnown = false;
      stopReason = telemetry.reason;
      return false;
    }
    tokens += telemetry.inputTokens;
    if (telemetry.outputTokens === undefined) usageKnown = false;
    if (telemetry.estimatedCostUsd === undefined) {
      costKnown = false;
      stopReason = "unknown-cost";
      return false;
    }
    estimatedCostUsd += telemetry.estimatedCostUsd;
    if (telemetry.outputTokens === undefined) {
      stopReason = "incomplete-usage";
      return false;
    }
    return true;
  }
for (const sample of samples) {
  const evidence = { contextEnabled: true, entries: [{ message: { role: "user", content: sample.evidence } }] };
  const metadata = [{ name: "known.md", classification: "safe" as const, type: "project", description: sample.existing ?? "Project package manager and test commands" }];
  const baselineStarted = performance.now();
  const baseline = manualIncrementalScreen(evidence.entries, { memory: false, harness: false, agents: false });
  const baselineDurationMs = performance.now() - baselineStarted;
  let candidate: unknown;
  if (!sample.candidate || typeof sample.candidate !== "object" || Array.isArray(sample.candidate)) throw new Error("Invalid evaluation candidate");
  if (sample.stage === "memory") {
    const content = (sample.candidate as { content?: unknown }).content;
    if (typeof content !== "string") throw new Error("Invalid evaluation Memory content");
    candidate = normalizeNewMemoryProposals({ newMemories: [{ name: "candidate.md", kind: "project", classification: "safe",
      content: `---\nname: candidate\ndescription: Fixed public evaluation fact\ntype: project\n---\n${content}\n`,
      evidence: [{ index: 0, quote: sample.evidence }] }] }, evidence)[0];
  } else {
    const rule = (sample.candidate as { rule?: Record<string, unknown> }).rule;
    if (!rule) throw new Error("Invalid evaluation Harness rule");
    candidate = { op: "addRule", rule: { id: "evaluation", ...rule },
      cases: (sample.candidate as { cases?: unknown }).cases ?? { positive: [{ bash: "git push production", expected: "block" }], negative: [{ bash: "pnpm test" }] } };
    const errors = validateHarnessPlan({ kind: "harness-consolidation-plan", operations: [candidate],
      evidence: [{ index: 0, source: "user", quote: sample.evidence, count: 1 }] }, { snapshot: evidence, automatic: true, availableSkills: [] });
    if (errors.length) throw new Error(`Evaluation code validation failed: ${errors.join("; ")}`);
  }
  let after: After | null = null;
  let stopped = false;
  if (mode !== "offline-baseline-only" && judge) {
    // One selection plus at most nine bounded support/review requests.
    if (calls + 13 > 120 || tokens + 48_000 > 1_000_000) { stopReason = "budget"; break; }
    const selection = await judge.select(evidence, metadata, sample.memoryOnly === true);
    calls += selection.telemetry.requestCount ?? 1;
    after = { selection: selection.selection, combinedMemory: selection.selection ? sample.memoryOnly === true || baseline.memory || selection.selection.memory : null,
      combinedHarness: selection.selection ? !sample.memoryOnly && (baseline.harness || selection.selection.harness) : null,
      candidateAllowed: null, selectionTelemetry: selection.telemetry };
    if (!account(selection.telemetry)) stopped = true;
    if (!stopped) {
      const existing: SelectedMemory[] = sample.existing ? [{ ...metadata[0], content: sample.existing }] : [];
      const validation = await judge.validate(sample.stage, evidence, [candidate], existing);
      calls += validation.telemetry.requestCount ?? 1;
      after.validationTelemetry = validation.telemetry;
      after.candidateAllowed = validation.decision === "allow";
      if (!account(validation.telemetry)) stopped = true;
    }
  }
  rows.push({ id: sample.id, language: sample.language, stage: sample.stage, expected: { memory: sample.memory, harness: sample.harness, candidateAllowed: sample.allow },
    codeValidation: "passed", baselineDurationMs,
    baseline: { memory: sample.memoryOnly === true || baseline.memory, harness: !sample.memoryOnly && baseline.harness,
      candidateAllowed: true }, after });
  if (stopped) break;
}
  const metricsByLanguage = Object.fromEntries((["en", "zh"] as const).map(language => {
    const subset = rows.filter(row => row.language === language);
    return [language, { samples: subset.length, baseline: metrics(subset, false), after: subset.some(row => row.after) ? metrics(subset, true) : null }];
  }));
  return { evidence: mode, modelRequested: "jev-1.13.0", complete: rows.length === samples.length && !stopReason,
    ...(stopReason ? { stopReason } : {}),
    baselineScope: "deterministic parent screen and code-validated candidate; not the legacy LLM selector or an end-to-end learning comparison",
    calls, costKnown, usageKnown, inputTokens: usageKnown ? tokens : null, knownInputTokens: tokens,
    estimatedCostUsd: costKnown ? estimatedCostUsd : null, knownEstimatedCostUsd: estimatedCostUsd,
    actualModels: [...new Set(rows.flatMap(row => [row.after?.selectionTelemetry.model, row.after?.validationTelemetry?.model].filter((model): model is string => model !== undefined)))],
    metrics: metricsByLanguage, rows };
}

/** Strict candidate gate; not a claim about legacy generation or native effects. */
export function candidateImprovementGate(report: { complete: boolean; evidence: string; rows: readonly {
  expected: { candidateAllowed: boolean }; baseline: { candidateAllowed: boolean };
  after: { candidateAllowed: boolean | null } | null;
}[] }) {
  const missing = report.rows.filter(row => typeof row.after?.candidateAllowed !== "boolean").length;
  const risks = report.rows.filter(row => !row.expected.candidateAllowed);
  const good = report.rows.filter(row => row.expected.candidateAllowed);
  const baselineFalseAccepts = risks.filter(row => row.baseline.candidateAllowed).length;
  const falseAccepts = risks.filter(row => row.after?.candidateAllowed === true).length;
  const baselineHolds = good.filter(row => !row.baseline.candidateAllowed).length;
  const holds = good.filter(row => row.after?.candidateAllowed === false).length;
  return { scope: "code-validated candidate gate only; not end-to-end effects", passed: report.complete && report.evidence === "real-jev-inference"
    && missing === 0 && risks.length > 0 && good.length > 0 && falseAccepts < baselineFalseAccepts && holds <= baselineHolds,
    missing, baselineFalseAccepts, falseAccepts, baselineHolds, holds };
}
