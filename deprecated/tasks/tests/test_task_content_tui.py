"""Verify collapsed task rows and native expansion in the native Pi fullscreen terminal.

The deterministic provider performs task edits without credentials or network requests.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import pty
import re
import select
import signal
import struct
import subprocess
import termios
import time

import pytest

from task_helpers import PACKAGE, REPO


ANSI = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-_]")


@pytest.mark.parametrize("mode", ["content", "ignore", "refusal"])
def test_native_tui_collapses_rows_and_expands_without_holder_rows(tmp_path: Path, mode: str) -> None:
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "settings.json").write_text(json.dumps({
        "quietStartup": True, "extensions": [], "packages": [],
        "compaction": {"enabled": False}, "retry": {"enabled": False},
    }), encoding="utf-8")
    record = tmp_path / "events.jsonl"
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith("PI_TEAMMATE_")
        and key not in {"PI_TASK_HOLDER", "PI_TEAM_STATE_DIR", "PI_CODING_AGENT_SESSION_DIR"}
    }
    env.update({
        "TERM": "xterm-256color", "PI_OFFLINE": "1", "HOME": str(tmp_path),
        "PI_CODING_AGENT_DIR": str(agent_dir),
        "PI_TASK_TEST_MODE": mode,
        "PI_TASK_TEST_OUTPUT": str(record),
        "PI_TASK_TEST_WORK_DIR": str(tmp_path),
    })
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 300, 100, 0, 0))
    process = subprocess.Popen([
        str(REPO / "node_modules/.bin/pi"), "--no-session", "--no-extensions", "--no-skills",
        "--no-context-files", "--no-prompt-templates", "--tui-mode", "fullscreen",
        "--provider", "tasks-stop-test", "--model", "scripted",
        "--extension", str(PACKAGE / "index.ts"),
        "--extension", str(PACKAGE / "tests/task-stop-live-fixture.ts"),
        "--tools", "create_task,get_task,list_tasks,update_task,read,write",
    ], cwd=tmp_path, env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
    os.close(slave)
    output = bytearray()

    def events() -> list[dict[str, object]]:
        if not record.exists():
            return []
        return [json.loads(line) for line in record.read_text().splitlines()]

    def screen_text() -> str:
        return ANSI.sub("", output.decode("utf-8", errors="replace"))

    def wait_for(predicate, label: str) -> None:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if predicate():
                return
            if process.poll() is not None:
                break
            readable, _, _ = select.select([master], [], [], 0.05)
            if readable:
                chunk = os.read(master, 65536)
                output.extend(chunk)
                if b"\x1b[6n" in chunk:
                    os.write(master, b"\x1b[1;1R")
        raise AssertionError(f"Pi did not reach {label}: {screen_text()[-5000:]}")

    try:
        wait_for(lambda: any(item.get("type") == "ready" for item in events()), "startup")
        os.write(master, b"Exercise the task content flow.\r")
        wait_for(lambda: any(item.get("type") == "settled" for item in events()), "settlement")
        wait_for(lambda: ("The tasks are planned. I am stopping now." if mode == "ignore" else "TASK_STOP_TEST_DONE") in screen_text(), "final response")
        settled = next(item for item in events() if item.get("type") == "settled")
        assert len(settled["failures"]) == (1 if mode == "refusal" else 0)
        if mode == "ignore":
            # Confirmed passive contract: open records never add automatic transcript rows.
            assert settled["requests"] == 4
            assert settled["reminders"] == []
            assert "[tasks] waiting" not in screen_text()
            assert "[tasks] continue" not in screen_text()
            assert "[tasks] create" in screen_text()
            assert "[tasks] update" in screen_text()
            return
        if mode == "refusal":
            assert settled["requests"] == 2
            assert settled["failures"][0]["tool"] == "get_task"
            # A refusal is collapsed like every other row and expands on the same native key.
            wait_for(lambda: "to expand" in screen_text(), "native expansion hint")
            wait_for(lambda: "[tasks] get not applied" in screen_text(), "collapsed refusal row")
            refusal_line = next(line for line in screen_text().splitlines() if "[tasks] get not applied" in line)
            assert "to expand" in refusal_line, "the refusal hint shares its headline line"
            assert "The task does not exist." not in screen_text()
            before = len(output)
            os.write(master, b"\x0f")
            wait_for(lambda: "The task does not exist." in ANSI.sub("", output[before:].decode("utf-8", errors="replace")), "expanded refusal body")
            assert "[Task]" not in screen_text()
            assert "holder ·" not in screen_text()
            assert "@main" not in screen_text()
            return
        assert settled["requests"] == 15
        # Every task row is collapsed by default: the headline stays whole and the hint follows it.
        # The renamed subject is long enough that this row must wrap at 100 columns.
        wait_for(lambda: "to expand" in screen_text(), "native expansion hint")
        collapsed = " ".join(screen_text().split())
        assert "Inspect the task content and confirm the collapsed row wraps" in collapsed
        assert "(completed)" in collapsed
        assert "to expand" in collapsed
        assert "..." not in collapsed and "\u2026" not in collapsed, "a collapsed headline is never elided"
        assert "[tasks] update" in screen_text()
        assert "[tasks] create" in screen_text()
        assert "[Task]" not in screen_text()
        assert "[update_task]" not in screen_text()
        assert "in_progress" not in screen_text()
        for hidden in ("Check the input handling and report failures.", "Confirm the input checks pass.", "Description:", "Depends on #1"):
            assert hidden not in screen_text(), hidden
        # Ctrl+O expands the most recent row and reveals its complete body.
        os.write(master, b"\x0f")
        wait_for(lambda: all(text in screen_text() for text in (
            "Check the input handling and report failures.", "Confirm the input checks pass.",
            "Description:", "Verify:", "Depends on #1")), "expanded task body")
        assert "holder ·" not in screen_text()
        assert "HELD BY" not in screen_text()
        assert "@main" not in screen_text()
        assert "resources ·" not in screen_text()
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        os.close(master)
