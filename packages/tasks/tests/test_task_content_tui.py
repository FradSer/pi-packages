"""Verify task content expansion in the native Pi fullscreen terminal.

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


@pytest.mark.parametrize("mode", ["content", "ignore"])
def test_native_tui_expands_task_content_without_holder_rows(tmp_path: Path, mode: str) -> None:
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
        "TERM": "xterm-256color",
        "PI_CODING_AGENT_DIR": str(agent_dir),
        "PI_TASK_TEST_MODE": mode,
        "PI_TASK_TEST_OUTPUT": str(record),
        "PI_TASK_TEST_WORK_DIR": str(tmp_path),
    })
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 100, 0, 0))
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
        wait_for(lambda: "TASK_STOP_TEST_DONE" in screen_text(), "final response")
        settled = next(item for item in events() if item.get("type") == "settled")
        assert settled["failures"] == []
        if mode == "ignore":
            assert settled["requests"] == 5
            assert settled["reminders"][-1]["details"]["status"] == "waiting"
            wait_for(lambda: "[tasks] waiting" in screen_text() and "no task progress" in screen_text(), "no-progress waiting row")
            assert "continuation limit reached" not in screen_text()
            before_expand = len(output)
            os.write(master, b"\x0f")
            wait_for(lambda: "depends · first-task" in
                     ANSI.sub("", output[before_expand:].decode("utf-8", errors="replace")), "status dependencies")
            assert "Task status check before settlement." not in screen_text(), "The transcript must keep full task instructions hidden"
            assert "[Task]" not in screen_text()
            return
        assert settled["requests"] == 15
        assert "Inspect the task content" in screen_text()
        assert "[tasks] update" in screen_text()
        assert "[tasks] create" in screen_text()
        assert "[Task]" not in screen_text()
        assert "depends · content-prerequisite" in screen_text()
        assert "[update_task]" not in screen_text()
        assert "in_progress" not in screen_text()
        assert "Check the input handling and report failures." not in screen_text(), "Task bodies stay collapsed initially"
        before_expand = len(output)
        os.write(master, b"\x0f")  # Pi's native Ctrl+O tool expansion.
        wait_for(lambda: all(text in ANSI.sub("", output[before_expand:].decode("utf-8", errors="replace"))
                 for text in ("Check the input handling and report failures.", "Confirm the input checks pass.",
                              "depends · content-prerequisite")), "complete expanded task sections")
        expanded = ANSI.sub("", output[before_expand:].decode("utf-8", errors="replace"))
        assert "Description:" in expanded
        assert "Verify:" in expanded
        assert "Confirm the input checks pass." in expanded
        assert "depends · content-prerequisite" in expanded
        assert expanded.index("Description:") < expanded.index("Verify:") < expanded.index("depends · content-prerequisite")
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
