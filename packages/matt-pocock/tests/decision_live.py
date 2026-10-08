"""Run the decision fixture through Pi v1.0's real PTY UI.

The provider and model are deterministic and local. The only subprocess fake is
an ``osascript`` failure used to prove native-dialog fallback on macOS.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from live_pty import isolated_env, live_pi, pi_command, read_jsonl, wait_for

FIXTURE = Path(__file__).with_name("decision-live-fixture.ts")


def check_results(rows: list[dict]) -> None:
    results = [row for row in rows if row["kind"] == "result"]
    assert len(results) == 9, results
    assert all(not row["isError"] for row in results), results
    asks = [row for row in results if row["tool"] == "matt_pocock_ask"]
    assert [row["details"] for row in asks] == [
        {"answer": "A", "is_custom": False, "source": "choice_selected"},
        {"answer": "live custom answer", "is_custom": True, "source": "custom_input"},
        {"pending": True, "source": "custom_input_cancelled"},
        {"pending": True, "timed_out": False, "source": "cancelled"},
        {"pending": True, "timed_out": False, "source": "cancelled"},
        # Pi's Ctrl-C is consumed by the active selector as user cancellation;
        # programmatic AbortSignal propagation is covered by unit boundaries.
        {"pending": True, "timed_out": False, "source": "cancelled"},
        {"answer": "(Recommended) Use adjacent verification", "is_custom": False,
         "timed_out": True, "pending": False, "source": "timeout_recommended"},
    ], asks
    assert asks[0]["content"][0]["text"] == "LIVE selection\n\n> A"
    assert asks[-1]["content"][0]["text"] == (
        "LIVE recommendation timeout\n\n> Use adjacent verification"
    )
    assert "(Recommended)" not in asks[-1]["content"][0]["text"]
    assert "Block for review" not in asks[-1]["content"][0]["text"]


def main() -> None:
    pi = shutil.which("pi")
    assert pi, "pi CLI is required"
    with tempfile.TemporaryDirectory(prefix="mp-decision-live-") as directory:
        root = Path(directory)
        config = root / "matt-pocock.json"
        config.write_text('{"useNativeDialog": true}')
        fake_bin = root / "bin"
        fake_bin.mkdir()
        marker = root / "native-fallback.log"
        fake = fake_bin / "osascript"
        fake.write_text(f'#!/bin/sh\nprintf "fallback\\n" >> {marker}\nexit 1\n')
        fake.chmod(0o755)
        env = isolated_env(root, extra={
            "PI_DECISION_LIVE_AUTH": secrets.token_hex(16), "PI_DECISION_LIVE_SNAPSHOTS": str(root / "snapshots.jsonl"),
            "PI_MATT_POCOCK_CONFIG_FILE": str(config), "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
            "TERM": "xterm-256color",
        })
        command = pi_command(pi, FIXTURE, "decision-live-fixture", "Run decision fixture")

        def prompt(name: str) -> None:
            wait_for(master, process, transcript, lambda: name.encode() in transcript)

        def send(data: bytes) -> None:
            os.write(master, data)

        def open_menu() -> int:
            start = len(transcript)
            send(b"\x1b[200~/matt-pocock\x1b[201~\r")
            wait_for(master, process, transcript, lambda: b"Matt Pocock" in transcript[start:])
            return start

        def next_ready() -> None:
            count = transcript.count(b"MP_DECISION_LIVE_READY")
            wait_for(master, process, transcript, lambda: transcript.count(b"MP_DECISION_LIVE_READY") > count)

        with live_pi(command, cwd=root, env=env) as (master, process, transcript):
            prompt("LIVE selection")
            send(b"\r")
            prompt("LIVE custom")
            send(b"\x1b[B\x1b[B\r")
            time.sleep(0.2)
            send(b"live custom answer\r")
            prompt("LIVE blank custom")
            send(b"\x1b[B\x1b[B\r")
            time.sleep(0.2)
            send(b"\r")
            prompt("LIVE escape")
            send(b"\x1b")
            prompt("LIVE timeout without recommendation")
            time.sleep(0.25)
            assert len([row for row in read_jsonl(root / "snapshots.jsonl") if row["kind"] == "result"]) == 5
            send(b"\x1b")
            prompt("LIVE abort")
            send(b"\x03")
            next_ready()

            # Exercise the inactive command menu through the same PTY. Its
            # selector's Enter/Escape paths are separate from tool questions.
            menu = open_menu()
            assert b"Start a workflow" in transcript[menu:] and b"Run a standalone capability" in transcript[menu:]
            send(b"\x1b")  # Escape leaves the inactive menu without a side effect.
            time.sleep(0.15)
            # Enter selects the menu's default Start a task item and keeps the
            # routing prompt in the model-facing turn without starting state.
            open_menu()
            send(b"\r")
            next_ready()
            send(b"/quit\r")
            wait_for(master, process, transcript, lambda: process.poll() is not None)
            assert process.returncode == 0, transcript.decode(errors="replace")[-4000:]
            check_results(read_jsonl(root / "snapshots.jsonl"))
            fallback_count = len(marker.read_text().splitlines()) if marker.exists() else 0
            native_enabled = (os.uname().sysname == "Darwin"
                              and not any(env.get(name) for name in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"))
                              and env.get("CI", "") in ("", "false", "0"))
            if native_enabled:
                assert fallback_count >= 6, fallback_count
            else:
                assert fallback_count == 0, fallback_count
            print(json.dumps({"pi": "1.0 live PTY passed", "nativeFallbackAttempts": fallback_count, "platform": os.uname().sysname}))


if __name__ == "__main__":
    main()
