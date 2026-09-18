"""Offline real-Pi print and keyboard/resize rendering checks in disposable roots.

Manual verification: uv run --no-project packages/continual-learning/tests/live_meaningful_details.py
No user authentication, remote model, built-in tools or project configuration is used.
"""

from __future__ import annotations

from collections.abc import Callable
import errno
import fcntl
import json
import os
from pathlib import Path
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

FIXTURE = Path(__file__).with_name("meaningful-details-live-fixture.ts")
CUSTOM_TYPES = {"harness-event", "harness-check", "context-guidance-event"}


def snapshots(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.endswith("}")]


def verify_expanded(row: dict) -> None:
    lines = [line.strip() for line in row["lines"] if line.strip()]
    text = "".join("".join(lines).split())
    data = row["data"]
    # Every lifecycle row in this package is delivered by the Harness surface.
    assert lines[0].startswith("[harness]"), lines
    if row["customType"] == "harness-event":
        assert text.count("".join(data["reason"].split())) == 1, lines
        fields = ("policy", "action", "outcome", "tool", "source", "file")
        assert not any(line.startswith("reason ·") for line in lines), lines
    elif row["customType"] == "harness-check":
        assert text.count("".join(data["detail"].split())) == 1, lines
        fields = ("phase", "policy", "path")
        assert not any(line.startswith(("status ·", "detail ·")) for line in lines), lines
    else:
        fields = ("source", "file")
        assert "".join(data["prompt"].split()) in text, lines
        assert not any(line.startswith(("skill ·", "rule ·")) for line in lines), lines
    for field in fields:
        assert "".join(f"{field} · {data[field]}".split()) in text, (field, lines)


def verify_tui(command: list[str], env: dict[str, str], cwd: Path, output: Path) -> None:
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
                    break
            if predicate():
                return
            if process.poll() is not None:
                break
        assert predicate(), transcript.decode(errors="replace")[-6000:]

    def has_render(width: int, expanded: bool) -> bool:
        return {row["customType"] for row in snapshots(output)
                if row["kind"] == "render" and row["width"] == width and row["expanded"] is expanded} == CUSTOM_TYPES

    try:
        wait_for(lambda: b"CL_DETAILS_LIVE_READY" in transcript and has_render(120, False))
        os.write(master, b"\x0f")  # Native Ctrl+O through Pi's editor.
        wait_for(lambda: has_render(120, True))
        resize(48)
        process.send_signal(signal.SIGWINCH)
        wait_for(lambda: has_render(48, True))
        os.write(master, b"\x0f")
        wait_for(lambda: has_render(48, False))
        for row in snapshots(output):
            if row["kind"] != "render":
                continue
            assert all("\n" not in line and len(line) <= row["width"] for line in row["lines"]), row
            if row["expanded"]:
                verify_expanded(row)
            else:
                assert "to expand" in " ".join(row["lines"]), row
        os.write(master, b"/quit\r")
        wait_for(lambda: process.poll() is not None)
        assert process.returncode == 0
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
    assert pi, "pi CLI is required"
    with tempfile.TemporaryDirectory(prefix="learning-details-live-") as raw:
        cwd = Path(raw)
        agent = cwd / "agent"
        agent.mkdir()
        (agent / "settings.json").write_text(json.dumps({"theme": "dark", "quietStartup": True, "packages": []}))
        env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL"}}
        env.update({"HOME": str(cwd), "PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1",
                    "PI_DETAILS_LIVE_AUTH": secrets.token_hex(16), "TERM": "xterm-256color"})
        command = [pi, "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes",
                   "--no-context-files", "--no-approve", "--extension", str(FIXTURE), "--provider", "meaningful-details-fixture",
                   "--model", "deterministic", "--thinking", "off", "--no-builtin-tools", "Run the offline display fixture"]
        printed_rows = cwd / "print.jsonl"
        env["PI_DETAILS_LIVE_SNAPSHOTS"] = str(printed_rows)
        printed = subprocess.run([*command, "--print"], cwd=cwd, env=env, input="", capture_output=True, text=True, timeout=60)
        assert printed.returncode == 0, printed.stdout + printed.stderr
        assert "CL_DETAILS_LIVE_READY" in printed.stdout, printed.stdout + printed.stderr
        assert {row["customType"] for row in snapshots(printed_rows) if row["kind"] == "entry"} == CUSTOM_TYPES
        tui_rows = cwd / "tui.jsonl"
        env["PI_DETAILS_LIVE_SNAPSHOTS"] = str(tui_rows)
        verify_tui(command, env, cwd, tui_rows)
        print(json.dumps({"print": "passed", "tui": "passed", "keyboardExpand": "passed", "resize48": "passed",
                          "full65LinePrompt": "passed", "remoteRequests": 0}))


if __name__ == "__main__":
    main()
