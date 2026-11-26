from __future__ import annotations



# ── test_real_model_live.py ──
"""Pure regressions for the real-model RPC harness.

These tests replay protocol metadata only; they never start Pi or a provider.
"""

import json
from pathlib import Path

import pytest

from real_model_live import (
    MATT_TOOL_NAMES,
    build_command,
    configured_model,
    is_interactive_ui_request,
    matt_call_records,
    overall_status,
    row_args,
    row_state,
    artifact_summary,
    agent_end_diagnostics,
    agent_failure_diagnostic,
    fixture_sandbox_healthy,
    summarize_matt_calls,
    summarize_ui_request,
    validate_case,
    validate_final_fixture_availability,
    validate_fixture_checks,
)


def test_real_model_requires_configured_provider_and_model(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    settings = tmp_path / ".pi/agent/settings.json"
    with pytest.raises(RuntimeError, match="provider and model"):
        configured_model()
    settings.parent.mkdir(parents=True)
    settings.write_text('{"defaultProvider":"chosen","defaultModel":"selected"}')
    assert configured_model() == ("chosen", "selected")
    settings.write_text('{"defaultProvider":"chosen"}')
    with pytest.raises(RuntimeError, match="provider and model"):
        configured_model()


def test_one_way_ui_notice_does_not_make_a_run_pending() -> None:
    assert not is_interactive_ui_request({"method": "setStatus"})
    assert not is_interactive_ui_request({"method": "notify"})
    assert is_interactive_ui_request({"method": "select"})
    assert is_interactive_ui_request({"method": "input"})


def test_command_exposes_all_matt_tools_to_pi() -> None:
    command = build_command("pi", "provider", "model")
    tools = command[command.index("--tools") + 1].split(",")
    assert set(MATT_TOOL_NAMES).issubset(tools)


def test_failed_fixture_checks_cannot_be_reported_as_passed() -> None:
    checks = [{
        "kind": "tool_execution_end",
        "toolName": "fixture_checks",
        "isError": False,
        "result": {"passed": False},
    }]
    errors = validate_fixture_checks(
        {"checkTests": True},
        checks,
        {"available": True, "passed": False},
        {"available": True, "passed": False},
    )
    assert "independent fixture_checks did not pass" in errors
    assert errors


def test_behavior_sequence_requires_red_then_green() -> None:
    checks = [
        {"kind": "tool_execution_end", "toolName": "fixture_checks", "isError": False, "result": {"passed": False}},
        {"kind": "tool_execution_end", "toolName": "fixture_checks", "isError": False, "result": {"passed": True}},
    ]
    assert validate_fixture_checks(
        {"checkTests": True},
        checks,
        {"available": True, "passed": False},
        {"available": True, "passed": True},
    ) == []


def test_scope_creep_is_a_green_baseline_without_fake_red_requirement() -> None:
    checks = [{
        "kind": "tool_execution_end",
        "toolName": "fixture_checks",
        "isError": False,
        "result": {"passed": True},
    }]
    assert validate_fixture_checks(
        {"checkTests": True, "fixture": "scope-creep", "requiresRed": False},
        checks,
        {"available": True, "passed": True},
        {"available": True, "passed": True},
    ) == []


def test_source_unchanged_rejects_new_source_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "new.mjs").write_text("changed", encoding="utf-8")
    errors = validate_case(
        {"sourceUnchanged": True},
        project,
        {},
        {"src/new.mjs": ("hash", 0o644, "file")},
        [],
    )
    assert any("source changed: src/new.mjs" in error for error in errors)


def test_pending_overall_status_is_not_collapsed_into_passed() -> None:
    assert overall_status([{"status": "passed"}, {"status": "awaiting_user"}]) == "awaiting_user"
    assert overall_status([{"status": "awaiting_user"}, {"status": "failed"}]) == "failed"
    assert overall_status([{"status": "passed"}]) == "passed"


def test_agent_end_provider_diagnostics_are_reported_but_abort_is_ignored_for_pending() -> None:
    diagnostics = agent_end_diagnostics([{
        "kind": "agent_end",
        "stopReason": "error",
        "errorMessage": "provider returned no usable response",
    }])
    assert diagnostics == {
        "stopReason": "error",
        "errorMessage": "provider returned no usable response",
    }
    assert agent_failure_diagnostic(diagnostics, pending=False) == "provider returned no usable response"
    assert agent_failure_diagnostic({"stopReason": "aborted"}, pending=True) == "aborted"
    assert agent_failure_diagnostic(
        {"stopReason": "aborted", "errorMessage": "Request was aborted"},
        pending=True,
        expected_pending_abort=True,
    ) is None
    assert agent_failure_diagnostic(
        {"stopReason": "error", "errorMessage": "This operation was aborted"},
        pending=True,
        expected_pending_abort=True,
    ) is None
    assert agent_failure_diagnostic(
        {"stopReason": "error", "errorMessage": "provider failed"},
        pending=True,
        expected_pending_abort=True,
    ) == "provider failed"
    assert agent_failure_diagnostic(
        {"stopReason": "aborted", "errorMessage": "provider failed"},
        pending=True,
        expected_pending_abort=True,
    ) == "provider failed"
    assert agent_failure_diagnostic({"stopReason": "error"}, pending=True) == "error"


def test_rpc_start_args_join_end_result_and_observer_duplicate_is_collapsed() -> None:
    events = [
        {
            "type": "tool_execution_start",
            "toolCallId": "call-1",
            "toolName": "matt_pocock_workflow",
            "args": {"mode": "capability", "capability": "grilling"},
        },
        {
            "type": "tool_execution_end",
            "toolCallId": "call-1",
            "toolName": "matt_pocock_workflow",
            "isError": False,
            "result": {"state": {"route": "hard-bug", "status": "active"}},
        },
        {
            "kind": "tool_execution_start",
            "toolCallId": "call-1",
            "toolName": "matt_pocock_workflow",
            "args": {"mode": "capability", "capability": "grilling"},
        },
        {
            "kind": "tool_execution_end",
            "toolCallId": "call-1",
            "toolName": "matt_pocock_workflow",
            "result": {"state": {"route": "hard-bug", "status": "active"}},
        },
    ]
    calls = matt_call_records(events)
    assert len(calls) == 1
    assert row_args(calls[0]) == {"mode": "capability", "capability": "grilling"}
    assert row_state(calls[0]) == {"route": "hard-bug", "status": "active"}


def test_rpc_result_details_are_normalized_from_nested_result() -> None:
    calls = matt_call_records([{
        "type": "tool_execution_end",
        "toolCallId": "call-2",
        "toolName": "matt_pocock_workflow",
        "isError": False,
        "result": {"details": {"status": "completed", "state": {"route": "hard-bug"}}},
    }])
    assert row_state(calls[0]) == {"route": "hard-bug", "status": "completed"}


def test_natural_route_accepts_canonical_branch_state_with_flat_result_details() -> None:
    events = [
        {
            "type": "tool_execution_start",
            "toolCallId": "route-1",
            "toolName": "matt_pocock_workflow",
            "args": {"mode": "workflow", "route": "wayfinding"},
        },
        {
            "type": "tool_execution_end",
            "toolCallId": "route-1",
            "toolName": "matt_pocock_workflow",
            "isError": False,
            "result": {"details": {"mode": "workflow", "status": "active"}},
        },
        {
            "kind": "session_start",
            "branch": [{
                "customType": "matt-pocock-workflow",
                "state": {"route": "wayfinding", "status": "active"},
            }],
        },
    ]
    assert validate_case(
        {"routing": True},
        Path("."),
        {},
        {},
        events,
    ) == []


def test_artifact_requires_independent_green_but_pending_does_not() -> None:
    failed = {"available": True, "passed": False, "sandbox": {"positive": {"code": 0}, "negative": {"code": 0}}}
    assert validate_final_fixture_availability({"kind": "artifact"}, failed)
    assert validate_final_fixture_availability({"kind": "pending"}, failed) == []
    unhealthy = {"available": True, "passed": False, "sandbox": {"positive": {"code": 1}}}
    assert validate_final_fixture_availability({"kind": "pending"}, unhealthy)


def test_artifact_symlink_escape_is_rejected_without_reading_outside(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("PRIVATE-SENTINEL", encoding="utf-8")
    (project / "REPORT.md").symlink_to(outside)
    case = {"artifact": "REPORT.md", "keywords": ["PRIVATE-SENTINEL"]}
    summary = artifact_summary(project, case, [])
    errors = validate_case(case, project, {}, {}, [])
    assert summary == {}
    assert any("unsafe or missing artifact" in error for error in errors)
    assert "PRIVATE-SENTINEL" not in json.dumps(summary)


def test_failed_sandbox_positive_probe_is_a_preflight_failure() -> None:
    healthy = {"available": True, "sandbox": {"positive": {"code": 0}, "negative": {"code": 0}}}
    assert fixture_sandbox_healthy(healthy)
    assert not fixture_sandbox_healthy({"available": True, "sandbox": {"positive": {"code": 1}, "negative": {"code": 0}}})
    assert not fixture_sandbox_healthy({"available": True, "sandbox": {"positive": {"code": 0}, "negative": {"code": 1}}})
    assert not fixture_sandbox_healthy({"available": False})


def test_failed_matt_result_and_pending_ask_metadata_are_bounded() -> None:
    calls = summarize_matt_calls([{
        "type": "tool_execution_end",
        "toolCallId": "bad-1",
        "toolName": "matt_pocock_ask",
        "isError": True,
        "result": {"content": [{"type": "text", "text": "x" * 1000}]},
    }])
    assert len(calls[0]["errorContent"]) == 256
    request = summarize_ui_request({
        "method": "select",
        "title": "Question",
        "message": "choose?",
        "options": ["a" * 1000],
        "recommended": "a",
        "timeoutMs": 500,
    }, [])
    assert len(request["options"][0]) == 256
    assert request["recommended"] == "a"
    assert request["timeoutMs"] == 500


def test_matt_ask_call_arguments_keep_question_options_and_recommendation() -> None:
    calls = matt_call_records([{
        "type": "tool_execution_start",
        "toolCallId": "ask-1",
        "toolName": "matt_pocock_ask",
        "args": {
            "question": "Which policy?",
            "options": ["line", "total"],
            "recommended": "missing-option",
            "timeoutMs": 750,
        },
    }, {
        "type": "tool_execution_end",
        "toolCallId": "ask-1",
        "toolName": "matt_pocock_ask",
        "isError": True,
        "result": {"content": [{"type": "text", "text": "The recommended answer must match an offered option."}]},
    }])
    summary = summarize_matt_calls(calls, ["total"])
    assert summary[0]["args"] == {
        "question": "Which policy?",
        "options": ["line", "[REDACTED]"],
        "recommended": "missing-option",
        "timeoutMs": 750,
    }
    assert "recommended answer" in summary[0]["errorContent"]


def test_forbidden_pattern_checks_regular_project_files_with_bounded_reads(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "GLOSSARY.md").write_text("## Open question\nimplementation path: src/receipt.mjs\n", encoding="utf-8")
    case = {
        "forbiddenPatterns": {
            "GLOSSARY.md": [r"src/receipt\.mjs", r"^## Open question"],
        },
    }
    errors = validate_case(case, project, {}, {}, [])
    assert any("forbidden pattern matched GLOSSARY.md" in error for error in errors)


def test_rpc_prompt_waits_for_pi_settlement_after_intermediate_agent_end(monkeypatch) -> None:
    import time
    from real_model_live import RpcRun
    run = object.__new__(RpcRun)
    run.deadline = time.monotonic() + 2
    run.secrets = []
    run.events = []
    run.current_tool = ""
    rows = iter([
        {"type": "agent_end"},
        {"type": "tool_execution_start", "toolName": "write"},
        {"type": "agent_end"},
        {"type": "agent_settled"},
    ])
    monkeypatch.setattr(run, "send", lambda value: None)
    monkeypatch.setattr(run, "next_id", lambda prefix: "request")
    monkeypatch.setattr(run, "read_line", lambda: next(rows, None))
    assert run.prompt("finish the handoff", "unused")["agentEnded"] is True
    assert [row["type"] for row in run.events] == ["agent_end", "tool_execution_start", "agent_end", "agent_settled"]


# ── test_real_model_observer.py ──
"""Pure guard checks for the real-model observer; no model or Pi process is started."""

import json
import stat
from pathlib import Path

from matt_pocock_helpers import run_typescript


def test_project_guard_resolves_relative_paths_and_rejects_escapes(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "verify.test.mjs").write_text("// fixed")
    (tmp_path / "tests-alias").symlink_to(tmp_path / "tests", target_is_directory=True)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    result = run_typescript(f'''
        import {{ guardToolInput, selfCheck }} from "./packages/matt-pocock/tests/real-model-observer.ts";
        const root = {str(tmp_path)!r};
        console.log(JSON.stringify({{
          read: guardToolInput(root, "read", {{ path: "tests/verify.test.mjs" }}),
          write: guardToolInput(root, "write", {{ path: ".fixture-output" }}),
          verifyWrite: guardToolInput(root, "write", {{ path: "tests/verify.test.mjs" }}),
          verifyEdit: guardToolInput(root, "edit", {{ path: "tests/verify.test.mjs" }}),
          testsDirectoryWrite: guardToolInput(root, "write", {{ path: "tests" }}),
          aliasVerifyWrite: guardToolInput(root, "write", {{ path: "tests-alias/verify.test.mjs" }}),
          aliasParentWrite: guardToolInput(root, "write", {{ path: "tests-alias" }}),
          artifactThroughProject: guardToolInput(root, "write", {{ path: ".fixture-output" }}),
          parent: guardToolInput(root, "read", {{ path: "../outside/file" }}),
          symlink: guardToolInput(root, "read", {{ path: "link/secret" }}),
          self: selfCheck(root),
        }}));
    ''')
    assert result["read"] == {"allowed": True}
    assert result["write"] == {"allowed": True}
    assert result["verifyWrite"]["allowed"] is False
    assert result["verifyEdit"]["allowed"] is False
    assert result["testsDirectoryWrite"]["allowed"] is False
    assert result["aliasVerifyWrite"]["allowed"] is False
    assert result["aliasParentWrite"]["allowed"] is False
    assert result["artifactThroughProject"] == {"allowed": True}
    assert result["parent"]["allowed"] is False
    assert result["symlink"]["allowed"] is False
    assert result["self"] == {"allowedRead": True, "allowedWrite": True, "parentEscapeRejected": True}


def test_non_file_tools_and_missing_optional_paths_remain_unrestricted(tmp_path: Path) -> None:
    result = run_typescript(f'''
        import {{ guardToolInput }} from "./packages/matt-pocock/tests/real-model-observer.ts";
        const root = {str(tmp_path)!r};
        console.log(JSON.stringify({{
          custom: guardToolInput(root, "fixture_checks", {{ value: "ignored" }}),
          optional: guardToolInput(root, "grep", {{ pattern: "x" }}),
          invalidRoot: guardToolInput(undefined, "read", {{ path: "x" }}),
        }}));
    ''')
    assert result["custom"] == {"allowed": True}
    assert result["optional"] == {"allowed": True}
    assert result["invalidRoot"]["allowed"] is False


def test_fixture_checks_runs_real_sandbox_self_checks_without_a_model(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "verify.test.mjs").write_text("import test from 'node:test'; console.log('x'.repeat(10000)); test('fixed', () => {});\n")
    (tmp_path.parent / f"{tmp_path.name}-external-secret.txt").write_text("must stay outside the fixture sandbox")
    evidence = tmp_path / "evidence.jsonl"
    result = run_typescript(f'''
        process.env.MP_REAL_PROJECT = {str(tmp_path)!r};
        process.env.MP_REAL_EVIDENCE = {str(evidence)!r};
        import observer from "./packages/matt-pocock/tests/real-model-observer.ts";
        const tools = [];
        observer({{ on() {{ return () => {{}}; }}, registerTool(tool) {{ tools.push(tool); }}, getActiveTools() {{ return []; }} }});
        const ctx = {{ signal: undefined }};
        const value = await tools[0].execute("self-check", {{}}, undefined, undefined, ctx);
        console.log(JSON.stringify(value));
    ''')
    assert result["details"]["available"] is True
    assert result["details"]["sandbox"]["positive"]["code"] == 0
    assert result["details"]["sandbox"]["negative"]["code"] == 0
    assert result["details"]["passed"] is True
    assert len(result["details"]["node"]["stdout"]) <= 4_000


def test_fixture_checks_canonicalizes_var_alias_before_building_sandbox(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "verify.test.mjs").write_text("import test from 'node:test'; test('fixed', () => {});\n")
    (tmp_path.parent / f"{tmp_path.name}-external-secret.txt").write_text("must stay outside the fixture sandbox")
    alias = str(tmp_path).replace("/private/var/", "/var/", 1)
    assert alias != str(tmp_path)
    result = run_typescript(f'''
        process.env.MP_REAL_EVIDENCE = {str(tmp_path / "evidence.jsonl")!r};
        import {{ runFixtureChecks }} from "./packages/matt-pocock/tests/real-model-observer.ts";
        console.log(JSON.stringify(await runFixtureChecks({alias!r}, undefined)));
    ''')
    assert result["details"]["available"] is True
    assert result["details"]["passed"] is True


def test_agent_end_records_error_diagnostic_and_aggregates_assistant_usage(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.jsonl"
    result = run_typescript(f'''
        process.env.MP_REAL_PROJECT = {str(tmp_path)!r};
        process.env.MP_REAL_EVIDENCE = {str(evidence)!r};
        import observer from "./packages/matt-pocock/tests/real-model-observer.ts";
        const handlers = new Map();
        let aborted = false;
        const pi = {{ on(name, handler) {{ handlers.set(name, handler); }}, registerTool() {{}}, getActiveTools() {{ return ["read"]; }} }};
        observer(pi);
        const ctx = {{ mode: "json", cwd: {str(tmp_path)!r}, sessionManager: {{ getBranch: () => [] }}, abort() {{ aborted = true; }} }};
        await handlers.get("agent_end")({{ messages: [
          {{ role: "assistant", content: [{{ type: "text", text: "first" }}], usage: {{ input: 2, output: 3 }} }},
          {{ role: "assistant", content: [{{ type: "text", text: "last" }}], usage: {{ input: 5, output: 7 }}, stopReason: "error", errorMessage: "provider diagnostic" }},
        ] }}, ctx);
        console.log(JSON.stringify({{ aborted, evidence: (await import("node:fs")).readFileSync({str(evidence)!r}, "utf8") }}));
    ''')
    row = json.loads(result["evidence"].strip())
    assert result["aborted"] is False
    assert row["kind"] == "agent_end"
    assert row["stopReason"] == "error"
    assert row["errorMessage"] == "provider diagnostic"
    assert row["usage"] == {"input": 7, "output": 10}
    assert stat.S_IMODE(evidence.stat().st_mode) == 0o600


def test_matt_tool_metadata_carries_start_args_and_normalized_result_fields(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.jsonl"
    result = run_typescript(f'''
        process.env.MP_REAL_PROJECT = {str(tmp_path)!r};
        process.env.MP_REAL_EVIDENCE = {str(evidence)!r};
        import observer from "./packages/matt-pocock/tests/real-model-observer.ts";
        const handlers = new Map();
        const pi = {{ on(name, handler) {{ handlers.set(name, handler); }}, registerTool() {{}}, getActiveTools() {{ return []; }} }};
        observer(pi);
        const ctx = {{ abort() {{}} }};
        await handlers.get("tool_execution_start")({{ toolCallId: "matt-1", toolName: "matt_pocock_workflow", args: {{ mode: "workflow", route: "hard-bug" }} }}, ctx);
        await handlers.get("tool_execution_end")({{ toolCallId: "matt-1", toolName: "matt_pocock_workflow", isError: false, result: {{ content: [{{ type: "text", text: "bounded" }}], details: {{ mode: "workflow", route: "hard-bug", passed: true, available: true, node: {{ code: 0 }}, state: {{ route: "hard-bug", procedure: "investigate", phase: "reproduce", status: "active", workItemId: "w-1" }} }} }} }}, ctx);
        console.log(JSON.stringify((await import("node:fs")).readFileSync({str(evidence)!r}, "utf8")));
    ''')
    rows = [json.loads(line) for line in result.strip().splitlines()]
    start, end = rows
    assert start["args"] == {"mode": "workflow", "capability": None, "route": "hard-bug", "reference": None, "action": None, "target": None}
    assert end["args"] == start["args"]
    assert end["result"] == {
        "mode": "workflow",
        "capability": None,
        "route": "hard-bug",
        "reference": None,
        "passed": True,
        "available": True,
        "nodeCode": 0,
        "contentParts": 1,
        "textBytes": 7,
        "detailsKeys": ["available", "mode", "node", "passed", "route", "state"],
        "structuredKeys": [],
        "status": None,
        "action": None,
        "pending": None,
        "state": {"route": "hard-bug", "procedure": "investigate", "phase": "reproduce", "status": "active", "workItemId": "w-1"},
    }


def test_context_snapshot_preserves_persisted_workflow_before_agent_end(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.jsonl"
    result = run_typescript(f'''
        process.env.MP_REAL_PROJECT = {str(tmp_path)!r};
        process.env.MP_REAL_EVIDENCE = {str(evidence)!r};
        import observer from "./packages/matt-pocock/tests/real-model-observer.ts";
        const handlers = new Map();
        const pi = {{ on(name, handler) {{ handlers.set(name, handler); }}, registerTool() {{}}, getActiveTools() {{ return ["matt_pocock_workflow"]; }} }};
        observer(pi);
        const ctx = {{ mode: "json", cwd: {str(tmp_path)!r}, sessionManager: {{ getBranch: () => [{{ type: "custom", customType: "matt-pocock-workflow", data: {{ route: "hard-bug", procedure: "investigate", phase: "reproduce", status: "active", workItemId: "w-2" }} }}] }}, abort() {{}} }};
        await handlers.get("context")({{ messages: [{{ role: "user", content: "route request" }}] }}, ctx);
        console.log(JSON.stringify((await import("node:fs")).readFileSync({str(evidence)!r}, "utf8")));
    ''')
    row = json.loads(result.strip())
    assert row["kind"] == "model_context"
    assert row["activeTools"] == ["matt_pocock_workflow"]
    assert row["branch"][0]["customType"] == "matt-pocock-workflow"
    assert row["branch"][0]["state"] == {"route": "hard-bug", "procedure": "investigate", "phase": "reproduce", "status": "active", "workItemId": "w-2"}


def test_ask_metadata_is_filtered_and_error_text_is_bounded(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.jsonl"
    result = run_typescript(f'''
        process.env.MP_REAL_PROJECT = {str(tmp_path)!r};
        process.env.MP_REAL_EVIDENCE = {str(evidence)!r};
        import observer from "./packages/matt-pocock/tests/real-model-observer.ts";
        const handlers = new Map();
        const pi = {{ on(name, handler) {{ handlers.set(name, handler); }}, registerTool() {{}}, getActiveTools() {{ return []; }} }};
        observer(pi);
        const ctx = {{ abort() {{}} }};
        await handlers.get("tool_execution_start")({{ toolCallId: "ask-1", toolName: "matt_pocock_ask", args: {{ title: "t".repeat(900), question: "q".repeat(900), options: ["a".repeat(900), "b", "c", "d", "ignored"], recommended: "a".repeat(900), timeout_seconds: 12, allow_custom: false }} }}, ctx);
        await handlers.get("tool_execution_end")({{ toolCallId: "ask-1", toolName: "matt_pocock_ask", isError: true, result: {{ content: [{{ type: "text", text: "schema error: " + "x".repeat(900) }}], details: {{}} }} }}, ctx);
        console.log(JSON.stringify((await import("node:fs")).readFileSync({str(evidence)!r}, "utf8")));
    ''')
    start, end = [json.loads(line) for line in result.strip().splitlines()]
    args = start["args"]
    assert len(args["title"]) == 512
    assert len(args["question"]) == 512
    assert len(args["options"]) == 4
    assert all(len(option) <= 512 for option in args["options"])
    assert args["timeout_seconds"] == 12
    assert args["allow_custom"] is False
    assert end["args"] == args
    assert len(end["result"]["errorText"]) <= 256


def test_developer_tool_budget_is_finite_and_bounded() -> None:
    from matt_pocock_helpers import run_typescript
    result = run_typescript('''
        import { realModelToolBudget } from "./packages/matt-pocock/tests/real-model-observer.ts";
        console.log(JSON.stringify({budgets:["40", "80", "0", "81", "Infinity", "1.5", "-1", ""].map(realModelToolBudget)}));
    ''')
    assert result["budgets"] == [40, 80, 40, 40, 40, 40, 40, 40]


def test_exhausted_budget_blocks_followup_turns_before_execution(tmp_path: Path) -> None:
    result = run_typescript(f'''
        process.env.MP_REAL_PROJECT = {str(tmp_path)!r};
        process.env.MP_REAL_EVIDENCE = {str(tmp_path / "evidence.jsonl")!r};
        process.env.MP_REAL_TOOL_BUDGET = "1";
        import observer from "./packages/matt-pocock/tests/real-model-observer.ts";
        const handlers = new Map();
        let aborts = 0;
        observer({{on(name, handler) {{handlers.set(name,handler);}}, registerTool() {{}}, getActiveTools() {{return [];}}}});
        const input = {{toolName:"fixture_checks",input:{{}}}};
        const before = await handlers.get("tool_call")(input);
        await handlers.get("tool_execution_start")({{toolCallId:"one",toolName:"fixture_checks",args:{{}}}}, {{abort() {{aborts++;}}}});
        const after = await handlers.get("tool_call")(input);
        console.log(JSON.stringify({{before:before ?? null,after:after ?? null,aborts}}));
    ''')
    assert result["before"] is None
    assert result["aborts"] == 1
    assert result["after"]["block"] is True
    assert result["after"]["terminate"] is True


def test_fixture_diagnostics_are_visible_and_redacted(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/verify.test.mjs").write_text("import test from 'node:test'; test('observed failure',()=>{throw new Error('diagnostic sentinel-private-token');});")
    (tmp_path.parent / f"{tmp_path.name}-external-secret.txt").write_text("public sentinel")
    result = run_typescript(f'''
        process.env.OPENAI_API_KEY = "sentinel-private-token";
        import {{ runFixtureChecks }} from "./packages/matt-pocock/tests/real-model-observer.ts";
        console.log(JSON.stringify(await runFixtureChecks({str(tmp_path)!r}, undefined)));
    ''')
    content = result["content"][0]["text"]
    assert "observed failure" in content
    assert "diagnostic [REDACTED]" in content
    assert "sentinel-private-token" not in content
    assert len(content) < 17000


def test_fixture_diagnostics_redact_secrets_across_output_limit(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    token = "sentinel-sensitive-token"
    (tmp_path / "tests/verify.test.mjs").write_text("console.log('x'.repeat(3980)+'" + token + "');")
    (tmp_path.parent / f"{tmp_path.name}-external-secret.txt").write_text("public sentinel")
    result = run_typescript(f'''
        process.env.OPENAI_API_KEY = {token!r};
        import {{ runFixtureChecks }} from "./packages/matt-pocock/tests/real-model-observer.ts";
        console.log(JSON.stringify(await runFixtureChecks({str(tmp_path)!r}, undefined)));
    ''')
    assert "sentinel-sensitive" not in result["content"][0]["text"]
    assert "sentinel-sensitive" not in result["details"]["node"]["stdout"]


def test_completion_tracker_preserves_line_boundaries_across_chunks() -> None:
    result=run_typescript(r'''
        import {acceptanceCompletionTracker} from "./packages/matt-pocock/tests/real-model-observer.ts";
        const marker='MP_ACCEPTANCE_COMPLETE_abcdef';
        const comment='# ok 99 - '+marker+'\n'+'# '.repeat(100)+'\n';
        const checks=[];
        for(let split=0;split<=comment.length;split++) {
          const track=acceptanceCompletionTracker(marker);
          checks.push(track(comment.slice(0,split)),track(comment.slice(split)));
        }
        const track=acceptanceCompletionTracker(marker);
        const actual=[track('x'.repeat(2000)+'\nok 1 - '+marker.slice(0,20)),track(marker.slice(20)+'\n')];
        console.log(JSON.stringify({checks,actual}));
    ''')
    assert not any(result['checks'])
    assert result['actual'] == [False,True]


# ── test_real_model_semantics.py ──
"""Semantic acceptance checks for the procedures used by real-model runs."""


from matt_pocock_helpers import run_typescript


def delivered_procedure_bundles() -> dict[str, str]:
    result = run_typescript(
        """
        import { resolveProcedureDelta } from "./packages/matt-pocock/src/resolver.ts";
        const ids = ["domain-modeling", "code-review", "to-questionnaire", "prototype", "codebase-design", "deslop",
          "grilling", "grill-me", "grill-with-docs", "pr", "retro", "to-tickets", "improve-codebase-architecture"];
        const delivered = Object.fromEntries(ids.map((id) => [
          id, resolveProcedureDelta(id, [], []).content,
        ]));
        console.log(JSON.stringify(delivered));
        """
    )
    return {key: str(value) for key, value in result.items()}


def test_domain_delivery_separates_glossary_vocabulary_from_implementation_and_unknown_policy() -> None:
    bundle = delivered_procedure_bundles()["domain-modeling"]

    assert "totally devoid of implementation details" in bundle
    assert "implementation paths, function behavior, tests" in bundle
    assert "unresolved policy" in bundle
    assert "do not state a universal policy" in bundle.lower()
    assert "Do not add Open questions or Resolutions sections" in bundle


def test_code_review_delivery_blocks_spec_pass_for_unresolved_scope_creep() -> None:
    bundle = delivered_procedure_bundles()["code-review"]

    assert "scope creep" in bundle
    assert "Spec finding" in bundle
    assert "Spec PASS" in bundle
    assert "non-breaking" in bundle
    assert "explicit compatibility requirement" in bundle


def test_questionnaire_delivery_requires_verified_context_and_single_decision_questions() -> None:
    bundle = delivered_procedure_bundles()["to-questionnaire"]

    assert "observed current behavior" in bundle
    assert "target behavior" in bundle
    assert "unresolved decision" in bundle
    assert "one independent decision" in bundle
    assert "do not combine" in bundle.lower()


def test_prototype_delivery_limits_conclusions_to_measured_results() -> None:
    bundle = delivered_procedure_bundles()["prototype"]

    assert "measured results" in bundle
    assert "proposed production choices" in bundle
    assert "unresolved policy" in bundle
    assert "not tested" in bundle


def test_grilling_delivery_keeps_the_required_recommendation_policy() -> None:
    """The question policy is a local contract: a sync must not drop it silently."""
    for capability in ("grilling", "grill-me", "grill-with-docs"):
        bundle = delivered_procedure_bundles()[capability]
        assert "matt_pocock_ask" in bundle, capability
        assert "recommended" in bundle, capability
        assert "waits indefinitely" in bundle or "deadline" in bundle, capability

    grilling = delivered_procedure_bundles()["grilling"]
    assert "required `recommended` value" in grilling
    assert "recommend the option that does not act" in grilling


def test_delivered_procedures_keep_the_written_deliverable_policy() -> None:
    """A procedure whose deliverable is a file must keep that requirement after a sync."""
    bundles = delivered_procedure_bundles()

    assert "do not end the turn until that file exists" in bundles["pr"]
    assert "do not end the turn before it exists" in bundles["to-questionnaire"]
    assert "writes the report and nothing else" in bundles["improve-codebase-architecture"]


def test_design_delivery_separates_sourced_requirements_from_proposed_invariants() -> None:
    bundle = delivered_procedure_bundles()["codebase-design"]

    assert "sourced requirements" in bundle
    assert "proposed invariants" in bundle
    assert "assumptions or unresolved decisions" in bundle


def test_review_requires_reachable_interleaving_for_concurrency_claims() -> None:
    bundle = delivered_procedure_bundles()["code-review"]
    assert "reachable interleaving" in bundle
    assert "actual public API" in bundle
    assert "hypothetical future" in bundle


def test_cleanup_cannot_call_retained_findings_clean() -> None:
    bundle = delivered_procedure_bundles()["deslop"]
    assert "retained finding" in bundle
    assert "readability preference" in bundle
    assert "PARTIAL" in bundle


def test_review_judgement_calls_do_not_erase_unresolved_smells() -> None:
    bundle = delivered_procedure_bundles()["code-review"]
    assert "changes confidence, not the verdict" in bundle
    assert "no lint rule" in bundle


def test_cleanup_records_only_observed_command_failures() -> None:
    bundle = delivered_procedure_bundles()["deslop"]
    assert "actually failed command" in bundle
    assert "unexecuted alternative" in bundle


def test_cleanup_inert_predicate_removal_is_not_a_product_policy_change() -> None:
    bundle = delivered_procedure_bundles()["deslop"]
    assert "Removing a proven inert predicate" in bundle
    assert "does not require changing the spec" in bundle


def test_teaching_existing_application_requires_separate_repair_authorization() -> None:
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "procedures/teach.md").read_text()
    assert "do not modify application source" in text
    assert "separate implementation request" in text
    assert "ask the mission question and wait" in text


# ── test_developer_journeys.py ──
"""Independent fixture contracts; these checks never call a model."""
from pathlib import Path

import pytest

from real_model_live import fixture_sandbox_healthy, load_cases, run_fixture_checks_direct, write_project


@pytest.mark.parametrize("fixture,green", [("discount", False), ("cache", False), ("config", True)])
def test_developer_acceptance_baselines(tmp_path: Path, fixture: str, green: bool) -> None:
    project = tmp_path / "project"
    project.mkdir()
    write_project(project, {"fixture": fixture, "checkTests": True})
    (tmp_path / "project-external-secret.txt").write_text("public sentinel")
    checks = run_fixture_checks_direct(project)
    assert fixture_sandbox_healthy(checks)
    assert checks["passed"] is green
    assert (project / "tests/verify.test.mjs").stat().st_mode & 0o222 == 0


def test_developer_case_catalog_contains_complete_local_journeys() -> None:
    cases = load_cases(Path(__file__).with_name("developer-journey-cases.json"))
    assert len(cases) == 3
    assert all(case["replies"] and case["checkTests"] for case in cases)
    assert {case["fixture"] for case in cases} == {"discount", "cache", "config"}
    assert all(case["terminal"] == "completed" for case in cases if case.get("route"))


def test_completed_label_cannot_replace_required_workflow_stages(tmp_path: Path) -> None:
    from real_model_live import validate_case
    state = {"route": "idea-to-ship", "procedure": "grill-with-docs", "status": "completed", "workItemId": "one"}
    events = [{"kind": "model_context", "sourceIds": ["grill-with-docs"], "branch": [
        {"customType": "matt-pocock-workflow", "state": state},
    ]}]
    errors = validate_case({"requiredStages": ["implement", "code-review"]}, tmp_path, {}, {}, events)
    assert "required workflow stages were not observed: implement, code-review" in errors


def test_restarting_a_workflow_cannot_replace_the_original_journey(tmp_path: Path) -> None:
    from real_model_live import validate_case
    events = [{"kind": "model_context", "branch": [
        {"customType": "matt-pocock-workflow", "state": {"workItemId": "one"}},
        {"customType": "matt-pocock-workflow", "state": {"workItemId": "two"}},
    ]}]
    errors = validate_case({"singleWorkItem": True}, tmp_path, {}, {}, events)
    assert "journey restarted with a different work item" in errors


def test_cache_acceptance_rejects_clear_all_on_failure(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    write_project(project, {"fixture": "cache", "checkTests": True})
    (tmp_path / "project-external-secret.txt").write_text("public sentinel")
    (project / "src/cache.mjs").write_text('''
export function createCache(load) {
  const entries = new Map();
  return {get(key) {
    if (!entries.has(key)) {
      const pending = Promise.resolve().then(() => load(key));
      pending.catch(() => entries.clear());
      entries.set(key, pending);
    }
    return entries.get(key);
  }};
}
''')
    checks = run_fixture_checks_direct(project)
    assert fixture_sandbox_healthy(checks)
    assert checks["passed"] is False


# ── test_expanded_types.py ──
"""Independent acceptance baselines for the broader developer task types."""
from pathlib import Path

import pytest

from real_model_live import load_cases, write_project, run_fixture_checks_direct, fixture_sandbox_healthy

TYPES = ("frontend", "api", "authorization", "migration", "performance", "localization", "paths", "test-design")


@pytest.mark.parametrize("task_type", TYPES)
def test_expanded_fixture_reproduces_its_own_defect(tmp_path: Path, task_type: str) -> None:
    project = tmp_path / "project"
    project.mkdir()
    write_project(project, {"fixture": task_type, "checkTests": True})
    (tmp_path / "project-external-secret.txt").write_text("public sandbox sentinel")
    assert (project / "src/feature.mjs").is_file()
    assert not (project / "src/receipt.mjs").exists()
    check = run_fixture_checks_direct(project)
    assert fixture_sandbox_healthy(check)
    assert check["passed"] is False
    assert (project / "tests/verify.test.mjs").stat().st_mode & 0o222 == 0


def test_unknown_fixture_fails_before_model_execution(tmp_path: Path) -> None:
    catalog = tmp_path / "cases.json"
    catalog.write_text('[{"id":"typo","fixture":"does-not-exist","prompt":"x"}]')
    with pytest.raises(ValueError, match="unknown fixture"):
        load_cases(catalog)


@pytest.mark.parametrize("fixture", [[], {}, 0, False])
def test_malformed_fixture_type_has_a_controlled_catalog_error(tmp_path: Path, fixture) -> None:
    import json
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"id":"bad","fixture":fixture,"prompt":"x"}]))
    with pytest.raises(ValueError, match="unknown fixture"):
        load_cases(path)


def test_early_successful_exit_cannot_skip_acceptance(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    project.mkdir()
    write_project(project, {'fixture':'authorization','checkTests':True})
    (tmp_path / 'project-external-secret.txt').write_text('public sentinel')
    (project / 'src/feature.mjs').write_text('process.exit(0); export function canRead(){return true;}')
    check = run_fixture_checks_direct(project)
    assert fixture_sandbox_healthy(check)
    assert check['passed'] is False


def test_printing_the_completion_marker_cannot_skip_acceptance(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    project.mkdir()
    write_project(project, {'fixture':'authorization','checkTests':True})
    (tmp_path / 'project-external-secret.txt').write_text('public sentinel')
    (project / 'src/feature.mjs').write_text("import fs from 'node:fs'; const text=fs.readFileSync('tests/verify.test.mjs','utf8'); const marker=text.match(/MP_ACCEPTANCE_COMPLETE_[a-f0-9]+/)[0]; console.log('ok 99 - '+marker); process.exit(0); export function canRead(){return true;}")
    check = run_fixture_checks_direct(project)
    assert fixture_sandbox_healthy(check)
    assert check['passed'] is False


# ── test_type_coverage.py ──
"""The current public catalog must have real invocation case contracts."""
from pathlib import Path

from real_model_live import load_cases
from type_inventory import inventory


def test_every_supported_public_type_has_a_real_case() -> None:
    report = inventory()
    assert report["missingPublicTypes"] == []
    assert set(report["resourceKinds"]) == {"workflow", "utility", "reference", "asset"}
    assert set(report["invocationModes"]) == {"model", "user", "internal"}
    assert report["transitions"] > report["placements"]


def test_omitted_public_cases_are_reported_as_gaps() -> None:
    root = Path(__file__).parent
    cases = [case for name in ("real-model-cases.json", "developer-journey-cases.json", "expanded-type-cases.json") for case in load_cases(root / name)]
    cases = [case for case in cases if case.get("expectSource") != "research"]
    assert "standalone:research" in inventory(cases)["missingPublicTypes"]


# ── test_docker_minimal_token.py ──
"""Grading never upgrades an incomplete compact study into a pass."""
import importlib.util
import json
from pathlib import Path

LOCATION = Path(__file__).parent / "docker-study/minimal.py"
SPEC = importlib.util.spec_from_file_location("matt_minimal_grade", LOCATION)
assert SPEC is not None and SPEC.loader is not None
GRADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRADER)


def native_fixture() -> dict:
    return {
        "registered": ["matt_pocock_active", "matt_pocock_ask", "matt_pocock_workflow"],
        "commands": ["matt-pocock"],
        "workflowCommand": {"route": "hard-bug", "procedure": "diagnosing-bugs", "status": "active",
            "request": "Fix receipt quantity", "hasStateContract": True, "textBytes": 100},
        "workflowState": {"status": "active", "workItemId": "item-1"},
        "restore": {"persistedRecordsAdded": 0,
            "activeTools": ["matt_pocock_workflow", "matt_pocock_active", "matt_pocock_ask"]},
        "transition": {"procedure": "implement", "hasStateContract": True,
            "parameters": ["action", "target", "reference", "reason"], "textBytes": 100},
        "ask": {"pending": True, "source": "no_ui"},
        "completed": {"status": "completed", "workItemId": "item-1",
            "activeTools": ["matt_pocock_workflow"]},
        "capability": {"mode": "capability", "hasSource": True, "textBytes": 100},
        "userCapability": {"mode": "user-capability", "textBytes": 100},
        "reference": {"mode": "reference", "hasHeading": True, "textBytes": 100},
        "invalidCapabilityRefused": True,
        "workflowReference": {"action": "load", "textBytes": 100},
        "cancelled": {"status": "cancelled", "reason": "done",
            "activeTools": ["matt_pocock_workflow"]},
        "unknownRouting": {"customType": "matt-pocock-procedure", "textHasRouting": True},
    }


def fixture(root: Path, *, mutate=None, requests: int = 2, errors: int = 0,
            reasoning: str = "none") -> dict:
    native = native_fixture()
    if mutate:
        mutate(native)
    (root / "native.json").write_text(json.dumps(native))
    (root / "parent-tui.json").write_text(json.dumps({"markerObserved": True,
        "gatewayRowObserved": True, "expandRepaintObserved": True, "resizeRepaintObserved": True}))
    return {"requests": requests, "transportErrors": errors, "piVersion": "1.5.0",
        "workspacePiVersions": {"kit": "1.5.0", "matt-pocock": "1.5.0"},
        "modelObservations": [{"reasoningEffortOnWire": reasoning, "toolCount": 2}]
        * requests}


def test_compact_study_passes_only_with_all_native_and_real_model_contracts(tmp_path: Path) -> None:
    metadata = fixture(tmp_path)
    graded = GRADER.grade(tmp_path, metadata)
    assert graded["passed"] is True, [name for name, value in graded["checks"].items() if not value]
    assert graded["nativeInjectedBytes"] == 600


def test_missing_workflow_state_reasoning_or_transport_health_fails_grading(tmp_path: Path) -> None:
    cases = [
        (lambda value: value["workflowState"].update(status="cancelled"), 2, 0, "none"),
        (None, 2, 0, "low"),
        (None, 2, 1, "none"),
        (None, 0, 0, "none"),
    ]
    for index, (mutate, requests, errors, reasoning) in enumerate(cases):
        root = tmp_path / f"case-{index}"
        root.mkdir()
        metadata = fixture(root, mutate=mutate, requests=requests,
            errors=errors, reasoning=reasoning)
        graded = GRADER.grade(root, metadata)
        assert graded["passed"] is False, index
        assert [name for name, value in graded["checks"].items() if not value]


def test_crossover_capability_refusal_is_required(tmp_path: Path) -> None:
    metadata = fixture(tmp_path,
        mutate=lambda value: value.update(invalidCapabilityRefused=False))
    graded = GRADER.grade(tmp_path, metadata)
    assert graded["checks"]["invalidCrossoverRefused"] is False
    assert graded["passed"] is False
