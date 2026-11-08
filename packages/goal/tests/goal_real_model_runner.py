"""One native Goal session driven by the configured real model."""
from __future__ import annotations
import json
import os
from pathlib import Path
import pty
import fcntl
import struct
import termios
import select
import signal
import subprocess
import time

from goal_native_frames import TerminalFrames

ROOT = Path("/work")
RESULTS = Path("/results")
AGENT = Path("/agent")
MODEL = "magpie-hy4/hunyuan-eval/hy4-dev"
REQUEST = "Set a persistent goal: write exactly GOAL_REAL_MODEL_OK into result.txt, then verify the file and request completion. Keep the objective short."
MARKER = "GOAL_REAL_MODEL_OK"


def goal_records() -> list[dict]:
    return [json.loads(path.read_text()) for path in sorted((AGENT / "goals").glob("*/*/record.json"))]


def main() -> None:
    env = dict(os.environ, HOME=str(ROOT), PI_CODING_AGENT_DIR=str(AGENT), TERM="xterm-256color",
        PI_SKIP_VERSION_CHECK="1")
    session = ROOT / "session.jsonl"
    command = ["pi", "--approve", "--no-extensions", "--no-skills",
        "--no-prompt-templates", "--no-themes", "--no-context-files",
        "-e", "/opt/study/packages/goal/index.ts",
        "-e", "/opt/study/packages/goal/tests/goal_real_model_audit.ts",
        "--model", MODEL, "--thinking", "off",
        "--session", str(session)]
    (RESULTS / "command.json").write_text(json.dumps(command, indent=2))
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
    child = subprocess.Popen(command, cwd=ROOT, env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
    os.close(slave)
    frames = TerminalFrames(120, 40)
    raw = bytearray()
    result = {"model": MODEL, "prompt": REQUEST, "command": command, "completed": False,
        "completionCheckObserved": False}
    terminal = {"requestRowObserved": False, "workResultObserved": False}

    def screen() -> str:
        return "\n".join(frames.display)

    def drain() -> None:
        if select.select([master], [], [], 0.05)[0]:
            data = os.read(master, 65536)
            raw.extend(data)
            frames.feed(data)

    def until(predicate, seconds: float = 180) -> None:
        deadline = time.monotonic() + seconds
        while not predicate():
            assert child.poll() is None, raw.decode(errors="replace")[-5000:]
            assert time.monotonic() < deadline, raw.decode(errors="replace")[-5000:]
            drain()

    def observe() -> None:
        text = screen()
        result["completionCheckObserved"] |= "Evaluating the objective and recorded evidence" in text
        work = ROOT / "result.txt"
        if work.exists():
            result["workFile"] = work.read_text(errors="replace").strip()
            terminal["workResultObserved"] = True
        records = goal_records()
        if records:
            result["goalId"] = records[0].get("goal", {}).get("id")

    def done() -> bool:
        records = goal_records()
        if not records:
            return False
        goal = records[0].get("goal", {})
        return (goal.get("status") == "complete"
            and result.get("workFile") == MARKER
            and result["completionCheckObserved"] is True)

    try:
        until(lambda: frames.count > 0, 60)
        events_path = RESULTS / "events.jsonl"
        def ready() -> bool:
            return events_path.exists() and any(
                json.loads(line).get("event") == "ready"
                for line in events_path.read_text(errors="replace").splitlines() if line.strip())
        until(ready, 120)
        os.write(master, ("/goal " + REQUEST + "\r").encode())
        until(lambda: "[goal] requesting" in screen(), 180)
        terminal["requestRowObserved"] = True
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            drain()
            observe()
            if done():
                result["completed"] = True
                break
            if child.poll() is not None:
                break
        drain()
        text = screen()
        result["completionCheckObserved"] |= "Evaluating the objective and recorded evidence" in text
        result["completionCheckObserved"] |= "[goal] completed" in text or "[goal] not met" in text
        records = goal_records()
        result["completionCheckObserved"] |= bool(records and "[goal] check failed" in text)
        if records:
            (RESULTS / "goal-record.json").write_text(json.dumps(records[0], indent=2))
        result["goalStatus"] = records[0].get("goal", {}).get("status") if records else None
        result["completed"] = done()
        result["screen"] = text[-6000:]
        terminal["lastScreen"] = text[-6000:]
    except BaseException as error:
        result["error"] = str(error)[-2000:]
    finally:
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=3)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=3)
                except ProcessLookupError:
                    pass
        os.close(master)
        (RESULTS / "raw-terminal.ansi").write_bytes(bytes(raw))
        (RESULTS / "run.json").write_text(json.dumps(result, indent=2))
        (RESULTS / "terminal.json").write_text(json.dumps(terminal, indent=2))
        session = ROOT / "session.jsonl"
        events_path = RESULTS / "events.jsonl"
        if not events_path.exists():
            events = []
            if session.exists():
                for line in session.read_text(errors="replace").splitlines():
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    message = row.get("message")
                    if isinstance(message, dict) and message.get("role") == "assistant" and isinstance(message.get("usage"), dict):
                        events.append({"type": "message_end", "message": {"usage": message["usage"]}})
            events_path.write_text("".join(json.dumps(row) + "\n" for row in events))


if __name__ == "__main__":
    main()
