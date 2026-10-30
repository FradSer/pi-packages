from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


TESTS = Path(__file__).parent
sys.path.insert(0, str(TESTS))

from live_manual_harness import _inspect_native_authoring, _validate_authored_rules  # noqa: E402
from live_harness_first_run import current_guidance_delivered  # noqa: E402


def test_current_guidance_requires_every_authored_revision_and_body() -> None:
    authored = {'rules': [{'id': name, 'instructions': f'{name} body'} for name in ('first', 'second')]}
    expected = [{'id': name, 'revision': f'{name}-revision'} for name in ('first', 'second')]
    records = [
        {'type': 'custom', 'customType': 'harness-guidance-delivery',
         'data': {'entries': [{**entry, 'status': 'active'} for entry in expected]}},
        {'type': 'message', 'message': {'role': 'system', 'sections': {
            'harness_guidance': '[harness:first] first body\n[harness:second] second body'}}},
    ]
    assert current_guidance_delivered(records, authored, expected)
    assert not current_guidance_delivered(records, authored, [])
    records[0]['data']['entries'].pop()
    assert not current_guidance_delivered(records, authored, expected)
    records[0]['data']['entries'].append({**expected[1], 'status': 'active'})
    records[1]['message']['sections']['harness_guidance'] = '[harness:first] first body'
    assert not current_guidance_delivered(records, authored, expected)
    records[1]['message']['sections']['harness_guidance'] += '\n[harness:second] stale body'
    assert not current_guidance_delivered(records, authored, expected)


def _session(path: Path, messages: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps({"type": "message", "message": message}) for message in messages) + "\n",
        encoding="utf-8",
    )


def test_authoring_trace_requires_one_successful_complete_target_write(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = project / ".pi" / "harness.json"
    target.parent.mkdir()
    candidate = {"rules": [{"id": "existing", "bash": "^printf\\s+EXISTING$", "message": "keep"}]}
    session = tmp_path / "session.jsonl"
    _session(session, [
        {"role": "assistant", "content": [{"type": "toolCall", "id": "read", "name": "read", "arguments": {"path": ".pi/harness.json"}}]},
        {"role": "toolResult", "toolCallId": "read", "toolName": "read", "isError": False, "content": [{"type": "text", "text": json.dumps(candidate)}]},
        {"role": "assistant", "content": [{"type": "toolCall", "id": "write", "name": "write", "arguments": {"path": ".pi/harness.json", "content": json.dumps(candidate)}}]},
        {"role": "toolResult", "toolCallId": "write", "toolName": "write", "isError": False, "content": [{"type": "text", "text": "Successfully wrote"}]},
    ])

    assert _inspect_native_authoring(session, project, target, (project / ".pi/harness.local.json",), json.dumps(candidate).encode()) == {
        "targetReadBeforeWrite": True,
        "completePredecessorRead": True,
        "successfulTargetWrites": 1,
        "completeJsonTargetWrite": True,
        "editCalls": 0,
        "otherLayerWrites": 0,
    }


def test_authoring_trace_rejects_edit_and_second_target_write(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = project / ".pi" / "harness.json"
    session = tmp_path / "session.jsonl"
    call = lambda ident, name, args: {"role": "assistant", "content": [{"type": "toolCall", "id": ident, "name": name, "arguments": args}]}
    result = lambda ident, name: {"role": "toolResult", "toolCallId": ident, "toolName": name, "isError": False, "content": [{"type": "text", "text": "ok"}]}
    _session(session, [
        call("read", "read", {"path": ".pi/harness.json"}),
        result("read", "read"),
        call("write1", "write", {"path": ".pi/harness.json", "content": "{}"}),
        result("write1", "write"),
        call("write2", "write", {"path": ".pi/harness.json", "content": "{}"}),
        result("write2", "write"),
        call("edit", "edit", {"path": ".pi/harness.json"}),
        result("edit", "edit"),
    ])

    with pytest.raises(AssertionError, match="exactly one successful target write"):
        _inspect_native_authoring(session, project, target, (), b'{"rules": []}')


def test_authored_rules_reject_wrong_target_patterns(tmp_path: Path) -> None:
    existing = {"id": "manual-existing-project", "bash": "^printf\\s+MANUAL_EXISTING$", "message": "keep"}
    authored = {
        "rules": [
            existing,
            {"id": "manual-harness-block", "bash": "^printf\\s+WRONG$", "action": "block", "message": "block"},
            {"id": "manual-harness-safe", "bash": "^printf\\s+CL_MANUAL_HARNESS_SAFE$", "message": "safe"},
        ],
    }
    target = tmp_path / "harness.json"
    target.write_text(json.dumps(authored), encoding="utf-8")

    with pytest.raises(AssertionError, match="block rule did not match"):
        _validate_authored_rules(target, existing)


def test_authoring_trace_rejects_empty_successful_predecessor_read(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = project / ".pi" / "harness.json"
    session = tmp_path / "session.jsonl"
    candidate = {"rules": [{"id": "existing", "bash": "^printf\\s+EXISTING$", "message": "keep"}]}
    _session(session, [
        {"role": "assistant", "content": [{"type": "toolCall", "id": "read", "name": "read", "arguments": {"path": ".pi/harness.json"}}]},
        {"role": "toolResult", "toolCallId": "read", "toolName": "read", "isError": False, "content": []},
        {"role": "assistant", "content": [{"type": "toolCall", "id": "write", "name": "write", "arguments": {"path": ".pi/harness.json", "content": json.dumps(candidate)}}]},
        {"role": "toolResult", "toolCallId": "write", "toolName": "write", "isError": False, "content": [{"type": "text", "text": "Successfully wrote"}]},
    ])

    with pytest.raises(AssertionError, match="complete predecessor"):
        _inspect_native_authoring(session, project, target, (), json.dumps(candidate).encode())


def test_authoring_trace_rejects_read_result_after_write_call(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = project / ".pi" / "harness.json"
    session = tmp_path / "session.jsonl"
    candidate = {"rules": [{"id": "existing", "bash": "^printf\\s+EXISTING$", "message": "keep"}]}
    _session(session, [
        {"role": "assistant", "content": [{"type": "toolCall", "id": "read", "name": "read", "arguments": {"path": ".pi/harness.json"}}]},
        {"role": "assistant", "content": [{"type": "toolCall", "id": "write", "name": "write", "arguments": {"path": ".pi/harness.json", "content": json.dumps(candidate)}}]},
        {"role": "toolResult", "toolCallId": "read", "toolName": "read", "isError": False, "content": [{"type": "text", "text": json.dumps(candidate)}]},
        {"role": "toolResult", "toolCallId": "write", "toolName": "write", "isError": False, "content": [{"type": "text", "text": "Successfully wrote"}]},
    ])

    with pytest.raises(AssertionError, match="complete predecessor"):
        _inspect_native_authoring(session, project, target, (), json.dumps(candidate).encode())


def test_authoring_trace_rejects_mismatched_result_tool_name(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = project / ".pi" / "harness.json"
    session = tmp_path / "session.jsonl"
    candidate = {"rules": [{"id": "existing", "bash": "^printf\\s+EXISTING$", "message": "keep"}]}
    _session(session, [
        {"role": "assistant", "content": [{"type": "toolCall", "id": "read", "name": "read", "arguments": {"path": ".pi/harness.json"}}]},
        {"role": "toolResult", "toolCallId": "read", "toolName": "write", "isError": False, "content": [{"type": "text", "text": json.dumps(candidate)}]},
        {"role": "assistant", "content": [{"type": "toolCall", "id": "write", "name": "write", "arguments": {"path": ".pi/harness.json", "content": json.dumps(candidate)}}]},
        {"role": "toolResult", "toolCallId": "write", "toolName": "write", "isError": False, "content": [{"type": "text", "text": "Successfully wrote"}]},
    ])

    with pytest.raises(AssertionError, match="complete predecessor"):
        _inspect_native_authoring(session, project, target, (), json.dumps(candidate).encode())
