"""Select optional flags supported by the actual installed Pi CLI."""
from __future__ import annotations

import shutil
import subprocess


def isolated_pi_command() -> list[str]:
    executable = shutil.which("pi") or "pi"
    help_result = subprocess.run([executable, "--help"], capture_output=True, text=True, check=True, timeout=30)
    return [executable, *(["--no-mcp"] if "--no-mcp" in help_result.stdout else [])]
