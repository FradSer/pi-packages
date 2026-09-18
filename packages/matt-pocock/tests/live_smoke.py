"""Run offline real-Pi print and PTY checks in a temporary home, without user auth.

Manual verification: uv run --no-project packages/matt-pocock/tests/live_smoke.py
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

FIXTURE = Path(__file__).with_name("lifecycle-live-fixture.ts")
EXPECTED = (
    "started · Reproducing & Diagnostics",
    "event · Reproducing & Diagnostics completed",
    "event · Implementation",
    "event · Code Review",
    "event · Code Review completed",
    "started · Architecture Survey",
    "event · Implementation cancelled",
)


def read_snapshots(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.endswith("}")]


def verify_results(rows: list[dict]) -> None:
    results = [row for row in rows if row["kind"] == "result"]
    assert len(results) == 9, results
    assert all(not row["isError"] for row in results), results
    assert results[1]["details"]["subject"] == "Reproducing & Diagnostics completed"
    assert results[5]["details"]["subject"] == "Code Review completed"
    assert results[8]["details"]["subject"] == "Implementation cancelled"
    assert results[1]["details"]["state"]["route"] == "hard-bug"
    assert results[1]["details"]["state"]["phase"] == "feedback-loop"
    assert results[1]["details"]["state"]["status"] == "completed"
    assert results[8]["details"]["state"]["status"] == "cancelled"


def verify_tui(command: list[str], env: dict[str, str], cwd: Path, snapshots: Path) -> list[str]:
    master, slave = pty.openpty()
    transcript = bytearray()

    def resize(width: int) -> None:
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 40, width, 0, 0))

    resize(120)
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)

    def wait_for(predicate: Callable[[], bool]) -> None:
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
        # Exit can occur between the predicate check and poll above.
        if predicate():
            return
        raise AssertionError(transcript.decode(errors="replace")[-6000:])

    def has_render(width: int, expanded: bool) -> bool:
        return any(row["kind"] == "render" and row["width"] == width and row["expanded"] is expanded
                   for row in read_snapshots(snapshots))

    try:
        wait_for(lambda: b"MP_PHASE_LIVE_READY" in transcript and has_render(120, False))
        rows = read_snapshots(snapshots)
        verify_results(rows)
        headers = [line.strip() for row in rows if row["kind"] == "render" and not row["expanded"]
                   for line in row["lines"] if "[matt pocock]" in line]
        for expected in EXPECTED:
            assert any(f"[matt pocock] {expected}" in line for line in headers), (expected, headers)
        assert all("hard-bug" not in line and "Hard Bug Diagnosis" not in line and "Codebase Architecture" not in line
                   for line in headers), headers
        os.write(master, b"\x0f")  # Actual Ctrl+O through Pi's editor.
        wait_for(lambda: has_render(120, True))
        expanded = "\n".join(line for row in read_snapshots(snapshots)
                             if row["kind"] == "render" and row["expanded"] for line in row["lines"])
        assert "route · Hard Bug Diagnosis" in expanded
        assert "route · Codebase Architecture" in expanded
        assert "route · hard-bug" not in expanded
        assert "phase ·" not in expanded
        assert "action ·" not in expanded
        assert "reason · Offline fixture finished" in expanded
        assert "procedure-source" not in expanded
        for row in read_snapshots(snapshots):
            if row["kind"] != "render" or row["width"] != 120:
                continue
            details = row.get("details") or {}
            text = "\n".join(row["lines"])
            if details.get("action") in ("transition", "complete"):
                assert "to expand" not in text, row
            if details.get("action") == "cancel":
                if row["expanded"]:
                    assert text.count("reason · Offline fixture finished") == 1, row
                else:
                    assert "to expand" in text and "Offline fixture finished" not in text, row
        resize(48)
        process.send_signal(signal.SIGWINCH)
        wait_for(lambda: has_render(48, True))
        os.write(master, b"\x0f")
        wait_for(lambda: has_render(48, False))
        for row in read_snapshots(snapshots):
            if row["kind"] == "render":
                assert all("\n" not in line and len(line) <= row["width"] for line in row["lines"]), row
        os.write(master, b"/quit\r")
        wait_for(lambda: process.poll() is not None)
        assert process.returncode == 0
        return sorted(set(headers))
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
    with tempfile.TemporaryDirectory(prefix="mp-phase-live-") as directory:
        cwd = Path(directory)
        agent_dir = cwd / "agent"
        agent_dir.mkdir()
        (agent_dir / "settings.json").write_text(json.dumps({"theme": "dark", "quietStartup": True}))
        env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
        env.update({
            "HOME": str(cwd), "PI_CODING_AGENT_DIR": str(agent_dir), "PI_OFFLINE": "1",
            "PI_PHASE_LIVE_AUTH": secrets.token_hex(16), "TERM": "xterm-256color",
        })
        command = [pi, "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes",
                   "--no-context-files", "--no-approve", "--extension", str(FIXTURE), "--provider", "phase-lifecycle-fixture",
                   "--model", "deterministic", "--thinking", "off", "--no-builtin-tools", "Run the offline lifecycle fixture"]
        print_snapshots = cwd / "print.jsonl"
        env["PI_PHASE_LIVE_SNAPSHOTS"] = str(print_snapshots)
        printed = subprocess.run([*command, "--print"], cwd=cwd, env=env, input="", capture_output=True, text=True, timeout=60)
        assert printed.returncode == 0, printed.stdout + printed.stderr
        assert "MP_PHASE_LIVE_READY" in printed.stdout, printed.stdout + printed.stderr
        verify_results(read_snapshots(print_snapshots))
        tui_snapshots = cwd / "tui.jsonl"
        env["PI_PHASE_LIVE_SNAPSHOTS"] = str(tui_snapshots)
        headers = verify_tui(command, env, cwd, tui_snapshots)
        print("MP_PHASE_LIVE_DONE=" + json.dumps({
            "print": "passed", "tui": "passed", "keyboardExpand": "passed", "resize48": "passed", "headers": headers,
        }))


if __name__ == "__main__":
    main()
