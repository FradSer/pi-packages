"""Real git worktree creation through the installed pi-utils redirect.

This driver runs inside the disposable container that utils_docker.sh starts. It
drives the installed Pi CLI with an offline provider fixture, so the real bash
tool executes the command the installed redirect produced. It then reads the
checkout, the branch, the lock state and the worktree list back from disk,
because the redirect is only correct when a real worktree lands in
.pi/worktrees/<name>.

Every case prints one PASS/FAIL line and is written to the evidence file. A
failed check stays in the evidence and sets the exit code.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RESULTS: list[dict] = []
FAILURES: list[str] = []
OBSERVATIONS: dict[str, dict] = {}


def check(case: str, name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"case": case, "check": name, "ok": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'} {case} :: {name}" + (f" [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(f"{case}::{name} [{detail}]")


def skip(case: str, name: str, detail: str = "") -> None:
    RESULTS.append({"case": case, "check": name, "ok": None, "skipped": True, "detail": detail})
    print(f"SKIP {case} :: {name}" + (f" [{detail}]" if detail else ""))


def git_version() -> str:
    return subprocess.run(["git", "--version"], capture_output=True, text=True, check=False).stdout.strip()


def worktree_add_help() -> str:
    """The 'git worktree add' help text, which needs a repository to print."""
    with tempfile.TemporaryDirectory() as probe:
        subprocess.run(["git", "init", "-q", probe], capture_output=True, text=True, check=False)
        result = subprocess.run(
            ["git", "worktree", "add", "-h"], cwd=probe, capture_output=True, text=True, check=False
        )
    return result.stdout + result.stderr


def orphan_supported() -> bool:
    return "--orphan" in worktree_add_help()


def git(cwd: Path, *args: str, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if expect_success and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}: {result.stderr.strip()}")
    return result


def head_of(cwd: Path) -> str:
    return git(cwd, "rev-parse", "HEAD").stdout.strip()


def worktrees(repo: Path) -> list[dict]:
    """Parse 'git worktree list --porcelain' into real entries."""
    output = git(repo, "worktree", "list", "--porcelain").stdout
    entries: list[dict] = []
    current: dict | None = None
    for line in output.splitlines():
        if line.startswith("worktree "):
            current = {
                "path": Path(line[len("worktree ") :]).resolve(),
                "branch": None,
                "locked": False,
                "reason": None,
                "detached": False,
                "head": None,
            }
            entries.append(current)
        elif current is None:
            continue
        elif line.startswith("locked"):
            current["locked"] = True
            parts = line.split(None, 1)
            current["reason"] = parts[1] if len(parts) > 1 else ""
        elif line.startswith("branch "):
            current["branch"] = line[len("branch ") :].removeprefix("refs/heads/")
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD ") :]
        elif line.strip() == "detached":
            current["detached"] = True
    return entries


def make_repo(
    root: Path,
    *,
    commits: int = 2,
    subdir: str | None = None,
    branches: tuple[str, ...] = (),
    gitignore: str | None = None,
) -> dict:
    """A real checkout whose first commit is the HEAD~1 of the later commits."""
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
    first = head_of(root)
    for index in range(2, commits + 1):
        (root / "tracked.txt").write_text(f"commit-{index}\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-qm", f"commit-{index}")
    for branch in branches:
        git(root, "branch", branch)
    return {"root": root.resolve(), "first": first, "head": head_of(root)}


def run_pi(
    case_dir: Path,
    cwd: Path,
    command: str,
    *,
    fixture: Path,
    agent_dir: Path,
    home: Path,
    extra_env: dict[str, str] | None = None,
) -> dict:
    """One real pi --print run that issues exactly one bash tool call."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "PI_CODING_AGENT_DIR": str(agent_dir),
        "PI_OFFLINE": "1",
        "PI_SKIP_VERSION_CHECK": "1",
        "TERM": "dumb",
        "LANG": "C.UTF-8",
        "PI_WORKTREE_FIXTURE_COMMAND": command,
    }
    env.update(extra_env or {})
    argv = [
        "pi",
        "--print",
        "--mode",
        "json",
        "--offline",
        "-ns",
        "-np",
        "-nc",
        "--no-themes",
        "-e",
        str(fixture),
        "--model",
        "worktree-bash/test",
        "--",
        "Create the requested worktree.",
    ]
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=300, check=False)
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "pi.jsonl").write_text(result.stdout, encoding="utf-8")
    (case_dir / "pi.stderr").write_text(result.stderr, encoding="utf-8")
    events: list[dict] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {"returncode": result.returncode, "events": events, "stdout": result.stdout, "stderr": result.stderr}


def tool_outcomes(run: dict) -> list[dict]:
    """Every tool result the host reported.

    A blocked call still produces tool_execution_start and tool_execution_end,
    so only the result text and its error flag tell what happened.
    """
    names = {
        event.get("toolCallId"): event.get("toolName")
        for event in run["events"]
        if event.get("type") == "tool_execution_start"
    }
    outcomes: list[dict] = []
    for event in run["events"]:
        if event.get("type") != "tool_execution_end":
            continue
        result = event.get("result") or {}
        parts = result.get("content") or []
        text = " ".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        outcomes.append(
            {
                "tool": names.get(event.get("toolCallId")) or event.get("toolName"),
                "isError": bool(event.get("isError")),
                "text": text.strip(),
            }
        )
    return outcomes


def bash_calls(run: dict) -> list[dict]:
    """The command the model issued and the result the real bash tool returned."""
    issued: dict[str, str] = {}
    for event in run["events"]:
        if event.get("type") == "tool_execution_start" and event.get("toolName") == "bash":
            issued[event.get("toolCallId", "")] = (event.get("args") or {}).get("command", "")
    calls: list[dict] = []
    for event in run["events"]:
        if event.get("type") != "tool_execution_end" or event.get("toolName") != "bash":
            continue
        structured = (event.get("result") or {}).get("structuredContent") or {}
        calls.append(
            {
                "issued": issued.get(event.get("toolCallId", ""), ""),
                "exit_code": structured.get("exit_code"),
                "output": structured.get("output", ""),
                "is_error": bool(event.get("isError")),
            }
        )
    return calls


def record_cli(
    case: str,
    run: dict,
    command: str,
    *,
    expect_error: bool = False,
    expect_enter: bool = False,
) -> list[dict]:
    calls = bash_calls(run)
    check(case, "pi --print exits 0", run["returncode"] == 0, f"rc={run['returncode']}")
    expected_calls = 2 if expect_enter else 1
    check(case, f"{expected_calls} bash tool call(s)", len(calls) == expected_calls, f"calls={len(calls)}")
    check(case, "creation turn completed", "WORKTREE_BASH_DONE" in run["stdout"], "")
    entered = "WORKTREE_ENTERED_DONE" in run["stdout"]
    if expect_enter:
        check(case, "replacement session ran a turn", entered, "")
    else:
        check(case, "no session move happened", not entered, "")
    if calls:
        check(case, "model issued the case command", calls[0]["issued"] == command, calls[0]["issued"])
        exit_code = calls[0]["exit_code"]
        if expect_error:
            check(case, "bash reports the git failure", exit_code not in (0, None), f"exit={exit_code}")
        else:
            check(case, "bash command succeeds", exit_code == 0, f"exit={exit_code}")
    OBSERVATIONS.setdefault(case, {})["toolOutcomes"] = tool_outcomes(run)
    OBSERVATIONS.setdefault(case, {})["sessionCwds"] = [
        event.get("cwd") for event in run["events"] if event.get("type") == "session" and event.get("cwd")
    ]
    return calls


def check_moved(case: str, repo: Path, target: Path) -> None:
    """The replacement session wrote its own cwd from inside the worktree."""
    marker = target / "pi-worktree-cwd.txt"
    moved = marker.is_file() and Path(marker.read_text(encoding="utf-8").strip()).resolve() == target.resolve()
    check(case, "replacement session runs in the worktree", moved, str(marker))
    check(case, "the parent checkout keeps no worktree file", not (repo / "pi-worktree-cwd.txt").exists())
    check(case, "no second worktree was created", len(worktrees(repo)) == 2, str(paths(worktrees(repo))))


def managed(repo: Path, name: str) -> Path:
    return repo / ".pi" / "worktrees" / name


def paths(entries: list[dict]) -> list[Path]:
    return [entry["path"] for entry in entries]


def case_root_plain(base: Path, ctx: dict) -> None:
    repo = make_repo(base / "repo", commits=2, branches=("feature/foo",))
    root = repo["root"]
    run = run_pi(base, root, "git worktree add ../foo feature/foo", **ctx)
    record_cli("root_plain", run, "git worktree add ../foo feature/foo", expect_enter=True)
    target = managed(root, "foo")
    check_moved("root_plain", root, target)
    check("root_plain", "worktree lands in .pi/worktrees", target.is_dir(), str(target))
    check("root_plain", "branch is feature/foo", git(target, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature/foo")
    check("root_plain", "worktree holds the real checkout", (target / "tracked.txt").read_text(encoding="utf-8") == "commit-2\n")
    check("root_plain", "no sibling checkout next to the repo", not (root.parent / "foo").exists())
    check("root_plain", "git worktree list holds both entries", paths(worktrees(root)) == [root, target], str(paths(worktrees(root))))
    status = git(root, "status", "--porcelain").stdout
    check("root_plain", "unignored .pi/ is reported untracked", "?? .pi/" in status, status.strip())
    check("root_plain", "repository .gitignore untouched", not (root / ".gitignore").exists())


def case_subdirectory_anchor(base: Path, ctx: dict) -> None:
    repo = make_repo(base / "repo", commits=2, subdir="packages/app", branches=("feature/foo",))
    root = repo["root"]
    shell_cwd = root / "packages" / "app"
    run = run_pi(base, shell_cwd, "git worktree add ../foo feature/foo", **ctx)
    record_cli("subdirectory_anchor", run, "git worktree add ../foo feature/foo", expect_enter=True)
    target = managed(root, "foo")
    check_moved("subdirectory_anchor", root, target)
    check("subdirectory_anchor", "worktree anchors to the repository root", target.is_dir(), str(target))
    check("subdirectory_anchor", "branch is feature/foo", git(target, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature/foo")
    check("subdirectory_anchor", "no .pi inside the shell directory", not (shell_cwd / ".pi").exists())
    check("subdirectory_anchor", "no worktree in the shell-relative parent", not (shell_cwd.parent / "foo").exists())
    check("subdirectory_anchor", "no worktree next to the repository", not (root.parent / "foo").exists())
    check("subdirectory_anchor", "main checkout unchanged", (root / "tracked.txt").read_text(encoding="utf-8") == "commit-2\n")


def case_options_preserved(base: Path, ctx: dict) -> None:
    repo = make_repo(base / "repo", commits=2)
    root = repo["root"]
    command = 'git worktree add --lock --reason "active task" -b feature/locked ../locked HEAD~1'
    run = run_pi(base, root, command, **ctx)
    record_cli("options_preserved", run, command, expect_enter=True)
    target = managed(root, "locked")
    check_moved("options_preserved", root, target)
    check("options_preserved", "worktree lands in .pi/worktrees", target.is_dir(), str(target))
    entry = next((item for item in worktrees(root) if item["path"] == target), None)
    check("options_preserved", "worktree exists in the list", entry is not None)
    if entry:
        check("options_preserved", "--lock survives", entry["locked"], str(entry))
        check("options_preserved", "--reason value survives", entry["reason"] == "active task", str(entry["reason"]))
        check("options_preserved", "-b branch survives", entry["branch"] == "feature/locked", str(entry["branch"]))
        check("options_preserved", "HEAD~1 positional survives", entry["head"] == repo["first"], f"{entry['head']} != {repo['first']}")
    check("options_preserved", "checkout is the older commit", (target / "tracked.txt").read_text(encoding="utf-8") == "base\n")


def case_quoted_space(base: Path, ctx: dict) -> None:
    repo = make_repo(base / "repo", commits=1, branches=("feature/foo",))
    root = repo["root"]
    command = 'git worktree add "../feature branch" feature/foo'
    run = run_pi(base, root, command, **ctx)
    record_cli("quoted_space", run, command, expect_enter=True)
    target = managed(root, "feature branch")
    check_moved("quoted_space", root, target)
    check("quoted_space", "quoted path is one directory", target.is_dir(), str(target))
    check("quoted_space", "branch is feature/foo", git(target, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature/foo")
    check("quoted_space", "no sibling directory with the same spelling", not (root.parent / "feature branch").exists())
    check("quoted_space", "only the redirected directory exists", [p.name for p in (root / ".pi" / "worktrees").iterdir()] == ["feature branch"])


def case_no_checkout(base: Path, ctx: dict) -> None:
    repo = make_repo(base / "repo", commits=1, branches=("feature/lazy",))
    root = repo["root"]
    command = "git worktree add --no-checkout ../lazy feature/lazy"
    run = run_pi(base, root, command, **ctx)
    record_cli("no_checkout", run, command, expect_enter=True)
    target = managed(root, "lazy")
    check_moved("no_checkout", root, target)
    check("no_checkout", "worktree lands in .pi/worktrees", target.is_dir(), str(target))
    check("no_checkout", "--no-checkout leaves the tree empty", not (target / "tracked.txt").exists())
    check("no_checkout", "branch is feature/lazy", git(target, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature/lazy")


def case_detached(base: Path, ctx: dict) -> None:
    repo = make_repo(base / "repo", commits=2)
    root = repo["root"]
    command = "git worktree add --detach ../detached HEAD~1"
    run = run_pi(base, root, command, **ctx)
    record_cli("detached", run, command, expect_enter=True)
    target = managed(root, "detached")
    check_moved("detached", root, target)
    check("detached", "worktree lands in .pi/worktrees", target.is_dir(), str(target))
    check("detached", "checkout is the older commit", (target / "tracked.txt").read_text(encoding="utf-8") == "base\n")
    entry = next((item for item in worktrees(root) if item["path"] == target), None)
    check("detached", "--detach survives", bool(entry and entry["detached"]), str(entry and entry["branch"]))


def case_orphan(base: Path, ctx: dict) -> None:
    case = "orphan"
    if not orphan_supported():
        skip(case, "orphan creation", f"no --orphan in {git_version()}")
        return
    repo = make_repo(base / "repo", commits=1)
    root = repo["root"]
    command = "git worktree add --orphan ../topic"
    run = run_pi(base, root, command, **ctx)
    record_cli(case, run, command, expect_enter=True)
    target = managed(root, "topic")
    check_moved(case, root, target)
    check(case, "worktree lands in .pi/worktrees", target.is_dir(), str(target))
    check(case, "unborn branch is named topic", git(target, "symbolic-ref", "--short", "HEAD").stdout.strip() == "topic")
    check(case, "worktree has no commit yet", git(target, "rev-parse", "HEAD", expect_success=False).returncode != 0)


def case_already_managed(base: Path, ctx: dict) -> None:
    repo = make_repo(base / "repo", commits=1, branches=("feature/qux",))
    root = repo["root"]
    command = "git worktree add .pi/worktrees/qux feature/qux"
    run = run_pi(base, root, command, **ctx)
    record_cli("already_managed", run, command)
    target = managed(root, "qux")
    check("already_managed", "managed path is used once", target.is_dir(), str(target))
    check("already_managed", "no nested .pi/worktrees/.pi", not (root / ".pi" / "worktrees" / ".pi").exists())
    check("already_managed", "exactly one linked worktree", paths(worktrees(root)) == [root, target], str(paths(worktrees(root))))


def case_chained_untouched(base: Path, ctx: dict) -> None:
    repo = make_repo(base / "repo", commits=1, branches=("feature/chained",))
    root = repo["root"]
    command = "git worktree add ../chained feature/chained && git status --porcelain"
    run = run_pi(base, root, command, **ctx)
    record_cli("chained_untouched", run, command)
    check("chained_untouched", "literal path wins for unsupported syntax", (root.parent / "chained").is_dir())
    check("chained_untouched", "no managed directory was created", not (root / ".pi").exists())
    check("chained_untouched", "both linked worktrees are outside the repo", paths(worktrees(root)) == [root, root.parent / "chained"], str(paths(worktrees(root))))


def case_unknown_option_untouched(base: Path, ctx: dict) -> None:
    repo = make_repo(base / "repo", commits=1, branches=("feature/foo",))
    root = repo["root"]
    command = "git worktree add --unknown-option ../u feature/foo"
    run = run_pi(base, root, command, **ctx)
    calls = record_cli("unknown_option_untouched", run, command, expect_error=True)
    output = calls[0]["output"] if calls else ""
    check("unknown_option_untouched", "git reports the unknown option", "unknown option" in output, output.strip())
    check("unknown_option_untouched", "no managed directory was created", not (root / ".pi").exists())
    check("unknown_option_untouched", "no worktree was created", len(worktrees(root)) == 1, str(paths(worktrees(root))))


def case_list_untouched(base: Path, ctx: dict) -> None:
    repo = make_repo(base / "repo", commits=1, branches=("feature/foo",))
    root = repo["root"]
    command = "git worktree list --porcelain"
    run = run_pi(base, root, command, **ctx)
    calls = record_cli("list_untouched", run, command)
    output = calls[0]["output"] if calls else ""
    check("list_untouched", "porcelain output reaches the tool", str(root) in output, "")
    check("list_untouched", "no managed directory was created", not (root / ".pi").exists())


def case_outside_repository(base: Path, ctx: dict) -> None:
    outside = base / "outside"
    outside.mkdir(parents=True)
    command = "git worktree add ../o feature/o"
    run = run_pi(base, outside, command, **ctx)
    calls = record_cli("outside_repository", run, command, expect_error=True)
    output = calls[0]["output"] if calls else ""
    check("outside_repository", "git reports the missing repository", "not a git repository" in output, output.strip())
    leftover = outside / ".pi" / "worktrees"
    check("outside_repository", "failed add leaves only the relative managed directory", leftover.is_dir() and not any(leftover.iterdir()), str(leftover))
    check("outside_repository", "no worktree was created", not (outside.parent / "o").exists())


def case_ignored_pi_dir(base: Path, ctx: dict) -> None:
    repo = make_repo(base / "repo", commits=1, branches=("feature/ign",), gitignore=".pi/\n")
    root = repo["root"]
    before = (root / ".gitignore").read_bytes()
    command = "git worktree add ../ign feature/ign"
    run = run_pi(base, root, command, **ctx)
    record_cli("ignored_pi_dir", run, command, expect_enter=True)
    target = managed(root, "ign")
    check_moved("ignored_pi_dir", root, target)
    check("ignored_pi_dir", "worktree lands in .pi/worktrees", target.is_dir(), str(target))
    status = git(root, "status", "--porcelain").stdout
    check("ignored_pi_dir", "ignored .pi/ stays out of git status", status.strip() == "", repr(status))
    check("ignored_pi_dir", ".gitignore is byte-identical", (root / ".gitignore").read_bytes() == before)


def case_sibling_batch_blocked(base: Path, ctx: dict) -> None:
    """The headline claim on the real host: one batch cannot edit the old checkout.

    The fixture emits the creation together with a sibling write. The host must
    block that sibling before execution, so the parent checkout keeps no file
    while the session moves into the created worktree.
    """
    case = "sibling_batch_blocked"
    repo = make_repo(base / "repo", commits=1, branches=("feature/foo",))
    root = repo["root"]
    run = run_pi(
        base,
        root,
        "git worktree add ../foo feature/foo",
        extra_env={"PI_WORKTREE_FIXTURE_SIBLING_WRITE": "leaked.txt"},
        **ctx,
    )
    record_cli(case, run, "git worktree add ../foo feature/foo", expect_enter=True)
    target = managed(root, "foo")
    check_moved(case, root, target)
    sibling = next((item for item in tool_outcomes(run) if item["tool"] == "write"), None)
    blocked = bool(
        sibling and sibling["isError"] and "is already queued for this turn" in sibling["text"]
    )
    check(case, "the sibling write was blocked, not executed", blocked, str(sibling))
    check(case, "the parent checkout keeps no leaked file", not (root / "leaked.txt").exists())
    check(case, "the worktree keeps no leaked file", not (target / "leaked.txt").exists())


CASES = (
    case_root_plain,
    case_sibling_batch_blocked,
    case_subdirectory_anchor,
    case_options_preserved,
    case_quoted_space,
    case_no_checkout,
    case_detached,
    case_orphan,
    case_already_managed,
    case_chained_untouched,
    case_unknown_option_untouched,
    case_list_untouched,
    case_outside_repository,
    case_ignored_pi_dir,
)


def environment() -> dict:
    def first_line(*argv: str) -> str:
        result = subprocess.run(argv, capture_output=True, text=True, check=False)
        text = (result.stdout + result.stderr).strip()
        return text.splitlines()[0] if text else ""

    manifest = Path("/isolated/node_modules/@fradser/pi-utils/package.json")
    settings = Path(os.environ.get("PI_WORKTREE_AGENT_DIR", "/isolated/agent")) / "settings.json"
    return {
        "node": first_line("node", "--version"),
        "pi": first_line("pi", "--version"),
        "git": git_version(),
        "os": first_line("sh", "-c", '. /etc/os-release && printf %s "$PRETTY_NAME"'),
        "packagesInstalled": json.loads(settings.read_text(encoding="utf-8"))["packages"] if settings.is_file() else [],
        "utilsVersion": json.loads(manifest.read_text(encoding="utf-8"))["version"] if manifest.is_file() else "",
        "orphanOptionSupported": orphan_supported(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Real git worktree creation cases for the installed pi-utils redirect.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--work", default="/isolated/work", type=Path)
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
        # A case that raises must stay in the evidence instead of hiding the
        # cases behind it.
        try:
            case(work / case.__name__, context)
        except Exception as error:  # noqa: BLE001 - the report needs the cause
            check(case.__name__, "case completed without an unexpected error", False, f"{type(error).__name__}: {error}")

    evidence = {
        "environment": environment(),
        "observations": OBSERVATIONS,
        "results": RESULTS,
        "failed": FAILURES,
        "status": "passed" if not FAILURES else "failed",
    }
    (arguments.output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    summary = {
        "cases": len(CASES),
        "checks": len(RESULTS),
        "passed": sum(1 for item in RESULTS if item["ok"] is True),
        "skipped": sum(1 for item in RESULTS if item.get("skipped")),
        "failed": len(FAILURES),
        "status": evidence["status"],
    }
    print(json.dumps(summary))
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
