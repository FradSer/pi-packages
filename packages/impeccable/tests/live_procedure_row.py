"""Verify the real /impeccable procedure row in a live Pi terminal, offline.

Manual verification: uv run --no-project packages/impeccable/tests/live_procedure_row.py
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import pty
import secrets
import select
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import time
from collections.abc import Callable
from pathlib import Path

FIXTURE = Path(__file__).with_name("procedure-row-live-fixture.ts")
REQUEST = "tighten the spacing\nand the padding"
FREEFORM = "aaaa\nzzzz"
# pi's dark theme paints userMessageBg #343541; tool bands stay green.
USER_MESSAGE_BG = "48;2;52;53;65"
TOOL_SUCCESS_BG = "48;2;40;50;40"


def read_snapshots(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.endswith("}")]


def procedure_rows(path: Path, width: int) -> list[dict]:
    return [row for row in read_snapshots(path) if row["kind"] == "procedure" and row["width"] == width]


def band_content(lines: list[str]) -> list[str]:
    """Drop the blank pad rows around the band and keep every authored row."""
    return [line.strip() for line in lines[1:-1]]


def verify_rows(rows: list[dict]) -> None:
    assert rows, "the procedure row never rendered"
    row = rows[-1]
    assert row["customType"] == "impeccable-procedure", row
    assert row["details"]["request"] == REQUEST, row["details"]
    content = band_content(row["lines"])
    assert content == ["[impeccable] started", "", "tighten the spacing", "and the padding"], content
    assert "to expand" not in "\n".join(row["lines"]), row["lines"]
    assert "# polish" not in "\n".join(row["lines"]), row["lines"]
    painted = "\n".join(row["raw"])
    assert USER_MESSAGE_BG in painted, "the row is not painted with pi's user-message background"
    assert TOOL_SUCCESS_BG not in painted, "the row still paints the tool-success band"


def wait_for(master: int, process: subprocess.Popen, transcript: bytearray, predicate: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if select.select([master], [], [], 0.05)[0]:
            try:
                transcript.extend(os.read(master, 65536))
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                process.wait(timeout=3)
                if predicate():
                    return
                break
        if predicate():
            return
        if process.poll() is not None:
            break
    if predicate():
        return
    raise AssertionError(transcript.decode(errors="replace")[-6000:])


def verify_tui(command: list[str], env: dict[str, str], cwd: Path, snapshots: Path) -> dict:
    master, slave = pty.openpty()
    transcript = bytearray()
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    try:
        wait_for(master, process, transcript, lambda: b"IM_ROW_LIVE_READY" in transcript)
        # Bracketed paste keeps the authored line break inside the submitted command.
        os.write(master, f"\x1b[200~/impeccable polish {REQUEST}\x1b[201~\r".encode())
        wait_for(master, process, transcript, lambda: bool(procedure_rows(snapshots, 120)))
        rows = procedure_rows(snapshots, 120)
        verify_rows(rows)
        assert REQUEST not in transcript.decode(errors="replace"), "the raw procedure request was echoed as user text"
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 48, 0, 0))
        process.send_signal(signal.SIGWINCH)
        wait_for(master, process, transcript, lambda: any(row["width"] == 48 for row in procedure_rows(snapshots, 48)))
        narrow = procedure_rows(snapshots, 48)[-1]
        assert "to expand" not in "\n".join(narrow["lines"]), narrow["lines"]
        assert all(len(line) <= 48 for line in narrow["lines"]), narrow["lines"]
        # The row never needs expansion: pi's expand key must reproduce the same content.
        os.write(master, b"\x0f")
        time.sleep(1.0)
        expanded = [row for row in procedure_rows(snapshots, 48) if row["expanded"]]
        # An unmatched freeform request must also arrive as one row, not as a plain-text pack.
        os.write(master, f"\x1b[200~/impeccable {FREEFORM}\x1b[201~\r".encode())
        wait_for(master, process, transcript,
                 lambda: any(row["details"]["request"] == FREEFORM for row in procedure_rows(snapshots, 48)))
        freeform = [row for row in procedure_rows(snapshots, 48) if row["details"]["request"] == FREEFORM][-1]
        assert band_content(freeform["lines"]) == ["[impeccable] started", "", "aaaa", "zzzz"], freeform["lines"]
        assert all(len(line) <= 48 for line in freeform["lines"]), freeform["lines"]
        os.write(master, b"/quit\r")
        wait_for(master, process, transcript, lambda: process.poll() is not None)
        assert process.returncode == 0
        rendered = transcript.decode(errors="replace")
        assert "max 2 capabilities" not in rendered, "the router pack leaked into the terminal as plain text"
        return {"width120": rows[-1]["lines"], "width48": narrow["lines"],
                "freeform": freeform["lines"], "expandedRepaints": len(expanded)}
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        os.close(master)


def main() -> None:
    pi = shutil.which("pi")
    assert pi, "pi CLI is required for live verification"
    with tempfile.TemporaryDirectory(prefix="impeccable-row-live-") as directory:
        cwd = Path(directory)
        agent_dir = cwd / "agent"
        agent_dir.mkdir()
        (agent_dir / "settings.json").write_text(json.dumps({"theme": "dark", "quietStartup": True}))
        env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
        env.update({
            "HOME": str(cwd), "PI_CODING_AGENT_DIR": str(agent_dir), "PI_OFFLINE": "1",
            "PI_IMPECCABLE_LIVE_AUTH": secrets.token_hex(16), "TERM": "xterm-256color",
            "PI_IMPECCABLE_LIVE_SNAPSHOTS": str(cwd / "rows.jsonl"),
        })
        command = [pi, "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes",
                   "--no-context-files", "--no-approve", "--extension", str(FIXTURE), "--provider",
                   "procedure-row-fixture", "--model", "deterministic", "--thinking", "off",
                   "--no-builtin-tools", "Say IM_ROW_LIVE_READY"]
        rendered = verify_tui(command, env, cwd, cwd / "rows.jsonl")
        print("IM_ROW_LIVE_DONE=" + json.dumps(rendered))


if __name__ == "__main__":
    main()