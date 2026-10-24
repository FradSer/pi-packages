"""Native acceptance: one /goal request that only creates the goal keeps pursuing.

Run: uv run --no-project --with pyte python packages/goal/tests/goal_native_request_continuation.py

Real Pi CLI, real Goal extension, deterministic scripted provider, disposable project and agent
directory. The probe types one `/goal` request with no goal in place. The scripted run records the
objective and stops without doing anything else, which is the shape a real model produces when it
plans to work in the continuation. The probe asserts what the runtime owes the user: the goal is
created, it keeps pursuing, exactly the authorized continuation runs and changes the workspace, and
the goal is never reported as waiting because that run called no tool.
"""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import tempfile
import termios
import time

from goal_native_frames import TerminalFrames
from goal_native_tui import terminate_fixture

REQUEST = "Add Windows CSV export."
# The reason an earlier runtime wrote when a settled run had no tool receipt, and the row it painted.
# Both are checked so a run-level no-work stop cannot come back unnoticed: a run that only answered
# spends a slot in the change window instead of stopping the goal.
NO_WORK_WAIT = "No effective work was recorded"


def open_goals(agent: Path) -> list[dict]:
    """Every open goal record this run wrote, under its own agent directory."""
    return [json.loads(path.read_text())["goal"] for path in sorted((agent / "goals").glob("*/*/record.json"))]


def pursuing(agent: Path) -> dict | None:
    """The one goal once it has really run its continuation, or None."""
    goals = open_goals(agent)
    if len(goals) != 1:
        return None
    goal = goals[0]
    scheduler = goal.get("scheduler") or {}
    if goal.get("status") != "active" or goal.get("autoContinue") is not True:
        return None
    if goal.get("pauseReason") is not None:
        return None
    if (scheduler.get("used") or 0) < 1:
        return None
    return goal


def main() -> None:
    repo = Path(os.environ.get("GOAL_VERIFY_ROOT", Path(__file__).resolve().parents[3]))
    fixture = repo / "packages/goal/tests/goal_completion_fixture.ts"
    with tempfile.TemporaryDirectory(prefix="goal-native-request-continuation-") as raw:
        root = Path(raw); agent = root / "agent"; agent.mkdir(); home = root / "home"; home.mkdir()
        trace = root / "trace.jsonl"
        env = dict(os.environ, HOME=str(home), PI_CODING_AGENT_DIR=str(agent), TERM="xterm-256color",
                   PI_OFFLINE="1", PI_GOAL_COMPLETION_CASE="request", PI_GOAL_COMPLETION_TRACE=str(trace))
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

        def painted() -> str:
            # Rows this run produced scroll away under its own work, so they are read
            # from the frames that were composed while it ran, not only from the last
            # visible screen.
            return "\n".join(seen)

        try:
            until(lambda: any(entry["kind"] == "ready" for entry in entries()) and frames.count > 0)
            os.write(master, ("/goal " + REQUEST + "\r").encode())
            # The request row and the creation it produced are what the user asked for.
            until(lambda: "[goal] requesting" in painted())
            until(lambda: "[goal] started" in painted())
            drain()
            assert REQUEST in painted(), painted()[-3000:]
            # The create-only run must not end the goal: a continuation runs, changes the
            # workspace, and the goal keeps pursuing.
            until(lambda: pursuing(agent) is not None)
            until(lambda: "Pursuing goal" in screen())
            until(lambda: list(root.glob("probe-work-*.txt")))
            drain()
            goal = open_goals(agent)[0]
            goal_id = goal["id"]
            phase = (goal.get("scheduler") or {}).get("phase")
            assert (goal.get("scheduler") or {}).get("used") >= 1, goal
            assert phase in {"ready", "claimed", "running"}, phase
            provider = [entry for entry in entries() if entry["kind"] == "provider"]
            assert len(provider) >= 3, entries()
            assert NO_WORK_WAIT not in painted(), "the run-level no-work wait must never be painted"
            assert NO_WORK_WAIT not in raw_output.decode(errors="replace"), "the wait must never be written"
            assert not (root / ".pi").exists(), "no goal state is written into the working directory"
            print("PASS native request continuation: " + str(frames.count) + " composed frames · one goal " + goal_id
                  + " · the create-only request kept pursuing and ran its continuation", flush=True)
        finally:
            terminate_fixture(child)
            os.close(master)
    print("GOAL_NATIVE_REQUEST_CONTINUATION_OK")


if __name__ == "__main__":
    main()