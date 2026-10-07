"""Native live-rows probe. Run explicitly; drives a real pi TUI over a pty.

Sends one idle ``/goal`` carrying a PROBE_LIVE requirement, then observes:
- exactly one ``[goal] started`` transcript row with the
  requirement verbatim in a block under the head;
- one ``[goal] Researching`` transcript row while the scripted progressive
  child works, showing the child's own latest activity as progress;
  reports as its activity;
- no widget mounted above the editor at any point, because research blocks and
  the tool row already shows the wait.
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

# The last activity the scripted child reports, which is the progress the row
# must show while it works.
LATEST_ACTIVITY = "export.ts builds the CSV"


def main() -> None:
    repo = pathlib.Path(__file__).resolve().parents[3]
    with tempfile.TemporaryDirectory(prefix="goal-live-") as raw:
        root = pathlib.Path(raw)
        agent = root / "agent"
        agent.mkdir()
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 60, 120, 0, 0))
        mounts_trace = root / "mounts.jsonl"
        env = dict(os.environ, PI_CODING_AGENT_DIR=str(agent), TERM="xterm-256color",
                   PI_GOAL_OFFLINE_RESEARCH="progressive",
                   PI_GOAL_OFFLINE_MOUNTS=str(mounts_trace),
                   PI_GOAL_OFFLINE_LIVE="1")
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

        try:
            deadline = time.monotonic() + 15
            while b"goal_offline_fixture.ts" not in output and time.monotonic() < deadline:
                drain(0.05)
            assert b"goal_offline_fixture.ts" in output, "native extension startup did not finish"
            drain(0.2)
            send("/goal PROBE_LIVE Export the reports page as CSV")
            deadline = time.monotonic() + 60
            # A resize makes the TUI re-render every stored row from its state, which
            # is the only way to observe a row that was completed off the repaint
            # path. ctrl+o then expands the rows so the body is visible.
            drain(1.5)
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 58, 120, 0, 0))
            drain(2.0)
            os.write(master, b"\x0f")
            drain(3.0)
            result_screen = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07", "",
                                   output.decode(errors="replace"))
            assert result_screen
            screen = output.decode(errors="replace")
            clean = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07", "", screen)
            heads = re.findall(r"\[goal\] started", clean)
            assert len(heads) == 1, f"exactly one lifecycle row, saw {len(heads)}"
            assert "[goal] started" in clean, clean[-2000:]
            assert "[goal] started ·" not in clean, "the head must not repeat the subject"
            assert "Export the reports page as CSV" in clean, "requirement verbatim under the head"
            research_rows = re.findall(r"\[goal\] Researching\.\.\.", clean)
            assert len(research_rows) == 1, f"exactly one in-progress research row, saw {len(research_rows)}"
            subject_at = clean.find("[goal] Researching...")
            activity_at = clean.find(LATEST_ACTIVITY, subject_at)
            assert activity_at != -1, "the newest activity is rendered after the subject"
            # pi-kit fits every band row to the content width, so a stacked row is
            # separated by the subject row's end padding. Side by side would leave
            # only a small gap.
            gap = activity_at - (subject_at + len("[goal] Researching..."))
            assert gap >= 20, f"the activity starts its own row, gap was {gap}"
            mounts = [json.loads(line) for line in mounts_trace.read_text().splitlines() if line.strip()]
            above = [row for row in mounts if row.get("placement") == "aboveEditor"]
            assert not above, f"research mounted a widget above the editor: {above}"
            assert all(row.get("key") != "goal-research" for row in mounts), mounts
            research_files = list((root / ".pi/goals").glob("*/research.md"))
            assert research_files, "research findings attach to the created goal"
            assert "writes the CSV" in research_files[0].read_text(), "the attached findings are the live child output"
            # The finished row should have a markdown body and no character count.
            # Pi 1.0.4 does not repaint this tool row after completion, even with a
            # final partial update; record that host limitation explicitly.
            completed_painted = "[goal] Research ready" in result_screen
            raw_stream = output.decode(errors="replace")
            # The completion row may be painted with styling between characters that
            # the cleaning regex leaves behind, so the raw bytes are checked too.
            raw_has_result = "Research ready" in raw_stream
            print(f"raw stream contains 'Research ready': {'yes' if raw_has_result else 'no'}")
            if raw_has_result:
                at = raw_stream.find("Research ready")
                print("raw window: " + repr(raw_stream[max(0, at - 90):at + 60]))
            if completed_painted:
                assert "chars)" not in result_screen, "the result subject carries no character count"
                assert "Findings" in result_screen, "the findings body is rendered"
                assert "# Findings" not in result_screen, "markdown consumed the heading marker"
            print("GOAL_NATIVE_LIVE_OK")
            print(f"research row: {len(research_rows)} [goal] Researching... row with the activity on its own row")
            if completed_painted:
                print("result row: [goal] Research ready, markdown body, no character count")
            else:
                print("result row: NOT painted; the row keeps its in-progress spec")
            print("completed row painted: "
                  f"{'yes' if completed_painted else 'NO, the row keeps its in-progress spec'}")
            # A goal row that never streamed a partial, for contrast: if this one is
            # painted, the difference is the streaming, not the renderer.
            print(f"non-streamed completed row ([goal] Goal created and focused): "
                  f"{'yes' if '[goal] Goal created and focused' in result_screen else 'no'}")
            print(f"widget mounts: {len(mounts)}, none above the editor")
            print(f"latest progress on screen: {'yes' if LATEST_ACTIVITY in clean else 'MISSING'}")
            print("procedure head: [goal] started")
        finally:
            try:
                terminate_fixture(child)
            finally:
                os.close(master)
        assert child.poll() is not None
        print("GOAL_NATIVE_LIVE_DONE")


if __name__ == "__main__":
    main()
