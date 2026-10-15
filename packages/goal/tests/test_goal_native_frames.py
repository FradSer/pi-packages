"""Native frame acceptance must reject missing results and truncated tails."""
import pytest
from goal_native_live import REQUEST_WORDS, assert_progress_frame, assert_request_frame, assert_settled_frame
from goal_native_completion import assert_completion_frame

SETTLED = ["[goal] started", "Objective: Export CSV", "GOAL_REQUIREMENT_END", "[goal] active", "Completion conditions:", "GOAL_CONTRACT_END"]
REQUEST = ["[goal] requesting", REQUEST_WORDS, "[goal] started", "Objective: Export CSV"]


def test_complete_authored_bodies_require_both_tails() -> None:
    assert_settled_frame(SETTLED)
    for missing in ("[goal] started", "[goal] active", "GOAL_REQUIREMENT_END", "GOAL_CONTRACT_END"):
        with pytest.raises(AssertionError):
            assert_settled_frame([line for line in SETTLED if missing not in line])


def test_repaint_duplicates_and_expansion_requirements_are_failures() -> None:
    with pytest.raises(AssertionError):
        assert_settled_frame(SETTLED + SETTLED)
    with pytest.raises(AssertionError):
        assert_settled_frame(SETTLED + ["ctrl+o to expand"])


def test_checker_progress_is_neutral_and_present() -> None:
    assert_progress_frame(["Evaluating the objective and recorded evidence..."])
    with pytest.raises(AssertionError):
        assert_progress_frame(["[goal] checking...", "Evaluating the objective and recorded evidence..."])
    with pytest.raises(AssertionError):
        assert_progress_frame(["Evaluating the objective and recorded evidence...", "NOT MET"])


def test_refusal_cannot_be_a_pause() -> None:
    assert_completion_frame(["[goal] not met", "Review missing", "Goal waiting"], "refuse")
    with pytest.raises(AssertionError):
        assert_completion_frame(["[goal] paused", "Review missing"], "refuse")


def test_error_cannot_have_two_failure_headers() -> None:
    assert_completion_frame(["[goal] check failed", "Offline provider unavailable"], "error")
    with pytest.raises(AssertionError):
        assert_completion_frame(["[goal] failed · check failed", "Offline provider unavailable"], "error")


def test_completion_is_an_actual_completion_result() -> None:
    with pytest.raises(AssertionError):
        assert_completion_frame(["Goal paused", "archived history"], "complete")
    assert_completion_frame(["[goal] completed", "Verified."], "complete")


def test_request_row_shows_the_words_before_the_creation_result() -> None:
    assert_request_frame(REQUEST, created=False)
    assert_request_frame(REQUEST)
    for missing in ("[goal] requesting", REQUEST_WORDS, "[goal] started"):
        with pytest.raises(AssertionError):
            assert_request_frame([line for line in REQUEST if missing not in line])
    with pytest.raises(AssertionError):
        assert_request_frame(["[goal] started", "Objective: Export CSV", "[goal] requesting", REQUEST_WORDS])
    with pytest.raises(AssertionError):
        assert_request_frame(REQUEST + REQUEST)
    with pytest.raises(AssertionError):
        assert_request_frame(REQUEST + ["Preserve all acceptance conditions and scope constraints."])

