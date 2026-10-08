/** Exhaustive acceptance through the configured adapter; no cached receipts. */
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseFeature } from "../src/gherkin.ts";
import { E2EGate } from "../src/harness.ts";
import { parseRunner, runAndVerify, verifiedRun } from "../src/run.ts";

const cwd = process.cwd();
const featurePath = path.resolve(cwd, "packages/goal/features/goal.feature");
const feature = parseFeature(await readFile(featurePath, "utf8"));
const runner = parseRunner(JSON.parse(await readFile(".e2e/runner.json", "utf8")));
const output = process.argv[2];
if (!output) throw new Error("Supply a report output path");
const gate = new E2EGate();
await gate.beginTurn("Verify packages/goal/features/goal.feature completely", cwd);
gate.recordToolResult("write", { path: featurePath }, false, cwd);
const observeVerdict = gate.verdictListener();
const results: { scenario: string; status?: string; verified?: boolean; clauses?: unknown; asked?: readonly string[]; error?: string }[] = [];
let next = 0;
const abort = new AbortController();
const interrupt = () => abort.abort(new Error("Acceptance interrupted"));
process.once("SIGINT", interrupt);
process.once("SIGTERM", interrupt);
await Promise.all(Array.from({ length: 4 }, async () => {
  while (next < feature.scenarios.length && !abort.signal.aborted) {
    const scenario = feature.scenarios[next++]!;
    try {
      const result = await runAndVerify({ cwd, featurePath, scenario: scenario.name, runner, offline: true, signal: abort.signal });
      const scenarios = await verifiedRun(result.verdict, featurePath);
      if (!scenarios) throw new Error("Fresh adapter proof missing or changed");
      await observeVerdict(result.verdict, featurePath, cwd, scenarios);
      results.push({ scenario: scenario.name, status: result.verdict.status, verified: true, clauses: result.verdict.clauses, asked: result.asked });
    } catch (error) {
      results.push({ scenario: scenario.name, error: String(error) });
      abort.abort(error);
    }
    console.log(JSON.stringify({ completed: results.length, total: feature.scenarios.length, errors: results.filter(item => item.error).length }));
  }
}));
process.removeListener("SIGINT", interrupt);
process.removeListener("SIGTERM", interrupt);
await gate.refreshFeatureChanges(cwd);
const checkpoint = gate.checkBeforeSettle({ outcome: "completed", entries: [], context: { pendingMessages: [] } } as never, { cwd } as never);
const passed = results.length === feature.scenarios.length && results.every(item => item.status === "fulfilled" && item.verified && item.asked?.length === 0) && checkpoint === undefined;
await writeFile(output, JSON.stringify({ feature: path.relative(cwd, featurePath), scenarios: feature.scenarios.length, passed, pendingCheckpoint: checkpoint ?? null, results }, null, 2) + "\n");
console.log(JSON.stringify({ passed, scenarios: results.length, pendingCheckpoint: checkpoint !== undefined }));
if (!passed) process.exitCode = 1;
