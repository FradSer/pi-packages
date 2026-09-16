"""Human-facing coordination rows expose names, subjects, and typed text."""

import os
import subprocess

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_coordination_rows_are_readable_without_identifiers():
    result = subprocess.run(["node", "tests/coordination-rows-fixture.ts"], cwd=PACKAGE, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert "COORDINATION_ROWS_OK" in result.stdout
