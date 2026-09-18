from __future__ import annotations

import os
import subprocess
import tempfile

from test_open_deskos_package import PACKAGE, REPO


def test_machine_session_discovery_regressions() -> None:
    loader = [] if os.environ.get("ODK_TEST_NATIVE_TS") == "1" else ["--import", "tsx"]
    with tempfile.TemporaryDirectory(prefix="desk-discovery-suite-") as registry:
        env = dict(os.environ, PI_DIRECTORY_SESSIONS_DIR=registry)
        env.pop("ODK_DESK_LINK_ADDRESS", None)
        env.pop("ODK_DESK_LINK_TOKEN", None)
        result = subprocess.run(
            ["node", *loader, "--test", str(PACKAGE / "tests/machine-session-discovery.test.mjs"), str(PACKAGE / "tests/discovery-extension.test.mjs")],
            cwd=REPO,
            env=env,
            text=True,
            capture_output=True,
            timeout=40,
            check=False,
        )
    assert result.returncode == 0, f"discovery regressions failed:\n{result.stdout}\n{result.stderr}"
