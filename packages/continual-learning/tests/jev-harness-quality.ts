import { evaluateBash, mergeLayers } from "../extensions/guardrail-engine";

export interface HarnessQualityProbe { id: string; command: string; expected: "block" | "execute" }

/** Matcher-only audit: never executes probe commands or writes Harness. */
export function assessHarnessContainerQuality(container: Record<string, unknown>, probes: readonly HarnessQualityProbe[]) {
  const config = mergeLayers([{ ...container, source: "frozen-project" }]);
  const cases = probes.map(probe => ({ id: probe.id, expected: probe.expected, decision: evaluateBash(config, probe.command).decision }));
  const incompleteCases = cases.filter(item => item.decision === "incomplete").length;
  const falseBlocks = cases.filter(item => item.expected === "execute" && ["block", "confirm"].includes(item.decision)).length;
  const missedConstraints = cases.filter(item => item.expected === "block" && item.decision !== "block" && item.decision !== "incomplete").length;
  return { evaluatedCases: cases.length - incompleteCases, incompleteCases, falseBlocks, missedConstraints,
    satisfiesAll: cases.length > 0 && !incompleteCases && !falseBlocks && !missedConstraints, cases };
}

/** Synthetic fixture convenience; real artifacts use the full container entry point. */
export function assessHarnessQuality(rules: readonly Record<string, unknown>[], probes: readonly HarnessQualityProbe[]) {
  return assessHarnessContainerQuality({ rules: [...rules] }, probes);
}
