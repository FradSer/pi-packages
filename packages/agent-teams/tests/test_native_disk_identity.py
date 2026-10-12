"""Native Pi 1.1.0 coordinator checks with fixture-only loopback config."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


@pytest.fixture
def native_team_environment(tmp_path: Path) -> Iterator[tuple[dict[str, str], list[dict[str, object]]]]:
    core = REPO / "node_modules" / "@earendil-works" / "pi-coding-agent" / "package.json"
    assert json.loads(core.read_text())["version"] == "1.1.0"
    requests: list[dict[str, object]] = []
    started = threading.Event()
    release = threading.Event()
    if os.environ.get("PI_TEST_MODE") != "interrupt":
        release.set()

    class ModelHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path != "/started" or not started.wait(timeout=20):
                self.send_error(408, "No actual model request arrived")
                return
            self.send_response(200)
            self.end_headers()

        def do_POST(self) -> None:
            if self.path == "/release":
                release.set()
                self.send_response(200)
                self.end_headers()
                return
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            started.set()
            if not release.wait(timeout=25):
                self.send_error(504, "Model fixture was not released")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            chunk = {"id": "team-data", "object": "chat.completion.chunk", "created": 1, "model": "evidence"}
            for delta, finish in (({"role": "assistant", "content": "LIVE_TEAM_DATA_OK"}, None), ({}, "stop")):
                event = {**chunk, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = Path(os.environ["PI_CODING_AGENT_DIR"])
    credential = secrets.token_hex(16)
    (config / "settings.json").write_text(json.dumps({"quietStartup": True, "defaultProjectTrust": "always"}))
    (config / "models.json").write_text(json.dumps({"providers": {
        "teams-local-fixture": {"api": "openai-completions", "apiKey": credential,
            "baseUrl": f"http://127.0.0.1:{server.server_port}/v1",
            "models": [{"id": "evidence", "name": "Team data fixture", "reasoning": False,
                "input": ["text"], "contextWindow": 200000, "maxTokens": 4096,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}
    }}))
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TERM", "HOME", "PI_CODING_AGENT_DIR") if key in os.environ}
    env.update({"PI_OFFLINE": "1", "PI_TEST_DIR": str(tmp_path), "PI_TEST_MODEL": "teams-local-fixture/evidence",
        "PI_TEST_MODEL_CONTROL": f"http://127.0.0.1:{server.server_port}", "PI_TEST_MODE": os.environ.get("PI_TEST_MODE", "two-inputs")})
    try:
        yield env, requests
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("unread_mail", [False, True])
def test_native_clean_idle_close_has_no_unexpected_stop(
    native_team_environment: tuple, tmp_path: Path, unread_mail: bool,
) -> None:
    env, requests = native_team_environment
    loader = (PACKAGE / "tests/native-clean-close-loader.mjs").as_uri()
    env = {**env, "NODE_OPTIONS": f"--import={loader}", "PI_TEST_UNREAD_MAIL": "1" if unread_mail else "0"}
    result = subprocess.run(["node", str(PACKAGE / "tests/native-clean-close.ts")],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["nativePid"] > 0
    assert report["status"] == "stopped"
    assert report["unexpectedReports"] == int(unread_mail)
    assert report["subject"] == ("Agent stopped unexpectedly" if unread_mail else "Agent stopped")
    assert requests == [], "The clean-close slash command must not request a model"


def test_native_team_disk_memory_and_history(native_team_environment: tuple, tmp_path: Path) -> None:
    env, requests = native_team_environment
    result = subprocess.run(["node", str(PACKAGE / "tests" / "live-workspace-memory.ts")],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1])["durableDataRetained"] is True
    assert len(requests) == 1
    messages = requests[0]["messages"]
    text = json.dumps(messages)
    assert "AGENT MEMORY" in text and "known-method.md" in text, text
    assert "Native durable data probe" not in text or "Return the requested evidence" in text
    assert str(tmp_path / "project") in text


def test_native_hosted_two_inputs_keep_process_and_history(native_team_environment: tuple, tmp_path: Path) -> None:
    env, requests = native_team_environment
    result = subprocess.run(["node", str(PACKAGE / "tests" / "live-hosted-resident.ts")],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["reports"] == 2 and report["sameProcess"] is True
    assert len(requests) == 2, "send creates exactly one model turn"
    history = json.dumps(requests[1]["messages"])
    assert "First input" in history and "Second input" in history and "LIVE_TEAM_DATA_OK" in history
    assert history.count("PINNED_HOSTED_ROLE") == 1, "standing role is delivered on first input only"


@pytest.fixture
def interrupt_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_TEST_MODE", "interrupt")


def test_native_hosted_interrupt_is_same_sequence(interrupt_mode: None, native_team_environment: tuple, tmp_path: Path) -> None:
    env, requests = native_team_environment
    result = subprocess.run(["node", str(PACKAGE / "tests" / "live-hosted-resident.ts")],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["reports"] == 1 and report["sameProcess"] is True
    assert requests, "the active sequence must have actually reached the loopback model"
    assert len(requests) <= 2, "steering may continue the same sequence, never add an independent input"
