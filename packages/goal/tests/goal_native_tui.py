"""Native offline TUI probe. Run explicitly; it uses a fresh project and agent dir."""
from __future__ import annotations

import fcntl
import json
import os
import pathlib
import pty
import re
import select
import signal
import struct
import subprocess
import tempfile
import termios
import time


def terminate_fixture(child: subprocess.Popen, grace_seconds: float = 2.0) -> None:
    """Stop only the isolated process group created by this probe, then reap it."""
    if child.poll() is not None:
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=3)


def main() -> None:
    repo = pathlib.Path(__file__).resolve().parents[3]
    with tempfile.TemporaryDirectory(prefix="goal-tui-") as raw:
        root = pathlib.Path(raw)
        agent = root / "agent"
        agent.mkdir()
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
        trace = root / "old-turn.trace"
        widget_trace = root / "widget.trace"
        env = dict(os.environ, PI_CODING_AGENT_DIR=str(agent), TERM="xterm-256color",
                   PI_GOAL_OFFLINE_TRACE=str(trace), PI_GOAL_OFFLINE_WIDGET=str(widget_trace))
        child = subprocess.Popen(
            ["pi", "-ne", "-ns", "-np", "-nc", "--no-session", "-e",
             str(repo / "packages/goal/tests/goal_offline_fixture.ts"),
             "--model", "goal-offline/scripted"],
            cwd=root, env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
        )
        os.close(slave)
        output = bytearray()

        def drain(seconds: float) -> None:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.05)[0]:
                    try:
                        output.extend(os.read(master, 65536))
                    except OSError:
                        break

        def send(text: str) -> None:
            os.write(master, text.encode() + b"\r")
            drain(0.8)

        def record() -> dict:
            paths = list((root / ".pi/goals").glob("*/record.json"))
            assert len(paths) == 1, output.decode(errors="replace")[-4000:]
            return json.loads(paths[0].read_text())["goal"]

        try:
            deadline = time.monotonic() + 10
            while b"goal_offline_fixture.ts" not in output and time.monotonic() < deadline:
                drain(0.05)
            assert b"goal_offline_fixture.ts" in output, "native extension startup did not finish"
            drain(0.2)
            send("Verify offline goal behavior.")
            assert record()["status"] == "paused"
            before = record()["usage"]["tokensUsed"]
            send("/goal")
            assert record()["usage"]["tokensUsed"] == before
            assert b"Status: paused" in output
            widgets = [json.loads(line) for line in widget_trace.read_text().splitlines()]
            assert widgets and all(item["placement"] == "belowEditor" for item in widgets), widgets
            assert all(not line[:1].isspace() for item in widgets for line in item["lines"]), "goal rows must align with the native footer"
            assert any("0m" in " ".join(item["lines"]) for item in widgets), widgets
            assert b"0m" in output, "minimum minute value must be present in native TUI"
            os.write(master, b"OLD_TURN_EDIT\r")
            deadline = time.monotonic() + 5
            while not trace.exists() and time.monotonic() < deadline:
                drain(0.05)
            assert trace.exists(), "the old response must be streaming before rejection"
            os.write(master, b"/goal Rejected busy objective must not activate.\r")
            drain(2)
            rejected = record()
            assert rejected["status"] == "paused", rejected
            assert rejected["scheduler"]["used"] == 0, rejected
            assert rejected["objective"] == "Unrelated internal edit from the old turn.", rejected
            assert b"Wait for it to finish" in output, output.decode(errors="replace")[-4000:]
            ledger = list((root / ".pi/goals").glob("*/ledger.jsonl"))[0]
            assert not any(json.loads(line)["type"] == "goal_resumed" for line in ledger.read_text().splitlines()), "rejection must not resume"
            send("/goal Revised offline acceptance: E2E must pass.")
            revised = record()
            assert "Revised offline acceptance" in revised["objective"], revised
            assert revised["scheduler"]["used"] == 1, revised
            assert b"revised and activated" in output, output.decode(errors="replace")[-4000:]
            assert b"Pursuing goal" in output, "the active row reads as a sentence"
            assert b"[goal] Pursuing goal" not in output, "the pursuing row drops the goal tag"
            _seen = [ln for ln in output.decode(errors="replace").splitlines() if "goal" in ln.lower() or any(c in ln for c in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏○✓✗")]
            # A goal id is `goal_<base36>_<base36>`. The fixture filename
            # `goal_offline_fixture.ts` also starts `goal_`, so match the id
            # shape rather than the prefix.
            # The fixture filename `goal_offline_fixture.ts` is a test artifact,
            # not product output, and it has the same shape as a goal id
            # (`goal_<6+>_<4+>`). Strip it before judging the transcript.
            _probe = output.replace(b"goal_offline_fixture.ts", b"")
            _hit = re.search(rb"goal_[a-z0-9]{6,}_[a-z0-9]{4,}", _probe)
            assert _hit is None, "goal id shown near: " + repr(_probe[max(0, _hit.start() - 200):_hit.end() + 80])
            assert b"running" not in output, "the status verb is the row itself, not a field"
            send("/goal resume")
            r = record()
            assert r["scheduler"]["used"] == 1, r
            assert r["status"] == "paused", r
            send("/goal pause")
            assert record()["status"] == "paused"
            drain(0.8)
            assert b"Goal paused" in output, "the paused row reads as a sentence"
            assert b"[goal] Goal paused" not in output, "no state tags the status row"
            send("/goal clear")
            os.write(master, b"\r")
            drain(0.8)
            assert not list((root / ".pi/goals").glob("*/record.json"))
            assert list((root / ".pi/goals/archived").glob("*/record.json"))
            assert b"No goal is focused" not in output
        finally:
            try:
                terminate_fixture(child)
            finally:
                os.close(master)
        assert child.poll() is not None
        print("GOAL_NATIVE_TUI_OK")


if __name__ == "__main__":
    main()
