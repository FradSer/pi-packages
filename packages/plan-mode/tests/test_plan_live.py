"""Real minimal Pi child and native TUI verification against a local model server."""
from __future__ import annotations

import errno
import fcntl
import json
import os
import pty
import re
import secrets
import select
import shutil
import struct
import subprocess
import termios
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


@pytest.fixture
def live_command(tmp_path: Path) -> Iterator[tuple[list[str], dict[str, str], list[dict]]]:
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("Pi CLI is required for live verification")
    requests: list[dict] = []
    (tmp_path / "input.txt").write_text("fixture-source-content")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(request)
            index = len(requests) - 1
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if index < 2:
                name = "write" if index == 0 else "read"
                args = {"path": str(tmp_path / ("unexpected-write" if index == 0 else "input.txt"))}
                if index == 0:
                    args["content"] = "must not be written"
                delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": f"probe-{index}", "type": "function",
                         "function": {"name": name, "arguments": json.dumps(args)}}]}
                reason = "tool_calls"
            else:
                text = "# Offline verified plan\nUse fixture-source-content to implement the requested change." if index == 2 else "IMPLEMENTATION_OK"
                delta = {"role": "assistant", "content": text}
                reason = "stop"
            for event in [{"id": "offline", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                          {"id": "offline", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": reason}]}]:
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "settings.json").write_text(json.dumps({"quietStartup": True, "theme": "dark"}))
    (agent_dir / "models.json").write_text(json.dumps({"providers": {"plan-live": {
        "baseUrl": f"http://127.0.0.1:{server.server_port}/v1", "api": "openai-completions",
        "apiKey": secrets.token_hex(16), "models": [{"id": "offline", "contextWindow": 200000, "maxTokens": 4096}]
    }}}))
    env = {key: os.environ[key] for key in ("PATH", "SHELL", "TMPDIR", "LANG") if key in os.environ}
    env.update({"PI_CODING_AGENT_DIR": str(agent_dir), "PI_OFFLINE": "1", "PI_TELEMETRY": "0", "TERM": "xterm-256color"})
    command = [pi, "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates",
               "--no-themes", "--no-context-files", "--no-approve", "--extension", str(Path(__file__).parents[1] / "index.ts"),
               "--provider", "plan-live", "--model", "offline", "--thinking", "off"]
    try:
        yield command, env, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def assert_planner_is_read_only(root: Path, requests: list[dict]) -> None:
    assert not (root / "unexpected-write").exists()
    plans = list((root / "agent" / "plans").glob("*.md"))
    assert len(plans) == 1
    assert "# Offline verified plan" in plans[0].read_text()
    for request in requests[:3]:
        names = {tool["function"]["name"] for tool in request["tools"]}
        assert names == {"read", "grep", "find", "ls"}, names
    assert "fixture-source-content" in json.dumps(requests[2]["messages"])


def test_live_print_awaits_one_minimal_read_only_planner(
    live_command: tuple[list[str], dict[str, str], list[dict]], tmp_path: Path,
) -> None:
    command, env, requests = live_command
    result = subprocess.run([*command, "--print", "/plan verify guards"], cwd=tmp_path, env=env,
                            input="", text=True, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Plan written to" in result.stderr, result.stdout + result.stderr
    assert len(requests) == 3
    assert_planner_is_read_only(tmp_path, requests)


@pytest.mark.parametrize("fresh", [False, True])
def test_live_native_tui_requires_implementation_choice(
    live_command: tuple[list[str], dict[str, str], list[dict]], tmp_path: Path, fresh: bool,
) -> None:
    command, env, requests = live_command
    master, slave = pty.openpty()
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 35, 100, 0, 0))
    process = subprocess.Popen(command, cwd=tmp_path, env=env, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    transcript = bytearray()

    def screen() -> str:
        return re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", bytes(transcript)).decode(errors="replace")

    def wait_for(predicate: Callable[[], bool]) -> None:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.05)[0]:
                try:
                    transcript.extend(os.read(master, 65536))
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    break
            if predicate():
                return
            if process.poll() is not None:
                break
        assert predicate(), screen()[-6000:]

    def send(text: str) -> None:
        transcript.clear()
        os.write(master, text.encode())

    try:
        wait_for(lambda: "offline" in screen())
        send("/plan verify guards\r")
        wait_for(lambda: "Implement in new session" in screen())
        assert len(requests) == 3, "parent must not run before a selection"
        assert_planner_is_read_only(tmp_path, requests)
        # Dismiss and reopen through the command, then make an explicit choice.
        send("\x1b")
        wait_for(lambda: "Plan kept." in screen())
        send("/plan review\r")
        wait_for(lambda: "Implement in new session" in screen())
        send("\x1b[B\r" if fresh else "\r")
        wait_for(lambda: "IMPLEMENTATION_OK" in screen())
        assert len(requests) == 4
        send("/quit\r")
        wait_for(lambda: process.poll() is not None)
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        os.close(master)
