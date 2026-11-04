"""The workspace test toolchain runs on bun, outside continual-learning.

`packages/continual-learning/` is excluded: its study harnesses are maintained
separately. Three files name another package manager because that manager is the
subject under test, not a command this workspace runs.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FORBIDDEN = "pn" + "pm"
ALLOWED = {
    "tests/test_publish_release.py",  # asserts that releases never use it
    "packages/utils/tests/test_init_extension.py",  # bare token in a policy-word list
    "packages/utils/tests/test_npm_publish_guard.py",  # tests the publish guard feature
}
SCANNED_SUFFIXES = {".py", ".mjs", ".ts", ".mts", ".sh", ".json"}


def test_non_continual_learning_test_tooling_invokes_only_bun() -> None:
    roots = [REPO / "scripts", REPO / "tests", *sorted((REPO / "packages").glob("*/tests"))]
    scanned: list[str] = []
    offenders: list[str] = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
                continue
            if "node_modules" in path.parts or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(REPO).as_posix()
            if rel.startswith("packages/continual-learning/") or rel in ALLOWED:
                continue
            scanned.append(rel)
            if FORBIDDEN in path.read_text():
                offenders.append(rel)
    assert scanned
    assert not offenders, f"non-bun package manager in test tooling: {offenders}"
    assert '"bun", "pm", "pack"' in (REPO / "packages/matt-pocock/tests/conftest.py").read_text()
    assert '"bun", "x", "tsc"' in (REPO / "packages/matt-pocock/tests/test_pi_v1_resolution.py").read_text()
    assert "bun run typecheck" in (REPO / "packages/matt-pocock/AGENTS.md").read_text()
