from __future__ import annotations

import os
import subprocess
import tempfile

from test_open_deskos_package import PACKAGE, REPO


def test_machine_session_discovery_regressions() -> None:
    loader = [] if os.environ.get("ODK_TEST_NATIVE_TS") == "1" else ["--import", "tsx"]
    with tempfile.TemporaryDirectory(prefix="desk-discovery-suite-") as registry:
        home = os.path.join(registry, "home")
        os.makedirs(home, exist_ok=True)
        env = dict(os.environ, PI_DIRECTORY_SESSIONS_DIR=registry, HOME=home)
        # The default desks file is resolved from the home directory, so stripping
        # ODK_ environment variables is not enough on its own: a developer machine
        # that actually runs Desk Link would have its real desks read instead of the
        # configuration each script declares, and the harness would silently report
        # to a real desk rather than to its own local server. Isolating HOME keeps
        # the declared environment authoritative.
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
