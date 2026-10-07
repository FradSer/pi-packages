/** Hash-bound, read-only paired research. --live is paid; never grants writes. */
import fs from "node:fs/promises";
import { createHash } from "node:crypto";
import { createJevJudge, type JevJudge } from "../extensions/jev-learning";
import { validateHarnessPlan } from "../extensions/harness-consolidation";
import { harnessSupportAnswers } from "./jev-harness-support-shadow";
import { loadFiniteAuthorityJudge } from "./jev-finite-authority-shadow";
import { validateHarnessResearch } from "./jev-harness-research-validation";
import { pairedPlanMetrics, pairedPlansComplete } from "./jev-paired-metrics";
const live = process.argv.includes("--live");
if (!live && !process.argv.includes("--preflight-only")) throw new Error("Explicit research mode required");
const digest = (text: string) => createHash("sha256").update(text).digest("hex");
const study = JSON.parse(await fs.readFile(new URL("./jev-finite-authority-heldout-study-manifest.json", import.meta.url), "utf8")) as {
  corpusSha256: string; patchedSha256: string; codeHashes: Record<string, string>;
};
async function verifyCode() {
  for (const [file, expected] of Object.entries(study.codeHashes)) {
    if (digest(await fs.readFile(new URL(file, import.meta.url), "utf8")) !== expected) throw new Error("Frozen research code changed");
  }
}
await verifyCode();
interface Input { id: string; expectedAllow: boolean | null; snapshot: unknown; plan: { operations: unknown[]; evidence?: unknown }; snapshotHash: string; planHash: string }
const inputs: Input[] = [];
const corpusText = await fs.readFile(new URL("./fixtures/jev-finite-authority-heldout-corpus.json", import.meta.url), "utf8");
if (digest(corpusText) !== study.corpusSha256) throw new Error("Frozen bilingual corpus changed");
const corpus: { id: string; expectedAllow: boolean; snapshot: unknown; plan: Input["plan"] }[] = JSON.parse(corpusText);
inputs.push(...corpus.map(row => ({ ...row, snapshotHash: digest(JSON.stringify(row.snapshot)), planHash: digest(JSON.stringify(row.plan)) })));
for (const input of inputs) {
  const errors = validateHarnessPlan(input.plan, { snapshot: input.snapshot, snapshotText: JSON.stringify(input.snapshot), automatic: true, requireEvidence: true, requireCases: true });
  if (errors.length || !input.plan.operations.length) throw new Error("Parent validation rejected fixed research input");
}
if (!live) { console.log(JSON.stringify({ samples: inputs.length, labeledSamples: corpus.length, corpusSha256: digest(corpusText), outboundRequests: 0 })); process.exit(0); }
if (!process.env.TYPESAFE_API_KEY) throw new Error("Real inference requires credentials; no mock substitute");
const outputIndex = process.argv.indexOf("--output");
const outputPath = outputIndex >= 0 ? process.argv[outputIndex + 1] : undefined;
if (!outputPath) throw new Error("Live research requires a saved report path before any inference");
const reserved = await fs.open(outputPath, "wx");
await reserved.writeFile(JSON.stringify({ evidence: "research-started-incomplete", complete: false }) + "\n");
await reserved.close();
const MAX_REQUESTS = 192;
const research = await loadFiniteAuthorityJudge();
if (research.sourceSha256 !== study.codeHashes["../extensions/jev-learning.ts"] || research.patchedSha256 !== study.patchedSha256) {
  await research.dispose(); throw new Error("Frozen source experiment changed");
}
let outboundRequests = 0;
type Verdict = Awaited<ReturnType<JevJudge["validate"]>>;
const results: (Input & { before: Verdict; after: Verdict })[] = [];
const diagnostics: { id: string; arm: "before" | "after"; answers: Record<string, unknown> }[] = [];
const durations: Record<string, number[]> = { before: [], after: [] };
const requests: Record<string, number> = { before: 0, after: 0 };
try {
for (const input of inputs) {
  const outcomes: Verdict[] = [];
  for (const arm of ["before", "after"] as const) {
    const factory = arm === "after" ? research.createJevJudge : createJevJudge;
    const judge = factory({ enabled: true, defaultModel: "jev-1.13.0", scopes: ["harness"], fetch: async (url, init) => {
      const sent = init;
      const request = JSON.parse(String(sent?.body));
      if (Buffer.byteLength(JSON.stringify(request)) > 64_000) throw new Error("Unchanged request byte cap exceeded");
      if (outboundRequests >= MAX_REQUESTS) throw new Error("Research request budget exhausted");
      outboundRequests++; requests[arm]++;
      const response = await fetch(url, sent);
      if (response.ok) diagnostics.push({ id: input.id, arm, answers: harnessSupportAnswers(await response.clone().json(), request.questions) });
      return response;
    } });
    const verdict = await validateHarnessResearch(judge, input);
    durations[arm].push(verdict.telemetry.durationMs);
    outcomes.push(verdict);
  }
  results.push({ ...input, before: outcomes[0], after: outcomes[1] });
}
} finally { await research.dispose(); }
const labeled = results.filter((row): row is typeof row & { expectedAllow: boolean } => row.expectedAllow !== null);
// expectedAllow is irrelevant to completeness; unlabeled real artifacts receive
// no accuracy label and never enter false-accept/false-hold metrics.
const complete = pairedPlansComplete(results.map(row => ({ ...row, expectedAllow: row.expectedAllow ?? false })));
const telemetry = results.flatMap(row => [row.before.telemetry, row.after.telemetry]);
await verifyCode();
const report = { evidence: "real-jev-finite-command-family-heldout-paired-research", productionWriteEligible: false,
  change: "Only new block rules with exact proven finite Git grammar use existing lasting-authority, explanation and argument-family judgments; full counterevidence, thresholds, bounds and parent permissions remain mandatory",
  complete, samples: results.length, labeledSamples: labeled.length, corpusSha256: digest(corpusText), codeHashes: study.codeHashes, patchedSha256: research.patchedSha256, outboundRequests, requestBudget: MAX_REQUESTS,
  requests, durationsMs: durations, metrics: { before: pairedPlanMetrics(labeled, "before"), after: pairedPlanMetrics(labeled, "after") },
  knownInputTokens: telemetry.reduce((sum, row) => sum + (row.inputTokens ?? row.knownInputTokens ?? 0), 0),
  knownEstimatedCostUsd: telemetry.reduce((sum, row) => sum + (row.estimatedCostUsd ?? row.knownEstimatedCostUsd ?? 0), 0),
  results: results.map(({ snapshot: _snapshot, plan: _plan, ...row }) => row), diagnostics };
await fs.writeFile(outputPath, JSON.stringify(report, null, 2) + "\n", "utf8");
console.log(JSON.stringify({ complete, samples: results.length, labeledSamples: labeled.length, outboundRequests, metrics: report.metrics, knownInputTokens: report.knownInputTokens, knownEstimatedCostUsd: report.knownEstimatedCostUsd }));
if (!complete) process.exitCode = 1;
