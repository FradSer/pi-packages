"""Real Pi v1.0 restore-boundary checks against persisted workflow records.

Each case starts a workflow through the real agent, edits only the newest
persisted custom record, then starts a second real Pi process on that session.
The provider is deterministic and local; no model service or user auth is used.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from runtime_live import call, command, isolated_env, read_rows

FIXTURE = Path(__file__).with_name("restore-live-fixture.ts")
WORKFLOW_TYPE = "matt-pocock-workflow"


def restore_command(pi: str, session: Path) -> list[str]:
    args = command(pi, session=session)
    extension_index = args.index("--extension")
    args[extension_index + 1] = str(FIXTURE)
    return args


def prepare_latest_record(session: Path, transform: Callable[[dict], dict]) -> dict:
    lines = [json.loads(line) for line in session.read_text().splitlines() if line.strip()]
    active = next(
        entry["data"]
        for entry in reversed(lines)
        if entry.get("type") == "custom" and entry.get("customType") == WORKFLOW_TYPE
        and isinstance(entry.get("data"), dict) and entry["data"].get("status") == "active"
    )
    latest = lines[-1]
    record = transform(dict(active))
    lines.append({
        "type": "custom",
        "customType": WORKFLOW_TYPE,
        "data": record,
        "id": str(uuid.uuid4()),
        "parentId": latest.get("id"),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })
    session.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    return active


def run_case(pi: str, name: str, transform: Callable[[dict], dict], expect_cancelled: bool) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix=f"mp-restore-{name}-") as directory:
        root = Path(directory)
        session = root / "restore.jsonl"
        evidence = root / "restore-evidence.jsonl"
        first_env = isolated_env(root, evidence, [call("matt_pocock_workflow", mode="workflow", route="hard-bug")])
        first = subprocess.run(
            [*restore_command(pi, session), "--print", "Create restore probe workflow"],
            cwd=root, env=first_env, input="", text=True, capture_output=True, timeout=60,
        )
        assert first.returncode == 0, first.stdout + first.stderr
        assert session.exists(), f"{name}: Pi did not write a session"
        old_state = prepare_latest_record(session, transform)
        baseline_rows = read_rows(evidence)
        baseline = len(baseline_rows)
        baseline_contexts = [row for row in baseline_rows if row.get("kind") == "model_context"]
        assert baseline_contexts, (name, baseline_rows)
        historical_source_count = baseline_contexts[-1]["procedureSourceCount"]

        second_env = isolated_env(root, evidence, [])
        second = subprocess.run(
            [*restore_command(pi, session), "--print", f"Inspect {name} restore"],
            cwd=root, env=second_env, input="", text=True, capture_output=True, timeout=60,
        )
        assert second.returncode == 0, second.stdout + second.stderr
        rows = read_rows(evidence)[baseline:]
        starts = [row for row in rows if row.get("kind") == "session_start"]
        assert starts, (name, rows)
        active_tools = starts[-1]["activeTools"]
        assert "matt_pocock_active" not in active_tools and "matt_pocock_ask" not in active_tools, (name, starts)
        assert "matt_pocock_workflow" in active_tools, (name, starts)

        restored = [row for row in rows if row.get("kind") == "procedure" and row.get("display") is False]
        assert not restored, (name, restored)
        # Pi renders the system prompt from mutable prompt sections and never hands it
        # to the provider, so the contract is observed on the injected section itself:
        # the restored turn receives the inactive catalogue and no active guidance.
        prompt_sections = [row for row in rows if row.get("kind") == "prompt_section"]
        assert prompt_sections, (name, rows)
        assert all("## Available Matt Pocock Workflows and Capabilities" in row["guidance"]
                   for row in prompt_sections), prompt_sections
        assert all("Matt Pocock workflow active:" not in row["guidance"]
                   for row in prompt_sections), prompt_sections
        contexts = [row for row in rows if row.get("kind") == "model_context"]
        assert contexts, (name, rows)
        # Pi keeps historical procedure messages in the transcript. The
        # restore contract is that the current turn receives no extra restore
        # message or active guidance; the source count must remain unchanged.
        assert all(row.get("procedureSourceCount") == historical_source_count for row in contexts), (name, contexts)

        cancelled = [row for row in rows if row.get("kind") == "append"
                     and row.get("data", {}).get("status") == "cancelled"]
        if expect_cancelled:
            assert cancelled, (name, rows)
            terminal = cancelled[-1]["data"]
            assert terminal["workItemId"] == old_state["workItemId"]
            assert terminal["reason"].startswith("Restore validation failed"), terminal
        else:
            assert not cancelled, (name, cancelled)
        return {
            "case": name,
            "latest": transform(old_state)["status"],
            "activeTools": active_tools,
            "restoreCancelled": bool(cancelled),
            "modelContexts": len(contexts),
        }


def main() -> None:
    pi = shutil.which("pi")
    assert pi, "Pi v1.0 CLI is required"
    cases = [
        ("terminal-completed", lambda state: {**state, "status": "completed"}, False),
        ("terminal-cancelled", lambda state: {**state, "status": "cancelled", "reason": "fixture cancellation"}, False),
        ("bad-version", lambda state: {**state, "version": 99}, False),
        ("wrong-phase", lambda state: {**state, "phase": "invalid-phase"}, True),
        ("invalid-reference", lambda state: {**state, "loadedReferences": ["__invalid_reference__"]}, True),
        ("invalid-procedure", lambda state: {**state, "procedure": "__invalid_procedure__"}, True),
    ]
    results = [run_case(pi, name, transform, expect_cancelled) for name, transform, expect_cancelled in cases]
    print(json.dumps({"pi": "1.0 restore boundaries passed", "cases": results}))


if __name__ == "__main__":
    main()
