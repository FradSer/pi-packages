from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from matt_pocock_helpers import PACKAGE


@pytest.fixture(scope="session")
def packed_package(tmp_path_factory: pytest.TempPathFactory) -> Path:
    destination = tmp_path_factory.mktemp("matt-pocock-pack")
    result = subprocess.run(
        ["pnpm", "--dir", str(PACKAGE), "pack", "--pack-destination", str(destination)],
        text=True, capture_output=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    archives = list(destination.glob("*.tgz"))
    assert len(archives) == 1
    return archives[0]
