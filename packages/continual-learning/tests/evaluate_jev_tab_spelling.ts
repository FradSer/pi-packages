/** Read-only same-input comparison; frozen public synthetic fixture, paid only with --live. */
import { createHash } from "node:crypto";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { createJevJudge } from "../extensions/jev-learning";
import { validateHarnessPlan } from "../extensions/harness-consolidation";
import { controlledJevAnswers } from "./jev-controlled-diagnostics";

if (!process.argv.includes("--live") || !process.env.TYPESAFE_API_KEY) throw new Error("--live and TYPESAFE_API_KEY required");
const manifest = JSON.parse(await readFile(new URL("./jev-tab-spelling-replay-manifest.json", import.meta.url), "utf8"));
const samples = [];
for (const row of manifest.cases) {
  const snapshotText = await readFile(row.snapshot, "utf8");
  const proposalText = await readFile(row.proposal, "utf8");
  if (createHash("sha256").update(snapshotText).digest("hex") !== row.snapshotSha256
    || createHash("sha256").update(proposalText).digest("hex") !== row.proposalSha256) throw new Error("Frozen input changed");
  const snapshot = JSON.parse(snapshotText), proposal = JSON.parse(proposalText).proposal;
  if (validateHarnessPlan(proposal, { snapshot, automatic: true, availableSkills: [] }).length) throw new Error("Parent structure rejected frozen candidate");
  samples.push({ row, snapshot, proposal });
}
const sourceUrl = new URL("../extensions/jev-learning.ts", import.meta.url);
const source = await readFile(sourceUrl, "utf8");
if (process.argv.includes("--meaning-shadow") && source.includes('const commandWords = stage === "harness" ?')) {
  throw new Error("Meaning shadow is already production; use the production comparison without --meaning-shadow");
}
const line = 'const pattern = candidate.rule.bash.replaceAll("[ \\t]", "[ \\\\t]");';
if (source.split(line).length !== 2) throw new Error("Expected exact reviewed normalization once");
const require = createRequire(import.meta.url);
// Recover only the prior proof grammar. All prompts, input, privacy and thresholds
// are identical; the temporary module is never imported by the extension.
const oldSource = source.replace(line, "const pattern = candidate.rule.bash;")
  .replace(/from "(\.\/[^\"]+)"/g, (_whole: string, relative: string) => `from ${JSON.stringify(new URL(relative + ".ts", sourceUrl).href)}`)
  .replace('from "@typesafe-ai/sdk"', `from ${JSON.stringify(pathToFileURL(require.resolve("@typesafe-ai/sdk")).href)}`);
const temporary = await mkdtemp(join(tmpdir(), "jev-proof-baseline-"));
const diagnostics: Record<string, unknown[]> = { before: [], after: [] };
const meaningShadow = process.argv.includes("--meaning-shadow");
const outboundRequests: Record<string, number> = { before: 0, after: 0 };
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
try {
  const baselinePath = join(temporary, "baseline.ts");
  await writeFile(baselinePath, oldSource, { mode: 0o600 });
  const baseline: typeof import("../extensions/jev-learning") = await import(pathToFileURL(baselinePath).href);
  const results = [];
  for (const { row, snapshot, proposal } of samples) {
    const outcomes = [];
    for (const [label, factory] of [["before", meaningShadow ? createJevJudge : baseline.createJevJudge], ["after", createJevJudge]] as const) {
      const judge = factory({ enabled: true, defaultModel: "jev-1.13.0", scopes: ["harness"], fetch: async (url, init) => {
        if (meaningShadow && label === "after") {
          const request = JSON.parse(String(init?.body));
          for (const [key, question] of Object.entries(request.questions)) {
            if (!key.startsWith("counter_")) continue;
            if (!record(question) || !record(question.instructions) || !record(question.instructions.candidate)
              || !record(question.instructions.candidate.rule)) throw new Error("Unexpected fixed counter question shape");
            const rule = question.instructions.candidate.rule;
            if (typeof rule.action !== "string" || typeof rule.message !== "string") throw new Error("Unexpected fixed rule shape");
            // Research-only fixed git-push fixture, not a general parser or a
            // production bypass. Full originals passed privacy preflight first.
            question.instructions.candidate = { rule: { commandWords: "git push", action: rule.action, message: rule.message,
              matching: "The raw command starts with git and push, separated by ASCII spaces or tabs. Additional arguments may follow; only a space, tab or absolute command end follows push.", scope: "current project" } };
          }
          init = { ...init, body: JSON.stringify(request) };
        }
        outboundRequests[label]++;
        const response = await fetch(url, init);
        if (response.ok) diagnostics[label].push(controlledJevAnswers(await response.clone().json(), JSON.parse(String(init?.body)).questions));
        return response;
      } });
      outcomes.push(await judge.validate("harness", snapshot, proposal.operations, [], undefined, proposal.evidence));
    }
    results.push({ snapshotSha256: row.snapshotSha256, proposalSha256: row.proposalSha256, expectedAllow: true, before: outcomes[0], after: outcomes[1] });
  }
  const telemetry = results.flatMap(row => [row.before.telemetry, row.after.telemetry]);
  const usageComplete = telemetry.every(item => item.inputTokens !== undefined && item.model === "jev-1.13.0");
  const passed = usageComplete && results.every(row => row.after.decision === "allow");
  console.log(JSON.stringify({ evidence: "real-jev-same-input-ascii-tab-proof-comparison", productionWriteEligible: false,
    sourceSha256: createHash("sha256").update(source).digest("hex"), comparison: meaningShadow ? "Research-only: same current proof, counterevidence replaces regex with exact code-proved matching description" : "Only exact ASCII class spelling proof changes; frozen full input, prompts, thresholds and parent validation stay identical",
    usageComplete, passed, outboundRequests, calls: Object.values(outboundRequests).reduce((sum, count) => sum + count, 0),
    judgeAttempts: telemetry.reduce((sum, item) => sum + (item.requestCount ?? 0), 0),
    knownInputTokens: telemetry.reduce((sum, item) => sum + (item.inputTokens ?? item.knownInputTokens ?? 0), 0),
    knownEstimatedCostUsd: telemetry.reduce((sum, item) => sum + (item.estimatedCostUsd ?? item.knownEstimatedCostUsd ?? 0), 0), diagnostics, results }, null, 2));
  if (!passed) process.exitCode = 1;
} finally {
  await rm(temporary, { recursive: true, force: true });
}
