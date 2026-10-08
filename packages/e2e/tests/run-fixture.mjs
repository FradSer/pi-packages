// A real, isolated HTTP test adapter. No production services are contacted.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { writeFile, symlink, rename } from "node:fs/promises";
import { spawn } from "node:child_process";
import { once } from "node:events";

const mode = process.argv[2] ?? "pass";
const target = process.env.PI_E2E_EVIDENCE_PATH;
if (mode === "package-suites") {
  const { spawnSync } = await import("node:child_process");
  const suites = ["packages/goal/tests/", "packages/tasks/tests/"];
  for (const suite of suites) {
    const result = spawnSync("python3", ["-m", "pytest", suite, "-q"], {
      cwd: process.cwd(), encoding: "utf8", maxBuffer: 1024 * 1024,
    });
    if (result.status !== 0) {
      process.stderr.write(result.stderr || result.stdout);
      process.exit(result.status ?? 1);
    }
  }
  if (!target) throw new Error("PI_E2E_EVIDENCE_PATH is required");
  const scenariosText = process.env.PI_E2E_SCENARIOS;
  if (!scenariosText) throw new Error("PI_E2E_SCENARIOS is required");
  const scenarioEvidence = JSON.parse(scenariosText);
  const checks = scenarioEvidence.scenarios.map((item) => ({
    clause: item.clause,
    path: `scenarios.${item.key}`,
    op: "equals",
    value: true,
  }));
  await writeFile(target, JSON.stringify({
    run: { suite: "packages/goal/tests and packages/tasks/tests", observations: scenarioEvidence },
    checks,
  }));
  process.exit(0);
}
if (!target) throw new Error("PI_E2E_EVIDENCE_PATH is required");
if (mode === "hang") { setInterval(() => {}, 1000); await new Promise(() => {}); }
if (mode === "tree") {
  const child = spawn(process.execPath, ["-e", "setInterval(() => {},1000)"], {stdio: "inherit"});
  await writeFile("child.pid.tmp", String(child.pid));
  await rename("child.pid.tmp", "child.pid");
  setInterval(() => {}, 1000);
  await new Promise(() => {});
}
if (mode === "missing") process.exit(0);
if (mode === "output") { process.stdout.write("x".repeat(2 * 1048576)); await new Promise(() => {}); }
if (mode === "malformed") { await writeFile(target, "{"); process.exit(0); }
if (mode === "large") { await writeFile(target, "x".repeat(2 * 1048576)); process.exit(0); }
if (mode === "symlink") { await writeFile("old.json", "{}"); await symlink(`${process.cwd()}/old.json`, target); process.exit(0); }
if (mode === "modify") await writeFile("test.feature", "Feature: Changed\nScenario: Changed\nThen changed\n");

const server = createServer((_request, response) => {
  response.setHeader("content-type", "application/json");
  response.end(JSON.stringify({ value: true, message: mode === "semantic-negative" ? "Payment failed. No order was placed." : "Your order is confirmed and ready for collection." }));
});
server.listen(0, "127.0.0.1");
await once(server, "listening");
try {
  const address = server.address();
  const response = await fetch(`http://127.0.0.1:${address.port}/checkout`);
  assert.equal(response.status, 200);
  const observations = await response.json();
  assert.equal(observations.value, true);
  assert.match(observations.message, mode === "semantic-negative" ? /failed/ : /confirmed/);
  await writeFile(target, JSON.stringify({
    run: { suite: "isolated-http-checkout", observations },
    ...(mode.startsWith("semantic") ? {} : {checks: [{clause: 1, path: "value", op: "equals", value: mode !== "unmet"}]}),
  }));
} finally {
  server.closeAllConnections();
  await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
}
if (mode === "fail") process.exitCode = 1;
