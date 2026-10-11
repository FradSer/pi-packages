"""Real Pi PTY retry probe; scripted provider, no external model requests."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time

from pi_cli import isolated_pi_command

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
# Reuse the existing test-only synchronized terminal decoder. No Tasks runtime is loaded.
sys.path.insert(0, str(REPO / "packages/tasks/tests"))
from task_terminal_frames import TerminalFrames


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=["retry", "inline", "failed", "provider-error", "runner-error"], default="retry")
    options = parser.parse_args()
    output = options.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fixture = output / "long-fixture.ts"
    source = (PACKAGE / "tests/live-fixture.ts").read_text()
    source = source.replace('../../../tests/e2e/support/scripted.ts', (REPO / 'tests/e2e/support/scripted.ts').as_uri())
    source = source.replace('new URL("./run-fixture.mjs",import.meta.url).href', json.dumps((PACKAGE / 'tests/run-fixture.mjs').as_uri()))
    source = source.replace('Scenario: Works\\nThen value is true', 'Scenario: ' + 'Long scenario ' * 25 + 'SCENARIO_TAIL\\nThen ' + 'value is true ' * 25 + 'CLAUSE_TAIL')
    source = source.replace('  pi.on("agent_before_settle",', '  pi.on("session_start", () => appendFileSync(process.env.PI_E2E_READY_FILE!, "ready"));\n  pi.on("agent_before_settle",')
    fixture.write_text(source)
    if not (output / "node_modules").exists():
        (output / "node_modules").symlink_to(REPO / "node_modules", target_is_directory=True)
    with tempfile.TemporaryDirectory(prefix="e2e-native-tui-") as raw:
        work = Path(raw)
        agent = work / "agent"
        agent.mkdir()
        (agent / "settings.json").write_text(json.dumps({"packages": [str(PACKAGE)], "quietStartup": True, "retry": {"enabled": False}, "compaction": {"enabled": False}}))
        (work / ".e2e").mkdir()
        adapter = work / "adapter.mjs"
        running_marker, release = work / "runner-started", work / "release-runner"
        adapter.write_text('process.stderr.write("RUNNER_DIAGNOSTIC_TAIL");process.exit(1);' if options.case == "runner-error" else (
            'import {watch,writeFileSync,existsSync} from "node:fs";'
            f'await new Promise(resolve=>{{const watcher=watch({json.dumps(str(work))},()=>{{if(existsSync({json.dumps(str(release))})){{watcher.close();resolve();}}}});writeFileSync({json.dumps(str(running_marker))},"ready");}});'
            f'process.argv[2]="unmet"; await import({json.dumps((PACKAGE / "tests/run-fixture.mjs").as_uri())});'
        ))
        (work / ".e2e/runner.json").write_text(json.dumps({"executable": subprocess.check_output(["node", "-p", "process.execPath"], text=True).strip(), "args": ["adapter.mjs"], "adapterFiles": ["adapter.mjs", str(PACKAGE / "tests/run-fixture.mjs")]}))
        (work / "test.feature").write_text("Feature: Test\nScenario: Before\nThen value is true\n")
        (work / "supplied.json").write_text(json.dumps({"run":{"observations":{"value":True}},"checks":[{"clause":1,"path":"value","op":"equals","value":True}]}))
        ready = work / "ready"
        env = {**os.environ, "PI_CODING_AGENT_DIR": str(agent), "PI_E2E_AUTH": "isolated-test-provider", "PI_E2E_CASE": options.case, "PI_E2E_READY_FILE": str(ready), "TERM": "xterm-256color", "PI_OFFLINE": "1"}
        frames = TerminalFrames(80, 700)
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 700, 80, 0, 0))
        child = subprocess.Popen([*isolated_pi_command(), "-ns", "-np", "-nc", "--no-session", "--provider", "e2e-gate-scripted", "--model", "deterministic", "-e", str(fixture), "--tools", "write,e2e_verify,e2e_gate_probe"], cwd=work, env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)

        def wait(predicate) -> None:
            deadline = time.monotonic() + 40
            while not predicate():
                if child.poll() is not None or time.monotonic() > deadline:
                    (output / "failed-frame.txt").write_text("\n".join(frames.display))
                    raise AssertionError("Native TUI did not reach the expected lifecycle state")
                if select.select([master], [], [], 0.05)[0]:
                    data = os.read(master, 65536)
                    frames.feed(data)
                    if b"\x1b[6n" in data:
                        os.write(master, b"\x1b[1;1R")

        try:
            wait(lambda: ready.exists() and frames.count > 0)
            os.write(master, b"Update this feature and verify its e2e acceptance.\r")
            if options.case == "retry":
                wait(lambda: running_marker.exists() and "[e2e] running" in "\n".join(frames.display) and "Running project tests" in "\n".join(frames.display))
                (output / "running-80.txt").write_text("\n".join(frames.display))
                release.write_text("continue")
            wait(lambda: "E2E_REPORT" in "\n".join(frames.display))
            if options.case != "retry":
                wait(lambda: "[e2e] waiting" in "\n".join(frames.display))
            initial = "\n".join(frames.display)
            (output / "default-80.txt").write_text(initial)
            if options.case == "retry":
                os.write(master,b"/e2e test.feature supplied.json\r")
                wait(lambda: "[e2e] needs review" in "\n".join(frames.display) and "caller-supplied" in "\n".join(frames.display))
                slash = "\n".join(frames.display)
                (output / "slash-80.txt").write_text(slash)
                command_body = slash.rsplit("[e2e] needs review",1)[1]
                assert "**Verdict**" not in command_body and "| --- |" not in command_body
            before = frames.count
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 1000, 40, 0, 0))
            frames.resize(40, 1000)
            os.kill(child.pid, signal.SIGWINCH)
            wait(lambda: frames.count > before)
            narrow = "\n".join(frames.display)
            (output / "default-40.txt").write_text(narrow)
            if options.case == "retry":
                assert "[e2e] needs review" in narrow and "caller-supplied" in narrow
                (output / "slash-40.txt").write_text(narrow)
            for text in [initial, narrow]:
                assert "SCENARIO_TAIL" in text
                if options.case != "runner-error":
                    assert "CLAUSE_TAIL" in text
                assert "to expand" not in text
                if options.case == "retry":
                    assert "[e2e] waiting" not in text
                    assert "[e2e] passed" in text and "[e2e] failed" in text
                elif options.case == "runner-error":
                    assert "[e2e] error" in text and "RUNNER_DIAGNOSTIC_TAIL" in text
                elif options.case == "failed":
                    assert "[e2e] failed" in text
                else:
                    assert "[e2e] needs review" in text
                    assert "[e2e] passed" not in text
                    assert ("NO_API_KEY" if options.case == "provider-error" else "caller-supplied") in text
                feedback = text.split("E2E_REPORT", 1)[0]
                assert "**Verdict**" not in feedback and "| --- |" not in feedback
                headers = [line.strip() for line in feedback.splitlines() if line.strip().startswith("[e2e]")]
                assert all(re.fullmatch(r"\[e2e\] (running|passed|failed|needs review|error|continue|waiting)", line) for line in headers), headers
            result = {"runtime": "real Pi PTY", "provider": "scripted", "case": options.case, "widths": [80, 40], "defaultTails": True, "bareHeaders": True, "phaseVisible": options.case == "retry", "frames": frames.count}
            (output / "results.json").write_text(json.dumps(result, indent=2))
            print(json.dumps(result))
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
            os.close(master)


if __name__ == "__main__":
    main()
