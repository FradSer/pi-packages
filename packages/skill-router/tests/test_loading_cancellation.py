from pathlib import Path
import subprocess

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


@pytest.mark.parametrize("mode", ["escape-auth", "external-auth", "escape-model", "external-model"])
def test_loading_cancellation_does_not_wait_for_external_operation(tmp_path: Path, mode: str) -> None:
    result = subprocess.run(
        ["node", "--import", "tsx", str(PACKAGE / "tests/loading_cancellation_harness.mjs"), mode, str(tmp_path)],
        cwd=REPO, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
