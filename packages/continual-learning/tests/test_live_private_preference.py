from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import live_private_preference as probe


def artifacts(agent: Path) -> tuple[Path, Path, Path]:
    runs = agent / "memory" / "runs" / "scope"
    run = runs / "run_fixture"
    run.mkdir(parents=True)
    snapshot = b'{"user":"private preference and shared knowledge"}\n'
    (run / "snapshot.json").write_bytes(snapshot)
    identity = {"runId": run.name, "scopeKey": "scope", "scopeDigest": "scope-digest",
                "artifactHash": hashlib.sha256(snapshot).hexdigest()}
    (run / "manifest.json").write_text(json.dumps({**identity, "snapshotDigest": identity["artifactHash"]}))
    plan = {"kind": "memory-consolidation-plan", "version": 1, "schemaVersion": 1, **identity,
            "selected": [probe.SEED], "operations": [{"name": probe.SEED, "kind": "rewrite"}],
            "newMemories": [
                {"name": "personal.md", "kind": "preference", "classification": "private", "content": probe.PRIVATE},
                {"name": "release.md", "kind": "project", "classification": "safe", "content": probe.SHARED},
            ]}
    plan_path = run / "plan.json"
    plan_path.write_text(json.dumps(plan))
    post_path = run / "post-receipt.json"
    post_path.write_text(json.dumps({"kind": "memory-consolidation-receipt", "version": 1, "schemaVersion": 1, "phase": "post", **identity,
                                    "selected": [probe.SEED], "created": ["personal.md", "release.md"],
                                    "planDigest": hashlib.sha256(plan_path.read_bytes()).hexdigest()}))
    receipt_path = runs / "learning-pipeline-receipt.json"
    receipt_path.write_text(json.dumps({
        "kind": "learning-pipeline-receipt", "version": 1, "mode": "automatic",
        "screen": {"memory": True, "harness": False, "agents": False, "reasons": ["durable evidence"]},
        "attempts": [{"phase": "selector", "attempt": 0, "outcome": "applied", "operations": 0, "durationMs": 1},
                     {"phase": "memory", "attempt": 0, "outcome": "applied", "operations": 3, "durationMs": 1}],
        "operations": 3, "retries": 0,
    }))
    return receipt_path, plan_path, post_path


def test_preference_acceptance_uses_bound_automatic_plan(tmp_path: Path) -> None:
    artifacts(tmp_path)
    assert probe.verify_preference_artifacts(tmp_path, ["personal.md"], ["release.md"])["mode"] == "automatic"


@pytest.mark.parametrize("corruption", ["receipt-kind", "receipt-version", "receipt-mode", "hidden-phase", "invalid-attempt",
                                        "preference-kind", "preference-privacy", "preference-name", "stale-snapshot", "stale-post-receipt"])
def test_preference_acceptance_rejects_unbound_or_misclassified_evidence(tmp_path: Path, corruption: str) -> None:
    receipt_path, plan_path, post_path = artifacts(tmp_path)
    receipt = json.loads(receipt_path.read_text())
    plan = json.loads(plan_path.read_text())
    if corruption.startswith("receipt-"):
        key = corruption.removeprefix("receipt-")
        receipt[key] = {"kind": "unrelated-receipt", "version": 2, "mode": "manual"}[key]
    elif corruption == "hidden-phase":
        receipt["attempts"].append({"phase": "harness", "attempt": 0, "outcome": "noop", "operations": 0, "durationMs": 1})
    elif corruption == "invalid-attempt":
        receipt["attempts"][1]["attempt"] = -1
    elif corruption.startswith("preference-"):
        key = {"preference-kind": "kind", "preference-privacy": "classification", "preference-name": "name"}[corruption]
        plan["newMemories"][0][key] = {"kind": "project", "classification": "safe", "name": "unrelated.md"}[key]
        plan_path.write_text(json.dumps(plan))
        post = json.loads(post_path.read_text())
        post["planDigest"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        post_path.write_text(json.dumps(post))
    elif corruption == "stale-snapshot":
        (plan_path.parent / "snapshot.json").write_text("changed after planning")
    elif corruption == "stale-post-receipt":
        post = json.loads(post_path.read_text())
        post["runId"] = "run_other"
        post_path.write_text(json.dumps(post))
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(AssertionError):
        probe.verify_preference_artifacts(tmp_path, ["personal.md"], ["release.md"])
