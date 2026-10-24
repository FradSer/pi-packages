"""Native acceptance: one /goal request revises the open goal in place.

Run: uv run --no-project --with pyte python packages/goal/tests/goal_native_revision.py

Real Pi CLI, real Goal extension, deterministic scripted provider, disposable project and agent
directory. The probe creates one goal, lets three runs that change nothing stop it, then sends one
/goal request with a goal already in place. It asserts what the runtime owes the user: the accepted
request lands as a revision of that one goal, the earlier requirement survives inside the objective,
the goal pursues again, and no archive or ledger appears.
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

REQUEST = "Audit the export path."
EARLIER = "Probe the live goal rows."
MERGED = "Probe the live goal rows. Audit the export path."


def goal_records(agent: Path) -> list[dict]:
    """Every open goal record this run wrote, under its own agent directory.

    State lives at `<agent>/goals/<project key>/<goal id>/record.json`; the probe
    globs for it rather than rebuilding the project key.
    """
    return [json.loads(path.read_text())["goal"] for path in sorted((agent / "goals").glob("*/*/record.json"))]


def main() -> None:
    repo = Path(os.environ.get("GOAL_VERIFY_ROOT", Path(__file__).resolve().parents[3]))
    fixture = repo / "packages/goal/tests/goal_completion_fixture.ts"
    with tempfile.TemporaryDirectory(prefix="goal-native-revision-") as raw:
        root = Path(raw); agent = root / "agent"; agent.mkdir(); home = root / "home"; home.mkdir()
        trace = root / "trace.jsonl"
        env = dict(os.environ, HOME=str(home), PI_CODING_AGENT_DIR=str(agent), TERM="xterm-256color",
                   PI_OFFLINE="1", PI_GOAL_COMPLETION_CASE="revision", PI_GOAL_COMPLETION_TRACE=str(trace))
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
            # One read per call, so the record is sampled every few milliseconds while a run
            # floods the screen. The revision's authorization lasts only as long as that run.
            if select.select([master], [], [], 0.05)[0]:
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

        def open_goals() -> list[dict]:
            return goal_records(agent)

        try:
            until(lambda: any(entry["kind"] == "ready" for entry in entries()) and frames.count > 0)
            # One goal, created by the real create_goal tool, then stopped because three
            # runs in a row produced nothing new: the receipt they repeat is one the
            # session had already seen.
            os.write(master, b"Start the goal.\r")

            def stopped_for_no_change() -> dict | None:
                goals = open_goals()
                if len(goals) != 1 or goals[0].get("objective") != EARLIER:
                    return None
                if goals[0].get("autoContinue") is not False:
                    return None
                return goals[0]

            until(lambda: stopped_for_no_change() is not None)
            until(lambda: "[goal] waiting" in screen())
            drain()
            seeded = stopped_for_no_change()
            assert seeded is not None, open_goals()
            assert "produced nothing new" in (seeded.get("pauseReason") or ""), seeded

            # One real /goal request with that goal in place.
            os.write(master, ("/goal " + REQUEST + "\r").encode())
            # The revision is the transition to observe: the accepted request lifts the stop on
            # this one goal, so the record turns active and pursuing again, and every later run
            # changes the workspace, so it stays that way.
            def revised_and_pursuing() -> bool:
                goals = open_goals()
                if len(goals) != 1:
                    return False
                scheduler = goals[0].get("scheduler") or {}
                return (goals[0]["objective"] == MERGED and goals[0]["autoContinue"] is True
                        and scheduler.get("phase") in {"ready", "claimed", "running"})
            until(revised_and_pursuing)
            until(lambda: "Pursuing goal" in screen())
            drain()
            # Read again after the pursuit assertion, so the state under test is the state the
            # screen reports and not only the moment the revision landed.
            goal = open_goals()[0]
            phase = (goal.get("scheduler") or {}).get("phase")
            goal_id = goal["id"]
            assert goal_id == seeded["id"], "the request revised the open goal instead of replacing it"
            assert "verificationContract" not in goal, "the objective is the record's only requirement text"
            assert goal["status"] == "active" and goal["autoContinue"] is True, goal
            assert phase in {"ready", "claimed", "running"}, phase
            assert not (root / ".pi").exists(), "no goal state is written into the working directory"
            assert not list((agent / "goals").rglob("ledger.jsonl")), "no ledger is written"
            assert not list((agent / "goals").rglob("research.md")), "no research file is written"
            assert "Evaluating the objective and recorded evidence" not in screen(), "no completion check ran for a revision"
            # Rows this run produced scroll away under its own work, so they are read from the
            # frames that were composed while it ran: goal_native_request_row.py owns the
            # composed-screen proof that the request row paints, and this probe owns the record
            # the request produced.
            painted = "\n".join(seen)
            assert "[goal] requesting" in painted, "the request row was never painted"
            assert "[goal] updated" in painted, "the revision result was never painted"
            print("PASS native revision: " + str(frames.count) + " composed frames · one goal " + goal_id
                  + " · objective carries the earlier requirement and the request · pursuing again", flush=True)
        finally:
            terminate_fixture(child)
            os.close(master)
    print("GOAL_NATIVE_REVISION_OK")


if __name__ == "__main__":
    main()
