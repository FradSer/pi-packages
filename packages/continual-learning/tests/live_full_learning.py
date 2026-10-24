"""Real-provider cold-start full learning, with disposable native Pi sessions."""
from __future__ import annotations

from live_acceptance_support import workspace_pi

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from live_manual_memory import NativeTui, _model, _receipt_files, _receipt_state, _runtime_env, _changed_receipt_views
from live_smoke import (prepare, memory_bodies, private_memory_root, shared_surface_leaks,
                        run_pi, successful_tool_call, path_argument_matches, assistant_visible_text)

PACKAGE = Path(__file__).resolve().parents[1]
PRIVATE = "PRIVATE_FULL_SIGNOFF_AMBER"
SHARED = "PROJECT_FULL_RELEASE_INDIGO"


def full_receipt(tui: NativeTui, agent: Path, before: dict) -> dict:
    found: dict | None = None

    def ready() -> bool:
        nonlocal found
        matches=[value for value in _changed_receipt_views(agent,before)
                 if value.get('kind')=='learning-pipeline-receipt' and value.get('version')==1 and value.get('mode')=='full']
        if len(matches)==1:
            found=matches[0]
            return True
        return False

    tui.wait_until(ready, 480, "Full learning did not produce a parent receipt")
    assert found is not None
    return found


def successful_phases(receipt: dict) -> bool:
    # A bounded pre-mutation rejection followed by a verified repair is an
    # observed success; checking every attempt would misreport that recovery.
    final = {attempt["phase"]: attempt["outcome"] for attempt in receipt["attempts"]}
    return bool(final) and all(outcome in {"applied", "noop"} for outcome in final.values())


def verify() -> dict:
    with tempfile.TemporaryDirectory(prefix="cl-full-learning-") as raw:
        base = Path(raw).resolve()
        project, agent, probe = prepare(base, False)
        (agent / "memory" / "settings.json").write_text(json.dumps({"autoMemory": False, "agentsMd": {"disabled": True}}))
        provider, model = _model(agent)
        home = base / "home"
        home.mkdir()
        env = _runtime_env(agent, home)
        pi = workspace_pi(Path(__file__).resolve().parents[3])
        ready = base / "ready"
        probe.write_text("import fs from 'node:fs';export default function(pi){pi.on('session_start',()=>"
                         f"fs.writeFileSync({json.dumps(str(ready))},'ready'));}}")
        command = [pi, "--no-extensions", "-e", str(probe), "-e", str(PACKAGE / "index.ts"),
                   "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-approve",
                   "--model", f"{provider}/{model}", "--tools", "read"]
        tui = NativeTui(command, project, env)
        try:
            tui.wait_until(ready.is_file, 30, "Pi did not start")
            before = _receipt_state(agent)
            tui.send("/consolidate full")
            empty = full_receipt(tui, agent, before)
            assert empty["attempts"] == [] and empty["totals"]["totalTokens"] == 0
            assert empty["input"] == {"source": "none", "entryCount": 0}
        finally:
            tui.close()
        ready.unlink()

        source_prompt = (f"My personal response sign-off preference is {PRIVATE}. This is personal preference data. "
                         f"The settled project release marker is {SHARED}. This project fact is public, non-sensitive, and explicitly safe to share in project Memory. These are durable facts. Reply only: acknowledged.")
        result = subprocess.run([pi, "--no-extensions", "--no-skills", "--no-context-files", "--no-prompt-templates",
                                 "--no-themes", "--no-approve", "--model", f"{provider}/{model}",
                                 "--tools", "read", "--print", source_prompt],
                                cwd=project, env=env, capture_output=True, text=True, timeout=480)
        assert result.returncode == 0, "Source Pi session failed"
        sources = [file for file in (agent / "sessions").rglob("*.jsonl") if SHARED in file.read_text()]
        assert len(sources) == 1
        source = sources[0]
        original = source.read_bytes()
        source_id = json.loads(original.splitlines()[0])["id"]
        source_digest = hashlib.sha256(original).hexdigest()

        tui = NativeTui(command, project, env)
        try:
            tui.wait_until(ready.is_file, 30, "Fresh Pi did not start")
            before = _receipt_state(agent)
            tui.send("/consolidate full")
            receipt = full_receipt(tui, agent, before)
            assert receipt["input"]["source"] == "recent-project-session"
            assert receipt["input"]["sessionId"] == source_id and receipt["input"]["sourceDigest"] == source_digest
            assert any(attempt["phase"] == "memory" and attempt["outcome"] == "applied" and attempt["operations"] >= 2
                       for attempt in receipt["attempts"]), receipt
            assert successful_phases(receipt), {"receipt": receipt, "errors": [file.read_text() for file in (agent / "memory" / "runs").rglob("harness-error.txt")], "repairErrors": [json.loads(file.read_text().splitlines()[-1]).get("errors") for file in (agent / "memory" / "runs").rglob("harness-repair.md")]}
            root = private_memory_root(agent)
            private, public = memory_bodies(root), memory_bodies(project / ".memory")
            preferences = [name for name, body in private.items() if PRIVATE in body]
            facts = [name for name, body in public.items() if SHARED in body]
            assert preferences and facts and not shared_surface_leaks(project, PRIVATE), {"private": private, "public": public, "sharedLeak": shared_surface_leaks(project, PRIVATE)}
            assert all(private[name] == public[name] for name in facts)
            plans = [json.loads(file.read_text()) for file in (agent / "memory" / "runs").rglob("plan.json")]
            assert any(any(item.get("name") in preferences and item.get("kind") == "preference" and item.get("classification") == "private"
                           for item in plan.get("newMemories", [])) for plan in plans)
            names_before = set(private)
            before = _receipt_state(agent)
            tui.send("/consolidate full")
            repeated = full_receipt(tui, agent, before)
            assert successful_phases(repeated), {"receipt": repeated, "errors": [file.read_text() for file in (agent / "memory" / "runs").rglob("harness-error.txt")], "repairErrors": [json.loads(file.read_text().splitlines()[-1]).get("errors") for file in (agent / "memory" / "runs").rglob("harness-repair.md")]}
            assert set(memory_bodies(root)) == names_before, "Repeated full learning duplicated existing knowledge"
        finally:
            tui.close()
        assert source.read_bytes() == original, "Learning modified its source session"
        preference, fact = root / preferences[0], project / ".memory" / facts[0]
        fresh = run_pi(project, agent, probe, f"Read `{preference}` and `{fact}` with the read tool. "
                       "State the project release marker and finish with my saved preferred sign-off.", "read")
        for target, marker in ((preference, PRIVATE), (fact, SHARED)):
            assert successful_tool_call(fresh["messages"], "read", lambda args, target=target: path_argument_matches(project, target, args), marker)
        visible = assistant_visible_text(fresh["messages"])
        assert PRIVATE in visible and SHARED in visible
        return {"provider": provider, "model": model, "emptyFullZeroCalls": True,
                "recentProjectSourceFrozen": True, "sourceUnchanged": True, "coldStartMemories": len(private),
                "privatePreference": True, "safeFactMirrored": True, "repeatNoDuplicate": True,
                "freshNativeReadsAndUse": True, "firstOperations": receipt["operations"], "repeatOperations": repeated["operations"],
                "harnessValidationDiagnostics": [json.loads(file.read_text().splitlines()[-1]).get("errors", [])
                    for file in (agent / "memory" / "runs").rglob("harness-repair.md")]}


if __name__ == "__main__":
    print(json.dumps(verify()), flush=True)
