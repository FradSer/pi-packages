"""Isolated native Pi print verification for the five-tool model interface."""
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
PROSE_LABEL = "Task SQL measured optimization"
PROSE_LABEL_ENV = {"PI_INTENT_LABEL": PROSE_LABEL}


def assert_confirmed_stop(report: dict[str, object]) -> None:
    stops = [control for control in report["controls"] if control["tool"] == "agent_stop"]
    assert len(stops) == 1, "Every run must record its exact stop outcome."
    stop = stops[0]
    assert not stop["isError"] and stop["details"]["ok"] and stop["details"]["disposition"] == "stopped", "Stop was not confirmed."
    assert stop["details"]["session"] == report["receipts"][0]["session"], "Stop must address the original exact session."
    assert stop["details"]["state"] == "stopped", "The stop receipt must report observed closure."


# Storage selection and retry are protocol assertions, already checked in print.
# TUI retains continuation, steering, pending cancellation and native error rows.
@pytest.mark.parametrize("interface,case,drop_first_stream", [
    ("print", "configured", False), ("print", "configured", True),
    ("print", "stop-pending", False), ("print", "saved-identity", False),
    ("print", "steer", False), ("print", "rejected-stop", False),
    ("print", "prose-label", False), ("tui", "prose-label", False),
    ("tui", "configured", False), ("tui", "stop-pending", False),
    ("tui", "steer", False), ("tui", "rejected-stop", False),
])
def test_native_next_input_keeps_history_and_result_ids(tmp_path: Path, interface: str, case: str, drop_first_stream: bool) -> None:
    requests: list[dict[str, object]] = []
    closed = threading.Event()

    class LocalModel(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            request_index = len(requests)
            if case == "stop-pending":
                closed.wait(timeout=30)
                return
            if request_index == 1:
                time.sleep(0.5)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if drop_first_stream and request_index == 1:
                self.wfile.write(("data: " + json.dumps({"error": {"message":
                    "stream error: stream disconnected before completion: stream closed before response.completed"}}) + "\n\n").encode())
                self.wfile.flush()
                return
            answer = ("INTERMEDIATE" if request_index == 1 else "STEERED_FINAL") if case == "steer" else (
                "FIRST RESULT" if request_index == (2 if drop_first_stream else 1) else "SECOND RESULT")
            for delta, finish in (({"role": "assistant", "content": answer}, None), ({}, "stop")):
                chunk = {"id": "intent-answer", "object": "chat.completion.chunk", "created": 1, "model": "fixture",
                         "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    server = LoopbackServer(LocalModel)
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    credential = secrets.token_hex(16)
    definition = agent_dir / "agents" / "native-saved" / "agent.md"
    if case == "saved-identity":
        definition.parent.mkdir(parents=True)
        definition.write_text("---\nname: native-saved\ndescription: Native saved identity fixture\ntools: []\n---\nSAVED_IDENTITY_INSTRUCTIONS\n")
    (agent_dir / "settings.json").write_text(json.dumps({"quietStartup": True,
        "packages": [str(REPO / "packages" / "subagents")],
        "extensions": ["-builtin:mcp", "-builtin:llama.cpp", "-builtin:codemode", "-builtin:tool-search"],
        "retry": {"enabled": True, "maxRetries": 1, "baseDelayMs": 0}}))
    (agent_dir / "models.json").write_text(json.dumps({"providers": {
        "intent-loopback": {"baseUrl": f"http://127.0.0.1:{server.server_port}/v1", "api": "openai-completions",
                            "apiKey": credential, "models": [{"id": "fixture", "reasoning": False, "input": ["text"],
                            "contextWindow": 200000, "maxTokens": 4096,
                            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}
    }}))
    evidence = tmp_path / "intent-evidence.json"
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(agent_dir),
           "PI_OFFLINE": "1", "PI_INTENT_AUTH": credential, "PI_INTENT_EVIDENCE": str(evidence),
           "PI_INTENT_CONFIGURED": "1", "PI_INTENT_CASE": case,
           **({**PROSE_LABEL_ENV} if case == "prose-label" else {})}
    cli = REPO / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
    screen = ""
    try:
        command = ["node", str(cli), "--no-session", "--no-skills",
                   "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-approve",
                   "--no-builtin-tools", "--extension", str(Path(__file__).with_name("live-intent-fixture.ts")),
                   "--provider", "intent-parent", "--model", "scripted", "--thinking", "off",
                   "Run the authorized native intent fixture"]
        if interface == "print":
            result = subprocess.run([*command, "--print"], cwd=tmp_path, env=env,
                                    input="", capture_output=True, text=True, timeout=40)
            assert result.returncode == 0, result.stderr + result.stdout
            assert "NATIVE_INTENT_OK" in result.stdout
        else:
            with NativeTui(command, cwd=tmp_path, env=env, rows=28, columns=70, timeout=40) as tui:
                tui.wait_for(lambda: "NATIVE_INTENT_OK" in tui.screen())
                # Captured before the resize, so the assertion reads the composer
                # at the width the rows were first painted at.
                screen = tui.screen()
                tui.send(b'\x0f')
                tui.resize(45)
                tui.send(b'/quit\r')
                tui.wait_for(lambda: tui.process.poll() is not None)
                assert tui.process.returncode == 0, tui.screen()[-5000:]
        report = json.loads(evidence.read_text())
        family = {"agent_start", "agent_input", "agent_stop", "agent_list"}
        assert set(report["activeTools"]) & (family | {"agent"}) == family
        assert len(report["receipts"]) == 2
        assert all(receipt["ok"] and not receipt["isError"] for receipt in report["receipts"]), report
        stopped = [control for control in report["controls"] if control["tool"] == "agent_stop"]
        assert len(stopped) == 1, "Every applicable run must record its exact stop outcome."
        exact = report["receipts"][0]["session"]
        stop = stopped[0]
        if case == "rejected-stop":
            assert stop["isError"] and not stop["details"]["ok"] and stop["details"]["disposition"] == "rejected", report
            assert stop["details"]["session"] == exact + "-not-current"
            # The same successful-run acceptance gate must reject this terminal-marker run.
            with pytest.raises(AssertionError, match="Stop was not confirmed"):
                assert_confirmed_stop(report)
        else:
            assert_confirmed_stop(report)
            assert all(control["details"]["ok"] and not control["isError"] for control in report["controls"]), report
        assert report["receipts"][1]["disposition"] == ("steered" if case == "steer" else "queued")
        if case == "steer":
            assert [entry["text"] for entry in report["notices"]] == ["STEERED_FINAL"]
            assert report["receipts"][0]["inputId"] == report["receipts"][1]["inputId"] == report["notices"][0]["inputId"]
            assert len(requests) == 2
            assert json.dumps(requests[-1]["messages"]).count("STEER_INPUT") == 1
        elif case == "stop-pending":
            assert len(report["notices"]) == 1, report
            assert report["notices"][0]["kind"] == "input-cancelled"
            assert report["notices"][0]["inputId"] == report["receipts"][1]["inputId"]
            assert [entry["details"]["disposition"] for entry in report["controls"]] == ["stopped", "listed"]
            stopped_rows, = [row for row in report["controls"][1]["details"]["sessions"] if row["status"] == "stopped"]
            assert stopped_rows["inputId"], "the roster page keeps the stopped incarnation's input"
            assert len(requests) <= 1
            assert all("SECOND INPUT" not in json.dumps(request) for request in requests)
        else:
            assert [entry["text"] for entry in report["notices"]] == ["FIRST RESULT", "SECOND RESULT"]
            assert [entry["inputId"] for entry in report["notices"]] == [entry["inputId"] for entry in report["receipts"]]
            assert len(report["notices"]) == 2
            assert len(requests) == (3 if drop_first_stream else 2)
            assert "FIRST RESULT" in json.dumps(requests[-1]["messages"])
            if drop_first_stream:
                assert "SECOND INPUT" not in json.dumps(requests[1]["messages"]), "Next input cannot enter a retrying sequence"
        if case == "saved-identity":
            assert report["receipts"][0]["identity"] == "native-saved"
            assert report["receipts"][0]["label"] == "native-intent"
            assert all("SAVED_IDENTITY_INSTRUCTIONS" in json.dumps(request) for request in requests)
            home = definition.parent
            assert (home / "memory" / "MEMORY.md").is_file()
            assert list((home / "projects").glob("*/parents/parent-*/session/*.jsonl"))
            assert definition.read_text().endswith("SAVED_IDENTITY_INSTRUCTIONS\n")
        elif case == "prose-label":
            # One real Pi process, one real composer: the display name a row reads
            # is one identifier-shaped token, and the authored phrasing is absent.
            authored = PROSE_LABEL
            projected = "task-sql-measured-optimization"
            assert report["receipts"][0]["label"] == projected, report["receipts"][0]
            assert [notice["name"] for notice in report["notices"]] == [projected] * 2, report["notices"]
            stopped_rows = [row for row in report["controls"][0]["details"].get("sessions", [])
                            if row["status"] == "stopped"]
            assert report["controls"][0]["details"]["state"] == "stopped", report["controls"][0]
            assert report["controls"][0]["details"]["label"] == projected, report["controls"][0]
            assert all(row["label"] == projected for row in stopped_rows), stopped_rows
            if interface == "tui":
                assert f"@{projected}" in screen, screen
                assert authored not in screen, screen
        else:
            assert not (agent_dir / "agents").exists()
    finally:
        closed.set()
        server.close()
