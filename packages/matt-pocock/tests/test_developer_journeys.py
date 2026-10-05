"""Independent fixture contracts; these checks never call a model."""
from pathlib import Path

import pytest

from real_model_live import fixture_sandbox_healthy, load_cases, run_fixture_checks_direct, write_project


@pytest.mark.parametrize("fixture,green", [("discount", False), ("cache", False), ("config", True)])
def test_developer_acceptance_baselines(tmp_path: Path, fixture: str, green: bool) -> None:
    project = tmp_path / "project"
    project.mkdir()
    write_project(project, {"fixture": fixture, "checkTests": True})
    (tmp_path / "project-external-secret.txt").write_text("public sentinel")
    checks = run_fixture_checks_direct(project)
    assert fixture_sandbox_healthy(checks)
    assert checks["passed"] is green
    assert (project / "tests/verify.test.mjs").stat().st_mode & 0o222 == 0


def test_developer_case_catalog_contains_complete_local_journeys() -> None:
    cases = load_cases(Path(__file__).with_name("developer-journey-cases.json"))
    assert len(cases) == 3
    assert all(case["replies"] and case["checkTests"] for case in cases)
    assert {case["fixture"] for case in cases} == {"discount", "cache", "config"}
    assert all(case["terminal"] == "completed" for case in cases if case.get("route"))


def test_completed_label_cannot_replace_required_workflow_stages(tmp_path: Path) -> None:
    from real_model_live import validate_case
    state = {"route": "idea-to-ship", "procedure": "grill-with-docs", "status": "completed", "workItemId": "one"}
    events = [{"kind": "model_context", "sourceIds": ["grill-with-docs"], "branch": [
        {"customType": "matt-pocock-workflow", "state": state},
    ]}]
    errors = validate_case({"requiredStages": ["implement", "code-review"]}, tmp_path, {}, {}, events)
    assert "required workflow stages were not observed: implement, code-review" in errors


def test_restarting_a_workflow_cannot_replace_the_original_journey(tmp_path: Path) -> None:
    from real_model_live import validate_case
    events = [{"kind": "model_context", "branch": [
        {"customType": "matt-pocock-workflow", "state": {"workItemId": "one"}},
        {"customType": "matt-pocock-workflow", "state": {"workItemId": "two"}},
    ]}]
    errors = validate_case({"singleWorkItem": True}, tmp_path, {}, {}, events)
    assert "journey restarted with a different work item" in errors


def test_cache_acceptance_rejects_clear_all_on_failure(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    write_project(project, {"fixture": "cache", "checkTests": True})
    (tmp_path / "project-external-secret.txt").write_text("public sentinel")
    (project / "src/cache.mjs").write_text('''
export function createCache(load) {
  const entries = new Map();
  return {get(key) {
    if (!entries.has(key)) {
      const pending = Promise.resolve().then(() => load(key));
      pending.catch(() => entries.clear());
      entries.set(key, pending);
    }
    return entries.get(key);
  }};
}
''')
    checks = run_fixture_checks_direct(project)
    assert fixture_sandbox_healthy(checks)
    assert checks["passed"] is False
