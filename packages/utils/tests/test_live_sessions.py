import pathlib
import subprocess


def test_live_sessions():
    root = pathlib.Path(__file__).resolve().parents[3]
    subprocess.run(
        ['pnpm', 'exec', 'tsx', '--test', 'packages/utils/tests/live-sessions.test.ts', 'packages/utils/tests/live-sessions-lifecycle.test.ts', 'packages/utils/tests/live-sessions-sdk.test.ts'],
        cwd=root,
        check=True,
    )
