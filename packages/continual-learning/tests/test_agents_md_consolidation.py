from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1]
REPO = PKG_DIR.parents[1]
MODULE = "./packages/continual-learning/extensions/agents-md-consolidation.ts"


def js(source: str, env: dict[str, str] | None = None) -> dict[str, object] | list[object]:
    """Run a Bun snippet whose final stdout line is one JSON value."""
    result = subprocess.run(
        ["bun", "-e", source],
        cwd=REPO,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def call_js(body: str, *imports: str) -> dict[str, object] | list[object]:
    """Run a Bun snippet; `body` may be sync or async and must evaluate to one JSON value."""
    import_lines = "".join(f"import {{ {name} }} from '{MODULE}';\n" for name in imports)
    return js(f"{import_lines}const out = await ({body});\nconsole.log(JSON.stringify(out));\n")


def evidence(quote: str, entry_index: int = 0, occurrences: int = 1, kind: str = "gap") -> dict:
    return {"kind": kind, "quote": quote, "entryIndex": entry_index, "occurrences": occurrences}


def add_op(text: str = "- New rule unit", quote: str | None = None, occurrences: int = 2) -> dict:
    return {
        "op": "addUnit",
        "placement": "append",
        "text": text,
        "evidence": [evidence(quote or f"observed {text}", occurrences)],
    }


def rewrite_plan() -> dict:
    return {
        "kind": "agents-md-consolidation-plan",
        "version": 1,
        "schemaVersion": 1,
        "operations": [
            {
                "op": "rewriteUnit",
                "oldText": "- Run tests with npm test",
                "newText": "- Run tests with pnpm test",
                "evidence": [evidence("npm test failed with ERR_PNPM_NO_SCRIPT", kind="wrong")],
            }
        ],
        "report": [{"index": 0, "summary": "switch to pnpm"}],
    }


def extract_skill_plan() -> dict:
    return {
        "kind": "agents-md-consolidation-plan",
        "version": 1,
        "schemaVersion": 1,
        "operations": [
            {
                "op": "extractUnit",
                "oldText": "- Use coda0.com as the default artifacts host",
                "extraction": {
                    "target": "skillRule",
                    "ruleId": "artifact-host",
                    "skillName": "using-open-artifacts",
                    "instructions": "Use coda0.com as the default instance.",
                },
                "rationale": "only matters when that skill is invoked",
                "evidence": [evidence("published to the wrong host", kind="unused")],
            },
            {
                "op": "extractUnit",
                "oldText": "- Regenerate fixtures after schema changes",
                "extraction": {
                    "target": "memory",
                    "memoryName": "fixture-regeneration.md",
                    "description": "Fixtures must be regenerated after schema changes",
                    "type": "project",
                    "classification": "safe",
                },
                "rationale": "durable but too detailed for the always-loaded file",
                "evidence": [evidence("stale fixtures broke the build")],
            },
        ],
    }


# ── plan validation ───────────────────────────────────────────────────


def test_valid_plans_pass() -> None:
    for plan in (rewrite_plan(), extract_skill_plan(), {"kind": "agents-md-consolidation-plan"}):
        plan_json = json.dumps(plan)
        result = call_js(f"validateAgentsMdPlan({plan_json})", "validateAgentsMdPlan")
        assert result["ok"] is True, result


def test_wrong_kind_is_rejected() -> None:
    plan_json = json.dumps({"kind": "memory-consolidation-plan"})
    result = call_js(f"validateAgentsMdPlan({plan_json})", "validateAgentsMdPlan")
    assert result["ok"] is False
    assert any("kind" in str(e) for e in result["errors"])


def test_more_than_five_operations_is_rejected() -> None:
    plan = {**rewrite_plan(), "operations": [add_op(f"- Rule {i}") for i in range(6)]}
    plan_json = json.dumps(plan)
    result = call_js(f"validateAgentsMdPlan({plan_json})", "validateAgentsMdPlan")
    assert result["ok"] is False
    assert any("maximum of 5" in str(e) for e in result["errors"])


def test_operation_without_evidence_is_rejected() -> None:
    plan = {**rewrite_plan(), "operations": [{"op": "removeUnit", "oldText": "- something"}]}
    plan_json = json.dumps(plan)
    result = call_js(f"validateAgentsMdPlan({plan_json})", "validateAgentsMdPlan")
    assert result["ok"] is False
    assert any("evidence" in str(e) for e in result["errors"])


def test_extract_memory_rejects_noncanonical_names_types_and_classifications() -> None:
    base = extract_skill_plan()["operations"][1]
    for bad in (
        {**base, "extraction": {**base["extraction"], "memoryName": "../escape.md"}},
        {**base, "extraction": {**base["extraction"], "memoryName": "MEMORY.md"}},
        {**base, "extraction": {**base["extraction"], "type": "diary"}},
        {**base, "extraction": {**base["extraction"], "classification": "secret"}},
        {**base, "extraction": {key: value for key, value in base["extraction"].items() if key != "classification"}},
    ):
        plan = {**extract_skill_plan(), "operations": [bad]}
        plan_json = json.dumps(plan)
        result = call_js(f"validateAgentsMdPlan({plan_json})", "validateAgentsMdPlan")
        assert result["ok"] is False


def test_extract_pointer_schema_is_optional_bounded_and_extraction_only() -> None:
    base = extract_skill_plan()["operations"][1]
    pointer = "- For schema changes, read @.memory/fixture-regeneration.md."
    for replacement in (pointer, "x" * 500):
        op = {**base, "replacementText": replacement}
        result = call_js(f"validateAgentsMdPlan({json.dumps({'kind': 'agents-md-consolidation-plan', 'operations': [op]})})", "validateAgentsMdPlan")
        assert result["ok"] is True
        assert result["operations"][0]["replacementText"] == replacement
    for replacement in (None, 1, "", " ", "x" * 501, "- One\n- Two", "route\rhidden", "route\u2028hidden"):
        op = {**base, "replacementText": replacement}
        result = call_js(f"validateAgentsMdPlan({json.dumps({'kind': 'agents-md-consolidation-plan', 'operations': [op]})})", "validateAgentsMdPlan")
        assert result["ok"] is False, replacement
    for op in (rewrite_plan()["operations"][0], add_op(), {"op": "removeUnit", "oldText": "x", "evidence": [evidence("x")]}):
        op["replacementText"] = pointer
        result = call_js(f"validateAgentsMdPlan({json.dumps({'kind': 'agents-md-consolidation-plan', 'operations': [op]})})", "validateAgentsMdPlan")
        assert result["ok"] is False


def test_memory_description_is_short_nonblank_and_single_line() -> None:
    base = extract_skill_plan()["operations"][1]
    for description, expected in (("Schema changes: regenerate fixtures before testing", True), ("x" * 120, True), ("x" * 121, False), (" ", False), ("Schema\nextra: injected", False), ("Schema\rhidden", False)):
        op = {**base, "extraction": {**base["extraction"], "description": description}}
        result = call_js(f"validateAgentsMdPlan({json.dumps({'kind': 'agents-md-consolidation-plan', 'operations': [op]})})", "validateAgentsMdPlan")
        assert result["ok"] is expected, description


def test_skill_extraction_requires_flat_rule_fields_and_rejects_obsolete_targets() -> None:
    base = extract_skill_plan()["operations"][0]
    for extraction in (
        {key: value for key, value in base["extraction"].items() if key != "ruleId"},
        {**base["extraction"], "ruleId": " "},
        {**base["extraction"], "ruleId": "x" * 129},
        {**base["extraction"], "skillName": "invented skill"},
        {**base["extraction"], "instructions": " "},
        {**base["extraction"], "instructions": "x" * 2001},
        {"target": "skillPrompt", "skillName": "using-open-artifacts", "prompt": "obsolete", "promptTarget": "system"},
        {"target": "projectDoc", "path": "docs/rules.md"},
    ):
        plan = {"kind": "agents-md-consolidation-plan", "operations": [{**base, "extraction": extraction}]}
        result = call_js(f"validateAgentsMdPlan({json.dumps(plan)})", "validateAgentsMdPlan")
        assert result["ok"] is False, extraction


# ── quote verification ────────────────────────────────────────────────

SNAPSHOT_OBJECT = {
    "entries": [
        {"message": {"role": "user", "content": [{"type": "text", "text": "the build failed because\nstale fixtures broke the build again"}]}},
        {"type": "tool_execution_end", "result": "npm test failed with ERR_PNPM_NO_SCRIPT"},
        {"message": {"role": "assistant", "content": "assistant invented evidence"}},
        {"type": "tool_execution_end", "toolName": "write", "policyName": "metadata-only", "result": "ordinary result"},
        {"message": {"role": "toolResult", "content": [{"type": "text", "text": "SDK tool result evidence"}]}},
        {"message": {"role": "user", "content": "stale fixtures broke the build again"}},
    ]
}
SNAPSHOT = json.dumps(SNAPSHOT_OBJECT)


def test_quote_verification_requires_indexed_user_or_tool_result_content() -> None:
    snapshot_json = json.dumps(SNAPSHOT)
    cases = [
        ("stale fixtures broke the build again", 0, True),
        ("npm test failed with ERR_PNPM_NO_SCRIPT", 1, True),
        ("SDK tool result evidence", 4, True),
        ("assistant invented evidence", 2, False),
        ("metadata-only", 3, False),
        ("ordinary result", 0, False),
        ("fixtures were outdated and broke things", 0, False),
    ]
    for quote, entry_index, expected in cases:
        result = call_js(
            f"quoteInSnapshot({json.dumps(quote)}, {snapshot_json}, {entry_index})",
            "quoteInSnapshot",
        )
        assert result is expected, (quote, entry_index)


def test_verify_plan_quotes_drops_unindexed_and_unverified_operations() -> None:
    ops = [
        {**add_op("- Keep me"), "evidence": [evidence("stale fixtures broke the build again", 0)]},
        {**add_op("- Wrong entry"), "evidence": [evidence("ordinary result", 0)]},
        {**add_op("- Assistant"), "evidence": [evidence("assistant invented evidence", 2)]},
    ]
    result = call_js(
        f"(() => {{ const r = verifyPlanQuotes({json.dumps(ops)}, {json.dumps(SNAPSHOT)}); "
        f"return {{ kept: r.operations.length, dropped: r.dropped, first: r.operations[0]?.evidence?.[0] }}; }})()",
        "verifyPlanQuotes",
    )
    assert result["kept"] == 1
    assert result["dropped"] == [1, 2]
    assert result["first"]["entryIndex"] == 0


def test_add_unit_counts_distinct_snapshot_entries_not_planner_occurrences() -> None:
    cases = [
        (
            {**add_op(occurrences=99), "evidence": [evidence("npm test failed with ERR_PNPM_NO_SCRIPT", 1, 99)]},
            False,
        ),
        (
            {**add_op(), "evidence": [evidence("stale fixtures broke the build again", 0), evidence("stale fixtures broke the build again", 5)]},
            True,
        ),
        (
            {**add_op(), "evidence": [evidence("stale fixtures broke the build again", 0), evidence("stale fixtures broke the build again", 0)]},
            False,
        ),
        ({"op": "removeUnit", "oldText": "- x", "evidence": [evidence("stale fixtures broke the build again", 0)]}, True),
    ]
    for op, expected in cases:
        verified = call_js(
            f"(() => {{ const r = verifyPlanQuotes([{json.dumps(op)}], {json.dumps(SNAPSHOT)}); return r.operations[0] ?? null; }})()",
            "verifyPlanQuotes",
        )
        result = call_js(f"addUnitEvidenceSufficient({json.dumps(verified)})", "addUnitEvidenceSufficient") if verified else False
        assert result is expected, (op, expected, result)


def test_evidence_schema_requires_snapshot_entry_index() -> None:
    plan = rewrite_plan()
    del plan["operations"][0]["evidence"][0]["entryIndex"]
    result = call_js(f"validateAgentsMdPlan({json.dumps(plan)})", "validateAgentsMdPlan")
    assert result["ok"] is False
    assert any("entryIndex" in str(error) for error in result["errors"])


# ── simulation ────────────────────────────────────────────────────────

DOC = "# Guide\n\n- Run tests with npm test\n- Use coda0.com\n"


def simulate(doc: str, ops: list[dict]) -> dict:
    doc_json = json.dumps(doc)
    ops_json = json.dumps(ops)
    return call_js(f"simulateAgentsOps({doc_json}, {ops_json})", "simulateAgentsOps")  # type: ignore[return-value]


def test_rewrite_remove_roundtrip() -> None:
    out = simulate(DOC, [
        {
            "op": "rewriteUnit",
            "oldText": "- Run tests with npm test",
            "newText": "- Run tests with pnpm test",
            "evidence": [evidence("x")],
        },
        {"op": "removeUnit", "oldText": "\n- Use coda0.com", "evidence": [evidence("y", kind="unused")]},
    ])
    assert out["ok"] is True
    assert out["doc"] == "# Guide\n\n- Run tests with pnpm test\n"
    assert len(out["applied"]) == 2


def test_add_append_and_anchor_positions() -> None:
    out = simulate(DOC, [
        add_op("- Appended rule"),
        {**add_op("- Before rule"), "anchor": "# Guide", "position": "before"},
        {**add_op("- After rule"), "anchor": "- Use coda0.com", "position": "after"},
    ])
    assert out["ok"] is True
    doc = out["doc"]
    lines = doc.strip().splitlines()
    assert lines[0] == "- Before rule"
    assert "- Appended rule" in doc
    after_index = next(i for i, l in enumerate(lines) if l == "- After rule")
    anchor_index = next(i for i, l in enumerate(lines) if l == "- Use coda0.com")
    assert after_index == anchor_index + 1
    assert "- Run tests with npm test" in doc


def test_ambiguous_or_missing_matches_fail_closed() -> None:
    dup = simulate("# T\n\n- x\n- x\n", [{"op": "removeUnit", "oldText": "- x", "evidence": [evidence("q")]}])
    assert dup["ok"] is False
    assert "more than once" in str(dup["error"])
    missing = simulate(DOC, [{"op": "removeUnit", "oldText": "- not present", "evidence": [evidence("q")]}])
    assert missing["ok"] is False
    assert "does not match" in str(missing["error"])


def test_extraction_replaces_only_exact_unit_and_fingerprints_the_pointer() -> None:
    base = extract_skill_plan()["operations"][1]
    pointer = "- For schema changes, read @.memory/fixture-regeneration.md."
    op = {**base, "replacementText": pointer}
    doc = "# Rules\n\n- Common cross-task rule\n" + base["oldText"] + "\n- Unrelated task rule\n"
    out = simulate(doc, [op])
    assert out["ok"] is True
    assert out["doc"] == doc.replace(base["oldText"], pointer)
    assert simulate(doc, [base])["doc"] == doc.replace(base["oldText"], "")
    for bad_doc in (doc + base["oldText"], "# No anchor\n"):
        assert simulate(bad_doc, [op])["ok"] is False
    fingerprints = call_js(f"[{json.dumps(base)}, {json.dumps(op)}].map(fingerprintOp)", "fingerprintOp")
    assert fingerprints[0] != fingerprints[1]


# ── budget ────────────────────────────────────────────────────────────


def test_budget_allows_growth_only_below_budget() -> None:
    calls = {}
    for name, args in {
        "growUnderBudget": (100, 200, 1000),
        "exceedBudget": (100, 1500, 1000),
        "zeroSumAtBudget": (1000, 900, 1000),
        "rejectGrowthAtBudget": (1000, 1100, 1000),
    }.items():
        result = call_js(f"budgetAllows({args[0]}, {args[1]}, {args[2]})", "budgetAllows")
        calls[name] = result
    assert calls["growUnderBudget"] is True
    assert calls["exceedBudget"] is False
    assert calls["zeroSumAtBudget"] is True
    assert calls["rejectGrowthAtBudget"] is False



# ── user-level protection ─────────────────────────────────────────────


def test_target_resolution_and_user_level_guard(tmp_path: Path) -> None:
    # A symlinked project directory that physically points at the agent dir
    # must still be refused — even when the target file does not exist yet.
    agent_dir = tmp_path / "agent-dir"
    agent_dir.mkdir()
    link = tmp_path / "link-to-agent"
    link.symlink_to(agent_dir, target_is_directory=True)
    result = call_js(
        "(() => { const normal = resolveAgentsTargetFile('/repo', '/home/u/.pi/agent'); "
        "const overlap = resolveAgentsTargetFile('/home/u/.pi/agent', '/home/u/.pi/agent'); "
        f"const symlinked = resolveAgentsTargetFile({json.dumps(str(link))}, {json.dumps(str(agent_dir))}); "
        "return { normalPath: normal.path, normalSkip: normal.skipReason ?? null, "
        "overlapSkip: overlap.skipReason ?? null, overlapPath: overlap.path ?? null, "
        f"symlinkedSkip: symlinked.skipReason ?? null, "
        "guardDirect: isUserLevelInstructionsFile('/home/u/.pi/agent/AGENTS.md', '/home/u/.pi/agent'), "
        "guardOther: isUserLevelInstructionsFile('/repo/AGENTS.md', '/home/u/.pi/agent') }; })()",
        "resolveAgentsTargetFile",
        "isUserLevelInstructionsFile",
    )
    assert str(result["normalPath"]).endswith("/repo/AGENTS.md")
    assert result["normalSkip"] is None
    assert result["overlapPath"] is None
    assert "user-level" in str(result["overlapSkip"])
    assert "user-level" in str(result["symlinkedSkip"])
    assert result["guardDirect"] is True
    assert result["guardOther"] is False


# ── transactional application ─────────────────────────────────────────


def apply_plan_script(
    project: Path,
    agent: Path,
    run_dir: Path,
    operations: list[dict],
    *,
    cancelled_after: int | None = None,
    fail_at: str | None = None,
) -> str:
    run = {
        "manifest": {
            "runId": "run_test",
            "scopeDigest": "scope",
            "snapshotDigest": "snapshot",
            "runDir": str(run_dir),
            "harnessDir": str(agent / "memory" / "project"),
            "publicDir": str(project / ".memory"),
        }
    }
    doc = (project / "AGENTS.md").read_text(encoding="utf-8")
    planning = {
        "run": run,
        "targetPath": str(project / "AGENTS.md"),
        "docBytesBase64": __import__("base64").b64encode(doc.encode()).decode(),
        "doc": doc,
        "preBytes": len(doc.encode()),
        "snapshotText": SNAPSHOT,
        "rawPlan": {"kind": "agents-md-consolidation-plan", "operations": operations},
        "operations": operations,
        "droppedCount": 0,
        "durationMs": 1,
    }
    return f"""
      import {{ applyAgentsMdConsolidationPlan }} from '{MODULE}';
      const state = {{ active: true, generation: 1, cancelled: false }};
      const opts = {{ pkgDir: {json.dumps(str(PKG_DIR))}, cwd: {json.dumps(str(project))}, reason: 'test', budgetBytes: 16384, disabled: false, availableSkills: ['using-open-artifacts'], transactionFault: {json.dumps(fail_at)} }};
      let checks = 0;
      const planning = {json.dumps(planning)};
      planning.docBytes = Buffer.from(planning.docBytesBase64, 'base64');
      delete planning.docBytesBase64;
      const result = await applyAgentsMdConsolidationPlan({{ ui: {{ notify() {{}} }} }}, state, opts, planning, 1, {json.dumps(cancelled_after)} === null ? undefined : () => ++checks < {json.dumps(cancelled_after)});
      const read = async (file) => await Bun.file(file).text().catch(() => null);
      const exists = async (file) => await Bun.file(file).exists();
      console.log(JSON.stringify({{
        result,
        agents: await read({json.dumps(str(project / 'AGENTS.md'))}),
        harnessMemory: await read({json.dumps(str(agent / 'memory' / 'project' / 'fixture-regeneration.md'))}),
        publicMemory: await read({json.dumps(str(project / '.memory' / 'fixture-regeneration.md'))}),
        harnessIndex: await read({json.dumps(str(agent / 'memory' / 'project' / 'MEMORY.md'))}),
        publicIndex: await read({json.dumps(str(project / '.memory' / 'MEMORY.md'))}),
        harnessConfig: await read({json.dumps(str(project / '.pi' / 'harness.json'))}),
        preReceipt: JSON.parse((await read({json.dumps(str(run_dir / 'agents-pre-receipt.json'))})) ?? 'null'),
        preReceiptExists: await exists({json.dumps(str(run_dir / 'agents-pre-receipt.json'))}),
        receiptExists: await exists({json.dumps(str(run_dir / 'agents-post-receipt.json'))}),
      }}));
    """


def extraction_ops(memory_type: str = "project", classification: str = "safe") -> list[dict]:
    return [
        {
            "op": "extractUnit",
            "oldText": "- Regenerate fixtures after schema changes",
            "extraction": {
                "target": "memory",
                "memoryName": "fixture-regeneration.md",
                "description": "Regenerate fixtures after schema changes",
                "type": memory_type,
                "classification": classification,
            },
            "evidence": [evidence("stale fixtures broke the build again", 0)],
        },
        {
            "op": "extractUnit",
            "oldText": "- Use coda0.com as the default artifacts host",
            "extraction": {
                "target": "skillRule",
                "ruleId": "artifact-host",
                "skillName": "using-open-artifacts",
                "instructions": "Use coda0.com as the default instance.",
            },
            "evidence": [evidence("npm test failed with ERR_PNPM_NO_SCRIPT", 1)],
        },
    ]


def prepare_extraction_roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    agent = tmp_path / "agent"
    run_dir = tmp_path / "run"
    (project / ".memory").mkdir(parents=True)
    (project / ".pi").mkdir()
    (agent / "memory" / "project").mkdir(parents=True)
    run_dir.mkdir()
    (project / "AGENTS.md").write_text(
        "# Rules\n\n- Regenerate fixtures after schema changes\n- Use coda0.com as the default artifacts host\n",
        encoding="utf-8",
    )
    harness_index = "# Memory Index\n\n- [existing-private.md](existing-private.md) (harness only)\n"
    public_index = "# Memory Index\n"
    (agent / "memory" / "project" / "existing-private.md").write_text("private\n", encoding="utf-8")
    (agent / "memory" / "project" / "MEMORY.md").write_text(harness_index, encoding="utf-8")
    (project / ".memory" / "MEMORY.md").write_text(public_index, encoding="utf-8")
    return project, agent, run_dir


def test_safe_extraction_updates_both_roots_and_preserves_private_markers(tmp_path: Path) -> None:
    project, agent, run_dir = prepare_extraction_roots(tmp_path)
    result = js(apply_plan_script(project, agent, run_dir, extraction_ops()), {"PI_CODING_AGENT_DIR": str(agent)})
    assert result["result"]["outcome"] == "applied"
    assert result["result"]["applied"] == 2
    assert json.loads(result["harnessConfig"])["rules"] == [{
        "id": "artifact-host", "skill": "using-open-artifacts", "instructions": "Use coda0.com as the default instance.",
    }]
    assert "skillPrompts" not in json.loads(result["harnessConfig"])
    assert not (project / ".pi" / "harness.local.json").exists()
    assert result["harnessMemory"] == result["publicMemory"]
    assert "(harness only)" in result["harnessIndex"]
    assert "fixture-regeneration.md" in result["publicIndex"]
    assert result["preReceiptExists"] is True
    assert result["preReceipt"]["phase"] == "pre"
    assert result["preReceipt"]["planDigest"]
    assert any(entry["file"].endswith("AGENTS.md") and entry["bytesBase64"] for entry in result["preReceipt"]["predecessors"])
    assert result["receiptExists"] is True
    assert "Regenerate fixtures" not in result["agents"]
    assert "coda0.com" not in result["agents"]


def test_routing_pointer_survives_while_extracted_detail_reaches_memory(tmp_path: Path) -> None:
    project, agent, run_dir = prepare_extraction_roots(tmp_path)
    ops = extraction_ops()[:1]
    pointer = "- For schema changes, read @.memory/fixture-regeneration.md."
    ops[0]["replacementText"] = pointer
    before = (project / "AGENTS.md").read_text()
    result = js(apply_plan_script(project, agent, run_dir, ops), {"PI_CODING_AGENT_DIR": str(agent)})
    assert result["result"]["outcome"] == "applied"
    assert result["agents"] == before.replace(ops[0]["oldText"], pointer)
    assert ops[0]["oldText"] in result["harnessMemory"]
    assert pointer not in result["harnessMemory"]
    assert result["harnessMemory"] == result["publicMemory"]
    assert result["receiptExists"] is True


def test_extraction_pointer_failures_leave_every_surface_unchanged(tmp_path: Path) -> None:
    for case in ("oversized", "unverified", "missing-anchor", "duplicate-anchor", "budget"):
        project, agent, run_dir = prepare_extraction_roots(tmp_path / case)
        op = extraction_ops()[0]
        op["replacementText"] = "- For schema changes, read @.memory/fixture-regeneration.md."
        if case == "oversized":
            op["replacementText"] = "x" * 501
        elif case == "unverified":
            op["evidence"] = [evidence("invented quotation", 0)]
        elif case == "missing-anchor":
            op["oldText"] = "missing"
        elif case == "duplicate-anchor":
            (project / "AGENTS.md").write_text(op["oldText"] + "\n" + op["oldText"] + "\n")
        before = (project / "AGENTS.md").read_text()
        script = apply_plan_script(project, agent, run_dir, [op])
        if case == "budget":
            script = script.replace("budgetBytes: 16384", f"budgetBytes: {len(before.encode())}")
        result = js(script, {"PI_CODING_AGENT_DIR": str(agent)})
        assert result["result"]["outcome"] == "failed", case
        assert result["result"]["applied"] == 0
        assert result["agents"] == before
        assert result["harnessMemory"] is None and result["publicMemory"] is None
        assert result["preReceiptExists"] is False and result["receiptExists"] is False


def test_extraction_indexes_include_relevance_without_forging_privacy(tmp_path: Path) -> None:
    project, agent, run_dir = prepare_extraction_roots(tmp_path)
    op = extraction_ops()[0]
    op["extraction"]["description"] = "Schema changes: review (harness only) labels before regenerating fixtures"
    result = js(apply_plan_script(project, agent, run_dir, [op]), {"PI_CODING_AGENT_DIR": str(agent)})
    assert result["result"]["outcome"] == "applied"
    assert result["harnessMemory"] == result["publicMemory"]
    for index in (result["harnessIndex"], result["publicIndex"]):
        line = next(line for line in index.splitlines() if line.startswith("- [fixture-regeneration.md]"))
        assert "Schema changes: review" in line
        assert "harness only" in line and "(harness only)" not in line
    assert "existing-private.md](existing-private.md) (harness only)" in result["harnessIndex"]
    assert "existing-private.md" not in result["publicIndex"]


def test_skill_rule_extraction_checks_registration_and_every_layer_id_owner(tmp_path: Path) -> None:
    for case in ("missing-registry", "unknown-skill", "built-in", "user", "project", "personal", "disabled", "invalid", "other-selector", "duplicate-plan", "unreadable-layer"):
        project, agent, run_dir = prepare_extraction_roots(tmp_path / case)
        ops = extraction_ops()[1:]
        op = ops[0]
        if case == "unknown-skill":
            op["extraction"]["skillName"] = "not-registered"
        elif case == "built-in":
            op["extraction"]["ruleId"] = "no-bulk-memory-deletion"
        elif case == "duplicate-plan":
            second = json.loads(json.dumps(op))
            second["oldText"] = extraction_ops()[0]["oldText"]
            ops.append(second)
        elif case not in ("missing-registry",):
            config_path = agent / "harness.json" if case in ("user", "unreadable-layer") else project / ".pi" / ("harness.local.json" if case == "personal" else "harness.json")
            owned = {"id": "artifact-host", "skill": "using-open-artifacts", "instructions": "Owned guidance"}
            if case == "disabled":
                owned = {"id": "artifact-host", "enabled": False}
            elif case == "invalid":
                owned = {"id": "artifact-host", "skill": "using-open-artifacts", "instructions": 42}
            elif case == "other-selector":
                owned = {"id": "artifact-host", "bash": "dangerous", "action": "block", "message": "Keep constraint"}
            config_path.write_text("{malformed" if case == "unreadable-layer" else json.dumps({"rules": [owned]}))
        before_agents = (project / "AGENTS.md").read_text()
        configs = {p: p.read_bytes() for p in (agent / "harness.json", project / ".pi" / "harness.json", project / ".pi" / "harness.local.json") if p.exists()}
        script = apply_plan_script(project, agent, run_dir, ops)
        if case == "missing-registry":
            script = script.replace("availableSkills: ['using-open-artifacts']", "availableSkills: []")
        result = js(script, {"PI_CODING_AGENT_DIR": str(agent)})
        assert result["result"]["outcome"] == "failed", case
        assert result["agents"] == before_agents
        assert all(p.read_bytes() == content for p, content in configs.items())
        assert result["preReceiptExists"] is False and result["receiptExists"] is False


def test_skill_rule_extraction_preserves_distinct_rules_and_ownership_metadata(tmp_path: Path) -> None:
    project, agent, run_dir = prepare_extraction_roots(tmp_path)
    prior = {"id": " artifact-host ", "skill": "using-open-artifacts", "instructions": "Keep guidance."}
    revision = js(f"import {{ ruleRevision }} from './packages/continual-learning/extensions/guardrail-engine.ts'; console.log(JSON.stringify(ruleRevision({json.dumps(prior)})));")
    base = {"rules": [prior], "learnedRules": {" artifact-host ": {"origin": "consolidation", "revision": revision}}}
    (project / ".pi" / "harness.json").write_text(json.dumps(base))
    result = js(apply_plan_script(project, agent, run_dir, extraction_ops()[1:]), {"PI_CODING_AGENT_DIR": str(agent)})
    assert result["result"]["outcome"] == "applied"
    after = json.loads(result["harnessConfig"])
    assert after["rules"] == base["rules"] + [{"id": "artifact-host", "skill": "using-open-artifacts", "instructions": "Use coda0.com as the default instance."}]
    assert after["learnedRules"] == base["learnedRules"]
    assert "skillPrompts" not in after


def test_skill_extraction_preserves_legacy_containers_and_respects_reserved_names(tmp_path: Path) -> None:
    from test_harness_upgrade_compatibility import LEGACY
    for conflict in (False, True):
        project, agent, run_dir = prepare_extraction_roots(tmp_path / str(conflict))
        base = json.loads(json.dumps(LEGACY))
        if conflict:
            base['policies'][0]['name'] = 'artifact-host'
        target = project / '.pi/harness.json'
        target.write_text(json.dumps(base))
        before = target.read_bytes()
        result = js(apply_plan_script(project, agent, run_dir, extraction_ops()[1:]), {'PI_CODING_AGENT_DIR': str(agent)})
        if conflict:
            assert result['result']['outcome'] == 'failed'
            assert target.read_bytes() == before
        else:
            assert result['result']['outcome'] == 'applied'
            after = json.loads(result['harnessConfig'])
            assert {key: after[key] for key in base} == base
            assert after['rules'][0]['id'] == 'artifact-host'


def test_skill_extraction_executes_positive_and_negative_selector_checks(tmp_path: Path) -> None:
    for case in ("valid", "positive-misses", "negative-matches"):
        project, agent, run_dir = prepare_extraction_roots(tmp_path / case)
        script = apply_plan_script(project, agent, run_dir, extraction_ops()[1:])
        import_line = f"import {{ applyAgentsMdConsolidationPlan }} from '{MODULE}';"
        script = script.replace(import_line, f"const {{ applyAgentsMdConsolidationPlan }} = await import('{MODULE}');")
        script = f"""
          import {{ mock }} from 'bun:test';
          const engine = await import('./packages/continual-learning/extensions/guardrail-engine.ts');
          const originalEvaluateSkill = engine.evaluateSkill;
          const selectors = [];
          mock.module('./packages/continual-learning/extensions/guardrail-engine.ts', () => ({{
            ...engine,
            evaluateSkill: (config, name) => {{
              selectors.push(name);
              const matches = originalEvaluateSkill(config, name);
              if ({json.dumps(case)} === 'positive-misses' && name === 'using-open-artifacts') return [];
              if ({json.dumps(case)} === 'negative-matches' && name !== 'using-open-artifacts') return originalEvaluateSkill(config, 'using-open-artifacts');
              return matches;
            }},
          }}));
        """ + script
        script = script.replace("        result,", "        result, selectors,")
        before = (project / "AGENTS.md").read_text()
        result = js(script, {"PI_CODING_AGENT_DIR": str(agent)})
        assert "using-open-artifacts" in result["selectors"]
        if case == "valid":
            assert any(name != "using-open-artifacts" for name in result["selectors"])
            assert result["result"]["outcome"] == "applied"
            assert "artifact-host" not in json.loads(result["harnessConfig"]).get("learnedRules", {})
        else:
            assert result["result"]["outcome"] == "failed"
            assert result["agents"] == before
            assert result["harnessConfig"] is None
            assert result["preReceiptExists"] is False and result["receiptExists"] is False


def test_skill_rule_ownership_is_rechecked_before_receipt_creation(tmp_path: Path) -> None:
    project, agent, run_dir = prepare_extraction_roots(tmp_path)
    user_config = agent / "harness.json"
    owned = json.dumps({"rules": [{"id": "artifact-host", "enabled": False}]})
    before = (project / "AGENTS.md").read_text()
    script = apply_plan_script(project, agent, run_dir, extraction_ops()[1:])
    script = script.replace(
        "const opts = {",
        f"const opts = {{ transactionHook: async stage => {{ if (stage === 'before-artifacts') await Bun.write({json.dumps(str(user_config))}, {json.dumps(owned)}); }},",
        1,
    )
    result = js(script, {"PI_CODING_AGENT_DIR": str(agent)})
    assert result["result"]["outcome"] == "failed"
    assert "already exists" in result["result"]["detail"]
    assert result["agents"] == before
    assert user_config.read_text() == owned
    assert result["harnessConfig"] is None
    assert result["preReceiptExists"] is False and result["receiptExists"] is False


def test_private_extraction_stays_private_and_is_indexed(tmp_path: Path) -> None:
    project, agent, run_dir = prepare_extraction_roots(tmp_path)
    result = js(apply_plan_script(project, agent, run_dir, extraction_ops("project", "private")[:1]), {"PI_CODING_AGENT_DIR": str(agent)})
    assert result["result"]["outcome"] == "applied"
    assert result["harnessMemory"] is not None
    assert result["publicMemory"] is None
    assert "fixture-regeneration.md](fixture-regeneration.md) (harness only)" in result["harnessIndex"]
    assert "existing-private.md](existing-private.md) (harness only)" in result["harnessIndex"]


def test_skill_rule_extraction_rejects_symlinked_project_config_path(tmp_path: Path) -> None:
    project, agent, run_dir = prepare_extraction_roots(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (project / ".pi").rmdir()
    (project / ".pi").symlink_to(outside, target_is_directory=True)
    before_agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    result = js(apply_plan_script(project, agent, run_dir, extraction_ops()[1:]), {"PI_CODING_AGENT_DIR": str(agent)})
    assert result["result"]["outcome"] == "failed"
    assert result["agents"] == before_agents
    assert not (outside / "harness.json").exists()
    assert result["receiptExists"] is False


def test_existing_memory_name_fails_without_overwriting_or_editing_agents(tmp_path: Path) -> None:
    project, agent, run_dir = prepare_extraction_roots(tmp_path)
    existing = agent / "memory" / "project" / "FIXTURE-REGENERATION.md"
    existing.write_text("do not overwrite\n", encoding="utf-8")
    before_agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    result = js(apply_plan_script(project, agent, run_dir, extraction_ops()[:1]), {"PI_CODING_AGENT_DIR": str(agent)})
    assert result["result"]["outcome"] == "failed"
    assert result["result"]["applied"] == 0
    assert existing.read_text(encoding="utf-8") == "do not overwrite\n"
    assert result["agents"] == before_agents
    assert result["receiptExists"] is False


def test_failure_and_cancellation_roll_back_every_surface(tmp_path: Path) -> None:
    for fail_at, cancelled_after in (("after-artifacts", None), ("after-agents", None), ("before-receipt", None), (None, 3)):
        case = tmp_path / f"case-{fail_at or 'cancel'}"
        project, agent, run_dir = prepare_extraction_roots(case)
        before = {
            "agents": (project / "AGENTS.md").read_bytes(),
            "harnessIndex": (agent / "memory" / "project" / "MEMORY.md").read_bytes(),
            "publicIndex": (project / ".memory" / "MEMORY.md").read_bytes(),
        }
        ops = extraction_ops()
        ops[0]["replacementText"] = "- For schema changes, read @.memory/fixture-regeneration.md."
        ops[1]["replacementText"] = "- When publishing artifacts, use /skill:using-open-artifacts."
        result = js(
            apply_plan_script(project, agent, run_dir, ops, cancelled_after=cancelled_after, fail_at=fail_at),
            {"PI_CODING_AGENT_DIR": str(agent)},
        )
        expected = "cancelled" if cancelled_after is not None else "failed"
        assert result["result"]["outcome"] == expected
        assert result["result"]["applied"] == 0
        assert (project / "AGENTS.md").read_bytes() == before["agents"]
        assert (agent / "memory" / "project" / "MEMORY.md").read_bytes() == before["harnessIndex"]
        assert (project / ".memory" / "MEMORY.md").read_bytes() == before["publicIndex"]
        assert result["harnessMemory"] is None
        assert result["publicMemory"] is None
        assert result["harnessConfig"] is None
        assert result["preReceiptExists"] is False
        assert result["receiptExists"] is False


def test_duplicate_case_insensitive_memory_names_fail_before_mutation(tmp_path: Path) -> None:
    project, agent, run_dir = prepare_extraction_roots(tmp_path)
    (project / "AGENTS.md").write_text("# Rules\n\n- One\n- Two\n", encoding="utf-8")
    first = extraction_ops()[0]
    first["oldText"] = "- One"
    second = json.loads(json.dumps(first))
    second["oldText"] = "- Two"
    second["extraction"]["memoryName"] = "FIXTURE-REGENERATION.md"
    before = (project / "AGENTS.md").read_text(encoding="utf-8")
    result = js(apply_plan_script(project, agent, run_dir, [first, second]), {"PI_CODING_AGENT_DIR": str(agent)})
    assert result["result"]["outcome"] == "failed"
    assert result["agents"] == before
    assert result["harnessMemory"] is None
    assert result["preReceiptExists"] is False
    assert result["receiptExists"] is False


def test_orphan_pre_receipt_recovers_predecessors_before_new_work(tmp_path: Path) -> None:
    project, agent, run_dir = prepare_extraction_roots(tmp_path)
    agents_file = project / "AGENTS.md"
    memory_file = agent / "memory" / "project" / "partial.md"
    predecessor = agents_file.read_bytes()
    memory_file.write_text("partial\n", encoding="utf-8")
    agents_file.write_text("# Partially changed\n", encoding="utf-8")
    snapshot = run_dir / "snapshot.json"
    snapshot.write_text('{"entries":[]}\n', encoding="utf-8")
    digest = __import__("hashlib").sha256(snapshot.read_bytes()).hexdigest()
    receipt = {
        "kind": "agents-md-consolidation-receipt", "phase": "pre",
        "runId": "run_recover", "scopeDigest": "scope", "snapshotDigest": digest,
        "targetFile": str(agents_file), "budgetBytes": 16384, "planDigest": "a" * 64,
        "predecessors": [
            {"file": str(agents_file), "existed": True, "mode": 0o644, "bytesBase64": __import__("base64").b64encode(predecessor).decode()},
            {"file": str(memory_file), "existed": False, "mode": None, "bytesBase64": None},
        ],
        "directories": [],
    }
    (run_dir / "agents-pre-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    result = js(f'''
      import {{ recoverAgentsMdConsolidation }} from '{MODULE}';
      const run = {{ manifest: {{ runId: 'run_recover', scopeDigest: 'scope', snapshotDigest: {json.dumps(digest)}, harnessDir: {json.dumps(str(agent / 'memory' / 'project'))}, publicDir: {json.dumps(str(project / '.memory'))}, runDir: {json.dumps(str(run_dir))} }} }};
      console.log(JSON.stringify({{ recovered: await recoverAgentsMdConsolidation(run, {json.dumps(str(project))}) }}));
    ''', {"PI_CODING_AGENT_DIR": str(agent)})
    assert result["recovered"] is True
    assert agents_file.read_bytes() == predecessor
    assert not memory_file.exists()
    assert not (run_dir / "agents-pre-receipt.json").exists()


def test_pending_recovery_is_discovered_from_the_project_runs_directory(tmp_path: Path) -> None:
    project = tmp_path / "project"
    agent = tmp_path / "agent"
    project.mkdir(); agent.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    import hashlib
    paths = js(f'''
      import {{ resolveMemoryPaths }} from './packages/continual-learning/extensions/memory-paths.ts';
      console.log(JSON.stringify(resolveMemoryPaths({json.dumps(str(project))}, {json.dumps(str(agent))})));
    ''')
    scope_key = paths["scopeKey"]
    harness_dir = Path(paths["harnessDir"])
    public_dir = project / ".memory"
    run_id = "run_recover_pending"
    run_dir = agent / "memory" / "runs" / scope_key / run_id
    run_dir.mkdir(parents=True)
    (project / "AGENTS.md").write_text("changed\n", encoding="utf-8")
    snapshot = run_dir / "snapshot.json"; snapshot.write_text('{"entries":[]}\n', encoding="utf-8")
    snapshot_digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    manifest = {
        "schemaVersion": 1, "runId": run_id, "cwd": str(project.resolve()), "scopeKey": scope_key,
        "scopeDigest": "scope", "harnessDir": str(harness_dir), "publicDir": str(public_dir),
        "runDir": str(run_dir), "contextEnabled": True, "contextMode": "snapshot",
        "snapshotPath": str(snapshot), "snapshotDigest": snapshot_digest, "createdAt": "2026-01-01T00:00:00.000Z",
        "sourceHashes": {"harness": {}, "public": {}},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    predecessor = b"original\n"
    receipt = {
        "kind": "agents-md-consolidation-receipt", "phase": "pre", "runId": run_id,
        "scopeDigest": "scope", "snapshotDigest": snapshot_digest, "targetFile": str(project / "AGENTS.md"),
        "budgetBytes": 16384, "planDigest": "a" * 64,
        "predecessors": [{"file": str(project / "AGENTS.md"), "existed": True, "mode": 0o644, "bytesBase64": __import__("base64").b64encode(predecessor).decode()}],
        "directories": [],
    }
    (run_dir / "agents-pre-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    result = js(f'''
      process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
      const {{ recoverPendingAgentsMdConsolidations }} = await import('{MODULE}');
      console.log(JSON.stringify({{ recovered: await recoverPendingAgentsMdConsolidations({json.dumps(str(project))}) }}));
    ''', {"PI_CODING_AGENT_DIR": str(agent)})
    assert result["recovered"] == 1
    assert (project / "AGENTS.md").read_bytes() == predecessor
    assert not (run_dir / "agents-pre-receipt.json").exists()


def test_failed_extraction_restores_previously_absent_directories(tmp_path: Path) -> None:
    project = tmp_path / "project"
    agent = tmp_path / "agent"
    run_dir = tmp_path / "run"
    project.mkdir(); agent.mkdir(); run_dir.mkdir()
    (project / "AGENTS.md").write_text("# Rules\n\n- Regenerate fixtures after schema changes\n", encoding="utf-8")
    result = js(
        apply_plan_script(project, agent, run_dir, extraction_ops()[:1], fail_at="after-artifacts"),
        {"PI_CODING_AGENT_DIR": str(agent)},
    )
    assert result["result"]["outcome"] == "failed"
    assert not (agent / "memory" / "project").exists()
    assert not (project / ".memory").exists()
    assert result["preReceiptExists"] is False
    assert result["receiptExists"] is False


def test_swapped_memory_roots_are_rejected_before_redirected_write(tmp_path: Path) -> None:
    for root_kind in ("private", "public"):
        case = tmp_path / root_kind
        project, agent, run_dir = prepare_extraction_roots(case)
        memory_root = agent / "memory" / "project" if root_kind == "private" else project / ".memory"
        predecessor = memory_root.with_name(f"{memory_root.name}-predecessor")
        outside = case / "outside"
        outside.mkdir()
        script = apply_plan_script(project, agent, run_dir, extraction_ops()[:1])
        script = script.replace(
            "const opts = {",
            f"const swapRoot = async () => {{ await (await import('node:fs/promises')).rename({json.dumps(str(memory_root))}, {json.dumps(str(predecessor))}); await (await import('node:fs/promises')).symlink({json.dumps(str(outside))}, {json.dumps(str(memory_root))}, 'dir'); }}; const opts = {{ transactionHook: async stage => {{ if (stage === 'before-artifacts') await swapRoot(); }},",
            1,
        )
        result = js(script, {"PI_CODING_AGENT_DIR": str(agent)})
        assert result["result"]["outcome"] == "failed"
        assert not (outside / "fixture-regeneration.md").exists()
        assert not (outside / "MEMORY.md").exists()
        assert result["preReceiptExists"] is False
        assert result["receiptExists"] is False


# ── wiring and procedure contract ─────────────────────────────────────


def test_pipeline_plans_harness_and_agents_in_parallel_then_applies_sequentially() -> None:
    inject = (PKG_DIR / "extensions" / "inject-memory.ts").read_text(encoding="utf-8")
    agents = (PKG_DIR / "extensions" / "agents-md-consolidation.ts").read_text(encoding="utf-8")
    assert "Promise.all([harnessPromise, agentsPromise])" in inject
    harness_apply = inject.index("await applyHarnessConsolidationPlan")
    agents_apply = inject.index("await applyAgentsMdConsolidationPlan")
    assert harness_apply < agents_apply
    assert "settings.agentsMd?.disabled !== true" in inject
    assert "DEFAULT_AGENTS_MD_BUDGET_BYTES" in inject
    assert "hasUI" not in agents
    assert "ctx.ui.select" not in agents


def test_changed_snapshot_bytes_are_rejected_before_agents_planning() -> None:
    result = js(r'''
      import { mock } from 'bun:test';
      import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path';
      import { EventEmitter } from 'node:events'; import { createHash } from 'node:crypto';
      const kit = await import('./packages/kit/src/index.ts');
      mock.module('./packages/kit/src/index.ts', () => ({
        ...kit,
        spawnPiChild: () => { const child = new EventEmitter(); child.stdout = new EventEmitter(); child.stderr = new EventEmitter(); return child; },
      }));
      const { planAgentsMdConsolidationPhase } = await import('./packages/continual-learning/extensions/agents-md-consolidation.ts');
      const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'agents-stale-snapshot-'));
      fs.writeFileSync(path.join(temp, 'AGENTS.md'), '# Rules\n');
      const snapshotPath = path.join(temp, 'snapshot.json');
      const original = JSON.stringify({ entries: [{ message: { role: 'user', content: 'original' } }] });
      fs.writeFileSync(snapshotPath, original);
      const digest = createHash('sha256').update(original).digest('hex');
      fs.writeFileSync(snapshotPath, JSON.stringify({ entries: [{ message: { role: 'user', content: 'replacement' } }] }));
      const run = { manifest: { runId: 'run', scopeDigest: 'scope', snapshotDigest: digest, snapshotPath, cwd: temp, runDir: temp }, paths: { snapshotFile: snapshotPath } };
      const result = await planAgentsMdConsolidationPhase(
        { cwd: temp, ui: { notify() {} } }, { active: true, generation: 1, cancelled: false },
        { pkgDir: process.cwd(), cwd: temp, reason: 'test', budgetBytes: 16384, disabled: false }, run, 1,
      );
      fs.rmSync(temp, { recursive: true, force: true });
      console.log(JSON.stringify(result));
    ''')
    assert result["outcome"] == "failed"
    assert "snapshot changed" in result["detail"]


def test_agents_planner_uses_package_prompt_and_minimal_readonly_args() -> None:
    source = (PKG_DIR / "extensions" / "agents-md-consolidation.ts").read_text(encoding="utf-8")
    assert "buildAgentsMdConsolidatorPrompt" in source
    assert 'minimalPiWorkerArgs(["read", "grep", "find", "ls"])' in source
    header = source.split("const taskText = [", 1)[1].split('].join("\\n");', 1)[0]
    for duplicate in ("Run ID:", "Scope digest:", "Artifact/snapshot digest:", "Immutable task-slice snapshot:", "Authoritative Learning Dossier:"):
        assert duplicate not in header
    assert "Registered skill names" in header


def test_procedure_declares_readonly_boundary_and_discipline() -> None:
    text = (PKG_DIR / "prompts" / "agents-md-consolidator.md").read_text(encoding="utf-8")
    assert "Read-only boundary" in text
    assert "{{BUDGET_BYTES}}" in text
    assert "verbatim" in text
    assert "entryIndex" in text
    assert "user or tool-result" in text
    assert "parent" in text and "distinct" in text
    assert "five operations" in text
    assert '"agents-md-consolidation-plan"' in text


def test_procedure_routes_conditionally_with_compact_authority() -> None:
    text = (PKG_DIR / "prompts" / "agents-md-consolidator.md").read_text(encoding="utf-8")
    normalized = " ".join(text.split())
    for retained in ("common", "conditional pointer", "replacementText", "500", "120", "front-loaded", "registered", "skillRule", "ruleId", "instructions", "safe", "private"):
        assert retained in normalized
    assert "always-relevant" not in normalized
    assert "neural net" not in normalized and "gradient" not in normalized
    assert "skillPrompt" not in normalized
    assert normalized.count("confirmation") == 1
    assert "not proof" in normalized
    assert "need not" in normalized


def test_evidence_harness_requires_parent_completion_not_child_claims() -> None:
    for scenario in ("verified", "empty", "streamed-gates", "gates-in-tool-result"):
        result = subprocess.run(
            ["bun", str(PKG_DIR / "tests" / "consolidation_evidence_harness.ts"), scenario],
            cwd=REPO, capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stderr
        missing = json.loads(result.stdout.strip().splitlines()[-1])
        assert missing == ([] if scenario == "verified" else [
            "completed tool work", "exactly one schema-valid consolidation plan", "a parent-owned validation receipt",
        ])


def test_plan_and_apply_interfaces_are_discriminated() -> None:
    source = (PKG_DIR / "extensions" / "agents-md-consolidation.ts").read_text(encoding="utf-8")
    assert 'outcome: "planned"' in source
    assert 'outcome: "noop" | "rejected" | "failed" | "cancelled" | "skipped"' in source
    assert 'outcome: "applied" | "noop" | "failed" | "cancelled"' in source


def test_planner_timeout_output_limit_and_post_spawn_cancel_await_child_close() -> None:
    result = js(r'''
      import { mock } from 'bun:test';
      import fs from 'node:fs';
      import os from 'node:os';
      import path from 'node:path';
      import { EventEmitter } from 'node:events';
      import { createHash } from 'node:crypto';
      const kit = await import('./packages/kit/src/index.ts');
      let mode = '';
      let lastChild;
      mock.module('./packages/kit/src/index.ts', () => ({
        ...kit,
        spawnPiChild: () => {
          const child = new EventEmitter();
          child.stdout = new EventEmitter(); child.stderr = new EventEmitter();
          child.exitCode = null; child.signalCode = null; child.pid = undefined;
          child.closed = false; child.closeScheduled = false;
          child.kill = signal => {
            if (!child.closeScheduled) {
              child.closeScheduled = true;
              setTimeout(() => { child.signalCode = signal; child.closed = true; child.emit('close', null, signal); }, 30);
            }
            return true;
          };
          if (mode === 'output-limit') setTimeout(() => child.stdout.emit('data', Buffer.alloc(16 * 1024 * 1024 + 1)), 0);
          lastChild = child;
          return child;
        },
      }));
      const { planAgentsMdConsolidationPhase } = await import('./packages/continual-learning/extensions/agents-md-consolidation.ts');
      const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'agents-planner-stop-'));
      fs.writeFileSync(path.join(temp, 'AGENTS.md'), '# Rules\n');
      const runCase = async name => {
        mode = name;
        const runDir = path.join(temp, name); fs.mkdirSync(runDir, { recursive: true });
        const snapshotPath = path.join(runDir, 'snapshot.json');
        const snapshot = JSON.stringify({ entries: [] }); fs.writeFileSync(snapshotPath, snapshot);
        const snapshotDigest = createHash('sha256').update(snapshot).digest('hex');
        const run = { manifest: { runId: `run-${name}`, scopeDigest: 'scope', snapshotDigest, snapshotPath, cwd: temp, runDir }, paths: { snapshotFile: snapshotPath } };
        const state = { active: true, generation: 1, cancelled: false };
        const started = Date.now();
        const planning = planAgentsMdConsolidationPhase(
          { cwd: temp, ui: { notify() {} } }, state,
          { pkgDir: process.cwd(), cwd: temp, reason: name, budgetBytes: 16384, disabled: false, timeoutMs: 5 }, run, 1,
        );
        if (name === 'cancel') queueMicrotask(() => { state.cancelled = true; });
        const value = await planning;
        return { outcome: value.outcome, detail: value.detail, closedWhenResolved: lastChild.closed, elapsed: Date.now() - started };
      };
      const outputLimit = await runCase('output-limit');
      const cancel = await runCase('cancel');
      const timeout = await runCase('timeout');
      fs.rmSync(temp, { recursive: true, force: true });
      console.log(JSON.stringify({ outputLimit, cancel, timeout }));
    ''')
    assert result["outputLimit"]["closedWhenResolved"] is True
    assert "stdout exceeded" in result["outputLimit"]["detail"]
    assert result["cancel"]["closedWhenResolved"] is True
    assert result["cancel"]["outcome"] == "cancelled"
    assert result["timeout"]["closedWhenResolved"] is True
    assert result["timeout"]["elapsed"] >= 30
    assert "timed out" in result["timeout"]["detail"]
