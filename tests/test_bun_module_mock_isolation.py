"""Bun keeps a `mock.module` bound for the whole process, so a test file that
mocks a shared package module at load time changes what every later test file in
the same `bun test` run sees. Bun loads all matched files before running their
tests, so this is order-independent breakage and the machine-dependent failures
it produces cannot be reproduced by running one file alone.

The workspace rule: a test file may mock a shared module only inside a child
process it spawns itself, guarded by a `--fixture` argument, the way
`packages/continual-learning/tests/memory-maintenance-terminal.test.ts` does.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEST_SUFFIXES = (".test.ts", ".test.mts", ".test.mjs", ".test.js")
FIXTURE_GUARD = 'process.argv.includes("--fixture")'


def _bun_test_files() -> list[Path]:
    roots = [REPO / "tests", *sorted((REPO / "packages").glob("*/tests"))]
    files: list[Path] = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or not path.name.endswith(TEST_SUFFIXES):
                continue
            if "node_modules" in path.parts or "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def test_no_test_file_mocks_a_module_at_top_level() -> None:
    offenders: list[str] = []
    for path in _bun_test_files():
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            # Column zero means the call runs while Bun loads the file, before
            # any test of any other file has executed.
            if line.startswith("mock.module("):
                offenders.append(f"{path.relative_to(REPO).as_posix()}:{number}")
    assert offenders == [], "module mock at file load leaks into other test files: " + ", ".join(offenders)


def test_every_module_mock_is_isolated_in_a_spawned_fixture_process() -> None:
    users = [path for path in _bun_test_files() if "mock.module(" in path.read_text()]
    for path in users:
        text = path.read_text()
        rel = path.relative_to(REPO).as_posix()
        assert FIXTURE_GUARD in text, f"{rel} mocks a module without a --fixture child-process guard"
        assert "spawnSync" in text or "spawn(" in text, f"{rel} never spawns the guarded fixture process"
