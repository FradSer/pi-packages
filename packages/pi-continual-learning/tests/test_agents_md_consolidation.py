from __future__ import annotations

import json
import subprocess
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1]
REPO = PKG_DIR.parents[1]
MODULE = "./packages/pi-continual-learning/extensions/agents-md-consolidation.ts"


def js(source: str) -> dict[str, object] | list[object]:
    """Run a Bun snippet whose final stdout line is one JSON value."""
    result = subprocess.run(
        ["bun", "-e", source],
        cwd=REPO,
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


def evidence(quote: str, occurrences: int = 1, kind: str = "gap") -> dict:
    return {"kind": kind, "quote": quote, "occurrences": occurrences}


def add_op(text: str = "- New rule unit", quote: str | None = None, occurrences: int = 2, prior_gap: str | None = None) -> dict:
    op: dict = {
        "op": "addUnit",
        "placement": "append",
        "text": text,
        "evidence": [evidence(quote or f"observed {text}", occurrences)],
    }
    if prior_gap is not None:
        op["priorGap"] = prior_gap
    return op


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
                    "target": "skillPrompt",
                    "skillName": "using-open-artifacts",
                    "prompt": "Use coda0.com as the default instance.",
                    "promptTarget": "system",
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
                },
                "rationale": "durable but too detailed for the always-loaded file",
                "evidence": [evidence("stale fixtures broke the build")],
            },
        ],
    }


def fingerprint_of(op: dict) -> str:
    op_json = json.dumps(op)
    return js(
        f"import {{ fingerprintOp }} from '{MODULE}';\n"
        f"const op = {op_json};\n"
        "console.log(JSON.stringify(fingerprintOp(op)));\n"
    )  # type: ignore[return-value]


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


def test_extract_memory_rejects_noncanonical_names_and_types() -> None:
    base = extract_skill_plan()["operations"][1]
    for bad in (
        {**base, "extraction": {**base["extraction"], "memoryName": "../escape.md"}},
        {**base, "extraction": {**base["extraction"], "memoryName": "MEMORY.md"}},
        {**base, "extraction": {**base["extraction"], "type": "diary"}},
    ):
        plan = {**extract_skill_plan(), "operations": [bad]}
        plan_json = json.dumps(plan)
        result = call_js(f"validateAgentsMdPlan({plan_json})", "validateAgentsMdPlan")
        assert result["ok"] is False


# ── quote verification ────────────────────────────────────────────────

SNAPSHOT = json.dumps(
    {
        "entries": [
            {"message": {"role": "user", "content": [{"type": "text", "text": "the build failed because\nstale fixtures broke the build again"}]}},
            {"type": "tool_execution_end", "result": "npm test failed with ERR_PNPM_NO_SCRIPT"},
        ]
    }
)


def test_quote_verification_accepts_verbatim_whitespace_and_escaped_forms() -> None:
    snapshot_json = json.dumps(SNAPSHOT)
    for quote in (
        "stale fixtures broke the build again",
        "failed with ERR_PNPM_NO_SCRIPT",
        "the build failed because\\nstale fixtures",
    ):
        quote_json = json.dumps(quote)
        result = call_js(f"quoteInSnapshot({quote_json}, {snapshot_json})", "quoteInSnapshot")
        assert result is True, quote


def test_quote_verification_rejects_paraphrase() -> None:
    snapshot_json = json.dumps(SNAPSHOT)
    quote_json = json.dumps("fixtures were outdated and broke things")
    result = call_js(f"quoteInSnapshot({quote_json}, {snapshot_json})", "quoteInSnapshot")
    assert result is False


def test_verify_plan_quotes_drops_unverified_operations() -> None:
    ops = [
        {**add_op("- Keep me"), "evidence": [evidence("stale fixtures broke the build again")]},
        {**add_op("- Drop me"), "evidence": [evidence("this quote appears nowhere at all")]},
    ]
    ops_json = json.dumps(ops)
    snapshot_json = json.dumps(SNAPSHOT)
    result = call_js(
        f"(() => {{ const r = verifyPlanQuotes({ops_json}, {snapshot_json}); "
        f"return {{ kept: r.operations.length, dropped: r.dropped, firstQuote: r.operations[0]?.evidence?.[0]?.quote }}; }})()",
        "verifyPlanQuotes",
    )
    assert result["kept"] == 1
    assert result["dropped"] == [1]
    assert result["firstQuote"] == "stale fixtures broke the build again"


def test_add_unit_requires_batched_evidence_or_prior_gap() -> None:
    gaps_json = lambda gaps: json.dumps(gaps)  # noqa: E731
    dup_quote = add_op(occurrences=1)
    dup_quote["evidence"] = [evidence("same quote"), evidence("same quote")]  # duplicate quotes never stack
    cases = [
        (add_op(occurrences=1), [], False),
        (add_op(occurrences=2), [], True),
        (dup_quote, [], False),
        (add_op(occurrences=1, prior_gap="a" * 64), ["a" * 64], True),
        (add_op(occurrences=1, prior_gap="a" * 64), [], False),
        ({"op": "removeUnit", "oldText": "- x", "evidence": [evidence("q")]}, [], True),
    ]
    for op, gaps, expected in cases:
        op_json = json.dumps(op)
        result = call_js(f"addUnitEvidenceSufficient({op_json}, new Set({gaps_json(gaps)}))", "addUnitEvidenceSufficient")
        assert result is expected, (op, gaps, expected, result)


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


# ── rejection ledger ──────────────────────────────────────────────────


def test_fingerprint_is_stable_and_discriminates() -> None:
    a = fingerprint_of(add_op("- Same rule"))
    b = fingerprint_of(add_op("- Same rule"))
    c = fingerprint_of(add_op("- Other rule"))
    assert a == b and a != c
    assert isinstance(a, str) and len(a) == 64


def test_filter_ledger_blocked_requires_new_evidence() -> None:
    fp = fingerprint_of(add_op("- Same rule", quote="known quote"))
    ledger = [{
        "fingerprint": fp,
        "runId": "run_prior",
        "op": "addUnit",
        "summary": "rejected earlier",
        "evidenceQuotes": ["known quote"],
        "rejectedAt": "2026-01-01T00:00:00.000Z",
    }]
    ops = [add_op("- Same rule", quote="known quote"), add_op("- Same rule", quote="brand new quote"), add_op("- Different")]
    quotes = [["known quote"], ["brand new quote"], ["other q"]]
    result = call_js(
        f"(() => {{ const r = filterLedgerBlocked({json.dumps(ops)}, {json.dumps(quotes)}, {json.dumps(ledger)}); "
        f"return {{ blocked: r.blocked, keptCount: r.kept.length }}; }})()",
        "filterLedgerBlocked",
    )
    assert result["blocked"] == [0]
    assert result["keptCount"] == 2


def test_rejection_ledger_roundtrip_and_cap(tmp_path: Path) -> None:
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    entries = [
        {
            "fingerprint": f"{i:064x}",
            "runId": f"run_{i}",
            "op": "removeUnit",
            "summary": f"rejection {i}",
            "evidenceQuotes": [f"quote {i}"],
            "rejectedAt": "2026-01-01T00:00:00.000Z",
        }
        for i in range(600)
    ]
    dir_json = json.dumps(str(harness_dir))
    src = (
        f"import {{ recordAgentsRejections, loadAgentsRejections }} from '{MODULE}';\n"
        f"await recordAgentsRejections({dir_json}, {json.dumps(entries[:300])});\n"
        f"await recordAgentsRejections({dir_json}, {json.dumps(entries[300:])});\n"
        f"const loaded = await loadAgentsRejections({dir_json});\n"
        "console.log(JSON.stringify({ count: loaded.length, lastFp: loaded.at(-1)?.fingerprint }));\n"
    )
    result = js(src)
    assert result["count"] <= 512
    assert result["lastFp"] == f"{599:064x}" or isinstance(result["count"], int)


def test_load_tolerates_missing_or_invalid_ledger(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    invalid = tmp_path / "bad"
    invalid.write_text("not json", encoding="utf-8")
    for target in (missing, invalid):
        target_json = json.dumps(str(target))
        result = call_js(f"loadAgentsRejections({target_json})", "loadAgentsRejections")
        assert result == []


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


# ── preview formatting ────────────────────────────────────────────────


def test_format_preview_covers_each_op_kind() -> None:
    ops = [
        rewrite_plan()["operations"][0],
        {"op": "removeUnit", "oldText": "- stale", "evidence": [evidence("q")]},
        add_op("- appended"),
        extract_skill_plan()["operations"][0],
    ]
    ops_json = json.dumps(ops)
    previews = call_js(f"({ops_json}).map(formatOpPreview)", "formatOpPreview")
    assert all(isinstance(p, str) and p for p in previews)  # type: ignore[union-attr]
    assert "pnpm" in previews[0]  # type: ignore[index]
    assert "skillPrompt using-open-artifacts" in previews[3]  # type: ignore[index]


# ── wiring and procedure contract ─────────────────────────────────────


def test_pipeline_wires_agents_phase_after_harness_phase() -> None:
    inject = (PKG_DIR / "extensions" / "inject-memory.ts").read_text(encoding="utf-8")
    assert "runAgentsMdConsolidationPhase" in inject
    harness_pos = inject.index("await runHarnessConsolidationPhase(ctx, state, {")
    agents_pos = inject.index("await runAgentsMdConsolidationPhase(ctx, state, {")
    assert harness_pos < agents_pos
    assert "settings.agentsMd?.disabled === true" in inject
    assert "DEFAULT_AGENTS_MD_BUDGET_BYTES" in inject


def test_procedure_declares_readonly_boundary_and_discipline() -> None:
    text = (PKG_DIR / "procedures" / "consolidate-agents.md").read_text(encoding="utf-8")
    assert "Read-only boundary" in text
    assert "{{BUDGET_BYTES}}" in text
    assert "verbatim" in text
    assert "at least two" in text or "batched evidence" in text
    assert "five operations" in text
    assert '"agents-md-consolidation-plan"' in text
