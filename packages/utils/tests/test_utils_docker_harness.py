"""The Docker harness must start on a host that exports no TMPDIR.

The documented command is 'sh packages/utils/tests/utils_docker.sh'. Linux CI
hosts usually export no TMPDIR, and the harness runs under 'set -u', so its
prologue must still reach the first tool call there.
"""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = UTILS_PKG_DIR.parents[1]
HARNESS = UTILS_PKG_DIR / "tests" / "utils_docker.sh"


class DockerHarnessStartTests(unittest.TestCase):
    def test_prologue_reaches_its_first_tool_without_tmpdir(self) -> None:
        # A stub mktemp proves the receipt-directory line ran. An unguarded
        # $TMPDIR aborts under 'set -u' before that line, so the marker would be
        # missing even though printenv, dirname and pwd run earlier.
        with tempfile.TemporaryDirectory(prefix="pi-utils-harness-") as tools:
            stub = Path(tools) / "mktemp"
            # The command substitution captures stdout, so the marker goes to stderr.
            stub.write_text("#!/bin/sh\necho STUB_MKTEMP_REACHED >&2\nexit 3\n", encoding="utf-8")
            stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
            env = {key: value for key, value in os.environ.items() if key != "TMPDIR"}
            env["PATH"] = f"{tools}{os.pathsep}{env.get('PATH', '')}"
            result = subprocess.run(
                ["sh", str(HARNESS)],
                cwd=REPO,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        output = result.stdout + result.stderr
        self.assertNotIn("unbound variable", output, output)
        self.assertIn("STUB_MKTEMP_REACHED", output, output)
        self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
