"""Native supersede probe. Run explicitly; drives a real pi TUI over a pty.

Seeds an existing, focused, paused goal, then sends ONE ``/goal <new request>``
and observes the supersede route. A scripted model drives that route, because
it is now the escape hatch rather than what ``/goal`` asks for: the seeded
requirement tells the model to revise the focused goal in place, and only a goal
that stopped for good, because it completed or spent its token budget, is
replaced.

- a new goal whose objective carries the earlier objective plus the new request;
- the earlier goal archived, with a ``goal_cleared`` / ``superseded`` event;
- the research-then-create route ran, so the new goal has attached findings.
"""
from __future__ import annotations

import fcntl
import json
import os
import pathlib
import pty
import re
import select
import struct
import subprocess
import tempfile
import termios
import time

from goal_native_tui import terminate_fixture


def main() -> None:
    repo = pathlib.Path(__file__).resolve().parents[3]
    with tempfile.TemporaryDirectory(prefix="goal-supersede-") as raw:
        root = pathlib.Path(raw)
        agent = root / "agent"
        agent.mkdir()
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
        env = dict(os.environ, PI_CODING_AGENT_DIR=str(agent), TERM="xterm-256color",
                   PI_GOAL_OFFLINE_RESEARCH="progressive",
                   PI_GOAL_OFFLINE_LIVE="1",
                   PI_GOAL_OFFLINE_SEED_EXISTING="1")
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
            drain(1.0)

        def open_goals() -> list[dict]:
            return [json.loads(path.read_text())["goal"]
                    for path in (root / ".pi/goals").glob("*/record.json")]

        def archived_goals() -> list[dict]:
            return [json.loads(path.read_text())["goal"]
                    for path in (root / ".pi/goals/archived").glob("*/record.json")]

        try:
            deadline = time.monotonic() + 15
            while b"goal_offline_fixture.ts" not in output and time.monotonic() < deadline:
                drain(0.05)
            assert b"goal_offline_fixture.ts" in output, "native extension startup did not finish"
            drain(0.5)
            seeded = [(root / ".pi/goals" / "goal_existing_probe" / "record.json")]
            assert seeded[0].exists(), "the fixture seeded no existing goal"
            assert json.loads(seeded[0].read_text())["goal"]["status"] == "paused", "the seeded goal is paused"

            # One real /goal request, with a goal already in place. Retried only
            # because the command refuses while a turn is still settling.
            carried: dict | None = None
            for _attempt in range(3):
                send("/goal PROBE_SUPERSEDE Audit the export path.")
                deadline = time.monotonic() + 25
                while time.monotonic() < deadline:
                    drain(0.5)
                    for goal in open_goals():
                        if "audit the export path" in goal.get("objective", ""):
                            carried = goal
                if carried:
                    break
            assert carried, f"no open goal carries the new request: {[g.get('objective') for g in open_goals()]}"
            assert "Probe the live goal rows" in carried["objective"], (
                f"the new objective carries the earlier goal: {carried['objective']}")
            assert "audit the export path" in carried["objective"], f"and the new request: {carried['objective']}"

            assert any("Probe the live goal rows" in goal.get("objective", "") for goal in archived_goals()), (
                f"the earlier goal is archived: {[g.get('objective') for g in archived_goals()]}")
            assert any("audit the export path" in goal.get("objective", "") for goal in open_goals()), "the new goal is the open one"
            assert len(open_goals()) == 1, f"one open goal remains, got {len(open_goals())}"

            events = [json.loads(line) for path in (root / ".pi/goals").rglob("ledger.jsonl")
                      for line in path.read_text().splitlines() if line.strip()]
            assert any(event.get("type") == "goal_cleared" and event.get("reason") == "superseded" for event in events), (
                f"the supersede is recorded: {[e.get('type') for e in events][-12:]}")
            assert list((root / ".pi/goals").rglob("research.md")), "the research-then-create route attached findings"

            # A bare /goal reports the focused goal. Naming the NEW objective is
            # what shows the earlier goal left the focused slot, not merely that
            # its directory moved into the archive.
            drain(1.5)
            send("/goal")
            drain(3.0)
            screen = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07", "", output.decode(errors="replace"))
            expected = f"Objective: {carried['objective']}"
            assert expected in screen, "the focused goal is the new one; screen tail: " + screen[-400:]

            print("GOAL_NATIVE_SUPERSEDE_OK")
            print("seeded goal: Probe the live goal rows. (paused, focused)")
            print(f"new goal: {carried['objective']}")
            print("earlier goal archived: yes; ledger goal_cleared/superseded: yes; research attached: yes")
            print("bare /goal reports the new objective: yes")
            print("GOAL_NATIVE_SUPERSEDE_DONE")
        finally:
            try:
                terminate_fixture(child)
            finally:
                os.close(master)
        assert child.poll() is not None


if __name__ == "__main__":
    main()