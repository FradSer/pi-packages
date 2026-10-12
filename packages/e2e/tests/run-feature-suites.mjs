import { spawnSync } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseFeature, scenarioByName } from "../src/gherkin.ts";

const evidencePath = process.env.PI_E2E_EVIDENCE_PATH;
const featurePath = process.env.PI_E2E_FEATURE_PATH;
const scenarioName = process.env.PI_E2E_SCENARIO_NAME;
if (!evidencePath || !featurePath || !scenarioName) throw new Error("Missing E2E runner environment fields");
const feature = path.relative(process.cwd(), featurePath).split(path.sep).join("/");
const index = JSON.parse(await readFile("packages/e2e/tests/scenario-behavior-map.json", "utf8"));
const tests = index[feature]?.[scenarioName];
if (!Array.isArray(tests) || tests.length === 0) throw new Error(`No linked behavior tests for ${feature}: ${scenarioName}`);

const completed = [];
for (const reference of tests) {
  if (typeof reference !== "string" || !/^packages\/(?:goal|tasks|e2e|continual-learning)\/tests\/test_[\w-]+\.py::test_[\w-]+$/.test(reference)) {
    throw new Error(`Invalid mapped test reference: ${String(reference)}`);
  }
  const result = spawnSync("python3", ["-m", "pytest", reference, "-q"], {
    cwd: process.cwd(), encoding: "utf8", maxBuffer: 1024 * 1024,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    process.stderr.write(result.stdout ?? "");
    process.stderr.write(result.stderr ?? "");
    process.exit(result.status ?? 1);
  }
  completed.push({test: reference, output: (result.stdout ?? "").trim()});
}

// Only registered observations can declare clause checks. Linked tests alone
// remain unjudged; never convert their exit status into every Then clause.
const bindings = JSON.parse(await readFile("packages/e2e/tests/scenario-observation-map.json", "utf8"));
const binding = bindings[feature]?.[scenarioName];
let command;
let checks;
if (binding) {
  const parsed = parseFeature(await readFile(featurePath, "utf8"));
  const scenario = scenarioByName(parsed, scenarioName);
  const steps = scenario && [...scenario.background, ...scenario.clauses].map(({ kind, text }) => ({ kind, text }));
  if (!scenario || JSON.stringify(steps) !== JSON.stringify(binding.steps)) {
    throw new Error("Observation binding no longer matches the scenario steps; update the producer contract");
  }
  const producer = binding.producer;
  if (typeof producer !== "string" || !/^packages\/e2e\/tests\/observe-[\w-]+\.mts$/.test(producer)) {
    throw new Error("Invalid observation producer path");
  }
  const configured = JSON.parse(await readFile(".e2e/runner.json", "utf8"));
  if (!configured.adapterFiles?.includes(producer)) throw new Error("Observation producer must be registered in adapterFiles");
  const observed = spawnSync(process.execPath, ["--import", "tsx", producer], {
    cwd: process.cwd(), encoding: "utf8", maxBuffer: 1024 * 1024,
  });
  if (observed.error) throw observed.error;
  if (observed.status !== 0) throw new Error(`Observation producer failed: ${observed.stderr || observed.status}`);
  const output = JSON.parse(observed.stdout);
  if (!output.observations || typeof output.observations !== "object" || Array.isArray(output.observations) ||
      !Array.isArray(output.checks) || output.checks.length === 0 || output.checks.some(check => typeof check.path !== "string")) {
    throw new Error("Observation producer needs observations and clause checks");
  }
  command = output.observations;
  checks = output.checks.map(check => ({ ...check, path: `command.${check.path}` }));
}
await writeFile(evidencePath, JSON.stringify({
  run: {
    suite: "scenario-linked package tests and registered observations",
    steps: completed,
    observations: { feature, scenario: scenarioName, tests: completed, ...(command ? { command } : {}) },
  },
  ...(checks ? { checks } : {}),
}));
