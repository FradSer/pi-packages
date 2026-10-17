"""Exercise active /matt-pocock menu actions through real Pi v1.0 PTYs."""
from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
import time
from pathlib import Path

from live_pty import isolated_env, live_pi, pi_command, read_jsonl, wait_for

FIXTURE = Path(__file__).with_name("active-menu-live-fixture.ts")
ACTIVE_LABELS = (
    b"View current workflow",
    b"Transition current workflow",
    b"Complete current workflow",
    b"Cancel current workflow",
)


def run_case(pi: str, action: str, index: int) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"mp-active-menu-{action}-") as directory:
        root = Path(directory)
        evidence = root / "evidence.jsonl"
        env = isolated_env(root, extra={
            "PI_ACTIVE_MENU_AUTH": secrets.token_hex(16),
            "PI_ACTIVE_MENU_EVIDENCE": str(evidence),
        })
        command = pi_command(pi, FIXTURE, "active-menu-live-fixture", "Run active menu fixture")
        with live_pi(command, cwd=root, env=env) as (master, process, transcript):
            wait_for(master, process, transcript, lambda: b"ACTIVE_MENU_READY" in transcript)
            time.sleep(0.4)
            start = len(transcript)
            os.write(master, b"\x1b[200~/matt-pocock\x1b[201~\r")
            wait_for(master, process, transcript, lambda: all(label in transcript[start:] for label in ACTIVE_LABELS))
            for _ in range(index):
                os.write(master, b"\x1b[B")
                time.sleep(0.35)
            os.write(master, b"\r")

            if action == "view":
                wait_for(master, process, transcript, lambda: b"Matt Pocock workflow:" in transcript)
            elif action == "transition":
                wait_for(master, process, transcript, lambda: b"Transition Hard Bug Diagnosis" in transcript[start:] and b"Implementation" in transcript[start:])
                os.write(master, b"\r")
                wait_for(master, process, transcript, lambda: any(
                    row.get("kind") == "entry" and row.get("data", {}).get("procedure") == "implement"
                    for row in read_jsonl(evidence)
                ))
            else:
                expected = {"cancel": b"workflow cancelled", "complete": b"workflow completed"}[action]
                wait_for(master, process, transcript, lambda: expected in transcript)

            rows = read_jsonl(evidence)
            entries = [row["data"] for row in rows if row.get("kind") == "entry" and row.get("customType") == "matt-pocock-workflow"]
            active_tools = [row["names"] for row in rows if row.get("kind") == "activeTools"]
            assert any("matt_pocock_active" in names and "matt_pocock_ask" in names for names in active_tools), active_tools
            if action == "transition":
                assert entries[-1]["status"] == "active" and entries[-1]["procedure"] == "implement", entries
                assert active_tools[-1] == ["matt_pocock_workflow", "matt_pocock_active", "matt_pocock_ask"], active_tools
            elif action == "cancel":
                assert any(entry["status"] == "cancelled" for entry in entries), entries
                assert active_tools[-1] == ["matt_pocock_workflow"], active_tools
            elif action == "complete":
                assert any(entry["status"] == "completed" for entry in entries), entries
                assert active_tools[-1] == ["matt_pocock_workflow"], active_tools

            os.write(master, b"/quit\r")
            wait_for(master, process, transcript, lambda: process.poll() is not None)
            assert process.returncode == 0, transcript.decode(errors="replace")[-4000:]
            return {"action": action, "entries": len(entries), "activeToolsTransitions": len(active_tools)}


def main() -> None:
    pi = shutil.which("pi")
    assert pi, "pi CLI is required"
    cases = [run_case(pi, "view", 1), run_case(pi, "transition", 2), run_case(pi, "cancel", 4), run_case(pi, "complete", 3)]
    print(json.dumps({"pi": "1.0 active menu PTY passed", "cases": cases}))


if __name__ == "__main__":
    main()
