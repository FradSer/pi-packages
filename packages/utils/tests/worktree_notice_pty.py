"""Interactive notification capture for the installed worktree redirect.

This script runs inside the disposable container that utils_docker.sh starts. It
drives the real interactive Pi CLI through a PTY, because print mode drops
ui.notify, so the redirect notice and the unignored-directory warning exist only
in the terminal UI. Each case keeps its raw bytes, its screen frames and the
disk result of the same run.

It proves the notice text and the notice's absence for untouched commands. It
does not prove model-driven behaviour beyond the deterministic fixture turn.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

import pyte

RESULTS: list[dict] = []
FAILURES: list[str] = []

INFO_FRAGMENTS = ("worktree path redirected", "linked worktrees stay inside")
WARNING_FRAGMENTS = ("is not git-ignored here", "add it to .gitignore", "untracked in")


def check(case: str, name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"case": case, "check": name, "ok": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'} {case} :: {name}" + (f" [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(f"{case}::{name} [{detail}]")


def git(cwd: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}: {result.stderr.strip()}")


def make_repo(root: Path, *, subdir: str | None = None, branches: tuple[str, ...] = (), gitignore: str | None = None) -> Path:
    if subdir:
        (root / subdir).mkdir(parents=True)
    else:
        root.mkdir(parents=True)
    if gitignore is not None:
        (root / ".gitignore").write_text(gitignore, encoding="utf-8")
    git(root, "init", "-q")
    git(root, "config", "user.name", "Worktree Test")
    git(root, "config", "user.email", "worktree@example.invalid")
    (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    for branch in branches:
        git(root, "branch", branch)
    return root.resolve()


def capture(
    case: str,
    case_dir: Path,
    cwd: Path,
    command: str,
    *,
    size: tuple[int, int],
    ctx: dict,
    hold: float = 12.0,
    persist: bool = False,
    keys_after: list[tuple[str, bytes]] | None = None,
) -> str:
    rows, columns = size
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(ctx["home"]),
        "PI_CODING_AGENT_DIR": str(ctx["agent_dir"]),
        "PI_OFFLINE": "1",
        "PI_SKIP_VERSION_CHECK": "1",
        "TERM": "xterm-256color",
        "LANG": "C.UTF-8",
        "PI_WORKTREE_FIXTURE_COMMAND": command,
    }
    argv = [
        "pi",
        "--offline",
        *( [] if persist else ["--no-session"] ),
        "-ns",
        "-np",
        "-nc",
        "--no-themes",
        "-e",
        str(ctx["fixture"]),
        "--model",
        "worktree-bash/test",
        "Create the requested worktree.",
    ]
    primary, secondary = pty.openpty()
    fcntl.ioctl(secondary, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=secondary, stdout=secondary, stderr=secondary,
                               close_fds=True, preexec_fn=os.setsid)
    os.close(secondary)
    screen = pyte.Screen(columns, rows)
    stream = pyte.ByteStream(screen)
    raw = bytearray()
    frames: list[str] = []
    pending_keys = list(keys_after or [])
    sent_keys: list[str] = []
    deadline = time.time() + hold
    while time.time() < deadline:
        ready, _, _ = select.select([primary], [], [], 0.25)
        if not ready:
            continue
        try:
            chunk = os.read(primary, 65536)
        except OSError:
            break
        if not chunk:
            break
        raw.extend(chunk)
        stream.feed(chunk)
        frame = "\n".join(screen.display)
        frames.append(frame)
        # Send each key only after the render that proves the row is on screen.
        while pending_keys and pending_keys[0][0] in frame:
            _marker, keys = pending_keys.pop(0)
            os.write(primary, keys)
            sent_keys.append(keys.hex())
    os.write(primary, b"\x03")
    time.sleep(1.0)
    os.write(primary, b"\x04")
    time.sleep(1.5)
    if process.poll() is None:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    process.wait(timeout=10)
    try:
        while True:
            chunk = os.read(primary, 65536)
            if not chunk:
                break
            raw.extend(chunk)
            stream.feed(chunk)
            frames.append("\n".join(screen.display))
    except OSError:
        pass
    os.close(primary)
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "raw.bin").write_bytes(bytes(raw))
    (case_dir / "frames.txt").write_text("\n----FRAME----\n".join(frames), encoding="utf-8")
    (case_dir / "last-screen.txt").write_text("\n".join(screen.display) + "\n", encoding="utf-8")
    (case_dir / "interaction.json").write_text(
        json.dumps(
            {
                "case": case,
                "cwd": str(cwd),
                "command": command,
                "terminal": {"columns": columns, "rows": rows},
                "persistedSession": persist,
                "keys": ["\\x03 (Ctrl-C interrupt)", "\\x04 (Ctrl-D exit)", *(sent_keys and ["\\x0f (Ctrl-O expand the entered row)"] or [])],
                "frames": len(frames),
                "rawBytes": len(raw),
                "exitStatus": process.returncode,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return "\n----FRAME----\n".join(frames)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def case_notice_root_relative(base: Path, ctx: dict) -> None:
    case = "notice_root_relative"
    repo = make_repo(base / "repo", branches=("feature/foo",))
    frames = capture(case, base, repo, "git worktree add ../foo feature/foo", size=(40, 120), ctx=ctx)
    text = normalize(frames)
    check(case, "redirect notice is displayed", all(fragment in text for fragment in INFO_FRAGMENTS), "")
    check(case, "notice names the managed target", ".pi/worktrees/foo" in text, "")
    check(case, "unignored-directory warning is displayed", all(fragment in text for fragment in WARNING_FRAGMENTS), "")
    check(case, "worktree was created", (repo / ".pi" / "worktrees" / "foo" / "tracked.txt").is_file(), "")
    check(case, "repository .gitignore untouched", not (repo / ".gitignore").exists())
    check(case, "ephemeral session is told it cannot switch", "cannot switch to it" in text, "")


def case_notice_subdirectory_absolute(base: Path, ctx: dict) -> None:
    case = "notice_subdirectory_absolute"
    repo = make_repo(base / "repo", subdir="packages/app", branches=("feature/foo",))
    shell_cwd = repo / "packages" / "app"
    frames = capture(case, base, shell_cwd, "git worktree add ../foo feature/foo", size=(40, 120), ctx=ctx)
    text = normalize(frames)
    target = repo / ".pi" / "worktrees" / "foo"
    check(case, "redirect notice is displayed", all(fragment in text for fragment in INFO_FRAGMENTS), "")
    check(case, "notice names the absolute managed target", str(target) in text, str(target))
    check(case, "notice does not repeat the relative spelling", "redirected to .pi/worktrees/foo" not in text, "")
    check(case, "worktree anchors to the repository root", (target / "tracked.txt").is_file(), str(target))
    check(case, "no .pi inside the shell directory", not (shell_cwd / ".pi").exists())


def case_notice_ignored_no_warning(base: Path, ctx: dict) -> None:
    case = "notice_ignored_no_warning"
    repo = make_repo(base / "repo", branches=("feature/ign",), gitignore=".pi/\n")
    before = (repo / ".gitignore").read_bytes()
    frames = capture(case, base, repo, "git worktree add ../ign feature/ign", size=(40, 120), ctx=ctx)
    text = normalize(frames)
    check(case, "redirect notice is displayed", all(fragment in text for fragment in INFO_FRAGMENTS), "")
    check(case, "no warning for an ignored directory", not any(fragment in text for fragment in WARNING_FRAGMENTS), "")
    check(case, "worktree was created", (repo / ".pi" / "worktrees" / "ign" / "tracked.txt").is_file(), "")
    check(case, ".gitignore is byte-identical", (repo / ".gitignore").read_bytes() == before)


def case_notice_untouched_syntax(base: Path, ctx: dict) -> None:
    case = "notice_untouched_syntax"
    repo = make_repo(base / "repo", branches=("feature/chained",))
    frames = capture(case, base, repo, "git worktree add ../chained feature/chained && git status --porcelain",
                     size=(40, 120), ctx=ctx)
    text = normalize(frames)
    check(case, "no redirect notice for unsupported syntax", "worktree path redirected" not in text, "")
    check(case, "no managed directory was created", not (repo / ".pi").exists())
    check(case, "literal sibling worktree was created", (repo.parent / "chained" / "tracked.txt").is_file())


def case_notice_root_narrow(base: Path, ctx: dict) -> None:
    case = "notice_root_narrow"
    repo = make_repo(base / "repo", branches=("feature/foo",))
    frames = capture(case, base, repo, "git worktree add ../foo feature/foo", size=(24, 48), ctx=ctx)
    text = normalize(frames)
    check(case, "redirect notice survives a narrow terminal", "worktree path redirected" in text, "")
    check(case, "managed directory survives a narrow terminal", "worktrees/" in text, "")
    check(case, "warning survives a narrow terminal", "is not git-ignored here" in text, "")
    check(case, "worktree was created", (repo / ".pi" / "worktrees" / "foo" / "tracked.txt").is_file())


def case_notice_session_move(base: Path, ctx: dict) -> None:
    case = "notice_session_move"
    repo = make_repo(base / "repo", branches=("feature/foo",))
    frames = capture(
        case, base, repo, "git worktree add ../foo feature/foo",
        size=(40, 120), ctx=ctx, hold=24.0, persist=True,
        keys_after=[("[worktree] entered", b"\x0f")],
    )
    text = normalize(frames)
    target = repo / ".pi" / "worktrees" / "foo"
    check(case, "the move is announced", "moves there when the turn ends" in text, "")
    check(case, "the replacement session records the entered row", "[worktree] entered" in text, "")
    check(case, "the row names the managed path", ".pi/worktrees/foo" in text, "")
    check(case, "Ctrl-O expansion shows the labelled directory", f"Path: {target}" in text, f"Path: {target}")
    check(case, "the terminal shows the worktree", str(target) in text, str(target))
    marker = target / "pi-worktree-cwd.txt"
    # pwd may print the logical spelling, so compare canonical paths.
    moved = marker.is_file() and Path(marker.read_text(encoding="utf-8").strip()).resolve() == target.resolve()
    check(case, "the replacement session works in the worktree", moved, str(marker))
    check(case, "the parent checkout keeps no worktree file", not (repo / "pi-worktree-cwd.txt").exists())


CASES = (
    case_notice_root_relative,
    case_notice_subdirectory_absolute,
    case_notice_ignored_no_warning,
    case_notice_untouched_syntax,
    case_notice_root_narrow,
    case_notice_session_move,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive notice capture for the installed pi-utils worktree redirect.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--work", default="/isolated/notice-work", type=Path)
    parser.add_argument("--fixture", default=os.environ.get("PI_WORKTREE_FIXTURE", "/utils-tests/worktree_bash_fixture.ts"))
    parser.add_argument("--agent-dir", default=os.environ.get("PI_WORKTREE_AGENT_DIR", "/isolated/agent"))
    parser.add_argument("--home", default=os.environ.get("PI_WORKTREE_HOME", "/isolated/home"))
    arguments = parser.parse_args()

    work = arguments.work
    if work.exists():
        subprocess.run(["rm", "-rf", str(work)], check=True)
    work.mkdir(parents=True)
    arguments.output.mkdir(parents=True, exist_ok=True)
    home = Path(arguments.home)
    home.mkdir(parents=True, exist_ok=True)
    fixture = Path(arguments.fixture)
    if not fixture.is_file():
        print(f"fixture not found: {fixture}", file=sys.stderr)
        return 2

    context = {"fixture": fixture, "agent_dir": Path(arguments.agent_dir), "home": home}
    for case in CASES:
        case(work / case.__name__, context)

    evidence = {
        "results": RESULTS,
        "failed": FAILURES,
        "status": "passed" if not FAILURES else "failed",
    }
    (arguments.output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    summary = {
        "cases": len(CASES),
        "checks": len(RESULTS),
        "passed": sum(1 for item in RESULTS if item["ok"]),
        "failed": len(FAILURES),
        "status": evidence["status"],
    }
    print(json.dumps(summary))
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
