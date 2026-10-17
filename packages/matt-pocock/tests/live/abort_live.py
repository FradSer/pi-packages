"""Verify programmatic AbortSignal dismissal in a real Pi v1.0 PTY."""
from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path

from live_pty import isolated_env, live_pi, pi_command, read_jsonl, wait_for

FIXTURE = Path(__file__).with_name("abort-live-fixture.ts")


def main() -> None:
    pi = shutil.which("pi")
    assert pi, "pi CLI is required"
    with tempfile.TemporaryDirectory(prefix="mp-abort-live-") as directory:
        root = Path(directory)
        evidence = root / "evidence.jsonl"
        env = isolated_env(root, extra={
            "PI_NO_NATIVE_DIALOG": "1",
            "PI_ABORT_LIVE_AUTH": secrets.token_hex(16),
            "PI_ABORT_LIVE_EVIDENCE": str(evidence),
        })
        command = pi_command(pi, FIXTURE, "abort-live-fixture", "Run abort fixture")
        with live_pi(command, cwd=root, env=env) as (master, process, transcript):
            wait_for(master, process, transcript, lambda: b"LIVE programmatic abort" in transcript)
            wait_for(master, process, transcript, lambda: b"ABORT_LIVE_READY" in transcript)
            rows = read_jsonl(evidence)
            asks = [row for row in rows if row["tool"] == "matt_pocock_ask"]
            assert len(asks) == 1, rows
            assert asks[0]["details"] == {"pending": True, "source": "aborted"}, asks
            assert b"A" in transcript and b"B" in transcript, transcript.decode(errors="replace")[-4000:]
            os.write(master, b"/quit\r")
            wait_for(master, process, transcript, lambda: process.poll() is not None)
            assert process.returncode == 0, transcript.decode(errors="replace")[-4000:]
            print(json.dumps({"pi": "1.0 programmatic abort PTY passed", "result": asks[0]["details"]}))


if __name__ == "__main__":
    main()
