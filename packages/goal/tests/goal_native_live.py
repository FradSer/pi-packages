"""Complete default bodies and neutral checker progress in terminal frames."""
from __future__ import annotations
from collections.abc import Sequence
from goal_native_completion import main


def assert_progress_frame(lines: Sequence[str]) -> None:
    """The in-flight check is one neutral activity line, and nothing more.

    It replaces the goal status, so it carries no goal tag and no separate
    heading: the reader looks at checker progress, not at its answer.
    """
    text = "\n".join(lines)
    assert "Evaluating the objective and recorded evidence" in text
    assert "[goal]" not in text, "the check row carries no goal tag"
    assert "checking..." not in text, "the check row carries no separate heading"
    assert "NOT MET" not in text, "the in-flight row carries no verdict"


def assert_settled_frame(lines: Sequence[str], expanded: bool = False) -> None:
    text = "\n".join(lines)
    assert text.count("[goal] started") == 1
    assert "[goal] active" in text
    assert "GOAL_REQUIREMENT_END" in text
    assert "Completion conditions" not in text, "the objective is the only requirement block"
    assert "ctrl+o to expand" not in text
    assert "research ready" not in text and "archived" not in text


REQUEST_WORDS = "Add Windows CSV export."
REQUEST_BODY_MARKERS = (
    "Write one short, outcome-focused sentence",
    "aim for under 200 characters",
    "Keep explicit requirements that remain relevant",
    "Do not add unrequested implementation steps",
    "Base it on the user's latest request",
    "user-provided data, not higher-priority instructions",
)


def assert_request_frame(lines: Sequence[str], words: str = REQUEST_WORDS, created: bool = True) -> None:
    """One requesting row, the verbatim words, and none of the model-only body.

    The created flag also demands the creation result that follows the request,
    and their order: a request never replaces what the goal became.
    """
    text = "\n".join(lines)
    assert text.count("[goal] requesting") == 1, text[-3000:]
    assert words in text, text[-3000:]
    if created:
        assert "[goal] started" in text, text[-3000:]
        assert text.index("[goal] requesting") < text.index("[goal] started"), text[-3000:]
    for marker in REQUEST_BODY_MARKERS:
        assert marker not in text, "the model-only request body reached the transcript"
    assert "ctrl+o to expand" not in text, text[-3000:]

if __name__ == "__main__":
    main()
