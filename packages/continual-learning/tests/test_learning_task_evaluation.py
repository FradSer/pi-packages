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
    assert (source / "auth.json").read_text() == '{"fixture":"synthetic"}'
