/** Fixed public samples only. --live requires prior model/cost authorization. */
import fs from "node:fs/promises";
import { createJevJudge } from "../extensions/jev-learning";
import { evaluateJevSamples, candidateImprovementGate, type Sample } from "./jev-evaluation";
const expanded = process.argv.includes("--expanded-acceptance");
const family = process.argv.includes("--family-acceptance");
const fresh = process.argv.includes("--fresh-acceptance");
const authority = process.argv.includes("--authority-holdout");
const holdout = process.argv.includes("--holdout");
const samples: Sample[] = JSON.parse(await fs.readFile(new URL(expanded ? "./fixtures/jev-expanded-acceptance.json" : family ? "./fixtures/jev-family-safe-acceptance.json" : fresh ? "./fixtures/jev-fresh-acceptance.json" : authority ? "./fixtures/jev-authority-holdout.json" : holdout ? "./fixtures/jev-learning-holdout.json" : "./fixtures/jev-learning.json", import.meta.url), "utf8"));
const live = process.argv.includes("--live");
// Only this checked-in public synthetic corpus contains preference candidates
// that parent normalization marks private. Never load real private entries.
const judge = live ? createJevJudge({ enabled: true, defaultModel: "jev-1.13.0", scopes: ["selection", "memory", "harness"], ...(holdout ? { allowPrivateMemory: true } : {}) }) : undefined;
const report = await evaluateJevSamples(samples, live ? "real-jev-inference" : "offline-baseline-only", judge);
const acceptance = candidateImprovementGate(report);
console.log(JSON.stringify({ ...report, acceptance }, null, 2));
if (!report.complete || (process.argv.includes("--require-improvement") && !acceptance.passed)) process.exitCode = 1;
