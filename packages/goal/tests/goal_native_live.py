"""Complete default bodies and neutral checker progress in terminal frames."""
from __future__ import annotations
from collections.abc import Sequence
from goal_native_completion import main


def assert_progress_frame(lines: Sequence[str]) -> None:
    text = "\n".join(lines)
    assert "[goal] checking" in text
    assert "Evaluating the objective and recorded evidence" in text


def assert_settled_frame(lines: Sequence[str], expanded: bool = False) -> None:
    text = "\n".join(lines)
    assert text.count("[goal] started") == 1
    assert "[goal] active" in text
    assert "GOAL_REQUIREMENT_END" in text and "GOAL_CONTRACT_END" in text
    assert "ctrl+o to expand" not in text
    assert "research ready" not in text and "archived" not in text


if __name__ == "__main__":
    main()
