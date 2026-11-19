import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { mock } from "bun:test";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const before = '  {"rules": []}\r\n';
const foreign = ' {"rules":[{"id":"external","text":"external","instructions":"External edit"}]}\n';
const scenarios = ["post-644", "post-600", "post-missing", "readback-direct", "readback-pipeline", "external-bytes", "external-permissions", "rollback-race"];

async function fixture(scenario: string) {
  const { mock } = await import("bun:test");
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "cl-harness-rollback-")));
  const cwd = path.join(root, "project"), agent = path.join(root, "agent");
  fs.mkdirSync(path.join(cwd, ".pi"), { recursive: true });
  fs.mkdirSync(agent);
  process.env.PI_CODING_AGENT_DIR = agent;
  const target = path.join(cwd, ".pi/harness.json");
  const mode = scenario === "post-missing" ? null : scenario === "post-600" ? 0o600 : 0o644;
  if (mode !== null) { fs.writeFileSync(target, before); fs.chmodSync(target, mode); }
  const real = {rename: fs.promises.rename.bind(fs.promises), readFile: fs.promises.readFile.bind(fs.promises),
    open: fs.promises.open.bind(fs.promises), lstat: fs.promises.lstat.bind(fs.promises)};
  let postReceipt = "", written = false, injected = false, failedPost = false, rollbackTemporary = false, raced = false;
  const isPipeline = !scenario.startsWith("post-") && !scenario.startsWith("readback-");
  let candidate: Buffer | undefined;
  const patched = {
    ...real,
    rename: async (from: fs.PathLike, to: fs.PathLike) => {
      if (String(to) === postReceipt && !injected && !scenario.startsWith("readback")) {
        injected = true;
        failedPost = true;
        candidate = fs.readFileSync(target);
        if (scenario === "external-bytes") fs.writeFileSync(target, foreign);
        if (scenario === "external-permissions") fs.chmodSync(target, 0o640);
        throw new Error("fixture post-receipt failure");
      }
      await real.rename(from, to);
      if (String(to) === target) written = true;
    },
    readFile: async (...args: Parameters<typeof real.readFile>) => {
      if (scenario.startsWith("readback") && written && !injected && String(args[0]) === target) {
        injected = true;
        throw new Error("fixture readback failure");
      }
      return real.readFile(...args);
    },
    open: async (...args: Parameters<typeof real.open>) => {
      const handle = await real.open(...args);
      if (failedPost && String(args[0]).startsWith(target + ".") && String(args[0]).endsWith(".tmp")) rollbackTemporary = true;
      return handle;
    },
    lstat: async (...args: Parameters<typeof real.lstat>) => {
      const stat = await real.lstat(...args);
      if (scenario === "rollback-race" && rollbackTemporary && !raced && String(args[0]) === target) {
        raced = true;
        fs.writeFileSync(target, foreign);
      }
      return stat;
    },
  };
  // Each case owns a child process. Patch the namespace object in place so
  // already-loaded modules with live binding imports see the same functions.
  Object.assign(fs.promises, patched);
  const { createConsolidationRun, releaseConsolidationRun } = await import("../extensions/consolidation-run.ts");
  const { applyHarnessConsolidationPlan, applyHarnessOps } = await import("../extensions/harness-consolidation.ts");
  const { checkPendingLearningMutations, listLearningHistory } = await import("../extensions/learning-history.ts");
  const quote = "Block dangerous-fixture; use the safe fixture.";
  const operations = [{ op: "addRule" as const, rule: { id: "learned", bash: "^dangerous-fixture$", action: "block", message: "Use the safe fixture." },
    cases: { positive: [{ bash: "dangerous-fixture", expected: "block" as const }], negative: [{ bash: "safe-fixture" }] } }];
  const validationOptions = { automatic: true, snapshot: { entries: [{ message: { role: "user", content: quote } }] },
    evidence: [{ index: 0, source: "user", quote, count: 1 }] };
  const run = await createConsolidationRun({ cwd, sessionManager: { getBranch: () => validationOptions.snapshot.entries } } as never, cwd, false);
  postReceipt = path.join(run.manifest.runDir, "harness-post-receipt.json");
  try {
    const result = scenario === "readback-direct"
      ? await applyHarnessOps(target, operations, validationOptions)
      : await applyHarnessConsolidationPlan({ target, run, durationMs: 0, validationOptions,
          plan: { kind: "harness-consolidation-plan", operations, evidence: validationOptions.evidence } });
    assert.equal(injected, true, JSON.stringify(result));
    assert.equal("ok" in result ? result.ok : result.outcome === "applied", false);
    assert.equal(fs.existsSync(postReceipt), false);
    const preserve = scenario.startsWith("external") || scenario === "rollback-race";
    if (scenario === "rollback-race") assert.equal(raced, true);
    if (preserve) {
      assert.deepEqual(fs.readFileSync(target), scenario === "external-permissions" ? candidate : Buffer.from(foreign));
      assert.equal(fs.statSync(target).mode & 0o777, scenario === "external-permissions" ? 0o640 : 0o600);
      const records = await listLearningHistory(cwd);
      assert.equal(records.length, 1);
      assert.equal(records[0]!.status, "pending");
      await releaseConsolidationRun(run);
      await assert.rejects(checkPendingLearningMutations(cwd), /Unfinished learning/);
    } else {
      if (mode === null) assert.equal(fs.existsSync(target), false);
      else { assert.equal(fs.readFileSync(target, "utf8"), before); assert.equal(fs.statSync(target).mode & 0o777, mode); }
      assert.deepEqual(await listLearningHistory(cwd), []);
      await releaseConsolidationRun(run);
      await checkPendingLearningMutations(cwd);
    }
  } finally {
    mock.restore();
    await releaseConsolidationRun(run);
    fs.rmSync(root, { recursive: true, force: true });
  }
}

if (process.argv.includes("--fixture")) await fixture(process.argv.find(argument => scenarios.includes(argument))!);
else for (const scenario of scenarios) test(`Harness rollback preserves ownership: ${scenario}`, () => {
  const result = spawnSync("bun", [fileURLToPath(import.meta.url), "--", "--fixture", scenario], {
    cwd: fileURLToPath(new URL("../../../", import.meta.url)), encoding: "utf8", timeout: 30000,
    env: { PATH: process.env.PATH, PI_OFFLINE: "1" }, maxBuffer: 4 * 1024 * 1024,
  });
  assert.equal(result.status, 0, result.stderr + result.stdout);
});
