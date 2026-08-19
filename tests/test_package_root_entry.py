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
    "memory",
    "monitor",
    "recap",
    "utils",
    "vision",
}


def read_manifest(package: str) -> dict[str, object]:
    return json.loads((PACKAGES / package / "package.json").read_text(encoding="utf-8"))


def test_feature_covers_package_root_entry_contract() -> None:
    feature = (REPO / "features" / "package-root-entry.feature").read_text(encoding="utf-8")
    assert "Every runtime package declares the package-root entry" in feature
    assert "Multi-module packages compose registration through the root entry" in feature
    assert "Skill-only packages keep a skill-only manifest" in feature


def test_all_runtime_packages_use_root_index_entry() -> None:
    for package in sorted(RUNTIME_PACKAGES):
        package_dir = PACKAGES / package
        manifest = read_manifest(package)
        assert manifest["pi"]["extensions"] == ["./index.ts"]
        assert (package_dir / "index.ts").is_file()
        assert "index.ts" in manifest["files"]


def test_pi_kit_uses_root_export_without_becoming_a_pi_extension() -> None:
    manifest = read_manifest("pi-kit")
    assert "pi" not in manifest
    assert manifest["exports"] == {".": "./index.ts"}
    assert (PACKAGES / "pi-kit" / "index.ts").is_file()
    assert "index.ts" in manifest["files"]


def test_skill_only_package_does_not_gain_an_extension_entry() -> None:
    manifest = read_manifest("mattpocock")
    assert manifest["pi"] == {"skills": ["./skills/engineering", "./skills/productivity"]}
    assert not (PACKAGES / "mattpocock" / "index.ts").exists()
