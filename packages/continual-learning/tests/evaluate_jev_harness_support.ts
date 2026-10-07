/** Hash-bound, read-only paired research. --live is paid; never grants writes. */
import fs from "node:fs/promises";
import { createHash } from "node:crypto";
import { createJevJudge, type JevJudge } from "../extensions/jev-learning";
import { validateHarnessPlan } from "../extensions/harness-consolidation";
import { harnessSupportShadow, harnessSupportAnswers } from "./jev-harness-support-shadow";
import { pairedPlanMetrics, pairedPlansComplete } from "./jev-paired-metrics";
const live = process.argv.includes("--live");
if (!live && !process.argv.includes("--preflight-only")) throw new Error("Explicit research mode required");
const digest = (text: string) => createHash("sha256").update(text).digest("hex");
const study = JSON.parse(await fs.readFile(new URL("./jev-harness-support-study-manifest.json", import.meta.url), "utf8")) as {
  corpusSha256: string; codeHashes: Record<string, string>;
};
async function verifyCode() {
  for (const [file, expected] of Object.entries(study.codeHashes)) {
    if (digest(await fs.readFile(new URL(file, import.meta.url), "utf8")) !== expected) throw new Error("Frozen research code changed");
  }
}
await verifyCode();
interface Input { id: string; expectedAllow: boolean | null; snapshot: unknown; plan: { operations: unknown[] }; snapshotHash: string; planHash: string }
const inputs: Input[] = [];
for (const file of ["./jev-harness-support-r8-regression-manifest.json", "./jev-harness-support-p-limit-r8-regression-manifest.json"]) {
  const manifest = JSON.parse(await fs.readFile(new URL(file, import.meta.url), "utf8"));
  const texts: Record<string, string> = {};
  for (const [name, item] of Object.entries(manifest.files as Record<string, { path: string; sha256: string }>)) {
    const text = await fs.readFile(item.path, "utf8");
    if (digest(text) !== item.sha256) throw new Error("Frozen real artifact changed");
    texts[name] = text;
  }
  const realPlan = JSON.parse(texts.history).proposal;
  inputs.push({ id: manifest.id, expectedAllow: null, snapshot: JSON.parse(texts.snapshot), plan: realPlan,
    snapshotHash: digest(texts.snapshot), planHash: digest(JSON.stringify(realPlan)) });
}
const corpusText = await fs.readFile(new URL("./fixtures/jev-harness-support-corpus.json", import.meta.url), "utf8");
if (digest(corpusText) !== study.corpusSha256) throw new Error("Frozen bilingual corpus changed");
const corpus: { id: string; expectedAllow: boolean; snapshot: unknown; plan: Input["plan"] }[] = JSON.parse(corpusText);
inputs.push(...corpus.map(row => ({ ...row, snapshotHash: digest(JSON.stringify(row.snapshot)), planHash: digest(JSON.stringify(row.plan)) })));
for (const input of inputs) {
  const errors = validateHarnessPlan(input.plan, { snapshot: input.snapshot, snapshotText: JSON.stringify(input.snapshot), automatic: true, requireEvidence: true, requireCases: true });
  if (errors.length || !input.plan.operations.length) throw new Error("Parent validation rejected fixed research input");
}
if (!live) { console.log(JSON.stringify({ samples: inputs.length, labeledSamples: corpus.length, corpusSha256: digest(corpusText), outboundRequests: 0 })); process.exit(0); }
if (!process.env.TYPESAFE_API_KEY) throw new Error("Real inference requires credentials; no mock substitute");
const MAX_REQUESTS = 144;
let outboundRequests = 0;
type Verdict = Awaited<ReturnType<JevJudge["validate"]>>;
const results: (Input & { before: Verdict; after: Verdict })[] = [];
const diagnostics: { id: string; arm: "before" | "after"; answers: Record<string, unknown> }[] = [];
const durations: Record<string, number[]> = { before: [], after: [] };
const requests: Record<string, number> = { before: 0, after: 0 };
for (const input of inputs) {
  const outcomes: Verdict[] = [];
  for (const arm of ["before", "after"] as const) {
    const judge = createJevJudge({ enabled: true, defaultModel: "jev-1.13.0", scopes: ["harness"], fetch: async (url, init) => {
      const sent = arm === "after" ? harnessSupportShadow(init) : init;
      const request = JSON.parse(String(sent?.body));
      if (Buffer.byteLength(JSON.stringify(request)) > 64_000) throw new Error("Unchanged request byte cap exceeded");
      if (outboundRequests >= MAX_REQUESTS) throw new Error("Research request budget exhausted");
      outboundRequests++; requests[arm]++;
      const response = await fetch(url, sent);
      if (response.ok) diagnostics.push({ id: input.id, arm, answers: harnessSupportAnswers(await response.clone().json(), request.questions) });
      return response;
    } });
    const verdict = await judge.validate("harness", input.snapshot, input.plan.operations, []);
    durations[arm].push(verdict.telemetry.durationMs);
    outcomes.push(verdict);
  }
  results.push({ ...input, before: outcomes[0], after: outcomes[1] });
}
const labeled = results.filter((row): row is typeof row & { expectedAllow: boolean } => row.expectedAllow !== null);
// expectedAllow is irrelevant to completeness; unlabeled real artifacts receive
// no accuracy label and never enter false-accept/false-hold metrics.
const complete = pairedPlansComplete(results.map(row => ({ ...row, expectedAllow: row.expectedAllow ?? false })));
const telemetry = results.flatMap(row => [row.before.telemetry, row.after.telemetry]);
await verifyCode();
console.log(JSON.stringify({ evidence: "real-jev-harness-support-message-action-paired-research", productionWriteEligible: false,
  change: "Only addRule command support question changes; original scope/counter questions, complete evidence, thresholds and bounds remain unchanged",
  complete, samples: results.length, labeledSamples: labeled.length, corpusSha256: digest(corpusText), codeHashes: study.codeHashes, outboundRequests, requestBudget: MAX_REQUESTS,
  requests, durationsMs: durations, metrics: { before: pairedPlanMetrics(labeled, "before"), after: pairedPlanMetrics(labeled, "after") },
  knownInputTokens: telemetry.reduce((sum, row) => sum + (row.inputTokens ?? row.knownInputTokens ?? 0), 0),
  knownEstimatedCostUsd: telemetry.reduce((sum, row) => sum + (row.estimatedCostUsd ?? row.knownEstimatedCostUsd ?? 0), 0),
  results: results.map(({ snapshot: _snapshot, plan: _plan, ...row }) => row), diagnostics }, null, 2));
if (!complete) process.exitCode = 1;
