"""The test harnesses must be type checked, not merely run.

`pnpm typecheck` resolves `packages/*/src/**` only, so `tsconfig.tests.json` is
the one check that sees `tests/`. Nothing ran it, which is how a harness can
import a name the module does not export and still pass: Bun and tsx erase
unused type-only imports at runtime.
"""
from __future__ import annotations

import subprocess

from test_loop import PACKAGE, REPO


def test_package_typecheck_covers_the_test_harnesses() -> None:
    config = (PACKAGE / "tsconfig.tests.json").read_text(encoding="utf-8")
    assert "tests/**/*.ts" in config, "test harnesses must be part of a type check"
    result = subprocess.run(
        ["pnpm", "exec", "tsc", "--noEmit", "-p", "packages/loop/tsconfig.tests.json"],
        cwd=REPO, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
