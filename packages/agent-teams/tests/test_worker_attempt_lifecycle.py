from __future__ import annotations

import json
from pathlib import Path

from test_teammate_package import PACKAGE, SRC, run_node

FIXTURE = (PACKAGE / "tests" / "worker-attempt-lifecycle-fixture.ts").as_uri()


def attempt_case(tmp_path: Path, script: str, kind: str = "direct") -> dict[str, object]:
    return run_node(f'''\
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import {{ createAttemptFixture }} from "{FIXTURE}";
        const fixture = createAttemptFixture({str(tmp_path)!r}, {kind!r});
        {script}
    ''')


def test_recovery_required_work_is_never_autonomously_claimable(tmp_path: Path) -> None:
    payload = attempt_case(tmp_path, '''
        const board = JSON.parse(fs.readFileSync(fixture.binding.boardFile, "utf8"));
        board.tasks["work-2"].recoveryRequired = true;
        board.tasks["work-2"].status = "pending";
        fs.writeFileSync(fixture.binding.boardFile, JSON.stringify(board));
        const listed = await fixture.call("work", { action: "list" });
        let explicit;
        try { await fixture.call("work", { action: "claim", id: "work-2" }); }
        catch (error) { explicit = error.message; }
        const automatic = await fixture.call("work", { action: "claim" }).then(
          (result) => result.details, (error) => error.message);
        console.log(JSON.stringify({ listed: listed.content[0].text, explicit, automatic,
          intents: fixture.intents(fixture.binding.claimsDir) }));
    ''', "none")
    assert "pending/recovery-required" in str(payload["listed"]), "Board must name the recovery hold"
    assert "explicit leader Work assignment" in str(payload["explicit"])
    assert "held for explicit leader recovery" in str(payload["automatic"]).lower()
    assert payload["intents"] == [], "Recovery-held Work must not queue a claim intent"


def test_leader_assignment_clears_recovery_and_claim_follows(tmp_path: Path) -> None:
    payload = run_node(f'''\
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import {{ initTeamMachine, shutdownTeamMachine, processTaskIntents, attemptSubmission }} from "{(SRC / 'team-machine.ts').as_uri()}";
        import {{ resetState, registerTeammate, createTask, setTaskClaimed, getTask, reclaimDirectWork }} from "{(SRC / 'state.ts').as_uri()}";
        const reports = [];
        resetState();
        initTeamMachine({{ cwd: {str(tmp_path)!r} }}, {{ sendUpdate: r => reports.push(r), notifyChange() {{}} }});
        registerTeammate({{ name: "w", agent: "reviewer", spawnId: "s1", pid: 0, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const task = createTask({{ subject: "recoverable work" }}).task;
        setTaskClaimed(task.id, "w");
        attemptSubmission("w", "s1", task.id, "failed", "External parser rejected every authorized attempt");
        processTaskIntents();
        const held = {{ status: getTask(task.id).status, recoveryRequired: getTask(task.id).recoveryRequired,
          error: getTask(task.id).errorMessage }};
        const recovered = reclaimDirectWork(task.id, "w", {{ id: "attempt-2", kind: "direct", resources: [] }}, "pending");
        console.log(JSON.stringify({{ held, recovered: recovered.ok, after: getTask(task.id).recoveryRequired ?? null,
          status: getTask(task.id).status }}));
        shutdownTeamMachine();
    ''')
    assert payload["held"] == {
        "status": "pending",
        "recoveryRequired": True,
        "error": "External parser rejected every authorized attempt",
    }
    assert payload["recovered"] is True
    assert payload["after"] is None
    assert payload["status"] == "claimed"


def test_unassigned_discussion_and_board_notice_stay_usable(tmp_path: Path) -> None:
    payload = attempt_case(tmp_path, '''
        await fixture.prompt("Unassigned discussion about scope");
        const discussion = await fixture.call("agent_event", { to: "leader", message: "Context question before claiming" });
        const hidden = fixture.active();
        await fixture.prompt("Wake up. New activity for you:\\n\\n=== BOARD NOTICE ===\\nUnclaimed tasks: work-2\\nUse work action=claim to take one.");
        const disclosed = fixture.active();
        const notice = await fixture.call("work", { action: "claim", id: "work-2" });
        console.log(JSON.stringify({ discussion: discussion.details.outcome, hidden, disclosed,
          notice: notice.details.outcome, intents: fixture.intents(fixture.binding.claimsDir) }));
    ''', "none")
    assert payload["discussion"] == "queued"
    assert payload["hidden"] == ["read", "agent_event"], "Unassigned work must stay undisclosed"
    assert "work" in payload["disclosed"], "A board notice must disclose work"
    assert payload["notice"] == "queued"
    assert [intent["taskId"] for intent in payload["intents"]] == ["work-2"]


def test_released_attempt_does_not_dead_end_following_unassigned_turns(tmp_path: Path) -> None:
    payload = attempt_case(tmp_path, '''
        await fixture.start();
        // The harness retires the attempt without a replacement marker: the next
        // wake is an ordinary unassigned turn and must still be able to talk.
        fixture.patch({ assignment: undefined, currentTaskId: undefined });
        await fixture.prompt("Wake up. New activity for you:\\n\\n=== INBOX (1 new) ===\\nFrom leader · Context question");
        const message = await fixture.call("agent_event", { to: "leader", message: "Answer after release" });
        console.log(JSON.stringify({ outcome: message.details.outcome, intents: fixture.intents(fixture.binding.submissionsDir) }));
    ''')
    assert payload["outcome"] == "queued", "A retired attempt must not block a fresh unassigned turn"
    assert payload["intents"] == []


def test_claim_is_rejected_after_a_terminal_outcome(tmp_path: Path) -> None:
    payload = attempt_case(tmp_path, '''
        await fixture.start();
        await fixture.call("work", { action: "submit", outcome: "failed", result: "Cancellation acknowledged" });
        fixture.patch({ assignment: { id: "attempt-1", kind: "direct", resources: [], closed: true } });
        const claim = await fixture.call("work", { action: "claim", id: "work-2" })
          .then((result) => result.details, (error) => error.message);
        console.log(JSON.stringify({ claim, intents: fixture.intents(fixture.binding.claimsDir) }));
    ''')
    assert payload["claim"] != "queued", "A closed attempt must not queue new board work"
    assert "terminal report or is closed" in str(payload["claim"])
    assert payload["intents"] == []


def test_explicit_outcome_closes_worker_side_effects_once(tmp_path: Path) -> None:
    payload = attempt_case(tmp_path, '''
        await fixture.start();
        await fixture.call("work", { action: "submit", outcome: "failed", result: "Cancellation acknowledged" });
        const after = { active: fixture.active() };
        for (const [name, params] of [
          ["agent_event", { to: "leader", message: "Repeating the acknowledgement" }],
          ["work", { action: "submit", outcome: "failed", result: "Repeating the acknowledgement" }],
          ["work", { action: "claim" }],
        ]) {
          try { await fixture.call(name, params); after[name] = "accepted"; }
          catch (error) { after[name] = error.message; }
        }
        console.log(JSON.stringify({ after, peer: fixture.peerRecords(),
          intents: fixture.intents(fixture.binding.submissionsDir) }));
    ''')
    assert "work" not in payload["after"]["active"], "A closed attempt must not keep write tools"
    for name in ("agent_event", "work"):
        assert payload["after"][name] != "accepted", f"{name} must be rejected after a terminal outcome"
    assert payload["peer"] == [], "No peer mail may be written after the attempt closes"
    assert len(payload["intents"]) == 1, "Exactly one submission intent may exist"