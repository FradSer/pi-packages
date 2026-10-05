/** Explicitly authorized real calls over the fixed public synthetic corpus only. */
import fs from "node:fs/promises";
import { createJevJudge } from "../extensions/jev-learning";
import type { Sample } from "./jev-evaluation";
const samples: Sample[] = JSON.parse(await fs.readFile(new URL("./fixtures/jev-expanded-acceptance.json", import.meta.url), "utf8"));
const transport: unknown[] = [];
const judge = createJevJudge({ enabled: true, defaultModel: "jev-1.13.0", scopes: ["selection"],
  fetch: async (url, init) => {
    const response = await fetch(url, init);
    // Public numeric judgments only; never retain requests, headers or errors.
    if (response.ok) {
      const body = await response.clone().json() as { model: string; answers: Record<string, Record<string, unknown>>; usage: unknown };
      transport.push({ model: body.model, usage: body.usage, answers: Object.fromEntries(Object.entries(body.answers).map(([key, answer]) =>
        [key, { type: answer.type, noul: answer.noul, score: answer.score, confidence: answer.confidence, probabilities: answer.probabilities }])) });
    }
    return response;
  },
});
const rows: unknown[] = [];
for (const sample of samples) {
  const result = await judge.select({ entries: [{ index: 0, message: { role: "user", content: sample.evidence } }] },
    [{ name: "known.md", classification: "safe", type: "project", description: "Fixed public evaluation fact" }], false);
  rows.push({ id: sample.id, ...result, response: transport.at(-1) });
  if (result.telemetry.inputTokens === undefined) break;
}
console.log(JSON.stringify({ evidence: "real-jev-inference-public-numeric-diagnostic", rows }, null, 2));
