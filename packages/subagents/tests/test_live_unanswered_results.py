"""Real Pi/RPC/loopback cases for empty review output and incomplete final text."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from native_support import LoopbackServer, NativeTui

REPO = Path(__file__).resolve().parents[3]


# Print covers every parsing/result variation. TUI covers each visible outcome
# and exhausted retry, without repeating whitespace and transport equivalents.
@pytest.mark.parametrize("interface,first_text,finish,reason,retries", [
    ("print", "", "stop", "empty", 0),
    ("print", "  \n\t", "stop", "empty", 0),
    ("print", "Partial review", "length", "length", 0),
    ("print", "", "length", "length", 0),
    ("print", "", "error", "error", 0),
    ("print", "", "stream-close", "error", 0),
    ("print", "", "stream-close", "error", 1),
    ("tui", "", "stop", "empty", 0),
    ("tui", "Partial review", "length", "length", 0),
    ("tui", "", "error", "error", 0),
    ("tui", "", "stream-close", "error", 1),
])
def test_native_blank_or_truncated_review_is_not_a_successful_result(
    tmp_path: Path, first_text: str, finish: str, reason: str, retries: int, interface: str,
) -> None:
    requests: list[dict[str, object]] = []

    class LocalModel(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            first = len(requests) <= 1 + retries
            text = first_text if first else "Complete final review. Static only."
            final_reason = finish if first else "stop"
            if first and finish == "error":
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": {"message": "LOCAL REVIEW PROVIDER ERROR",
                    "type": "invalid_request_error"}}).encode())
                self.wfile.flush()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if first and finish == "stream-close":
                self.wfile.write(("data: " + json.dumps({"error": {"message":
                    "stream error: stream disconnected before completion: stream closed before response.completed"}}) + "\n\n").encode())
                self.wfile.flush()
                return
            for delta, stop in (({"role": "assistant", "content": text}, None), ({}, final_reason)):
                chunk = {"id": "blank-review", "object": "chat.completion.chunk", "created": 1, "model": "reviewer",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": stop}]}
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    server = LoopbackServer(LocalModel)
    agent = tmp_path / "agent"
    agent.mkdir()
    credential = secrets.token_hex(16)
    (agent / "settings.json").write_text(json.dumps({"quietStartup": True,
        "retry": {"enabled": retries > 0, "maxRetries": retries, "baseDelayMs": 0}, "compaction": {"enabled": False}}))
    (agent / "models.json").write_text(json.dumps({"providers": {
        "unanswered-loopback": {"api": "openai-completions", "apiKey": credential,
            "baseUrl": f"http://127.0.0.1:{server.server_port}/v1",
            "models": [{"id": "reviewer", "reasoning": False, "input": ["text"],
                "contextWindow": 200000, "maxTokens": 4096,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}
    }}))
    evidence = tmp_path / "outcomes.json"
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(agent),
        "PI_OFFLINE": "1", "PI_UNANSWERED_AUTH": credential, "PI_UNANSWERED_EVIDENCE": str(evidence), "TERM": "xterm-256color"}
    cli = REPO / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
    try:
        command = ["node", str(cli), "--no-session", "--no-extensions",
            "--no-skills", "--no-prompt-templates", "--no-context-files", "--no-themes", "--no-approve",
            "--no-builtin-tools", "--extension", str(REPO / "tests" / "live-unanswered-result-fixture.ts"),
            "--provider", "unanswered-parent", "--model", "scripted", "--thinking", "off",
            "Reproduce blank review and request one later answer"]
        if interface == "print":
            # Include the 30-second cold-start window and both scripted inputs.
            result = subprocess.run([*command, "--print"], cwd=tmp_path, env=env,
                input="", text=True, capture_output=True, timeout=65)
            assert result.returncode == 0, result.stdout + result.stderr
            assert "UNANSWERED_REPRO_DONE" in result.stdout, result.stdout + result.stderr
        else:
            # A tall terminal keeps the whole native transcript on screen, so the
            # expanded unanswered row stays visible next to the rows below it.
            tui = NativeTui(command, cwd=tmp_path, env=env, rows=60, columns=100, timeout=60)
            try:
                tui.wait_for(lambda: "UNANSWERED_REPRO_DONE" in tui.screen())
                # The collapsed row names the child and the verdict only; the reason
                # is expansion detail, so the reader opens the row to read it.
                assert "[agent] unanswered · @reviewer" in tui.screen(), tui.screen()
                tui.send(b"\x0f")
                tui.wait_for(lambda: "No usable final answer" in tui.screen())
                tui.send(b"/quit\r")
                tui.wait_for(lambda: tui.process.poll() is not None)
                assert tui.process.returncode == 0
            finally:
                tui.close()
        report = json.loads(evidence.read_text())
        first, second = report["notices"]
        assert first["kind"] == "unanswered" and first["reason"] == reason, report
        assert first["text"] == first_text and first["stopReason"] == ("error" if finish == "stream-close" else finish), first
        if finish == "stream-close":
            assert "stream closed before response.completed" in first["errorMessage"], first
            assert "explicit final answer" not in json.dumps(requests[0]["messages"])
        if finish == "error":
            assert "LOCAL REVIEW PROVIDER ERROR" in first["errorMessage"], first
        assert second["kind"] == "result" and second["text"] == "Complete final review. Static only."
        assert first["turn"] == 1 and second["turn"] == 2
        assert report["sameHandle"] is True and report["closed"] is True and report["living"] == 0
        assert len(requests) == 2 + retries, "The native retry budget and one explicit send are the only requests"
        if retries:
            assert "explicit final answer" not in json.dumps(requests[1]["messages"]), "The retry cannot dispatch the later input"
        assert not (agent / "agents").exists()
        assert not (agent / "subagent-sessions").exists()
    finally:
        server.close()
