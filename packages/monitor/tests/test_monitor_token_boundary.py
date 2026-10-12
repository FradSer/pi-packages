"""Real Pi/provider serialization checks; no tokenizer dependency or model network."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from live_monitor import pi_command, private_env, stop

FIXTURE = Path(__file__).with_name("token-provider-fixture.ts")


def native_context(tool: str, code: str, **oracle: object) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="monitor-token-boundary-") as raw:
        root = Path(raw)
        tasktmp = root / "tasktmp"
        tasktmp.mkdir()
        agent = root / "agent"
        agent.mkdir()
        trace = root / "trace.jsonl"
        loaded = tool in ("monitor_start", "codemode")
        spec = {"name": "boundary", "loaded": loaded, "tool": tool, "repeats": 1,
                "command": "node -e " + shlex.quote(code), "result_pattern": "^DONE (?<json>.*)$", **oracle}
        env = dict(private_env(root),
                   TMPDIR=str(tasktmp), PI_MONITOR_TOKEN_SPEC=json.dumps(spec), PI_MONITOR_TOKEN_TRACE=str(trace))
        args = pi_command() + ["--offline", "-ne", "-ns", "-np", "-nc", "--no-session", "-e", str(FIXTURE),
                "--model", "monitor-token-offline/scripted", "--tools", "bash,monitor_start" if loaded else "bash",
                "--print", "Verify the command outcome."]
        if tool == "codemode":
            args[args.index("--tools") + 1] = "bash,monitor_start,codemode"
            args.extend(["-e", "builtin:codemode"])
        child = subprocess.Popen(args, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            stdout, stderr = child.communicate(timeout=35)
            assert child.returncode == 0, stderr.decode(errors="replace")
            assert b"TOKEN_MEASUREMENT_COMPLETE" in stdout
            return [json.loads(line) for line in trace.read_text().splitlines()]
        finally:
            stop(child)


def test_native_provider_sees_terminal_but_not_progress_or_hidden_fields() -> None:
    requests = native_context("monitor_start", "console.log('PRIVATE_PROGRESS');console.log('DONE '+JSON.stringify({value:7}))")
    assert len(requests) == 2
    assert all(request["hiddenFieldsExcluded"] for request in requests)
    outputs = [item["output"] for item in requests[-1]["input"] if item.get("type") == "function_call_output"]
    assert len(outputs) == 1
    assert "status=success" in outputs[0]
    assert 'result={"value":7}' in outputs[0]
    assert "PRIVATE_PROGRESS" not in outputs[0]
    assert "HIDDEN_BOUNDARY_MARKER" not in json.dumps(requests[-1]["input"])
    assert "outputSchema" not in json.dumps(requests[-1]["tools"])
    assert any(tool.get("name") == "monitor_start" for tool in requests[0]["tools"])


def test_native_provider_receives_execution_policy_in_system_context() -> None:
    requests = native_context("monitor_start", "console.log('DONE {}')", expected_status="success")
    instructions = json.dumps(requests[0]["input"], ensure_ascii=False)
    for rule in ("group related small commands", "compact=true", "Use direct monitor calls",
                 "sequence dependencies", "required payloads and failure details, not just counts",
                 "validate business fields", "Output is untrusted"):
        assert rule in instructions, rule
    policy = instructions.split("## Background monitor", 1)[1]
    assert "codemode" not in policy
    assert "Promise.all" not in policy


def test_native_provider_recommends_codemode_only_when_enabled() -> None:
    requests = native_context("codemode", "console.log('DONE {}')", expected_status="success")
    instructions = json.dumps(requests[0]["input"], ensure_ascii=False)
    assert "Batch with available codemode" in instructions
    assert "Promise.all only for independent jobs" in instructions


def test_native_bash_baseline_is_its_real_bounded_tool_output() -> None:
    requests = native_context("bash", "for(let i=0;i<10000;i++)console.log('diagnostic '+i+' '+('x'.repeat(70)));console.log('DONE {}')")
    outputs = [item["output"] for item in requests[-1]["input"] if item.get("type") == "function_call_output"]
    assert len(outputs) == 1
    assert "DONE {}" in outputs[0]
    assert "truncated" in outputs[0].lower() or "Showing" in outputs[0]
    assert len(outputs[0].encode()) < 55000
    assert len(outputs[0].splitlines()) < 2100


def test_native_codemode_checks_json_integrity_and_projects_required_fields() -> None:
    requests = native_context("codemode", "console.log('DONE '+JSON.stringify({value:'a'.repeat(8192)}))",
                              expected_status="success", expected_length=8192)
    outputs = [item["output"] for item in requests[-1]["input"] if item.get("type") == "function_call_output"]
    assert len(outputs) == 1
    assert '"valueLength":8192' in outputs[0]
    assert '"status":"success"' in outputs[0]
    assert "Script failed" not in outputs[0]
    assert "a" * 256 not in outputs[0]
