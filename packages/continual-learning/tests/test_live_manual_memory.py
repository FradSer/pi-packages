from __future__ import annotations

import sys
from pathlib import Path

import pytest


TESTS = Path(__file__).parent
sys.path.insert(0, str(TESTS))

from live_manual_memory import _assert_safe_memory_tree, _memory_bodies  # noqa: E402


def test_memory_bodies_rejects_symlinked_root(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "root").symlink_to(real, target_is_directory=True)

    with pytest.raises(AssertionError, match="real directory"):
        _memory_bodies(tmp_path / "root")


def test_memory_bodies_rejects_symlinked_markdown_entry(tmp_path: Path) -> None:
    root = tmp_path / "memory"
    root.mkdir()
    target = tmp_path / "outside.md"
    target.write_text("outside\n", encoding="utf-8")
    (root / "fact.md").symlink_to(target)

    with pytest.raises(AssertionError, match="symlink"):
        _memory_bodies(root)


def test_memory_tree_rejects_nested_symlink(tmp_path: Path) -> None:
    root = tmp_path / "memory"
    nested = root / "nested"
    nested.mkdir(parents=True)
    target = tmp_path / "outside"
    target.mkdir()
    (nested / "link").symlink_to(target, target_is_directory=True)

    with pytest.raises(AssertionError, match="symlink"):
        _assert_safe_memory_tree(root)
