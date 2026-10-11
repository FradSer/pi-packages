import { spawn } from "node:child_process";
import { readFile, rename, writeFile } from "node:fs/promises";

// This check claims only that the named public regression command succeeded.
// Hidden requirement coverage is graded separately, outside the agent sandbox.
const config = JSON.parse(await readFile(process.argv[2] ?? "/pilot/public-check.json", "utf8"));
const started = Date.now();
async function execute(command, timeoutMs) {
return await new Promise((resolve, reject) => {
  const child = spawn("bash", ["-o", "pipefail", "-lc", command], { cwd: process.cwd(), detached: true });
  let output = "";
  let timedOut = false;
  const terminate = () => {
    try { process.kill(-child.pid, "SIGKILL"); } catch {}
  };
  const cancel = () => { terminate(); process.exit(130); };
  process.once("SIGTERM", cancel);
  process.once("SIGINT", cancel);
  const capture = (chunk) => { output = (output + chunk.toString()).slice(-12000); };
  child.stdout.on("data", capture);
  child.stderr.on("data", capture);
  const timer = setTimeout(() => {
    timedOut = true;
    terminate();
  }, timeoutMs);
  child.on("error", (error) => { clearTimeout(timer); reject(error); });
  child.on("close", (code, signal) => {
    clearTimeout(timer);
    process.removeListener("SIGTERM", cancel);
    process.removeListener("SIGINT", cancel);
    resolve({ exitCode: code, signal, timedOut, output });
  });
});
}
const result = await execute(config.command, config.timeoutMs);
const evidence = {
  run: { suite: config.command, observations: { ...result, elapsedMs: Date.now() - started } },
  checks: [{ clause: 1, path: "exitCode", op: "equals", value: 0 },
    { clause: 1, path: "timedOut", op: "equals", value: false }],
};
if (config.requirements) {
  let plan = {};
  try { plan = JSON.parse(await readFile(config.coverageFile, "utf8")); } catch {}
  evidence.run.observations.requirements = {};
  evidence.checks = [];
  const observed = new Map([[config.command, result]]);
  for (let index = 1; index <= config.requirements.length; index++) {
    const entry = plan[String(index)];
    const mapped = entry && typeof entry.command === "string" && entry.command.trim() && entry.command !== config.command
      && Array.isArray(entry.tests) && entry.tests.length > 0 && entry.tests.every(test => typeof test === "string" && test.trim());
    let observation = {exitCode: null, timedOut: false, output: "Uncovered requirement: missing command/test mapping"};
    if (mapped && result.exitCode === 0 && !result.timedOut) {
      if (!observed.has(entry.command)) observed.set(entry.command, await execute(entry.command, Math.max(1, config.timeoutMs - (Date.now() - started))));
      observation = observed.get(entry.command);
    }
    const testNamesObserved = Boolean(mapped && entry.tests.every(test => observation.output.includes(test)));
    evidence.run.observations.requirements[String(index)] = {...observation, testNamesObserved, coverageClaimed: Boolean(mapped)};
    evidence.checks.push({clause: index, path: `requirements.${index}.testNamesObserved`, op: "equals", value: true}, {clause: index, path: `requirements.${index}.exitCode`, op: "equals", value: 0},
      {clause: index, path: `requirements.${index}.timedOut`, op: "equals", value: false});
    process.stderr.write(`Requirement ${index}: ${observation.output}\n`);
  }
}
if (process.env.PI_E2E_EVIDENCE_PATH) {
  const destination = process.env.PI_E2E_EVIDENCE_PATH;
  await writeFile(destination + ".tmp", JSON.stringify(evidence));
  await rename(destination + ".tmp", destination);
} else {
  process.stdout.write(JSON.stringify(evidence) + "\n");
  process.exitCode = result.exitCode === 0 && !result.timedOut && (!config.requirements || Object.values(evidence.run.observations.requirements).every(value => value.exitCode === 0 && !value.timedOut && value.testNamesObserved)) ? 0 : 1;
}
process.stderr.write(result.output + "\n");
