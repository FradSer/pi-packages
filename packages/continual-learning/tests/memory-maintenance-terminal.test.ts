import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {spawnSync} from "node:child_process";
import {fileURLToPath} from "node:url";
import {test} from "node:test";

const kinds = ["model-error", "cancelled", "process-exit", "spawn-error", "stdout-limit", "jsonl-line-limit", "stderr-limit", "prompt-delivery-error"];
async function fixture() {
  const {mock} = await import("bun:test");
  const root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), "memory-audit-terminal-")));
  const cwd = path.join(root, "project");await fs.mkdir(cwd);await fs.writeFile(path.join(cwd, "runtime.js"), "export const value = 1;\n");
  const kit = await import("../../kit/src/index.ts");
  let result: any;
  let workerCalls = 0;
  mock.module("../../kit/src/index.ts", () => ({...kit, runPiWorker: async () => { workerCalls++; return result; }}));
  const {auditMemoryMaintenanceSources} = await import("../extensions/memory-maintenance-audit.ts");
  const rows: any[] = [];
  try {
    const settled = await auditMemoryMaintenanceSources({
      cwd, request: "Inspect settled edits", memoryFiles: [], outputDir: root,
      purpose: "settled-task", replayPaths: ["runtime.js"],
    });
    const settledReceipt = JSON.parse(await fs.readFile(path.join(settled.directory, "receipt.json"), "utf8"));
    const settledWorkerCalls = workerCalls;
    await settled.assertSourcesUnchanged();
    const variants = [...kinds.map((kind, index) => ({kind, nativeExitCode: index === 0 ? 0 : index, discarded: "PRIVATE-CONTENT"})),
      {kind: "model-error", nativeExitCode: Infinity}, {kind: "model-error", nativeExitCode: 1.5},
      {kind: "model-error", nativeExitCode: "7"}, {kind: "model-error", nativeExitCode: null},
      {kind: "PRIVATE-CONTENT", nativeExitCode: 7}, null];
    for (const terminal of variants) {
      result = {exitCode: 1, text: "PRIVATE-CONTENT", stderr: "PRIVATE-CONTENT", terminal,
        cancelled: terminal?.kind === "cancelled", usageLedger: {knownUsage: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: 0}, assistantMessages: 1, complete: false}};
      const audit = await auditMemoryMaintenanceSources({cwd, request: "整理记忆", memoryFiles: [], outputDir: root});
      const receipt = JSON.parse(await fs.readFile(path.join(audit.directory, "receipt.json"), "utf8"));
      rows.push({receipt, returned: {outcome: audit.outcome, workerOutcome: audit.workerOutcome,
        workerTerminal: (audit as any).workerTerminal, entries: audit.entries, usageComplete: audit.usageComplete}});
    }
    process.stdout.write(JSON.stringify({rows, settled: {outcome: settled.outcome, entries: settled.entries, receipt: settledReceipt, workerCalls: settledWorkerCalls}}));
  } finally {await fs.rm(root, {recursive: true, force: true});}
}

if (process.argv.includes("--fixture")) await fixture();
else {
  let payload: {rows: any[]; settled: any} | undefined;
  const observed = () => {
    if (payload) return payload;
    const result = spawnSync("bun", [fileURLToPath(import.meta.url), "--fixture"], {
      cwd: fileURLToPath(new URL("../../../..", import.meta.url)), encoding: "utf8", timeout: 30_000,
      env: {...process.env, TYPESAFE_API_KEY: ""}, maxBuffer: 4 * 1024 * 1024,
    });
    assert.equal(result.status, 0, result.stderr);
    payload = JSON.parse(result.stdout);return payload!;
  };
  test("settled-task source audit reads edited files directly in parent with zero LLM worker calls", () => {
    const {settled} = observed();
    assert.equal(settled.workerCalls, 0);
    assert.equal(settled.outcome, "observed");
    assert.equal(settled.receipt.modelCalls, 0);
    assert.equal(settled.receipt.sourceEvidenceStatus, "verified-observations");
    assert.equal(settled.entries.length, 2);
    assert.match(JSON.stringify(settled.entries), /export const value = 1;/);
  });
  test("failed source audits retain the existing safe worker terminal category in receipt and return", () => {
    for (const [index, kind] of kinds.entries()) {
      const row = observed().rows[index], expected = {kind, nativeExitCode: index === 0 ? 0 : index};
      assert.deepEqual(row.receipt.workerTerminal, expected);
      assert.deepEqual(row.returned.workerTerminal, expected);
      assert.equal(row.receipt.operations, undefined);
      assert.equal(row.receipt.mutationAuthorized, false);
      assert.equal(row.returned.entries.length, 0);
      assert.equal(row.returned.usageComplete, false);
      assert.equal(row.returned.outcome, kind === "cancelled" ? "cancelled" : "failed");
    }
  });
  test("audit terminal retention admits only integer native exits and known categories", () => {
    const values = observed().rows;
    for (const row of values.slice(8, 12)) assert.deepEqual(row.receipt.workerTerminal, {kind: "model-error", nativeExitCode: null});
    for (const row of values.slice(12)) {
      assert.equal(row.receipt.workerTerminal, undefined);
      assert.equal(row.returned.workerTerminal, undefined);
    }
    assert.equal(JSON.stringify(values).includes("PRIVATE-CONTENT"), false);
  });
}
