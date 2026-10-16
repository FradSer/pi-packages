"""Native TUI row probe for /loop. Run explicitly from the repository root:

    uv run --no-project --with pyte python packages/loop/tests/live_loop_rows.py

What it establishes: the start row and the below-editor status row are composed by the
real Pi terminal, stay readable at 120 and 48 columns, survive a live resize of the same
component, are reachable by PageUp when the viewport is shorter than the transcript, and
the status row clears when the loop finishes.

What it does not establish: physical-terminal or theme rendering, screen-reader output,
and any real-model behavior. The provider is scripted and local.
"""
from __future__ import annotations

import fcntl
import json
import os
import pathlib
import pty
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time

import pyte

PACKAGE = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = PACKAGE / "tests" / "loop-live-fixture.ts"
COMMAND = "/loop --every 1s --times 2 UI_PROBE"
TRACE_PROMPT = "UI_PROBE"


def history_lines(screen) -> list[str]:
    """Rows that scrolled above the viewport, oldest first."""
    history = getattr(screen, "history", None)
    if history is None:
        return []
    return ["".join(row[x].data for x in range(screen.columns)).rstrip() for row in history.top]


def read_trace(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run_case(name: str, cols: int, rows: int, resize: tuple[int, int] | None = None,
             scroll_pages: int = 0) -> dict:
    with tempfile.TemporaryDirectory(prefix="loop-rows-") as raw:
        root = pathlib.Path(raw)
        agent = root / "agent"
        agent.mkdir()
        trace = root / "trace.jsonl"
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        screen = pyte.HistoryScreen(cols, rows, history=500)
        stream = pyte.ByteStream(screen)
        env = dict(os.environ, HOME=str(root), PI_CODING_AGENT_DIR=str(agent),
                   TERM="xterm-256color", PI_OFFLINE="1", PI_LOOP_TRACE=str(trace))
        env.pop("TYPESAFE_API_KEY", None)
        child = subprocess.Popen(
            ["pi", "-ne", "-ns", "-np", "-nc", "--no-session",
             "-e", str(FIXTURE), "--model", "loop-offline/scripted"],
            cwd=root, env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
        )
        os.close(slave)
        raw_bytes = bytearray()

        def pump() -> None:
            if not select.select([master], [], [], 0.05)[0]:
                return
            try:
                data = os.read(master, 65536)
            except OSError:
                return
            raw_bytes.extend(data)
            stream.feed(data)

        def lines() -> list[str]:
            return history_lines(screen) + [line.rstrip() for line in screen.display]

        def wait_for(predicate, seconds: float):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                pump()
                found = predicate(lines())
                if found is not None:
                    return found
            return None

        def injections() -> int:
            return len([r for r in read_trace(trace)
                        if r.get("kind") == "start" and r.get("prompt") == TRACE_PROMPT])

        try:
            assert wait_for(lambda _l: True if any(
                r.get("kind") == "ready" for r in read_trace(trace)) else None, 30) is not None, \
                name + ": the fixture never started"
            os.write(master, (COMMAND + "\r").encode())

            assert wait_for(lambda _l: True if injections() >= 1 else None, 30) is not None, \
                name + ": the first injection never arrived"
            active = wait_for(lambda l: l if any("Looping" in line for line in l) else None, 5)
            active_lines = active if active is not None else lines()

            if resize is not None:
                new_cols, new_rows = resize
                fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", new_rows, new_cols, 0, 0))
                os.killpg(child.pid, signal.SIGWINCH)
                screen.resize(new_rows, new_cols)
                pump()

            assert wait_for(lambda _l: True if injections() >= 2 else None, 30) is not None, \
                name + ": the second injection never arrived"
            wait_for(lambda _l: None, 2.5)
            if scroll_pages > 0:
                # The transcript is reachable by scrolling even when it is above the viewport.
                for _page in range(scroll_pages):
                    os.write(master, b"\x1b[5~")
                    wait_for(lambda _l: None, 0.4)
            final = lines()
            visible = [line.rstrip() for line in screen.display if line.strip()]
            return {
                "case": name,
                "columns": screen.columns if resize is None else resize[0],
                "rows": screen.lines if resize is None else resize[1],
                "active_lines": [line for line in active_lines if line.strip()],
                "final_lines": [line for line in final if line.strip()],
                "visible_lines": visible,
                "raw_viewport": [line for line in screen.display],
                "raw_bytes": len(raw_bytes),
            }
        finally:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
            os.close(master)


def find(lines: list[str], *needles: str) -> str | None:
    for line in lines:
        if all(needle in line for needle in needles):
            return line
    return None


def main() -> int:
    failures: list[str] = []
    wanted = sys.argv[1:]
    planned = [
        ("wide-120x40", 120, 40, None, 0),
        ("live-resize-120x40-to-48x24", 120, 40, (48, 24), 0),
        ("short-48x12-scrolled", 48, 12, None, int(os.environ.get("LOOP_ROWS_PAGES", "5"))),
    ]
    cases = [run_case(name, cols, rows, resize, scroll)
             for name, cols, rows, resize, scroll in planned
             if not wanted or name in wanted]
    for case in cases:
        name = case["case"]
        final = case["final_lines"]
        active = case["active_lines"]
        row = find(final, "loop", "started", "every 1s")
        if row is None:
            failures.append(name + ": no start row naming the loop and its cadence")
        status = find(active, "Looping", "every 1s")
        if status is None:
            failures.append(name + ": no below-editor status row while the loop ran")
        if find(final, "Looping"):
            failures.append(name + ": the status row survived the finished loop")
        if not name.endswith("scrolled") and find(case["visible_lines"], TRACE_PROMPT) is None:
            failures.append(name + ": the newest injection is not visible")
        case["row"] = row
        case["status"] = status
        print(json.dumps(case))
    if failures:
        print(json.dumps({"failures": failures}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
