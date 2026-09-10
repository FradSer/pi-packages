import pathlib
import subprocess


def test_live_session_control():
    root = pathlib.Path(__file__).resolve().parents[3]
    subprocess.run(
        ['pnpm', 'exec', 'tsx', '--test', 'packages/session-control/tests/control.test.ts', 'packages/session-control/tests/lifecycle.test.ts', 'packages/session-control/tests/sdk.test.ts'],
        cwd=root,
        check=True,
    )
