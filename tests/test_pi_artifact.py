from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "packages" / "pi-artifact"
CLI = PACKAGE / "scripts" / "artifact.mjs"
MENU = PACKAGE / "extensions" / "menu.ts"
EXTENSION = PACKAGE / "extensions" / "index.ts"


def read_manifest() -> dict:
    return json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))


def test_manifest_registers_one_extension_with_pi_kit_dependency() -> None:
    manifest = read_manifest()
    assert manifest["name"] == "pi-artifact"
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"] == {"extensions": ["./index.ts"]}
    assert "skills" not in manifest["pi"]
    assert manifest["dependencies"] == {"@fradser/pi-kit": "workspace:*"}
    assert manifest["peerDependencies"] == {"@earendil-works/pi-coding-agent": "*"}
    expected_files = [
        "index.ts",
        "extensions",
        "procedures",
        "references",
        "examples",
        "vendor",
        "scripts",
        "README.md",
    ]
    assert manifest["files"] == expected_files
    assert (PACKAGE / "index.ts").read_text(encoding="utf-8") == (
        'export { default } from "./extensions/index.ts";\n'
    )
    for shipped in ("procedures", "references", "examples", "vendor", "scripts"):
        assert (PACKAGE / shipped).is_dir()


def test_menu_offers_four_workflows_without_login() -> None:
    menu_source = MENU.read_text(encoding="utf-8")
    for procedure in ("publish.md", "update.md", "status.md", "show.md"):
        assert f'"{procedure}"' in menu_source
    menu_definition = menu_source[menu_source.index("const MENU") :]
    menu_definition = menu_definition[: menu_definition.index("];")]
    assert "login" not in menu_definition.lower()
    # update and show pick a target from the merged project manifest
    assert "picksArtifact: true" in menu_definition
    assert "manifest.local.json" in menu_source
    for procedure in ("login", "logout"):
        assert not (PACKAGE / "procedures" / f"{procedure}.md").exists()


def test_procedures_use_pkg_dir_and_bundled_cli() -> None:
    for name in ("publish", "update", "status", "show"):
        text = (PACKAGE / "procedures" / f"{name}.md").read_text(encoding="utf-8")
        assert "{{PKG_DIR}}/scripts/artifact.mjs" in text
        assert "https://coda0.com" in text
    publish = (PACKAGE / "procedures" / "publish.md").read_text(encoding="utf-8")
    assert "{{PKG_DIR}}/references/design.md" in publish
    assert "{{PKG_DIR}}/references/recipe.md" in publish


def test_guidance_routes_natural_language_without_a_skill_surface() -> None:
    extension = EXTENSION.read_text(encoding="utf-8")
    assert "before_agent_start" in extension
    assert "{{PKG_DIR}}/scripts/artifact.mjs" in extension
    assert "https://coda0.com" in extension
    manifest = read_manifest()
    assert "skills" not in manifest.get("pi", {})
    assert not (PACKAGE / "SKILL.md").exists()
    assert not (PACKAGE / "skills").exists()


def test_bundled_cli_defaults_to_coda0() -> None:
    script = CLI.read_text(encoding="utf-8")
    assert 'const DEFAULT_API_URL = "https://coda0.com";' in script
    chain_markers = (
        "flags.api ??",
        "process.env.OPEN_ARTIFACTS_URL ??",
        "project.apiUrl ??",
        "global.apiUrl ??",
        "DEFAULT_API_URL;",
    )
    positions = [script.index(marker) for marker in chain_markers]
    assert positions == sorted(positions)
    assert "no instance configured" not in script


def test_upstream_provenance_documents_source_and_local_changes() -> None:
    upstream = (PACKAGE / "UPSTREAM.md").read_text(encoding="utf-8")
    assert "coda0HQ/open-artifacts" in upstream
    assert "2720b65" in upstream
    assert 'DEFAULT_API_URL = "https://coda0.com"' in upstream
    assert "not shipped" in upstream  # SKILL.md replaced by procedures


def test_release_allowlist_includes_pi_artifact() -> None:
    release_script = (REPO / "scripts" / "publish-release.mjs").read_text(encoding="utf-8")
    assert '"pi-artifact"' in release_script
