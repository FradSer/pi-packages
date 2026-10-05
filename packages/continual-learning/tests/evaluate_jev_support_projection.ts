/** Read-only research: same frozen evidence, candidates and policy; --live is paid. */
import fs from "node:fs/promises";
import { createHash } from "node:crypto";
import { createJevJudge, type JevTelemetry, type JevJudge } from "../extensions/jev-learning";
import { normalizeNewMemoryProposals } from "../extensions/consolidation-run";
import { pairedPlanMetrics, pairedPlansComplete } from "./jev-paired-metrics";
import { controlledJevAnswers } from "./jev-controlled-diagnostics";
import type { Sample } from "./jev-evaluation";
import type { SelectedMemory } from "../extensions/incremental-learning";
const live = process.argv.includes("--live");
if (!live && !process.argv.includes("--preflight-only")) throw new Error("Explicit mode required");
const hash = (text: string) => createHash("sha256").update(text).digest("hex");
const manifest = JSON.parse(await fs.readFile(new URL("./jev-support-projection-manifest.json", import.meta.url), "utf8")) as { snapshot: string; plan: string; snapshotHash: string; planHash: string; id: string }[];
const inputs = [];
for (const item of manifest) {
  const [snapshotText, planText] = await Promise.all([fs.readFile(item.snapshot, "utf8"), fs.readFile(item.plan, "utf8")]);
  if (hash(snapshotText) !== item.snapshotHash || hash(planText) !== item.planHash) throw new Error("Frozen public input changed");
  const snapshot = JSON.parse(snapshotText);
  inputs.push({ id: item.id, expectedAllow: true, snapshot, candidates: normalizeNewMemoryProposals(JSON.parse(planText), snapshot), existing: [] as SelectedMemory[], snapshotHash: item.snapshotHash, planHash: item.planHash });
}
const samples: Sample[] = JSON.parse(await fs.readFile(new URL(process.argv.includes("--expanded") ? "./fixtures/jev-expanded-acceptance.json" : "./fixtures/jev-learning-holdout.json", import.meta.url), "utf8"));
for (const sample of samples.filter(row => row.stage === "memory" && (process.argv.includes("--expanded") || !row.existing))) {
  const snapshot = { contextEnabled: true, entries: [{ role: "user", content: sample.evidence }] };
  const content = (sample.candidate as { content: string }).content;
  const plan = { newMemories: [{ name: "candidate.md", kind: "project", classification: "safe", content: `---\nname: candidate\ndescription: Public fixed evaluation fact\ntype: project\n---\n${content}\n`, evidence: [{ index: 0, quote: sample.evidence }] }] };
  inputs.push({ id: sample.id, expectedAllow: sample.allow, snapshot, candidates: normalizeNewMemoryProposals(plan, snapshot), existing: sample.existing ? [{ name: "known.md", type: "project", classification: "safe" as const, description: "Public fixed existing knowledge", content: sample.existing }] : [], snapshotHash: hash(JSON.stringify(snapshot)), planHash: hash(JSON.stringify(plan)) });
}
if (inputs.some(row => !row.candidates.length)) throw new Error("Parent normalization found no candidate");
if (!live) { console.log(JSON.stringify({ samples: inputs.length, outboundRequests: 0 })); process.exit(0); }
if (!process.env.TYPESAFE_API_KEY) throw new Error("Real inference requires key");
type Verdict = Awaited<ReturnType<JevJudge["validate"]>>;
const results: { id: string; expectedAllow: boolean; snapshotHash: string; planHash: string; before: Verdict; after: Verdict }[] = [];
const diagnostics: Record<string, unknown[]> = { before: [], after: [] };
const requests: Record<string, number> = { before: 0, after: 0 };
for (const input of inputs) {
  const outcomes: Verdict[] = [];
  for (const label of ["before", "after"] as const) {
    const judge = createJevJudge({ enabled: true, defaultModel: "jev-1.13.0", allowPrivateMemory: true, scopes: ["memory"], fetch: async (url, init) => {
      const request = JSON.parse(String(init?.body));
      for (const [key, value] of Object.entries(request.questions)) {
        if (!key.startsWith("supported_")) continue;
        const question = value as { instructions: { candidate?: { content?: unknown; action?: string; target?: string; storageScope?: string } } };
        const content = question.instructions.candidate?.content;
        if (typeof content !== "string") throw new Error("Fixed create candidate has no knowledge body");
        const candidate = input.candidates[Number(key.slice("supported_".length))];
        question.instructions.candidate = label === "after" ? { content } : {
          action: "create", target: candidate.name,
          storageScope: candidate.classification === "private" ? "Parent-validated private Memory; never mirrored to project files." : "Parent-validated shareable project Memory.", content,
        };
      }
      if (Buffer.byteLength(JSON.stringify(request)) > 64_000) throw new Error("Unchanged wire cap exceeded");
      requests[label]++;
      const response = await fetch(url, { ...init, body: JSON.stringify(request) });
      if (response.ok) diagnostics[label].push({ id: input.id, answers: controlledJevAnswers(await response.clone().json(), request.questions) });
      return response;
    } });
    outcomes.push(await judge.validate("memory", input.snapshot, input.candidates, input.existing));
  }
  results.push({ id: input.id, expectedAllow: input.expectedAllow, snapshotHash: input.snapshotHash, planHash: input.planHash, before: outcomes[0], after: outcomes[1] });
}
const telemetry: JevTelemetry[] = results.flatMap(row => [row.before.telemetry, row.after.telemetry]);
const complete = pairedPlansComplete(results);
const metrics = (label: "before" | "after") => pairedPlanMetrics(results, label);
console.log(JSON.stringify({ evidence: "real-jev-support-body-only-paired-comparison", productionWriteEligible: false, measurementUnit: "whole-plan decisions, not individual candidate claims", complete, samples: results.length, requests, metrics: { before: metrics("before"), after: metrics("after") }, knownInputTokens: telemetry.reduce((sum, row) => sum + (row.inputTokens ?? row.knownInputTokens ?? 0), 0), knownEstimatedCostUsd: telemetry.reduce((sum, row) => sum + (row.estimatedCostUsd ?? row.knownEstimatedCostUsd ?? 0), 0), results, diagnostics }, null, 2));
if (!complete) process.exitCode = 1;
