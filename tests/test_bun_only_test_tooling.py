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
TEST_SUFFIXES = (".test.ts", ".test.mts", ".test.mjs", ".test.js")
FIXTURE_GUARD = 'process.argv.includes("--fixture")'


def _bun_test_files() -> list[Path]:
    roots = [REPO / "tests", *sorted((REPO / "packages").glob("*/tests"))]
    return [
        path
        for root in roots
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.name.endswith(TEST_SUFFIXES)
        and "node_modules" not in path.parts
        and "__pycache__" not in path.parts
    ]


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
    assert '"bun", "x", "tsc"' in (REPO / "packages/matt-pocock/tests/test_package.py").read_text()
    assert "bun run typecheck" in (REPO / "packages/matt-pocock/AGENTS.md").read_text()


def test_bun_module_mocks_never_run_at_top_level_and_use_fixture_subprocess_guards() -> None:
    offenders: list[str] = []
    for path in _bun_test_files():
        text = path.read_text()
        rel = path.relative_to(REPO).as_posix()
        for number, line in enumerate(text.splitlines(), start=1):
            if line.startswith("mock.module("):
                offenders.append(f"{rel}:{number}")
        if "mock.module(" in text:
            assert FIXTURE_GUARD in text, f"{rel} mocks a module without a --fixture child-process guard"
            assert "spawnSync" in text or "spawn(" in text, f"{rel} never spawns the guarded fixture process"
    assert offenders == [], "module mock at file load leaks into other test files: " + ", ".join(offenders)
