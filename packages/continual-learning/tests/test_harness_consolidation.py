from __future__ import annotations

import json
from pathlib import Path

import pytest

from support import PKG_DIR, PKG_REL, run_bun


def validate(plan: dict) -> list[str]:
    return run_bun(f"import {{validateHarnessPlan}} from './{PKG_REL}/extensions/harness-consolidation.ts';console.log(JSON.stringify(validateHarnessPlan({json.dumps(plan)})));")


def test_harness_result_example_copies_the_current_parent_identity() -> None:
    result = run_bun(r"""
      import {buildHarnessConsolidatorPrompt} from './packages/continual-learning/extensions/planner-prompts.ts';
      const bindings={runId:'run_current',scopeDigest:'a'.repeat(64),artifactHash:'b'.repeat(64),snapshotPath:'/fixture/snapshot.json',dossierPath:'/fixture/older-selector/dossier.json',repoRoot:'/fixture'};
      const prompt=buildHarnessConsolidatorPrompt(bindings);
      const example=JSON.parse(/```json\n([\s\S]*?)\n```/.exec(prompt)[1]);
      console.log(JSON.stringify({runId:example.runId,scopeDigest:example.scopeDigest,artifactHash:example.artifactHash}));
    """)
    assert result == {"runId": "run_current", "scopeDigest": "a" * 64, "artifactHash": "b" * 64}


def validate_against_snapshot(plan: dict, snapshot: dict, **context: object) -> list[str]:
    return run_bun(f"import {{validateHarnessPlan}} from './{PKG_REL}/extensions/harness-consolidation.ts';console.log(JSON.stringify(validateHarnessPlan({json.dumps(plan)},{json.dumps({'snapshot':snapshot,**context})})));")


def valid_plan() -> dict:
    return {"kind":"harness-consolidation-plan","version":1,"schemaVersion":1,
        "operations":[{"op":"addRule","rule":rule(f"rule-{i}"),"cases":cases()} for i in range(3)],
        "evidence":[{"index":i,"observation":"observed fixture constraint","count":1} for i in range(3)]}


def test_valid_plan_with_operations_passes() -> None:
    assert validate(valid_plan()) == []


def test_empty_and_missing_operations_are_verified_noops() -> None:
    assert validate({"kind":"harness-consolidation-plan"}) == []
    assert validate({"kind":"harness-consolidation-plan","operations":[]}) == []


@pytest.mark.parametrize('mutate, expected', [
    ({'kind':'other'}, 'kind'), ({'operations':[{'op':'addRule','rule':{'id':'x'}}]*13}, 'maximum'),
    ({'operations':[{'op':'addPolicy'}]}, 'op must be one of'),
    ({'operations':[{'op':'addRule','rule':{'id':'big','bash':'x','message':'x'*9000}}]}, '8192 bytes'),
    ({'operations':[{'op':'addRule','rule':{'id':'legacy','scope':{},'rule':'x'}}]}, 'unsupported field'),
])
def test_shape_bounds_and_legacy_operations_fail_closed(mutate: dict, expected: str) -> None:
    assert any(expected in error for error in validate(valid_plan() | mutate))


def evidence_snapshot() -> dict:
    return {
        "entries": [
            {
                "type": "message_end",
                "message": {
                    "role": "user",
                    "content": "Please keep blocking hard-coded widths in writes.",
                },
            },
            {
                "type": "tool_execution_end",
                "toolName": "write",
                "result": "blocked by ui-width policy; use design tokens",
                "isError": True,
            },
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": "The model speculates that all writes should be blocked.",
                },
            },
        ]
    }


def rule(name: str = "learned-width", action: str = "block") -> dict:
    return {"id": name, "bash": "^publish-fixture$", "action": action, "message": "Use the safe fixture."}


def cases(action: str = "block") -> dict:
    return {"positive": [{"bash": "publish-fixture", "expected": action}], "negative": [{"bash": "safe-fixture"}]}


def grounded_plan(op: dict, *, source: str = "tool", quote: str = "blocked by ui-width policy; use design tokens") -> dict:
    return {
        "kind": "harness-consolidation-plan",
        "version": 1,
        "schemaVersion": 1,
        "operations": [op],
        "evidence": [
            {
                "index": 0,
                "quote": quote,
                "source": source,
                "observation": quote,
                "count": 1,
            }
        ],
    }


def test_evidence_requires_verbatim_snapshot_quote_and_observed_actor() -> None:
    plan = grounded_plan({"op": "addRule", "rule": rule(), "cases": cases()})
    assert validate_against_snapshot(plan, evidence_snapshot()) == []

    invented = grounded_plan(
        {"op": "addRule", "rule": rule("invented"), "cases": cases()},
        source="user",
        quote="The user prefers a universal write prohibition.",
    )
    errors = validate_against_snapshot(invented, evidence_snapshot())
    assert any("quote" in error and "snapshot" in error for error in errors)

    model_quote = grounded_plan(
        {"op": "addRule", "rule": rule("model-only"), "cases": cases()},
        source="model",
        quote="The model speculates that all writes should be blocked.",
    )
    errors = validate_against_snapshot(model_quote, evidence_snapshot())
    assert any("source" in error and "user" in error and "tool" in error for error in errors)


def test_evidence_matches_actual_content_leaves_and_distinct_events() -> None:
    multiline = 'First line\nquoted "width: 480px" with a \\ slash.'
    snapshot = {
        "entries": [
            {"type": "message_end", "message": {"role": "user", "content": multiline}},
            {"type": "tool_execution_end", "toolName": "write", "result": "blocked once"},
            {"type": "tool_execution_end", "toolName": "write", "result": "blocked once"},
            {"type": "tool_execution_end", "toolName": "write", "policyName": "metadata-only", "result": "ordinary outcome"},
            {"type": "message_end", "message": {"role": "assistant", "content": "assistant-only claim"}},
        ]
    }
    user_plan = grounded_plan(
        {"op": "addRule", "rule": rule("multiline"), "cases": cases()},
        source="user",
        quote=multiline,
    )
    assert validate_against_snapshot(user_plan, snapshot) == []

    two_events = grounded_plan(
        {"op": "addRule", "rule": rule("two-events"), "cases": cases()},
        source="tool",
        quote="blocked once",
    )
    two_events["evidence"][0]["count"] = 2
    assert validate_against_snapshot(two_events, snapshot) == []

    repeated_in_one_event = grounded_plan(
        {"op": "addRule", "rule": rule("one-event"), "cases": cases()},
        source="tool",
        quote="ordinary outcome",
    )
    repeated_in_one_event["evidence"][0]["count"] = 2
    errors = validate_against_snapshot(repeated_in_one_event, snapshot)
    assert any("count exceeds" in error for error in errors)

    metadata = grounded_plan(
        {"op": "addRule", "rule": rule("metadata"), "cases": cases()},
        source="tool",
        quote="metadata-only",
    )
    errors = validate_against_snapshot(metadata, snapshot)
    assert any("not grounded" in error for error in errors)

    assistant = grounded_plan(
        {"op": "addRule", "rule": rule("assistant"), "cases": cases()},
        source="user",
        quote="assistant-only claim",
    )
    errors = validate_against_snapshot(assistant, snapshot)
    assert any("not grounded" in error for error in errors)


def test_sdk_tool_result_message_content_is_tool_evidence() -> None:
    snapshot = {
        "entries": [
            {
                "type": "message",
                "message": {
                    "role": "toolResult",
                    "toolName": "write",
                    "content": [{"type": "text", "text": "blocked by sdk policy"}],
                },
                "policyName": "metadata-only",
            },
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "assistant-only tool claim"}],
                },
            },
        ]
    }
    accepted = grounded_plan(
        {"op": "addRule", "rule": rule("sdk-tool-result"), "cases": cases()},
        source="tool",
        quote="blocked by sdk policy",
    )
    assert validate_against_snapshot(accepted, snapshot) == []

    metadata = grounded_plan(
        {"op": "addRule", "rule": rule("sdk-metadata"), "cases": cases()},
        source="tool",
        quote="write",
    )
    errors = validate_against_snapshot(metadata, snapshot)
    assert any("not grounded" in error for error in errors)

    assistant = grounded_plan(
        {"op": "addRule", "rule": rule("sdk-assistant"), "cases": cases()},
        source="tool",
        quote="assistant-only tool claim",
    )
    errors = validate_against_snapshot(assistant, snapshot)
    assert any("not grounded" in error for error in errors)


def test_policy_add_and_update_require_passing_positive_and_negative_evaluator_cases() -> None:
    base = {"op": "addRule", "rule": rule()}
    missing = validate_against_snapshot(grounded_plan(base), evidence_snapshot())
    assert any("positive" in error and "negative" in error for error in missing)

    bad_cases = cases()
    bad_cases["negative"][0]["bash"] = "publish-fixture"
    errors = validate_against_snapshot(
        grounded_plan({**base, "cases": bad_cases}), evidence_snapshot()
    )
    assert any("negative" in error and ("match" in error or "unmatched" in error) for error in errors)

    valid = validate_against_snapshot(
        grounded_plan({**base, "cases": cases()}), evidence_snapshot()
    )
    assert valid == []



# ── wiring contracts (source assertions per repo test style) ──────────


def test_command_registered_as_harness_not_guardrails() -> None:
    src = (PKG_DIR / "extensions" / "guardrails.ts").read_text(encoding="utf-8")
    assert 'pi.registerCommand("harness"' in src
    assert 'pi.registerCommand("guardrails"' not in src
    assert "harness confirmation:" in src


def test_consolidate_pipeline_gates_harness_phase() -> None:
    src = (PKG_DIR / "extensions" / "inject-memory.ts").read_text(encoding="utf-8")
    assert 'planHarnessConsolidationPhase, shouldRunHarnessPhase' in src
    assert "applyHarnessConsolidationPlan" in src
    assert 'shouldRunHarnessPhase(state, opts.noContext)' in src
    assert 'gate !== "run"' in src
    assert 'if (opts.noContext)' in src
    assert 'await writeCurrentReceipt()' in src
    assert "await startConsolidationPipeline(ctx, dreamState," in src
    assert "selectedScope: incrementalSelection?.selection?.selected" in src
    assert "dossierPath: incrementalSelection?.dossierPath" in src
    assert "Promise.all([harnessPromise, agentsPromise])" in src
    assert "exploreLearningContext" not in src


def test_incremental_harness_task_uses_authoritative_dossier_without_broad_discovery(tmp_path: Path) -> None:
    result = run_bun(rf'''
      process.env.PI_CODING_AGENT_DIR = {json.dumps(str(tmp_path / 'agent'))};
      import {{ mock }} from 'bun:test';
      import fs from 'node:fs';
      import path from 'node:path';
      import {{ EventEmitter }} from 'node:events';
      const tasks = [];
      const kit = await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts', () => ({{
        ...kit,
        spawnPiChild: (_command, args) => {{
          const taskFile = args.find(arg => arg.startsWith('@')).slice(1);
          tasks.push(fs.readFileSync(taskFile, 'utf8'));
          const manifest = JSON.parse(fs.readFileSync(path.join(path.dirname(taskFile), 'manifest.json'), 'utf8'));
          const plan = {{ kind: 'harness-consolidation-plan', version: 1, schemaVersion: 1, runId: manifest.runId, scopeDigest: manifest.scopeDigest, artifactHash: manifest.snapshotDigest, operations: [], evidence: [], report: [] }};
          const child = new EventEmitter(); child.stdout = new EventEmitter(); child.stderr = new EventEmitter(); child.exitCode = null; child.signalCode = null;
          queueMicrotask(() => {{ child.stdout.emit('data', Buffer.from(JSON.stringify({{ type: 'message_end', message: {{ role: 'assistant', content: [{{ type: 'text', text: JSON.stringify(plan) }}] }} }}) + '\n')); child.exitCode = 0; child.emit('close', 0); }});
          return child;
        }},
      }}));
      const {{ createConsolidationRun, releaseConsolidationRun }} = await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const {{ planHarnessConsolidationPhase }} = await import('./packages/continual-learning/extensions/harness-consolidation.ts');
      const cwd = {json.dumps(str(tmp_path))};
      const entries = [{{ message: {{ role: 'user', content: 'Never write generated files.' }} }}];
      const ctx = {{ cwd, ui: {{ notify() {{}} }}, sessionManager: {{ getBranch: () => entries, buildContextEntries: () => entries }} }};
      const run = await createConsolidationRun(ctx, cwd, false);
      const dossier = path.join(run.manifest.runDir, 'incremental-learning-dossier.json'); fs.writeFileSync(dossier, '{{}}\n');
      const outcome = await planHarnessConsolidationPhase(ctx, {{ pkgDir: process.cwd(), cwd, reason: 'incremental', run, explorationPath: dossier, explorationDigest: 'dossier-digest', resolveCli: () => ({{ command: process.execPath, args: [] }}) }});
      await releaseConsolidationRun(run);
      console.log(JSON.stringify({{ ok: outcome.ok, task: tasks[0], runDir: run.manifest.runDir }}));
    ''')
    assert Path(result["runDir"]).is_relative_to(tmp_path / "agent")
    assert result["ok"] is True
    assert "Authoritative Learning Dossier" in result["task"]
    assert "immutable task-slice snapshot" in result["task"]
    assert "do not perform independent repository-wide exploration" in result["task"]


def test_plan_requires_version_and_schema_version_one() -> None:
    plan = valid_plan()
    errs = validate(plan | {"version": 2})
    assert any("version must be 1" in e for e in errs)
    errs = validate(plan | {"schemaVersion": "x"})
    assert any("schemaVersion must be 1" in e for e in errs)


def test_plan_without_evidence_is_rejected_fail_closed() -> None:
    plan = valid_plan()
    del plan["evidence"]
    errs = validate(plan)
    assert any("evidence must be an array" in e for e in errs)


def test_evidence_must_cover_every_operation_index() -> None:
    plan = valid_plan()
    plan["evidence"] = [e for e in plan["evidence"] if e["index"] != 1]
    errs = validate(plan)
    assert any("operations[1] has no evidence entry" in e for e in errs)


def test_evidence_entries_are_shape_checked() -> None:
    plan = valid_plan()
    plan["evidence"] = [
        {"index": 0, "observation": "ok", "count": 1},
        {"index": 9, "observation": "out of range", "count": 1},
        {"index": 1, "observation": "", "count": 0},
        {"index": 2, "observation": "no count"},
    ]
    errs = validate(plan)
    assert any("out of range" in e for e in errs)
    assert any("observation must be 1..600" in e for e in errs)
    assert any("count must be a positive integer" in e for e in errs)


def test_report_entries_require_bounded_summaries() -> None:
    plan = valid_plan()
    plan["report"] = [{"summary": ""}]
    errs = validate(plan)
    assert any("1..400 char summary" in e for e in errs)

    plan["report"] = [{"summary": "ok"}] * 13
    errs = validate(plan)
    assert any("report exceeds" in e for e in errs)


def test_should_run_harness_phase_decision_table() -> None:
    src = f"""
        import {{ shouldRunHarnessPhase }} from './{PKG_REL}/extensions/harness-consolidation.ts';
        const table = {{
          waitWhileActive: shouldRunHarnessPhase({{ outcome: undefined, active: true, cancelled: false }}),
          waitUntilOutcome: shouldRunHarnessPhase({{ outcome: undefined, active: false, cancelled: false }}),
          cancelledStaysWaiting: shouldRunHarnessPhase({{ outcome: "failed", active: false, cancelled: true }}),
          failedSkips: shouldRunHarnessPhase({{ outcome: "failed", active: false, cancelled: false }}),
          unverifiedSkips: shouldRunHarnessPhase({{ outcome: "unverified", active: false, cancelled: false }}),
          completedRuns: shouldRunHarnessPhase({{ outcome: "completed", active: false, cancelled: false }}),
          noContextSkipsEvenWhenCompleted: shouldRunHarnessPhase({{ outcome: "completed", active: false, cancelled: false }}, true),
        }};
        console.log(JSON.stringify(table));
    """
    out = run_bun(src)
    assert out == {
        "waitWhileActive": "wait",
        "waitUntilOutcome": "wait",
        "cancelledStaysWaiting": "wait",
        "failedSkips": "skip",
        "unverifiedSkips": "skip",
        "completedRuns": "run",
        "noContextSkipsEvenWhenCompleted": "skip-no-context",
    }


def test_receipt_builder_shapes_pre_and_post() -> None:
    src = f"""
        import {{ buildHarnessReceipt }} from './{PKG_REL}/extensions/harness-consolidation.ts';
        const base = {{ runId: "run_x", scopeDigest: "s", snapshotDigest: "a", targetFile: "/t/p", digestBefore: "aa", planDigest: "pd" }};
        console.log(JSON.stringify({{
          pre: buildHarnessReceipt({{ ...base, phase: "pre" }}),
          post: buildHarnessReceipt({{ ...base, phase: "post", digestAfter: "bb", applied: ["addRule:x"] }}),
        }}));
    """
    out = run_bun(src)
    assert out["pre"]["phase"] == "pre" and "applied" not in out["pre"] and "digestAfter" not in out["pre"]
    assert out["post"]["phase"] == "post"
    assert out["post"]["digestAfter"] == "bb" and out["post"]["applied"] == ["addRule:x"]
    for receipt in (out["pre"], out["post"]):
        assert receipt["kind"] == "harness-consolidation-receipt"
        assert receipt["digestBefore"] == "aa" and receipt["planDigest"] == "pd"


def test_planner_timeout_output_limit_and_post_spawn_cancel_await_child_close() -> None:
    result = run_bun(r'''
      import { mock } from 'bun:test';
      import fs from 'node:fs';
      import os from 'node:os';
      import path from 'node:path';
      import { EventEmitter } from 'node:events';
      const kit = await import('./packages/kit/src/index.ts');
      let mode = '';
      let lastChild;
      mock.module('./packages/kit/src/index.ts', () => ({
        ...kit,
        spawnPiChild: () => {
          const child = new EventEmitter();
          child.stdout = new EventEmitter();
          child.stderr = new EventEmitter();
          child.exitCode = null;
          child.signalCode = null;
          child.pid = undefined;
          child.closed = false;
          child.closeScheduled = false;
          child.kill = signal => {
            if (!child.closeScheduled) {
              child.closeScheduled = true;
              setTimeout(() => {
                child.signalCode = signal;
                child.closed = true;
                child.emit('close', null, signal);
              }, 30);
            }
            return true;
          };
          if (mode === 'output-limit') {
            setTimeout(() => child.stdout.emit('data', Buffer.alloc(16 * 1024 * 1024 + 1)), 0);
          }
          lastChild = child;
          return child;
        },
      }));
      const { planHarnessConsolidationPhase } = await import('./packages/continual-learning/extensions/harness-consolidation.ts');
      const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'harness-planner-stop-'));

      const runCase = async name => {
        mode = name;
        const runDir = path.join(temp, name);
        fs.mkdirSync(runDir, { recursive: true });
        const snapshotPath = path.join(runDir, 'snapshot.json');
        fs.writeFileSync(snapshotPath, JSON.stringify({ entries: [] }));
        const run = {
          manifest: {
            runId: `run-${name}`,
            scopeDigest: 'scope-digest',
            snapshotDigest: 'snapshot-digest',
            snapshotPath,
            cwd: temp,
            runDir,
          },
        };
        let current = true;
        const started = Date.now();
        const planning = planHarnessConsolidationPhase(
          { cwd: temp, ui: { notify() {} } },
          {
            pkgDir: process.cwd(), cwd: temp, reason: name, run,
            resolveCli: () => ({ command: process.execPath, args: [] }),
            timeoutMs: 5,
          },
          {
            current: () => current,
            onChild: () => { if (name === 'cancel') current = false; },
          },
        );
        const raced = await Promise.race([
          planning.then(value => ({ value })),
          new Promise(resolve => setTimeout(() => resolve({ watchdog: true }), 150)),
        ]);
        const child = lastChild;
        const closedWhenResolved = child.closed;
        const elapsed = Date.now() - started;
        if ('watchdog' in raced) {
          child.exitCode = 1;
          child.closed = true;
          child.emit('close', 1, null);
        } else if (!child.closed) {
          await new Promise(resolve => child.once('close', resolve));
        }
        const value = await planning;
        return { watchdog: 'watchdog' in raced, closedWhenResolved, elapsed, detail: value.detail };
      };

      const outputLimit = await runCase('output-limit');
      const cancel = await runCase('cancel');
      const timeout = await runCase('timeout');
      fs.rmSync(temp, { recursive: true, force: true });
      console.log(JSON.stringify({ outputLimit, cancel, timeout }));
    ''')
    assert result["outputLimit"]["watchdog"] is False
    assert result["outputLimit"]["closedWhenResolved"] is True
    assert "stdout exceeded" in result["outputLimit"]["detail"]
    assert result["cancel"]["watchdog"] is False
    assert result["cancel"]["closedWhenResolved"] is True
    assert "cancelled" in result["cancel"]["detail"]
    assert result["timeout"]["watchdog"] is False
    assert result["timeout"]["closedWhenResolved"] is True
    assert result["timeout"]["elapsed"] >= 30
    assert "timed out" in result["timeout"]["detail"]


def test_no_cli_dependency_fails_isolated_without_touching_state(tmp_path: Path) -> None:
    target = tmp_path / "harness.json"
    target.write_text(json.dumps({"rules": [rule("keep")]}), encoding="utf-8")
    before = target.read_bytes()
    script = f"""
        import {{ runHarnessConsolidationPhase }} from './{PKG_REL}/extensions/harness-consolidation.ts';
        const notes = [];
        const state = {{ active: false, generation: 0, cancelled: false }};
        await runHarnessConsolidationPhase(
          {{ cwd: {json.dumps(str(tmp_path))}, ui: {{ notify: (m) => notes.push(m) }} }},
          state,
          {{ pkgDir: {json.dumps(str(PKG_DIR))}, cwd: {json.dumps(str(tmp_path))}, reason: "test", resolveCli: () => null, targetPath: {json.dumps(str(target))} }},
        );
        console.log(JSON.stringify({{ notes, active: state.active, generation: state.generation }}));
    """
    out = run_bun(script)
    assert any("skipped" in n for n in out["notes"])
    assert out["active"] is False and out["generation"] == 0
    assert target.read_bytes() == before


def test_phase_writes_pre_receipt_before_apply_and_post_after(tmp_path: Path) -> None:
    src = (PKG_DIR / "extensions" / "harness-consolidation.ts").read_text(encoding="utf-8")
    pre_idx = src.index('"harness-pre-receipt.json"')
    apply_idx = src.index("await writePreparedHarness(target, prepared);", pre_idx)
    post_idx = src.index('"harness-post-receipt.json"')
    assert pre_idx < apply_idx < post_idx
    assert 'sha256Digest(prepared.before)' in src and 'sha256Digest(prepared.next)' in src
    assert 'now?.equals(Buffer.from(prepared.next))' in src


def test_harness_planner_uses_package_prompt_and_minimal_readonly_args() -> None:
    src = (PKG_DIR / "extensions" / "harness-consolidation.ts").read_text(encoding="utf-8")
    assert "buildHarnessConsolidatorPrompt" in src
    assert 'minimalPiWorkerArgs(["read", "grep", "find", "ls"])' in src


def test_procedure_declares_readonly_boundary_and_bounds() -> None:
    proc = (PKG_DIR / "prompts" / "harness-consolidator.md").read_text(encoding="utf-8")
    assert "Do not write, edit, delete, rename, or copy any file." in proc
    assert "At most 12 operations total." in proc
    assert '"harness-consolidation-plan"' in proc
