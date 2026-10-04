"""Native offline CLI and TUI completion, refusal advice, and empty-loop bounds."""
from __future__ import annotations

import fcntl
import json
import os
import pathlib
import pty
import select
import struct
import subprocess
import tempfile
import termios
import time

from goal_native_tui import terminate_fixture


def main() -> None:
    repo = pathlib.Path(__file__).resolve().parents[3]
    fixture = repo / "packages/goal/tests/goal_completion_fixture.ts"
    for mode in ("complete", "refuse", "empty"):
        for tui in (False, True):
            with tempfile.TemporaryDirectory(prefix="goal-native-complete-") as raw:
                root = pathlib.Path(raw)
                agent = root / "agent"
                agent.mkdir()
                trace = root / "trace.jsonl"
                env = dict(os.environ, PI_CODING_AGENT_DIR=str(agent), TERM="xterm-256color",
                           PI_GOAL_COMPLETION_CASE=mode, PI_GOAL_COMPLETION_TRACE=str(trace))
                command = ["pi", "-ne", "-ns", "-np", "-nc", "--no-session", "-e", str(fixture),
                           "--model", "goal-completion-offline/scripted"]
                output = bytearray()
                if not tui:
                    result = subprocess.run(command + ["--print", "Verify native completion."], cwd=root, env=env,
                                            capture_output=True, timeout=20)
                    assert result.returncode == 0, result.stderr.decode(errors="replace")
                    output.extend(result.stdout)
                else:
                    master, slave = pty.openpty()
                    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
                    child = subprocess.Popen(command, cwd=root, env=env, stdin=slave, stdout=slave, stderr=slave,
                                             start_new_session=True)
                    os.close(slave)

                    def drain(seconds: float) -> None:
                        deadline = time.monotonic() + seconds
                        while time.monotonic() < deadline:
                            if select.select([master], [], [], 0.05)[0]:
                                try:
                                    output.extend(os.read(master, 65536))
                                except OSError:
                                    break

                    try:
                        deadline = time.monotonic() + 10
                        while b"goal_completion_fixture.ts" not in output and time.monotonic() < deadline:
                            drain(0.05)
                        assert b"goal_completion_fixture.ts" in output
                        drain(0.2)
                        os.write(master, b"Verify native completion.\r")
                        deadline = time.monotonic() + 10
                        paths: list[pathlib.Path] = []
                        while time.monotonic() < deadline:
                            drain(0.1)
                            base = root / ".pi/goals"
                            paths = list(base.glob("archived/*/record.json")) if mode == "complete" else list(base.glob("*/record.json"))
                            if paths:
                                record = json.loads(paths[0].read_text())["goal"]
                                if record["status"] == ("complete" if mode == "complete" else "paused"):
                                    break
                        assert paths, output.decode(errors="replace")[-4000:]
                        entries = [json.loads(line) for line in trace.read_text().splitlines()]
                        count = sum(entry["kind"] == "provider" for entry in entries)
                        drain(0.6)
                        later = [json.loads(line) for line in trace.read_text().splitlines()]
                        assert sum(entry["kind"] == "provider" for entry in later) == count, "a stopped or complete goal must not add turns"
                        if mode == "complete":
                            widgets = [entry for entry in later if entry["kind"] == "widget"]
                            assert widgets and widgets[-1]["mounted"] is False, widgets
                            assert b"completed" in output or b"archived" in output
                        else:
                            assert b"resume" in output and (b"missing" in output or b"no work" in output), output.decode(errors="replace")[-10000:]
                    finally:
                        try:
                            terminate_fixture(child)
                        finally:
                            os.close(master)
                    assert child.poll() is not None
                base = root / ".pi/goals"
                paths = list(base.glob("archived/*/record.json")) if mode == "complete" else list(base.glob("*/record.json"))
                assert len(paths) == 1, mode
                record = json.loads(paths[0].read_text())["goal"]
                assert record["status"] == ("complete" if mode == "complete" else "paused"), record
                ledger = [json.loads(line) for line in (paths[0].parent / "ledger.jsonl").read_text().splitlines()]
                if mode == "complete":
                    assert not list(base.glob("*/record.json"))
                    assert sum(entry["type"] == "goal_completed" for entry in ledger) == 1
                    checks = [json.loads(line) for line in trace.read_text().splitlines() if json.loads(line)["kind"] == "check"]
                    assert any("NATIVE_COMPLETION_E2E_PASS" in str(entry) for entry in checks)
                elif mode == "refuse":
                    assert record["completionFailures"] == 3, record
                    assert "independent review" in record["pauseReason"]
                    assert "Run" in record["pauseReason"] and "/goal resume" in record["pauseReason"]
                    assert sum(entry["type"] == "completion_refused" for entry in ledger) == 3
                else:
                    assert record["scheduler"]["idleRuns"] == 3, record
                    assert record["scheduler"]["used"] <= 2, record
                print(f"PASS native {'TUI' if tui else 'CLI'} {mode}")
    print("GOAL_NATIVE_COMPLETION_OK")


if __name__ == "__main__":
    main()
