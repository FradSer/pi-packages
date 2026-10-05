"""Native Pi verification for the child-only agent_message channel."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from native_support import LoopbackServer, NativeTui

REPO = Path(__file__).resolve().parents[3]


def _sse(answer: str, *, tool: str | None = None, arguments: str | None = None) -> bytes:
    if tool is not None:
        delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": "child-message-call",
            "type": "function", "function": {"name": tool, "arguments": arguments or "{}"}}]}
        finish = "tool_calls"
    else:
        delta, finish = {"role": "assistant", "content": answer}, "stop"
    chunks = [
        {"id": "parent-message-fixture", "object": "chat.completion.chunk", "created": 1, "model": "fixture",
         "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {"id": "parent-message-fixture", "object": "chat.completion.chunk", "created": 1, "model": "fixture",
         "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
    ]
    return b"".join(("data: " + json.dumps(chunk) + "\n\n").encode() for chunk in chunks) + b"data: [DONE]\n\n"


def _child_response(payload: dict[str, object], granted: bool) -> bytes:
    raw_messages = payload.get("messages", [])
    typed_messages = raw_messages if isinstance(raw_messages, list) else []
    user_indexes = [index for index, item in enumerate(typed_messages)
                    if isinstance(item, dict) and item.get("role") == "user"]
    last_user = user_indexes[-1] if user_indexes else -1
    second = "SECOND INPUT" in json.dumps(typed_messages[last_user:], ensure_ascii=False)
    # A persistent resident session retains the first turn's tool result. Only
    # a result after the current input means that this input's agent_message
    # call has completed.
    tool_result_count = sum(isinstance(item, dict) and item.get("role") == "tool"
                             for item in typed_messages[last_user + 1:])
    if tool_result_count < 2:
        if not granted:
            if tool_result_count > 0:
                return _sse("CHILD_NO_GRANT_FINAL")
            return _sse("", tool="agent_message", arguments=json.dumps({"message": "FORBIDDEN_ATTEMPT"}))
        message = "INTERMEDIATE_B" if second else "INTERMEDIATE_A"
        return _sse("", tool="agent_message", arguments=json.dumps({"message": message}))
    if not granted:
        return _sse("CHILD_NO_GRANT_FINAL")
    return _sse("CHILD_FINAL_B" if second else "CHILD_FINAL_A")


@pytest.mark.parametrize("interface,case", [("print", "granted"), ("tui", "granted"), ("print", "no-grant")])
def test_native_parent_message_is_isolated_fifo_and_explicit(tmp_path: Path, interface: str, case: str) -> None:
    granted = case == "granted"
    requests: list[dict[str, object]] = []
    request_kinds: list[str] = []
    request_trace = tmp_path / "requests.json"
    final_a_gate = threading.Event()
    child_finished = threading.Event()

    class Control(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            if self.path != "/release-final-a":
                self.send_error(404)
                return
            final_a_gate.set()
            self.send_response(204)
            self.end_headers()

        def do_GET(self) -> None:
            if self.path != "/child-finished":
                self.send_error(404)
                return
            child_finished.wait(timeout=35)
            self.send_response(204 if child_finished.is_set() else 504)
            self.end_headers()

    control = LoopbackServer(Control)

    class LocalChildModel(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            typed_messages = payload.get("messages", []) if isinstance(payload.get("messages", []), list) else []
            user_indexes = [index for index, item in enumerate(typed_messages)
                            if isinstance(item, dict) and item.get("role") == "user"]
            last_user = user_indexes[-1] if user_indexes else -1
            current = json.dumps(typed_messages[last_user:], ensure_ascii=False)
            tool_results = sum(isinstance(item, dict) and item.get("role") == "tool"
                               for item in typed_messages[last_user + 1:])
            prefix = "B" if "SECOND INPUT" in current else "A"
            threshold = 2 if granted else 1
            kind = f"tool-{prefix}" if tool_results < threshold else f"final-{prefix}"
            request_kinds.append(kind)
            request_trace.write_text(json.dumps(request_kinds))
            # Keep the first child model request active while the parent issues
            # its already-queued next input. The fixture releases this gate only
            # after Pi reports the real queued receipt.
            if granted and kind == "tool-A" and tool_results == 1 and not final_a_gate.wait(timeout=45):
                self.send_error(504)
                return
            body = _child_response(payload, granted)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            if kind == "final-B" or (not granted and kind == "final-A"):
                # Let the resident consume the complete local stream and emit
                # its Session Result before releasing the parent keepalive.
                time.sleep(0.5)
                child_finished.set()

    server = LoopbackServer(LocalChildModel)
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    credential = secrets.token_hex(16)
    (agent_dir / "settings.json").write_text(json.dumps({"quietStartup": True,
        "packages": [str(REPO / "packages" / "subagents")],
        "extensions": ["-builtin:mcp", "-builtin:llama.cpp", "-builtin:codemode", "-builtin:tool-search"],
        "retry": {"enabled": True, "maxRetries": 1, "baseDelayMs": 0}}))
    (agent_dir / "models.json").write_text(json.dumps({"providers": {
        "parent-message-child": {"baseUrl": f"http://127.0.0.1:{server.server_port}/v1",
            "api": "openai-completions", "apiKey": credential,
            "models": [{"id": "fixture", "reasoning": False, "input": ["text"],
                "contextWindow": 200000, "maxTokens": 4096,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}
    }}))
    evidence = tmp_path / "parent-message-evidence.json"
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(agent_dir),
           "PI_OFFLINE": "1", "PI_PARENT_MESSAGE_AUTH": credential,
           "PI_PARENT_MESSAGE_EVIDENCE": str(evidence), "PI_PARENT_MESSAGE_CONFIGURED": "1",
           "PI_PARENT_MESSAGE_CASE": case, "PI_PARENT_MESSAGE_REQUEST_TRACE": str(request_trace)}
    env["PI_PARENT_MESSAGE_CONTROL_URL"] = f"http://127.0.0.1:{control.server_port}"
    cli = REPO / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
    command = ["node", str(cli), "--no-session", "--no-skills", "--no-prompt-templates", "--no-themes",
               "--no-context-files", "--no-approve", "--no-builtin-tools", "--extension",
               str(Path(__file__).with_name("native-parent-message-fixture.ts")),
               "--provider", "parent-message-parent", "--model", "scripted", "--thinking", "off",
               "Run the isolated parent message fixture"]
    try:
        if interface == "print":
            result = subprocess.run([*command, "--print"], cwd=tmp_path, env=env, input="", capture_output=True,
                                    text=True, timeout=60)
            assert result.returncode == 0, result.stderr + result.stdout
            if granted:
                assert "NATIVE_PARENT_MESSAGE_OK" in result.stdout + result.stderr
        else:
            with NativeTui(command, cwd=tmp_path, env=env, rows=28, columns=70, timeout=60) as tui:
                tui.wait_for(lambda: "NATIVE_PARENT_MESSAGE_OK" in tui.screen() and "Idle" in tui.screen())
                collapsed = tui.screen()
                assert "[agent] queued · @native-parent-message" in collapsed, collapsed[-5000:]
                assert "native-parent-message · Idle" in collapsed, collapsed[-5000:]
                assert "session:subagent-" not in collapsed, collapsed[-5000:]
                tui.send(b"\x0f")
                tui.resize(45)
                tui.send(b"/quit\r")
                tui.wait_for(lambda: tui.process.poll() is not None)
                assert tui.process.returncode == 0, tui.screen()[-5000:]
                for marker in ("INTERMEDIATE_A", "INTERMEDIATE_B", "CHILD_FINAL_A", "CHILD_FINAL_B"):
                    assert marker in tui.screen(), tui.screen()[-5000:]
        assert evidence.is_file()
        report = json.loads(evidence.read_text())
        assert not report.get("failures"), report
        intermediate = [item for item in report["notices"] if item.get("kind") == "intermediate"]
        finals = [item for item in report["notices"] if item.get("kind") == "result"]
        if granted:
            assert [item["text"] for item in intermediate] == ["INTERMEDIATE_A", "INTERMEDIATE_B"], json.dumps(report, ensure_ascii=False)
            assert [item["text"] for item in finals] == ["CHILD_FINAL_A", "CHILD_FINAL_B"], report
            assert len({item["text"] for item in intermediate}) == 2
            assert all(item["session"] == report["receipts"][0]["session"] for item in intermediate + finals)
            assert len(report["receipts"]) == 2 and all(not item["isError"] for item in report["receipts"])
            assert report["receipts"][0]["tool"] == "agent_start"
            assert report["receipts"][1]["tool"] == "agent_input"
            assert report["receipts"][1]["disposition"] == "queued"
            assert report["receipts"][1]["state"] in {"starting", "working"}
            assert report["receipts"][1]["rosterSequenceEnded"] is False
            assert report["receipts"][0].get("inputId") == intermediate[0].get("inputId") == finals[0].get("inputId")
            assert report["receipts"][1].get("inputId") == intermediate[1].get("inputId") == finals[1].get("inputId")
            assert intermediate[0]["inputId"] != intermediate[1]["inputId"]
            assert [item["sequence"] for item in intermediate] == [1, 2]
            assert intermediate[0]["customType"] == intermediate[1]["customType"] == "subagents-parent-message"
            assert all(item["customType"] != intermediate[0]["customType"] for item in finals)
            assert intermediate[0]["order"] < finals[0]["order"] < intermediate[1]["order"] < finals[1]["order"]
            assert json.loads((tmp_path / "requests.json").read_text()) == [
                "tool-A", "tool-A", "final-A", "tool-B", "tool-B", "final-B"]
        else:
            assert not intermediate, report
            assert finals and finals[0]["text"] == "CHILD_NO_GRANT_FINAL", report
            assert report["receipts"] and "agent_message" not in json.dumps(report["receipts"][0].get("grant", []))
            assert any("FORBIDDEN_ATTEMPT" in json.dumps(request) for request in requests)
            assert json.loads((tmp_path / "requests.json").read_text()) == ["tool-A", "final-A"]
    finally:
        server.close()
        control.close()
