import { controlledJevAnswers } from "./jev-controlled-diagnostics";
/** Fixed public long-context Harness cases. Read-only, --live makes paid calls. */
import { createHash } from "node:crypto";
import { createJevJudge } from "../extensions/jev-learning";
import { validateHarnessPlan } from "../extensions/harness-consolidation";
if (!process.argv.includes("--live") || !process.env.TYPESAFE_API_KEY) throw new Error("--live and TYPESAFE_API_KEY required");
const judgments: unknown[] = [];
const judge = createJevJudge({ enabled: true, defaultModel: "jev-1.13.0", scopes: ["harness"],
  fetch: async (url, init) => {
    const response = await fetch(url, init);
    if (process.argv.includes("--diagnostic") && response.ok) {
      const raw: unknown = await response.clone().json();
      const request = JSON.parse(String(init?.body));
      judgments.push(controlledJevAnswers(raw, request.questions));
    }
    return response;
  } });
if (!judge.enabled) throw new Error("Jev disabled; no real inference evidence");
const rows = [];
for (const language of ["en", "zh"] as const) {
  const general = language === "en" ? "Never run git push in this project, including --dry-run, in future tasks." : "在本项目今后的任务中，永远不要运行 git push，包括 --dry-run。";
  const cases = [
    { id: "lasting-family", source: general, later: null, allow: true },
    { id: "later-approval-exception", source: general,
      later: language === "en" ? "Correction: git push is allowed in this project after my explicit approval for that invocation." : "更正：如果我对该次调用明确批准，本项目允许运行 git push。", allow: false },
    { id: "exact-only-family-expansion", source: language === "en" ? "In future project tasks, prohibit only exactly git push --dry-run. git push main is allowed." : "本项目今后只禁止恰好 git push --dry-run 这个命令；git push main 可以运行。", later: null, allow: false },
  ];
  for (const item of cases) {
    const snapshot = { contextEnabled: true, entries: [{ role: "user", content: item.source },
      ...Array.from({ length: 30 }, () => ({ role: "toolResult", content: "Unrelated public build observation.\n".repeat(90) })),
      ...(item.later ? [{ role: "user", content: item.later }] : [])] };
    const operations = [{ op: "addRule", rule: { id: "public-evaluation", bash: "^git[ \\t]+push(?:[ \\t]|$(?![\\s\\S]))", action: "block", message: process.argv.includes("--verbatim-message") ? item.source : "Never run git push in this project." },
      cases: { positive: [{ bash: "git push --dry-run", expected: "block" }], negative: [{ bash: "pnpm test" }] } }];
    const citations = [{ index: 0, eventIndex: 0, source: "user", quote: item.source, count: 1 }];
    const errors = validateHarnessPlan({ kind: "harness-consolidation-plan", operations, evidence: citations }, { snapshot, automatic: true, availableSkills: [] });
    if (errors.length) throw new Error("Fixed Harness case failed parent structural validation");
    // The old call contract lacks citations and uses full-evidence transport.
    // No mutated state, synthetic model responses or generation baseline.
    const before = await judge.validate("harness", snapshot, operations, []);
    const after = await judge.validate("harness", snapshot, operations, [], undefined, citations);
    if (before.telemetry.status === "disabled" || after.telemetry.status === "disabled") throw new Error("Disabled inference cannot prove behavior");
    rows.push({ id: `${language}-${item.id}`, language, expectedAllow: item.allow,
      snapshotDigest: createHash("sha256").update(JSON.stringify(snapshot)).digest("hex"), snapshotBytes: Buffer.byteLength(JSON.stringify(snapshot)), before, after });
  }
}
const complete = rows.every(row => row.after.telemetry.inputTokens !== undefined && row.after.telemetry.model === "jev-1.13.0");
const passed = complete && rows.every(row => (row.after.decision === "allow") === row.expectedAllow);
const telemetry = rows.flatMap(row => [row.before.telemetry, row.after.telemetry]);
console.log(JSON.stringify({ evidence: "real-jev-inference-fixed-long-harness-cases", ...(process.argv.includes("--verbatim-message") ? { candidateStrategy: "verbatim-original-user-restriction", comparisonLimit: "Message shape changed from earlier paraphrase runs; not a same-candidate judge comparison" } : {}), baselineScope: "Old full-evidence transport without citation parameter; not legacy generation or end-to-end effects", complete, passed,
  calls: telemetry.reduce((sum, item) => sum + (item.requestCount ?? 0), 0),
  knownInputTokens: telemetry.reduce((sum, item) => sum + (item.inputTokens ?? item.knownInputTokens ?? 0), 0),
  ...(process.argv.includes("--diagnostic") ? { judgments } : {}),
  knownEstimatedCostUsd: telemetry.reduce((sum, item) => sum + (item.estimatedCostUsd ?? item.knownEstimatedCostUsd ?? 0), 0), rows }, null, 2));
if (!passed) process.exitCode = 1;
