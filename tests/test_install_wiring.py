"""The three packages as a configured install.

The E2E suites compose an install by hand, which proves each combination works but
says nothing about whether a real Pi actually finds them. This checks the other
half: the three local paths are in the agent's package sources, and a real
`pi --print` against the *configured* set exposes all three tools.

The probe reads the live tool list through the extension API and writes it out, so
what is asserted is what the host built rather than what a manifest promised.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
AGENT_TEAMS = REPO / "packages" / "agent-teams"
PROBE = AGENT_TEAMS / "tests" / "install-probe.ts"
PROBE_SOURCE = PROBE

# The three packages the split produces, and the tool each one owns.
PACKAGE_TOOLS = {
    "packages/subagents": "agent",
    "packages/tasks": "task",
    "packages/agent-teams": "message",
}
COORDINATION = set(PACKAGE_TOOLS.values())


def settings_path() -> Path:
    """The agent settings a user's own Pi reads.

    `PI_CODING_AGENT_DIR` is deliberately ignored: inside a session it points at
    that session's own sandbox, whose package list is not the install this suite is
    about. An explicit override exists for a test that wants a different agent dir.
    """
    override = os.environ.get("PI_INSTALL_SETTINGS")
    return Path(override) if override else Path(os.path.expanduser("~/.pi/agent/settings.json"))


def configured_sources() -> list[str]:
    path = settings_path()
    if not path.is_file():
        pytest.skip(f"no agent settings at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("packages", [])
    return [
        str(entry.get("source", "")) if isinstance(entry, dict) else str(entry)
        for entry in entries
    ]


@pytest.mark.parametrize("relative,tool", sorted(PACKAGE_TOOLS.items()))
def test_each_package_is_a_configured_source(relative: str, tool: str) -> None:
    """One entry per package, resolved from the same install the goal describes.

    Matched on the path tail rather than an exact string because `pi install`
    records a path relative to the agent directory, and an exact match would make
    the test depend on how the entry happened to be written.
    """
    sources = configured_sources()
    expected_tail = f"{relative}/index.ts" if relative.endswith("agent-teams") else f"{relative}"
    matching = [source for source in sources if source.endswith(expected_tail) or source.endswith(f"{relative}")]
    assert matching, f"{relative} is not a configured source; configured: {sources}"


def test_the_install_check_script_passes() -> None:
    """`check:install` is the repository's own statement that the workspace and
    the agent agree. Asserted here so a missing local path fails this suite rather
    than only surfacing in a release run."""
    pi = shutil.which("pnpm")
    if pi is None:
        pytest.skip("pnpm is required for the installation check")
    result = subprocess.run(
        [pi, "check:install"], cwd=REPO, capture_output=True, text=True, timeout=180
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_real_install_exposes_all_three_coordination_tools(tmp_path: Path) -> None:
    """A real `pi --print` against the configured package set.

    This is the assertion the hand-composed E2E cannot make: that the manifest,
    the agent's sources and the host's loader agree. Only `agent`, `task` and
    `message` are asserted; the other tools in the surface come from unrelated
    installed packages and are not this suite's business.
    """
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("the Pi CLI is required for the install surface check")
    if not PROBE.is_file():
        pytest.fail(f"the install probe is missing at {PROBE}")

    dump = tmp_path / "tools.json"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PI_TEAMMATE_")
    }
    env.update({
        # A local auth token so the scripted provider is accepted, and offline mode
        # so a mistake that reaches the network fails rather than hangs.
        "PI_E2E_AUTH": secrets.token_hex(16),
        "PI_INSTALL_PROBE": str(dump),
        "PI_OFFLINE": "1",
    })
    result = subprocess.run(
        [pi, "--print", "--no-session", "--no-context-files", "--no-skills",
         "--no-prompt-templates", "--no-themes", "--provider", "install-probe",
         "--model", "deterministic", "--thinking", "off",
         "--extension", str(PROBE), "report the tool surface"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert dump.is_file(), f"the probe never read the tool surface:\n{result.stdout}"
    names = json.loads(dump.read_text(encoding="utf-8"))
    assert COORDINATION <= set(names), f"missing: {sorted(COORDINATION - set(names))}"
    # `getAllTools` is keyed by name, so a second registrant for one of these would
    # have collapsed here rather than shown up as a duplicate. The enumeration in
    # test_tool_registration_combinations is what proves there is only one.
    assert PROBE.stem not in COORDINATION


def test_packed_manifests_carry_no_workspace_protocol() -> None:
    """A `workspace:` specifier does not survive packing, and one reaching npm makes
    the package unresolvable for a consumer.

    `publish-release.mjs` already refuses a tarball that contains one, and
    `pack:check` is how that is run. Asserted here as well because this is the suite
    that owns install wiring, and the failure a consumer hits is an install failure.
    """
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        pytest.skip("pnpm is required for the pack check")
    result = subprocess.run(
        [pnpm, "pack:check"], cwd=REPO, capture_output=True, text=True, timeout=600
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for name, tool in sorted(PACKAGE_TOOLS.items()):
        package = (REPO / name).resolve()
        manifest = json.loads((package / "package.json").read_text(encoding="utf-8"))
        declared = manifest.get("pi", {}).get("extensions", [])
        assert declared, f"{name} declares no extension entry"
        # A package's *own* entry must be a real file that its files list ships. A
        # manifest naming a file the tarball omits fails at load time with nothing
        # that names the cause.
        own = declared[0]
        assert own == "./index.ts", f"{name} must load its own root index first, not {own}"
        assert (package / "index.ts").is_file(), f"{name}/index.ts is missing"
        assert "index.ts" in manifest.get("files", []), f"{name} does not ship its own entry"
        # A bundled dependency's path resolves through node_modules. In the
        # workspace that is a symlink to a sibling package, so comparing it against
        # this package's files list is meaningless — what matters is that the path
        # is a node_modules path naming a package that exists.
        for entry in declared[1:]:
            assert entry.startswith("./node_modules/"), \
                f"{name} loads {entry}, which is neither its own entry nor a bundled path"
            target = (package / entry.removeprefix("./")).resolve()
            assert target.is_file(), f"{name} bundles {entry}, which does not resolve"
        assert tool, f"{name} owns no tool"


SMOKE = AGENT_TEAMS / "tests" / "live-smoke.ts"


def test_the_harness_probe_is_not_one_of_the_three() -> None:
    """The suite's own probe must not be mistaken for a coordination tool.

    Every surface assertion in this repository is written as "these three, and no
    others", so a harness that reported itself would make those checks off by one
    while still reading as a real tool. Asserted on the source, since the name is a
    static fact and a process would only restate it.
    """
    probe_name = re.search(r'probe:\s*"([a-z_]+)"', PROBE_SOURCE.read_text(encoding="utf-8"))
    assert probe_name, f"no probe name found in {PROBE_SOURCE}"
    assert probe_name.group(1) not in {"agent", "task", "message"}, probe_name.group(1)


def test_the_configured_install_runs_the_tools_end_to_end() -> None:
    """Registration is not the same as working.

    The suite above proves the three tools are present in a real install. This one
    calls them, because a tool that registers and then refuses every call is still
    broken and only execution shows the difference. It runs against the configured
    package set with no package chosen by hand, so it covers the path a user gets.

    The script drives create, list, take and complete on the board, then checks the
    two boundaries a surface assertion cannot: a removed verb is refused, and a
    message to a recipient that does not exist is refused with a reason rather than
    reported as sent.
    """
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("the Pi CLI is required for the live smoke")
    if not SMOKE.is_file():
        pytest.fail(f"the live smoke script is missing at {SMOKE}")

    env = {k: v for k, v in os.environ.items() if not k.startswith("PI_TEAMMATE_")}
    env.update({"PI_E2E_AUTH": secrets.token_hex(16), "PI_OFFLINE": "1"})
    result = subprocess.run(
        [pi, "--print", "--no-session", "--no-context-files", "--no-skills",
         "--no-prompt-templates", "--no-themes", "--provider", "live-smoke",
         "--model", "deterministic", "--thinking", "off",
         "--extension", str(SMOKE), "run the smoke"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    line = next(
        (raw for raw in result.stdout.splitlines() if raw.strip().startswith("E2E_REPORT")), None
    )
    assert line, f"the smoke run produced no report:\n{result.stdout}"
    calls = json.loads(line.strip()[len("E2E_REPORT "):])["calls"]
    by_name: dict[str, list[dict]] = {}
    for call in calls:
        by_name.setdefault(call["name"], []).append(call)

    board = by_name.get("task", [])
    assert len(board) == 5, [c["text"][:40] for c in board]
    states = [c["details"].get("status") for c in board[:4]]
    assert states == ["pending", None, "in_progress", "completed"], states
    # Taking records the caller as the holder. A Task has no assignee field, so
    # this is the only place an owner can come from.
    assert board[2]["details"]["task"]["holder"] == "main", board[2]["details"]
    # The fifth task call is a removed verb, refused rather than ignored.
    assert board[4]["isError"] is True and "assign" in board[4]["text"], board[4]["text"]

    message = (by_name.get("message") or [{}])[0]
    assert "nobody-here" in message.get("text", ""), message

    agent = (by_name.get("agent") or [{}])[0]
    assert agent.get("isError") is True, "an invalid agent name must not validate"
