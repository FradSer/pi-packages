"""Offline real-Pi print, management-menu and keyboard/resize checks in disposable roots.

Manual verification: uv run --no-project packages/continual-learning/tests/live_meaningful_details.py
No user authentication, remote model, built-in tools or project configuration is used.
"""

from __future__ import annotations

from live_acceptance_support import workspace_pi

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
CUSTOM_TYPES = {"harness-event", "harness-check", "harness-guidance-event", "continual-learning-result"}


def snapshots(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.endswith("}")]


def verify_expanded(row: dict) -> None:
    lines = [line.strip() for line in row["lines"] if line.strip()]
    text = "".join("".join(lines).split())
    data = row["data"]
    if row["customType"] == "continual-learning-result":
        assert lines[0].startswith("[learning]"), lines
        assert "1AGENTS.mdchangeapplied" in text, lines
        assert "agents" in text and "automatic" in text, lines
        assert "jev-1.13.0" in text and "uncertain" in text and "test-command.md" in text, lines
        return
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

    def resize(width: int, height: int = 40) -> None:
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", height, width, 0, 0))

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
        resize(120)
        process.send_signal(signal.SIGWINCH)

        def has_notice(message: str) -> bool:
            return any(row["kind"] == "notification" and message in row["message"] for row in snapshots(output))

        def menu_count() -> int:
            return sum(row["kind"] == "menu" for row in snapshots(output))

        def latest_menu() -> dict:
            menus = [row for row in snapshots(output) if row["kind"] == "menu"]
            assert menus, "expected a captured native menu"
            return menus[-1]

        def close_root() -> None:
            before = sum(row["kind"] == "menu-closed" for row in snapshots(output))
            os.write(master, b"\x03")
            wait_for(lambda: sum(row["kind"] == "menu-closed" for row in snapshots(output)) > before)

        def open_memory_menu() -> dict:
            before = menu_count()
            os.write(master, b"/memory\r")
            wait_for(lambda: menu_count() == before + 1)
            return latest_menu()

        root = open_memory_menu()
        resize(48, 24)
        process.send_signal(signal.SIGWINCH)
        before = menu_count()
        os.write(master, b"\r")  # Browse memories.
        wait_for(lambda: menu_count() == before + 1)
        for _ in range(4):
            current = latest_menu()
            assert "Next page" in current["options"], current
            before = menu_count()
            os.write(master, b"\x1b[B" * current["options"].index("Next page") + b"\r")
            wait_for(lambda: menu_count() == before + 1)
        current = latest_menu()
        assert "page 5/5" in current["title"], current
        assert "memory-129.md" in current["options"][0], current
        before = menu_count()
        os.write(master, b"\r")
        wait_for(lambda: menu_count() == before + 1)
        def reader_has(marker: str) -> bool:
            return any(row["kind"] == "management-render" and marker in " ".join(row["lines"]) for row in snapshots(output))

        wait_for(lambda: reader_has("CL_MEMORY_BODY_START"))
        resize(120)
        process.send_signal(signal.SIGWINCH)
        wait_for(lambda: any(row["kind"] == "management-render" and row["title"].startswith("Memory entry") and row["width"] == 80 for row in snapshots(output)))
        for _ in range(10):
            if reader_has("CL_MEMORY_BODY_TAIL"):
                break
            before_render = len(snapshots(output))
            os.write(master, b"\x1b[6~")
            wait_for(lambda: len(snapshots(output)) > before_render)
        assert reader_has("CL_MEMORY_BODY_TAIL")
        before = menu_count()
        os.write(master, b"\r")  # Close reader, return to the same list page.
        wait_for(lambda: menu_count() == before + 1)
        assert "page 5/5" in latest_menu()["title"]
        before = menu_count()
        os.write(master, b"\x1b")  # Back to Memory's root.
        wait_for(lambda: menu_count() == before + 1)
        close_root()  # Wait until the selector releases input ownership.

        root = open_memory_menu()
        assert root["options"][:3] == ["Browse memories", "Learning settings", "Recent learning"], root
        before = menu_count()
        os.write(master, b"\x1b[B" * root["options"].index("Recent learning") + b"\r")
        wait_for(lambda: has_notice("No recent learning changes") and menu_count() == before + 1)
        close_root()

        root = open_memory_menu()
        assert root["options"][:3] == ["Browse memories", "Learning settings", "Recent learning"], root
        settings_menu_before = menu_count()
        os.write(master, b"\x1b[B" * root["options"].index("Learning settings") + b"\r")
        wait_for(lambda: menu_count() == settings_menu_before + 1)
        settings_menu = latest_menu()
        assert settings_menu["options"][:3] == [
            "Select learning model", "Toggle automatic learning", "Advanced phase policies"
        ], settings_menu
        phase_menu_before = menu_count()
        os.write(master, b"\x1b[B" * settings_menu["options"].index("Advanced phase policies") + b"\r")
        wait_for(lambda: menu_count() == phase_menu_before + 1)
        assert "phase" in latest_menu()["title"].lower()
        # Cancel the nested native selector before it can mutate any policy.
        # Ctrl-C is the selector's explicit cancellation path and avoids
        # sending the next command while a just-opened menu is still painting.
        time.sleep(0.2)
        os.write(master, b"\x03")
        wait_for(lambda: latest_menu()["title"].startswith("Learning settings"))
        before = menu_count()
        os.write(master, b"\x03")
        wait_for(lambda: menu_count() > before and latest_menu()["title"].startswith("Memory"))
        close_root()
        assert process.poll() is None

        # /harness with no request must open the real native rule picker. Closing
        # it at a narrow width must not send a follow-up or create configuration.
        resize(48)
        process.send_signal(signal.SIGWINCH)
        harness_menu_before = menu_count()
        os.write(master, b"/harness\r")
        wait_for(lambda: menu_count() == harness_menu_before + 1)
        harness_menu = latest_menu()
        assert "Create or update rule" in harness_menu["options"], harness_menu
        assert "Close" in harness_menu["options"], harness_menu
        os.write(master, b"\x1b[B" * harness_menu["options"].index("Close") + b"\r")
        wait_for(lambda: process.poll() is None)
        assert not any(row["kind"] == "follow-up" for row in snapshots(output))
        management = [row for row in snapshots(output) if row["kind"] == "management-render"]
        assert any(row["width"] == 48 and row["height"] == 24 for row in management)
        assert all(len(row["lines"]) <= row["height"] for row in management)
        assert not any(row["kind"] == "notification" and "CL_MEMORY_BODY" in row["message"] for row in snapshots(output))
        assert not (cwd / ".pi" / "harness.json").exists()
        resize(120)
        process.send_signal(signal.SIGWINCH)
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
    pi = workspace_pi(Path(__file__).resolve().parents[3])
    assert pi, "pi CLI is required"
    with tempfile.TemporaryDirectory(prefix="learning-details-live-") as raw:
        cwd = Path(raw)
        agent = cwd / "agent"
        agent.mkdir()
        (agent / "settings.json").write_text(json.dumps({"theme": "dark", "quietStartup": True, "packages": []}))
        (agent / "memory").mkdir()
        (agent / "memory" / "settings.json").write_text(json.dumps({"autoMemory": False}))
        canonical = str(cwd.resolve())
        scope = "--" + canonical.lstrip("/").replace("/", "-").replace("\\", "-").replace(":", "-") + "--"
        registry = agent / "memory" / "scopes"; registry.mkdir()
        (registry / f"{scope}.json").write_text(json.dumps({"version":1,"cwd":canonical}))
        memories = agent / "memory" / scope; memories.mkdir()
        for number in range(1,130):
            body = "CL_MEMORY_BODY_START\n" + ("body " * 900) + "CL_MEMORY_BODY_TAIL" if number == 129 else "Small reference"
            (memories / f"memory-{number:03d}.md").write_text(f"---\nname: memory-{number:03d}\ndescription: Reference {number}\ntype: project\n---\n{body}")
        (memories / "MEMORY.md").write_text("\n".join(f"- [memory-{number:03d}.md](memory-{number:03d}.md)" for number in range(1,130)))
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
                          "full65LinePrompt": "passed", "agentsSummary": "passed", "managementMenus": "passed", "management48x24": "passed", "readerResize": "passed",
                          "phasePolicyMenu": "passed", "jevReceiptDetails": "passed", "remoteRequests": 0}))


if __name__ == "__main__":
    main()
