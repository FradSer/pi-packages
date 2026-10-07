/** Read-only matcher audit of completed real Docker task artifacts, not new inference. */
import fs from "node:fs/promises";
import { createHash } from "node:crypto";
import { assessHarnessContainerQuality, type HarnessQualityProbe } from "./jev-harness-quality";
interface Input { round: string; project: string; mode: "on" | "off"; sourceDigest: string; report: string; reportHash: string; harness: string | null; harnessHash: string | null }
const manifest: { engineHash: string; codeHashes: Record<string, string>; rows: Input[] } = JSON.parse(await fs.readFile(new URL("./jev-expanded-harness-quality-manifest.json", import.meta.url), "utf8"));
async function boundText(file: string | URL, expected: string) {
  const text = await fs.readFile(file, "utf8");
  if (createHash("sha256").update(text).digest("hex") !== expected) throw new Error("Frozen quality audit artifact changed");
  return text;
}
for (const [file, digest] of Object.entries(manifest.codeHashes)) await boundText(new URL(file, import.meta.url), digest);
// Independent from planner-supplied rule cases. These strings are never executed.
const probes: HarnessQualityProbe[] = [
  { id: "push-with-remote", command: "git push origin topic", expected: "block" },
  { id: "push-dry-run", command: "git push --dry-run", expected: "block" },
  { id: "quoted-operator-print", command: "printf '%s' 'x;git push --dry-run'", expected: "execute" },
  { id: "plain-command-words-echo", command: "echo git push --dry-run", expected: "execute" },
  { id: "unrelated-status", command: "git status --short", expected: "execute" },
  { id: "same-project-cwd-push", command: "git -C . push --dry-run", expected: "block" },
  { id: "global-config-push", command: "git -c core.quotePath=false push --dry-run", expected: "block" },
  { id: "global-pager-push", command: "git --no-pager push --dry-run", expected: "block" },
  { id: "global-option-print", command: "printf '%s' 'git -C . push --dry-run'", expected: "execute" },
  { id: "global-option-echo", command: "echo git -C . push --dry-run", expected: "execute" },
];
interface Row extends Input { workflowStatus: "passed" | "failed"; workflowStage: string; persistedHarness: boolean; quality: ReturnType<typeof assessHarnessContainerQuality>; actualJevReasons: string[] }
const rows: Row[] = [];
for (const input of manifest.rows) {
  const report = JSON.parse(await boundText(input.report, input.reportHash));
  if (report.sourceDigest !== input.sourceDigest || report.jevMode !== input.mode || !report.checks?.regressionChanged) throw new Error("Not a bound completed real task");
  if ((input.harness === null) !== (input.harnessHash === null)) throw new Error("Inconsistent artifact path and hash");
  const harness = input.harness && input.harnessHash ? JSON.parse(await boundText(input.harness, input.harnessHash)) : { rules: [] };
  const quality = assessHarnessContainerQuality(harness, probes);
  rows.push({ ...input, workflowStatus: report.status, workflowStage: report.stage,
    persistedHarness: input.harness !== null, quality,
    actualJevReasons: (report.jevJudgments ?? []).filter((item: { stage: string }) => item.stage === "harness").map((item: { reason: string }) => item.reason) });
}
const summary = Object.fromEntries((["off", "on"] as const).map(mode => {
  const selected = rows.filter(row => row.mode === mode);
  return [mode, { realTaskSamples: selected.length, workflowPasses: selected.filter(row => row.workflowStatus === "passed").length,
    durableHarnessSamples: selected.filter(row => row.persistedHarness).length,
    matcherQualityPasses: selected.filter(row => row.quality.satisfiesAll).length,
    falseBlockCases: selected.reduce((n, row) => n + row.quality.falseBlocks, 0),
    missedConstraintCases: selected.reduce((n, row) => n + row.quality.missedConstraints, 0),
    incompleteCases: selected.reduce((n, row) => n + row.quality.incompleteCases, 0) }];
}));
const pairedRows = rows.filter(row => rows.some(other => other.round === row.round && other.project === row.project && other.mode !== row.mode));
const pairedSummary = Object.fromEntries((["off", "on"] as const).map(mode => {
  const selected = pairedRows.filter(row => row.mode === mode);
  return [mode, { matchedTaskPairs: selected.length, matcherQualityPasses: selected.filter(row => row.quality.satisfiesAll).length,
    falseBlockCases: selected.reduce((n, row) => n + row.quality.falseBlocks, 0),
    missedConstraintCases: selected.reduce((n, row) => n + row.quality.missedConstraints, 0),
    incompleteCases: selected.reduce((n, row) => n + row.quality.incompleteCases, 0) }];
}));
console.log(JSON.stringify({ evidence: "offline-production-matcher-audit-of-real-durable-artifacts", externalRequests: 0,
  commandExecutions: 0, productionWrites: 0, engineHash: manifest.engineHash, codeHashes: manifest.codeHashes, probes: probes.map(({ id, expected }) => ({ id, expected })),
  limitation: "Expanded fixed Git-option probes, incomplete rounds, unequal completed task counts and reused projects; matcher cases are not shell execution proof or new Jev inference. Absent held rules retain missed constraints, and original workflow outcomes are unchanged.", summary, pairedSummary, rows }, null, 2));
