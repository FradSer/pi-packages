"""Given/When/Then contracts for the manually invoked, real-model pilot."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("promax_protocol", Path(__file__).with_name("protocol.py"))
assert SPEC and SPEC.loader
protocol = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(protocol)


def test_selection_is_reproducible_and_stratified() -> None:
    # Given four languages with repeated repositories, when order changes,
    # then eight fixed tasks from distinct repositories are still selected.
    rows = [{"instance_id": f"{lang}-{i}", "language": lang, "repo": f"{lang}/{i // 2}"}
            for lang in protocol.LANGUAGES for i in range(6)]
    selected = protocol.select_tasks(rows)
    assert selected == protocol.select_tasks(list(reversed(rows)))
    assert len(selected) == 8
    assert len({r["repo"] for r in selected}) == 8
    assert all(sum(r["language"] == lang for r in selected) == 2 for lang in protocol.LANGUAGES)


def test_agent_metadata_excludes_answers() -> None:
    # Given private reference patches and grading scripts, when preparing an
    # agent input, then neither answers nor hidden tests are disclosed.
    row = {"instance_id": "task", "language": "python", "problem_statement": "Fix it",
           "base_commit": "base", "patch": "secret solution", "test_patch": "secret tests"}
    public = protocol.public_task(row)
    assert "patch" not in public and "test_patch" not in public
    assert "base_commit" not in public and "instance_id" not in public
    assert public["problem_statement"] == "Fix it"


def test_environment_replacement_is_same_language_and_deterministic() -> None:
    # Given a blocked repository before inference, when selecting a replacement,
    # then preserve the language and avoid the blocked repository.
    selected = [{"instance_id": "blocked", "language": "typescript", "repo": "blocked/repo"},
                {"instance_id": "kept", "language": "typescript", "repo": "other/repo"}]
    rows = selected + [{"instance_id": "replacement", "language": "typescript", "repo": "other/repo"},
                       {"instance_id": "excluded", "language": "typescript", "repo": "blocked/repo"}]
    result = protocol.replace_environment_task(selected, rows, "blocked")
    assert result == protocol.replace_environment_task(selected, list(reversed(rows)), "blocked")
    assert result[0]["instance_id"] == "replacement"
    assert result[1] == selected[1]


def test_grading_requires_success_not_matching_failures() -> None:
    # Given matching infrastructure failures, when parsing either run, then it
    # must never become a pass merely because the reference failed identically.
    assert not protocol.grade_succeeded(1, "OMNIGRIL_EXIT_CODE=1", "")
    assert not protocol.grade_succeeded(0, "OMNIGRIL_TEST_PATCH_APPLY_FAILED=1\nOMNIGRIL_EXIT_CODE=0", "")
    assert not protocol.grade_succeeded(124, "OMNIGRIL_EXIT_CODE=0", "")
    assert protocol.grade_succeeded(0, "OMNIGRIL_EXIT_CODE=0", "")


def test_empty_control_requires_an_observed_test_failure() -> None:
    # Given a good oracle but failed infrastructure, when checking eligibility,
    # then the empty control cannot qualify the task.
    assert not protocol.gate_eligible({"passed": True}, {"passed": False, "reason": "timeout"})
    assert not protocol.gate_eligible({"passed": True}, {"passed": False, "reason": "verifier_finished", "scriptExitCodes": []})
    assert protocol.gate_eligible({"passed": True}, {"passed": False, "reason": "verifier_finished", "scriptExitCodes": [1]})


def test_preexisting_attempt_is_rejected(tmp_path: Path) -> None:
    # Given a previous model patch, when an attempt is started at the same path,
    # then refuse instead of grading old artifacts as a fresh run.
    import pytest
    (tmp_path / "model.patch").write_text("old patch")
    with pytest.raises(FileExistsError):
        protocol.create_attempt_directory(tmp_path)


def test_replacement_never_reintroduces_a_previous_environment_failure() -> None:
    selected = [{"instance_id": "blocked", "language": "typescript", "repo": "blocked/repo"}]
    rows = selected + [{"instance_id": "failed-before", "language": "typescript", "repo": "other/repo"},
                       {"instance_id": "replacement", "language": "typescript", "repo": "other/repo"}]
    result = protocol.replace_environment_task(selected, rows, "blocked", {"failed-before"})
    assert result[0]["instance_id"] == "replacement"


def test_compiler_crash_is_not_an_empty_control_behavior_failure() -> None:
    empty = {'passed': False, 'reason': 'verifier_finished', 'scriptExitCodes': [1], 'compilerFailure': True}
    assert not protocol.gate_eligible({'passed': True}, empty)


def test_compiler_panic_is_distinguished_from_application_deadlock() -> None:
    assert protocol.compiler_failure('fatal error: all goroutines are asleep - deadlock!\ncmd/compile/internal/gc.Main')
    assert not protocol.compiler_failure('fatal error: all goroutines are asleep - deadlock!\nmyproject/main.go:9')
