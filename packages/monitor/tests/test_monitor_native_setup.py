"""The native runner must use the selected workspace Pi without user state."""
from pathlib import Path

from live_monitor import REPO, setup


def test_native_runner_uses_workspace_pi_and_private_environment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-propagate")
    args, env, trace = setup(tmp_path, "standalone")
    assert args[1] == str(REPO / "node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js")
    assert env["HOME"] == str(tmp_path)
    assert env["PI_CODING_AGENT_DIR"] == str(tmp_path / "agent")
    assert "OPENAI_API_KEY" not in env
    assert "--no-builtin-tools" in args
    assert "--no-approve" in args
    assert trace == tmp_path / "trace.jsonl"


def test_native_transport_success_retains_raw_output(tmp_path: Path, monkeypatch) -> None:
    from live_transport_matrix import cases, run_case

    monkeypatch.setenv("MONITOR_ACCEPTANCE_OUTPUT", str(tmp_path))
    result = run_case(cases()[0])
    assert result["passed"] is True
    evidence, = tmp_path.glob("monitor-transport-*")
    assert b'"type":"message_end"' in (evidence / "stdout.bin").read_bytes()
    assert (evidence / "trace.jsonl").is_file()
    assert (evidence / "stderr.bin").read_bytes() == b""
