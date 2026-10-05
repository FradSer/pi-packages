"""Real Pi v1.0 adversarial gateway and UI race checks.

The extension fixture uses Pi's registered handlers and provider transport. Its
only deterministic intervention is an in-process state replacement while the
real selector/menu is open; there are no fake dialogs, model calls, or auth.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path

from live_pty import isolated_env, live_pi, pi_command, read_jsonl, wait_for

FIXTURE = Path(__file__).with_name("adversarial-live-fixture.ts")


def run_reference(pi: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="mp-adversarial-reference-") as directory:
        root = Path(directory)
        evidence = root / "evidence.jsonl"
        env = isolated_env(root, extra={
            "PI_NO_NATIVE_DIALOG": "1",
            "PI_ADVERSARIAL_LIVE_CASE": "reference",
            "PI_ADVERSARIAL_LIVE_AUTH": secrets.token_hex(16),
            "PI_ADVERSARIAL_LIVE_EVIDENCE": str(evidence),
        })
        command = pi_command(pi, FIXTURE, "matt-pocock-adversarial-live", "Run reference adversarial fixture")
        with live_pi(command, cwd=root, env=env) as (master, process, transcript):
            wait_for(master, process, transcript, lambda: any(row.get("kind") == "tool_result" for row in read_jsonl(evidence)))
            rows = read_jsonl(evidence)
            results = [row for row in rows if row.get("kind") == "tool_result"]
            assert len(results) == 1, rows
            result = results[0]
            assert result["tool"] == "matt_pocock_workflow", result
            assert result["isError"] is False, result
            content = json.dumps(result["content"], ensure_ascii=False)
            assert 'procedure/domain' in content, result
            assert 'procedure/setup-matt-pocock-skills' not in content, result
            assert not any(row.get("kind") == "append" for row in rows), rows
            assert not any(row.get("kind") == "procedure" for row in rows), rows
            os.write(master, b"/quit\r")
            wait_for(master, process, transcript, lambda: process.poll() is not None)
            assert process.returncode == 0, transcript.decode(errors="replace")[-4000:]
            return {"case": "reference-only", "isError": result["isError"], "rootInvoked": False}


def run_ask_replacement(pi: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="mp-adversarial-ask-") as directory:
        root = Path(directory)
        evidence = root / "evidence.jsonl"
        env = isolated_env(root, extra={
            "PI_NO_NATIVE_DIALOG": "1",
            "PI_ADVERSARIAL_LIVE_CASE": "ask-complete",
            "PI_ADVERSARIAL_LIVE_AUTH": secrets.token_hex(16),
            "PI_ADVERSARIAL_LIVE_EVIDENCE": str(evidence),
        })
        command = pi_command(pi, FIXTURE, "matt-pocock-adversarial-live", "Run ask replacement fixture")
        with live_pi(command, cwd=root, env=env) as (master, process, transcript):
            wait_for(master, process, transcript, lambda: any(row.get("kind") == "replacement" for row in read_jsonl(evidence)))
            wait_for(master, process, transcript, lambda: any(row.get("kind") == "ask_result" for row in read_jsonl(evidence)))
            rows = read_jsonl(evidence)
            replacement = next(row for row in rows if row.get("kind") == "replacement")
            result = next(row for row in rows if row.get("kind") == "ask_result")["result"]
            assert isinstance(result, dict), rows
            assert result.get("details") == {"pending": True, "source": "aborted"}, result
            assert isinstance(replacement.get("result"), dict), replacement
            assert replacement["result"].get("details", {}).get("state", {}).get("status") == "completed", replacement
            os.write(master, b"/quit\r")
            wait_for(master, process, transcript, lambda: process.poll() is not None)
            assert process.returncode == 0, transcript.decode(errors="replace")[-4000:]
            return {"case": "ask-complete", "ask": result.get("details"), "replacement": "completed"}


def run_human_reference(pi: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="mp-adversarial-human-reference-") as directory:
        root = Path(directory)
        evidence = root / "evidence.jsonl"
        env = isolated_env(root, extra={
            "PI_NO_NATIVE_DIALOG": "1",
            "PI_ADVERSARIAL_LIVE_CASE": "human-reference",
            "PI_ADVERSARIAL_LIVE_AUTH": secrets.token_hex(16),
            "PI_ADVERSARIAL_LIVE_EVIDENCE": str(evidence),
        })
        command = pi_command(pi, FIXTURE, "matt-pocock-adversarial-live", "Run human reference fixture")
        with live_pi(command, cwd=root, env=env) as (master, process, transcript):
            wait_for(master, process, transcript, lambda: b"ADVERSARIAL_LIVE_READY" in transcript)
            os.write(master, b"/adversarial-reference\r")
            wait_for(master, process, transcript, lambda: any(row.get("kind") == "human_reference_started" for row in read_jsonl(evidence)))
            wait_for(master, process, transcript, lambda: any(
                row.get("kind") == "tool_result" and row.get("tool") == "matt_pocock_workflow"
                and row.get("details", {}).get("mode") == "reference"
                for row in read_jsonl(evidence)
            ))
            rows = read_jsonl(evidence)
            results = [row for row in rows if row.get("kind") == "tool_result" and row.get("details", {}).get("mode") == "reference"]
            assert len(results) == 1, rows
            result = results[0]
            assert result["isError"] is False, result
            assert result["details"] == {
                "mode": "reference", "capability": "setup-matt-pocock-skills", "reference": "domain",
            }, result
            os.write(master, b"/quit\r")
            wait_for(master, process, transcript, lambda: process.poll() is not None)
            assert process.returncode == 0, transcript.decode(errors="replace")[-4000:]
            return {"case": "human-reference", "isError": result["isError"], "reference": "domain"}


def run_menu_replacement(pi: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="mp-adversarial-menu-") as directory:
        root = Path(directory)
        evidence = root / "evidence.jsonl"
        env = isolated_env(root, extra={
            "PI_NO_NATIVE_DIALOG": "1",
            "PI_ADVERSARIAL_LIVE_CASE": "menu-complete",
            "PI_ADVERSARIAL_LIVE_AUTH": secrets.token_hex(16),
            "PI_ADVERSARIAL_LIVE_EVIDENCE": str(evidence),
        })
        command = pi_command(pi, FIXTURE, "matt-pocock-adversarial-live", "Run menu replacement fixture")
        with live_pi(command, cwd=root, env=env) as (master, process, transcript):
            wait_for(master, process, transcript, lambda: b"ADVERSARIAL_LIVE_READY" in transcript)
            os.write(master, b"/adversarial-menu\r")
            wait_for(master, process, transcript, lambda: any(row.get("kind") == "menu_invoked" for row in read_jsonl(evidence)))
            wait_for(master, process, transcript, lambda: b"Matt Pocock" in transcript)
            wait_for(master, process, transcript, lambda: any(row.get("kind") == "menu_replacement" for row in read_jsonl(evidence)))
            os.write(master, b"\x1b[B\x1b[B\x1b[B\r")
            wait_for(master, process, transcript, lambda: any(row.get("kind") == "menu_after" for row in read_jsonl(evidence)))
            rows = read_jsonl(evidence)
            started = next(row for row in rows if row.get("kind") == "menu_replacement")["started"]
            workflow_a = next(row for row in rows if row.get("kind") == "menu_workflow_a")["result"]
            state = next(row for row in rows if row.get("kind") == "menu_after")["state"]
            assert isinstance(state, dict), rows
            assert state.get("status") == "active", state
            assert isinstance(started, dict) and isinstance(workflow_a, dict), rows
            started_state = started.get("details", {})
            workflow_a_state = workflow_a.get("details", {})
            assert started_state.get("status") == "active", started
            assert workflow_a_state.get("status") == "active", workflow_a
            assert started_state.get("workItemId") == state.get("workItemId"), (started, state)
            assert workflow_a_state.get("workItemId") != state.get("workItemId"), (workflow_a, state)
            assert any(row.get("kind") == "menu_done" for row in rows), rows
            os.write(master, b"/quit\r")
            wait_for(master, process, transcript, lambda: process.poll() is not None)
            assert process.returncode == 0, transcript.decode(errors="replace")[-4000:]
            return {
                "case": "menu-complete",
                "latestStatus": state.get("status"),
                "selection": "Complete current workflow",
                "workItemA": workflow_a_state.get("workItemId"),
                "workItemB": state.get("workItemId"),
            }


def main() -> None:
    pi = shutil.which("pi")
    assert pi, "Pi v1.0 CLI is required"
    results = [run_reference(pi), run_human_reference(pi), run_ask_replacement(pi), run_menu_replacement(pi)]
    print(json.dumps({"pi": "1.0 adversarial live passed", "cases": results}))


if __name__ == "__main__":
    main()
