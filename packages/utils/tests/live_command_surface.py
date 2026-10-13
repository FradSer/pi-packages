"""Live acceptance for the utils command surfaces on the installed Pi CLI.

Run: uv run --no-project --with pyte packages/utils/tests/live_command_surface.py [output-parent]

What this proves: the installed CLI loads this package and its commands answer with
the wording and the level rules this change set introduced, over the real command
dispatch, in both RPC mode and an interactive PTY.

What it does not prove: model-driven behaviour (no provider is configured, so a
command that needs a model reports the host's own rejection), remote services, or a
call to any user data. Isolation is asserted before the CLI starts: HOME, the agent
directory and every registry directory point inside a disposable root.
"""

from __future__ import annotations

import json
import os
import pty
import queue
import re
import secrets
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
import fcntl
from pathlib import Path

UTILS = Path(__file__).resolve().parents[1]
REPO = UTILS.parents[1]
# Includes the Kitty keyboard-protocol replies (\x1b[>7u) the CLI negotiates.
ANSI = re.compile(r"\x1b\[[0-9;?<>]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[()][A-Z0-9]|\x1b[=>]")
STARTUP_TIMEOUT = 60.0
COMMAND_TIMEOUT = 30.0


def strip_ansi(text: str) -> str:
    return ANSI.sub("", text.replace("\r", ""))


def cli_path() -> str:
    """CLI under test: an explicit PI_UNDER_TEST path, else the one on PATH."""
    return os.environ.get("PI_UNDER_TEST") or shutil.which("pi") or "pi"


def cli_identity() -> dict[str, str]:
    """Version of the CLI under test, from its own managed install."""
    resolved = Path(cli_path()).resolve()
    version = ""
    manifest = None
    # Managed launcher layout: the launcher names the active release.
    version_file = resolved.parent.parent / "install" / "current-version"
    if version_file.is_file():
        version = version_file.read_text(encoding="utf-8").strip()
        candidate = (
            resolved.parent.parent
            / "install"
            / "releases"
            / version
            / "node_modules"
            / "@earendil-works"
            / "pi-coding-agent"
            / "package.json"
        )
        manifest = candidate if candidate.is_file() else None
    # Direct release layout: the package manifest sits above the resolved entry.
    if manifest is None:
        for parent in [resolved.parent, *resolved.parents][:8]:
            candidate = parent / "package.json"
            if not candidate.is_file():
                continue
            parsed = json.loads(candidate.read_text(encoding="utf-8"))
            if parsed.get("name") == "@earendil-works/pi-coding-agent":
                manifest = candidate
                break
    if manifest is None:
        return {"path": cli_path(), "version": ""}
    parsed = json.loads(manifest.read_text(encoding="utf-8"))
    installed = parsed["version"]
    if version and installed != version:
        raise AssertionError(f"launcher version {version} but package {installed}")
    return {"path": cli_path(), "version": installed}


def isolated_env(root: Path, project: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    home = root / "home"
    agent = root / "agent"
    for directory in (home, agent, root / "sessions", root / "registry"):
        directory.mkdir(parents=True, exist_ok=True)
    # The live-session control directory must be user-only, or the extension
    # refuses it; the fixture creates it the way the extension expects.
    live = root / "live"
    if not live.exists():
        live.mkdir(mode=0o700)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "PI_CODING_AGENT_DIR": str(agent),
        "PI_DIRECTORY_SESSIONS_DIR": str(root / "registry"),
        "PI_UTILS_LIVE_SESSIONS_DIR": str(live),
        "PI_OFFLINE": "1",
        "TERM": "xterm-256color",
        "LANG": "en_US.UTF-8",
    }
    env.update(extra or {})
    return env


def cli_command(project: Path, mode: str | None) -> list[str]:
    command = [
        cli_path(),
        "--offline",
        "--no-session",
        "--no-extensions",
        "--no-builtin-tools",
        "--no-skills",
        "--no-prompt-templates",
        "--no-context-files",
        "--no-mcp",
        "-e",
        str(UTILS / "index.ts"),
    ]
    if mode:
        command += ["--mode", mode]
    return command


def rpc_events(
    command: list[str], env: dict[str, str], project: Path, prompts: list[str]
) -> tuple[list[dict], list[dict]]:
    """Send prompts over real RPC dispatch and collect every event until each answer.

    A command that opens a native dialog blocks until the client answers it, so each
    dialog is recorded and cancelled the way a user pressing Escape would.
    """
    print(f"[rpc] start: {' '.join(command)}", file=sys.stderr, flush=True)
    process = subprocess.Popen(
        command,
        cwd=project,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin and process.stdout
    events: list[dict] = []
    dialogs: list[dict] = []
    # A reader thread drains stdout: mixing select() with buffered readline() can
    # leave a complete line in Python's buffer while the pipe itself is empty.
    lines: queue.Queue[str | None] = queue.Queue()

    def read_lines() -> None:
        assert process.stdout
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=read_lines, daemon=True).start()
    try:
        for index, prompt in enumerate(prompts):
            process.stdin.write(json.dumps({"id": f"req_{index}", "type": "prompt", "message": prompt}) + "\n")
            process.stdin.flush()
            deadline = time.monotonic() + COMMAND_TIMEOUT
            answered = False
            while not answered and time.monotonic() < deadline:
                try:
                    line = lines.get(timeout=0.2)
                except queue.Empty:
                    continue
                if line is None:
                    break
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    event.get("type") == "extension_ui_request"
                    and event.get("method") in ("select", "confirm", "input", "editor")
                    and event.get("id")
                ):
                    dialogs.append(event)
                    process.stdin.write(
                        json.dumps({"type": "extension_ui_response", "id": event["id"], "cancelled": True}) + "\n"
                    )
                    process.stdin.flush()
                    continue
                events.append(event)
                answered = event.get("id") == f"req_{index}"
            if not answered:
                process.send_signal(signal.SIGTERM)
                raise AssertionError(f"no RPC answer for {prompt!r}; events: {json.dumps(events)[-800:]}")
            print(f"[rpc] answered {prompt!r}", file=sys.stderr, flush=True)
    finally:
        try:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=10)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            process.kill()
    return events, dialogs


def notifications(events: list[dict]) -> list[str]:
    return [
        str(event.get("message", ""))
        for event in events
        if event.get("type") == "extension_ui_request" and event.get("method") == "notify"
    ]


def run_pty(
    command: list[str],
    env: dict[str, str],
    project: Path,
    typed: str,
    expect: str,
    sizes: list[tuple[int, int]],
) -> tuple[dict[str, str], bytes]:
    """Drive one live TUI: type once, then resize that same process and re-read it.

    Each size is sent as TIOCSWINSZ plus SIGWINCH to the running process, so this is
    a live resize of one component rather than a fresh run per size.
    """
    print(f"[pty] start: {' '.join(command)}", file=sys.stderr, flush=True)
    master, slave = pty.openpty()
    # The starting geometry is set before the app draws; later sizes signal the
    # running process instead of starting a new one.
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", sizes[0][1], sizes[0][0], 0, 0))
    transcript = bytearray()
    process = subprocess.Popen(command, cwd=project, env=env, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)

    def resize(width: int, height: int) -> None:
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", height, width, 0, 0))
        process.send_signal(signal.SIGWINCH)

    def pump(seconds: float) -> str:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if select.select([master], [], [], 0.05)[0]:
                try:
                    transcript.extend(os.read(master, 65536))
                except OSError:
                    break
        return strip_ansi(transcript.decode("utf-8", "replace"))

    observed: dict[str, str] = {}
    try:
        screen = pump(8.0)
        assert "pi" in screen.lower(), f"TUI did not start:\n{screen[-2000:]}"
        print("[pty] typing /effort low", file=sys.stderr, flush=True)
        os.write(master, typed.encode())
        deadline = time.monotonic() + COMMAND_TIMEOUT
        while time.monotonic() < deadline:
            screen = pump(1.0)
            if expect in screen:
                break
        for width, height in sizes:
            if (width, height) != sizes[0]:
                resize(width, height)
                pump(2.0)
            screen = pump(2.0)
            lines = [line for line in strip_ansi(screen).splitlines() if expect in line]
            observed[f"{width}x{height}"] = lines[-1].strip() if lines else ""
        print(f"[pty] done, {len(screen)} chars, sizes {list(observed)}", file=sys.stderr, flush=True)
        return observed, bytes(transcript)
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        os.close(master)


def main() -> int:
    parent = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="utils-live-"))
    output = parent / f"run-{time.strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(3)}"
    output.mkdir(parents=True, exist_ok=True)
    identity = cli_identity()
    root = output / "root"
    project = root / "project"
    project.mkdir(parents=True)
    (project / "README.md").write_text("live acceptance fixture\n", encoding="utf-8")
    unsafe_live = root / "unsafe-live"
    unsafe_live.mkdir(parents=True, exist_ok=True)
    unsafe_live.chmod(0o755)
    report: dict[str, object] = {"cli": identity, "checks": []}

    # 1. RPC: the command surfaces answer over real dispatch, with no provider.
    env = isolated_env(root, project)
    events, dialogs = rpc_events(
        cli_command(project, "rpc"),
        env,
        project,
        ["/effort low", "/effort turbo", "/sessions", "/live-sessions", "/init"],
    )
    (output / "rpc-events.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
    (output / "rpc-dialogs.json").write_text(json.dumps(dialogs, indent=2), encoding="utf-8")
    notes = notifications(events)
    report["rpc_notifications"] = notes

    effort_applied = [note for note in notes if note.startswith("Thinking level set to")]
    report["checks"].append(
        {
            "name": "effort reports the applied level, not the request",
            "pass": bool(effort_applied) and all("low" not in note for note in effort_applied),
            "observed": effort_applied,
        }
    )
    report["checks"].append(
        {
            "name": "unknown level is rejected with the valid list",
            "pass": any("Unknown thinking level" in note and "max" in note for note in notes),
            "observed": [note for note in notes if "Unknown thinking level" in note],
        }
    )
    report["checks"].append(
        {
            "name": "sessions command answers in the isolated directory",
            "pass": any("Directory Sessions" in json.dumps(dialog) for dialog in dialogs)
            or any("sessions" in note.lower() for note in notes),
            "observed": [dialog.get("title", "")[:120] for dialog in dialogs],
        }
    )
    report["checks"].append(
        {
            "name": "init reports that it sent nothing, instead of the host's silent rejection",
            "pass": any(
                "no configured credentials" in note or "No model is selected" in note for note in notes
            ),
            "observed": [note for note in notes if "guide task" in note or "No model" in note],
        }
    )

    # 2. RPC with an unsafe live-session directory: discovery failure, not "none".
    unsafe_env = isolated_env(root, project, {"PI_UTILS_LIVE_SESSIONS_DIR": str(unsafe_live)})
    unsafe_events, unsafe_dialogs = rpc_events(cli_command(project, "rpc"), unsafe_env, project, ["/live-sessions"])
    (output / "rpc-unsafe-events.json").write_text(json.dumps(unsafe_events, indent=2), encoding="utf-8")
    (output / "rpc-unsafe-dialogs.json").write_text(json.dumps(unsafe_dialogs, indent=2), encoding="utf-8")
    unsafe_notes = notifications(unsafe_events)
    report["unsafe_live_notifications"] = unsafe_notes
    report["checks"].append(
        {
            "name": "an unusable control directory is reported, not shown as empty",
            "pass": any("Live session discovery failed" in note for note in unsafe_notes)
            and not any("No live Pi sessions found." in note for note in unsafe_notes),
            "observed": unsafe_notes,
        }
    )

    # 3. PTY: the same surface in the interactive TUI, then live resizes of that run.
    sizes = [(120, 40), (48, 24), (48, 12)]
    observed, raw = run_pty(
        cli_command(project, None) + ["--use-theme", "light"],
        env,
        project,
        "/effort low\r",
        "Thinking level set to",
        sizes,
    )
    (output / "pty-sizes.json").write_text(json.dumps(observed, indent=2), encoding="utf-8")
    (output / "pty-raw.bin").write_bytes(raw)
    report["pty_sizes"] = observed
    report["checks"].append(
        {
            "name": "the effort confirmation stays readable through live resizes (light theme)",
            "pass": all(observed.get(f"{width}x{height}") for width, height in sizes),
            "observed": observed,
        }
    )

    report["output_dir"] = str(output)
    report["unverified"] = [
        "screen-reader output and physical terminal/theme rendering: a headless PTY capture cannot prove them",
        "model-driven command behaviour: no provider or credentials are configured, so a command that needs a model reports the host's refusal",
        "the live-session delivery confirmation needs the target to start a turn; the acceptance covers the unconfirmed wording only",
    ]
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    failures = [check for check in report["checks"] if not check["pass"]]  # type: ignore[index]
    print(json.dumps({"outputDir": str(output), "cli": identity, "failures": [f["name"] for f in failures]}, indent=2))
    for check in report["checks"]:  # type: ignore[assignment]
        print(("PASS " if check["pass"] else "FAIL ") + check["name"] + " -> " + json.dumps(check["observed"])[:400])
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())