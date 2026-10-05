import { controlledJevAnswers } from "./jev-controlled-diagnostics";
import { contentOnlyShadow } from "./jev-content-only-shadow";
/** Explicit hash-bound replay of public Docker artifacts, never a write grant. */
import { invalidationShadow } from "./jev-invalidation-shadow";
import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { createJevJudge } from "../extensions/jev-learning";
import { normalizeNewMemoryProposals } from "../extensions/consolidation-run";
const root = process.argv[2];
if (!root || (!process.argv.includes("--live") && !process.argv.includes("--preflight-only"))) throw new Error("Explicit artifact directory and mode required");
const manifest = JSON.parse(await fs.readFile(new URL("./jev-cited-context-replay-manifest.json", import.meta.url), "utf8")) as { project: string; planPath: string; planHash: string; snapshotHash: string }[];
const digest = (value: string) => createHash("sha256").update(value).digest("hex");
const inputs = [];
for (const item of manifest) {
  const planPath = path.resolve(root, item.planPath);
  if (!planPath.startsWith(path.resolve(root) + path.sep)) throw new Error("Artifact path outside explicitly supplied root");
  const [planText, snapshotText] = await Promise.all([fs.readFile(planPath, "utf8"), fs.readFile(path.join(path.dirname(planPath), "snapshot.json"), "utf8")]);
  if (digest(planText) !== item.planHash || digest(snapshotText) !== item.snapshotHash) throw new Error("Unknown or modified public artifact");
  const snapshot = JSON.parse(snapshotText);
  const candidates = normalizeNewMemoryProposals(JSON.parse(planText), snapshot);
  inputs.push({ ...item, snapshot, candidates });
}
if (process.argv.includes("--preflight-only")) { console.log(JSON.stringify({ checked: inputs.length, outboundCalls: 0 })); process.exit(0); }
if (!process.env.TYPESAFE_API_KEY) throw new Error("Key required for real inference");
const rows = [];
for (const input of inputs) {
  const common = { enabled: true, defaultModel: "jev-1.13.0", allowPrivateMemory: true, scopes: ["memory"] as const };
  // Paired transport experiment: only the support context field is removed.
  // Complete evidence windows and current capacity remain identical.
  const beforeJudge = createJevJudge({ ...common, scopes: [...common.scopes], fetch: async (url, init) => {
    const request = JSON.parse(String(init?.body));
    const state = JSON.parse(request.state);
    if (!process.argv.includes("--invalidation-shadow") && !process.argv.includes("--content-only-shadow") && !process.argv.includes("--metadata-baseline")) delete state.supportEvidence;
    request.state = JSON.stringify(state);
    if (process.argv.includes("--metadata-baseline")) {
      for (const [key, question] of Object.entries(request.questions)) {
        if (!key.startsWith("counter_")) continue;
        const i = Number(key.split("_")[1]);
        const candidate = input.candidates[i];
        const raw = question as { instructions: { candidate: { content: string; action?: string; target?: string; storageScope?: string } } };
        raw.instructions.candidate = { action: "create", target: candidate.name,
          storageScope: candidate.classification === "private" ? "Parent-validated private Memory; never mirrored to project files." : "Parent-validated shareable project Memory.",
          content: raw.instructions.candidate.content };
      }
    }
    if (Buffer.byteLength(JSON.stringify(request)) > 64_000) throw new Error("Baseline request exceeds unchanged wire cap");
    return fetch(url, { ...init, body: JSON.stringify(request) });
  } });
  const judgments: unknown[] = [];
  const afterJudge = createJevJudge({ ...common, scopes: [...common.scopes], fetch: async (url, init) => {
    const response = await fetch(url, process.argv.includes("--content-only-shadow") ? contentOnlyShadow(init) : process.argv.includes("--invalidation-shadow") ? invalidationShadow(init) : init);
    if (process.argv.includes("--diagnostic") && response.ok) {
      const raw: unknown = await response.clone().json();
      const request = JSON.parse(String(init?.body));
      judgments.push(controlledJevAnswers(raw, request.questions));
    }
    return response;
  } });
  const before = await beforeJudge.validate("memory", input.snapshot, input.candidates, []);
  const after = await afterJudge.validate("memory", input.snapshot, input.candidates, []);
  rows.push({ project: input.project, planHash: input.planHash, snapshotHash: input.snapshotHash, before, after, ...(process.argv.includes("--diagnostic") ? { judgments } : {}) });
}
const telemetry = rows.flatMap(row => [row.before.telemetry, row.after.telemetry]);
console.log(JSON.stringify({ evidence: "real-jev-same-candidate-complete-evidence-context-ablation", productionWriteEligible: false,
  baselineScope: process.argv.includes("--metadata-baseline") ? "Same complete evidence, support context and thresholds; before restores prior Memory write metadata in counter questions" : process.argv.includes("--content-only-shadow") ? "Same complete evidence and thresholds; after removes only Memory write metadata from counterevidence questions" : process.argv.includes("--invalidation-shadow") ? "Current complete-state judgments versus research invalidation criteria; unchanged evidence and thresholds" : "Both use current whole-entry capacity; before removes only supportEvidence from review requests. Not an end-to-end comparison.",
  calls: telemetry.reduce((sum, value) => sum + (value.requestCount ?? 0), 0),
  usageComplete: telemetry.every(value => value.inputTokens !== undefined),
  knownInputTokens: telemetry.reduce((sum, value) => sum + (value.inputTokens ?? value.knownInputTokens ?? 0), 0),
  knownEstimatedCostUsd: telemetry.reduce((sum, value) => sum + (value.estimatedCostUsd ?? value.knownEstimatedCostUsd ?? 0), 0), rows }, null, 2));
if (!rows.every(row => row.after.decision === "allow" && row.after.telemetry.inputTokens !== undefined)) process.exitCode = 1;
