"""Native acceptance: /goal <text> shows one requesting row with the verbatim words.

Run: uv run --no-project --with pyte python packages/goal/tests/goal_native_request_row.py

The real Pi CLI runs the real Goal extension behind a deterministic scripted provider inside a
disposable project and agent directory. The probe types one goal request, then reads the composed
terminal screen. It asserts what a reader sees and that the model-only request body never reaches
the terminal.
"""
from __future__ import annotations
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

from goal_native_frames import TerminalFrames
from goal_native_live import REQUEST_BODY_MARKERS, REQUEST_WORDS, assert_request_frame
from goal_native_tui import terminate_fixture


def goal_records(agent: Path) -> list[Path]:
    """Every goal record this run wrote, under its own agent directory."""
    return sorted((agent / "goals").glob("*/*/record.json"))


def main() -> None:
    repo = Path(os.environ.get("GOAL_VERIFY_ROOT", Path(__file__).resolve().parents[3]))
    fixture = repo / "packages/goal/tests/goal_completion_fixture.ts"
    with tempfile.TemporaryDirectory(prefix="goal-native-request-") as raw:
        root = Path(raw); agent = root / "agent"; agent.mkdir(); home = root / "home"; home.mkdir()
        trace = root / "trace.jsonl"
        env = dict(os.environ, HOME=str(home), PI_CODING_AGENT_DIR=str(agent), TERM="xterm-256color",
                   PI_OFFLINE="1", PI_GOAL_COMPLETION_CASE="complete", PI_GOAL_COMPLETION_TRACE=str(trace),
                   PI_GOAL_FIXTURE_DELAY_MS="4000")
        command = [os.environ.get("GOAL_PI_BIN", "pi"), "-ne", "-ns", "-np", "-nc", "--no-session",
                   "-e", str(fixture), "--model", "goal-completion-offline/scripted"]
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
        child = subprocess.Popen(command, cwd=root, env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        frames = TerminalFrames(120, 40)
        raw_output = bytearray()
        seen: list[str] = []

        def drain() -> None:
            while select.select([master], [], [], 0.05)[0]:
                data = os.read(master, 65536); raw_output.extend(data)
                before = frames.count
                frames.feed(data)
                if frames.count != before:
                    seen.append("\n".join(frames.display))

        def until(predicate, seconds: float = 30) -> None:
            deadline = time.monotonic() + seconds
            while not predicate():
                assert child.poll() is None, raw_output.decode(errors="replace")[-5000:]
                assert time.monotonic() < deadline, raw_output.decode(errors="replace")[-5000:]
                drain()

        def entries() -> list[dict]:
            return [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []

        def screen() -> str:
            return "\n".join(frames.display)

        try:
            until(lambda: any(entry["kind"] == "ready" for entry in entries()) and frames.count > 0)
            os.write(master, ("/goal " + REQUEST_WORDS + "\r").encode())
            until(lambda: "[goal] requesting" in screen())
            drain()
            assert_request_frame(frames.display, created=False)
            # The start delay holds the run, so the request row is the only transcript row.
            # Resize that same live component and require the words to stay readable.
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 60, 0, 0))
            frames.resize(60, 24)
            os.kill(child.pid, signal.SIGWINCH)
            until(lambda: REQUEST_WORDS in screen() and "[goal] requesting" in screen())
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
            frames.resize(120, 40)
            os.kill(child.pid, signal.SIGWINCH)
            until(lambda: "[goal] started" in screen())
            drain()
            assert_request_frame(frames.display)
            # The model-only body is not on the screen, and no frame ever painted it.
            for marker in REQUEST_BODY_MARKERS:
                assert marker not in "\n".join(seen), f"the request body reached the terminal: {marker}"
                assert marker not in raw_output.decode(errors="replace"), f"the request body reached the terminal: {marker}"
            # The same run created the goal and ran its completion check. The check trace line is
            # written before the verdict, so wait for the outcome it produces rather than asserting
            # between the two. A completed goal keeps its record with the terminal status.
            until(lambda: sum(1 for entry in entries() if entry["kind"] == "check") == 1)
            assert sum(1 for entry in entries() if entry["kind"] == "provider") >= 2, entries()
            until(lambda: goal_records(agent) and json.loads(goal_records(agent)[0].read_text())["goal"]["status"] == "complete")
            assert not (root / ".pi").exists(), "no goal state is written into the working directory"
        finally:
            terminate_fixture(child)
            os.close(master)
        # Print the facts the assertions read, so the transcript carries the evidence and not
        # only the claim: the row, the scanned surface, and the creation that followed.
        head = next((line.strip() for line in frames.display if "[goal] requesting" in line), "")
        print(
            f"PASS native request row: {frames.count} composed frames, {len(raw_output)} raw bytes · "
            f"row={head} / {REQUEST_WORDS} · "
            f"body markers absent from every frame and every raw byte ({len(REQUEST_BODY_MARKERS)} markers) · "
            f"creation row present after the request",
            flush=True,
        )
    print("GOAL_NATIVE_REQUEST_ROW_OK")


if __name__ == "__main__":
    main()
