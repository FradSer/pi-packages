from pathlib import Path
import subprocess

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


@pytest.mark.parametrize("mode", [
    "pre-aborted", "auth-cancel", "model-reject", "model-resolve", "provider-abort", "collection-auth-cancel",
])
def test_summary_cancellation_never_becomes_a_fallback_success(mode: str) -> None:
    result = subprocess.run(
        ["node", "--import", "tsx", str(PACKAGE / "tests/summary_cancellation_harness.mjs"), mode],
        cwd=REPO, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
