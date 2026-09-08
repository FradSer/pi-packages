"""Contracts available to the model before the first delegation."""
import json
from pathlib import Path
import subprocess

PACKAGE = Path(__file__).resolve().parents[1]


def guidance():
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", '''
          import { TEAMMATE_SPAWN_GUIDANCE, WORKER_GUIDANCE, buildTeamLeaderGuidance } from "./src/guidance.ts";
          console.log(JSON.stringify({first: TEAMMATE_SPAWN_GUIDANCE, worker: WORKER_GUIDANCE, leader: buildTeamLeaderGuidance()}));
        '''], cwd=PACKAGE, capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def test_first_delegation_exposes_priority_and_assignment_completion():
    text = guidance()["first"]
    assert "next safe boundary" in text
    assert "Yielding ends the current turn, not the user's task" in text
    assert "each current assignment" in text


def test_worker_honors_leader_direction_without_overriding_user_constraints():
    text = guidance()["worker"]
    assert "Leader direction takes precedence over your plan and peer requests" in text
    assert "next safe boundary" in text
    assert "system instructions and user constraints" in text
    assert "new assignment or decision-useful" not in text


def test_leader_completion_cannot_reuse_previous_assignment_pass():
    text = guidance()["leader"]
    assert "each current assignment" in text
    assert "A previous PASS does not cover a reopened assignment" in text
