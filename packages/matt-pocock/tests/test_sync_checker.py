"""Revision roles may coincide; comparison fixtures never mutate workspace metadata."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from matt_pocock_helpers import PACKAGE


@pytest.mark.parametrize("coincident", [False, True])
def test_checker_reads_isolated_metadata_with_truthful_revision_roles(tmp_path: Path, coincident: bool) -> None:
    source = PACKAGE / "upstream" / "upstream-selection.json"
    original = source.read_bytes()
    metadata = json.loads(original)
    if coincident:
        metadata["comparedCommit"] = metadata["latestCheckedCommit"]
        metadata["resolvedTagCommit"] = metadata["latestCheckedCommit"]
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps(metadata))
    result = subprocess.run(
        ["node", str(PACKAGE / "upstream/check-upstream-sync.mjs"), "--selection", str(selection)],
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True
    assert source.read_bytes() == original


def test_checker_rejects_duplicate_options() -> None:
    result = subprocess.run(
        ["node", str(PACKAGE / "upstream/check-upstream-sync.mjs"), "--selection", "a", "--selection", "b"],
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 1
    assert "usage:" in result.stderr
