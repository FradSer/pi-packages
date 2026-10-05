from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate-learning.py"


def test_task_evaluation_scoring_and_validation() -> None:
    spec = importlib.util.spec_from_file_location("learning_task_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = {"id": "held-out", "prompt": "Where?", "required": ["canary-a"], "forbidden": ["production"]}
    assert module.score_case(case, "Use canary-a.") is True
    assert module.score_case(case, "Use canary-a in production.") is False
    assert module.score_case(case, "Unknown.") is False
    suite = {"version": 1, "baseline": {"memories": {}}, "candidate": {"memories": {}}, "cases": [case]}
    module.validate_suite(suite)
    suite["candidate"]["harness"] = {"rules": []}
    with pytest.raises(ValueError, match="only memories"):
        module.validate_suite(suite)
    del suite["candidate"]["harness"]
    suite["candidate"]["memories"] = {"../escape.md": "bad"}
    try:
        module.validate_suite(suite)
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe fixture Memory path was accepted")


def test_exact_answer_scoring_rejects_ambiguous_substrings() -> None:
    spec = importlib.util.spec_from_file_location("learning_task_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = {"id": "exact", "prompt": "Channel?", "required": ["canary"], "exact": "canary"}
    assert module.score_case(case, "canary") is True
    assert module.score_case(case, "unknown; canary") is False
    assert module.score_case(case, "canaryish") is False
    assert module.score_case(case, "not canary") is False


def test_effectiveness_rejects_failed_provider_arms() -> None:
    live_script = SCRIPT.parent.parent / "tests" / "live_effectiveness.py"
    spec = importlib.util.spec_from_file_location("live_effectiveness", live_script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = {
        "baseline": {"successRate": 0.0, "results": [{"id": "one", "passed": False, "error": "provider failed"}]},
        "candidate": {"successRate": 1.0, "results": [{"id": "one", "passed": True, "error": None}]},
        "regressions": [],
    }
    with pytest.raises(AssertionError, match="execute"):
        module.assert_effectiveness_report(report)


def test_read_body_evidence_requires_successful_native_read() -> None:
    spec = importlib.util.spec_from_file_location("learning_task_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = {"readBody": {"path": "orbit.md", "required": "BODY_MARKER"}}
    memory_root = Path("/tmp/project/.memory")
    assert module.read_body_matches(case, [{"path": "/tmp/project/.memory/orbit.md", "isError": False, "result": "BODY_MARKER"}], memory_root) is True
    assert module.read_body_matches(case, [{"path": ".memory/orbit.md", "isError": False, "result": "BODY_MARKER"}], memory_root) is True
    assert module.read_body_matches(case, [{"path": "orbit.md", "isError": False, "result": "BODY_MARKER"}], memory_root) is False
    assert module.read_body_matches(case, [{"path": "/tmp/project/other/orbit.md", "isError": False, "result": "BODY_MARKER"}], memory_root) is False
    assert module.read_body_matches(case, [{"path": "/tmp/project/.memory/nested/orbit.md", "isError": False, "result": "BODY_MARKER"}], memory_root) is False
    assert module.read_body_matches(case, [{"path": "/tmp/project/.memory/orbit.md", "isError": True, "result": "BODY_MARKER"}], memory_root) is False
    assert module.read_body_matches(case, [{"path": "/tmp/project/.memory/orbit.md", "isError": False, "result": "wrong body"}], memory_root) is False


def test_read_events_require_matching_native_call_ids() -> None:
    spec = importlib.util.spec_from_file_location("learning_task_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    start = {"type": "tool_execution_start", "toolName": "read", "toolCallId": "read-1", "args": {"path": ".memory/orbit.md"}}
    end = {"type": "tool_execution_end", "toolName": "read", "toolCallId": "read-1", "isError": False, "result": "BODY_MARKER"}
    assert module._read_events((json.dumps(start) + "\n" + json.dumps(end)).encode()) == [
        {"path": ".memory/orbit.md", "isError": False, "result": "BODY_MARKER"}
    ]
    no_id_end = {**end, "toolCallId": None, "args": {"path": "/tmp/project/.memory/orbit.md"}}
    mismatched_end = {**end, "toolCallId": "read-2", "args": {"path": "/tmp/project/.memory/orbit.md"}}
    assert module._read_events((json.dumps({**start, "toolCallId": None}) + "\n" + json.dumps(no_id_end)).encode()) == []
    assert module._read_events((json.dumps(start) + "\n" + json.dumps(mismatched_end)).encode()) == []


def test_provider_config_snapshot_is_private_and_detaches_symlinks(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("learning_task_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "agent"
    source.mkdir()
    auth_target = source / "auth-target.json"
    auth_target.write_text('{"fixture":"auth"}')
    (source / "auth.json").symlink_to(auth_target)
    (source / "models.json").write_text('{"fixture":"models"}')
    temporary, snapshot, fingerprint = module._snapshot_provider_config(source)
    try:
        assert snapshot.stat().st_mode & 0o777 == 0o700
        assert all((snapshot / name).stat().st_mode & 0o777 == 0o600 for name in ("auth.json", "models.json"))
        assert not (snapshot / "auth.json").is_symlink()
        (snapshot / "auth.json").write_text('{"fixture":"local-refresh"}')
        assert auth_target.read_text() == '{"fixture":"auth"}'
        assert fingerprint
    finally:
        temporary.cleanup()


def test_shipped_task_evaluation_suite_validates_without_authentication(tmp_path: Path) -> None:
    suite = SCRIPT.parent.parent / "examples" / "learning-task-evaluation.json"
    result = subprocess.run([sys.executable, str(SCRIPT), str(suite), "--validate"], cwd=tmp_path, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"valid": True, "cases": 1}


def test_task_arms_are_isolated_and_missing_prices_are_not_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = importlib.util.spec_from_file_location("learning_task_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "agent"
    source.mkdir()
    (source / "auth.json").write_text('{"fixture":"synthetic"}')
    roots: list[Path] = []
    copied_auth: list[str] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 0)
        assert command[command.index("--tools") + 1] == "read"
        assert "--no-extensions" in command and "--no-session" in command
        project = kwargs["cwd"]
        assert isinstance(project, Path)
        roots.append(project)
        agent = Path(kwargs["env"]["PI_CODING_AGENT_DIR"])
        assert agent != source
        assert (agent / "auth.json").stat().st_mode & 0o777 == 0o600
        assert json.loads((agent / "memory/settings.json").read_text()) == {"autoMemory": False}
        copied_auth.append((agent / "auth.json").read_text())
        if len(copied_auth) == 1:
            (source / "auth.json").write_text('{"fixture":"changed-after-snapshot"}')
        (agent / "auth.json").write_text("local refresh")
        answer = "canary-a" if (project / ".memory/orbit.md").exists() else "unknown"
        kwargs["stdout"].write((json.dumps({"type": "message_end", "message": {
            "role": "assistant", "content": [{"type": "text", "text": answer}], "stopReason": "stop",
            "usage": {"input": 10, "output": 2, "totalTokens": 12, "cost": {"total": 0}},
        }}) + "\n").encode())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", run)
    suite = {"version": 1, "baseline": {"memories": {}}, "candidate": {"memories": {"orbit.md": "canary-a"}},
             "cases": [{"id": "held-out", "prompt": "Channel?", "required": ["canary-a"]}]}
    report = module.evaluate_suite(suite, "fixture/model", source)
    assert report["baseline"]["successRate"] == 0 and report["candidate"]["successRate"] == 1
    assert report["candidate"]["usage"]["totalTokens"] == 12
    assert report["baseline"]["cost"] is None and report["candidate"]["cost"] is None
    assert len(set(roots)) == 2 and all(not root.exists() for root in roots)
    assert copied_auth == ['{"fixture":"synthetic"}', '{"fixture":"synthetic"}']
    assert (source / "auth.json").read_text() == '{"fixture":"changed-after-snapshot"}'
    assert report["configSnapshot"]["files"] == ["auth.json"]


@pytest.mark.parametrize("include_read", [False, True])
def test_candidate_requires_native_read_body_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, include_read: bool) -> None:
    spec = importlib.util.spec_from_file_location("learning_task_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "agent"
    source.mkdir()

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 0)
        project = kwargs["cwd"]
        assert isinstance(project, Path)
        candidate = (project / ".memory/orbit.md").exists()
        events: list[dict[str, object]] = []
        if candidate and include_read:
            events.extend([
                {"type": "tool_execution_start", "toolName": "read", "toolCallId": "read-1", "args": {"path": str(project / ".memory/orbit.md")}},
                {"type": "tool_execution_end", "toolName": "read", "toolCallId": "read-1", "isError": False, "result": "BODY_MARKER"},
            ])
        answer = "canary" if candidate else "unknown"
        events.append({"type": "message_end", "message": {
            "role": "assistant", "content": [{"type": "text", "text": answer}], "stopReason": "stop",
            "usage": {"input": 1, "output": 1, "totalTokens": 2, "cost": {"total": 0}},
        }})
        kwargs["stdout"].write(("\n".join(json.dumps(event) for event in events) + "\n").encode())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", run)
    suite = {"version": 1, "baseline": {"memories": {}}, "candidate": {"memories": {"orbit.md": "body"}},
             "cases": [{"id": "held-out", "prompt": "Channel?", "required": ["canary"], "exact": "canary",
                         "readBody": {"path": "orbit.md", "required": "BODY_MARKER"}}]}
    report = module.evaluate_suite(suite, "fixture/model", source)
    assert report["baseline"]["results"][0]["passed"] is False
    assert report["candidate"]["results"][0]["passed"] is include_read
