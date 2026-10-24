"""Real automatic-Memory regression for an omitted personal preference.

Two fresh trials combine private response preferences, shared facts and an
existing-entry correction. Harness and AGENTS phases are disabled to keep their
independent outcomes from masking Memory evidence. This explicit check spends
configured-provider tokens; it is not collected by pytest.
"""

from __future__ import annotations

from continuous_failure_retention import deduplicate_receipt_views

import json
import hashlib
import math
from pathlib import Path
import re
import tempfile

from live_smoke import (
    assert_current_memory_command, assistant_visible_text, memory_bodies,
    path_argument_matches, prepare, private_memory_root, run_pi,
    shared_surface_leaks, successful_tool_call,
)

PRIVATE = "PRIVATE_PREF_QUARTZ"
SHARED = "PROJECT_FACT_CALDERA"
SEED = "project_smoke_build_command.md"


def verify_preference_artifacts(agent: Path, preferences: list[str], facts: list[str]) -> dict:
    runs = agent / "memory" / "runs"
    try:
        receipts = deduplicate_receipt_views([json.loads(p.read_text()) for p in runs.rglob("learning-pipeline-receipt.json")])
    except ValueError as error:
        raise AssertionError("Invalid or conflicting learning receipts") from error
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.get("kind") == "learning-pipeline-receipt" and receipt.get("version") == 1
    assert receipt.get("mode") == "automatic"
    assert receipt["screen"]["memory"] is True and receipt["screen"]["harness"] is False and receipt["screen"]["agents"] is False
    attempts = receipt.get("attempts")
    assert isinstance(attempts, list) and attempts
    for attempt in attempts:
        assert isinstance(attempt, dict) and attempt.get("phase") in {"selector", "memory"}
        assert type(attempt.get("attempt")) is int and attempt["attempt"] in {0, 1}
        assert attempt.get("outcome") in {"applied", "noop"}
        assert type(attempt.get("operations")) is int and attempt["operations"] >= 0
        duration = attempt.get("durationMs")
        assert type(duration) in {int, float} and math.isfinite(duration) and duration >= 0
    assert attempts[0]["phase"] == "selector" and attempts[0]["attempt"] == 0 and attempts[0]["operations"] == 0
    assert attempts[0]["outcome"] == "applied"
    assert all(attempt["phase"] == "memory" for attempt in attempts[1:])
    assert [attempt["attempt"] for attempt in attempts[1:]] in [[0], [0, 1]]
    assert attempts[-1]["outcome"] == "applied" and attempts[-1]["operations"] >= 3
    assert receipt.get("operations") == sum(attempt["operations"] for attempt in attempts)
    assert receipt.get("retries") == sum(attempt["attempt"] > 0 for attempt in attempts)

    # The disposable scope has one Memory application. A matching marker in
    # an unrelated historical plan cannot stand in for this run's evidence.
    plans = [(file, json.loads(file.read_text())) for file in runs.rglob("plan.json")]
    plans = [(file, plan) for file, plan in plans if plan.get("kind") == "memory-consolidation-plan"]
    assert len(plans) == 1, "Expected one applied Memory plan in the fresh scope"
    plan_path, plan = plans[0]
    assert plan.get("version") == 1 and plan.get("schemaVersion") == 1
    manifest = json.loads((plan_path.parent / "manifest.json").read_text())
    snapshot_hash = hashlib.sha256((plan_path.parent / "snapshot.json").read_bytes()).hexdigest()
    assert plan.get("runId") == manifest.get("runId") == plan_path.parent.name
    assert plan.get("scopeKey") == manifest.get("scopeKey")
    assert plan.get("scopeDigest") == manifest.get("scopeDigest")
    assert plan.get("artifactHash") == manifest.get("snapshotDigest") == snapshot_hash
    assert SEED in plan.get("selected", [])
    assert any(operation.get("name") == SEED and operation.get("kind") == "rewrite"
               for operation in plan.get("operations", []) if isinstance(operation, dict))
    proposals = plan.get("newMemories", [])
    assert any(proposal.get("name") in preferences and proposal.get("kind") == "preference"
               and proposal.get("classification") == "private" and PRIVATE in proposal.get("content", "")
               for proposal in proposals if isinstance(proposal, dict)), "Missing exact private preference proposal"
    assert any(proposal.get("name") in facts and proposal.get("kind") == "project"
               and proposal.get("classification") == "safe" and SHARED in proposal.get("content", "")
               for proposal in proposals if isinstance(proposal, dict)), "Missing exact shared fact proposal"
    post = json.loads((plan_path.parent / "post-receipt.json").read_text())
    assert post.get("kind") == "memory-consolidation-receipt" and post.get("version") == 1
    assert post.get("phase") == "post"
    for key in ("runId", "scopeDigest", "artifactHash"):
        assert post.get(key) == plan[key]
    assert post.get("planDigest") == hashlib.sha256(plan_path.read_bytes()).hexdigest()
    assert sorted(post.get("selected", [])) == sorted(plan["selected"])
    assert set(preferences + facts) <= set(post.get("created", []))
    return receipt


def trial() -> dict:
    with tempfile.TemporaryDirectory(prefix="cl-private-preference-") as raw:
        project, agent, probe = prepare(Path(raw), True, seed_memory=True)
        settings = agent / "memory" / "settings.json"
        settings.write_text(json.dumps({"autoMemory": True, "agentsMd": {"disabled": True},
                                      "automaticPhases": {"memory": "apply", "harness": "off", "agents": "off"}}))
        run_pi(project, agent, probe,
               f"For my personal replies, I prefer the sign-off marker {PRIVATE}; this is private "
               "preference data and must never become a project Memory entry. Also record this project "
               f"fact as settled shared knowledge: {SHARED} is the release marker for this project. "
               f"The existing {SEED} Memory entry is stale: update it from `bun run check` to "
               "`bun run verify`, and use the updated command in future tasks. "
               "All three are durable requirements. Reply only: acknowledged.", "read")
        private_root = private_memory_root(agent)
        private, public = memory_bodies(private_root), memory_bodies(project / ".memory")
        index = (private_root / "MEMORY.md").read_text()
        preferences = [name for name, body in private.items() if PRIVATE in body
                       and any(name in row and re.search(r"harness[ _-]+only", row, re.I) for row in index.splitlines())]
        assert preferences, "Automatic mixed-task learning omitted the private preference"
        assert not shared_surface_leaks(project, PRIVATE)
        facts = [name for name, body in public.items() if SHARED in body]
        assert facts and all(private[name] == public[name] for name in facts)
        assert private[SEED] == public[SEED]
        assert_current_memory_command(private[SEED], "bun run check", "bun run verify")
        verify_preference_artifacts(agent, preferences, facts)
        settings.write_text(json.dumps({"autoMemory": False, "agentsMd": {"disabled": True}}))
        preference, fact = private_root / preferences[0], project / ".memory" / facts[0]
        fresh = run_pi(project, agent, probe,
                       f"Read `{preference}` and `{fact}` with the read tool. Then state the project's "
                       "release marker and finish with my saved preferred sign-off.", "read", session_name="fresh-memory.jsonl")
        for target, marker in ((preference, PRIVATE), (fact, SHARED)):
            assert successful_tool_call(fresh["messages"], "read", lambda args, target=target: path_argument_matches(project, target, args), marker)
        visible = assistant_visible_text(fresh["messages"])
        assert PRIVATE in visible and SHARED in visible
        return {"privatePreference": True, "sharedFact": True, "updatedSeed": True,
                "nativeBodyReads": True, "savedPreferenceUsed": True, "verifiedReceipt": True}


if __name__ == "__main__":
    for index in range(2):
        print(json.dumps({"trial": index, **trial()}), flush=True)
