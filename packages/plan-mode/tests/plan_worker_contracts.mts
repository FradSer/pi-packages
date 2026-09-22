import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runPlanWorker } from "../src/plan-worker.ts";

const root = mkdtempSync(join(tmpdir(), "plan-worker-contract-"));
const originalArgv = process.argv[1];
try {
  writeFileSync(join(root, "package.json"), JSON.stringify({ name: "@earendil-works/pi-coding-agent" }));
  const cli = join(root, "cli.cjs"), capture = join(root, "writer-prompt"), planPath = join(root, "plan.md");
  writeFileSync(cli, `const fs = require("node:fs");
const args = process.argv.slice(2), prompt = args.at(-1);
if (!args.includes("-ne") || args[args.indexOf("--tools") + 1] !== "read,grep,find,ls") process.exit(8);
if (prompt.startsWith("# Explore Worker") && prompt.includes("FAIL_RESEARCH")) { console.error("provider rejected research"); process.exit(7); }
if (prompt.startsWith("# Explore Worker") && prompt.includes("EMPTY_RESEARCH")) process.exit(0);
if (prompt.startsWith("# Plan Writer")) fs.writeFileSync(${JSON.stringify(capture)}, prompt);
console.log(JSON.stringify({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: prompt.startsWith("# Plan Writer") ? "# Final plan" : "Verified findings" }] } }));
`);
  process.argv[1] = cli;
  const options = { prompt: "inspect the project", cwd: root, planPath };
  // A failed research result still informs the writer when another task succeeds.
  const partial = await runPlanWorker({ ...options, exploreTasks: [
    { focus: "working", instructions: "inspect" }, { focus: "missing", instructions: "FAIL_RESEARCH" },
  ] });
  assert.equal(partial.exitCode, 0);
  assert.equal(partial.exploreResults[0].diagnostics, "");
  assert.equal(partial.exploreResults[1].status, "failed");
  assert.equal(partial.exploreResults[1].exitCode, 7);
  assert.match(readFileSync(capture, "utf8"), /missing \[failed\]/);
  assert.match(readFileSync(capture, "utf8"), /provider rejected research/);
  assert.equal(readFileSync(planPath, "utf8"), "# Final plan\n");
  for (const instructions of ["FAIL_RESEARCH", "EMPTY_RESEARCH"]) {
    writeFileSync(planPath, "# Previous plan\n");
    const failed = await runPlanWorker({ ...options, exploreTasks: [{ focus: "missing", instructions }] });
    assert.notEqual(failed.exitCode, 0);
    assert.match(failed.stderr, /All explore workers failed/);
    assert.match(failed.exploreResults[0].diagnostics, instructions === "FAIL_RESEARCH" ? /provider rejected research/ : /no structured result/);
    assert.equal(readFileSync(planPath, "utf8"), "# Previous plan\n");
  }
} finally {
  process.argv[1] = originalArgv;
  rmSync(root, { recursive: true, force: true });
}
