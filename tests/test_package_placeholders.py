from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_pi_design_placeholder_manifest_and_release_scope() -> None:
    package_dir = REPO / "packages" / "pi-design"
    manifest = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
    release_script = (REPO / "scripts" / "publish-release.mjs").read_text(encoding="utf-8")

    assert manifest["name"] == "pi-design"
    assert manifest["version"] == "0.0.1"
    assert manifest["main"] == "./index.js"
    assert manifest["exports"] == {".": "./index.js"}
    assert "pi" not in manifest
    assert manifest["files"] == ["index.js", "README.md"]
    assert (package_dir / "index.js").read_text(encoding="utf-8") == "export {};\n"
    assert '"pi-design"' in release_script


def test_pi_artifact_is_not_a_placeholder() -> None:
    manifest = json.loads(
        (REPO / "packages" / "pi-artifact" / "package.json").read_text(encoding="utf-8")
    )
    assert (REPO / "packages" / "pi-artifact" / "extensions").is_dir()
    assert "pi" in manifest
