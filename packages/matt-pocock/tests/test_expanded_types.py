"""Independent acceptance baselines for the broader developer task types."""
from pathlib import Path

import pytest

from real_model_live import load_cases, write_project, run_fixture_checks_direct, fixture_sandbox_healthy

TYPES = ("frontend", "api", "authorization", "migration", "performance", "localization", "paths", "test-design")


@pytest.mark.parametrize("task_type", TYPES)
def test_expanded_fixture_reproduces_its_own_defect(tmp_path: Path, task_type: str) -> None:
    project = tmp_path / "project"
    project.mkdir()
    write_project(project, {"fixture": task_type, "checkTests": True})
    (tmp_path / "project-external-secret.txt").write_text("public sandbox sentinel")
    assert (project / "src/feature.mjs").is_file()
    assert not (project / "src/receipt.mjs").exists()
    check = run_fixture_checks_direct(project)
    assert fixture_sandbox_healthy(check)
    assert check["passed"] is False
    assert (project / "tests/verify.test.mjs").stat().st_mode & 0o222 == 0


def test_unknown_fixture_fails_before_model_execution(tmp_path: Path) -> None:
    catalog = tmp_path / "cases.json"
    catalog.write_text('[{"id":"typo","fixture":"does-not-exist","prompt":"x"}]')
    with pytest.raises(ValueError, match="unknown fixture"):
        load_cases(catalog)


@pytest.mark.parametrize("fixture", [[], {}, 0, False])
def test_malformed_fixture_type_has_a_controlled_catalog_error(tmp_path: Path, fixture) -> None:
    import json
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"id":"bad","fixture":fixture,"prompt":"x"}]))
    with pytest.raises(ValueError, match="unknown fixture"):
        load_cases(path)


def test_early_successful_exit_cannot_skip_acceptance(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    project.mkdir()
    write_project(project, {'fixture':'authorization','checkTests':True})
    (tmp_path / 'project-external-secret.txt').write_text('public sentinel')
    (project / 'src/feature.mjs').write_text('process.exit(0); export function canRead(){return true;}')
    check = run_fixture_checks_direct(project)
    assert fixture_sandbox_healthy(check)
    assert check['passed'] is False


def test_printing_the_completion_marker_cannot_skip_acceptance(tmp_path: Path) -> None:
    project = tmp_path / 'project'
    project.mkdir()
    write_project(project, {'fixture':'authorization','checkTests':True})
    (tmp_path / 'project-external-secret.txt').write_text('public sentinel')
    (project / 'src/feature.mjs').write_text("import fs from 'node:fs'; const text=fs.readFileSync('tests/verify.test.mjs','utf8'); const marker=text.match(/MP_ACCEPTANCE_COMPLETE_[a-f0-9]+/)[0]; console.log('ok 99 - '+marker); process.exit(0); export function canRead(){return true;}")
    check = run_fixture_checks_direct(project)
    assert fixture_sandbox_healthy(check)
    assert check['passed'] is False
