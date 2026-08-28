from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = (REPO / "scripts" / "publish-release.mjs").read_text(encoding="utf-8")


def test_feature_covers_local_and_ci_provenance_modes() -> None:
    feature = (REPO / "features" / "publish-provenance.feature").read_text(encoding="utf-8")
    assert "Local publishing does not force CI-only provenance" in feature
    assert "CI publishing enables npm provenance" in feature


def test_publish_script_only_enables_provenance_in_github_actions() -> None:
    assert 'process.env.GITHUB_ACTIONS === "true"' in SCRIPT
    assert '...(useProvenance ? ["--provenance"] : [])' in SCRIPT


def test_workflow_runs_publish_script_after_version_commits() -> None:
    workflow = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "publish: node scripts/publish-release.mjs" in workflow
    assert "NPM_CONFIG_PROVENANCE" in workflow


def test_workflow_has_a_main_branch_publish_retry() -> None:
    workflow = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "if: github.ref == 'refs/heads/main'" in workflow
    assert "node scripts/publish-release.mjs" in workflow


def test_workflow_skips_retry_when_changesets_created_a_version_pr() -> None:
    workflow = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "steps.changesets.outputs.hasChangesets != 'true'" in workflow
    assert "steps.changesets.outputs.has-changesets" not in workflow


def test_workflow_uses_node_24_compatible_actions() -> None:
    workflow = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "actions/checkout@v5" in workflow
    assert "actions/setup-node@v5" in workflow
    assert "pnpm/action-setup@v5" in workflow
    assert "actions/checkout@v4" not in workflow
    assert "actions/setup-node@v4" not in workflow
    assert "pnpm/action-setup@v4" not in workflow


def test_publish_allowlist_includes_skill_router() -> None:
    assert '"pi-skill-router"' in SCRIPT
    assert '"pi-mattpocock"' not in SCRIPT
    assert '"pi-marketingskills"' not in SCRIPT
