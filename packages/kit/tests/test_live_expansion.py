"""Real Pi print/PTY verification with offline transport and an isolated home."""

from __future__ import annotations

import errno
import fcntl
import json
import os
import pty
import re
import secrets
import select
import shutil
import signal
import struct
import subprocess
import termios
import time
from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def live_command(tmp_path: Path) -> tuple[list[str], dict[str, str], Path]:
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("Pi CLI is required for native lifecycle verification")
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "settings.json").write_text(json.dumps({"theme": "dark", "quietStartup": True}))
    snapshots = tmp_path / "renders.jsonl"
    widgets = tmp_path / "widgets.jsonl"
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update({"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(agent_dir), "PI_OFFLINE": "1",
                "PI_EXPANSION_AUTH": secrets.token_hex(16), "PI_EXPANSION_SNAPSHOTS": str(snapshots),
                "PI_WIDGET_SNAPSHOTS": str(widgets), "TERM": "xterm-256color"})
    command = [pi, "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes",
               "--no-context-files", "--no-approve", "--extension", str(Path(__file__).with_name("live-expansion-fixture.ts")),
               "--provider", "kit-expansion-fixture", "--model", "deterministic", "--thinking", "off",
               "--no-builtin-tools", "Run the offline lifecycle expansion fixture"]
    return command, env, snapshots


def test_native_print_and_host_mouse_expansion(live_command: tuple[list[str], dict[str, str], Path], tmp_path: Path) -> None:
    command, env, _ = live_command
    result = subprocess.run([*command, "--print"], cwd=tmp_path, env=env, input="", text=True, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    output = result.stdout + result.stderr
    assert "KIT_NATIVE_EXPANSION_OK" in output, output
    assert "KIT_NATIVE_MOUSE_OK" in output or "KIT_NATIVE_MOUSE_UNAVAILABLE" in output, output
    assert "KIT_EXPANSION_READY" in result.stdout, result.stdout + result.stderr
    assert "AssertionError" not in result.stderr


def test_native_tui_hints_keyboard_and_width_changes(live_command: tuple[list[str], dict[str, str], Path], tmp_path: Path) -> None:
    command, env, snapshots = live_command
    master, slave = pty.openpty()
    transcript = bytearray()

    def resize(width: int) -> None:
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 40, width, 0, 0))

    def renders() -> list[dict]:
        if not snapshots.exists():
            return []
        return [json.loads(line) for line in snapshots.read_text().splitlines() if line.endswith("}")]

    def has_all(width: int, expanded: bool) -> bool:
        return {row["kind"] for row in renders() if row["width"] == width and row["expanded"] is expanded} == {
            "short", "empty", "title", "summary", "details",
        }

    resize(90)
    process = subprocess.Popen(command, cwd=tmp_path, env=env, stdin=slave, stdout=slave, stderr=slave)
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
                if predicate():
                    return
                break
        raise AssertionError(transcript.decode(errors="replace")[-6000:])

    try:
        wait_for(lambda: b"KIT_EXPANSION_READY" in transcript and has_all(90, False))
        os.write(master, b"\x0f")
        wait_for(lambda: has_all(90, True))
        resize(48)
        process.send_signal(signal.SIGWINCH)
        wait_for(lambda: has_all(48, True))
        os.write(master, b"\x0f")
        wait_for(lambda: has_all(48, False))
        resize(240)
        process.send_signal(signal.SIGWINCH)
        wait_for(lambda: has_all(240, False))
        resize(48)
        process.send_signal(signal.SIGWINCH)
        wait_for(lambda: has_all(48, False))
        records = renders()
        assert all(row["bounded"] for row in records)
        assert all("MODEL_ONLY_CONTENT" not in "\n".join(row["lines"]) for row in records)
        for width in (48, 90, 240):
            for kind in ("short", "empty", "title", "summary", "details"):
                row = next(row for row in reversed(records) if row["width"] == width and row["kind"] == kind and not row["expanded"])
                expected_hint = kind == "details" or (kind in ("title", "summary") and width < 240)
                assert ("ctrl+o to expand" in "\n".join(row["lines"])) is expected_hint, row
        for kind, last_word in (("title", "evidence-13"), ("summary", "answer-15")):
            row = next(row for row in records if row["width"] == 48 and row["kind"] == kind and row["expanded"])
            assert last_word in "\n".join(row["lines"]), row
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


def test_native_tui_renders_both_canonical_activity_rows(live_command: tuple[list[str], dict[str, str], Path], tmp_path: Path) -> None:
    command, env, _ = live_command
    widgets = tmp_path / "widgets.jsonl"
    master, slave = pty.openpty()
    transcript = bytearray()

    def resize(width: int) -> None:
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 40, width, 0, 0))

    def rows() -> list[dict]:
        if not widgets.exists():
            return []
        return [json.loads(line) for line in widgets.read_text().splitlines() if line.endswith("}")]

    def latest_rows() -> dict[str, dict]:
        # The host may render at its startup width before the resize lands, so
        # assert on the newest row per key instead of pinning one width.
        latest: dict[str, dict] = {}
        for row in rows():
            latest[row["key"]] = row
        return latest

    def screen_text() -> str:
        return re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", bytes(transcript)).decode(errors="replace")

    def both_rows_on_screen() -> bool:
        """Both widget rows must be rendered *and* drained from the PTY: the
        snapshot file is written by the fixture, so it can lead the terminal."""
        if set(latest_rows()) != {"kit-widget-plain", "kit-widget-markdown"}:
            return False
        screen = screen_text()
        return (
            "researcher · **Scanning** `rg` output" in screen
            and re.search(r"researcher · Scanning rg output", screen) is not None
        )

    resize(90)
    process = subprocess.Popen(command, cwd=tmp_path, env=env, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)

    def wait_for(predicate: Callable[[], bool]) -> None:
        deadline = time.monotonic() + 60
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
                if predicate():
                    return
                break
        raise AssertionError(transcript.decode(errors="replace")[-6000:])

    try:
        wait_for(both_rows_on_screen)
        records = latest_rows()
        assert all(row["bounded"] for row in records.values()), records
        # Both rows carry the shared identity and the same activity text; only
        # the requested format differs, and the spinner frame is free to move.
        for key, row in records.items():
            assert len(row["lines"]) == 1, row
            assert re.match(r"^ . researcher · ", row["lines"][0]), (key, row)
        plain = records["kit-widget-plain"]["lines"][0]
        markdown = records["kit-widget-markdown"]["lines"][0]
        assert "**Scanning** `rg` output" in plain, plain
        assert "Scanning rg output" in markdown, markdown
        assert "**" not in markdown and "`" not in markdown, markdown
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
