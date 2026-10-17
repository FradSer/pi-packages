from __future__ import annotations

import fcntl
import json
import os
import pty
import select
import signal
import struct
import subprocess
import termios
import time
from pathlib import Path

from test_btw_package import PACKAGE, REPO


def test_real_pi_tui_followups_cancel_scroll_resize_and_close(tmp_path: Path) -> None:
    record = tmp_path / "events.jsonl"
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 100, 0, 0))
    process = subprocess.Popen(
        ["pi", "--offline", "--no-session", "--no-extensions", "--no-skills",
         "--no-context-files", "--no-approve", "--extension", str(PACKAGE / "index.ts"),
         "--extension", str(PACKAGE / "tests/tui-fixture.ts"), "--tui-mode", "fullscreen"],
        cwd=REPO, stdin=slave, stdout=slave, stderr=slave,
        env={**os.environ, "TERM": "xterm-256color", "BTW_TUI_RECORD": str(record)},
        start_new_session=True,
    )
    os.close(slave)
    output = bytearray()

    def events() -> list[dict]:
        if not record.exists():
            return []
        return [json.loads(line) for line in record.read_text().splitlines()]

    def wait_for(predicate, description: str) -> list[dict]:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            current = events()
            if predicate(current):
                return current
            if process.poll() is not None:
                break
            readable, _, _ = select.select([master], [], [], 0.05)
            if readable:
                chunk = os.read(master, 65536)
                output.extend(chunk)
                # Answer terminal capability queries emitted during startup.
                if b"\x1b[6n" in chunk:
                    os.write(master, b"\x1b[1;1R")
        raise AssertionError(f"TUI did not reach {description}: {output[-4000:]!r}")

    def rendered(text: str):
        return lambda current: any(event.get("type") == "render" and text in "\n".join(event["lines"]) for event in current)

    try:
        wait_for(lambda current: any(event.get("type") == "ready" for event in current), "session startup")
        os.write(master, b"/btw-tui-test\r")
        wait_for(rendered("answer-initial"), "initial answer")
        os.write(master, b"cancel\r")
        wait_for(lambda current: any(event.get("question") == "cancel" for event in current), "loading follow-up")
        os.write(master, b"\x1b")
        wait_for(lambda current: any(event.get("type") == "abort" for event in current), "follow-up abort")
        os.write(master, b"replacement\r")
        current = wait_for(rendered("answer-replacement"), "replacement answer")
        replacement = next(event for event in current if event.get("question") == "replacement")
        assert replacement["history"] == [{"question": "initial", "answer": "answer-initial"}]
        os.write(master, b"long\r")
        wait_for(rendered("line-59"), "long answer")
        before_scroll = len(events())
        os.write(master, b"\x1b[<64;20;20M" * 80)
        wait_for(lambda current: any(event.get("type") == "render" and "line-59" not in "\n".join(event["lines"]) for event in current[before_scroll:]), "native wheel scroll")
        before_scroll = len(events())
        os.write(master, b"\x1b[5~" * 30)
        wait_for(lambda current: rendered("answer-initial")(current[before_scroll:]), "page scroll top")
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 60, 0, 0))
        os.kill(process.pid, signal.SIGWINCH)
        wait_for(lambda current: any(event.get("width") == 60 for event in current), "resize")
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 8, 20, 0, 0))
        os.kill(process.pid, signal.SIGWINCH)
        wait_for(lambda current: any(event.get("width") == 20 for event in current), "minimum resize")
        os.write(master, b"\x1b")
        current = wait_for(lambda current: any(event.get("type") == "closed" for event in current), "overlay close")
        closed = next(event for event in current if event.get("type") == "closed")
        assert not any(entry.get("type") == "message" for entry in closed["branch"])
        assert not any("late cancelled answer" in "\n".join(event.get("lines", [])) for event in current)
        for event in current:
            if event.get("type") == "render":
                assert len(event["lines"]) <= int(event["rows"] * 0.8)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        os.close(master)
