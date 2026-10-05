/** Replays explicitly named public-repository artifacts and synthetic preferences.
 * --live is a real paid call; never discovers host sessions or records raw evidence.
 */
import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { createJevJudge } from "../extensions/jev-learning";
import { normalizeNewMemoryProposals } from "../extensions/consolidation-run";
const root = process.argv[2];
if (!root || !process.argv.includes("--live")) throw new Error("Explicit artifact directory and --live required");
async function find(dir: string, name: string): Promise<string[]> {
  const found: string[] = [];
  for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...await find(file, name));
    else if (entry.isFile() && entry.name === name) found.push(file);
  }
  return found.sort();
}
const planPath = (await find(root, "plan.json"))[0];
if (!planPath) throw new Error("No preserved Memory plan");
const snapshotText = await fs.readFile(path.join(path.dirname(planPath), "snapshot.json"), "utf8");
const planText = await fs.readFile(planPath, "utf8");
const snapshot = JSON.parse(snapshotText);
const candidates = normalizeNewMemoryProposals(JSON.parse(planText), snapshot);
const answers: unknown[] = [];
const judge = createJevJudge({ fetch: async (url, init) => {
  const response = await fetch(url, init);
  if (response.ok) {
    const body = await response.clone().json() as { answers: Record<string, Record<string, unknown>> };
    const request = JSON.parse(String(init?.body));
    answers.push(Object.fromEntries(Object.entries(body.answers).filter(([key]) => key in request.questions).map(([key, answer]) => [key, {
      type: answer.type === "choice" || answer.type === "noul" ? answer.type : undefined,
      choice: typeof answer.choice === "string" && answer.choice in (request.questions[key].criteria ?? {}) ? answer.choice : undefined,
      confidence: typeof answer.confidence === "number" ? answer.confidence : undefined,
      noul: typeof answer.noul === "number" ? answer.noul : undefined,
      probabilities: answer.type === "choice" ? Object.fromEntries(Object.keys(request.questions[key].criteria).map(label =>
        [label, typeof (answer.probabilities as Record<string, unknown>)?.[label] === "number" ? (answer.probabilities as Record<string, unknown>)[label] : null])) : undefined,
    }])));
  }
  return response;
}, enabled: true, defaultModel: "jev-1.13.0", allowPrivateMemory: true, scopes: ["memory"] });
const result = await judge.validate("memory", snapshot, candidates, []);
console.log(JSON.stringify({ evidence: "real-jev-inference-frozen-public-repository-replay",
  snapshotDigest: createHash("sha256").update(snapshotText).digest("hex"),
  planDigest: createHash("sha256").update(planText).digest("hex"), snapshotBytes: Buffer.byteLength(snapshotText),
  candidates: candidates.length, answers, ...result }, null, 2));
