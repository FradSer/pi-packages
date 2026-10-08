import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { runAndVerify } from "../src/run.ts";

const results = [];
for (const mode of ["semantic", "semantic-negative"]) {
  const cwd = await mkdtemp(path.join(tmpdir(), "pi-e2e-jev-"));
  try {
    await mkdir(path.join(cwd, ".e2e"));
    const adapter = path.resolve(import.meta.dirname, "run-fixture.mjs");
    const runner = {executable: process.execPath, args: [adapter, mode]};
    await writeFile(path.join(cwd, ".e2e/runner.json"), JSON.stringify({...runner, adapterFiles: [adapter]}));
    await writeFile(path.join(cwd, "test.feature"), "Feature: Checkout\nScenario: Pickup confirmation\nGiven a shopper submits an order\nWhen the checkout response is displayed\nThen the shopper is clearly told their order is confirmed and available for pickup\n");
    const result = await runAndVerify({runner, cwd, featurePath: "test.feature", signal: AbortSignal.timeout(30_000)});
    assert.equal(result.modelError, undefined);
    assert.ok(result.verdict.model);
    if (mode === "semantic") assert.equal(result.verdict.status, "fulfilled");
    else assert.notEqual(result.verdict.status, "fulfilled");
    results.push({mode, ...result});
  } finally {await rm(cwd, {recursive: true, force: true});}
}
console.log(JSON.stringify({runtime: "real HTTP adapter + TypeSafe API", results}, null, 2));
