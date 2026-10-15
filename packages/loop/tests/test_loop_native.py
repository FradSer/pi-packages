"""Native /loop acceptance: a real pi TUI, a real command, a real user turn."""
from __future__ import annotations

import fcntl
import http.server
import json
import os
import pathlib
import pty
import select
import shutil
import struct
import subprocess
import tempfile
import termios
import threading
import time

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
FIXTURE = pathlib.Path(__file__).with_name("loop-live-fixture.ts")
PARAMETERIZED = "/loop --every 1s --times 2 LOOP_PROBE {{index}}/{{total}}"
UNTIL = '/loop --every 1s --until "the build is green" REPORT_STATUS'


def read_trace(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def choice(key: str, confidence: float = 0.9) -> dict:
    return {"type": "choice", "choice": key, "probabilities": {key: confidence}, "confidence": confidence}


def start_decision_server(respond) -> tuple[http.server.HTTPServer, list[list[str]]]:
    """A real loopback endpoint. Nothing inside the transport is stubbed."""
    seen: list[list[str]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            ids = sorted(body.get("questions", {}).keys())
            seen.append(ids)
            payload = json.dumps(respond(ids)).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


def envelope(answers: dict) -> dict:
    return {"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 9, "output_tokens": 3}}


def run_native(
    command: str,
    expected: list[str],
    extra_env: dict[str, str] | None = None,
    quiet: float = 2.5,
    timeout: float = 60,
) -> tuple[list[dict], list[dict], bytes]:
    """Drive the real CLI over a pty and return (start rows, all rows, terminal bytes)."""
    with tempfile.TemporaryDirectory(prefix="loop-native-") as raw:
        root = pathlib.Path(raw)
        agent = root / "agent"
        agent.mkdir()
        trace = root / "trace.jsonl"
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
        env = dict(os.environ, HOME=str(root), PI_CODING_AGENT_DIR=str(agent),
                   TERM="xterm-256color", PI_OFFLINE="1", PI_LOOP_TRACE=str(trace))
        env.pop("TYPESAFE_API_KEY", None)
        if extra_env:
            env.update(extra_env)
        child = subprocess.Popen(
            ["pi", "-ne", "-ns", "-np", "-nc", "--no-session",
             "-e", str(FIXTURE), "--model", "loop-offline/scripted"],
            cwd=root, env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
        )
        os.close(slave)
        output = bytearray()

        def await_trace(predicate, seconds: float):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.05)[0]:
                    try:
                        output.extend(os.read(master, 65536))
                    except OSError:
                        pass
                found = predicate(read_trace(trace))
                if found is not None:
                    return found
            return None

        try:
            assert await_trace(lambda rows: rows if any(r.get("kind") == "ready" for r in rows) else None,
                               30) is not None, (
                "the fixture extension never started: " + output.decode(errors="replace")
            )
            os.write(master, (command + "\r").encode())

            def reached(rows: list[dict]):
                hits = [r for r in rows if r.get("kind") == "start" and r.get("prompt") in expected]
                return hits if len(hits) >= len(expected) else None

            starts = await_trace(reached, timeout)
            if starts is None:
                started = [r for r in read_trace(trace) if r.get("kind") == "start"]
                if started and all(r.get("prompt") is None for r in started):
                    pytest.skip("the installed pi does not report the starting prompt for a run")
                assert False, "injections did not arrive: " + json.dumps(started)
            await_trace(lambda rows: None, quiet)
            rows = read_trace(trace)
            return rows, [r for r in rows if r.get("kind") == "start"], bytes(output)
        finally:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
            os.close(master)


@pytest.mark.skipif(shutil.which("pi") is None, reason="the pi CLI is not installed")
def assert_user_turns(starts: list[dict], expected: list[str]) -> None:
    """A run started by a user prompt carries that prompt; a custom message does not."""
    assert [row["prompt"] for row in starts] == expected, starts
    reported = [row["messageType"] for row in starts if row.get("messageType") is not None]
    assert all(value == "user" for value in reported), starts


@pytest.mark.skipif(shutil.which("pi") is None, reason="the pi CLI is not installed")
def test_scheduled_injection_arrives_as_a_native_user_turn() -> None:
    rows, starts, _output = run_native(PARAMETERIZED, ["LOOP_PROBE 1/2", "LOOP_PROBE 2/2"])
    assert_user_turns(starts, ["LOOP_PROBE 1/2", "LOOP_PROBE 2/2"])
    assert not [r for r in rows if isinstance(r.get("prompt"), str) and r["prompt"].startswith("/loop ")], \
        "the command was sent to the model instead of being dispatched"


@pytest.mark.skipif(shutil.which("pi") is None, reason="the pi CLI is not installed")
def test_a_met_stop_condition_ends_the_loop_after_one_turn() -> None:
    """Above the threshold the loop stops, and it stops after the first turn."""
    server, seen = start_decision_server(lambda ids: envelope({"met": {"type": "noul", "noul": 0.95}}))
    try:
        base = "http://127.0.0.1:%d" % server.server_address[1]
        rows, starts, _output = run_native(
            UNTIL, ["REPORT_STATUS"],
            {"TYPESAFE_API_KEY": "loop-fixture-key", "TYPESAFE_BASE_URL": base},
        )
    finally:
        server.shutdown()
    assert_user_turns(starts, ["REPORT_STATUS"])
    assert [ids for ids in seen] == [["met"]], "one judgment, and no repeat after the stop: " + json.dumps(seen)


@pytest.mark.skipif(shutil.which("pi") is None, reason="the pi CLI is not installed")
def test_a_below_threshold_stop_condition_keeps_the_loop_running() -> None:
    """The differential: the same request with 0.3 keeps injecting, so the threshold is what stops it."""
    server, seen = start_decision_server(lambda ids: envelope({"met": {"type": "noul", "noul": 0.3}}))
    try:
        base = "http://127.0.0.1:%d" % server.server_address[1]
        _rows, starts, _output = run_native(
            UNTIL, ["REPORT_STATUS", "REPORT_STATUS"],
            {"TYPESAFE_API_KEY": "loop-fixture-key", "TYPESAFE_BASE_URL": base},
            quiet=1.0,
            timeout=30,
        )
    finally:
        server.shutdown()
    assert len([row for row in starts if row.get("prompt") == "REPORT_STATUS"]) >= 2, starts
    assert len(seen) >= 2, "a below-threshold judgment must not end the loop: " + json.dumps(seen)
    assert all(ids == ["met"] for ids in seen), seen

