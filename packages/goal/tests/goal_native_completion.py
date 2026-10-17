"""CLI and rendered terminal acceptance for the simplified Goal runtime.

Run: uv run --no-project --with pyte python packages/goal/tests/goal_native_completion.py
Supports GOAL_PI_BIN and GOAL_VERIFY_ROOT for isolated packed Docker installs.
"""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import tempfile
import termios
import time
from goal_native_frames import TerminalFrames
from goal_native_tui import terminate_fixture


def goal_records(agent: Path) -> list[Path]:
    """Every goal record this run wrote.

    State lives at `<agent>/goals/<project key>/<goal id>/record.json`, so a probe
    reads it by globbing rather than by rebuilding the project key, and a run that
    never writes into its working directory is provable from the absence of one.
    """
    return sorted((agent / "goals").glob("*/*/record.json"))


def goal_of(path: Path) -> dict:
    return json.loads(path.read_text())["goal"]


def assert_completion_frame(lines: list[str], mode: str) -> None:
    text = "\n".join(lines)
    targets = {"complete": "[goal] completed", "refuse": "[goal] not met", "empty": "Goal waiting", "error": "[goal] check failed", "blocked": "Goal blocked", "cancel": "Goal paused"}
    assert targets[mode] in text, text[-5000:]
    assert "Archived under" not in text and "ledger events" not in text
    if mode == "refuse":
        assert "[goal] paused" not in text and "Three consecutive completion" not in text
    if mode == "error":
        assert "Offline provider unavailable" in text and "[goal] failed · check failed" not in text


def main() -> None:
    repo = Path(os.environ.get("GOAL_VERIFY_ROOT", Path(__file__).resolve().parents[3]))
    fixture = repo / "packages/goal/tests/goal_completion_fixture.ts"
    cases = os.environ.get("GOAL_CASES", "complete,refuse,empty,error,blocked,long,cancel").split(",")
    for mode in cases:
        for tui in (False, True):
            if mode == "cancel" and not tui:
                continue
            with tempfile.TemporaryDirectory(prefix="goal-native-simple-") as raw:
                root = Path(raw); agent = root / "agent"; agent.mkdir(); trace = root / "trace.jsonl"
                release = root / "release"
                env = dict(os.environ, PI_CODING_AGENT_DIR=str(agent), TERM="xterm-256color", PI_OFFLINE="1", PI_GOAL_COMPLETION_CASE=mode,
                           PI_GOAL_COMPLETION_TRACE=str(trace), PI_GOAL_CHECK_RELEASE=str(release))
                autoload = os.environ.get("PI_GOAL_AUTOLOAD") == "1"
                if autoload:
                    (agent / "settings.json").write_text(json.dumps({"packages":[os.environ["GOAL_INSTALLED_PATH"]]}))
                command = [os.environ.get("GOAL_PI_BIN", "pi"), *([] if autoload else ["-ne"]), "-ns", "-np", "-nc", "--no-session", "-e", str(fixture), "--model", "goal-completion-offline/scripted"]
                def entries() -> list[dict]:
                    return [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
                if not tui:
                    result = subprocess.run(command + ["--print", "Verify Goal."], cwd=root, env=env, capture_output=True, timeout=30)
                    assert result.returncode == 0, result.stderr.decode(errors="replace")
                else:
                    master, slave = pty.openpty(); fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 240, 80, 0, 0))
                    child = subprocess.Popen(command, cwd=root, env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
                    os.close(slave); frames = TerminalFrames(80, 240); raw_output = bytearray()
                    def drain() -> None:
                        if select.select([master], [], [], 0.05)[0]:
                            data = os.read(master, 65536); raw_output.extend(data); frames.feed(data)
                    def until(predicate, seconds: float = 20) -> None:
                        deadline = time.monotonic() + seconds
                        while not predicate():
                            assert child.poll() is None, raw_output.decode(errors="replace")[-5000:]
                            assert time.monotonic() < deadline, raw_output.decode(errors="replace")[-5000:]
                            drain()
                    try:
                        until(lambda: any(e["kind"] == "ready" for e in entries()) and frames.count > 0)
                        os.write(master, b"Verify Goal.\r")
                        if mode == "cancel":
                            until(lambda: any(e["kind"] == "checking" for e in entries()))
                            until(lambda: "Evaluating the objective and recorded evidence" in "\n".join(frames.display))
                            assert "checking..." not in "\n".join(frames.display), "the replaced heading must not survive"
                            os.write(master, b"/goal pause\r")
                            until(lambda: "Goal paused" in "\n".join(frames.display))
                            release.touch()
                        else:
                            until(lambda: any(e["kind"] == "settled" for e in entries()))
                        if mode == "long":
                            until(lambda: all(marker in "\n".join(frames.display) for marker in ("GOAL_REQUIREMENT_END", "GOAL_CONTRACT_END")))
                            assert "ctrl+o to expand" not in "\n".join(frames.display)
                            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 360, 40, 0, 0)); frames.resize(40, 360)
                            os.kill(child.pid, __import__("signal").SIGWINCH)
                            until(lambda: all(marker in "\n".join(frames.display) for marker in ("GOAL_REQUIREMENT_END", "GOAL_CONTRACT_END")))
                        else:
                            target = {"complete":"[goal] completed", "refuse":"[goal] not met", "empty":"Goal waiting", "error":"[goal] check failed", "blocked":"Goal blocked", "cancel":"Goal paused"}[mode]
                            until(lambda: target in "\n".join(frames.display)); assert_completion_frame(frames.display, mode)
                        # Exercise durable command rows and clear against the real terminal.
                        if mode in ("empty", "long"):
                            os.write(master, b"/goal pause\r"); until(lambda: "[goal] paused" in "\n".join(frames.display))
                            os.write(master, b"/goal\r"); until(lambda: "Objective:" in "\n".join(frames.display))
                            os.write(master, b"/goal resume\r"); until(lambda: "[goal] resumed" in "\n".join(frames.display))
                            until(lambda: len([e for e in entries() if e["kind"] == "settled"]) >= 2)
                            os.write(master, b"/goal clear\r"); until(lambda: "[goal] cleared" in "\n".join(frames.display))
                            assert goal_of(goal_records(agent)[0])["status"] == "complete", "clearing keeps the record"
                    finally:
                        terminate_fixture(child); os.close(master)
                rows = entries(); checks = [e for e in rows if e["kind"] == "check"]
                assert len(checks) == {"complete":1,"refuse":3,"empty":0,"error":1,"blocked":0,"long":0,"cancel":1}[mode], (mode, rows)
                # A goal's record is never deleted: a completed or cleared goal keeps it
                # with its terminal status, and no state is written into the project.
                assert not (root / ".pi").exists(), "no goal state is written into the working directory"
                records = goal_records(agent)
                if mode == "complete" or tui and mode in ("empty", "long"):
                    assert len(records) == 1, mode
                    assert goal_of(records[0])["status"] == "complete", mode
                else:
                    assert len(records) == 1, mode
                    record = goal_of(records[0])
                    assert record["status"] == {"blocked":"blocked", "cancel":"paused"}.get(mode,"active"), record
                    if mode in ("empty","error","refuse","long"):
                        assert record["autoContinue"] is False, record
                print(f"PASS native {'TUI' if tui else 'CLI'} {mode}", flush=True)
    print("GOAL_NATIVE_SIMPLIFIED_OK")


if __name__ == "__main__":
    main()
