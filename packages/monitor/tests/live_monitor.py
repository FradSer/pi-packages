"""Explicit zero-network native Pi 1.1.0 acceptance. Run with uv run python this_file.

All project, settings, trace, and terminal output stay in an isolated temporary
folder. Each Pi child has an external 35 second watchdog and group cleanup.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import pty
import shutil
from contextlib import contextmanager
import select
import signal
import struct
import subprocess
import tempfile
import termios
import time

REPO = Path(__file__).resolve().parents[3]
PI_CLI = REPO / "node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js"


def pi_command() -> list[str]:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for native Pi acceptance"
    return [node, str(PI_CLI)]


def private_env(root: Path) -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", ""), "HOME": str(root),
            "PI_CODING_AGENT_DIR": str(root / "agent"), "PI_OFFLINE": "1",
            "PI_TELEMETRY": "0", "TERM": "xterm-256color"}


@contextmanager
def probe_directory(prefix: str):
    # Optional evidence retention uses the existing probes, not another runner.
    parent = os.environ.get("MONITOR_ACCEPTANCE_OUTPUT")
    if parent:
        Path(parent).mkdir(parents=True, exist_ok=True)
        yield tempfile.mkdtemp(prefix=prefix, dir=parent)
    else:
        with tempfile.TemporaryDirectory(prefix=prefix) as raw:
            yield raw


FIXTURE = REPO / "packages/monitor/tests/native-fixture.ts"


def stop(child: subprocess.Popen) -> None:
    """Terminate only this probe's isolated process group and reap its child."""
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=3)


def setup(root: Path, case: str) -> tuple[list[str], dict[str, str], Path]:
    agent = root / "agent"
    agent.mkdir(exist_ok=True)
    trace = root / "trace.jsonl"
    args = pi_command() + ["--offline", "--no-approve", "--no-builtin-tools", "-ne", "-ns", "-np", "-nc", "--no-session", "-e", str(FIXTURE), "--model", "monitor-offline/scripted"]
    env = {**private_env(root), "PI_MONITOR_NATIVE_TRACE": str(trace), "PI_MONITOR_NATIVE_CASE": case}
    return args, env, trace


def read_trace(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line]


def assert_transport(trace: list[dict], case: str, interactive: bool) -> None:
    requests = [item for item in trace if item["kind"] == "request"]
    assert len(requests) == 2, f"unexpected model requests: {len(requests)}"
    assert "fixture_foreign" in requests[1]["activeTools"], "terminal cleanup displaced the foreign tool"
    assert "monitor_stop" not in requests[1]["activeTools"], "terminal cleanup left monitor_stop active"
    result_content = [message.get("content") for message in requests[1]["messages"] if message["role"] != "assistant"]
    assert "PRIVATE_PROGRESS" not in json.dumps(result_content), "progress leaked to model context"
    sends = [item for item in trace if item["kind"] == "send" and item["message"]["customType"] == "monitor-result"]
    starts = [item for item in trace if item["kind"] == "tool_result" and item["event"]["toolName"] == "monitor_start"]
    assert len(starts) == 1, starts
    assert "fixture_foreign" in starts[0]["activeTools"], "monitor tool disclosure displaced the foreign tool"
    if interactive and case == "standalone":
        assert len(sends) == 1, sends
        assert sends[0]["message"]["details"]["monitorId"], "custom terminal missing monitor identity"
        assert "result" not in starts[0]["event"]["details"], "standalone interactive call should acknowledge intent"
        assert requests[1]["at"] >= sends[0]["at"], "model resumed before terminal notification"
    else:
        assert not sends, "synchronous terminal produced a duplicate wake"
        assert starts[0]["event"]["details"]["result"]["status"] == "success", starts
        assert requests[1]["at"] >= starts[0]["at"], "model resumed before synchronous terminal"


def print_probe(mode: str) -> None:
    with probe_directory(prefix="monitor-native-print-") as raw:
        root = Path(raw)
        args, env, trace = setup(root, "standalone")
        child = subprocess.Popen(args + ["--print", "--mode", mode, "Verify offline monitor."], cwd=root, env=env,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            stdout, stderr = child.communicate(timeout=35)
            (root / "stdout.bin").write_bytes(stdout)
            (root / "stderr.bin").write_bytes(stderr)
            assert child.returncode == 0, stderr.decode(errors="replace")
            assert b"MONITOR_NATIVE_READY" in stdout, stdout.decode(errors="replace")
            assert_transport(read_trace(trace), "standalone", False)
        finally:
            stop(child)
            stdout, stderr = child.communicate()
            (root / "stdout.bin").write_bytes(stdout)
            (root / "stderr.bin").write_bytes(stderr)
    print(f"MONITOR_NATIVE_{mode.upper()}_OK")


def rpc_probe(case: str) -> None:
    with probe_directory(prefix="monitor-native-rpc-") as raw:
        root = Path(raw)
        args, env, trace = setup(root, case)
        child = subprocess.Popen(args + ["--mode", "rpc"], cwd=root, env=env, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        output = bytearray()
        deadline = time.monotonic() + 35
        try:
            assert child.stdin is not None and child.stdout is not None
            child.stdin.write(b'{"id":"native-prompt","type":"prompt","message":"Verify offline monitor."}\n')
            child.stdin.flush()
            while time.monotonic() < deadline:
                if select.select([child.stdout], [], [], 0.05)[0]:
                    chunk = os.read(child.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    output.extend(chunk)
                if b"MONITOR_NATIVE_READY" in output and len([r for r in read_trace(trace) if r["kind"] == "request"]) == 2:
                    break
            assert b"MONITOR_NATIVE_READY" in output, output.decode(errors="replace")[-4000:]
            assert_transport(read_trace(trace), case, True)
        finally:
            stop(child)
            (root / "stdout.bin").write_bytes(output)
            assert child.stderr is not None
            (root / "stderr.bin").write_bytes(child.stderr.read())
    print(f"MONITOR_NATIVE_RPC_{case.upper()}_OK")


def tui_probe(columns: int, rows: int, snapshot_path: Path | None = None, case: str = "tui") -> None:
    with probe_directory(prefix="monitor-native-tui-") as raw:
        root = Path(raw)
        args, env, trace = setup(root, case)
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
        child = subprocess.Popen(args, cwd=root, env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        output = bytearray()
        watchdog = time.monotonic() + 35

        def drain(seconds: float) -> None:
            until = min(watchdog, time.monotonic() + seconds)
            while time.monotonic() < until:
                if select.select([master], [], [], 0.05)[0]:
                    try:
                        output.extend(os.read(master, 65536))
                    except OSError:
                        return

        def send(key: bytes) -> None:
            os.write(master, key)
            drain(0.3)

        try:
            until = min(watchdog, time.monotonic() + 10)
            while not any(item["kind"] == "session" for item in read_trace(trace)) and time.monotonic() < until:
                drain(0.1)
            assert any(item["kind"] == "session" for item in read_trace(trace)), output.decode(errors="replace")[-4000:]
            send(b"Verify offline monitor.\r")
            until = min(watchdog, time.monotonic() + 8)
            while len([item for item in read_trace(trace) if item["kind"] == "request"]) < 2 and time.monotonic() < until:
                drain(0.1)
            assert len([item for item in read_trace(trace) if item["kind"] == "request"]) == 2, "offline task did not settle"
            drain(0.2)
            send(b"/monitor\r")
            until = min(watchdog, time.monotonic() + 4)
            frames = [item for item in read_trace(trace) if item["kind"] == "frame"]
            while not frames and time.monotonic() < until:
                drain(0.1)
                frames = [item for item in read_trace(trace) if item["kind"] == "frame"]
            assert frames, "native monitor console did not open"
            values = case == "tui-values"
            tail = "PAYLOAD_END" if values else "diagnostic-79"
            assert not any(tail in line for line in frames[-1]["lines"]), "values/output must start folded"
            send(b"v" if values else b"\r")
            send(b"\x1b[6~")
            send(b"\x1b[F")
            frames = [item for item in read_trace(trace) if item["kind"] == "frame"]
            assert all(len(frame["lines"]) <= frame["rows"] for frame in frames), frames
            assert tail in "".join(frames[-1]["lines"]).replace(" ", ""), f"End cannot reach tail: {frames[-1]}"
            assert any("? help" in line for line in frames[-1]["lines"]), "help action must survive narrow layout"
            send(b"\x1b[27;2;63~")
            send(b"\x1b[F")
            frames = [item for item in read_trace(trace) if item["kind"] == "frame"]
            assert any("stop all" in line for line in frames[-1]["lines"]), "help must disclose stop-all even in narrow terminals"
            send(b"?")
            if snapshot_path is not None:
                snapshot_path.write_text(json.dumps(frames, ensure_ascii=False, indent=2) + "\n")
            before = len(frames)
            send(b"q")
            send(b"/monitor\r")
            assert len([item for item in read_trace(trace) if item["kind"] == "frame"]) > before, "q did not return to the editor"
            send(b"\x1b")
            keys = [item["key"] for item in read_trace(trace) if item["kind"] == "key"]
            assert all(key in keys for key in ["v" if values else "\r", "\x1b[6~", "\x1b[F", "q", "\x1b"]), keys
        finally:
            try:
                stop(child)
            finally:
                (root / "terminal.ansi").write_bytes(output)
                (root / "terminal.json").write_text(json.dumps({"columns": columns, "rows": rows, "case": case}) + "\n")
                os.close(master)
    print(f"MONITOR_NATIVE_TUI_{columns}x{rows}_{case}_OK")


def main() -> None:
    with probe_directory(prefix="monitor-native-version-") as raw:
        root = Path(raw)
        (root / "agent").mkdir(mode=0o700)
        version = subprocess.run(pi_command() + ["--version"], cwd=root, env=private_env(root), capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        (root / "version.txt").write_text(version + "\n")
    assert version == "1.1.0", f"native acceptance requires Pi 1.1.0, got {version}"
    print(f"MONITOR_NATIVE_PI_{version}")
    print_probe("text")
    print_probe("json")
    rpc_probe("standalone")
    rpc_probe("mixed")
    for columns, rows in [(80, 24), (40, 6), (20, 4), (120, 40)]:
        tui_probe(columns, rows)
    tui_probe(80, 24, case="tui-values")
    tui_probe(40, 6, case="tui-values")


if __name__ == "__main__":
    main()
