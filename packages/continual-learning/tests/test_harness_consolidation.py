from __future__ import annotations

# --- Merged from test_harness_consolidation.py ---
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
      const example=[...prompt.matchAll(/```json\n([\s\S]*?)\n[ \t]*```/g)].map(m=>JSON.parse(m[1])).find(p=>p.kind==='harness-consolidation-plan');
      console.log(JSON.stringify({runId:example.runId,scopeDigest:example.scopeDigest,artifactHash:example.artifactHash}));
    """)
    assert result == {"runId": "run_current", "scopeDigest": "a" * 64, "artifactHash": "b" * 64}


def validate_against_snapshot(plan: dict, snapshot: dict, **context: object) -> list[str]:
    return run_bun(f"import {{validateHarnessPlan}} from './{PKG_REL}/extensions/harness-consolidation.ts';console.log(JSON.stringify(validateHarnessPlan({json.dumps(plan)},{json.dumps({'snapshot':snapshot,**context})})));")


def valid_plan() -> dict:
    return {"kind":"harness-consolidation-plan","version":1,"schemaVersion":1,
        "operations":[{"op":"addRule","rule":_s0_rule(f"rule-{i}"),"cases":_s0_cases()} for i in range(3)],
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


def _s0_rule(name: str = "learned-width", action: str = "block") -> dict:
    return {"id": name, "bash": "^publish-fixture$", "action": action, "message": "Use the safe fixture."}


def _s0_cases(action: str = "block") -> dict:
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
    plan = grounded_plan({"op": "addRule", "rule": _s0_rule(), "cases": _s0_cases()})
    assert validate_against_snapshot(plan, evidence_snapshot()) == []

    invented = grounded_plan(
        {"op": "addRule", "rule": _s0_rule("invented"), "cases": _s0_cases()},
        source="user",
        quote="The user prefers a universal write prohibition.",
    )
    errors = validate_against_snapshot(invented, evidence_snapshot())
    assert any("quote" in error and "snapshot" in error for error in errors)

    model_quote = grounded_plan(
        {"op": "addRule", "rule": _s0_rule("model-only"), "cases": _s0_cases()},
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
        {"op": "addRule", "rule": _s0_rule("multiline"), "cases": _s0_cases()},
        source="user",
        quote=multiline,
    )
    assert validate_against_snapshot(user_plan, snapshot) == []

    two_events = grounded_plan(
        {"op": "addRule", "rule": _s0_rule("two-events"), "cases": _s0_cases()},
        source="tool",
        quote="blocked once",
    )
    two_events["evidence"][0]["count"] = 2
    assert validate_against_snapshot(two_events, snapshot) == []

    repeated_in_one_event = grounded_plan(
        {"op": "addRule", "rule": _s0_rule("one-event"), "cases": _s0_cases()},
        source="tool",
        quote="ordinary outcome",
    )
    repeated_in_one_event["evidence"][0]["count"] = 2
    errors = validate_against_snapshot(repeated_in_one_event, snapshot)
    assert any("count exceeds" in error for error in errors)

    metadata = grounded_plan(
        {"op": "addRule", "rule": _s0_rule("metadata"), "cases": _s0_cases()},
        source="tool",
        quote="metadata-only",
    )
    errors = validate_against_snapshot(metadata, snapshot)
    assert any("not grounded" in error for error in errors)

    assistant = grounded_plan(
        {"op": "addRule", "rule": _s0_rule("assistant"), "cases": _s0_cases()},
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
        {"op": "addRule", "rule": _s0_rule("sdk-tool-result"), "cases": _s0_cases()},
        source="tool",
        quote="blocked by sdk policy",
    )
    assert validate_against_snapshot(accepted, snapshot) == []

    metadata = grounded_plan(
        {"op": "addRule", "rule": _s0_rule("sdk-metadata"), "cases": _s0_cases()},
        source="tool",
        quote="write",
    )
    errors = validate_against_snapshot(metadata, snapshot)
    assert any("not grounded" in error for error in errors)

    assistant = grounded_plan(
        {"op": "addRule", "rule": _s0_rule("sdk-assistant"), "cases": _s0_cases()},
        source="tool",
        quote="assistant-only tool claim",
    )
    errors = validate_against_snapshot(assistant, snapshot)
    assert any("not grounded" in error for error in errors)


def test_policy_add_and_update_require_passing_positive_and_negative_evaluator_cases() -> None:
    base = {"op": "addRule", "rule": _s0_rule()}
    missing = validate_against_snapshot(grounded_plan(base), evidence_snapshot())
    assert any("positive" in error and "negative" in error for error in missing)

    bad_cases = _s0_cases()
    bad_cases["negative"][0]["bash"] = "publish-fixture"
    errors = validate_against_snapshot(
        grounded_plan({**base, "cases": bad_cases}), evidence_snapshot()
    )
    assert any("negative" in error and ("match" in error or "unmatched" in error) for error in errors)

    valid = validate_against_snapshot(
        grounded_plan({**base, "cases": _s0_cases()}), evidence_snapshot()
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
    assert 'shouldRunHarnessPhase(state) !== "run"' in src
    assert "noContext" not in src
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
      import {{ createHash }} from 'node:crypto';
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
      const outcome = await planHarnessConsolidationPhase(ctx, {{ pkgDir: process.cwd(), cwd, reason: 'incremental', run, explorationPath: dossier, explorationDigest: createHash('sha256').update(fs.readFileSync(dossier)).digest('hex'), resolveCli: () => ({{ command: process.execPath, args: [] }}) }});
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
          heldMemorySkips: shouldRunHarnessPhase({{ outcome: "completed", active: false, cancelled: false, memoryReviewHeld: true }}),
          resolvedMemoryRuns: shouldRunHarnessPhase({{ outcome: "completed", active: false, cancelled: false, memoryReviewHeld: false }}),
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
        "heldMemorySkips": "skip",
        "resolvedMemoryRuns": "run",
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
        const snapshotBytes = JSON.stringify({ entries: [] });
        fs.writeFileSync(snapshotPath, snapshotBytes);
        const { sha256Digest } = await import('./packages/continual-learning/extensions/consolidation-run.ts');
        const run = {
          manifest: {
            runId: `run-${name}`,
            scopeDigest: 'scope-digest',
            snapshotDigest: sha256Digest(snapshotBytes),
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
        let watchdog;
        const raced = await Promise.race([
          planning.then(value => ({ value })),
          // This detects a cleanup deadlock, not filesystem scheduling latency.
          // The closedWhenResolved assertion below proves the ordering directly.
          new Promise(resolve => { watchdog = setTimeout(() => resolve({ watchdog: true }), 2000); }),
        ]);
        clearTimeout(watchdog);
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
    target.write_text(json.dumps({"rules": [_s0_rule("keep")]}), encoding="utf-8")
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
    assert "plannerNoToolArgs()" in src
    assert "workerCliArgs" not in src
    assert "plannerReadArgs" not in src
    assert "harnessPlannerPreviewArgs" not in src
    assert "TOOL_NAMES.harnessCheckCases" not in src
    assert "inlineDossierBlock" in src


def test_procedure_declares_readonly_boundary_and_bounds() -> None:
    proc = (PKG_DIR / "prompts" / "harness-consolidator.md").read_text(encoding="utf-8")
    assert "Do not write, edit, delete, rename, or copy" in proc
    assert "no file reads are possible or permitted" in proc
    assert "At most 12 operations total." in proc
    assert '"harness-consolidation-plan"' in proc

@pytest.mark.parametrize("mode", ["identity", "multiple-plans", "secret", "repair", "archive-unavailable"])
def test_rejected_harness_transport_retains_bound_evidence_without_retry(tmp_path: Path, mode: str) -> None:
    result = run_bun(rf'''
      process.env.PI_CODING_AGENT_DIR = {json.dumps(str(tmp_path / 'agent'))};
      import {{ mock }} from 'bun:test';
      import fs from 'node:fs';
      import path from 'node:path';
      import {{ EventEmitter }} from 'node:events';
      import {{ createHash }} from 'node:crypto';
      const tasks = [];
      const kit = await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts', () => ({{
        ...kit,
        spawnPiChild: (_command, args) => {{
          const taskFile = args.find(arg => arg.startsWith('@')).slice(1);
          tasks.push(fs.readFileSync(taskFile, 'utf8'));
          if ({json.dumps(mode)} === 'archive-unavailable' && tasks.length === 2) fs.mkdirSync(path.join(path.dirname(taskFile), 'harness-repair-output.json'));
          const manifest = JSON.parse(fs.readFileSync(path.join(path.dirname(taskFile), 'manifest.json'), 'utf8'));
          const plan = {{ kind: 'harness-consolidation-plan', version: 1, schemaVersion: 1, runId: manifest.runId, scopeDigest: manifest.scopeDigest, artifactHash: manifest.snapshotDigest, operations: [], evidence: [], report: [] }}; if ({json.dumps(mode)} !== "multiple-plans") plan.runId = "foreign-run";
          if ({json.dumps(mode)} === "secret") plan.note = "api_key=" + "sk-" + "a".repeat(40);
          const child = new EventEmitter(); child.stdout = new EventEmitter(); child.stderr = new EventEmitter(); child.exitCode = null; child.signalCode = null;
          queueMicrotask(() => {{ if ({json.dumps(mode)} === 'multiple-plans') child.stdout.emit('data', Buffer.from(JSON.stringify({{type:'message_end',message:{{role:'assistant',content:[{{type:'text',text:JSON.stringify(plan)}}]}}}})+'\n')); child.stdout.emit('data', Buffer.from(JSON.stringify({{ type: 'message_end', message: {{ role: 'assistant', content: [{{ type: 'text', text: (['repair','archive-unavailable'].includes({json.dumps(mode)}) && tasks.length === 1) ? 'No structured output' : JSON.stringify(plan) }}] }} }}) + '\n')); child.exitCode = 0; child.emit('close', 0); }});
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
      const outcome = await planHarnessConsolidationPhase(ctx, {{ pkgDir: process.cwd(), cwd, reason: 'incremental', run, explorationPath: dossier, explorationDigest: createHash('sha256').update(fs.readFileSync(dossier)).digest('hex'), resolveCli: () => ({{ command: process.execPath, args: [] }}) }});
      await releaseConsolidationRun(run, {{keepArtifacts:true}});
      console.log(JSON.stringify({{ ok: outcome.ok, attempts: outcome.attempts, calls: tasks.length, runDir: run.manifest.runDir }}));
    ''')
    assert result["ok"] is False
    assert result["calls"] == (2 if mode in ("repair", "archive-unavailable") else 1)
    category = "multiple-plans" if mode == "multiple-plans" else "identity"
    assert result["attempts"][-1]["diagnostic"] == f"Parent Harness extraction: {category}"
    if mode == "archive-unavailable":
        assert len(result["attempts"]) == 2
        assert result["attempts"][-1]["outcome"] == "rejected"
        return
    archive_file = Path(result["runDir"]) / ("harness-repair-output.json" if mode == "repair" else "harness-initial-output.json")
    archive = json.loads(archive_file.read_text())
    assert archive["category"] == category
    assert archive["originalTransportRetained"] is (mode != "secret")
    assert archive_file.stat().st_mode & 0o777 == 0o600
    if mode == "secret":
        assert "stdout" not in archive
        assert "sk-" not in json.dumps(archive)
        return
    assert archive["semanticAcceptance"] is False
    import hashlib
    assert hashlib.sha256(archive["stdout"].encode()).hexdigest() == archive["originalTransportSha256"]
    assert archive["originalTransportBytes"] == len(archive["stdout"].encode())


@pytest.mark.parametrize("defect", ["snapshot-race", "dossier-mismatch"])
def test_inline_dossier_holds_without_spawning_on_digest_or_content_defect(tmp_path: Path, defect: str) -> None:
    # Given a parent-owned immutable snapshot and selector dossier, When a file
    # drifts or its digest mismatches, Then the Harness planner child must NOT
    # spawn and the phase must report the hold. Evidence content itself is
    # ordinary planner input; the separate test below covers that case.
    import hashlib
    result = run_bun(rf'''
      process.env.PI_CODING_AGENT_DIR = {json.dumps(str(tmp_path / 'agent'))};
      import {{ mock }} from 'bun:test';
      import fs from 'node:fs';
      import path from 'node:path';
      import {{ EventEmitter }} from 'node:events';
      import {{ createHash }} from 'node:crypto';
      let spawns = 0;
      const kit = await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts', () => ({{
        ...kit,
        spawnPiChild: () => {{
          spawns += 1;
          const child = new EventEmitter(); child.stdout = new EventEmitter(); child.stderr = new EventEmitter(); child.exitCode = null; child.signalCode = null;
          queueMicrotask(() => child.emit('close', 0));
          return child;
        }},
      }}));
      const {{ createConsolidationRun, releaseConsolidationRun }} = await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const {{ planHarnessConsolidationPhase }} = await import('./packages/continual-learning/extensions/harness-consolidation.ts');
      const cwd = {json.dumps(str(tmp_path))};
      const entries = [{{ message: {{ role: 'user', content: 'Never write generated files.' }} }}];
      const ctx = {{ cwd, ui: {{ notify() {{}} }}, sessionManager: {{ getBranch: () => entries, buildContextEntries: () => entries }} }};
      const run = await createConsolidationRun(ctx, cwd, false);
      const dossier = path.join(run.manifest.runDir, 'incremental-learning-dossier.json');
      const dossierText = '{{"observed":"project evidence"}}\n';
      fs.writeFileSync(dossier, dossierText);
      const defect = {json.dumps(defect)};
      if (defect === 'snapshot-race') fs.appendFileSync(run.manifest.snapshotPath, ' ');
      const dossierDigest = defect === 'dossier-mismatch' ? '0'.repeat(64) : createHash('sha256').update(dossierText).digest('hex');
      const outcome = await planHarnessConsolidationPhase(ctx, {{ pkgDir: process.cwd(), cwd, reason: 'incremental', run, explorationPath: dossier, explorationDigest: dossierDigest, resolveCli: () => ({{ command: process.execPath, args: [] }}) }});
      await releaseConsolidationRun(run);
      console.log(JSON.stringify({{ ok: outcome.ok, detail: outcome.detail, spawns }}));
    ''')
    assert result['ok'] is False, result
    assert result['spawns'] == 0, result
    assert 'dossier unavailable' in result['detail'], result


def test_credential_shaped_snapshot_is_delivered_to_the_harness_planner(tmp_path: Path) -> None:
    # Given a frozen snapshot carrying credential-shaped project text with a
    # matching parent digest, When the Harness phase builds its inline dossier,
    # Then the planner child spawns with that unchanged evidence instead of a
    # "dossier unavailable" hold.
    import json
    from support import run_bun

    value = run_bun(rf'''
      process.env.PI_CODING_AGENT_DIR = {json.dumps(str(tmp_path / "agent"))};
      import {{ mock }} from 'bun:test';
      import fs from 'node:fs';
      import path from 'node:path';
      import {{ EventEmitter }} from 'node:events';
      import {{ createHash }} from 'node:crypto';
      let spawns = 0;
      const kit = await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts', () => ({{
        ...kit,
        spawnPiChild: () => {{
          spawns += 1;
          const child = new EventEmitter(); child.stdout = new EventEmitter(); child.stderr = new EventEmitter(); child.exitCode = null; child.signalCode = null;
          queueMicrotask(() => child.emit('close', 0));
          return child;
        }},
      }}));
      const {{ createConsolidationRun, releaseConsolidationRun, sha256Digest }} = await import('./packages/continual-learning/extensions/consolidation-run.ts');
      const {{ planHarnessConsolidationPhase }} = await import('./packages/continual-learning/extensions/harness-consolidation.ts');
      const cwd = {json.dumps(str(tmp_path))};
      const entries = [{{ message: {{ role: 'user', content: 'Inspect the CI token incident.' }} }}];
      const ctx = {{ cwd, ui: {{ notify() {{}} }}, sessionManager: {{ getBranch: () => entries, buildContextEntries: () => entries }} }};
      const run = await createConsolidationRun(ctx, cwd, false);
      const dossier = path.join(run.manifest.runDir, 'incremental-learning-dossier.json');
      const dossierText = '{{"observed":"project evidence"}}\n';
      fs.writeFileSync(dossier, dossierText);
      const snapshotText = 'api_key: abcdefghijklmnop\n\n';
      fs.writeFileSync(run.manifest.snapshotPath, snapshotText);
      run.manifest.snapshotDigest = sha256Digest(snapshotText);
      const outcome = await planHarnessConsolidationPhase(ctx, {{ pkgDir: process.cwd(), cwd, reason: 'incremental', run,
        explorationPath: dossier, explorationDigest: createHash('sha256').update(dossierText).digest('hex'),
        resolveCli: () => ({{ command: process.execPath, args: [] }}) }});
      await releaseConsolidationRun(run);
      console.log(JSON.stringify({{ detail: outcome.detail, spawns }}));
    ''')
    assert value["spawns"] >= 1, value
    assert "dossier unavailable" not in value["detail"], value


# --- Merged from test_current_user_harness_correction.py ---
from pathlib import Path
import pytest
from support import isolated_run_bun


def test_only_actual_current_explicit_durable_user_corrections_nominate_early_review():
    result = isolated_run_bun(r'''
      import {currentUserCorrectionEntry, ownedCorrectionPlan} from './packages/continual-learning/extensions/current-user-harness-correction.ts';
      const text='Permanently retire the automatically learned npm-test restriction: npm commands are no longer forbidden by project policy.';
      const entry={id:'actual-user',type:'message',message:{role:'user',content:[{type:'text',text}]}};
      const nominates=(entries,prompt)=>Boolean(currentUserCorrectionEntry(entries,prompt));
      const old={npm:'a'.repeat(64)};
      const op={op:'updateRule',rule:{id:'npm',enabled:false},correction:{eventIndex:0,quote:text,priorRevision:old.npm}};
      console.log(JSON.stringify({current:nominates([entry],text),extension:nominates([entry],'Please continue.'),
        temporary:nominates([{...entry,message:{role:'user',content:[{type:'text',text:'Allow npm --version for this task only.'}]}}],'Allow npm --version for this task only.'),
        quotedTool:nominates([{...entry,message:{role:'toolResult',content:[{type:'text',text}]}}],text),
        assistant:nominates([{...entry,message:{role:'assistant',content:[{type:'text',text}]}}],text),
        nonOriginal:nominates([{message:entry.message}],text),
        mixed:nominates([{...entry,message:{role:'user',content:[{type:'text',text},{type:'image',data:'data'}]}}],text),
        valid:ownedCorrectionPlan({operations:[op]},old),
        added:ownedCorrectionPlan({operations:[{...op,op:'addRule'}]},old),
        foreign:ownedCorrectionPlan({operations:[{...op,rule:{id:'manual'}}]},old),
        stale:ownedCorrectionPlan({operations:[{...op,correction:{...op.correction,priorRevision:'b'.repeat(64)}}]},old),
        missing:ownedCorrectionPlan({operations:[{...op,correction:undefined}]},old),
        wrongEntry:ownedCorrectionPlan({operations:[{...op,correction:{...op.correction,eventIndex:1}}]},old)}));
    ''')
    assert result['current'] and result['valid']
    assert all(not value for name, value in result.items() if name not in ('current', 'valid'))


def test_registered_early_review_uses_only_current_user_and_never_acknowledges_unfinished_task():
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'early-harness-'));fs.mkdirSync(path.join(cwd,'.git'));fs.mkdirSync(path.join(cwd,'.pi'));
      const agent=process.env.PI_CODING_AGENT_DIR;fs.mkdirSync(path.join(agent,'memory'),{recursive:true});
      fs.writeFileSync(path.join(agent,'continual-learning.json'),JSON.stringify({jev:{apiKey:'offline-fixture',scopes:['harness']},autoSettledLearning:true,autoContinualLearning:false,automaticPhases:{memory:'off',harness:'apply',agents:'off'}}));
      const rule={id:'owned-npm',bash:'^npm(?:\\s|$)',action:'block',message:'Block Bash commands whose first executable is npm.'};
      const target=path.join(cwd,'.pi/harness.json');const original=JSON.stringify({rules:[rule],learnedRules:{[rule.id]:{origin:'consolidation',revision:ruleRevision(rule)}}});fs.writeFileSync(target,original);
      const preflightModule=await import('./packages/continual-learning/extensions/worker-model-preflight.ts');
      mock.module('./packages/continual-learning/extensions/worker-model-preflight.ts',()=>({...preflightModule,createWorkerModelPreflight:()=>({check:async()=>true})}));
      const harness=await import('./packages/continual-learning/extensions/harness-consolidation.ts');let plans=0,captured,bound;
      mock.module('./packages/continual-learning/extensions/harness-consolidation.ts',()=>({...harness,planHarnessConsolidationPhase:async(ctx,opts)=>{
        plans++;captured=ctx.sessionManager.getBranch();bound=opts.timeoutMs;return {ok:false,detail:'Controlled held plan',durationMs:1,run:opts.run,attempts:[{phase:'harness',attempt:0,outcome:'failed',durationMs:1,operations:0,modelCalls:0}]};
      }}));
      const {default:register}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const hooks=new Map(),receipts=[];register({on:(name,fn)=>hooks.set(name,[...(hooks.get(name)??[]),fn]),registerCommand:()=>{},registerEntryRenderer:()=>{},getCommands:()=>[],appendEntry:()=>{},sendMessage:m=>{if(m.customType==='continual-learning-result')receipts.push(m.details)}});
      const text='Correction of the prior permanent project constraint: npm --version is now allowed; only Bash commands starting npm test must be blocked. Replace the old broad npm restriction permanently.';
      const entry={id:'actual-user',type:'message',message:{role:'user',content:[{type:'text',text}]}};
      const entries=[{id:'older-user',type:'message',message:{role:'user',content:'Permanently block npm.'}},entry];
      const ctx={cwd,mode:'json',hasUI:false,model:{provider:'fixture',id:'fixture'},ui:{notify:()=>{},setWidget:()=>{}},sessionManager:{getSessionId:()=> 'current-session',getBranch:()=>entries,buildContextEntries:()=>entries}};
      for(const fn of hooks.get('session_start')??[])await fn({},ctx);
      const start=async prompt=>{for(const fn of hooks.get('before_agent_start')??[])await fn({prompt,systemPromptOptions:{sections:{}}},ctx)};
      await start('Extension continuation');const before=plans;for(const fn of hooks.get('input')??[])await fn({source:'interactive',text},ctx);await start(text);await start(text);
      const {readBacklog}=await import('./packages/continual-learning/extensions/learning-backlog.ts');
      console.log(JSON.stringify({before,plans,captured,bound,unchanged:fs.readFileSync(target,'utf8')===original,pending:readBacklog(cwd).pendingEntries.length,receipts:receipts.map(r=>({operations:r.operations,attempts:r.attempts.map(a=>a.outcome)}))}));
    ''')
    assert result['before'] == 0
    assert result['plans'] == 1
    assert len(result['captured']) == 1 and result['captured'][0]['inputProvenance']['source'] == 'interactive'
    assert result['bound'] == 230000
    assert result['unchanged'] and result['pending'] == 0
    assert result['receipts'] and result['receipts'][0]['operations'] == 0
    assert 'failed' in result['receipts'][0]['attempts']


def test_ordinary_config_writes_preserve_exact_owned_rules_and_markers():
    value = isolated_run_bun(r'''
      import {preservesOwnedHarnessRules} from './packages/continual-learning/extensions/current-user-harness-correction.ts';
      import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const rule={id:'owned',bash:'^npm$',action:'block',message:'Block npm.'};
      const before={rules:[rule],learnedRules:{owned:{origin:'consolidation',revision:ruleRevision(rule)}}};
      const changed={...before,rules:[{...rule,enabled:false}]};
      console.log(JSON.stringify({same:preservesOwnedHarnessRules(before,structuredClone(before)),
        unrelated:preservesOwnedHarnessRules(before,{...before,rules:[rule,{id:'manual',text:'topic',instructions:'Manual instruction.'}]}),
        changed:preservesOwnedHarnessRules(before,changed),removed:preservesOwnedHarnessRules(before,{rules:[],learnedRules:before.learnedRules}),
        markerRemoved:preservesOwnedHarnessRules(before,{rules:[rule]}),markerChanged:preservesOwnedHarnessRules(before,{...before,learnedRules:{owned:{origin:'consolidation',revision:'a'.repeat(64)}}}),
        manual:preservesOwnedHarnessRules({rules:[rule]},changed),stale:preservesOwnedHarnessRules({...before,rules:[{...rule,message:'Manually changed.'}]},changed)}));
    ''')
    assert value['same'] and value['unrelated'] and value['manual'] and value['stale']
    assert not value['changed'] and not value['removed'] and not value['markerRemoved'] and not value['markerChanged']


def test_total_early_deadline_terminates_child_and_retains_partial_cost_without_mutation():
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import path from 'node:path';import os from 'node:os';import {spawn} from 'node:child_process';
      import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'early-deadline-'));fs.mkdirSync(path.join(cwd,'.git'));fs.mkdirSync(path.join(cwd,'.pi'));
      const agent=process.env.PI_CODING_AGENT_DIR;fs.mkdirSync(path.join(agent,'memory'),{recursive:true});
      fs.writeFileSync(path.join(agent,'continual-learning.json'),JSON.stringify({jev:{apiKey:'offline-fixture',scopes:['harness']},autoSettledLearning:true,autoContinualLearning:false,automaticPhases:{memory:'off',harness:'apply',agents:'off'}}));
      const rule={id:'owned',bash:'^npm$',action:'block',message:'Block npm.'};const original=JSON.stringify({rules:[rule],learnedRules:{owned:{origin:'consolidation',revision:ruleRevision(rule)}}});const target=path.join(cwd,'.pi/harness.json');fs.writeFileSync(target,original);
      let fire,bound,pid,closed=false;
      const timer=globalThis.setTimeout;globalThis.setTimeout=(fn,ms,...args)=>ms===230_000?(bound=ms,fire=fn,timer(()=>{},60000)):timer(fn,ms,...args);
      const preflightModule=await import('./packages/continual-learning/extensions/worker-model-preflight.ts');
      mock.module('./packages/continual-learning/extensions/worker-model-preflight.ts',()=>({...preflightModule,createWorkerModelPreflight:()=>({check:async()=>true})}));
      const harness=await import('./packages/continual-learning/extensions/harness-consolidation.ts');
      mock.module('./packages/continual-learning/extensions/harness-consolidation.ts',()=>({...harness,planHarnessConsolidationPhase:async(ctx,opts,hooks)=>{
        const child=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:'ignore'});pid=child.pid;hooks.onChild(child);
        await new Promise(resolve=>{child.once('close',()=>{closed=true;resolve();});child.once('spawn',()=>fire());});
        return {ok:false,detail:'Controlled terminated worker',run:opts.run,durationMs:1,attempts:[{phase:'harness',attempt:0,outcome:'cancelled',operations:0,durationMs:1,usage:{input:2,output:3,cacheRead:0,cacheWrite:0,totalTokens:5,cost:0.25},usageComplete:false,costAvailable:false}]};
      }}));
      const {default:register}=await import('./packages/continual-learning/extensions/inject-memory.ts');const hooks=new Map();register({on:(n,f)=>hooks.set(n,[...(hooks.get(n)??[]),f]),registerCommand:()=>{},registerEntryRenderer:()=>{},getCommands:()=>[],appendEntry:()=>{},sendMessage:()=>{}});
      const ctx={cwd,mode:'json',hasUI:false,model:{provider:'fixture',id:'fixture'},ui:{notify:()=>{},setWidget:()=>{}},sessionManager:{getSessionId:()=> 'deadline-session',getBranch:()=>[],buildContextEntries:()=>[]}};
      const text='Permanently retire the owned rule.';for(const f of hooks.get('session_start')??[])await f({},ctx);for(const f of hooks.get('input')??[])await f({source:'rpc',text},ctx);for(const f of hooks.get('before_agent_start')??[])await f({prompt:text,systemPromptOptions:{sections:{}}},ctx);
      let alive=true;try{process.kill(pid,0)}catch{alive=false}
      const receipts=fs.readdirSync(agent,{recursive:true}).filter(f=>String(f).endsWith('learning-pipeline-receipt.json')).map(f=>JSON.parse(fs.readFileSync(path.join(agent,String(f)),'utf8')));
      console.log(JSON.stringify({bound,closed,alive,unchanged:fs.readFileSync(target,'utf8')===original,receipts}));
    ''', timeout=15)
    assert value['bound'] == 230000 and value['closed'] and not value['alive'] and value['unchanged']
    from continuous_failure_retention import deduplicate_receipt_views
    receipts=deduplicate_receipt_views(value['receipts'])
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt['operations'] == 0 and receipt['totals']['cost'] == 0.25 and not receipt['costAvailable']
    assert any(a.get('diagnostic') == 'Early Harness correction exceeded its 230-second deadline.' for a in receipt['attempts'])
    assert receipt['attempts'][-1]['outcome'] == 'cancelled'


@pytest.mark.parametrize('boundary', ['session_shutdown', 'session_start', 'new-input'])
@pytest.mark.parametrize('stage', ['read', 'planner'])
def test_preflight_cannot_restart_after_session_or_input_changes(boundary, stage):
    value = isolated_run_bun(Path(__file__).with_name('current-user-harness-cancel-fixture.ts').read_text(), env={'CL_EARLY_LIFECYCLE': boundary, 'CL_EARLY_CANCEL_STAGE': stage})
    assert value['plansAtShutdown'] == value['plans'] == (1 if stage == 'planner' else 0)
    assert value['applications'] == 0 and value['unchanged'] and value['pending'] == 0
    if stage == 'read':
        assert not value['receipts']


@pytest.mark.parametrize('mode', ['initial', 'repair'])
def test_real_harness_child_partial_usage_reaches_attempt_receipts(mode):
    value = isolated_run_bun(Path(__file__).with_name('harness-partial-usage-fixture.ts').read_text(), env={'CL_HARNESS_PARTIAL_MODE': mode}, timeout=15)
    assert value['childClosed'] and not value['ok'] and value['bound'] == 230000
    assert value['calls'] == (2 if mode == 'repair' else 1)
    attempt = value['attempts'][-1]
    ledger = next(item for item in value['ledgers'] if item['ledgerId'] == attempt.get('usageLedgerId'))
    assert not ledger['complete'] and ledger['knownUsage']['cost'] == 0.25
    assert attempt['usage']['cost'] == 0.25 and not attempt['usageComplete'] and not attempt['costAvailable']
    assert value['usage']['cost'] == (0.35 if mode == 'repair' else 0.25)


def test_ordinary_nearer_layer_cannot_shadow_owned_rule_in_another_layer():
    value = isolated_run_bun(r'''
      import {preservesOwnedHarnessRules} from './packages/continual-learning/extensions/current-user-harness-correction.ts';
      import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const rule={id:'owned',bash:'^npm$',action:'block',message:'Block npm.'};
      const other={source:'project',rules:[rule],learnedRules:{owned:{origin:'consolidation',revision:ruleRevision(rule)}}};
      const shadow={...rule,enabled:false};
      console.log(JSON.stringify({newShadow:preservesOwnedHarnessRules({}, {rules:[shadow]},[other]),
        sameCopy:preservesOwnedHarnessRules({}, {rules:[rule]},[other]),
        unchangedManual:preservesOwnedHarnessRules({rules:[shadow]},{rules:[shadow,{id:'unrelated',text:'topic',instructions:'Manual.'}]},[other]),
        changedManual:preservesOwnedHarnessRules({rules:[shadow]},{rules:[rule]},[other])}));
    ''')
    assert not value['newShadow'] and not value['sameCopy'] and not value['changedManual']
    assert value['unchangedManual']


# --- Merged from test_harness_audit_followup.py ---
import json
from pathlib import Path

import pytest

from agents_md_fixtures import apply_plan_script, extraction_ops, prepare_extraction_roots
from support import run_bun as js

MODULE = './packages/continual-learning/extensions/harness-consolidation.ts'


@pytest.mark.parametrize('asset_only', [False, True])
def test_native_path_aliases_enforce_gates(tmp_path: Path, asset_only: bool) -> None:
    source = r'''
      import register from './packages/continual-learning/extensions/guardrails.ts';
      import path from 'node:path'; import {pathToFileURL} from 'node:url';
      import {createWriteTool} from '@earendil-works/pi-coding-agent';
      const hooks={};
      register({on:(n,f)=>hooks[n]=f,registerCommand(){},registerEntryRenderer(){},getCommands:()=>[]});
      const ctx={cwd:process.env.HOME,hasUI:false};
      const results=[];
      const nativePaths=[];
      const native=createWriteTool(ctx.cwd,{operations:{mkdir:async()=>{},writeFile:async(p)=>nativePaths.push(p)}});
      for(const file of ['harness.local.json','harness.json']) {
        const absolute=path.join(process.env.HOME,'.pi/agent',file);
        for(const alias of ['~/.pi/agent/'+file,'@~/.pi/agent/'+file,'@'+absolute,absolute,'.pi/agent/'+file,'@./.pi/agent/../agent/'+file,pathToFileURL(absolute).href,'@'+pathToFileURL(absolute).href]) {
          await native.execute('probe',{path:alias,content:'{}'});
          if(nativePaths.at(-1)!==absolute) throw new Error('native path mismatch');
          for(const toolName of ['write','edit','read']) {
            const result=await hooks.tool_call({toolName,input:{path:alias,content:'{"rules":"invalid"}',edits:[]}},ctx);
            results.push({file,alias,toolName,result:result??null});
          }
        }
      }
      const spacedCwd=path.join(ctx.cwd,'with space');
      const spacedTarget=path.join(spacedCwd,'.pi/harness.json');
      const spacedNative=createWriteTool(spacedCwd,{operations:{mkdir:async()=>{},writeFile:async(p)=>nativePaths.push(p)}});
      for(const space of ['\u00a0','\u2000','\u200a','\u202f','\u205f','\u3000']) {
        const alias='@'+spacedTarget.replace('with space','with'+space+'space');
        await spacedNative.execute('probe',{path:alias,content:'{}'});
        if(nativePaths.at(-1)!==spacedTarget) throw new Error('native Unicode space mismatch');
        const result=await hooks.tool_call({toolName:'write',input:{path:alias,content:'{"rules":"invalid"}'}},{...ctx,cwd:spacedCwd});
        if(!result?.block) throw new Error('Unicode-space harness alias bypassed gate');
      }
      for(const toolName of ['write','edit']) {
        const result=await hooks.tool_call({toolName,input:{path:'ordinary.txt',content:'plain text',edits:[]}},ctx);
        if(result?.block) throw new Error('unrelated mutation blocked');
      }
      console.log(JSON.stringify(results));
    '''
    env = {'HOME': str(tmp_path), 'PI_CODING_AGENT_DIR': str(tmp_path / '.pi/agent')}
    if asset_only:
        assets = tmp_path / 'assets'
        assets.mkdir()
        (assets / 'README.md').write_text('Asset-only installation fixture')
        env['PI_PACKAGE_DIR'] = str(assets)
    results = js(source, env)
    for row in results:
        if row['toolName'] == 'read':
            assert row['result'] is None
        else:
            assert row['result'] and row['result']['block'], row
            assert ('Use ~/.pi/agent/harness.json for global configuration.' if row['file'] == 'harness.local.json' else ('validated' if row['toolName'] == 'edit' else 'Invalid')) in row['result']['reason']


MALFORMED = [None, [], 'retained', {'skillPrompts': ['retained']}, {'skillPrompts': None}, {'policies': {'retained': True}}, {'disabled': 'retained'}]


@pytest.mark.parametrize('base', MALFORMED)
def test_harness_apply_preserves_malformed_bytes(tmp_path: Path, base: object) -> None:
    target = tmp_path / 'harness.json'
    before = '  ' + json.dumps(base) + '\n'
    target.write_text(before)
    result = js(f"""
      import {{applyHarnessOps}} from '{MODULE}';
      console.log(JSON.stringify(await applyHarnessOps({json.dumps(str(target))}, [{{op:'addRule',rule:{{id:'known',skill:'known',instructions:'guidance'}}}}],new Set(['known']))));
    """)
    assert result['ok'] is False
    assert any(word in result['error'] for word in ['object', 'array', 'legacy'])
    assert target.read_text() == before


@pytest.mark.parametrize('base', MALFORMED)
def test_harness_orchestration_rejects_before_receipts(tmp_path: Path, base: object) -> None:
    target = tmp_path / 'harness.json'
    before = '  ' + json.dumps(base) + '\n'
    target.write_text(before)
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    result = js(f"""
      import {{applyHarnessConsolidationPlan}} from '{MODULE}';
      import fs from 'node:fs'; import {{createHash}} from 'node:crypto';
      const snapshotPath={json.dumps(str(run_dir/'snapshot.json'))}; fs.writeFileSync(snapshotPath,'{{}}');
      const snapshotDigest=createHash('sha256').update(fs.readFileSync(snapshotPath)).digest('hex');
      const planning={{
        target:{json.dumps(str(target))},
        run:{{manifest:{{runDir:{json.dumps(str(run_dir))},runId:'test',scopeDigest:'scope',snapshotPath,snapshotDigest}}}},
        plan:{{kind:'harness-consolidation-plan',operations:[{{op:'addRule',rule:{{id:'known',skill:'known',instructions:'guidance'}}}}]}},
        validationOptions:{{availableSkills:new Set(['known']),requireEvidence:false,requireCases:false}}
      }};
      console.log(JSON.stringify(await applyHarnessConsolidationPlan(planning)));
    """)
    assert result['outcome'] == 'rejected'
    assert any(word in result['error'] for word in ['object', 'array', 'legacy'])
    assert target.read_text() == before
    assert sorted(p.name for p in run_dir.iterdir()) == ['snapshot.json']
    assert sorted(p.name for p in tmp_path.iterdir()) == ['harness.json', 'run']


@pytest.mark.parametrize('base', MALFORMED)
def test_agents_extraction_preserves_malformed_bytes(tmp_path: Path, base: object) -> None:
    project, agent, run_dir = prepare_extraction_roots(tmp_path)
    target = project / '.pi/harness.json'
    before = '  ' + json.dumps(base) + '\n'
    target.write_text(before)
    doc = (project / 'AGENTS.md').read_bytes()
    result = js(apply_plan_script(project, agent, run_dir, [extraction_ops()[1]]), {'PI_CODING_AGENT_DIR': str(agent)})
    assert result['result']['outcome'] == 'failed'
    assert any(word in result['result']['detail'] for word in ['object', 'array', 'legacy'])
    assert target.read_text() == before
    assert (project / 'AGENTS.md').read_bytes() == doc
    assert result['preReceiptExists'] is False


def test_summary_filters_unknown_skills(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    (project / '.pi').mkdir(parents=True)
    (project / '.pi/harness.json').write_text(json.dumps({'rules': [{'id': name, 'skill': name, 'instructions': 'guidance'} for name in ['known', 'unknown']]}))
    result = js(f"""
      import {{harnessSurfaceSummary}} from '{MODULE}';
      console.log(JSON.stringify(JSON.parse(await harnessSurfaceSummary({json.dumps(str(project))},{json.dumps(str(tmp_path / 'agent'))},new Set(['known'])))));
    """)
    assert [rule['skill'] for rule in result['rules'] if 'skill' in rule] == ['known']
    assert any('unknown' in error for error in result['errors'])


# --- Merged from test_harness_authoring_preview.py ---
import json
from pathlib import Path
from support import isolated_run_bun as run_bun


def test_preview_executes_plain_fixtures_and_requires_complete_coverage() -> None:
    result = run_bun('''
      import {previewHarnessCandidate} from './packages/continual-learning/extensions/harness-authoring-preview.ts';
      const candidate=JSON.stringify({rules:[{id:'traffic',text:'D0',instructions:'confirm volume first'}]});
      const cases=[{ruleId:'traffic',input:'接下来维护 D0',matches:true},{ruleId:'traffic',input:'本地配色',matches:false}];
      const run=(content,fixtures)=>previewHarnessCandidate(content,fixtures,new Set());
      console.log(JSON.stringify({good:run(candidate,cases),missing:run(candidate,cases.slice(0,1)),
        inert:run(JSON.stringify({rules:[{id:'traffic',text:String.fromCharCode(92).repeat(2)+'bD0'+String.fromCharCode(92).repeat(2)+'b',instructions:'confirm volume first'}]}),cases),falseNegative:run(candidate,[...cases.slice(0,1),{...cases[1],input:'D0'}]),
        disabled:run(JSON.stringify({rules:[{id:'existing-rule',enabled:false}]}),[]),empty:run(JSON.stringify({rules:[]}),[]),invalid:run('{',cases),foreign:run(candidate,cases.map(c=>({...c,ruleId:'other'})))}));
    ''')
    assert result['good']['passed'] and result['disabled']['passed']
    for name in ['missing', 'inert', 'falseNegative', 'empty', 'invalid', 'foreign']:
        assert not result[name]['passed'], name


def test_authoring_write_requires_exact_preview_and_tool_expires(tmp_path: Path) -> None:
    result = run_bun(f'''
      import fs from 'node:fs';
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / 'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}},commands={{}},tools={{}}; let active=['read','write'];
      register({{on:(n,f)=>hooks[n]=f,registerEntryRenderer(){{}},registerMessageRenderer(){{}},registerCommand:(n,c)=>commands[n]=c,
        registerTool:t=>tools[t.name]=t,getActiveTools:()=>active,setActiveTools:t=>active=t,getCommands:()=>[],sendMessage(){{}}}});
      const ctx={{cwd:{json.dumps(str(tmp_path))},hasUI:true,ui:{{notify(){{}},select:async()=> 'Allow once'}}}};
      const content=JSON.stringify({{rules:[{{id:'traffic',text:'D0',instructions:'confirm volume first'}}]}});
      const event={{toolName:'write',toolCallId:'write',input:{{path:'.pi/harness.json',content}}}};
      const before=await tools.harness_preview.execute('inactive',{{content,cases:[]}},undefined,undefined,ctx);
      await commands.harness.handler('避免后续 D0 的流量被打爆',ctx);
      const admitted=active.includes('harness_preview');
      const blocked=await hooks.tool_call(event,ctx);
      const preview=await tools.harness_preview.execute('preview',{{content,cases:[{{ruleId:'traffic',input:'维护 D0',matches:true}},{{ruleId:'traffic',input:'本地配色',matches:false}}]}},undefined,undefined,ctx);
      const normalDuring=await hooks.tool_call({{toolName:'write',toolCallId:'normal-during',input:{{path:'notes.txt',content:'Ordinary source work'}}}},ctx);
      const allowed=await hooks.tool_call(event,ctx);
      const repeated=await hooks.tool_call(event,ctx);
      const normalAfter=await hooks.tool_call({{toolName:'write',toolCallId:'normal-after',input:{{path:'notes.txt',content:'Ordinary source work'}}}},ctx);
      const changed=await hooks.tool_call({{...event,input:{{...event.input,content:content+' '}}}},ctx);
      await hooks.agent_end?.({{}},ctx);
      const across=await tools.harness_preview.execute('across',{{content,cases:[{{ruleId:'traffic',input:'维护 D0',matches:true}},{{ruleId:'traffic',input:'本地配色',matches:false}}]}},undefined,undefined,ctx);
      const acrossWrite=await hooks.tool_call(event,ctx);
      await hooks.session_tree({{}},ctx);
      const tree=await tools.harness_preview.execute('tree',{{content,cases:[]}},undefined,undefined,ctx);
      const treeInactive=!active.includes('harness_preview');
      await commands.harness.handler('继续维护 D0',ctx);
      await hooks.session_shutdown({{}},ctx);
      const after=await tools.harness_preview.execute('expired',{{content,cases:[]}},undefined,undefined,ctx);
      console.log(JSON.stringify({{before,admitted,blocked,preview,allowed:allowed??null,repeated,changed,normalDuring:normalDuring??null,normalAfter:normalAfter??null,across,acrossWrite:acrossWrite??null,tree,treeInactive,active,after,files:fs.existsSync({json.dumps(str(tmp_path / '.pi'))})}}));
    ''')
    assert result['before']['isError'] and result['after']['isError']
    assert result['admitted'] and result['blocked']['block']
    assert result['preview']['details']['passed'] and result['allowed'] is None
    assert result['repeated']['block'] and result['changed']['block']
    assert result['across']['details']['passed'] and result['acrossWrite'] is None
    assert result['normalDuring'] is None and result['normalAfter'] is None
    assert result['tree']['isError'] and result['treeInactive']
    assert 'harness_preview' not in result['active'] and not result['files']


def test_preview_consumption_is_atomic_after_last_await_and_legacy_confirmation(tmp_path: Path) -> None:
    result = run_bun(f'''
      import fs from 'node:fs'; import path from 'node:path'; import {{AsyncLocalStorage}} from 'node:async_hooks';
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / 'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}},commands={{}},tools={{}};let active=['read','write'];
      register({{on:(n,f)=>hooks[n]=f,registerEntryRenderer(){{}},registerMessageRenderer(){{}},registerCommand:(n,c)=>commands[n]=c,
        registerTool:t=>tools[t.name]=t,getActiveTools:()=>active,setActiveTools:t=>active=t,getCommands:()=>[],sendMessage(){{}},appendEntry(){{}}}});
      const cwd={json.dumps(str(tmp_path))},target=path.join(cwd,'.pi/harness.json');
      fs.mkdirSync(path.dirname(target),{{recursive:true}});
      const content=JSON.stringify({{rules:[{{id:'traffic',text:'D0',instructions:'confirm volume first'}}]}});
      fs.writeFileSync(target,content);
      const ctx={{cwd,hasUI:true,ui:{{notify(){{}},select:async()=> 'Allow once'}}}};
      const event=i=>({{toolName:'write',toolCallId:'write-'+i,input:{{path:target,content}}}});
      const preview=()=>tools.harness_preview.execute('preview',{{content,cases:[]}},undefined,undefined,ctx);
      await commands.harness.handler('维护 D0',ctx);await preview();
      const original=fs.promises.lstat.bind(fs.promises);let arrivals=0,release,firstArrived;const barrier=new Promise(r=>release=r),firstAtFinal=new Promise(r=>firstArrived=r);
      const ownership=new AsyncLocalStorage();
      // Each admitted call reads its predecessor once, then rechecks on finalization.
      // Global ordinal reads assume an IO ordering and can strand the second call.
      fs.promises.lstat=async(...args)=>{{const value=await original(...args);const call=ownership.getStore();if(args[0]===target&&call&&++call.reads===2){{if(++arrivals===1)firstArrived();else release();await barrier;}}return value;}};
      const first=ownership.run({{reads:0}},()=>hooks.tool_call(event(1),ctx));
      await firstAtFinal; // Force the ordering that stranded the old global-read barrier.
      const second=ownership.run({{reads:0}},()=>hooks.tool_call(event(2),ctx));
      const parallel=await Promise.all([first,second]);
      fs.promises.lstat=original;
      fs.mkdirSync(process.env.PI_CODING_AGENT_DIR,{{recursive:true}});
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'harness.json'),JSON.stringify({{policies:[{{name:'confirm-write',tools:['write'],paths:['content'],pattern:'traffic',action:'confirm',reason:'confirm'}}],disabled:[],skillPrompts:{{}}}}));
      await preview();const confirmed=await hooks.tool_call(event(3),ctx);const reused=await hooks.tool_call(event(4),ctx);
      await preview();fs.writeFileSync(target,JSON.stringify({{rules:[]}}));const stale=await hooks.tool_call(event(5),ctx);
      console.log(JSON.stringify({{arrivals,parallel:parallel.map(x=>x??null),confirmed:confirmed??null,reused,stale,unchanged:fs.readFileSync(target,'utf8')}}));
    ''')
    assert result['arrivals'] == 2
    assert sum(item is None for item in result['parallel']) == 1
    assert sum(bool(item and item.get('block')) for item in result['parallel']) == 1
    assert result['confirmed'] is None and result['reused']['block']
    assert result['stale']['block'] and json.loads(result['unchanged']) == {'rules': []}


def test_preview_renderer_is_quiet_and_preserves_result_at_narrow_width() -> None:
    result = run_bun('''
      import {visibleWidth} from '@earendil-works/pi-tui';
      import register from './packages/continual-learning/extensions/guardrails.ts';
      const tools={};register({on(){},registerEntryRenderer(){},registerCommand(){},getCommands:()=>[],registerTool:t=>tools[t.name]=t});
      const tool=tools.harness_preview, theme={fg:(_c,t)=>t,bg:(_c,t)=>t,bold:t=>t};
      const component=tool.renderResult({content:[{type:'text',text:'complete candidate must stay out of UI'}],details:{passed:true,errors:[],cases:[{}]}},{expanded:false,isPartial:false},theme,{isError:false});
      const wide=component.render(120),narrow=component.render(48);
      const checking=tool.renderResult({content:[]},{isPartial:true},theme,{}).render(48);
      const rejected=tool.renderResult({content:[{type:'text',text:JSON.stringify({passed:false,raw:'must not dump JSON'})}],details:{passed:false,errors:['selector mismatch'],cases:[{}]}},{expanded:false,isPartial:false},theme,{isError:true}).render(48);
      console.log(JSON.stringify({shell:tool.renderShell,call:tool.renderCall().render(48),wide,narrow,widths:narrow.map(visibleWidth),checking,rejected}));
    ''')
    assert result['shell'] == 'self' and result['call'] == []
    assert 'verified' in '\n'.join(result['wide']) and 'verified' in '\n'.join(result['narrow'])
    assert all(width <= 48 for width in result['widths'])
    assert 'complete candidate' not in '\n'.join(result['wide'])
    assert 'rejected' not in '\n'.join(result['checking'])
    assert 'rejected' in '\n'.join(result['rejected'])
    assert 'must not dump JSON' not in '\n'.join(result['rejected'])
    assert '{' not in '\n'.join(result['rejected'])


def test_new_bash_rule_requires_parent_bound_command_evidence() -> None:
    result = run_bun('''
      import {previewHarnessCandidate} from './packages/continual-learning/extensions/harness-authoring-preview.ts';
      const content=JSON.stringify({rules:[{id:'gate',bash:'^git push$',message:'confirm',action:'confirm'}]});
      const cases=[{ruleId:'gate',input:'git push',matches:true},{ruleId:'gate',input:'git status',matches:false}];
      console.log(JSON.stringify({invented:previewHarnessCandidate(content,cases,new Set()),
        grounded:previewHarnessCandidate(content,cases,new Set(),undefined,new Set(['git push'])),
        wrong:previewHarnessCandidate(content,cases,new Set(),undefined,new Set(['git status'])),
        unchanged:previewHarnessCandidate(content,[],new Set(),JSON.parse(content))}));
    ''')
    assert not result['invented']['passed'] and not result['wrong']['passed']
    assert result['grounded']['passed'] and result['unchanged']['passed']


def test_parent_command_examples_exclude_failed_claimed_and_duplicate_calls() -> None:
    result = run_bun('''
      import {harnessCommandExamples} from './packages/continual-learning/extensions/guardrails.ts';
      const call=(id,command)=>({type:'message',message:{role:'assistant',content:[{type:'toolCall',name:'bash',id,arguments:{command}}]}});
      const done=(toolCallId,isError)=>({type:'message',message:{role:'toolResult',toolName:'bash',toolCallId,isError}});
      const branch=[call('ok','git push'),done('ok',false),call('bad','bad-command'),done('bad',true),
        call('dup','old-command'),done('dup',false),call('dup','new-command'),done('dup',false),
        {type:'message',message:{role:'assistant',content:[{type:'text',text:'I executed imaginary-command'}]}}];
      console.log(JSON.stringify([...harnessCommandExamples('guard `quoted command`',{sessionManager:{getBranch:()=>branch}})]));
    ''')
    assert sorted(result) == ['git push', 'quoted command']


# --- Merged from test_harness_authoring_safety.py ---
import json
from pathlib import Path

import pytest

from support import isolated_run_bun as run_bun


@pytest.mark.parametrize('rule_request', ['Every project change must preserve semantics', 'Make the popup better', '--local unknown semantic interception'])
def test_command_never_precreates_a_target_before_expressibility(tmp_path: Path, rule_request: str) -> None:
    result = run_bun(f'''
      import fs from 'node:fs';
      process.env.PI_CODING_AGENT_DIR = {json.dumps(str(tmp_path / 'agent'))};
      const {{default: register}} = await import('./packages/continual-learning/extensions/guardrails.ts');
      const commands = {{}}; const messages = [];
      register({{on(){{}}, registerEntryRenderer(){{}}, registerCommand:(n,c)=>commands[n]=c,
        getCommands:()=>[], sendMessage:(message)=>messages.push(message.content)}});
      await commands.harness.handler({json.dumps(rule_request)}, {{cwd:{json.dumps(str(tmp_path))},ui:{{notify(){{}}}}}});
      console.log(JSON.stringify({{files:fs.readdirSync({json.dumps(str(tmp_path))}),messages}}));
    ''')
    assert result['files'] == []
    assert len(result['messages']) == 1
    assert 'no file writes' in result['messages'][0]


def test_prompt_orders_assessment_before_one_complete_write_and_safe_verification() -> None:
    result = run_bun('''
      import {buildHarnessRulePrompt} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(buildHarnessRulePrompt('fullscreen popup means an overlay relationship', '/tmp/project/.pi/harness.json')));
    ''')
    assert result.index('Read the exact target') < result.index('Assess expressibility') < result.index('Write once') < result.index('Read back')
    assert 'no preliminary empty file' in result
    assert 'no file writes' in result
    assert 'does not authorize' in result and 'AGENTS.md' in result
    assert 'non-executing evaluator' in result and 'dangerous' in result
    assert 'opacity, input, or scroll' not in result
    assert 'fullscreen popup' not in result.split('User request:')[0]
    assert 'Preserve the user' in result and 'clarify' in result
    assert 'explicit user authorization' in result
    assert len(result) < 6500


def test_invalid_flat_guidance_is_rejected_without_mutation() -> None:
    result = run_bun('''
      import {validateHarnessWrite} from './packages/continual-learning/extensions/guardrails.ts';
      const prior = {rules:[{id:'bad',skill:'unknown',instructions:'overlay'},{id:'ok',skill:'known',instructions:'valid'}]};
      const before=JSON.stringify(prior);
      console.log(JSON.stringify({errors:validateHarnessWrite({content:before},new Set(['known']),prior),unchanged:JSON.stringify(prior)===before}));
    ''')
    assert result['errors'] and result['unchanged']


def test_registry_rejects_unknown_names_without_hiding_valid_siblings() -> None:
    result = run_bun('''
      import {mergeLayers} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const config=mergeLayers([{source:'project',rules:[{id:'bad',skill:'unknown',instructions:'inert'},{id:'ok',skill:'known',instructions:'valid'}]}],new Set(['known']));
      console.log(JSON.stringify({ids:config.rules.map(r=>r.id),errors:config.errors}));
    ''')
    assert result['ids'] == ['ok']
    assert any('unknown' in error for error in result['errors'])


def test_global_personal_write_is_blocked(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / 'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}};
      register({{on:(n,f)=>hooks[n]=f,registerEntryRenderer(){{}},registerCommand(){{}},getCommands:()=>[]}});
      console.log(JSON.stringify(await hooks.tool_call({{toolName:'write',input:{{path:{json.dumps(str(tmp_path / 'agent/harness.local.json'))},content:'{{}}'}}}},{{cwd:{json.dumps(str(tmp_path))}}})));
    ''')
    assert result['block'] is True
    assert result['reason'].startswith('Use ~/.pi/agent/harness.json')


def test_first_resource_safeguard_request_carries_absent_target_and_supported_path(tmp_path: Path) -> None:
    result = run_bun(f'''
      import fs from 'node:fs';
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / 'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const commands={{}},messages=[];
      register({{on(){{}},registerEntryRenderer(){{}},registerCommand:(n,c)=>commands[n]=c,
        getCommands:()=>[],sendMessage:m=>messages.push(m)}});
      await commands.harness.handler('避免后续 D0 的流量被打爆',{{cwd:{json.dumps(str(tmp_path))},ui:{{notify(){{}}}}}});
      console.log(JSON.stringify({{messages,files:fs.readdirSync({json.dumps(str(tmp_path))})}}));
    ''')
    assert result['files'] == []
    assert len(result['messages']) == 1
    prompt = result['messages'][0]['content']
    assert 'Target state checked by the parent: absent' in prompt
    assert 'Missing configuration is not a blocker' in prompt
    assert 'scoped text guidance' in prompt
    assert 'Do not invent' in prompt and 'rate limit' in prompt
    assert 'ask one concise' in prompt
    assert '避免后续 D0 的流量被打爆' in prompt


def test_native_first_run_fixture_enforces_exact_target_boundary(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_HARNESS_REAL='1';
      process.env.PI_HARNESS_SCHEMA_DOCS=JSON.stringify(['/tmp/public-sdk/README.md']);
      const {{default:register}}=await import('./packages/continual-learning/tests/harness-first-run-fixture.ts');
      const hooks={{}},events=[];
      register({{on:(n,f)=>(hooks[n]??=[]).push(f),registerEntryRenderer(){{}},registerCommand(){{}},
        getCommands:()=>[],appendEntry:(type,data)=>events.push({{type,data}})}});
      const gate=hooks.tool_call.at(-1);
      const target=process.cwd()+'/.pi/harness.json';
      const docRead=gate({{toolName:'read',input:{{path:'/tmp/public-sdk/README.md'}}}});
      const docWrite=gate({{toolName:'write',input:{{path:'/tmp/public-sdk/README.md',content:'x'}}}});
      const results=[gate({{toolName:'read',input:{{path:'/tmp/host-private'}}}}),
        gate({{toolName:'write',input:{{path:'/tmp/production',content:'x'}}}}),
        gate({{toolName:'bash',input:{{command:'true'}}}}),
        gate({{toolName:'read',input:{{path:target,offset:1}}}}),
        gate({{toolName:'read',input:{{path:'.pi/harness.json'}}}}),
        gate({{toolName:'write',input:{{path:target,content:'{{"rules":[]}}'}}}}),
        gate({{toolName:'write',input:{{path:target,content:'{{"rules":[]}}'}}}})];
      process.env.PI_HARNESS_FOLLOWUP='1';
      register({{on:(n,f)=>(hooks[n]??=[]).push(f),registerEntryRenderer(){{}},registerCommand(){{}},getCommands:()=>[],appendEntry:(type,data)=>events.push({{type,data}})}});
      const followup=hooks.tool_call.at(-1)({{toolName:'write',input:{{path:target,content:'{{"rules":[]}}'}}}});
      console.log(JSON.stringify({{results,events,followup,docRead:docRead??null,docWrite}}));
    ''')
    assert all(row and row['block'] for row in result['results'][:4])
    assert result['results'][4:6] == [None, None]
    assert result['results'][6]['block']
    assert len(result['events']) == 7
    assert result['docRead'] is None and result['docWrite']['block']
    assert result['followup']['block']


def test_regex_json_examples_decode_to_the_described_selector() -> None:
    prompt = run_bun('''
      import {buildHarnessRulePrompt} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(buildHarnessRulePrompt('resource safeguard','/tmp/project/.pi/harness.json')));
    ''')
    import re
    examples = [json.loads(value)['text'] for value in re.findall(r'\{"text":"[^\n]*?"\}', prompt)]
    assert len(examples) == 2
    assert re.search(examples[0], 'plain RESOURCE mention')
    assert not re.search(examples[1], 'plain RESOURCE mention')


def test_first_creation_uses_project_relative_access_and_no_scratch_verification() -> None:
    prompt = run_bun('''
      import {buildHarnessRulePrompt} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(buildHarnessRulePrompt('避免后续 D0 的流量被打爆', '/tmp/random-project/.pi/harness.json', 'project shared harness.json (git-tracked)', [], 'absent', '/tmp/random-project')));
    ''')
    assert 'Read the exact target .pi/harness.json' in prompt
    assert 'use write at .pi/harness.json' in prompt
    assert 'Read back .pi/harness.json' in prompt
    assert 'Do not create verification scripts or scratch files' in prompt
    assert 'If no non-executing evaluator is available' in prompt
    assert 'report trigger verification as unverified' in prompt


def test_global_target_outside_project_keeps_exact_absolute_access() -> None:
    prompt = run_bun('''
      import {buildHarnessRulePrompt} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(buildHarnessRulePrompt('resource safeguard', '/tmp/agent/harness.json', 'global shared harness.json', [], 'absent', '/tmp/project')));
    ''')
    assert 'Read the exact target /tmp/agent/harness.json' in prompt
    assert 'use write at /tmp/agent/harness.json' in prompt
    assert 'Read back /tmp/agent/harness.json' in prompt
    assert '../agent' not in prompt


def test_project_protocol_has_one_canonical_tool_path_and_parent_schema_authority() -> None:
    prompt = run_bun('''
      import {buildHarnessRulePrompt} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(buildHarnessRulePrompt('resource safeguard', '/tmp/random-project/.pi/harness.json', 'project shared harness.json (git-tracked)', [], 'absent', '/tmp/random-project')));
    ''')
    assert '/tmp/random-project' not in prompt
    assert 'Use the exact tool path .pi/harness.json; do not expand' in prompt
    assert 'Do not search SDK documentation' in prompt
    assert 'parent validates the complete candidate before write' in prompt


def test_authoring_requires_same_kind_resource_negative_not_only_unrelated_topic() -> None:
    prompt = run_bun('''
      import {buildHarnessRulePrompt} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(buildHarnessRulePrompt('resource safeguard','/tmp/project/.pi/harness.json')));
    ''')
    assert 'another resource with the same action' in prompt
    assert 'Never broaden a resource-specific rule with a standalone incident phrase' in prompt


# --- Merged from test_harness_correction_lifecycle.py ---
from support import isolated_run_bun


def test_owned_correction_requires_exact_semantic_approval_and_user_evidence() -> None:
    value = isolated_run_bun(r'''
      import {validateHarnessPlan, correctionDigest} from './packages/continual-learning/extensions/harness-consolidation.ts';
      import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const prior={id:'learned-test',bash:'^pnpm test',action:'block',message:'Old mistaken block'};
      const quote='Correction: learned-test must allow pnpm test; retire this learned restriction permanently.';
      const snapshot={entries:[{message:{role:'user',content:quote}}]};
      const op={op:'updateRule',rule:{...prior,enabled:false},correction:{eventIndex:0,quote,priorRevision:ruleRevision(prior)},
        cases:{positive:[{bash:'pnpm test',expected:'execute'}],negative:[{bash:'printf safe'}]}};
      const plan={kind:'harness-consolidation-plan',operations:[op],evidence:[{index:0,eventIndex:0,source:'user',quote,count:1}]};
      const options={automatic:true,snapshot,layers:[{source:'project',rules:[prior]}],learnedRules:{[prior.id]:ruleRevision(prior)}};
      const approved={...options,reviewedCorrections:{[prior.id]:correctionDigest(op)}};
      const errors=(p=plan,o=approved)=>validateHarnessPlan(p,o);
      console.log(JSON.stringify({approved:errors(),unreviewed:errors(plan,options),
        manual:errors(plan,{...approved,learnedRules:{}}),
        changed:errors({...plan,operations:[{...op,rule:{...op.rule,message:'changed after review'}}]}),
        assistant:errors(plan,{...approved,snapshot:{entries:[{message:{role:'assistant',content:quote}}]}}),
        tool:errors(plan,{...approved,snapshot:{entries:[{message:{role:'toolResult',content:quote}}]}})}));
    ''')
    assert value['approved'] == []
    for key in ('unreviewed','manual','changed','assistant','tool'):
        assert value[key], (key,value)


def test_owned_text_retirement_uses_prior_selector_as_scope() -> None:
    value = isolated_run_bun(r'''
      import {validateHarnessPlan, correctionDigest} from './packages/continual-learning/extensions/harness-consolidation.ts';
      import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const prior={id:'learned-label',text:'release checklist',instructions:'Always include this checklist.'};
      const quote='Permanently retire learned-label; the release checklist is obsolete.';
      const op={op:'updateRule',rule:{...prior,enabled:false},correction:{eventIndex:0,quote,priorRevision:ruleRevision(prior)},cases:{positive:[{text:['release checklist']}],negative:[{text:['unrelated prose']}]}};
      console.log(JSON.stringify(validateHarnessPlan({kind:'harness-consolidation-plan',operations:[op],evidence:[{index:0,eventIndex:0,source:'user',quote,count:1}]},{automatic:true,snapshot:{entries:[{message:{role:'user',content:quote}}]},layers:[{source:'project',rules:[prior]}],learnedRules:{[prior.id]:ruleRevision(prior)},reviewedCorrections:{[prior.id]:correctionDigest(op)}})));
    ''')
    assert value == []


# --- Merged from test_harness_correction_matching.py ---
from support import isolated_run_bun


def test_correction_explains_both_matchers_without_new_rule_shortcuts_or_authority():
    value = isolated_run_bun(r'''
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const quote='Correction of the prior permanent project constraint: npm --version is now allowed; only Bash commands starting npm test must be blocked. Replace the old broad npm restriction permanently, do not add a second conflicting rule.';
      const priorRule={id:'block-npm-first-executable',bash:'^[ \\t]*npm(?:[ \\t\\n;|&<>]|$(?![\\s\\S]))',action:'block',message:'Permanently block npm first-executable commands.'};
      const rule={...priorRule,bash:'^[ \\t]*npm[ \\t]+test(?:[ \\t\\n;|&<>]|$(?![\\s\\S]))',message:'Only Bash commands starting npm test are blocked; npm --version is allowed.'};
      const baseCandidate={op:'updateRule',rule,priorRule,correction:{eventIndex:0,quote,priorRevision:'a'.repeat(64)},cases:{positive:[{bash:'npm test',expected:'block'}],negative:[{bash:'npm --version',expected:'no-match'}]}};
      const evidence={contextEnabled:true,entries:[{role:'user',content:quote}]},citation=[{index:0,source:'user',quote,count:1}];const results=[];
      for(const mode of ['normal','bounded','uncertain','retired','unknown']){
        const candidate=mode==='retired'?{...baseCandidate,rule:{...rule,enabled:false}}:mode==='unknown'?{...baseCandidate,rule:{...rule,bash:'^npm.*$'},priorRule:{...priorRule,bash:'npm'}}:baseCandidate;
        const requests=[];const judge=createJevJudge({enabled:true,apiKey:'fixture',requestConcurrency:1,...(mode==='bounded'?{maxRequestBytes:64000}:{}),fetch:async(_u,init)=>{
          const r=JSON.parse(init.body);requests.push(r);return new Response(JSON.stringify({model:'jev-1.13.0',usage:{input_tokens:1,output_tokens:1},answers:Object.fromEntries(Object.entries(r.questions).map(([key,q])=>{if(q.type==='noul')return[key,{type:'noul',noul:mode==='uncertain'?.87:1}];const labels=Object.keys(q.criteria),choice=['same','compatible','grounded','independent','unrelated'].find(x=>labels.includes(x))??labels[0];return[key,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(labels.map(x=>[x,+(x===choice)]))}]}))}));
        }});const before=JSON.stringify(candidate);const result=await judge.validate('harness',evidence,[candidate],[],undefined,citation);results.push({mode,decision:result.decision,unchanged:before===JSON.stringify(candidate),candidates:requests.flatMap(r=>Object.values(r.questions).map(q=>q.instructions.candidate)),questions:requests.flatMap(r=>Object.keys(r.questions)),rawRule:rule,priorRule});
      }console.log(JSON.stringify(results));
    ''')
    normal, bounded, uncertain, retired, unknown = value
    assert normal['decision'] == 'allow' and normal['unchanged']
    assert 'supported_0' in normal['questions'] and 'expands_0' in normal['questions']
    assert any(q.startswith('counter_') for q in normal['questions'])
    assert not any(q.startswith(('authority_', 'general_arguments_')) for q in normal['questions'])
    for candidate in normal['candidates']:
        assert candidate['rule'] == normal['rawRule']
        assert candidate['priorRule'] == normal['priorRule']
        assert candidate['selectorMatching']['replacement']['commandWords'] == 'npm test'
        assert candidate['selectorMatching']['predecessor']['commandWords'] == 'npm'
        assert 'never authorization' in candidate['selectorMatching']['meaning']
        assert 'identity' in candidate['recordIdentity']
    assert all('selectorMatching' not in candidate for candidate in bounded['candidates'])
    assert bounded['decision'] == 'allow'
    assert uncertain['decision'] == 'propose'

    assert retired['decision'] == 'allow' and retired['unchanged']
    for candidate in retired['candidates']:
        assert candidate['rule']['enabled'] is False
        assert 'disabled rule does not restrict' in candidate['selectorMatching']['meaning']
    assert unknown['decision'] == 'allow' and unknown['unchanged']
    for candidate in unknown['candidates']:
        assert candidate['rule']['bash'] == '^npm.*$'
        assert candidate['priorRule']['bash'] == 'npm'
        assert 'selectorMatching' not in candidate
    for row in (retired, unknown):
        assert 'supported_0' in row['questions'] and 'expands_0' in row['questions']
        assert any(q.startswith('counter_') for q in row['questions'])
        assert not any(q.startswith(('authority_', 'general_arguments_')) for q in row['questions'])


# --- Merged from test_harness_duplicate_cases.py ---
from support import run_bun


def test_real_duplicate_removes_no_unique_input_and_changes_no_rule_or_evidence() -> None:
    result = run_bun(r'''
      import fs from 'node:fs';
      import {repairDuplicateHarnessCases,previewHarnessRuleCases} from './packages/continual-learning/extensions/harness-consolidation.ts';
      const original=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-harness-duplicate-case.json','utf8')).rejectedPlan;
      const raw=JSON.stringify(original),fixed=repairDuplicateHarnessCases(original);
      const op=fixed.plan.operations[0],prior=original.operations[0];
      const originalInputs=[...prior.cases.positive,...prior.cases.negative].map(x=>x.bash);
      const fixedInputs=[...op.cases.positive,...op.cases.negative].map(x=>x.bash);
      const broad=structuredClone(original);broad.operations[0].rule.bash='.*';
      const noNegative=structuredClone(original);noNegative.operations[0].cases.negative=[{bash:'npm test'}];
      console.log(JSON.stringify({fixed,unchanged:raw===JSON.stringify(original),sameRule:JSON.stringify(prior.rule)===JSON.stringify(op.rule),sameEvidence:JSON.stringify(original.evidence)===JSON.stringify(fixed.plan.evidence),sameInputs:JSON.stringify([...new Set(originalInputs)].sort())===JSON.stringify([...new Set(fixedInputs)].sort()),preview:previewHarnessRuleCases(op.rule,op.cases),broad:repairDuplicateHarnessCases(broad),noNegative:repairDuplicateHarnessCases(noNegative)}));
    ''')
    assert result['unchanged'] and result['sameRule'] and result['sameEvidence'] and result['sameInputs']
    assert len(result['fixed']['corrections']) == 1
    assert result['preview']['passed']
    assert result['broad']['corrections'] == []
    assert result['noNegative']['corrections'] == []


def test_production_normalization_still_requires_semantic_approval_and_retains_failed_plan() -> None:
    from test_harness_plan_repair import run
    for scenario, decision, calls in [('semantic-duplicate-allow', 'allow', 1), ('semantic-duplicate-hold', 'propose', 2)]:
        value = run(scenario)
        assert value['ok'], value
        assert value['semanticDecision'] == decision, value
        assert value['semanticCalls'] == calls, value
        assert all(value['boundScopeChecks'])
        assert len(value['normalizations']) == calls, value
        for record in value['normalizations']:
            proof = record['proof']
            assert record['mode'] == 0o600
            assert len(proof['corrections']) == 1
            assert proof['beforeSha256'] != proof['afterSha256']
            assert proof['originalPlan']['operations'][0]['cases']['negative'][-1]['bash'] == 'retired-compiler build'
        if decision == 'propose':
            assert not value['targetExists']
            assert value['directApply']['outcome'] != 'applied'


# --- Merged from test_harness_flat_ownership.py ---
import json
from pathlib import Path

import pytest

from support import CONSOLIDATION, ENGINE, cases, evidence, isolated_run_bun as run_bun, rule, snapshot


@pytest.mark.parametrize('change', [{'action': 'confirm'}, {'action': None}, {'bash': '^different$'}, {'enabled': False}, {'skill': 'known', 'instructions': 'changed'}])
def test_learned_update_cannot_weaken_or_change_selector(change: dict) -> None:
    result = run_bun(f'''
      import {{validateHarnessPlan}} from '{CONSOLIDATION}';import {{ruleRevision}} from '{ENGINE}';
      const original={json.dumps(rule())};const changed={{...original,...{json.dumps(change)}}};
      if(changed.action===null)delete changed.action;
      console.log(JSON.stringify(validateHarnessPlan({{kind:'harness-consolidation-plan',operations:[{{op:'updateRule',rule:changed,cases:{json.dumps(cases())}}}],evidence:{json.dumps(evidence())}}},{{automatic:true,snapshot:{json.dumps(snapshot())},availableSkills:['known'],layers:[{{source:'project',rules:[original]}}],learnedRules:{{learned:ruleRevision(original)}}}})));
    ''')
    assert any('cannot weaken' in error or 'cannot disable' in error for error in result)


def test_auto_update_guidance_only_preserves_match_and_advances_revision(tmp_path: Path) -> None:
    target = tmp_path/'harness.json'
    result = run_bun(f'''
      import fs from 'node:fs';import {{applyHarnessOps,learnedRuleRevisionsFromConfig}} from '{CONSOLIDATION}';import {{ruleRevision}} from '{ENGINE}';
      const target={json.dumps(str(target))},original={json.dumps(rule())};
      fs.writeFileSync(target,JSON.stringify({{rules:[original],learnedRules:{{learned:{{origin:'consolidation',revision:ruleRevision(original)}}}}}}));
      const changed={{...original,message:'Use the validated safe fixture instead.'}};
      const result=await applyHarnessOps(target,[{{op:'updateRule',rule:changed,cases:{json.dumps(cases())}}}],{{automatic:true,snapshot:{json.dumps(snapshot())},evidence:{json.dumps(evidence())}}});
      const config=JSON.parse(fs.readFileSync(target,'utf8'));
      console.log(JSON.stringify({{result,config,revisions:learnedRuleRevisionsFromConfig(config),expected:ruleRevision(changed)}}));
    ''')
    assert result['result']['ok'] and result['result']['applied'] == ['updateRule:learned']
    assert result['revisions']['learned'] == result['expected']
    assert result['config']['rules'][0]['bash'] == rule()['bash']


@pytest.mark.parametrize('selector, positive, negative, quote', [
    ({'skill':'known','instructions':'Use the skill checklist.'}, {'skill':'known'}, {'skill':'other'}, 'For known, use the skill checklist.'),
    ({'text':'Project A','instructions':'Project A is retired.'}, {'text':['Project A status']}, {'text':['Project B status']}, 'Project A is retired.'),
])
def test_automatic_guidance_requires_narrow_evidence_and_executed_cases(selector: dict, positive: dict, negative: dict, quote: str) -> None:
    result = run_bun(f'''
      import {{validateHarnessPlan}} from '{CONSOLIDATION}';
      const make=(quote,negative)=>{{const snapshot={{entries:[{{message:{{role:'user',content:quote}}}}]}};const plan={{kind:'harness-consolidation-plan',operations:[{{op:'addRule',rule:{{id:'guide',...{json.dumps(selector)}}},cases:{{positive:[{json.dumps(positive)}],negative:[negative]}}}}],evidence:[{{index:0,source:'user',quote,count:1}}]}};return validateHarnessPlan(plan,{{automatic:true,snapshot,availableSkills:['known']}})}};
      console.log(JSON.stringify({{valid:make({json.dumps(quote)},{json.dumps(negative)}),broad:make('Apply all conventions everywhere.',{json.dumps(negative)}),badCase:make({json.dumps(quote)},{json.dumps(positive)})}}));
    ''')
    assert result['valid'] == []
    assert any('narrow quoted evidence' in error for error in result['broad'])
    assert any('must remain unmatched' in error for error in result['badCase'])


def test_auto_apply_reloads_all_layers_and_rejects_new_personal_conflict(tmp_path: Path) -> None:
    project=tmp_path/'project'; (project/'.pi').mkdir(parents=True)
    target=project/'.pi/harness.json'
    (project/'.pi/harness.local.json').write_text(json.dumps({'rules':[{'id':'learned','enabled':False}]}))
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      const {{applyHarnessOps}}=await import('{CONSOLIDATION}');
      console.log(JSON.stringify(await applyHarnessOps({json.dumps(str(target))},[{{op:'addRule',rule:{json.dumps(rule())},cases:{json.dumps(cases())}}}],{{automatic:true,snapshot:{json.dumps(snapshot())},evidence:{json.dumps(evidence())},layers:[]}})));
    ''')
    assert not result['ok'] and 'project.local' in result['error']
    assert not target.exists()


@pytest.mark.parametrize('kind', ['symlink','bad-case','invalid-legacy'])
def test_rejected_automatic_application_changes_no_bytes_or_receipts(tmp_path: Path, kind: str) -> None:
    project=tmp_path/'project'; (project/'.pi').mkdir(parents=True)
    target=project/'.pi/harness.json'; run=tmp_path/'run';run.mkdir()
    before=' {"rules":[]}\n'
    if kind == 'invalid-legacy': before=' {"policies":[{"name":"invalid","pattern":"("}]}\n'
    if kind == 'symlink':
        outside=tmp_path/'outside.json';outside.write_text(before);target.symlink_to(outside)
    else: target.write_text(before)
    proposed_cases=cases()
    if kind == 'bad-case': proposed_cases['negative']=[{'bash':'dangerous-fixture'}]
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      const {{applyHarnessConsolidationPlan}}=await import('{CONSOLIDATION}');
      console.log(JSON.stringify(await applyHarnessConsolidationPlan({{
        target:{json.dumps(str(target))},run:{{manifest:{{cwd:{json.dumps(str(project))},runDir:{json.dumps(str(run))},runId:'r',scopeDigest:'s',snapshotDigest:'d'}}}},
        plan:{{kind:'harness-consolidation-plan',operations:[{{op:'addRule',rule:{json.dumps(rule())},cases:{json.dumps(proposed_cases)}}}],evidence:{json.dumps(evidence())}}},
        validationOptions:{{automatic:true,snapshot:{json.dumps(snapshot())}}}
      }})));
    ''')
    assert result['outcome'] == 'rejected'
    assert target.read_text() == before
    assert list(run.iterdir()) == []


def test_successful_parent_apply_receipts_bind_exact_before_and_after(tmp_path: Path) -> None:
    project=tmp_path/'project';(project/'.pi').mkdir(parents=True)
    target=project/'.pi/harness.json';target.write_text('{"rules":[]}\n')
    run=tmp_path/'run';run.mkdir()
    result=run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      import fs from 'node:fs';import path from 'node:path';import {{createHash}} from 'node:crypto';
      const {{applyHarnessConsolidationPlan}}=await import('{CONSOLIDATION}');
      const target={json.dumps(str(target))},runDir={json.dumps(str(run))};
      const hash=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');const before=hash(target);
      const snapshotPath=path.join(runDir,'snapshot.json');fs.writeFileSync(snapshotPath,JSON.stringify({json.dumps(snapshot())}));
      const result=await applyHarnessConsolidationPlan({{target,run:{{manifest:{{cwd:{json.dumps(str(project))},runDir,runId:'r',scopeDigest:'s',snapshotPath,snapshotDigest:hash(snapshotPath)}}}},plan:{{kind:'harness-consolidation-plan',operations:[{{op:'addRule',rule:{json.dumps(rule())},cases:{json.dumps(cases())}}}],evidence:{json.dumps(evidence())}}},validationOptions:{{automatic:true,snapshot:{json.dumps(snapshot())}}}}});
      console.log(JSON.stringify({{result,before,after:hash(target),pre:JSON.parse(fs.readFileSync(path.join(runDir,'harness-pre-receipt.json'),'utf8')),post:JSON.parse(fs.readFileSync(path.join(runDir,'harness-post-receipt.json'),'utf8'))}}));
    ''')
    assert result['result']['outcome'] == 'applied'
    assert result['pre']['digestBefore'] == result['before']
    assert result['post']['digestAfter'] == result['after']
    assert result['post']['applied'] == ['addRule:learned']


def test_automatic_validation_flags_cannot_skip_evidence_or_cases() -> None:
    result=run_bun(f'''
      import {{validateHarnessPlan}} from '{CONSOLIDATION}';
      console.log(JSON.stringify(validateHarnessPlan({{kind:'harness-consolidation-plan',operations:[{{op:'addRule',rule:{json.dumps(rule())}}}]}},{{automatic:true,requireEvidence:false,requireCases:false}})));
    ''')
    assert any('evidence' in error for error in result)
    assert any('positive and negative' in error for error in result)


# --- Merged from test_harness_flat_unification.py ---
import json
from pathlib import Path

import pytest

from support import CONSOLIDATION, ENGINE, cases, evidence, isolated_run_bun as run_bun, rule, snapshot


def test_legacy_layers_have_read_only_adapter_and_non_error_notices() -> None:
    result = run_bun(f'''
      import {{mergeLayers,evaluateBash}} from '{ENGINE}';
      const config=mergeLayers([{{source:'old',policies:[{{name:'old',pattern:'x',reason:'old'}}],disabled:['inherited'],skillPrompts:{{known:{{prompt:'old',target:'system'}}}}}}]);
      console.log(JSON.stringify({{config,decision:evaluateBash(config,'safe')}}));
    ''')
    assert 'policies' not in result['config'] and 'skillPrompts' not in result['config']
    assert result['config']['rules'] == []
    assert result['config']['errors'] == []
    assert any('legacy' in notice for notice in result['config']['notices'])
    assert result['config']['legacy']['policies'][0]['name'] == 'old'
    assert result['decision']['decision'] == 'execute'


def test_automatic_flat_add_writes_revision_bound_provenance(tmp_path: Path) -> None:
    target = tmp_path / '.pi/harness.json'
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR = {json.dumps(str(tmp_path / 'agent'))};
      import fs from 'node:fs';
      const {{applyHarnessOps}} = await import('{CONSOLIDATION}');
      import {{ruleRevision}} from '{ENGINE}';
      const rule={json.dumps(rule())};
      const result=await applyHarnessOps({json.dumps(str(target))},[{{op:'addRule',rule,cases:{json.dumps(cases())}}}],{{automatic:true,snapshot:{json.dumps(snapshot())},evidence:{json.dumps(evidence())}}});
      const config=fs.existsSync({json.dumps(str(target))})?JSON.parse(fs.readFileSync({json.dumps(str(target))},'utf8')):null;
      console.log(JSON.stringify({{result,config,revision:ruleRevision(rule)}}));
    ''')
    assert result['result']['ok'] is True
    assert result['config']['rules'] == [rule()]
    assert set(result['config']) == {'rules', 'learnedRules'}
    assert result['config']['learnedRules']['learned']['revision'] == result['revision']


@pytest.mark.parametrize('declaration', [{'id': 'taken', 'enabled': False}, {'id': 'taken', 'bash': '('}, {'id': 'taken', 'skill': 'unknown', 'instructions': 'manual'}])
def test_auto_add_conflicts_with_disabled_and_invalid_ids_in_any_layer(declaration: dict) -> None:
    result = run_bun(f'''
      import {{validateHarnessPlan}} from '{CONSOLIDATION}';
      console.log(JSON.stringify(validateHarnessPlan({{kind:'harness-consolidation-plan',operations:[{{op:'addRule',rule:{json.dumps(rule('taken'))},cases:{json.dumps(cases())}}}],evidence:{json.dumps(evidence())}}},{{automatic:true,snapshot:{json.dumps(snapshot())},layers:[{{source:'user',rules:[{json.dumps(declaration)}]}}]}})));
    ''')
    assert any('already' in error or 'conflict' in error for error in result)


def test_manual_edit_does_not_inherit_old_automatic_ownership(tmp_path: Path) -> None:
    target = tmp_path / 'harness.json'
    result = run_bun(f'''
      import fs from 'node:fs';
      import {{applyHarnessOps}} from '{CONSOLIDATION}';
      import {{ruleRevision}} from '{ENGINE}';
      const original={json.dumps(rule())};
      const edited={{...original,message:'User-owned manual revision'}};
      const before=JSON.stringify({{rules:[edited],learnedRules:{{learned:{{origin:'consolidation',revision:ruleRevision(original)}}}}}});
      fs.writeFileSync({json.dumps(str(target))},before);
      const result=await applyHarnessOps({json.dumps(str(target))},[{{op:'updateRule',rule:{{...original,message:'Overwrite manual'}},cases:{json.dumps(cases())}}}],{{automatic:true,snapshot:{json.dumps(snapshot())},evidence:{json.dumps(evidence())}}});
      console.log(JSON.stringify({{result,unchanged:fs.readFileSync({json.dumps(str(target))},'utf8')===before}}));
    ''')
    assert result['result']['ok'] is False and result['unchanged']
    assert 'revision' in result['result']['error'] or 'manually' in result['result']['error']


# --- Merged from test_harness_generalization.py ---
import pytest

from support import PKG_DIR, run_bun


@pytest.fixture(params=["direct", "consolidation"])
def guidance(request: pytest.FixtureRequest) -> str:
    if request.param == "consolidation":
        return ' '.join((PKG_DIR / "prompts" / "harness-consolidator.md").read_text(encoding="utf-8").split())
    return run_bun("""
        import { buildHarnessRulePrompt } from './packages/continual-learning/extensions/guardrails.ts';
        console.log(JSON.stringify(buildHarnessRulePrompt(
          'Preserve business semantics when updating project documents',
          '/tmp/project/.pi/harness.local.json')));
        """)


def test_guidance_generalizes_evidence_before_selecting_mechanism(guidance: str) -> None:
    assert "evidence -> reusable error class -> supported mechanism" in guidance
    assert "document tokens, row numbers, or verbatim phrases" in guidance
    assert "explicit resource-specific user requirement" in guidance
    assert "another same-kind document" in guidance
    assert "rephrasing" in guidance
    assert "unrelated actions remain allowed" in guidance
    assert any(text in guidance for text in ("keeping confirmation scoped to the requested action surface", "blanket confirmation of all writes"))


def test_semantic_guidance_does_not_claim_universal_enforcement(guidance: str) -> None:
    # Only the flat skill-rule guidance surface remains.
    assert "skill rule" in guidance
    # Registered/available-skill discipline (wording differs across the two surfaces).
    assert any(text in guidance for text in ("registered skill", "available skill", "invent a skill"))
    assert "expanded skill invocation" in guidance
    assert "plain read of SKILL.md" in guidance
    assert "not global interception" in guidance
    assert "report the limitation" in guidance.lower()
    assert any(text in guidance for text in ("preserve existing rules unchanged", "preserve existing rules.", "do not add a rule"))


def test_consolidation_does_not_claim_bare_git_matcher_covers_global_options() -> None:
    # Given a whole-family authorization, when generating a restriction, retain
    # legitimate global-option positives instead of weakening the test cases.
    prompt = (PKG_DIR / "prompts" / "harness-consolidator.md").read_text()
    assert "git -C . push --dry-run" in prompt
    assert "git --no-pager push --dry-run" in prompt
    assert "does not establish whole-family coverage" in prompt
    assert "Do not delete valid positive cases" in prompt
    assert "echo git -C . push --dry-run" in prompt


def test_git_template_preserves_bounded_coverage_and_requires_authorization() -> None:
    prompt = (PKG_DIR / 'prompts' / 'harness-consolidator.md').read_text(encoding='utf-8')
    assert r'^git(?:[ \t]+(?:-C[ \t]+\.|-c[ \t]+core\.quotePath=false|--no-pager))*[ \t]+push(?:[ \t]|$(?![\s\S]))' in prompt
    assert 'only a bounded subset of Git invocations' in prompt
    assert 'never infer authorization from the template' in prompt


# --- Merged from test_harness_message_completion.py ---
from support import isolated_run_bun


def test_literal_message_completion_only_extends_one_exact_user_quote() -> None:
    value = isolated_run_bun(r'''
      import {completeHarnessLiteralMessages} from './packages/continual-learning/extensions/harness-consolidation.ts';
      const operation={op:'addRule',rule:{id:'block-npm',bash:'^npm(?:[ \\t]|$(?![\\s\\S]))',action:'block',message:'Do not run npm.'},cases:{positive:[{bash:'npm test'}],negative:[{bash:'pnpm test'}]}};
      const quote='Do not run npm. This lasts for future project tasks.';
      const plan={kind:'harness-consolidation-plan',operations:[operation],evidence:[{index:0,source:'user',quote,count:1,eventIndex:0}]};
      const before=JSON.stringify(plan),completed=completeHarnessLiteralMessages(plan);
      const variants=[{...plan,evidence:[...plan.evidence,...plan.evidence]},
        {...plan,evidence:[{...plan.evidence[0],source:'toolResult'}]},
        {...plan,operations:[{...operation,correction:{priorRevision:'old'}}]},
        {...plan,operations:[{...operation,op:'updateRule'}]},
        {...plan,operations:[{...operation,rule:{...operation.rule,bash:'.*npm.*'}}]},
        {...plan,operations:[{...operation,rule:{...operation.rule,message:'Use pnpm.'}}]},
        {...plan,evidence:[{...plan.evidence[0],quote:quote+' api_key=sk-'+'a'.repeat(45)}]}];
      console.log(JSON.stringify({unchanged:before===JSON.stringify(plan),completed,plan,untouched:variants.map(v=>completeHarnessLiteralMessages(v)===v)}));
    ''')
    assert value['unchanged'] and all(value['untouched'])
    old, new = value['plan'], value['completed']
    assert new['operations'][0]['rule']['message'] == old['evidence'][0]['quote']
    new['operations'][0]['rule']['message'] = old['operations'][0]['rule']['message']
    assert new == old


def test_completion_does_not_authorize_temporary_conditional_or_revoked_rules() -> None:
    value = isolated_run_bun(r'''
      import {completeHarnessLiteralMessages} from './packages/continual-learning/extensions/harness-consolidation.ts';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const results=[];
      for(const [tail,authority,counter] of [['Only for this task.','temporary','compatible'],['Unless I approve.','conditional','compatible'],['For future tasks.','lasting','contradicts']]){
        const quote='Do not run npm. '+tail;
        const p=completeHarnessLiteralMessages({kind:'harness-consolidation-plan',operations:[{op:'addRule',rule:{id:'block-npm',bash:'^npm(?:[ \\t]|$(?![\\s\\S]))',action:'block',message:'Do not run npm.'}}],evidence:[{index:0,source:'user',quote,count:1,eventIndex:0}]});
        const questions=[];
        const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async(_url,init)=>{const r=JSON.parse(init.body);questions.push(...Object.keys(r.questions));const answers=Object.fromEntries(Object.entries(r.questions).map(([k,q])=>{const choice=k.startsWith('authority_')?authority:k.startsWith('family_')?'authorized':counter;return[k,{type:'choice',choice,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(x=>[x,x===choice?1:0]))}];}));return new Response(JSON.stringify({model:'jev-1.13.0',answers}));}});
        const verdict=await judge.validate('harness',{contextEnabled:true,entries:[{role:'user',content:quote},{role:'user',content:'The prior restriction is permanently revoked.'}]},p.operations,[],undefined,p.evidence);
        results.push({decision:verdict.decision,questions,message:p.operations[0].rule.message,quote});
      }
      console.log(JSON.stringify(results));
    ''')
    for row in value:
        assert row['message'] == row['quote']
        assert row['decision'] == 'propose'
        assert {'authority_0', 'family_0', 'counter_0_0'} <= set(row['questions'])


def test_completed_message_is_the_candidate_reviewed_stored_and_recorded() -> None:
    from pathlib import Path
    from support import run_bun_script
    row = run_bun_script(Path(__file__).with_name('harness-repair-harness.ts'), 'semantic-message-completion')
    assert row['ok'] and row['directApply']['outcome'] == 'applied'
    assert row['spawned'] == 1 and row['semanticCalls'] == 1
    evidence = row['messageCompletionEvidence']
    before, after = evidence['before'], evidence['after']
    message = after['evidence'][0]['quote']
    assert after['operations'][0]['rule']['message'] == message
    assert evidence['judgedOperations'] == [after['operations']]
    assert evidence['stored']['rules'][0]['message'] == message
    import base64
    import hashlib
    import json
    plan_bytes = json.dumps(after, ensure_ascii=False, separators=(',', ':')).encode()
    assert evidence['receipt']['planDigest'] == hashlib.sha256(plan_bytes).hexdigest()
    recorded = evidence['history'][0]['changes'][0]['after']
    recorded_bytes = base64.b64decode(recorded['bytes'])
    assert json.loads(recorded_bytes)['rules'][0]['message'] == message
    assert evidence['receipt']['digestAfter'] == hashlib.sha256(recorded_bytes).hexdigest()
    after['operations'][0]['rule']['message'] = before['operations'][0]['rule']['message']
    assert before == after


# --- Merged from test_harness_planner_preview.py ---
"""Harness case evaluation is parent-owned; the child tool is retired."""

import json
from pathlib import Path

from support import PKG_DIR, run_bun

_m12_FIXTURE = Path(__file__).parent / 'fixtures/real-harness-case-rejections.json'


def test_real_rejected_cases_are_executable_inside_read_only_parent() -> None:
    frozen = json.loads(_m12_FIXTURE.read_text())
    result = run_bun(f'''
      import {{previewHarnessRuleCases}} from './packages/continual-learning/extensions/harness-consolidation.ts';
      console.log(JSON.stringify({json.dumps(frozen)}.map(x=>previewHarnessRuleCases(x.rule,x.cases))));
    ''')
    for actual, original in zip(result, frozen):
        assert actual['passed'] is False
        assert actual['errors'] == original['parentErrors']


def test_case_preview_is_parent_only_and_child_tool_is_retired() -> None:
    # The parent evaluator survives; the worker registration and both generated
    # planner tool-extension helpers are gone. No child can call a case tool.
    src = (PKG_DIR / "extensions" / "harness-consolidation.ts").read_text(encoding="utf-8")
    assert "export function previewHarnessRuleCases" in src
    assert "TOOL_NAMES.harnessCheckCases" not in src
    assert not (PKG_DIR / "extensions" / "harness-planner-preview.ts").exists()
    planner_read = (PKG_DIR / "extensions" / "planner-read-scope.ts").read_text(encoding="utf-8")
    assert "plannerReadArgs" not in planner_read
    # Parent evaluator still rejects a negative case that matches its own rule.
    result = run_bun(r'''
      import {previewHarnessRuleCases} from './packages/continual-learning/extensions/harness-consolidation.ts';
      const rule={id:'r',bash:'^npm(?:[ \t]|$)',action:'block',message:'use pnpm'};
      const cases={positive:[{bash:'npm test',expected:'block'}],negative:[{bash:'npm test'}]};
      console.log(JSON.stringify(previewHarnessRuleCases(rule,cases)));
    ''')
    assert result['passed'] is False
    assert any('unmatched' in error for error in result['errors'])


# --- Merged from test_harness_project_wrapper.py ---
from support import run_bun


def test_parent_bound_template_covers_same_project_wrappers_only() -> None:
    # Given a parent-bound current project, when proposing a push-family matcher,
    # then retain actual wrapper coverage without matching printed/foreign calls.
    result = run_bun(r'''
      import { projectPushTemplate } from './packages/continual-learning/extensions/harness-command-coverage.ts';
      import { buildHarnessConsolidatorPrompt } from './packages/continual-learning/extensions/planner-prompts.ts';
      const template = projectPushTemplate('/work/mitt');
      if (!template) throw new Error('Missing bounded template');
      const re = new RegExp(template);
      for (const command of ['git push --dry-run', 'cd /work/mitt && git push --dry-run',
        "cd '/work/mitt' && git push origin topic", 'cd "/work/mitt" && git -C . push --dry-run',
        'git -C /work/mitt push --dry-run', "git -C '/work/mitt' push --dry-run",
        'cd . && git --no-pager push --dry-run']) {
        if (!re.test(command)) throw new Error('Missing current-project coverage');
      }
      for (const command of ['cd /work/other && git push --dry-run',
        'cd /work/mitt/../other && git push', "echo 'cd /work/mitt && git push'",
        "printf '%s' 'cd /work/mitt && git push'", 'echo x; cd /work/mitt && git push',
        'cd /work/mitt || git push', 'git\npush', 'git\u00a0push', 'git push\r']) {
        if (re.test(command)) throw new Error('Expanded scope or printed false match');
      }
      const prompt = buildHarnessConsolidatorPrompt({runId:'r', scopeDigest:'s', artifactHash:'h',
        snapshotPath:'/tmp/s', dossierPath:'', repoRoot:'/work/mitt'});
      if (!prompt.includes(template) || !prompt.includes('cd /work/mitt && git push --dry-run')) throw new Error('Planner omitted parent-bound coverage');
      if (projectPushTemplate('/work/a\nb') !== undefined || projectPushTemplate('/work/a$(pwd)') !== undefined
        || projectPushTemplate('relative') !== undefined) throw new Error('Unsupported shell spelling assumed');
      const dotted = new RegExp(projectPushTemplate('/work/a.b')!);
      if (dotted.test('cd /work/axb && git push')) throw new Error('Root not regex escaped');
      console.log(JSON.stringify('ok'));
    ''')
    assert result == 'ok'


# --- Merged from test_harness_readback_rollback.py ---
import json
from pathlib import Path

import pytest

from support import CONSOLIDATION, cases, evidence, isolated_run_bun as run_bun, rule, snapshot


@pytest.mark.parametrize('pipeline', [False, True])
@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('external_change', [False, True])
def test_readback_failure_restores_only_identifiable_parent_write(tmp_path: Path, pipeline: bool, existing: bool, external_change: bool) -> None:
    project=tmp_path/'project'; (project/'.pi').mkdir(parents=True)
    target=project/'.pi/harness.json'; run=tmp_path/'run'; run.mkdir()
    before='  {"rules": []}\n'
    if existing: target.write_text(before)
    external=' {"rules":[{"id":"external","text":"topic","instructions":"External edit"}]}\n'
    result=run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      import {{mock}} from 'bun:test';import fs from 'node:fs';import fsp from 'node:fs/promises';import {{createHash}} from 'node:crypto';
      const target={json.dumps(str(target))};let written=false,failed=false;
      const realRename=fsp.rename.bind(fsp),realReadFile=fsp.readFile.bind(fsp);
      const patched={{...fsp,
        rename:async(from,to)=>{{await realRename(from,to);if(String(to)===target)written=true}},
        readFile:async(file,...args)=>{{
          if(String(file)===target&&written&&!failed){{
            failed=true;
            if({json.dumps(external_change)})fs.writeFileSync(target,{json.dumps(external)});
            throw new Error('injected post-replacement readback failure');
          }}
          return realReadFile(file,...args);
        }}
      }};
      mock.module('node:fs/promises',()=>({{...patched,default:patched}}));
      const {{applyHarnessOps,applyHarnessConsolidationPlan}}=await import('{CONSOLIDATION}');
      const operations=[{{op:'addRule',rule:{json.dumps(rule())},cases:{json.dumps(cases())}}}];
      const validationOptions={{automatic:true,snapshot:{json.dumps(snapshot())},evidence:{json.dumps(evidence())}}};
      const snapshotPath={json.dumps(str(run/'snapshot.json'))};fs.writeFileSync(snapshotPath,JSON.stringify(validationOptions.snapshot));
      const snapshotDigest=createHash('sha256').update(fs.readFileSync(snapshotPath)).digest('hex');
      const result={json.dumps(pipeline)}?await applyHarnessConsolidationPlan({{
        target,run:{{manifest:{{cwd:{json.dumps(str(project))},runDir:{json.dumps(str(run))},runId:'r',scopeDigest:'s',snapshotPath,snapshotDigest}}}},
        plan:{{kind:'harness-consolidation-plan',operations,evidence:validationOptions.evidence}},validationOptions
      }}):await applyHarnessOps(target,operations,validationOptions);
      console.log(JSON.stringify({{result,failed,bytes:fs.existsSync(target)?fs.readFileSync(target,'utf8'):null,postReceipt:fs.existsSync({json.dumps(str(run/'harness-post-receipt.json'))})}}));
    ''')
    assert result['failed'] is True
    assert (result['result'].get('outcome') == 'rejected') if pipeline else result['result']['ok'] is False
    assert 'injected post-replacement readback failure' in result['result']['error']
    assert result['bytes'] == (external if external_change else before if existing else None)
    assert result['postReceipt'] is False


# --- Merged from test_harness_repair_bindings.py ---
from pathlib import Path
from support import run_bun_script

_m15_FIXTURE = Path(__file__).with_name('harness-repair-harness.ts')


def test_semantic_repair_receives_parent_owned_exact_bindings() -> None:
    value = run_bun_script(_m15_FIXTURE, 'semantic-pruned-supported')
    assert value['repairHasImmutableBindings']
    assert value['repairLocksCitationFields']
    assert value['spawned'] == 2
    assert value['semanticCalls'] == 2


def test_protected_field_failures_remain_held_with_precise_categories() -> None:
    for scenario, category in [('semantic-pruned-foreign', 'identity-mismatch'), ('semantic-pruned-requoted', 'citation-mismatch')]:
        value = run_bun_script(_m15_FIXTURE, scenario)
        assert value['spawned'] == 2 and value['semanticCalls'] == 1
        assert value['semanticDecision'] == 'propose'
        assert value['targetExists'] is False
        assert category in value['attempts'][-1]['diagnostic']


# --- Merged from test_harness_skill_registry.py ---
import json
from pathlib import Path

from support import isolated_run_bun as run_bun


def test_skill_rules_use_real_names_and_exact_schema() -> None:
    result = run_bun('''
      import {validateHarnessWrite} from './packages/continual-learning/extensions/guardrails.ts';
      const check=rule=>validateHarnessWrite({content:JSON.stringify({rules:[rule]})},new Set(['known']));
      const good={id:'guide',skill:'known',instructions:'Guide only the known workflow.'};
      console.log(JSON.stringify({good:check(good),unknown:check({...good,skill:'invented'}),bare:check('text'),extra:check({...good,target:'system'}),narrowed:check({...good,userMessagePattern:'^live$'})}));
    ''')
    assert result['good'] == []
    assert all(result[key] for key in ['unknown','bare','extra','narrowed'])


def test_apply_without_registry_fails_closed_for_skill_guidance(tmp_path: Path) -> None:
    result = run_bun(f'''
      import {{applyHarnessOps}} from './packages/continual-learning/extensions/harness-consolidation.ts';
      console.log(JSON.stringify(await applyHarnessOps({json.dumps(str(tmp_path/'harness.json'))},[{{op:'addRule',rule:{{id:'invented',skill:'invented',instructions:'guide'}}}}])));
    ''')
    assert not result['ok'] and not (tmp_path/'harness.json').exists()


# --- Merged from test_harness_user_scope.py ---
"""The user Harness layer follows the project, like private Memory does.

Memory scopes private state per canonical project path, so a rule authored for
one project cannot silently govern another. The user layer is scoped the same
way — in a directory parallel to `memory/`, not inside it, because a Memory root
admits only regular `.md` children and a JSON configuration there fails
consolidation's privacy validation and aborts the run. That failure was hit for
real during development, which is why the placement is asserted rather than
assumed.
"""


from support import isolated_run_bun

SNIPPET = r"""
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const { configPaths, loadLayers } = await import('./packages/continual-learning/extensions/guardrail-config.ts');
      const { escapedProjectPath, assertProjectScopeOwner } = await import('./packages/continual-learning/extensions/memory-paths.ts');
      const agent = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'scoped-harness-')));
      const a = path.join(agent,'a'), b = path.join(agent,'b');
      fs.mkdirSync(path.join(a,'.pi'),{recursive:true});
      fs.mkdirSync(path.join(b,'.pi'),{recursive:true});
      assertProjectScopeOwner(a, agent); assertProjectScopeOwner(b, agent);
      const pathsA = configPaths(a, agent), pathsB = configPaths(b, agent);
      fs.mkdirSync(path.dirname(pathsA.userScoped),{recursive:true});
      fs.writeFileSync(pathsA.userScoped, JSON.stringify({rules:[{id:'only-a',bash:'^only-a',action:'block',message:'A only.'}]}));
      fs.writeFileSync(path.join(agent,'harness.json'), JSON.stringify({rules:[{id:'everywhere',bash:'^everywhere',action:'block',message:'Everywhere.'}]}));
      // A project layer too, so the precedence order is exercised rather than
      // asserted over a two-layer list.
      fs.writeFileSync(path.join(a,'.pi','harness.json'), JSON.stringify({rules:[{id:'shared-a',bash:'^shared-a',action:'block',message:'Shared.'}]}));
      const layersA = loadLayers(a, agent).map((l) => l.source);
      const layersB = loadLayers(b, agent).map((l) => l.source);
      const scopeA = escapedProjectPath(a);
      const memoryRoot = path.join(agent,'memory',scopeA);
      const { mergeLayers, evaluateBash } = await import('./packages/continual-learning/extensions/guardrail-engine.ts');
      const mergedA = mergeLayers(loadLayers(a, agent), []);
      const mergedB = mergeLayers(loadLayers(b, agent), []);
      console.log(JSON.stringify({
        layersA, layersB, scopeA,
        scopedRelative: path.relative(agent, pathsA.userScoped),
        insideMemoryRoot: pathsA.userScoped.startsWith(memoryRoot + path.sep),
        sameScopeKeyAsMemory: path.basename(pathsA.userScoped) === scopeA + '.json',
        distinctPerProject: pathsA.userScoped !== pathsB.userScoped,
        aBlocks: evaluateBash(mergedA, 'only-a build').decision,
        bBlocks: evaluateBash(mergedB, 'only-a build').decision,
        aSeesGlobal: evaluateBash(mergedA, 'everywhere').decision,
        bSeesGlobal: evaluateBash(mergedB, 'everywhere').decision,
      }));
"""


def test_the_user_layer_follows_the_project_like_private_memory() -> None:
    value = isolated_run_bun(SNIPPET)
    # Isolation: a personal rule for one project governs that project only.
    assert "user.scoped" in value["layersA"], value
    assert "user.scoped" not in value["layersB"], value
    assert value["aBlocks"] == "block", value
    assert value["bBlocks"] == "execute", value
    # The all-projects layer still governs both, so scoping added isolation
    # rather than removing a capability.
    assert value["aSeesGlobal"] == "block" and value["bSeesGlobal"] == "block", value
    assert value["distinctPerProject"] is True, value
    # The all-projects user layer is kept, so a cross-project rule still applies.
    assert "user" in value["layersA"] and "user" in value["layersB"], value
    # Nearest layer wins: this project's own file sits above the global one.
    assert value["layersA"].index("user.scoped") > value["layersA"].index("user"), value
    assert value["layersA"].index("project") > value["layersA"].index("user.scoped"), value


def test_the_scoped_layer_reuses_the_memory_scope_key_and_stays_out_of_a_memory_root() -> None:
    value = isolated_run_bun(SNIPPET)
    assert value["sameScopeKeyAsMemory"] is True, value
    # A Memory root admits only regular `.md` children; a JSON configuration
    # beside them fails privacy validation and aborts consolidation outright.
    assert value["insideMemoryRoot"] is False, value
    assert value["scopedRelative"].startswith("harness/"), value


def test_write_and_consolidation_layer_sort_keeps_user_scoped_between_global_and_project() -> None:
    result = isolated_run_bun(r'''
      import { compareHarnessLayers } from './packages/continual-learning/extensions/guardrail-config.ts';
      const layers = [
        { source: 'project.local' },
        { source: 'user' },
        { source: 'project' },
        { source: 'user.scoped' },
      ];
      layers.sort(compareHarnessLayers);
      console.log(JSON.stringify(layers.map(layer => layer.source)));
    ''')
    assert result == ['user', 'user.scoped', 'project', 'project.local']
