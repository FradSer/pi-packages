from __future__ import annotations


# ── test_worker_attempt_lifecycle.py ──

import json
from pathlib import Path

from test_agent_package import PACKAGE, SRC, run_node

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
        const tasks = JSON.parse(fs.readFileSync(fixture.binding.tasksFile, "utf8"));
        tasks.tasks["work-2"].status = "recovery_hold";
        fs.writeFileSync(fixture.binding.tasksFile, JSON.stringify(tasks));
        const listed = await fixture.call("task", { action: "list" });
        let explicit;
        try { await fixture.call("task", { action: "claim", id: "work-2" }); }
        catch (error) { explicit = error.message; }
        const automatic = await fixture.call("task", { action: "claim" }).then(
          (result) => result.details, (error) => error.message);
        console.log(JSON.stringify({ listed: listed.content[0].text, explicit, automatic,
          intents: fixture.intents(fixture.binding.claimsDir) }));
    ''', "none")
    assert "blocked" in str(payload["listed"]), "Legacy recovery holds are projected as blocked"
    assert "explicit leader Work assignment" in str(payload["explicit"])
    assert "held for explicit leader recovery" in str(payload["automatic"]).lower()
    assert payload["intents"] == [], "Recovery-held Work must not queue a claim intent"


def test_leader_assignment_clears_recovery_and_claim_follows(tmp_path: Path) -> None:
    payload = run_node(f'''\
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import {{ initTeamMachine, shutdownTeamMachine, processTaskIntents, attemptSubmission }} from "{(SRC / 'team-machine.ts').as_uri()}";
        import {{ resetState, registerAgent, createTask, takeTask, getTask, bindTask }} from "{(SRC / 'state.ts').as_uri()}";
        const reports = [];
        resetState();
        initTeamMachine({{ cwd: {str(tmp_path)!r} }}, {{ sendUpdate: r => reports.push(r), notifyChange() {{}} }});
        registerAgent({{ name: "w", role: "reviewer", spawnId: "s1", pid: 0, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 }});
        const task = createTask({{ subject: "recoverable work" }}).task;
        takeTask(task.id, "w");
        attemptSubmission("w", "s1", task.id, "failed", "External parser rejected every authorized attempt");
        processTaskIntents();
        const held = {{ status: getTask(task.id).status, evidence: getTask(task.id).result }};
        const recovered = bindTask(task.id, "w", {{ id: "attempt-2", kind: "direct", resources: [] }}, {{ from: ["blocked"] }});
        const after = getTask(task.id).status;
        processTaskIntents();
        console.log(JSON.stringify({{ held, recovered: recovered.ok, after,
          status: getTask(task.id).status }}));
        shutdownTeamMachine();
    ''')
    assert payload["held"] == {
        "status": "blocked",
        "evidence": "External parser rejected every authorized attempt",
    }
    assert payload["recovered"] is True
    assert payload["after"] == "in_progress", "Leader assignment must clear the recovery hold"
    assert payload["status"] == "in_progress", "Settling intents must not reopen the hold"


def test_unassigned_discussion_and_tasks_notice_stay_usable(tmp_path: Path) -> None:
    payload = attempt_case(tmp_path, '''
        await fixture.prompt("Unassigned discussion about scope");
        const discussion = await fixture.call("message", { to: "leader", body: "Context question before claiming" });
        const hidden = fixture.active();
        await fixture.prompt("Wake up. New activity for you:\\n\\n=== TASK NOTICE ===\\nUnclaimed tasks: work-2\\nUse work action=claim to take one.");
        const disclosed = fixture.active();
        const notice = await fixture.call("task", { action: "claim", id: "work-2" });
        console.log(JSON.stringify({ discussion: discussion.details.outcome, hidden, disclosed,
          notice: notice.details.outcome, intents: fixture.intents(fixture.binding.claimsDir) }));
    ''', "none")
    assert payload["discussion"] == "queued"
    assert payload["hidden"] == ["read", "message"], "Unassigned work must stay undisclosed"
    assert "task" in payload["disclosed"], "A task set notice must disclose the task tool"
    assert payload["notice"] == "queued"
    assert [intent["taskId"] for intent in payload["intents"]] == ["work-2"]


def test_released_attempt_does_not_dead_end_following_unassigned_turns(tmp_path: Path) -> None:
    payload = attempt_case(tmp_path, '''
        await fixture.start();
        // The harness retires the attempt without a replacement marker: the next
        // wake is an ordinary unassigned turn and must still be able to talk.
        fixture.patch({ assignment: undefined, currentTaskId: undefined });
        await fixture.prompt("Wake up. New activity for you:\\n\\n=== INBOX (1 new) ===\\nFrom leader · Context question");
        const message = await fixture.call("message", { to: "leader", body: "Answer after release" });
        console.log(JSON.stringify({ outcome: message.details.outcome, intents: fixture.intents(fixture.binding.submissionsDir) }));
    ''')
    assert payload["outcome"] == "queued", "A retired attempt must not block a fresh unassigned turn"
    assert payload["intents"] == []


def test_claim_is_rejected_after_a_terminal_outcome(tmp_path: Path) -> None:
    payload = attempt_case(tmp_path, '''
        await fixture.start();
        await fixture.call("task", { action: "submit", outcome: "failed", result: "Cancellation acknowledged" });
        fixture.patch({ assignment: { id: "attempt-1", kind: "direct", resources: [], closed: true } });
        const claim = await fixture.call("task", { action: "claim", id: "work-2" })
          .then((result) => result.details, (error) => error.message);
        console.log(JSON.stringify({ claim, intents: fixture.intents(fixture.binding.claimsDir) }));
    ''')
    assert payload["claim"] != "queued", "A closed attempt must not queue new task work"
    assert "terminal report or is closed" in str(payload["claim"])
    assert payload["intents"] == []


def test_explicit_outcome_closes_worker_side_effects_once(tmp_path: Path) -> None:
    payload = attempt_case(tmp_path, '''
        await fixture.start();
        await fixture.call("task", { action: "submit", outcome: "failed", result: "Cancellation acknowledged" });
        const after = { active: fixture.active() };
        for (const [name, params] of [
          ["agent_event", { to: "leader", body: "Repeating the acknowledgement" }],
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

# ── test_pi12_rendered_composition.py ──
"""Use the installed Pi 1.2 renderer, not a string-concatenation surrogate."""
import json
from pathlib import Path

import pytest

from test_agent_package import REPO, SRC, run_node


@pytest.mark.parametrize("custom", [False, True])
@pytest.mark.parametrize("worker", [False, True])
def test_pi12_renders_owned_guidance_with_default_and_custom_prompt(tmp_path, custom, worker):
    # The root development cohort is the renderer of record: the pinned 1.2
    # package this checkout resolves, not a machine's global Pi install.
    sdk = REPO / "node_modules" / "@earendil-works" / "pi-coding-agent"
    manifest = json.loads((sdk / "package.json").read_text())
    assert manifest["version"].startswith(("1.2.", "1.3.")), manifest["version"]
    script = '''
      const events = new Map();
      register({ on(name, handler) { events.set(name, handler); }, registerTool() {},
        registerCommand() {}, registerMessageRenderer() {}, registerEntryRenderer() {},
        getActiveTools() { return []; }, setActiveTools() {} });
      const options = normalizeBuildSystemPromptOptions({ cwd: process.cwd(), sections: { peer: "Peer section" },
        promptGuidelines: ["Peer guideline"], CUSTOM });
      const returned = await events.get("before_agent_start")({ messageType: "custom", systemPromptOptions: options }, { cwd: process.cwd() });
      const rendered = buildSystemPromptSections(options);
      console.log(JSON.stringify({ returned: returned ?? null, rendered, options }));
    '''.replace("CUSTOM", 'customPrompt: "Authored preamble"' if custom else '')
    imports = f'''
      import register from "{(SRC / 'index.ts').as_uri()}";
      import {{ buildSystemPromptSections, normalizeBuildSystemPromptOptions }} from "{(sdk / 'dist/core/system-prompt.js').as_uri()}";
    '''
    result = attempt_case(tmp_path, imports + script, "none") if worker else run_node(imports + script)
    assert result["returned"] is None
    key = "agent_teams_worker" if worker else "agent_teams_leader"
    assert key in result["rendered"]
    assert "assigned checks" in result["rendered"][key] if worker else "one integration owner" in result["rendered"][key]
    assert result["rendered"]["peer"] == "<peer>\nPeer section\n</peer>"
    assert result["options"]["promptGuidelines"] == ["Peer guideline"]
    if custom:
        assert result["rendered"]["preamble"] == "Authored preamble"
    else:
        assert result["rendered"]["preamble"].startswith("You are an expert coding assistant")

# ── test_run_start_composition.py ──


def test_absent_prompt_does_not_disclose_tasks_or_throw(tmp_path):
    result = attempt_case(tmp_path, '''
      const { default: register } = await import("./src/index.ts");
      const events = new Map();
      let active = ["read", "message", "task"];
      register({ on(name, handler) { events.set(name, handler); }, registerTool() {},
        getActiveTools() { return active; }, setActiveTools(names) { active = names; } });
      const options = { sections: { peer: "Peer section" }, promptGuidelines: ["Peer guideline"] };
      const returned = await events.get("before_agent_start")({ messageType: "custom", systemPromptOptions: options });
      assert.equal(returned, undefined);
      assert.equal(options.sections.peer, "Peer section");
      assert.equal(options.promptGuidelines[0], "Peer guideline");
      assert.deepEqual(options.promptGuidelines, ["Peer guideline"]);
      assert.ok(options.sections.agent_teams_worker.includes("assigned checks"));
      console.log(JSON.stringify({ active }));
    ''', "none")
    assert "task" not in result["active"]
