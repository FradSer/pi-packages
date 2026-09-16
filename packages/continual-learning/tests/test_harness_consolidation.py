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


def validate_against_snapshot(plan: dict, snapshot: dict, **context: object) -> list[str]:
    validation_context = {"snapshot": snapshot, **context}
    src = f"""
        import {{ validateHarnessPlan }} from './packages/continual-learning/extensions/harness-consolidation.ts';
        console.log(JSON.stringify(validateHarnessPlan({json.dumps(plan)}, {json.dumps(validation_context)})));
    """
    return run_bun(src)  # type: ignore[return-value]


def apply_ops(tmp_path: Path, ops: list[dict]) -> tuple[dict, Path]:
    target = tmp_path / "harness.json"
    src = f"""
        import {{ applyHarnessOps }} from './packages/continual-learning/extensions/harness-consolidation.ts';
        const result = await applyHarnessOps({json.dumps(str(target))}, {json.dumps(ops)}, new Set(['sk', 'impeccable']));
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


def test_unknown_skill_prompt_is_rejected_when_registry_is_supplied() -> None:
    src = """
        import { validateHarnessPlan } from './packages/continual-learning/extensions/harness-consolidation.ts';
        const plan = { kind: 'harness-consolidation-plan', operations: [{ op: 'addSkillPrompt', name: 'invented-skill', prompt: 'x', target: 'system' }], evidence: [{ index: 0, observation: 'x', count: 1 }] };
        console.log(JSON.stringify(validateHarnessPlan(plan, { availableSkills: new Set(['known-skill']) })));
    """
    result = subprocess.run(['bun', '-e', src], cwd=REPO, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    errors = json.loads(result.stdout.strip())
    assert any('available registered skill' in error for error in errors)


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


# ── autonomous evidence and evaluator gates ───────────────────────────


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


def executable_policy(name: str = "learned-width", action: str = "block") -> dict:
    return {
        "name": name,
        "tools": ["write"],
        "paths": ["content"],
        "pattern": r"width:\s*\d{3,}px",
        "action": action,
        "reason": "Use design tokens for responsive widths.",
    }


def executable_cases(action: str = "block") -> dict:
    return {
        "positive": [
            {
                "phase": "tool-call",
                "toolName": "write",
                "args": {"content": "width: 480px"},
                "action": action,
            }
        ],
        "negative": [
            {"phase": "tool-call", "toolName": "write", "args": {"content": "width: var(--card-width)"}}
        ],
    }


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
    plan = grounded_plan({"op": "addPolicy", "name": "learned-width", "policy": executable_policy(), "cases": executable_cases()})
    assert validate_against_snapshot(plan, evidence_snapshot()) == []

    invented = grounded_plan(
        {"op": "addPolicy", "name": "invented", "policy": executable_policy("invented"), "cases": executable_cases()},
        source="user",
        quote="The user prefers a universal write prohibition.",
    )
    errors = validate_against_snapshot(invented, evidence_snapshot())
    assert any("quote" in error and "snapshot" in error for error in errors)

    model_quote = grounded_plan(
        {"op": "addPolicy", "name": "model-only", "policy": executable_policy("model-only"), "cases": executable_cases()},
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
        {"op": "addPolicy", "name": "multiline", "policy": executable_policy("multiline"), "cases": executable_cases()},
        source="user",
        quote=multiline,
    )
    assert validate_against_snapshot(user_plan, snapshot) == []

    two_events = grounded_plan(
        {"op": "addPolicy", "name": "two-events", "policy": executable_policy("two-events"), "cases": executable_cases()},
        source="tool",
        quote="blocked once",
    )
    two_events["evidence"][0]["count"] = 2
    assert validate_against_snapshot(two_events, snapshot) == []

    repeated_in_one_event = grounded_plan(
        {"op": "addPolicy", "name": "one-event", "policy": executable_policy("one-event"), "cases": executable_cases()},
        source="tool",
        quote="ordinary outcome",
    )
    repeated_in_one_event["evidence"][0]["count"] = 2
    errors = validate_against_snapshot(repeated_in_one_event, snapshot)
    assert any("count exceeds" in error for error in errors)

    metadata = grounded_plan(
        {"op": "addPolicy", "name": "metadata", "policy": executable_policy("metadata"), "cases": executable_cases()},
        source="tool",
        quote="metadata-only",
    )
    errors = validate_against_snapshot(metadata, snapshot)
    assert any("not grounded" in error for error in errors)

    assistant = grounded_plan(
        {"op": "addPolicy", "name": "assistant", "policy": executable_policy("assistant"), "cases": executable_cases()},
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
        {"op": "addPolicy", "name": "sdk-tool-result", "policy": executable_policy("sdk-tool-result"), "cases": executable_cases()},
        source="tool",
        quote="blocked by sdk policy",
    )
    assert validate_against_snapshot(accepted, snapshot) == []

    metadata = grounded_plan(
        {"op": "addPolicy", "name": "sdk-metadata", "policy": executable_policy("sdk-metadata"), "cases": executable_cases()},
        source="tool",
        quote="write",
    )
    errors = validate_against_snapshot(metadata, snapshot)
    assert any("not grounded" in error for error in errors)

    assistant = grounded_plan(
        {"op": "addPolicy", "name": "sdk-assistant", "policy": executable_policy("sdk-assistant"), "cases": executable_cases()},
        source="tool",
        quote="assistant-only tool claim",
    )
    errors = validate_against_snapshot(assistant, snapshot)
    assert any("not grounded" in error for error in errors)


def test_policy_add_and_update_require_passing_positive_and_negative_evaluator_cases() -> None:
    base = {"op": "addPolicy", "name": "learned-width", "policy": executable_policy()}
    missing = validate_against_snapshot(grounded_plan(base), evidence_snapshot())
    assert any("positive" in error and "negative" in error for error in missing)

    bad_cases = executable_cases()
    bad_cases["negative"][0]["args"]["content"] = "width: 480px"
    errors = validate_against_snapshot(
        grounded_plan({**base, "cases": bad_cases}), evidence_snapshot()
    )
    assert any("negative" in error and ("match" in error or "unmatched" in error) for error in errors)

    valid = validate_against_snapshot(
        grounded_plan({**base, "cases": executable_cases()}), evidence_snapshot()
    )
    assert valid == []


def test_policy_cases_use_the_declared_output_and_artifact_evaluator_phases() -> None:
    output_policy = {
        "name": "output-secret",
        "phase": "output",
        "pattern": r"secret",
        "action": "block",
        "reason": "Do not disclose secrets.",
    }
    output_cases = {
        "positive": [{"phase": "output", "text": "secret value", "action": "block"}],
        "negative": [{"phase": "output", "text": "public value"}],
    }
    output_plan = grounded_plan(
        {"op": "addPolicy", "name": "output-secret", "policy": output_policy, "cases": output_cases}
    )
    assert validate_against_snapshot(output_plan, evidence_snapshot()) == []

    artifact_policy = {
        "name": "artifact-secret",
        "phase": "artifact",
        "artifactPaths": ["dist/app.js"],
        "pattern": r"secret",
        "action": "block",
        "reason": "Do not ship secrets.",
    }
    artifact_cases = {
        "positive": [{"phase": "artifact", "text": "bundle contains secret", "action": "block"}],
        "negative": [{"phase": "artifact", "text": "bundle is public"}],
    }
    artifact_plan = grounded_plan(
        {"op": "addPolicy", "name": "artifact-secret", "policy": artifact_policy, "cases": artifact_cases}
    )
    assert validate_against_snapshot(artifact_plan, evidence_snapshot()) == []

    missing_phase = grounded_plan(
        {
            "op": "addPolicy",
            "name": "missing-phase",
            "policy": executable_policy("missing-phase"),
            "cases": {
                "positive": [{"toolName": "write", "args": {"content": "width: 480px"}}],
                "negative": [{"phase": "tool-call", "toolName": "write", "args": {"content": "safe"}}],
            },
        }
    )
    errors = validate_against_snapshot(missing_phase, evidence_snapshot())
    assert any("phase is required" in error for error in errors)


def test_automatic_learning_rejects_shared_and_manual_rule_changes() -> None:
    layers = [
        {"source": "built-in defaults", "policies": [executable_policy("built-in")]},
        {"source": "user", "policies": [executable_policy("shared")]},
        {"source": "project", "policies": [executable_policy("manual"), executable_policy("learned")]},
    ]
    update_manual = grounded_plan(
        {"op": "updatePolicy", "name": "manual", "policy": executable_policy("manual", "confirm"), "cases": executable_cases("confirm")}
    )
    errors = validate_against_snapshot(
        update_manual, evidence_snapshot(), layers=layers, learnedPolicyNames=["learned"]
    )
    assert any("manual" in error and ("owned" in error or "authored" in error) for error in errors)

    disable_shared = grounded_plan(
        {"op": "disablePolicy", "name": "shared"},
        source="user",
        quote="Please disable the shared rule now.",
    )
    errors = validate_against_snapshot(
        disable_shared, evidence_snapshot(), layers=layers, learnedPolicyNames=["learned"]
    )
    assert any("shared" in error or "protected" in error for error in errors)

    prompt_layers = layers + [{"source": "project", "skillPrompts": {"impeccable": {"prompt": "manual guidance", "target": "system"}}}]
    overwrite_prompt = grounded_plan(
        {"op": "addSkillPrompt", "name": "impeccable", "prompt": "replacement", "target": "system"}
    )
    errors = validate_against_snapshot(
        overwrite_prompt, evidence_snapshot(), layers=prompt_layers, learnedPolicyNames=["learned"]
    )
    assert any("cannot be overwritten" in error for error in errors)


def test_automatic_learning_cannot_weaken_even_with_user_looking_evidence() -> None:
    layers = [{"source": "project", "policies": [executable_policy("learned")]}]
    weaken = grounded_plan(
        {"op": "updatePolicy", "name": "learned", "policy": executable_policy("learned", "confirm"), "cases": executable_cases("confirm")}
    )
    errors = validate_against_snapshot(
        weaken, evidence_snapshot(), layers=layers, learnedPolicyNames=["learned"]
    )
    assert any("cannot weaken" in error for error in errors)

    user_wording = grounded_plan(
        {
            "op": "updatePolicy",
            "name": "learned",
            "policy": executable_policy("learned", "confirm"),
            "cases": executable_cases("confirm"),
        },
        source="user",
        quote="Please weaken the learned width rule to confirmation.",
    )
    user_wording_snapshot = evidence_snapshot() | {
        "entries": evidence_snapshot()["entries"][:1]
        + [{"type": "message_end", "message": {"role": "user", "content": "Please weaken the learned width rule to confirmation."}}]
    }
    errors = validate_against_snapshot(
        user_wording, user_wording_snapshot, layers=layers, learnedPolicyNames=["learned"]
    )
    assert any("cannot weaken" in error for error in errors)


def test_learned_rule_can_receive_a_reason_only_revision() -> None:
    layers = [{"source": "project", "policies": [executable_policy("learned")]}]
    revision = grounded_plan(
        {
            "op": "updatePolicy",
            "name": "learned",
            "policy": executable_policy("learned") | {"reason": "Keep responsive widths tokenized."},
            "cases": executable_cases(),
        },
        source="tool",
        quote="blocked by ui-width policy; use design tokens",
    )
    assert validate_against_snapshot(
        revision, evidence_snapshot(), layers=layers, learnedPolicyNames=["learned"]
    ) == []


def test_learned_rule_scope_changes_are_rejected_as_unproven_weakening() -> None:
    layers = [{"source": "project", "policies": [executable_policy("learned")]}]
    remove_tool = grounded_plan(
        {
            "op": "updatePolicy",
            "name": "learned",
            "policy": executable_policy("learned") | {"tools": ["edit"]},
            "cases": executable_cases(),
        }
    )
    errors = validate_against_snapshot(
        remove_tool, evidence_snapshot(), layers=layers, learnedPolicyNames=["learned"]
    )
    assert any("cannot weaken" in error for error in errors)

    add_require = grounded_plan(
        {
            "op": "updatePolicy",
            "name": "learned",
            "policy": executable_policy("learned") | {"require": {"path": "content", "pattern": "width"}},
            "cases": executable_cases(),
        }
    )
    errors = validate_against_snapshot(
        add_require, evidence_snapshot(), layers=layers, learnedPolicyNames=["learned"]
    )
    assert any("cannot weaken" in error for error in errors)


def test_automatic_apply_records_parent_owned_learned_provenance(tmp_path: Path) -> None:
    op = {"op": "addPolicy", "name": "learned-on-apply", "policy": executable_policy("learned-on-apply"), "cases": executable_cases()}
    evidence = grounded_plan(op)["evidence"]
    target = tmp_path / "harness.json"
    src = f"""
        import {{ applyHarnessOps }} from './packages/continual-learning/extensions/harness-consolidation.ts';
        const result = await applyHarnessOps(
          {json.dumps(str(target))},
          {json.dumps([op])},
          {{ automatic: true, snapshot: {json.dumps(evidence_snapshot())}, evidence: {json.dumps(evidence)} }},
        );
        let after = null;
        try {{ after = JSON.parse(await Bun.file({json.dumps(str(target))}).text()); }} catch {{}}
        console.log(JSON.stringify({{ result, after }}));
    """
    out = run_bun(src)
    assert out["result"]["ok"] is True
    assert out["after"]["learnedPolicies"]["learned-on-apply"]["origin"] == "consolidation"


# ── apply semantics ───────────────────────────────────────────────────


def test_apply_creates_layer_file_when_missing(tmp_path: Path) -> None:
    out, _ = apply_ops(tmp_path, [{"op": "addPolicy", "name": "evidence-rule", "policy": policy()}])
    assert out["ok"] is True and out["applied"] == ["addPolicy:evidence-rule"]
    after = out["after"]
    assert after["policies"][0]["name"] == "evidence-rule"
    assert after["disabled"] == [] and after["skillPrompts"] == {}


def test_add_policy_conflict_rejects_whole_plan_without_writing(tmp_path: Path) -> None:
    target = tmp_path / "harness.json"
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
    target = tmp_path / "harness.json"
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
    assert "Immutable task-slice snapshot" in result["task"]
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
    apply_idx = src.index("const applied = await applyHarnessOps(target, ops,")
    post_idx = src.index('"harness-post-receipt.json"')
    assert pre_idx < apply_idx < post_idx
    assert 'sha256Digest(beforeBytes)' in src and 'sha256Digest(postBytes)' in src
    assert 'postBytes.equals(nowBytes)' in src


def test_harness_planner_uses_package_prompt_and_minimal_readonly_args() -> None:
    src = (PKG_DIR / "extensions" / "harness-consolidation.ts").read_text(encoding="utf-8")
    assert "buildHarnessConsolidatorPrompt" in src
    assert 'minimalPiWorkerArgs(["read", "grep", "find", "ls"])' in src


def test_procedure_declares_readonly_boundary_and_bounds() -> None:
    proc = (PKG_DIR / "prompts" / "harness-consolidator.md").read_text(encoding="utf-8")
    assert "Do not write, edit, delete, rename, or copy any file." in proc
    assert "At most 12 operations total." in proc
    assert '"harness-consolidation-plan"' in proc
