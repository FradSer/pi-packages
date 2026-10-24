from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_packed_package_in_native_pi_print_and_rpc(tmp_path: Path) -> None:
    """Given packed packages, when native Pi reads/writes/aborts, then records and receipts agree."""
    script = Path(__file__).with_name("live_sdlc.py")
    output = tmp_path / "native"
    result = subprocess.run([sys.executable, str(script), "--output", str(output)],
                            cwd=script.parents[3], text=True, capture_output=True, timeout=150)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((output / "report.json").read_text())
    assert report["status"] == "passed"
    assert [case["case"] for case in report["cases"]] == ["fresh", "correction", "abort", "pipeline"]
