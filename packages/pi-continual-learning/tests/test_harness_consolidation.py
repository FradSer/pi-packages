from __future__ import annotations

import json
import subprocess
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1]
REPO = PKG_DIR.parents[1]


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
        import {{ validateHarnessPlan }} from './packages/pi-continual-learning/extensions/harness-consolidation.ts';
        console.log(JSON.stringify(validateHarnessPlan({json.dumps(plan)})));
    """
    return run_bun(src)  # type: ignore[return-value]


def apply_ops(tmp_path: Path, ops: list[dict]) -> tuple[dict, Path]:
    target = tmp_path / "harness.local.json"
    src = f"""
        import {{ applyHarnessOps }} from './packages/pi-continual-learning/extensions/harness-consolidation.ts';
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


def test_valid_plan_with_operations_passes() -> None:
    errs = validate(
        {
            "kind": "harness-consolidation-plan",
            "version": 1,
            "schemaVersion": 1,
            "operations": [
                {"op": "updatePolicy", "name": "evidence-rule", "policy": policy()},
                {"op": "disablePolicy", "name": "stale-rule"},
                {"op": "addSkillPrompt", "name": "using-open-artifacts", "prompt": "Use coda0.com", "target": "system"},
            ],
            "evidence": [{"index": 0, "observation": "blocked 3 writes", "count": 3}],
        }
    )
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
        import {{ applyHarnessOps }} from './packages/pi-continual-learning/extensions/harness-consolidation.ts';
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
            {"op": "addSkillPrompt", "name": "sk", "prompt": "p", "target": "user"},
            {"op": "removeSkillPrompt", "name": "sk"},
        ],
    )
    assert out["ok"] is True
    after = out["after"]
    assert [p["name"] for p in after["policies"]] == ["r1", "r2"]
    assert after["policies"][0]["action"] == "confirm"
    assert after["disabled"] == ["r2"]
    assert after["skillPrompts"] == {}


def test_invalid_existing_json_is_reported_not_overwritten(tmp_path: Path) -> None:
    target = tmp_path / "harness.local.json"
    target.write_text("{not json", encoding="utf-8")
    before = target.read_bytes()
    src = f"""
        import {{ applyHarnessOps }} from './packages/pi-continual-learning/extensions/harness-consolidation.ts';
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
    assert 'import { runHarnessConsolidationPhase } from "./harness-consolidation"' in src
    assert "state.outcome !== \"completed\"" in src or 'state.outcome !== "completed"' in src
    assert "Harness consolidation needs captured context; skipped (no-context run)." in src
    assert "await startConsolidationPipeline(ctx, dreamState," in src
    assert src.count("await spawnAsyncConsolidation(ctx, state, opts);") == 1


def test_procedure_declares_readonly_boundary_and_bounds() -> None:
    proc = (PKG_DIR / "procedures" / "consolidate-harness.md").read_text(encoding="utf-8")
    assert "Do not write, edit, delete, rename, or copy any file." in proc
    assert "At most 12 operations total." in proc
    assert '"harness-consolidation-plan"' in proc
