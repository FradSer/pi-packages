from __future__ import annotations

import os
import subprocess
import tempfile

from test_open_deskos_package import PACKAGE, REPO


def test_multiline_result_regressions() -> None:
    loader = [] if os.environ.get("ODK_TEST_NATIVE_TS") == "1" else ["--import", "tsx"]
    with tempfile.TemporaryDirectory(prefix="desk-results-suite-") as registry:
        env = dict(os.environ, PI_DIRECTORY_SESSIONS_DIR=registry)
        env.pop("ODK_DESK_LINK_ADDRESS", None)
        env.pop("ODK_DESK_LINK_TOKEN", None)
        result = subprocess.run(
            ["node", *loader, "--test", str(PACKAGE / "tests/multiline-results.test.mjs")],
            cwd=REPO,
            env=env,
            text=True,
            capture_output=True,
            timeout=40,
            check=False,
        )
    assert result.returncode == 0, f"multiline result regressions failed:\n{result.stdout}\n{result.stderr}"
