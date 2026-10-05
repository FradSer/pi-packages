"""Run extension behavior tests through the TypeScript runtime."""

import json
import subprocess
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]


def run_typescript(script: str) -> Any:
    """Run a script and read its JSON report."""
    result = subprocess.run(
        ["bun", "run", "-"],
        cwd=REPO,
        input=script,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise AssertionError(f"TypeScript execution failed:\n{result.stderr}")
    return json.loads(result.stdout)
