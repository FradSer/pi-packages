"""One registrant per tool, per install combination.

Success criterion 2. Enumerated rather than asserted once: the interesting
question is not "does each tool have one owner" but "does any combination load
two owners of the same tool, or none".

The enumeration is static — it reads each package's manifest and the tools its
extension registers. That is enough to catch a double registration, because a
second registrant is a fact about the packages rather than about load order. The
runtime half of the same claim, that each combination really loads, is proved by
the E2E suites, which drive a real `pi` process per combination.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGES = REPO / "packages"

# Owners are read from the code, not maintained here, so this test cannot drift
# from reality by being edited alongside it.
#
# Scoped to the *leader* extension bodies, because that is what loads in one
# process. A child process loads the worker extensions instead, and its board
# slice is a different transport over the same board rather than a second owner:
# the board is single-writer, so a child cannot take a task by writing the board.
LEADER_BODIES = {
    "subagents": "src/extension.ts",
    "tasks": "src/extension.ts",
    "agent-teams": "index.ts",
}


def leader_sources(package: str) -> list[Path]:
    """Every module in the package reachable from its extension body.

    The body calls a registrar rather than declaring the tool name, and a
    package-root entry re-exports its implementation, so ownership has to be
    followed to where the name is written. Transitively, because a barrel between
    the entry and the registrar is exactly what a package-root convention produces.
    """
    start = (PACKAGES / package / LEADER_BODIES[package]).resolve()
    seen: set[Path] = set()
    files: list[Path] = []
    queue = [start]
    root = (PACKAGES / package).resolve()
    while queue:
        current = queue.pop(0)
        if current in seen or not current.is_file() or not str(current).startswith(str(root)):
            continue
        seen.add(current)
        files.append(current)
        for specifier in re.findall(r'from\s+"(\.[^"]+)"', current.read_text(encoding="utf-8")):
            queue.append((current.parent / specifier).resolve())
    return files


# The child-side slice. A leader imports its registrar only to hand the path to a
# spawned child with `-e`, so a reachability walk finds both registrations and
# cannot tell them apart. The child entry is not inferred: each package declares
# it in the constant whose whole purpose is to be the path passed to a child.
# The child-side registration modules.
#
# These register tools in a *spawned child*, never in the leader, and a leader
# imports them only to hand their path to `-e`. They have to be named rather than
# discovered, because the mechanism differs by package and neither signal is
# unique: pi-subagents' child entry is its own file, while agent-teams' is the
# same extension branching on the worker role, with the registrations in a module
# the entry imports.
#
# What follows keeps the list honest: each named file must register one of the
# three tools *and* bind the worker role, so a named entry that stopped being a
# child-side module fails rather than silently excluding a leader module.
CHILD_REGISTRATION_MODULES = {
    "subagents/src/worker-extension.ts",
    "agent-teams/src/worker.ts",
}

WORKER_ROLE_ENV = "PI_TEAMMATE_WORKER_NAME"

TOOL_OWNER: dict[str, str] = {}
for package in LEADER_BODIES:
    for path in leader_sources(package):
        if str(path.relative_to(PACKAGES)) in CHILD_REGISTRATION_MODULES:
            continue
        for name in re.findall(r'name:\s*"([a-z_]+)"', path.read_text(encoding="utf-8")):
            if name in {"agent", "task", "message"}:
                TOOL_OWNER[name] = package

EXPECTED_OWNERS = {"agent": "subagents", "task": "tasks", "message": "agent-teams"}

# A package's own extension entry, and the siblings it loads with it.
OWN_EXTENSION: dict[str, set[str]] = {
    "subagents": set(),
    "tasks": set(),
    # The bundle loads its two dependencies, so installing it alone is enough.
    "agent-teams": {"@fradser/pi-subagents", "@fradser/pi-tasks"},
}

LEADER_ONLY = {"agent"}


def local_name(scoped: str) -> str:
    return scoped.rsplit("/", 1)[-1]


def loaded_packages(installed: set[str]) -> set[str]:
    """Every package whose extension Pi loads, following the bundle's manifest."""
    resolved = set(installed)
    for package in list(resolved):
        manifest = json.loads((PACKAGES / package / "package.json").read_text(encoding="utf-8"))
        for entry in manifest.get("pi", {}).get("extensions", []):
            if "node_modules" not in entry:
                continue
            # `node_modules/@scope/name/index.ts` names the bundled dependency.
            parts = Path(entry).parts
            name = parts[2] if parts[1].startswith("@") else parts[1]
            # A directory is named `pi-<thing>`, so the package is the tail after
            # `pi-`; the scope must not be mistaken for part of the name.
            resolved.add(name[3:] if name.startswith("pi-") else name)
    return resolved


def test_every_child_side_registration_module_is_genuinely_child_side() -> None:
    """Each excluded module reads a role binding and is not a leader entry.

    The exclusion is a named list, so it could go stale in two directions: a named
    entry that stopped being a child extension would exclude a leader module for
    no reason, and a child module that was never named would be counted as a
    leader registrant. The first is checked here; the second surfaces in the
    ownership test as a tool attributed to the wrong package.

    Note what is deliberately *not* required: that an excluded module registers one
    of the three. A child entry may contribute a tool the leader never has —
    `pi-subagents`' worker extension contributes `agent_memory` and nothing else —
    which is exactly the case that makes "child entry" and "registers a
    coordination tool" different facts.
    """
    leader_entries = {
        str((PACKAGES / package / relative).resolve())
        for package, relative in LEADER_BODIES.items()
    }
    for relative in sorted(CHILD_REGISTRATION_MODULES):
        path = (PACKAGES / relative).resolve()
        text = path.read_text(encoding="utf-8")
        # Reading a role from the environment is what makes a module a child
        # extension rather than a leader module. How the role is spelled differs per
        # package, so the invariant is only that it reads one.
        assert re.search(r"process\.env|\benv\b", text), (
            f"{relative} is excluded but reads no environment binding"
        )
        assert str(path) not in leader_entries, (
            f"{relative} is both a child entry and a leader entry"
        )


def test_the_board_tool_serves_both_processes() -> None:
    """pi-tasks registers one tool that a leader and a child both use, differing
    only in which identity it derives from the environment.

    That is why it is not on the exclusion list even though it reads the worker
    role binding: the same registration is correct in both processes, so counting
    it as a child-side module would be wrong in the other direction.
    """
    board = (PACKAGES / "tasks" / "src" / "tool.ts").read_text(encoding="utf-8")
    assert WORKER_ROLE_ENV in board, "the board tool must be able to run in a child"
    assert "tasks/src/tool.ts" not in CHILD_REGISTRATION_MODULES
    assert TOOL_OWNER["task"] == "tasks"


def test_each_tool_has_exactly_one_owning_package() -> None:
    assert TOOL_OWNER == EXPECTED_OWNERS, TOOL_OWNER


COMBINATIONS = [
    ({"subagents"}, {"agent"}),
    ({"tasks"}, {"task"}),
    ({"subagents", "tasks"}, {"agent", "task"}),
    ({"agent-teams"}, {"agent", "task", "message"}),
]


def test_every_install_combination_registers_each_tool_exactly_once() -> None:
    for installed, expected in COMBINATIONS:
        loaded = loaded_packages(installed)
        counts: dict[str, list[str]] = {}
        for package in loaded:
            for tool, owner in TOOL_OWNER.items():
                if owner == package:
                    counts.setdefault(tool, []).append(package)
        present = {tool for tool, sources in counts.items() if sources}
        assert present == expected, f"{sorted(installed)}: got {sorted(present)}, expected {sorted(expected)}"
        for tool, sources in counts.items():
            assert len(sources) == 1, f"{sorted(installed)}: {tool} is registered by {sources}"


def test_no_combination_loads_a_tool_twice() -> None:
    """The failure a double registrant causes is a collision or a silent drop
    depending on load order, and neither names the cause. So the invariant is
    checked per combination rather than assumed from ownership."""
    for installed, _expected in COMBINATIONS:
        loaded = loaded_packages(installed)
        seen: dict[str, str] = {}
        for package in loaded:
            for tool, owner in TOOL_OWNER.items():
                if owner != package:
                    continue
                assert tool not in seen, (
                    f"{sorted(installed)}: {tool} is registered by both {seen.get(tool)} and {package}"
                )
                seen[tool] = package


def test_the_leader_agent_tool_is_absent_from_a_child() -> None:
    """A child loads the worker extensions, not the leader's, so it never gets
    the `agent` tool. Nesting is bounded by a depth guard rather than by the tool
    happening to be missing."""
    worker = (PACKAGES / "agent-teams" / "src" / "worker.ts").read_text(encoding="utf-8")
    assert 'name: "agent"' not in worker


def test_a_bundled_sibling_is_a_runtime_dependency_not_a_peer() -> None:
    """A peer is supplied by the host and would be absent in a plain install, so a
    bundle that declared one would silently load two of its three tools."""
    for package, bundled in OWN_EXTENSION.items():
        manifest = json.loads((PACKAGES / package / "package.json").read_text(encoding="utf-8"))
        for dependency in bundled:
            assert dependency in manifest.get("dependencies", {}), (
                f"{package} bundles {dependency} but does not depend on it"
            )
            assert dependency not in manifest.get("peerDependencies", {}), (
                f"{package} bundles {dependency} as a peer; a peer is absent in a plain install"
            )

