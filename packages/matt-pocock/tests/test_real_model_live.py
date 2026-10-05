"""Pure regressions for the real-model RPC harness.

These tests replay protocol metadata only; they never start Pi or a provider.
"""
from __future__ import annotations

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
