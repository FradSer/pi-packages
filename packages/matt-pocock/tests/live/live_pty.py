"""Small helpers shared by the Pi v1.0 PTY fixtures."""
from __future__ import annotations

import errno
import fcntl
import json
import os
import pty
import select
import struct
import subprocess
import termios
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path


def base_env() -> dict[str, str]:
    """Keep process/terminal settings without inheriting provider credentials."""
    allowed = {
        "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TERM", "COLORTERM",
        "CI", "SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY", "USER", "LOGNAME", "TZ",
        "__CF_USER_TEXT_ENCODING", "SYSTEMROOT", "WINDIR", "PATHEXT",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def isolated_env(root: Path, *, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    agent = root / "agent"
    agent.mkdir(exist_ok=True)
    (agent / "settings.json").write_text(json.dumps({"theme": "dark", "quietStartup": True}))
    env = base_env()
    env.update({
        "HOME": str(root),
        "PI_CODING_AGENT_DIR": str(agent),
        "PI_OFFLINE": "1",
        "TERM": "xterm-256color",
    })
    if extra:
        env.update(extra)
    return env


def pi_command(pi: str, fixture: Path, provider: str, prompt: str) -> list[str]:
    return [
        pi, "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates",
        "--no-themes", "--no-context-files", "--no-approve", "--extension", str(fixture),
        "--provider", provider, "--model", "deterministic", "--thinking", "off",
        "--no-builtin-tools", prompt,
    ]


def wait_for(
    master: int,
    process: subprocess.Popen[bytes],
    transcript: bytearray,
    predicate: Callable[[], bool],
    timeout: float = 30,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if select.select([master], [], [], 0.05)[0]:
            try:
                transcript.extend(os.read(master, 65536))
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                break
        if predicate():
            return
        if process.poll() is not None:
            break
    if predicate():
        return
    raise AssertionError(transcript.decode(errors="replace")[-8000:])


@contextmanager
def live_pi(
    command: list[str], *, cwd: Path, env: Mapping[str, str],
    size: tuple[int, int] | None = None, capture: Path | None = None,
) -> Iterator[tuple[int, subprocess.Popen[bytes], bytearray]]:
    master, slave = pty.openpty()
    if size is not None:
        set_size(slave, *size)
    process = subprocess.Popen(command, cwd=cwd, env=dict(env), stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    transcript = bytearray()
    try:
        yield master, process, transcript
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        # Drain what the terminal already produced before the capture is written.
        while select.select([master], [], [], 0.05)[0]:
            try:
                chunk = os.read(master, 65536)
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                break
            if not chunk:
                break
            transcript.extend(chunk)
        os.close(master)
        if capture is not None:
            capture.parent.mkdir(parents=True, exist_ok=True)
            capture.write_bytes(bytes(transcript))


def set_size(fd: int, columns: int, rows: int) -> None:
    """Set a live PTY size; the kernel signals the resize to the child component."""
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))


def drain(master: int, transcript: bytearray) -> None:
    """Read everything the terminal has already produced, without waiting."""
    while select.select([master], [], [], 0)[0]:
        try:
            chunk = os.read(master, 65536)
        except OSError as error:
            if error.errno != errno.EIO:
                raise
            return
        if not chunk:
            return
        transcript.extend(chunk)
