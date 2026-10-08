/** Explicit maintenance only: review fixture expectations before --write. */
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import type { ScenarioObservation } from "../../../tests/e2e/support/assertion-observer.ts";
import { parseFeature } from "../src/gherkin.ts";

const definitions = [
  ["goal_store", "Goal records", "test_durable_state_contracts"],
  ["goal_scheduling", "Goal scheduling", "test_scheduling_authorization_contracts"],
  ["goal_live_context", "Goal prompt replay", "test_prefix_stability_contracts"],
  ["goal_check", "Goal completion transport", "test_completion_check_contracts"],
  ["goal_session", "Goal native sessions", "test_live_session_contracts"],
  ["goal_completion", "Goal completion evidence", "test_completion_evidence_and_no_work_contracts"],
  ["goal_thread", "Goal thread lifecycle", "test_thread_lifecycle_contracts"],
  ["goal_simplified", "Simplified thread Goal lifecycle", "test_simplified_goal_contracts"],
  ["goal_dashboard", "Goal footer", "test_dashboard_geometry_and_input_contracts"],
  ["goal_monitor_evidence", "Goal monitor evidence", "test_monitor_evidence_contracts"],
  ["goal_probe_cleanup", "Goal fixture cleanup", "test_probe_cleanup_observations"],
] as const;
const file = "packages/goal/features/goal.feature";
const observationMapPath = "packages/e2e/tests/scenario-observation-map.json";
const behaviorMapPath = "packages/e2e/tests/scenario-behavior-map.json";
const bindings = JSON.parse(await readFile(observationMapPath, "utf8"));
const links = JSON.parse(await readFile(behaviorMapPath, "utf8"));
const seedName = "/goal hands the model a seed rather than creating a goal";
const seed = bindings[file][seedName];
const observed = new Map<string, { cases: ScenarioObservation[]; hash: string; reference: string; label: string }>();
const folder = await mkdtemp(path.join(tmpdir(), "goal-contract-sync-"));
try {
  for (const [name, label, test] of definitions) {
    const harness = `packages/goal/tests/${name}.mts`;
    const output = path.join(folder, `${name}.json`);
    const run = spawnSync(process.execPath, ["--import", "tsx", harness], {
      encoding: "utf8", timeout: 120000, maxBuffer: 1024 * 1024,
      env: { ...process.env, TMPDIR: folder, PI_E2E_ASSERTION_PATH: output },
    });
    if (run.error || run.status !== 0) throw new Error(`${harness} failed: ${run.error ?? (run.stderr || run.stdout)}`);
    const cases = JSON.parse(await readFile(output, "utf8")) as ScenarioObservation[];
    if (!cases.length || cases.some(item => !item.assertions.length || item.assertions.some(a => !a.matched || a.assertionId === "unknown"))) {
      throw new Error(`${harness} has missing or failed assertion observations`);
    }
    observed.set(harness, { cases, hash: createHash("sha256").update(await readFile(harness)).digest("hex"),
      reference: `${name === "goal_monitor_evidence" ? "packages/goal/tests/test_goal_monitor_evidence.py" : "packages/goal/tests/test_goal.py"}::${test}`, label });
  }
} finally { await rm(folder, { recursive: true, force: true }); }

type Input = { harness: string; case: string; harnessHash: string; assertions: { clause: number; assertionId: string; source: string; count: number }[] };
const caseInput = (harness: string, name: string, clause?: number): Input => {
  const fixture = observed.get(harness)!;
  const record = fixture.cases.find(item => item.name === name);
  if (!record) throw new Error(`Missing case: ${name}`);
  const unique = [...new Set(record.assertions.map(a => a.assertionId))];
  return { harness, case: name, harnessHash: fixture.hash, assertions: unique.map((id, index) => {
    const matches = record.assertions.filter(a => a.assertionId === id);
    return {clause: clause ?? index + 1, assertionId: id, source: matches[0]!.source, count: matches.length};
  }) };
};

const scenarios: { name: string; section: string; steps: { kind: string; text: string }[]; cases?: Input[]; references: string[] }[] = [];
scenarios.push({name: seedName, section: "Starting a goal", steps: seed.steps, references: links[file][seedName]});
const session = "packages/goal/tests/goal_session.mts";
const simplified = "packages/goal/tests/goal_simplified.mts";
const capability = caseInput(session, "the capability note requires an explicit persistent-goal request");
// Exact assertion selectors for the semantic clauses retained as readable aliases.
capability.assertions.forEach(item => { item.clause = item.source.includes("explicitly asks") ? 2 : item.source.includes("Write the objective") ? 3 : item.source.includes("ordinary work") || item.source.includes("创建") ? 4 : 1; });
scenarios.push({name: "Capability notes require an explicit persistent Goal request", section: "Starting a goal",
  steps: [{kind:"given",text:"no Goal is focused"},{kind:"when",text:"a real Pi request is built"},
    {kind:"then",text:"a capability note is injected"},{kind:"then",text:"it requires an explicit request for a persistent Goal"},
    {kind:"then",text:"it asks the model to write the objective from the conversation"},{kind:"then",text:"it says when NOT to make a Goal out of a request"}],
  cases:[capability], references:[observed.get(session)!.reference]});
scenarios.push({name:"Three model-facing tools",section:"Starting a goal",
  steps:[{kind:"given",text:"the Goal extension is loaded"},{kind:"when",text:"its tools are registered and ordinary research runs"},
    {kind:"then",text:"only create_goal, get_goal and update_goal are registered"},{kind:"then",text:"ordinary tools perform research without a Goal research child"}],
  cases:[caseInput(simplified, "Given a loaded Goal extension When tools register Then only three Goal tools exist",1),
    caseInput(session,"ordinary tools research without a Goal research child",2)],
  references:[observed.get(simplified)!.reference,observed.get(session)!.reference]});

for (const [harness, fixture] of observed) {
  for (const record of fixture.cases) {
    const input = caseInput(harness, record.name);
    scenarios.push({name:`${fixture.label}: ${record.name}`,section:fixture.label,
      steps:[{kind:"given",text:`the isolated fixtures for ${record.name}`},{kind:"when",text:"the real Goal modules execute this behavior case"},
        ...input.assertions.map(check=>({kind:"then",text:`the predicate ${check.source.replace(/\s+/g," ")} holds for every observed invocation`}))],
      cases:[input],references:[fixture.reference]});
  }
}
let content = "# Atomic current contracts; original 106 scenarios are traced in\n# packages/e2e/tests/goal-scenario-migration.json. Expectations come from\n# independent behavior fixtures; suite exit status is never clause evidence.\n";
let section = "";
for (const scenario of scenarios) {
  if (scenario.section !== section) { section = scenario.section; content += `\nFeature: ${section}\n`; }
  content += `\n  Scenario: ${scenario.name}\n`;
  scenario.steps.forEach((step,index)=> { content += `    ${step.kind === "then" && scenario.steps[index-1]?.kind === "then" ? "And" : step.kind[0]!.toUpperCase()+step.kind.slice(1)} ${step.text}\n`; });
}
// Parse the emitted Gherkin rather than assuming all expressions are accepted.
const parsed = parseFeature(content);
if (parsed.scenarios.length !== scenarios.length) throw new Error("Generated contract lost scenarios");
bindings[file] = Object.fromEntries(scenarios.map(s=>[s.name,s.cases ? {producer:"packages/e2e/tests/observe-goal-harness.mts",steps:s.steps,cases:s.cases} : seed]));
links[file] = Object.fromEntries(scenarios.map(s=>[s.name,s.references]));
const outputs = new Map([[file,content],[observationMapPath,JSON.stringify(bindings,null,2)+"\n"],[behaviorMapPath,JSON.stringify(links,null,2)+"\n"]]);
if (process.argv.includes("--write")) {
  for (const [target,value] of outputs) await writeFile(target,value);
} else {
  for (const [target,value] of outputs) if (await readFile(target,"utf8") !== value) throw new Error(`Stale ${target}; review changes before sync-goal-contracts.mts --write`);
}
console.log(JSON.stringify({scenarios:scenarios.length,clauses:scenarios.reduce((sum,s)=>sum+s.steps.filter(step=>step.kind==="then").length,0)}));
