"""Workspace integration checks live at the repository seam, not inside a runtime package."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "packages" / "kit"
SRC = PACKAGE / "src"
CONSUMERS = ["agent-teams", "btw", "context", "continual-learning", "keyboard", "matt-pocock", "monitor", "plan-mode", "recap", "skill-router", "utils", "vision"]
CORE_PACKAGES = ("@earendil-works/pi-ai", "@earendil-works/pi-agent-core", "@earendil-works/pi-coding-agent", "@earendil-works/pi-tui", "typebox")
SPLIT_CHAIN = ("packages/kit", "packages/subagents", "packages/tasks", "packages/agent-teams")


def run_typescript(script: str) -> dict[str, object]:
    result = subprocess.run(["node", "--import", "tsx", "--input-type=module"], cwd=REPO, input=script,
                            capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
    return json.loads(result.stdout.strip().splitlines()[-1])


WIDGET_OPTION_KEYS = {"key", "placement", "fit", "activityFormat", "fallbackActivity", "leadingSpaces"}


def widget_option_blocks(text: str) -> list[str]:
    """Return brace-balanced arguments of shared widget registrations."""
    blocks: list[str] = []
    marker = "createLiveActivityWidget({"
    index = text.find(marker)
    while index >= 0:
        depth = 0
        for offset, char in enumerate(text[index + len(marker) - 1:], start=index + len(marker) - 1):
            depth += int(char == "{") - int(char == "}")
            if depth == 0:
                blocks.append(text[index + len(marker):offset])
                break
        index = text.find(marker, index + 1)
    return blocks


def option_keys(block: str) -> set[str]:
    keys: set[str] = set()
    depth = 0
    for line in block.splitlines():
        depth += line.count("{") + line.count("[") + line.count("(")
        depth -= line.count("}") + line.count("]") + line.count(")")
        match = re.match(r"\s*([A-Za-z_$][\w$]*)\s*:", line)
        if match and depth >= 0:
            keys.add(match.group(1))
    return keys


def test_no_consumer_supplies_its_own_widget_row_formatter() -> None:
    source = (SRC / "index.ts").read_text(encoding="utf-8")
    assert "formatIdentity" not in source
    assert "formatActivity" not in source
    assert 'PiLiveActivityTextFormat = "plain" | "markdown"' in source
    for consumer in CONSUMERS:
        for path in sorted((REPO / "packages" / consumer).rglob("*.ts")):
            text = path.read_text(encoding="utf-8")
            assert "formatIdentity" not in text, f"{path}: identity formatting belongs to pi-kit"
            assert "formatActivity" not in text, f"{path}: activity formatting belongs to pi-kit"
            # A renamed restyle hook would still be a restyle hook: the widget
            # options are a closed vocabulary, so every mount is checked by key.
            # A source scan cannot prove "no second activity renderer" — recap,
            # plan-mode, and btw legitimately parse Markdown for overlay panels
            # in the same file — so that guarantee is behavioral instead: the
            # widget takes an activity *string* plus a format, and the fixture
            # proves a pre-styled activity cannot restyle a row.
            for options in widget_option_blocks(text):
                unknown = option_keys(options) - WIDGET_OPTION_KEYS
                assert not unknown, f"{path}: createLiveActivityWidget got unsupported options {sorted(unknown)}"


def test_no_consumer_labels_a_tool_call_without_the_shared_classifier() -> None:
    # A consumer that reacts to tool_execution_start and names the call must use
    # pi-kit's classifier, so the pattern-before-path rule cannot drift back into
    # a per-package copy. The precedence itself is covered behaviorally by
    # test_tool_activity_classification_prefers_a_search_pattern_over_its_root.
    for consumer in CONSUMERS:
        for path in sorted((REPO / "packages" / consumer).rglob("*.ts")):
            # Test fixtures legitimately emit raw tool events; this checks the
            # implementation files that label them.
            if {"tests", "fixtures"} & set(path.parts):
                continue
            text = path.read_text(encoding="utf-8")
            if "tool_execution_start" not in text:
                continue
            assert "classifyToolActivity" in text, f"{path}: tool-call labeling belongs to pi-kit"


def test_every_core_use_is_declared_as_a_star_peer() -> None:
    """pi's package guide: a bundled core package you use is a `"*"` peer, never
    an undeclared import resolved by hoisting and never a bundled dependency.
    `import type` counts: pi packages ship TypeScript source, so a consumer's
    type-checker must resolve it too."""
    for manifest_path in sorted((REPO / "packages").glob("*/package.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        used: set[str] = set()
        for path in manifest_path.parent.rglob("*.ts"):
            if "tests" in path.parts or "node_modules" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for package in CORE_PACKAGES:
                if re.search(rf'(?:from|import\(|import\.meta\.resolve\()\s*"{re.escape(package)}"', text):
                    used.add(package)
        declared = manifest.get("peerDependencies", {})
        missing = {package for package in used if declared.get(package) != "*"}
        assert not missing, f"{manifest_path}: used but not a \"*\" peer: {sorted(missing)}"
        bundled = sorted(set(CORE_PACKAGES) & set(manifest.get("dependencies", {})))
        assert not bundled, f"{manifest_path}: pi bundles core packages; do not ship them as dependencies: {bundled}"


def test_consumers_declare_kit_as_workspace_dependency() -> None:
    for consumer in CONSUMERS:
        manifest = json.loads((REPO / "packages" / consumer / "package.json").read_text(encoding="utf-8"))
        assert manifest.get("dependencies", {}).get("@fradser/pi-kit") == "workspace:*", (
            f"{consumer} must depend on @fradser/pi-kit via workspace:* under dependencies"
        )
        assert "@fradser/pi-kit" not in manifest.get("peerDependencies", {}), (
            f"{consumer} must not declare @fradser/pi-kit as a peer dependency"
        )


def test_packed_consumers_resolve_workspace_protocol_dependencies() -> None:
    feature = (PACKAGE / "features" / "pi-kit.feature").read_text(encoding="utf-8")
    assert "Consumer packages resolve workspace dependency protocols when packed" in feature
    # Reuse only the preinstalled CLI. Corepack otherwise treats isolated HOME
    # as an empty cache and attempts a download during a registry-free check.
    from importlib.util import module_from_spec, spec_from_file_location
    helper_file = REPO / "tests" / "install-wiring" / "install_wiring_helper.py"
    spec = spec_from_file_location("kit_install_wiring_helper", helper_file)
    assert spec and spec.loader
    helper = module_from_spec(spec)
    import sys
    sys.modules[spec.name] = helper
    spec.loader.exec_module(helper)
    pnpm = [helper.executable("pnpm")]
    if pnpm[0].endswith("pnpm.cjs"):
        pnpm.insert(0, helper.executable("node"))
    temp_dir = tempfile.mkdtemp(prefix="kit-pack-test-")
    try:
        for consumer in ("matt-pocock", "agent-teams", "vision"):
            output = subprocess.check_output(
                [*pnpm, "--dir", str(REPO / "packages" / consumer), "pack", "--pack-destination", temp_dir],
                text=True,
            )
            tarball_match = re.search(r"([^\s]+\.tgz)", output)
            assert tarball_match, f"Could not find tarball in output: {output}"
            tarball_path = tarball_match.group(1)
            pkg_json = subprocess.check_output(
                ["tar", "-xOf", tarball_path, "package/package.json"],
                text=True,
            )
            packed_manifest = json.loads(pkg_json)
            dep = packed_manifest.get("dependencies", {}).get("@fradser/pi-kit")
            assert dep and not dep.startswith("workspace:"), (
                f"{consumer} packed dependency must not use workspace protocol: {dep}"
            )
            assert re.match(r"^\d+\.\d+\.\d+", dep), (
                f"{consumer} packed dependency must be semver version: {dep}"
            )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_the_split_dependency_chain_resolves_one_pi_core_version() -> None:
    """One core version across the chain whose packages import each other.

    This has bitten three times: each newly added package resolved `"*"` to the
    latest core while every existing consumer stayed on the version the lockfile
    was first written against. It was tolerable only while nothing crossed a
    package boundary with core types, and it is not harmless — `addedToolNames`
    exists in pi-agent-core 0.84.1 and 0.85.1 but was removed in 0.87.1, so a
    package resolving 0.87.1 fails to typecheck code written against 0.84.

    Development dependencies select the root cohort through pnpm; wildcard
    published peers do not select a verification version by themselves. Run the
    package-manager operation rather than editing resolved lockfile entries.
    """
    lock = (REPO / "pnpm-lock.yaml").read_text(encoding="utf-8")
    importers = lock.split("importers:", 1)[1].split("\nsnapshots:", 1)[0]
    found: dict[str, dict[str, str]] = {}
    for block in re.split(r"\n  (?=\S)", importers):
        lines = block.strip().splitlines()
        if not lines:
            continue
        name = lines[0].strip().rstrip(":")
        if name not in SPLIT_CHAIN:
            continue
        found[name] = dict(re.findall(
            r"'(@earendil-works/pi-[a-z-]+)':\n\s+specifier: [^\n]+\n\s+version: ([\d.]+)", block
        ))
    assert set(found) == set(SPLIT_CHAIN), f"missing importers: {sorted(set(SPLIT_CHAIN) - set(found))}"
    for package in sorted({core for versions in found.values() for core in versions}):
        resolved = {name: versions[package] for name, versions in found.items() if package in versions}
        assert len(set(resolved.values())) == 1, (
            f"{package} resolves differently across the split chain: {resolved}. "
            f"Align the new package to the cohort in pnpm-lock.yaml."
        )


def test_publish_allowlist_orders_kit_before_consumers() -> None:
    script = (REPO / "scripts" / "publish-release.mjs").read_text(encoding="utf-8")
    kit_position = script.index('"@fradser/pi-kit"')
    assert kit_position > 0, "publish allowlist must include @fradser/pi-kit"
    for name in ['"@fradser/pi-agent-teams"', '"@fradser/pi-btw"', '"pi-continual-learning"',
                 '"@fradser/pi-recap"', '"@fradser/pi-utils"', '"@fradser/pi-vision"',
                 '"@fradser/pi-plan-mode"']:
        assert script.index(name) > kit_position, f"pi-kit must publish before {name}"


def test_publish_allowlist_orders_split_layers_before_their_consumer() -> None:
    """agent-teams' packed manifest depends on both extracted layers at exact
    versions, so neither may publish after it."""
    script = (REPO / "scripts" / "publish-release.mjs").read_text(encoding="utf-8")
    teams = script.index('"@fradser/pi-agent-teams"')
    for name in ('"@fradser/pi-kit"', '"@fradser/pi-subagents"', '"@fradser/pi-tasks"'):
        assert script.index(name) < teams, f"{name} must publish before @fradser/pi-agent-teams"


def test_pending_changesets_reference_workspace_package_names() -> None:
    workspace_names = {
        json.loads(manifest.read_text(encoding="utf-8"))["name"]
        for manifest in (REPO / "packages").glob("*/package.json")
    }
    changeset_files = (REPO / ".changeset").glob("*.md")

    for changeset_file in changeset_files:
        contents = changeset_file.read_text(encoding="utf-8")
        if not contents.startswith("---\n"):
            continue
        frontmatter = contents.split("---", 2)[1]
        declared_names = [line.split('"', 2)[1] for line in frontmatter.splitlines() if line.startswith('"')]
        unknown_names = set(declared_names) - workspace_names
        assert not unknown_names, f"{changeset_file.name} references unknown packages: {sorted(unknown_names)}"


def test_lifecycle_binding_unifies_rows_across_call_sites() -> None:
    result = run_typescript(
        f"""
        import {{ bindLifecycleRenderers, eventToolLifecycle }} from {json.dumps((SRC / "index.ts").as_uri())};
        const theme = {{ fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text }};
        const rows = bindLifecycleRenderers({{
          fit: (text, width) => text,
          visibleWidth: (text) => text.length,
          wrapDetail: (line) => [line],
          expandHint: "ctrl+o to expand",
        }});
        const first = rows.result(() => eventToolLifecycle("monitor", "nightly", {{ label: "started", details: ["command · make check"] }}));
        const second = rows.result(() => eventToolLifecycle("sessions", "two items", {{ label: "listed", details: ["a", "b"] }}));
        const message = rows.message(() => eventToolLifecycle("learning", "done", {{ label: "event", details: ["policy · allow"] }}), {{ cwd: "/repo" }});
        const collapsed = first({{ content: [] }}, {{ expanded: false }}, theme, {{}}).render(200).join("\\n");
        const empty = rows.emptyCall();
        console.log(JSON.stringify({{
          first: first({{ content: [] }}, {{ expanded: true }}, theme, {{}}).render(200).join("\\n"),
          second: second({{ content: [] }}, {{ expanded: true }}, theme, {{}}).render(200).join("\\n"),
          message: message({{ content: "done", details: {{}} }}, {{ expanded: true }}, theme).render(200).join("\\n"),
          collapsed: collapsed,
          empty: empty.render(200),
        }}));
        """
    )
    assert "[monitor] started · nightly · ctrl+o to expand" in result["collapsed"]
    assert "command · make check" in result["first"]
    assert "[sessions] listed · two items" in result["second"]
    assert "\n a\n b" in result["second"]
    assert "[learning] event · done" in result["message"]
    assert "policy · allow" in result["message"]
    assert result["empty"] == []


def test_the_roster_imports_no_consumer_package() -> None:
    """A consumer import would make the execution layer un-installable alone, and
    would close the cycle the three-package split exists to keep open.

    That covers the tasks as much as the team runtime: a child roster has no
    business importing a task domain, and an execution layer that names one makes
    every install drag the tasks along.
    """
    forbidden = ("@fradser/pi-agent-teams", "pi-agent-teams", "@fradser/pi-tasks", "pi-tasks")
    source = REPO / "packages" / "subagents" / "src"
    assert (source / "child-execution.ts").is_file(), "The guard must scan the subagent execution layer (child-execution.ts)."
    for module in sorted(source.glob("*.ts")):
        text = module.read_text(encoding="utf-8")
        for spec in re.findall(r'from\s+"([^"]+)"', text):
            for name in forbidden:
                assert name not in spec, f"{module.name} imports {spec}"


def test_the_roster_describes_what_a_holder_holds_itself() -> None:
    """The direction that is allowed is also the one that is not taken.

    Nothing here imports the task domain, so what a holder holds is described
    structurally, in the shape the published registry hands over. A roster that
    named the tasks's type would make the execution layer depend on the tasks for a
    field it stores rather than reads — and would put the dependency the wrong way
    round for the two packages whose whole split is that neither knows the other's
    shape. Asserted against the source so a future convenience import cannot
    reintroduce it quietly.
    """
    text = (REPO / "packages" / "subagents" / "src" / "roster.ts").read_text(encoding="utf-8")
    # Imports, not prose: the module documents the boundary in terms of the tasks
    # by name, and naming it in a comment is how the boundary is explained.
    imports = re.findall(r'from\s+"([^"]+)"', text)
    assert not any("pi-tasks" in spec for spec in imports), imports
    assert "WorkAssignment" not in text
    assert 'from "./participant-registry.ts"' in text
    registry_imports = re.findall(r'from\s+"([^"]+)"', (REPO / "packages" / "subagents" / "src" / "participant-registry.ts").read_text(encoding="utf-8"))
    assert not any("pi-tasks" in spec for spec in registry_imports), registry_imports


@pytest.mark.parametrize("declared", ["demo", "missing-package"])
def test_changeset_name_guard_checks_real_frontmatter(tmp_path: Path, monkeypatch, declared: str) -> None:
    package = tmp_path / "packages" / "demo"
    package.mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({"name": "demo"}))
    changesets = tmp_path / ".changeset"
    changesets.mkdir()
    (changesets / "example.md").write_text(f'---\n"{declared}": patch\n---\nExample change.\n')
    monkeypatch.setattr(sys.modules[__name__], "REPO", tmp_path)
    if declared == "demo":
        test_pending_changesets_reference_workspace_package_names()
    else:
        with pytest.raises(AssertionError, match="missing-package"):
            test_pending_changesets_reference_workspace_package_names()
