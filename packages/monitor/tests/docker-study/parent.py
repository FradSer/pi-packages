"""One native parent-model monitor selection and TUI repaint in a PTY."""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import pty
import signal
import struct
import subprocess
import sys
import termios

def wait_for(master: int, process: subprocess.Popen[bytes], transcript: bytearray,
             predicate, timeout: float = 30) -> None:
    import errno
    import select
    import time
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

PROMPT = ("Call monitor_start once with description 'receipt check', command "
    "\"printf 'DONE_HY4\\\\n'\", and result_pattern 'DONE_HY4'. Then finish with "
    "MP_PARENT_DONE. Do not call any other tool, do not edit files, and do not poll.")


def main() -> None:
    command = ["pi", "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates",
        "--no-themes", "--no-context-files", "--no-approve",
        "-e", "/opt/study/packages/monitor/index.ts",
        "--model", "magpie-hy4/hunyuan-eval/hy4-dev", "--thinking", "off",
        "--tools", "read,monitor_start", PROMPT]
    result: dict[str, object] = {"prompt": PROMPT, "command": command}
    master, slave = pty.openpty()
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
    transcript = bytearray()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(command, cwd="/work", env=dict(os.environ),
            stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        slave = -1

        def text() -> str:
            return transcript.decode(errors="replace")

        def done() -> bool:
            return "MP_PARENT_DONE" in text() and "[monitor]" in text()

        wait_for(master, process, transcript, done, timeout=180)
        Path("/results/parent-collapsed.txt").write_text(text())
        before = len(transcript)
        os.write(master, b"\x0f")
        wait_for(master, process, transcript, lambda: len(transcript) > before, timeout=20)
        result["expandRepaintObserved"] = True
        before = len(transcript)
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 48, 0, 0))
        process.send_signal(signal.SIGWINCH)
        wait_for(master, process, transcript, lambda: len(transcript) > before, timeout=20)
        result["resizeRepaintObserved"] = True
        result["markerObserved"] = done()
        result["monitorRowObserved"] = "[monitor]" in text()
    except BaseException as error:
        result["markerObserved"] = False
        result["error"] = str(error)[-1000:]
    finally:
        if slave >= 0:
            os.close(slave)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        os.close(master)
        Path("/results/parent-tui.txt").write_text(transcript.decode(errors="replace"))
        Path("/results/parent-tui.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
