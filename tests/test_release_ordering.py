"""The release wiring for the three-package split.

Two things have to hold for `1.0.0` to be publishable, and neither is visible in
the source: the publish order, and the bump levels. Both are asserted here so a
future edit to either fails a test rather than producing a release that cannot be
consumed.

The order is a genuine constraint rather than tidiness. `@fradser/pi-agent-teams`
resolves its dependencies to exact versions at pack time, so if it reached the
registry before the two packages it bundles, a consumer installing the bundle
would get a manifest pointing at versions that do not exist yet.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGES = REPO / "packages"
CHANGESETS = REPO / ".changeset"
SCOPE = REPO / "scripts" / "publish-release.mjs"

# The four whose relative order is load-bearing: the two shared foundations, the
# domain, and the bundle that loads all three.
ORDER = ["@fradser/pi-kit", "@fradser/pi-subagents", "@fradser/pi-tasks", "@fradser/pi-agent-teams"]

# Bumps the split requires, and why.
REQUIRED_BUMPS = {
    # The tool names, parameters and action set all changed, so a consumer that
    # pinned the old surface needs to be told rather than surprised.
    "@fradser/pi-agent-teams": "major",
    # Both are new on the registry; the internal shape still moved.
    "@fradser/pi-subagents": "minor",
    "@fradser/pi-tasks": "minor",
    "@fradser/pi-kit": "minor",
}


def publish_scope() -> list[str]:
    text = SCOPE.read_text(encoding="utf-8")
    match = re.search(r"PUBLISH_SCOPE\s*=\s*Object\.freeze\(\[(.*?)\]\)", text, re.S)
    assert match, "PUBLISH_SCOPE not found in scripts/publish-release.mjs"
    return re.findall(r'"([^"]+)"', match.group(1))


def changesets() -> list[tuple[str, dict[str, str], str]]:
    """Every changeset as (filename, bumps, body)."""
    out: list[tuple[str, dict[str, str], str]] = []
    for path in sorted(CHANGESETS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
        if not match:
            continue
        bumps = {}
        for line in match.group(1).splitlines():
            entry = re.match(r'\s*"([^"]+)":\s*(\w+)\s*$', line)
            if entry:
                bumps[entry.group(1)] = entry.group(2)
        out.append((path.name, bumps, match.group(2)))
    return out


RANK = {"patch": 0, "minor": 1, "major": 2}


def effective_bump(package: str) -> str:
    """The highest bump any changeset asks for, which is what Changesets applies."""
    best = "patch"
    found = False
    for _name, bumps, _body in changesets():
        level = bumps.get(package)
        if not level:
            continue
        found = True
        if RANK[level] > RANK[best]:
            best = level
    return best if found else "none"


# ── Publish order ──


def test_the_publish_scope_holds_the_required_relative_order() -> None:
    scope = publish_scope()
    positions = []
    for name in ORDER:
        assert name in scope, f"{name} is missing from PUBLISH_SCOPE"
        positions.append(scope.index(name))
    assert positions == sorted(positions), (
        f"publish order is wrong: {dict(zip(ORDER, positions))}; "
        "a consumer could get a manifest pointing at versions that do not exist yet"
    )


def workspace_packages() -> dict[str, Path]:
    """Package name to its directory, read from the manifests.

    Not derived from the name: the published name carries a `pi-` the directory
    does not, so a convention would have invented a path that is not there. The
    manifests are the ground truth a publish step will use.
    """
    found: dict[str, Path] = {}
    for manifest in sorted(PACKAGES.glob("*/package.json")):
        found[json.loads(manifest.read_text(encoding="utf-8"))["name"]] = manifest.parent
    return found


def test_every_publish_scope_entry_is_a_real_workspace_package() -> None:
    """An entry naming a package that is not here is a publish step that cannot
    succeed, and it would be reached only during a release."""
    packages = workspace_packages()
    missing = [name for name in publish_scope() if name not in packages]
    assert missing == [], f"PUBLISH_SCOPE names packages that do not exist: {missing}"


def test_every_workspace_package_is_in_the_publish_scope() -> None:
    """The other direction: a package nobody publishes is a package whose changes
    never ship, and it is silent until someone notices a version that never moved."""
    missing = sorted(set(workspace_packages()) - set(publish_scope()))
    assert missing == [], f"workspace packages absent from PUBLISH_SCOPE: {missing}"


def test_the_bundle_declares_the_packages_it_loads() -> None:
    """The order only matters because the bundle depends on the other two at exact
    versions. A dependency that is a peer is supplied by the host and would be
    absent in a plain install."""
    manifest = json.loads((PACKAGES / "agent-teams" / "package.json").read_text(encoding="utf-8"))
    for name in ("@fradser/pi-subagents", "@fradser/pi-tasks"):
        assert name in manifest.get("dependencies", {}), f"{name} must be a runtime dependency"
        assert name not in manifest.get("peerDependencies", {}), f"{name} as a peer would be absent in an install"


# ── Bump levels ──


@pytest.mark.parametrize("package,required", sorted(REQUIRED_BUMPS.items()))
def test_the_split_ships_the_required_bump(package: str, required: str) -> None:
    assert RANK[effective_bump(package)] >= RANK[required], (
        f"{package} bumps to {effective_bump(package)}, which is below the required {required}"
    )


def test_the_breaking_release_names_what_a_caller_must_change() -> None:
    """A major bump with no migration is a breaking change announced as a fact.

    Checked against the changeset that carries the major, so a later release that
    raises the bump again does not inherit this one's wording silently.
    """
    major = [
        (name, body) for name, bumps, body in changesets()
        if bumps.get("@fradser/pi-agent-teams") == "major"
    ]
    assert major, "no changeset marks @fradser/pi-agent-teams as major"
    text = "\n".join(body for _name, body in major)
    for required in ("work` is now `task", "agent_event` is now `message", "recovery hold"):
        assert required in text, f"the breaking release does not mention: {required}"


def test_no_pending_changeset_claims_the_tool_surface_is_unchanged() -> None:
    """Two extraction changesets said `agent`, `work` and `agent_event` were
    identical. That was true of those steps and is false of the release, and
    shipping both would tell a consumer the opposite of what changed."""
    offenders: list[str] = []
    for name, _bumps, body in changesets():
        if re.search(r"no public tool surface changed", body, re.I):
            offenders.append(name)
    assert offenders == [], (
        f"these changesets claim the tool surface did not change: {offenders}"
    )
