from __future__ import annotations

from test_e2e_package import PREAMBLE, REPO, SRC, run_typescript


def test_inline_fulfilled_evidence_cannot_clear_checkpoint() -> None:
    result = run_typescript(PREAMBLE + r'''
      import { mkdtemp, writeFile, rm } from "node:fs/promises";
      import { tmpdir } from "node:os";
      import path from "node:path";
      const cwd = await mkdtemp(path.join(tmpdir(), "pi-e2e-provenance-"));
      try {
        await writeFile(path.join(cwd, "test.feature"), "Feature: Test\nScenario: Works\nThen value is true\n");
        const gate = new E2EGate();
        gate.recordToolResult("write", {path: "test.feature"}, false, cwd);
        const result = await executeE2EVerify({feature: "test.feature", offline: true,
          evidence: {run: {observations: {value: true}}, checks: [{clause: 1, path: "value", op: "equals", value: true}]}
        }, (...args) => gate.recordVerdict(...args), {cwd});
        const checkpoint = gate.checkBeforeSettle({outcome: "completed", entries: [], context: {pendingMessages: []}} as never, {} as never);
        out({status: result.details?.status, continues: checkpoint?.continue ?? false, verified: result.details?.verifiedRun ?? false});
      } finally { await rm(cwd, {recursive: true, force: true}); }
    ''')
    assert result == {"status": "fulfilled", "continues": True, "verified": False}


def test_failed_verdict_keeps_changed_feature_directions() -> None:
    result = run_typescript(PREAMBLE + r'''
      const gate = new E2EGate();
      gate.recordToolResult("write", {path: "changed.feature"});
      gate.recordVerdict({feature: "Test", scenario: "Fails", status: "needs_review", exitCode: 2,
        reason: "missing evidence", clauses: [], unjudged: 1, triage: [], policy: {clauseGate: .8, verdictGate: .6}});
      const checkpoint = gate.checkBeforeSettle({outcome: "completed", entries: [], context: {pendingMessages: []}} as never, {} as never);
      const text = String(checkpoint?.entries[0]?.content);
      out({directions: ["changed.feature", "Inspect the current project instructions", "package scripts", "test setup", "existing E2E tests", "missing evidence"].every(s => text.includes(s)), count: checkpoint?.entries.length});
    ''')
    assert result == {"directions": True, "count": 1}


RUN_PREAMBLE = PREAMBLE + r'''
import { mkdtemp, mkdir, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
const cwd = await mkdtemp(path.join(tmpdir(), "pi-e2e-run-tests-"));
const source = "Feature: Test\nScenario: Works\nThen value is true\n";
await writeFile(path.join(cwd, "test.feature"), source);
const fixture = path.resolve("packages/e2e/tests/run-fixture.mjs");
await mkdir(path.join(cwd, ".e2e"));
await writeFile(path.join(cwd, ".e2e/runner.json"), JSON.stringify({executable: process.execPath, args: [fixture, "pass"], adapterFiles: [fixture]}));
const event = {outcome: "completed", entries: [], context: {pendingMessages: []}};
const pending = (gate) => gate.checkBeforeSettle(event as never, {} as never)?.continue ?? false;
const run = async (mode = "pass", extra = {}, gate = new E2EGate(), options = {}) => {
 await writeFile(path.join(cwd, ".e2e/runner.json"), JSON.stringify({executable: process.execPath, args: [fixture, mode], adapterFiles: [fixture]}));
 return executeE2EVerify({
  feature: "test.feature", offline: true, runner: {executable: process.execPath, args: [fixture, mode], ...extra}
}, gate.verdictListener(), {cwd, ...options});
};
'''


def test_real_http_run_clears_only_matching_fulfilled_scenarios() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        const gate = new E2EGate();
        await gate.beginTurn("verify", cwd);
        await writeFile(path.join(cwd, "test.feature"), source + "Scenario: Also works\nThen value is true\n");
        const first = await run("pass", {}, gate);
        const partial = pending(gate);
        const second = await executeE2EVerify({feature: "test.feature", scenario: "Also works", offline: true,
          runner: {executable: process.execPath, args: [fixture, "pass"]}}, gate.verdictListener(), {cwd});
        await gate.refreshFeatureChanges(cwd);
        out({first: first.details?.verifiedRun, partial, second: second.details?.verifiedRun, cleared: !pending(gate)});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert result == {"first": True, "partial": True, "second": True, "cleared": True}


def test_rejected_real_runs_never_clear_and_cleanup_private_artifacts() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      import { readdir } from "node:fs/promises";
      const before = new Set(await readdir(tmpdir()));
      try {
        const results = [];
        for (const mode of ["fail", "missing", "malformed", "large", "symlink", "modify", "output", "hang", "unmet"]) {
          await writeFile(path.join(cwd, "test.feature"), source);
          const gate = new E2EGate();
          gate.recordToolResult("write", {path: "test.feature"}, false, cwd);
          const result = await run(mode, {timeoutMs: mode === "hang" ? 50 : 4000}, gate);
          results.push({mode, error: result.isError, pending: pending(gate), status: result.details?.status});
        }
        out({results, leaked: (await readdir(tmpdir())).filter(name => name.startsWith("pi-e2e-run-") && !before.has(name))});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert result["leaked"] == []
    for item in result["results"]:
        assert item["error"] is True, item
        assert item["pending"] is True, item
    assert result["results"][-1]["status"] == "not_fulfilled"


def test_abort_kills_test_process_tree_after_lifecycle_marker() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      import { watch } from "node:fs";
      try {
        const controller = new AbortController();
        const watcher = watch(cwd);
        const ready = new Promise<void>(resolve => watcher.on("change", (_event, name) => {
          if (name === "child.pid") resolve();
        }));
        const gate = new E2EGate();
        gate.recordToolResult("write", {path: "test.feature"}, false, cwd);
        const resultPromise = run("tree", {timeoutMs: 4000}, gate, {signal: controller.signal});
        await ready;
        controller.abort();
        const result = await resultPromise;
        watcher.close();
        const pid = Number(await readFile(path.join(cwd, "child.pid"), "utf8"));
        if (!Number.isSafeInteger(pid) || pid <= 0) throw new Error("Invalid lifecycle PID marker");
        let alive = true;
        try {process.kill(pid, 0);} catch {alive = false;}
        // Linux can retain a killed orphan as a zombie until init reaps it.
        // It has exited and holds no runtime resources; kill(pid, 0) alone
        // cannot distinguish it from a process still executing after abort.
        if (alive && process.platform === "linux") {
          try {alive = !/^\d+ \([\s\S]*\) Z /.test(await readFile(`/proc/${pid}/stat`, "utf8"));}
          catch (error) {if (error.code === "ENOENT") alive = false; else throw error;}
        }
        out({error: result.isError, pending: pending(gate), alive});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert result == {"error": True, "pending": True, "alive": False}


def test_stale_turn_callbacks_and_post_run_mutations_cannot_clear() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        const stale = new E2EGate();
        stale.recordToolResult("write", {path: "test.feature"}, false, cwd);
        const listener = stale.verdictListener();
        stale.recordUserPrompt("Now run e2e tests again");
        stale.recordToolResult("write", {path: "test.feature"}, false, cwd);
        const result = await executeE2EVerify({feature: "test.feature", offline: true,
          runner: {executable: process.execPath, args: [fixture, "pass"]}}, listener, {cwd});
        const fresh = new E2EGate();
        await fresh.beginTurn("verify", cwd);
        fresh.recordToolResult("write", {path: "test.feature"}, false, cwd);
        await run("pass", {}, fresh);
        const cleared = !pending(fresh);
        fresh.recordToolResult("bash", {command: "update implementation"}, true, cwd);
        out({verified: result.details?.verifiedRun, stalePending: pending(stale), cleared, reopened: pending(fresh)});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert result == {"verified": True, "stalePending": True, "cleared": True, "reopened": True}


def test_unrelated_success_and_unproven_retry_do_not_hide_failed_verdict() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        const gate = new E2EGate();
        await run("unmet", {}, gate);
        await writeFile(path.join(cwd, "other.feature"), "Feature: Other\nScenario: Other\nThen value is true\n");
        await executeE2EVerify({feature: "other.feature", offline: true, runner: {executable: process.execPath, args: [fixture, "pass"]}}, gate.verdictListener(), {cwd});
        await executeE2EVerify({feature: "test.feature", offline: true, evidence: {
          run: {observations: {value: true}}, checks: [{clause: 1, path: "value", op: "equals", value: true}]
        }}, gate.verdictListener(), {cwd});
        const checkpoint = gate.checkBeforeSettle(event as never, {} as never);
        out({failed: String(checkpoint?.entries[0]?.content).includes("not_fulfilled")});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert result == {"failed": True}


def test_turn_start_configuration_survives_a_concurrent_generation_bump() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      import { runnerSnapshot } from "''' + (SRC / "run.ts").as_uri() + r'''";
      try {
        const gate = new E2EGate();
        const pendingTurn = gate.beginTurn("verify", cwd);
        gate.recordToolResult("write", {path: "test.feature"}, false, cwd);
        await pendingTurn;
        const observer = gate.verificationObserver();
        let error = null;
        try { observer.validateRunner(await runnerSnapshot(cwd)); } catch (caught) { error = String(caught); }
        out({error, pending: pending(gate)});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert result["error"] is None, result


def test_runner_drift_within_attempt_names_the_changed_adapter_file() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      import { runnerSnapshot } from "''' + (SRC / "run.ts").as_uri() + r'''";
      try {
        const adapter = path.join(cwd, "adapter.mjs");
        await writeFile(adapter, "process.exit(0)");
        await writeFile(path.join(cwd, ".e2e/runner.json"), JSON.stringify({executable: process.execPath, args: [adapter], adapterFiles: [adapter]}));
        const gate = new E2EGate();
        await gate.beginTurn("verify", cwd);
        const {writeFileSync} = await import("node:fs");
        const result = await executeE2EVerify({feature:"test.feature",runner:{executable:process.execPath,args:[adapter]},offline:true}, undefined, {
          cwd, validateRunner() {writeFileSync(adapter,"process.exit(0); // changed within attempt");}
        });
        const message = result.details.error;
        out({namesAdapter: message.includes("adapter.mjs"), message});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert result["namesAdapter"] is True, result


def test_command_substitution_is_refused_but_reconfigured_adapter_can_run() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        const gate = new E2EGate();
        await gate.beginTurn("verify", cwd);
        gate.recordToolResult("write", {path: "test.feature"}, false, cwd);
        const replacement = await executeE2EVerify({feature: "test.feature", offline: true,
          runner: {executable: process.execPath, args: ["-e", "console.log('fabricated')"]}}, gate.verdictListener(), {cwd});
        await writeFile(path.join(cwd, ".e2e/runner.json"), JSON.stringify({executable: process.execPath, args: [fixture], adapterFiles: [fixture]}));
        const changed = await executeE2EVerify({feature: "test.feature", offline: true,
          runner: {executable: process.execPath, args: [fixture]}}, gate.verdictListener(), {cwd});
        out({replacementError: replacement.isError, changedFulfilled: changed.details?.status, pending: pending(gate)});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert result == {"replacementError": True, "changedFulfilled": "fulfilled", "pending": False}


def test_duplicate_scenario_names_and_missing_then_are_rejected() -> None:
    result = run_typescript(PREAMBLE + r'''
      const rejected = [];
      for (const source of ["Feature: Test\nScenario: Same\nThen true\nScenario: Same\nThen false\n", "Feature: Test\nScenario: Empty\nGiven nothing\n"]) {
        try { parseFeature(source); rejected.push(false); } catch {rejected.push(true);}
      }
      out({rejected});
    ''')
    assert result == {"rejected": [True, True]}


def test_aborted_deterministic_verification_and_malformed_observations_do_not_pass() -> None:
    result = run_typescript(PREAMBLE + r'''
      const rejected = [];
      const targetScenario = firstScenario(parseFeature("Feature: Test\nScenario: Works\nThen value is true\n"));
      const controller = new AbortController(); controller.abort();
      for (const options of [
        {scenario: targetScenario, signal: controller.signal, evidence: {run: {observations: {value: true}}, checks: [{clause: 1, path: "value", op: "equals", value: true}]}},
        {scenario: targetScenario, evidence: {run: {observations: [true]}, checks: [{clause: 1, path: "0", op: "equals", value: true}]}},
      ]) {
        try {await verifyScenario({...options, offline: true} as never); rejected.push(false);} catch {rejected.push(true);}
      }
      out({rejected});
    ''')
    assert result == {"rejected": [True, True]}


def test_repaired_adapter_executes_fresh_tests_in_the_same_turn() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        const adapter = path.join(cwd, "adapter.mjs");
        await writeFile(adapter, "process.exit(1)");
        const configuration = {executable: process.execPath, args: [adapter], adapterFiles: [adapter, fixture]};
        await writeFile(path.join(cwd, ".e2e/runner.json"), JSON.stringify(configuration));
        const gate = new E2EGate();
        await gate.beginTurn("verify", cwd);
        await writeFile(adapter, `await import(${JSON.stringify("file://" + fixture)});`);
        gate.recordToolResult("write", {path: adapter}, false, cwd);
        gate.recordToolResult("write", {path: "test.feature"}, false, cwd);
        const result = await executeE2EVerify({feature: "test.feature", runner: configuration, offline: true}, gate.verdictListener(), {cwd});
        out({status: result.details?.status, pending: pending(gate)});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert result == {"status": "fulfilled", "pending": False}


def test_fifo_evidence_is_rejected_without_blocking() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      import { execFileSync } from "node:child_process";
      try {
        const adapter = path.join(cwd, "fifo.mjs");
        await writeFile(adapter, `import {execFileSync} from 'node:child_process'; execFileSync('mkfifo',[process.env.PI_E2E_EVIDENCE_PATH]);`);
        const configuration = {executable: process.execPath, args: [adapter], adapterFiles: [adapter]};
        await writeFile(path.join(cwd, ".e2e/runner.json"), JSON.stringify(configuration));
        const result = await executeE2EVerify({feature: "test.feature", runner: configuration, offline: true}, undefined, {cwd});
        out({error: result.isError, detail: result.details?.error});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert result["error"] is True
    assert "regular files" in result["detail"]


def test_native_runner_guard_rejects_changes_within_attempt_before_execution() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        const adapter = path.join(cwd, "adapter.mjs");
        await writeFile(adapter, "process.exit(1)");
        const configuration = {executable: process.execPath, args: [adapter], adapterFiles: [adapter]};
        await writeFile(path.join(cwd, ".e2e/runner.json"), JSON.stringify(configuration));
        const gate = new E2EGate(); await gate.beginTurn("verify", cwd);
        const observer = gate.verificationObserver();
        const {writeFileSync} = await import("node:fs");
        const result = await executeE2EVerify({feature: "test.feature", runner: configuration, offline: true}, observer.onVerdict, {cwd, validateRunner(snapshot) {
          observer.validateRunner(snapshot);
          writeFileSync(adapter, `import {writeFileSync} from 'node:fs'; writeFileSync('spawned', 'yes');`);
        }});
        let spawned = false; try {await readFile(path.join(cwd, "spawned")); spawned = true;} catch {}
        out({error: result.isError, spawned});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert result == {"error": True, "spawned": False}


def test_tool_lifecycle_renderer_bounds_long_untrusted_scenario_text() -> None:
    result = run_typescript(PREAMBLE + '\nimport {visibleWidth} from "' + (REPO / "node_modules/@earendil-works/pi-tui/dist/index.js").as_uri() + '";\n' + r'''
      import { registerE2ETools } from "''' + (SRC / "tool.ts").as_uri() + r'''";
      let tool;
      registerE2ETools({registerTool(definition) {tool = definition;}} as never);
      const theme = {fg: (_color, text) => text, bg: (_color, text) => text, bold: text => text};
      const result = {content: [{type: "text", text: "# report\n\nfulfilled"}], details: {status: "fulfilled", scenario: "A very long scenario ".repeat(100)}};
      const collapsed = tool.renderResult(result, {}, theme, {}).render(30);
      out({bounded: collapsed.every(line => visibleWidth(line) <= 30), labeled: collapsed.join("\n").includes("e2e")});
    ''')
    assert result == {"bounded": True, "labeled": True}


def test_external_adapter_mutation_after_a_pass_reopens_feature_checkpoint() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        const adapter = path.join(cwd, "adapter.mjs");
        await writeFile(adapter, `import ${JSON.stringify("file://" + fixture)};`);
        const configuration = {executable: process.execPath, args: [adapter], adapterFiles: [adapter, fixture]};
        await writeFile(path.join(cwd, ".e2e/runner.json"), JSON.stringify(configuration));
        const gate = new E2EGate(); await gate.beginTurn("verify", cwd);
        gate.recordToolResult("write", {path: "test.feature"}, false, cwd);
        const observer = gate.verificationObserver();
        await executeE2EVerify({feature: "test.feature", runner: configuration, offline: true}, observer.onVerdict, {cwd, validateRunner: observer.validateRunner});
        const cleared = !pending(gate);
        await writeFile(adapter, "process.exit(1)");
        await gate.refreshFeatureChanges(cwd);
        out({cleared, reopened: pending(gate)});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert result == {"cleared": True, "reopened": True}


def test_unchanged_feature_requested_run_is_revalidated_after_external_mutation() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        const adapter = path.join(cwd, "adapter.mjs");
        await writeFile(adapter, `import ${JSON.stringify("file://" + fixture)};`);
        const configuration = {executable: process.execPath, args: [adapter], adapterFiles: [adapter, fixture]};
        await writeFile(path.join(cwd, ".e2e/runner.json"), JSON.stringify(configuration));
        const gate = new E2EGate(); gate.recordUserPrompt("Run e2e tests"); await gate.beginTurn("verify", cwd);
        const observer = gate.verificationObserver();
        await executeE2EVerify({feature: "test.feature", runner: configuration, offline: true}, observer.onVerdict, {cwd, validateRunner: observer.validateRunner});
        const cleared = !pending(gate);
        await writeFile(adapter, "process.exit(1)");
        await gate.refreshFeatureChanges(cwd);
        out({cleared, reopened: pending(gate)});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert result == {"cleared": True, "reopened": True}


def test_stale_guard_after_async_preparation_prevents_child_spawn() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        const adapter = path.join(cwd, "adapter.mjs");
        await writeFile(adapter, `import {writeFileSync} from 'node:fs'; writeFileSync('spawned','yes'); await import(${JSON.stringify("file://" + fixture)});`);
        const configuration = {executable: process.execPath, args: [adapter], adapterFiles: [adapter, fixture]};
        await writeFile(path.join(cwd, ".e2e/runner.json"), JSON.stringify(configuration));
        let active = true;
        const result = await executeE2EVerify({feature: "test.feature", runner: configuration, offline: true}, undefined, {
          cwd, validateRunner: () => {
            if (!active) throw new Error("Turn is stale");
            queueMicrotask(() => {active = false;});
          },
        });
        let spawned = false; try {await readFile(path.join(cwd, "spawned")); spawned = true;} catch {}
        out({error: result.isError, spawned});
      } finally {await rm(cwd, {recursive: true, force: true});}
    ''')
    assert result == {"error": True, "spawned": False}


def test_non_error_abort_reason_returns_a_tool_error_without_rejection() -> None:
    result = run_typescript(PREAMBLE + r'''
      let rejected = false; let result;
      try {
        result = await executeE2EVerify({feature: "packages/e2e/examples/billing.feature", evidence, offline: true}, undefined, {signal: AbortSignal.abort(null)});
      } catch {rejected = true;}
      out({rejected, error: result?.isError ?? false});
    ''')
    assert result == {"rejected": False, "error": True}


def test_runner_exit_error_preserves_bounded_diagnostic() -> None:
    result=run_typescript(RUN_PREAMBLE+r'''
      try {
        const adapter=path.join(cwd,"diagnostic.mjs");
        await writeFile(adapter,'console.error("RUNNER_DIAGNOSTIC_TAIL");process.exit(1);');
        const runner={executable:process.execPath,args:[adapter]};
        await writeFile(path.join(cwd,".e2e/runner.json"),JSON.stringify({...runner,adapterFiles:[adapter]}));
        const result=await executeE2EVerify({feature:"test.feature",offline:true,runner},undefined,{cwd});
        out({error:String(result.details?.error),status:result.details?.status,verified:result.details?.verifiedRun??false});
      } finally {await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result["status"] == "error" and result["verified"] is False
    assert "Test runner exited with 1" in result["error"]
    assert "RUNNER_DIAGNOSTIC_TAIL" in result["error"]
