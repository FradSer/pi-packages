from pathlib import Path
import subprocess

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


@pytest.mark.parametrize(
    "mode",
    ["release", "cancel", "permission", "unknown-owner-error", "pre-aborted", "overlay"],
)
def test_collection_lock_wait_is_responsive_and_cancellable(tmp_path: Path, mode: str) -> None:
    result = subprocess.run(
        ["pnpm", "exec", "tsx", str(PACKAGE / "tests/lock_wait_harness.mts"), mode, str(tmp_path / "registry")],
        cwd=REPO, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
