"""Run offline real-Pi print and PTY checks in a temporary home, without user auth.

Manual verification: uv run --no-project packages/matt-pocock/tests/live/live_smoke.py
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

from live_pty import base_env

FIXTURE = Path(__file__).with_name("lifecycle-live-fixture.ts")
EXPECTED = (
    "started · Reproducing & Diagnostics",
    "event · Reproducing & Diagnostics completed",
    "event · Implementation",
    "event · Code Review",
    "event · Code Review completed",
    "started · Architecture Survey",
    "event · Implementation cancelled",
    "started · Diagnosing Bugs",
    "started · Writing For Agents · Skill Mechanics",
)


def read_snapshots(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.endswith("}")]


def verify_results(rows: list[dict], has_ui: bool = False) -> None:
    results = [row for row in rows if row["kind"] == "result"]
    assert len(results) == 15, results
    assert all(not row["isError"] for row in results), results
    assert results[1]["details"]["subject"] == "Reproducing & Diagnostics completed"
    assert results[5]["details"]["subject"] == "Code Review completed"
    assert results[8]["details"]["subject"] == "Implementation cancelled"
    assert results[1]["details"]["state"]["route"] == "hard-bug"
    assert results[1]["details"]["state"]["phase"] == "feedback-loop"
    assert results[1]["details"]["state"]["status"] == "completed"
    assert results[8]["details"]["state"]["status"] == "cancelled"
    questions = [row for row in results if row["tool"] == "matt_pocock_ask"]
    assert questions[0]["details"] == ({
        "answer": "A", "is_custom": False, "timed_out": True,
        "pending": False, "source": "timeout_recommended",
    } if has_ui else {"pending": True, "source": "no_ui"})
    assert questions[1]["details"] == ({
        "pending": True, "timed_out": False, "source": "cancelled",
    } if has_ui else {"pending": True, "source": "no_ui"})


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

    def has_message(width: int) -> bool:
        return any(row["kind"] == "message" and row["width"] == width and "[matt pocock]" in "\n".join(row["lines"])
                   for row in read_snapshots(snapshots))

    try:
        wait_for(lambda: b"Fixture cancel decision" in transcript)
        os.write(master, b"\x1b")  # Escape cancels a real Pi selector with a recommendation.
        wait_for(lambda: b"MP_PHASE_LIVE_READY" in transcript and has_render(120, False))
        rows = read_snapshots(snapshots)
        verify_results(rows, has_ui=True)
        headers = [line.strip() for row in rows if row["kind"] == "render" and not row["expanded"]
                   for line in row["lines"] if "[matt pocock]" in line]
        for expected in EXPECTED:
            assert any(f"[matt pocock] {expected}" in line for line in headers), (expected, headers)
        assert all("hard-bug" not in line and "Hard Bug Diagnosis" not in line and "Codebase Architecture" not in line
                   for line in headers), headers
        os.write(master, b"\x0f")  # Actual Ctrl+O through Pi's editor.
        # Pi renders rows sequentially; one expanded row does not mean the entire
        # transcript has been redrawn yet.
        wait_for(lambda: has_render(120, True))
        expanded = "\n".join(line for row in read_snapshots(snapshots)
                             if row["kind"] == "render" and row["expanded"] for line in row["lines"])
        # No Matt Pocock row hides a field body, so expansion adds nothing.
        assert "reason · Offline fixture finished" in expanded
        assert "route ·" not in expanded
        assert "phase ·" not in expanded
        assert "action ·" not in expanded
        assert "procedure-source" not in expanded
        for row in read_snapshots(snapshots):
            if row["kind"] != "render" or row["width"] != 120:
                continue
            details = row.get("details") or {}
            text = "\n".join(row["lines"])
            assert "to expand" not in text, row
            if details.get("action") == "cancel":
                assert text.count("reason · Offline fixture finished") == 1, row
        resize(48)
        process.send_signal(signal.SIGWINCH)
        wait_for(lambda: has_render(48, True))
        os.write(master, b"\x0f")
        wait_for(lambda: has_render(48, False))
        for row in read_snapshots(snapshots):
            if row["kind"] == "render":
                assert all("\n" not in line and len(line) <= row["width"] for line in row["lines"]), row
        # `/matt-pocock <route> [task]` delivers one impeccable-style block, never a user message.
        resize(120)
        process.send_signal(signal.SIGWINCH)
        wait_for(lambda: has_render(120, False))
        os.write(master, b"\x1b[200~/matt-pocock hard-bug fix the login redirect\x1b[201~\r")
        wait_for(lambda: has_message(120))
        procedure = [row for row in read_snapshots(snapshots) if row["kind"] == "message" and row["width"] == 120][-1]
        content = [line.strip() for line in procedure["lines"][1:-1]]
        assert procedure["customType"] == "matt-pocock-procedure", procedure
        assert content == ["[matt pocock] started", "", "fix the login redirect"], procedure["lines"]
        assert procedure["details"]["route"] == "hard-bug", procedure
        assert procedure["details"]["phase"] == "feedback-loop", procedure
        assert procedure["details"]["status"] == "active", procedure
        assert procedure["details"]["request"] == "fix the login redirect", procedure
        assert procedure["userMessageBg"] in "\n".join(procedure["raw"]), "the block is not on pi's user-message band"
        assert "to expand" not in "\n".join(procedure["lines"]), procedure
        assert "procedure/" not in "\n".join(procedure["lines"]), procedure
        assert all("\n" not in line and len(line) <= 120 for line in procedure["lines"]), procedure
        os.write(master, b"/quit\r")
        wait_for(lambda: process.poll() is not None)
        assert process.returncode == 0
        # The model-facing prompt never reaches the terminal; the block row stands in for it.
        rendered = transcript.decode(errors="replace")
        for leak in ("Matt Pocock workflow procedure", "User target/request"):
            assert leak not in rendered, rendered[-3000:]
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
        env = base_env()
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
            "print": "passed", "tui": "passed", "questionTimeout": "passed", "questionEscape": "passed", "keyboardExpand": "passed", "resize48": "passed", "headers": headers,
        }))


if __name__ == "__main__":
    main()
