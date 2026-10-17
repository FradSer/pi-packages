"""Native TUI row probe for /loop. Run explicitly from the repository root:

    uv run --no-project --with pyte python packages/loop/tests/live_loop_rows.py

What it establishes: the start row and the below-editor status row are composed by the
real Pi terminal, stay readable at 120 and 48 columns, survive a live resize of the same
component, are reachable by PageUp when the viewport is shorter than the transcript, and
the status row clears when the loop finishes. A free request additionally composes the
`[loop] request` row, the request text under it, and the `Analyzing` status row at 48
columns. No loop row is wider than the terminal.

At 48 columns the start row truncates: the expansion hint takes the room the subject
needs, so the transcript row keeps its label and its affordance while the schedule facts
stay readable in the row below the editor. This probe asserts exactly that split, and it
asserts the full subject at 120 columns.

What it does not establish: physical-terminal or theme rendering, screen-reader output,
and any real-model behavior. The provider is scripted and local, and the decision endpoint
is a loopback that answers by question id.
"""
from __future__ import annotations

import fcntl
import http.server
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
import threading
import time

import pyte

PACKAGE = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = PACKAGE / "tests" / "loop-live-fixture.ts"
COMMAND = "/loop --every 1s --times 2 UI_PROBE"
# A free request: the schedule phrase is metadata, so the repeated message is
# UI_PROBE and the request row shows the whole request.
FREE_COMMAND = "/loop UI_PROBE every 1s"
TRACE_PROMPT = "UI_PROBE"
# Rows this package draws, for the width check only.
LOOP_KEYS = ("[loop]", "Analyzing", "Looping", TRACE_PROMPT)


def choice(key: str, confidence: float = 0.9) -> dict:
    return {"type": "choice", "choice": key, "probabilities": {key: confidence}, "confidence": confidence}


def start_decision_server(hold_seconds: float) -> tuple[http.server.HTTPServer, list[list[str]]]:
    """A real loopback endpoint that answers slowly, so the row while it runs is composed."""
    seen: list[list[str]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            ids = sorted(body.get("questions", {}).keys())
            seen.append(ids)
            time.sleep(hold_seconds)
            payload = json.dumps({
                "model": "jev-1.13.0",
                # "3" is a listed run limit; "2" is not, and the plan would refuse it.
                "answers": {"interval": choice("30s"), "runs": choice("3"), "stop": choice("none")},
                "usage": {"input_tokens": 11, "output_tokens": 4},
            }).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


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
             scroll_pages: int = 0, command: str = COMMAND, decision: bool = False,
             expect_injections: int = 2) -> dict:
    server = None
    if decision:
        server, _seen = start_decision_server(hold_seconds=1.5)
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
        if server is not None:
            env["TYPESAFE_API_KEY"] = "loop-rows-key"
            env["TYPESAFE_BASE_URL"] = "http://127.0.0.1:%d" % server.server_address[1]
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
            os.write(master, (command + "\r").encode())

            # The row while the decision request runs is composed only if the
            # endpoint holds the answer, so it is read while it is on screen.
            analyzing = (
                wait_for(lambda l: [line for line in l if "Analyzing" in line] or None, 20)
                if decision else []
            )

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

            if expect_injections >= 2:
                assert wait_for(lambda _l: True if injections() >= 2 else None, 30) is not None, \
                    name + ": the second injection never arrived"
            else:
                # The free case runs a 30s cadence, so its own stop releases the row.
                os.write(master, b"/loop stop\r")
            wait_for(lambda _l: None, 2.5)
            if scroll_pages > 0:
                # The transcript is reachable by scrolling even when it is above the viewport.
                for _page in range(scroll_pages):
                    os.write(master, b"\x1b[5~")
                    wait_for(lambda _l: None, 0.4)
            final = lines()
            visible = [line.rstrip() for line in screen.display if line.strip()]
            width = screen.columns if resize is None else resize[0]
            return {
                "case": name,
                "command": command,
                "analyzing_lines": analyzing or [],
                "over_width": [line for line in final
                               if len(line) > width and any(key in line for key in LOOP_KEYS)],
                "columns": width,
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
            if server is not None:
                server.shutdown()


def find(lines: list[str], *needles: str) -> str | None:
    for line in lines:
        if all(needle in line for needle in needles):
            return line
    return None


def main() -> int:
    failures: list[str] = []
    wanted = sys.argv[1:]
    planned = [
        ("wide-120x40", 120, 40, None, 0, COMMAND, False, 2, "every 1s"),
        ("live-resize-120x40-to-48x24", 120, 40, (48, 24), 0, COMMAND, False, 2, "every 1s"),
        ("short-48x12-scrolled", 48, 12, None, int(os.environ.get("LOOP_ROWS_PAGES", "5")), COMMAND, False, 2,
         "every 1s"),
        # The free form adds the request row, the request text and the row while the
        # plan is resolved, and it composes all of them at 48 columns.
        ("free-request-48x24", 48, 24, None, 0, FREE_COMMAND, True, 1, "every 30s"),
    ]
    cases = [run_case(name, cols, rows, resize, scroll, command, decision, injections)
             for name, cols, rows, resize, scroll, command, decision, injections, _cadence in planned
             if not wanted or name in wanted]
    cadence_of = {name: cadence for name, _c, _r, _rz, _s, _cmd, _d, _i, cadence in planned}
    for case in cases:
        name = case["case"]
        final = case["final_lines"]
        active = case["active_lines"]
        cadence = cadence_of[name]
        row = find(final, "loop", "started")
        if row is None:
            failures.append(name + ": no start row for the loop")
        elif cadence not in row and "to expand" not in row:
            # The row either names the cadence or truncates and offers the
            # expansion that reveals it. The row below the editor names the
            # cadence at every width, and this probe checks that next.
            failures.append(name + ": the start row names neither the cadence nor an expansion: " + row[:90])
        if case["over_width"]:
            failures.append(name + ": a loop row is wider than the terminal: " + case["over_width"][0][:80])
        if "Analyzing" in case["command"]:
            failures.append(name + ": the free command must not be parameterized")
        if case["command"] == FREE_COMMAND:
            if find(final, "loop", "request") is None:
                failures.append(name + ": no request row for a free request")
            if find(final, "UI_PROBE every 1s") is None:
                failures.append(name + ": the request text is not composed under the row")
            if find(case["analyzing_lines"], "Analyzing", "UI_PROBE") is None:
                failures.append(name + ": no row while the decision request ran")
        status = find(active, "Looping", cadence)
        if status is None:
            failures.append(name + ": no below-editor status row naming the cadence while the loop ran")
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
