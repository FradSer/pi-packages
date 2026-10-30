import assert from "node:assert/strict";
import {spawnSync} from "node:child_process";
import {fileURLToPath} from "node:url";
import {test} from "node:test";

// Reuse the controlled production-command harness in its own Bun process so
// module mocks and isolated Memory roots cannot leak into another test.
function run(fixture: string, coverage = "held") {
  const result = spawnSync("bun", [fileURLToPath(new URL("./learning-policy-harness.ts", import.meta.url)), "remember-shared"], {
    cwd: fileURLToPath(new URL("../../../..", import.meta.url)),
    env: {...process.env, TYPESAFE_API_KEY: "", CL_JEV_FIXTURE: fixture,
      CL_COVERAGE_INITIAL_RESULT: coverage},
    encoding: "utf8", timeout: 120_000, maxBuffer: 16 * 1024 * 1024,
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout.trim().split("\n").at(-1)!);
}

for (const kind of ["citations", "body", "description", "retained-only", "mixed-retained"]) {
  test(`uncertain coverage alone does not launch a ${kind} correction`, () => {
    const result = run(`coverage-real-repair-${kind}`);
    assert.equal(result.semanticRepairs, 0);
    assert.equal(result.totalRepairs, 0);
    assert.equal(result.coverageRepairTransports.length, 1);
    assert.equal(result.bodyReviewCalls, 1);
    assert.equal(result.registryReceipt.operations, 0);
    assert.equal(result.memoryMirrored, false);
    assert.equal(result.coverageRepairContracts.length, 0);
    assert.equal(result.coverageRepairResponses.length, 1);
    const initial = result.coverageRepairReviews.find((review: any) => review.coverage);
    assert.ok(initial.coverage.checks.every((check: any) => check.choice === "complete" && check.confidence === .72));
    assert.ok(Object.values(initial.checks).every((check: any) => check.positiveProbabilityLowerBound >= .9 && check.confidence >= .8));
    assert.ok(result.registryReceipt.attempts.some((attempt: any) => attempt.jev?.status === "propose" && attempt.jev.reason === "uncertain"));
    assert.equal(result.registryReceipt.attempts.filter((attempt: any) => attempt.usage?.cost === .004).length, 1);
    if (["retained-only", "mixed-retained"].includes(kind)) {
      assert.ok(result.correctedKnownMemory.endsWith("Existing knowledge.\n"));
      // The initial safe mirror synchronization predates this review.
      assert.equal(result.history.filter((record: any) => record.status === "applied").length, 1);
      assert.ok(result.history.every((record: any) => record.status === "applied" || record.changes.length === 0));
    }
  });
}

test("a confirmed missing condition keeps its existing semantic correction", () => {
  const result = run("coverage-real-correction");
  assert.equal(result.semanticRepairs, 1);
  assert.equal(result.registryReceipt.operations, 1);
  assert.equal(result.memoryMirrored, true);
  assert.ok(result.conciseMemory.includes("Apply this convention only during releases."));
});

test("a genuine source hold keeps evidence-only correction when coverage passed", () => {
  const result = run("coverage-real-repair-source", "passed");
  assert.equal(result.semanticRepairs, 1);
  assert.equal(result.registryReceipt.operations, 1);
  assert.equal(result.coverageRepairTransports.length, 2);
  assert.equal(result.memoryMirrored, true);
});

test("a confirmed body contradiction still enters correction beside uncertain coverage", () => {
  const result = run("coverage-real-repair-body-conflict");
  assert.equal(result.semanticRepairs, 1);
  assert.equal(result.bodyReviewCalls, 1);
  // This fixture changes citations only; the original hold cannot be redrawn.
  assert.equal(result.registryReceipt.operations, 0);
  assert.equal(result.coverageRepairTransports.length, 1);
});

test("an invalid account cannot suppress an independently held source correction", () => {
  const result = run("coverage-real-invalid-correction");
  assert.equal(result.semanticRepairs, 1);
  assert.equal(result.registryReceipt.operations, 1);
  assert.equal(result.memoryMirrored, true);
});
