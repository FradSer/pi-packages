from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGES = REPO / "packages"
RUNTIME_PACKAGES = {
    "agent-teams",
    "btw",
    "context",
    "keyboard",
    "monitor",
    "continual-learning",
    "plan-mode",
    "recap",
    "utils",
    "vision",
    "skill-router",
}


def read_manifest(package: str) -> dict[str, object]:
    return json.loads((PACKAGES / package / "package.json").read_text(encoding="utf-8"))


def test_feature_covers_package_root_entry_contract() -> None:
    feature = (REPO / "features" / "package-root-entry.feature").read_text(encoding="utf-8")
    assert "Every runtime package declares the package-root entry" in feature
    assert "Multi-module packages compose registration through the root entry" in feature
    assert "A skill collection router declares the package-root entry" in feature


def test_all_runtime_packages_use_root_index_entry() -> None:
    for package in sorted(RUNTIME_PACKAGES):
        package_dir = PACKAGES / package
        manifest = read_manifest(package)
        assert manifest["pi"]["extensions"] == ["./index.ts"]
        assert (package_dir / "index.ts").is_file()
        assert "index.ts" in manifest["files"]


def test_kit_uses_root_export_without_becoming_a_pi_extension() -> None:
    manifest = read_manifest("kit")
    assert "pi" not in manifest
    assert manifest["exports"] == {".": "./index.ts"}
    assert (PACKAGES / "kit" / "index.ts").is_file()
    assert "index.ts" in manifest["files"]


def test_concise_workspace_directories_link_their_published_packages() -> None:
    feature = (REPO / "features" / "package-root-entry.feature").read_text(encoding="utf-8")
    assert "Package directories use concise names independently of npm package names" in feature

    continual_learning = read_manifest("continual-learning")
    kit = read_manifest("kit")
    assert continual_learning["name"] == "pi-continual-learning"
    assert kit["name"] == "@fradser/pi-kit"

    lockfile = (REPO / "pnpm-lock.yaml").read_text(encoding="utf-8")
    assert "packages/continual-learning:" in lockfile
    assert "packages/kit: {}" in lockfile
    assert "version: link:../kit" in lockfile


def test_git_agent_scopes_cover_the_current_package_layout() -> None:
    feature = (REPO / "features" / "package-root-entry.feature").read_text(encoding="utf-8")
    assert "Commit scopes describe the current package layout" in feature

    config = (REPO / ".git-agent" / "config.yml").read_text(encoding="utf-8")
    descriptions = [line.strip() for line in config.splitlines() if line.strip().startswith("description:")]
    current_packages = {path.name for path in PACKAGES.iterdir() if (path / "package.json").is_file()}
    scope_names = [line.strip().removeprefix("- name: ").strip() for line in config.splitlines() if line.strip().startswith("- name:")]
    described_packages = {
        package
        for package in current_packages
        if f"packages/{package}/" in config
    }

    assert described_packages == current_packages
    scope_names = [line.strip().removeprefix("- name: ").strip() for line in config.splitlines() if line.strip().startswith("- name:")]
    assert len(scope_names) == len(set(scope_names))
    assert all(len(name) <= 5 for name in scope_names)
    legacy_continual_learning = "packages/" + "pi-continual-learning/"
    legacy_kit = "packages/" + "pi-kit/"
    assert legacy_continual_learning not in config
    assert legacy_kit not in config
    assert all("packages/pi-" not in description for description in descriptions)
    assert "packages/" in config


def test_skill_router_is_a_runtime_package() -> None:
    manifest = read_manifest("skill-router")
    assert manifest["name"] == "pi-skill-router"
    assert manifest["pi"]["extensions"] == ["./index.ts"]
    assert "skills" not in manifest["pi"]
    assert (PACKAGES / "skill-router" / "index.ts").is_file()
    assert "index.ts" in manifest["files"]
