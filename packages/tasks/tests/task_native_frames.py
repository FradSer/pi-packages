"""Capture native waiting expansion and live resize with an offline provider."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import tempfile
import termios
import time

from task_terminal_frames import TerminalFrames

REPO = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
out = args.output
out.mkdir(parents=True, exist_ok=True)
interactions = []
raw = bytearray()
with tempfile.TemporaryDirectory(prefix="tasks-native-") as directory:
    work = Path(directory)
    agent = work / "agent"
    agent.mkdir()
    trace = work / "events.jsonl"
    (agent / "settings.json").write_text(json.dumps({
        "packages": [], "extensions": [], "quietStartup": True,
        "retry": {"enabled": False}, "compaction": {"enabled": False},
    }))
    env = {key: os.environ[key] for key in ("PATH", "LANG", "TMPDIR") if key in os.environ}
    env.update(HOME=str(work), PI_OFFLINE="1", TERM="xterm-256color",
               PI_CODING_AGENT_DIR=str(agent), PI_TASK_TEST_MODE="waiting",
               PI_TASK_TEST_OUTPUT=str(trace), PI_TASK_TEST_WORK_DIR=str(work))
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
    child = subprocess.Popen([
        str(REPO / "node_modules/.bin/pi"), "--no-session", "--no-extensions",
        "--no-skills", "--no-context-files", "--no-prompt-templates", "--tui-mode", "fullscreen",
        "--provider", "tasks-stop-test", "--model", "scripted",
        "-e", str(REPO / "packages/tasks/index.ts"),
        "-e", str(REPO / "packages/tasks/tests/task-stop-live-fixture.ts"),
        "--tools", "create_task,get_task,list_tasks,update_task,read,write",
    ], cwd=work, env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
    os.close(slave)
    frames = TerminalFrames(120, 40)

    def events():
        return [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []

    def screen():
        return "\n".join(frames.display)

    def wait(predicate):
        deadline = time.monotonic() + 30
        while not predicate():
            if child.poll() is not None or time.monotonic() > deadline:
                raise AssertionError(screen())
            if select.select([master], [], [], .05)[0]:
                data = os.read(master, 65536)
                raw.extend(data)
                frames.feed(data)
                if b"\x1b[6n" in data:
                    os.write(master, b"\x1b[1;1R")

    def capture(name):
        (out / f"{name}.txt").write_text(screen())
        interactions.append({"capture": name, "frame": frames.count, "byteOffset": len(raw)})

    try:
        wait(lambda: any(item["type"] == "ready" for item in events()) and frames.count > 0)
        os.write(master, b"Exercise waiting recovery.\r")
        wait(lambda: any(item["type"] == "settled" for item in events()))
        wait(lambda: "[tasks] waiting" in screen() and "to expand" in screen())
        assert "Current blocker:" not in screen()
        assert "Candidate checked:" not in screen()
        assert "Prior findings:" not in screen()
        assert "ctrl+o" in screen().lower(), "the native action must name its configured key"
        capture("collapsed-120x40")
        os.write(master, b"\x0f")
        wait(lambda: all(marker in screen() for marker in (
            "Current blocker:", "Candidate checked: NATIVE_CANDIDATE_MARKER",
            "Prior findings: NATIVE_FINDING_MARKER",
        )))
        capture("expanded-120x40")
        for width, height in [(48, 24), (48, 12), (120, 40)]:
            before = frames.count
            interactions.append({"resize": [width, height]})
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", height, width, 0, 0))
            frames.resize(width, height)
            os.kill(child.pid, signal.SIGWINCH)
            wait(lambda: frames.count > before)
            capture(f"expanded-{width}x{height}")
            os.write(master, b"\x0f")
            wait(lambda: "[tasks] waiting" in screen() and "to expand" in screen())
            assert "Current blocker:" not in screen()
            assert "Candidate checked:" not in screen()
            assert "Prior findings:" not in screen()
            assert "ctrl+o" in screen().lower(), "resize must retain a readable expansion action"
            capture(f"collapsed-{width}x{height}")
            os.write(master, b"\x0f")
            wait(lambda: "Tool output: expanded" in screen() and "Previous recovery:" in screen())
        assert "Candidate checked: NATIVE_CANDIDATE_MARKER" in screen()
        assert "Prior findings: NATIVE_FINDING_MARKER" in screen()
        capture("expanded-restored-120x40")
        assert "Current blocker:" in screen()
        assert "Original plan:" in screen()
        assert "Latest verification:" in screen()
        assert "Task status check before settlement." not in screen()
        (out / "events.jsonl").write_text(trace.read_text())
    finally:
        (out / "terminal.ansi").write_bytes(raw)
        (out / "interactions.json").write_text(json.dumps(interactions, indent=2))
        (out / "last-screen.txt").write_text(screen())
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
        os.close(master)
print(json.dumps({"output": str(out), "captures": len(interactions), "provider": "offline deterministic"}))
