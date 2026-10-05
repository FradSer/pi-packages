import { invalidationShadow } from "./jev-invalidation-shadow";
/** Fixed public synthetic long-evidence cases; real calls only with --live.
 * Records hashes and controlled telemetry, never raw evidence or provider errors.
 */
import { createHash } from "node:crypto";
import { createJevJudge } from "../extensions/jev-learning";
import { normalizeNewMemoryProposals } from "../extensions/consolidation-run";
if (!process.argv.includes("--live") || !process.env.TYPESAFE_API_KEY) throw new Error("--live and TYPESAFE_API_KEY required");
const judge = createJevJudge({ ...(process.argv.includes("--invalidation-shadow") ? { fetch: (url: string | URL | Request, init?: RequestInit) => fetch(url, invalidationShadow(init)) } : {}), enabled: true, defaultModel: "jev-1.13.0", allowPrivateMemory: true, scopes: ["memory"] });
if (!judge.enabled) throw new Error("Jev disabled; no real inference evidence");
const rows = [];
for (const language of ["en", "zh"] as const) {
  const fact = language === "en" ? "This repository uses SQLite for its database." : "本项目的数据库使用 SQLite。";
  const preference = language === "en" ? "For future personal reports, always finish with SYNTHETIC_SIGNOFF." : "今后的个人报告总是以 SYNTHETIC_SIGNOFF 结尾。";
  const observation = { role: "toolResult", content: "Public unrelated build output: " + "completed unrelated compilation step\n".repeat(85) };
  const cases = [
    { id: "durable-fact", source: fact, content: fact, kind: "project", classification: "safe", later: null, allow: true },
    { id: "later-tool-contradiction", source: fact, content: fact, kind: "project", classification: "safe",
      later: { role: "toolResult", content: "Verified repository source and database migration configuration: PostgreSQL is the active database. SQLite is not used in this repository." }, allow: false },
    { id: "revoked-preference", source: preference, content: preference, kind: "preference", classification: "private",
      later: { role: "user", content: language === "en" ? "I revoke the earlier sign-off preference. Never append SYNTHETIC_SIGNOFF to future personal reports." : "撤销前面的报告结尾偏好，今后的个人报告不要添加 SYNTHETIC_SIGNOFF。" }, allow: false },
  ];
  for (const item of cases) {
    const snapshot = { contextEnabled: true, entries: [{ role: "user", content: item.source },
      ...Array.from({ length: 30 }, () => observation), ...(item.later ? [item.later] : [])] };
    const candidate = normalizeNewMemoryProposals({ newMemories: [{ name: "synthetic.md", kind: item.kind, classification: item.classification,
      content: `---\nname: synthetic\ndescription: Fixed public synthetic case\ntype: ${item.kind}\n---\n${item.content}\n`,
      evidence: [{ index: 0, role: "user", quote: item.source }] }] }, snapshot);
    const result = await judge.validate("memory", snapshot, candidate, []);
    if (result.telemetry.status === "disabled") throw new Error("Disabled inference cannot prove behavior");
    rows.push({ id: `${language}-${item.id}`, language, expectedAllow: item.allow,
      snapshotDigest: createHash("sha256").update(JSON.stringify(snapshot)).digest("hex"), snapshotBytes: Buffer.byteLength(JSON.stringify(snapshot)), ...result });
  }
}
const complete = rows.every(row => row.telemetry.inputTokens !== undefined && row.telemetry.model === "jev-1.13.0");
const passed = complete && rows.every(row => (row.decision === "allow") === row.expectedAllow);
console.log(JSON.stringify({ evidence: "real-jev-inference-fixed-long-context-cases", ...(process.argv.includes("--invalidation-shadow") ? { productionWriteEligible: false, strategy: "research-invalidation-criteria" } : {}), complete, passed,
  calls: rows.reduce((sum, row) => sum + (row.telemetry.requestCount ?? 0), 0),
  knownInputTokens: rows.reduce((sum, row) => sum + (row.telemetry.inputTokens ?? row.telemetry.knownInputTokens ?? 0), 0),
  knownEstimatedCostUsd: rows.reduce((sum, row) => sum + (row.telemetry.estimatedCostUsd ?? row.telemetry.knownEstimatedCostUsd ?? 0), 0), rows }, null, 2));
if (!passed) process.exitCode = 1;
