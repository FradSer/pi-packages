"""Run the decision fixture through Pi v1.0's real PTY UI.

The provider and model are deterministic and local. The only subprocess fake is
an ``osascript`` failure used to prove native-dialog fallback on macOS.

Set ``PI_DECISION_LIVE_CAPTURE`` to a directory to retain the raw PTY bytes, the
terminal dimensions and the ordered interactions of the run.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from live_pty import isolated_env, live_pi, pi_command, read_jsonl, set_size, wait_for

FIXTURE = Path(__file__).with_name("decision-live-fixture.ts")
PACKAGE = Path(__file__).resolve().parents[2]
REPO = PACKAGE.parents[1]
INITIAL_SIZE = (120, 40)
RESIZES = ((48, 24), (48, 12), (120, 40))


def check_results(rows: list[dict]) -> None:
    results = [row for row in rows if row["kind"] == "result"]
    assert len(results) == 10, results
    assert all(not row["isError"] for row in results), results
    asks = [row for row in results if row["tool"] == "matt_pocock_ask"]
    assert [row["details"] for row in asks] == [
        {"answer": "A", "is_custom": False, "source": "choice_selected"},
        {"answer": "live custom answer", "is_custom": True, "source": "custom_input"},
        {"pending": True, "source": "custom_input_cancelled"},
        {"pending": True, "timed_out": False, "source": "cancelled"},
        # The 0.05 second deadline dismisses this selector with no key press and adopts
        # the recommendation, so the workflow continues instead of waiting.
        {"answer": "B", "is_custom": False, "timed_out": True,
         "pending": False, "source": "timeout_recommended"},
        # The same live selector survives two resizes and is still dismissed by
        # its own deadline.
        {"answer": "A", "is_custom": False, "timed_out": True,
         "pending": False, "source": "timeout_recommended"},
        # Pi's Ctrl-C is consumed by the active selector as user cancellation;
        # programmatic AbortSignal propagation is covered by unit boundaries.
        {"pending": True, "timed_out": False, "source": "cancelled"},
        {"answer": "(Recommended) Use adjacent verification", "is_custom": False,
         "timed_out": True, "pending": False, "source": "timeout_recommended"},
    ], asks
    assert asks[0]["content"][0]["text"] == "LIVE selection\n\n> A"
    assert asks[4]["content"][0]["text"] == "LIVE deadline adopts the second option\n\n> B"
    assert asks[5]["content"][0]["text"] == "LIVE resized deadline\n\n> A"
    assert asks[-1]["content"][0]["text"] == (
        "LIVE recommendation timeout\n\n> Use adjacent verification"
    )
    assert "(Recommended)" not in asks[-1]["content"][0]["text"]
    assert "Block for review" not in asks[-1]["content"][0]["text"]


def source_revision() -> dict[str, object]:
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True, capture_output=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(REPO), "status", "--porcelain", "packages/matt-pocock"],
        text=True, capture_output=True,
    ).stdout.strip()
    return {
        "gitHead": head or None,
        "packageWorkTreeDirty": bool(status),
        "indexTsSha256": hashlib.sha256((PACKAGE / "src" / "index.ts").read_bytes()).hexdigest(),
        "fixtureSha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
    }


def main() -> None:
    pi = shutil.which("pi")
    assert pi, "pi CLI is required"
    capture_directory = os.environ.get("PI_DECISION_LIVE_CAPTURE")
    capture = Path(capture_directory) if capture_directory else None
    if capture is not None:
        capture.mkdir(parents=True, exist_ok=True)
    interactions: list[dict[str, object]] = []
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
            interactions.append({"kind": "expect", "text": name})
            wait_for(master, process, transcript, lambda: name.encode() in transcript)

        def send(data: bytes) -> None:
            interactions.append({"kind": "input", "bytes": data.hex(), "text": data.decode(errors="replace")})
            os.write(master, data)

        def resize(columns: int, rows: int, question: str) -> None:
            before = len(transcript)
            set_size(master, columns, rows)
            # A macOS master-side size change does not signal the child, so send the
            # resize event to the live component and wait for it to repaint.
            os.kill(process.pid, signal.SIGWINCH)
            wait_for(master, process, transcript, lambda: question.encode() in transcript[before:])
            redrawn = bytes(transcript[before:])
            interactions.append({
                "kind": "resize", "columns": columns, "rows": rows,
                "redrawBytes": len(redrawn), "questionRedrawn": question.encode() in redrawn,
            })
            # The composed screen must still carry the decision row after the resize.
            assert question.encode() in transcript, (columns, rows)

        def open_menu() -> int:
            start = len(transcript)
            send(b"\x1b[200~/matt-pocock\x1b[201~\r")
            # Synchronize on the drawn rows, not on the header: the rows are what
            # the assertions below inspect.
            wait_for(master, process, transcript, lambda: b"Matt Pocock" in transcript[start:])
            wait_for(master, process, transcript, lambda: b"Run a standalone capability" in transcript[start:])
            return start

        def next_ready() -> None:
            count = transcript.count(b"MP_DECISION_LIVE_READY")
            wait_for(master, process, transcript, lambda: transcript.count(b"MP_DECISION_LIVE_READY") > count)

        with live_pi(command, cwd=root, env=env, size=INITIAL_SIZE, capture=capture and capture / "decision-live.pty") as (master, process, transcript):
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
            # No key press reaches this selector: its own deadline must dismiss it.
            prompt("LIVE deadline adopts the second option")
            wait_for(master, process, transcript, lambda: len([
                row for row in read_jsonl(root / "snapshots.jsonl") if row["kind"] == "result"
            ]) >= 6)
            # Resize the same live selector, then let its own deadline dismiss it.
            prompt("LIVE resized deadline")
            for columns, rows in RESIZES:
                resize(columns, rows, "LIVE resized deadline")
            wait_for(master, process, transcript, lambda: len([
                row for row in read_jsonl(root / "snapshots.jsonl") if row["kind"] == "result"
            ]) >= 7)
            prompt("LIVE abort")
            send(b"\x03")
            prompt("LIVE recommendation timeout")
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

        report: dict[str, object] = {
            "pi": "1.0 live PTY passed", "nativeFallbackAttempts": fallback_count, "platform": os.uname().sysname,
        }
        if capture is not None:
            raw = (capture / "decision-live.pty").read_bytes()
            for label in ("LIVE selection", "LIVE resized deadline", "LIVE recommendation timeout"):
                assert label.encode() in raw, label
            assert b"\x1b[" in raw, "the capture must keep the terminal escape sequences"
            (capture / "decision-live-interactions.jsonl").write_text(
                "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in interactions),
            )
            (capture / "decision-live-capture.json").write_text(json.dumps({
                "provider": "decision-live-fixture",
                "command": command,
                "fixture": FIXTURE.name,
                "cwdKind": "disposable temporary directory",
                "isolatedHome": True,
                "offline": env.get("PI_OFFLINE") == "1",
                "initialSize": {"columns": INITIAL_SIZE[0], "rows": INITIAL_SIZE[1]},
                "resizeSequence": [{"columns": columns, "rows": rows} for columns, rows in RESIZES],
                "captureBytes": len(raw),
                "captureSha256": hashlib.sha256(raw).hexdigest(),
                "interactions": "decision-live-interactions.jsonl",
                "sourceRevision": source_revision(),
                "nativeFallbackAttempts": fallback_count,
                "platform": os.uname().sysname,
            }, indent=2, sort_keys=True) + "\n")
            report["captureDirectory"] = str(capture)
            report["captureBytes"] = len(raw)
            report["captureSha256"] = hashlib.sha256(raw).hexdigest()
        print(json.dumps(report))


if __name__ == "__main__":
    main()