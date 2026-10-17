#!/usr/bin/env python3
"""Explicit-run probe: real Terminal.app rendering and assistive text.

macOS only, and it needs Accessibility and Screen Recording permission for the
process that runs it. Run from the repository root:

    uv run --no-project python packages/loop/tests/live_terminal_accessibility.py

What it establishes: in a real Terminal.app window on the physical display, with
the real TUI and the real extension, the loop's start row and its below-editor
status row are composed and readable at 120x40, after a live resize of the same
window to 48x24 and 48x12, and in a fresh 48x12 window. At 48 columns the start
row truncates to `[loop] started · every 1... · ctrl+o to expand`, so the label
and the expand affordance stay readable instead of cutting silently. It records
real OS screenshots of the window content and the terminal's accessibility text
area value, which is the text a screen reader receives from this emulator.

What it does not establish: VoiceOver speech output is not captured, a hardware
terminal is not exercised, other emulators are not tested, and the pty probe
(`live_loop_rows.py`) remains the portable evidence for PageUp reachability from a
long transcript, because Terminal.app consumes PageUp as its own scrollback key.

The captures deliberately exclude the window title bar: this host's Terminal
profile prints environment variables, including credentials, into the title.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import time

PACKAGE = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = pathlib.Path(__file__).with_name("delivery-refusal-fixture.ts")
LOOP_COMMAND = "/loop --every 1h --times 200 UI_PROBE"
SIZES = [("120x40", 40, 120), ("48x24", 24, 48), ("48x12", 12, 48)]
TITLE_BAR_PIXELS = 30


def tell(script: str, seconds: int = 30) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=seconds)
    return (result.stdout or result.stderr).strip()


def window_bounds() -> tuple[int, int, int, int] | None:
    raw = tell('tell application "System Events" to tell process "Terminal" to get {position, size} of window 1')
    try:
        numbers = [int(part) for part in raw.replace("{", " ").replace("}", " ").replace(",", " ").split()]
    except ValueError:
        return None
    return (numbers[0], numbers[1], numbers[2], numbers[3]) if len(numbers) >= 4 else None


def accessibility_text() -> str:
    return tell('''tell application "System Events"
  tell process "Terminal"
    tell window 1
      try
        return value of text area 1 of scroll area 1 of UI element 1
      on error
        return ""
      end try
    end tell
  end tell
end tell''')


def close_own_windows() -> None:
    """Close only windows running this probe's script, matched by title."""
    tell('''with timeout of 15 seconds
  tell application "Terminal"
    close (every window whose name contains "loop-a11y-probe")
  end tell
end timeout''', 25)


def set_size(rows: int, columns: int) -> str:
    return tell(f'''with timeout of 20 seconds
  tell application "Terminal"
    set number of rows of front window to {rows}
    set number of columns of front window to {columns}
    set position of front window to {{120, 40}}
  end tell
end timeout''')


def capture(bounds: tuple[int, int, int, int] | None, path: pathlib.Path) -> None:
    if bounds is None:
        return
    x, y, w, h = bounds
    subprocess.run(["screencapture", "-x", "-R", f"{x},{y + TITLE_BAR_PIXELS},{w},{h - TITLE_BAR_PIXELS}",
                    str(path)], timeout=60)


def wait_for(predicate, seconds: float, poll: float = 0.3) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(poll)
    return predicate()


def launch_script(root: pathlib.Path) -> pathlib.Path:
    """A self-contained launcher: disposable HOME, agent dir and working folder."""
    script = root / "loop-a11y-probe.command"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -u\n"
        f"export HOME={root}/home\n"
        f"export PI_CODING_AGENT_DIR={root}/agent\n"
        "export PI_OFFLINE=1\n"
        "export TERM=xterm-256color\n"
        "unset TYPESAFE_API_KEY\n"
        f"mkdir -p {root}/work\n"
        f"cd {root}/work || exit 1\n"
        "exec pi -ne -ns -np -nc \\\n"
        f"  -e {FIXTURE} \\\n"
        "  --model loop-probe/scripted \\\n"
        f'  "{LOOP_COMMAND}"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def observe(name: str, shot_dir: pathlib.Path) -> dict:
    text = accessibility_text()
    bounds = window_bounds()
    shot = shot_dir / f"{name}.png"
    capture(bounds, shot)
    lines = [line for line in text.splitlines() if line.strip()]
    return {
        "size": name,
        "bounds": bounds,
        "screenshot": str(shot),
        "screenshot_bytes": shot.stat().st_size if shot.exists() else 0,
        "start_row": [line for line in lines if "started" in line],
        "status_row": [line for line in lines if "Looping" in line],
    }


def main() -> int:
    if sys.platform != "darwin":
        print(json.dumps({"error": "this probe drives Terminal.app and runs on macOS only"}))
        return 1
    root = pathlib.Path(tempfile.mkdtemp(prefix="loop-a11y-"))
    shots = root / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    launch = launch_script(root)
    close_own_windows()
    subprocess.run(["open", "-a", "Terminal", str(launch)], check=False, timeout=60)
    time.sleep(3)
    cases: list[dict] = []
    failures: list[str] = []
    if not wait_for(lambda: any("started" in line for line in accessibility_text().splitlines()), 120):
        failures.append("the loop start row never appeared in the accessibility text")
    else:
        for name, rows, columns in SIZES:
            size_error = set_size(rows, columns)
            time.sleep(3)
            case = observe(name, shots)
            case["size_error"] = size_error or None
            cases.append(case)
            print(json.dumps(case))
        # A fresh window at the short size: Terminal.app consumes PageUp, so a row
        # above the viewport is only reachable through the pty probe.
        close_own_windows()
        subprocess.run(["open", "-a", "Terminal", str(launch)], check=False, timeout=60)
        time.sleep(3)
        set_size(12, 48)
        if wait_for(lambda: any("started" in line for line in accessibility_text().splitlines()), 90):
            fresh = observe("48x12-fresh", shots)
            cases.append(fresh)
            print(json.dumps(fresh))
        else:
            failures.append("48x12-fresh: the row never appeared in a fresh twelve-row window")
    for case in cases:
        if not case["start_row"]:
            failures.append(f"{case['size']}: no loop start row in the accessibility text")
        if not case["status_row"]:
            failures.append(f"{case['size']}: no status row in the accessibility text")
        if not case["screenshot_bytes"]:
            failures.append(f"{case['size']}: no screenshot written")
        if case.get("size_error"):
            failures.append(f"{case['size']}: resize failed: {case['size_error']}")
    close_own_windows()
    print(json.dumps({"outputDir": str(shots), "failures": failures}))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())