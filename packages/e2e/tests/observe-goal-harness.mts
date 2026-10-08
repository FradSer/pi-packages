/** Run the registered behavior case and expose its individual assertion witnesses. */
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import type { ScenarioObservation } from "../../../tests/e2e/support/assertion-observer.ts";

const featurePath = process.env.PI_E2E_FEATURE_PATH;
const scenarioName = process.env.PI_E2E_SCENARIO_NAME;
if (!featurePath || !scenarioName) throw new Error("Missing feature or scenario for observation");
const feature = path.relative(process.cwd(), featurePath).split(path.sep).join("/");
const bindings = JSON.parse(await readFile("packages/e2e/tests/scenario-observation-map.json", "utf8"));
type CaseBinding = {
  harness: string; case: string; harnessHash: string;
  assertions: { clause: number; assertionId: string; source: string; count: number }[];
};
const binding = bindings[feature]?.[scenarioName] as { cases: CaseBinding[] } | undefined;
if (!binding?.cases?.length) throw new Error("Missing registered Goal cases");
const observations: {case: string; harness: string; assertions: ScenarioObservation["assertions"]}[] = [];
const checks: {clause: number; path: string; op: string; value: boolean}[] = [];
for (const [caseIndex, item] of binding.cases.entries()) {
  if (!/^packages\/goal\/tests\/goal_[\w-]+\.mts$/.test(item.harness)) throw new Error("Missing registered Goal harness");
  const source = await readFile(item.harness, "utf8");
  if (createHash("sha256").update(source).digest("hex") !== item.harnessHash) {
    throw new Error("Behavior harness changed; review its assertion bindings before verification");
  }
  const folder = await mkdtemp(path.join(tmpdir(), "goal-assertion-run-"));
  try {
    const outputPath = path.join(folder, "observations.json");
    const run = spawnSync(process.execPath, ["--import", "tsx", item.harness], {
      cwd: process.cwd(), encoding: "utf8", maxBuffer: 1024 * 1024, timeout: 120000,
      env: { ...process.env, TMPDIR: folder, PI_E2E_ASSERTION_PATH: outputPath },
    });
    if (run.error) throw run.error;
    if (run.status !== 0) throw new Error(`Behavior harness failed: ${run.stderr || run.stdout}`);
    const cases = JSON.parse(await readFile(outputPath, "utf8")) as ScenarioObservation[];
    const matches = cases.filter(observed => observed.name === item.case);
    if (matches.length !== 1) throw new Error("Expected exactly one observed behavior case");
    const assertions = matches[0]!.assertions;
    if (!item.assertions.length || assertions.some(observed => !item.assertions.some(check => check.assertionId === observed.assertionId))) {
      throw new Error("Unexpected or unbound behavior assertions");
    }
    const caseChecks = item.assertions.flatMap(check => {
      const witnessed = assertions.map((item, index) => ({ item, index })).filter(({ item }) => item.assertionId === check.assertionId);
      if (witnessed.length !== check.count || witnessed.some(({ item }) => item.source !== check.source)) {
        throw new Error("Missing, changed or repeated assertion witnesses differ from the approved contract");
      }
      return witnessed.map(({ index }) => ({ clause: check.clause, path: `cases[${caseIndex}].assertions[${index}].matched`, op: "equals", value: true }));
    });
    observations.push({case: item.case, harness: item.harness, assertions});
    checks.push(...caseChecks);
  } finally { await rm(folder, { recursive: true, force: true }); }
}
console.log(JSON.stringify({observations: {cases: observations}, checks}));
