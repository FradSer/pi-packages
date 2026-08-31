from __future__ import annotations

import json
import subprocess
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1]
REPO = PKG_DIR.parents[1]
PKG_REL = "packages/continual-learning"


def run_bun(source: str) -> dict[str, object]:
    result = subprocess.run(
        ["bun", "-e", source],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def validate(plan: dict) -> list[str]:
    src = f"""
        import {{ validateHarnessPlan }} from './packages/continual-learning/extensions/harness-consolidation.ts';
        console.log(JSON.stringify(validateHarnessPlan({json.dumps(plan)})));
    """
    return run_bun(src)  # type: ignore[return-value]


def apply_ops(tmp_path: Path, ops: list[dict]) -> tuple[dict, Path]:
    target = tmp_path / "harness.local.json"
    src = f"""
        import {{ applyHarnessOps }} from './packages/continual-learning/extensions/harness-consolidation.ts';
        const result = await applyHarnessOps({json.dumps(str(target))}, {json.dumps(ops)});
        let after = null;
        try {{ after = JSON.parse(await Bun.file({json.dumps(str(target))}).text()); }} catch {{}}
        console.log(JSON.stringify({{ ...result, after }}));
    """
    out = run_bun(src)
    return out, target


def policy(name: str = "evidence-rule") -> dict:
    return {
        "name": name,
        "tools": ["edit", "write"],
        "paths": ["content", "newText"],
        "patterns": ["width:\\s*\\d{3,}px"],
        "action": "block",
        "reason": "use design tokens",
    }


# ── plan validation ───────────────────────────────────────────────────


def valid_plan() -> dict:
    return {
        "kind": "harness-consolidation-plan",
        "version": 1,
        "schemaVersion": 1,
        "operations": [
            {"op": "updatePolicy", "name": "evidence-rule", "policy": policy()},
            {"op": "disablePolicy", "name": "stale-rule"},
            {
                "op": "addSkillPrompt",
                "name": "using-open-artifacts",
                "prompt": "Use coda0.com",
                "target": "system",
                "userMessagePattern": "^publish",
            },
        ],
        "evidence": [
            {"index": 0, "observation": "blocked 3 writes hard-coding px widths", "count": 3},
            {"index": 1, "observation": "stale rule contradicts current guidance twice", "count": 2},
            {"index": 2, "observation": "skill invocation went off-target once", "count": 1},
        ],
    }


def test_valid_plan_with_operations_passes() -> None:
    errs = validate(valid_plan())
    assert errs == []


def test_empty_and_missing_operations_are_verified_noops() -> None:
    assert validate({"kind": "harness-consolidation-plan"}) == []
    assert validate({"kind": "harness-consolidation-plan", "operations": []}) == []


def test_wrong_kind_is_rejected() -> None:
    errs = validate({"kind": "memory-consolidation-plan", "operations": []})
    assert any("kind" in e for e in errs)


def test_operation_overflow_is_rejected() -> None:
    ops = [{"op": "disablePolicy", "name": f"rule-{i}"} for i in range(13)]
    errs = validate({"kind": "harness-consolidation-plan", "operations": ops})
    assert any("maximum" in e for e in errs)


def test_unknown_op_kind_is_rejected() -> None:
    errs = validate({"kind": "harness-consolidation-plan", "operations": [{"op": "deleteEverything"}]})
    assert any("op must be one of" in e for e in errs)


def test_oversized_policy_payload_is_rejected() -> None:
    big = policy()
    big["reason"] = "x" * 9000
    errs = validate({"kind": "harness-consolidation-plan", "operations": [{"op": "addPolicy", "name": "big", "policy": big}]})
    assert any("8192 bytes" in e for e in errs)


def test_policy_operations_require_runtime_supported_schema() -> None:
    legacy = {
        "name": "legacy",
        "action": "confirm",
        "scope": {"commands": ["node live.mjs"]},
        "rule": "check first",
    }
    errs = validate({
        "kind": "harness-consolidation-plan",
        "operations": [{"op": "addPolicy", "name": "legacy", "policy": legacy}],
    })
    assert any("unsupported field(s): scope, rule" in error for error in errs)


def test_skill_prompt_requires_target_and_prompt() -> None:
    errs = validate(
        {"kind": "harness-consolidation-plan", "operations": [{"op": "addSkillPrompt", "name": "s"}]}
    )
    assert any("prompt" in e for e in errs) and any("target" in e for e in errs)


# ── apply semantics ───────────────────────────────────────────────────


def test_apply_creates_layer_file_when_missing(tmp_path: Path) -> None:
    out, _ = apply_ops(tmp_path, [{"op": "addPolicy", "name": "evidence-rule", "policy": policy()}])
    assert out["ok"] is True and out["applied"] == ["addPolicy:evidence-rule"]
    after = out["after"]
    assert after["policies"][0]["name"] == "evidence-rule"
    assert after["disabled"] == [] and after["skillPrompts"] == {}


def test_add_policy_conflict_rejects_whole_plan_without_writing(tmp_path: Path) -> None:
    target = tmp_path / "harness.local.json"
    target.write_text(json.dumps({"policies": [policy("dup")]}), encoding="utf-8")
    before = target.read_bytes()
    ops = [
        {"op": "addPolicy", "name": "fresh", "policy": policy("fresh")},
        {"op": "addPolicy", "name": "dup", "policy": policy("dup")},
    ]
    src = f"""
        import {{ applyHarnessOps }} from './packages/continual-learning/extensions/harness-consolidation.ts';
        const result = await applyHarnessOps({json.dumps(str(target))}, {json.dumps(ops)});
        console.log(JSON.stringify(result));
    """
    conflict = run_bun(src)
    assert conflict["ok"] is False and "already exists" in str(conflict["error"])
    assert target.read_bytes() == before


def test_update_disable_and_skill_prompt_roundtrip(tmp_path: Path) -> None:
    out, _ = apply_ops(
        tmp_path,
        [
            {"op": "addPolicy", "name": "r1", "policy": policy("r1")},
            {"op": "updatePolicy", "name": "r1", "policy": policy("r1") | {"action": "confirm"}},
            {"op": "updatePolicy", "name": "r2", "policy": policy("r2")},
            {"op": "disablePolicy", "name": "r2"},
            {"op": "addSkillPrompt", "name": "sk", "prompt": "p", "target": "user", "userMessagePattern": "^live$"},
            {"op": "removeSkillPrompt", "name": "sk"},
        ],
    )
    assert out["ok"] is True
    after = out["after"]
    assert [p["name"] for p in after["policies"]] == ["r1", "r2"]
    assert after["policies"][0]["action"] == "confirm"
    assert after["disabled"] == ["r2"]
    assert after["skillPrompts"] == {}


def test_skill_prompt_pattern_is_persisted_and_invalid_pattern_is_rejected(tmp_path: Path) -> None:
    out, _ = apply_ops(
        tmp_path,
        [{"op": "addSkillPrompt", "name": "impeccable", "prompt": "p", "target": "system", "userMessagePattern": "^live$"}],
    )
    assert out["ok"] is True
    assert out["after"]["skillPrompts"]["impeccable"]["userMessagePattern"] == "^live$"
    errs = validate({
        "kind": "harness-consolidation-plan",
        "operations": [{"op": "addSkillPrompt", "name": "impeccable", "prompt": "p", "target": "system", "userMessagePattern": "(["}],
        "evidence": [{"index": 0, "observation": "Live prompts were repeatedly misapplied", "count": 2}],
    })
    assert any("userMessagePattern must be a valid regular expression" in error for error in errs)


def test_invalid_existing_json_is_reported_not_overwritten(tmp_path: Path) -> None:
    target = tmp_path / "harness.local.json"
    target.write_text("{not json", encoding="utf-8")
    before = target.read_bytes()
    src = f"""
        import {{ applyHarnessOps }} from './packages/continual-learning/extensions/harness-consolidation.ts';
        const result = await applyHarnessOps({json.dumps(str(target))}, []);
        console.log(JSON.stringify(result));
    """
    out = run_bun(src)
    assert out["ok"] is False and "not valid JSON" in str(out["error"])
    assert target.read_bytes() == before


# ── wiring contracts (source assertions per repo test style) ──────────


def test_command_registered_as_harness_not_guardrails() -> None:
    src = (PKG_DIR / "extensions" / "guardrails.ts").read_text(encoding="utf-8")
    assert 'pi.registerCommand("harness"' in src
    assert 'pi.registerCommand("guardrails"' not in src
    assert "`harness: ${decision.policyName}" in src


def test_consolidate_pipeline_gates_harness_phase() -> None:
    src = (PKG_DIR / "extensions" / "inject-memory.ts").read_text(encoding="utf-8")
    assert 'import { runHarnessConsolidationPhase, shouldRunHarnessPhase } from "./harness-consolidation"' in src
    assert 'shouldRunHarnessPhase(state, opts.noContext)' in src
    assert 'gate !== "run"' in src
    assert "skipped (no-context run)" in src
    assert "await startConsolidationPipeline(ctx, dreamState," in src
    assert src.count("await spawnAsyncConsolidation(ctx, state, opts);") == 1


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
          post: buildHarnessReceipt({{ ...base, phase: "post", digestAfter: "bb", applied: ["disablePolicy:x"] }}),
        }}));
    """
    out = run_bun(src)
    assert out["pre"]["phase"] == "pre" and "applied" not in out["pre"] and "digestAfter" not in out["pre"]
    assert out["post"]["phase"] == "post"
    assert out["post"]["digestAfter"] == "bb" and out["post"]["applied"] == ["disablePolicy:x"]
    for receipt in (out["pre"], out["post"]):
        assert receipt["kind"] == "harness-consolidation-receipt"
        assert receipt["digestBefore"] == "aa" and receipt["planDigest"] == "pd"


def test_no_cli_dependency_fails_isolated_without_touching_state(tmp_path: Path) -> None:
    target = tmp_path / "harness.local.json"
    target.write_text(json.dumps({"policies": [policy("keep")]}), encoding="utf-8")
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
    result = subprocess.run(["bun", "-e", script], cwd=REPO, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert any("skipped" in n for n in out["notes"])
    assert out["active"] is False and out["generation"] == 0
    assert target.read_bytes() == before


def test_phase_writes_pre_receipt_before_apply_and_post_after(tmp_path: Path) -> None:
    src = (PKG_DIR / "extensions" / "harness-consolidation.ts").read_text(encoding="utf-8")
    pre_idx = src.index('"harness-pre-receipt.json"')
    apply_idx = src.index("const applied = await applyHarnessOps(target, ops);")
    post_idx = src.index('"harness-post-receipt.json"')
    assert pre_idx < apply_idx < post_idx
    assert 'sha256Digest(beforeBytes)' in src and 'sha256Digest(postBytes)' in src
    assert 'postBytes.equals(nowBytes)' in src


def test_procedure_declares_readonly_boundary_and_bounds() -> None:
    proc = (PKG_DIR / "procedures" / "consolidate-harness.md").read_text(encoding="utf-8")
    assert "Do not write, edit, delete, rename, or copy any file." in proc
    assert "At most 12 operations total." in proc
    assert '"harness-consolidation-plan"' in proc
