from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]


def test_routing_behavioral_seams() -> None:
    result = subprocess.run(
        ["node", "--import", "tsx/esm", "--test", "packages/impeccable/tests/routing.test.mjs"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
