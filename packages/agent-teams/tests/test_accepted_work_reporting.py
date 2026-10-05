from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_agent_package import SRC, run_node


def machine_case(tmp_path: Path, script: str, owned: bool = True) -> dict[str, object]:
    return run_node(f'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import {{ initTeamMachine, shutdownTeamMachine, applyProgress,
          attemptSubmission, processTaskIntents, drainTeammateOutboxes,
          hasUnfinalizedReport, setVerifyGateRunner }} from "{(SRC / 'team-machine.ts').as_uri()}";
        import {{ resetState, registerAgent, createTask, takeTask,
          getAgent, getTask, getState, revertUndeliveredTake, bindTask }} from "{(SRC / 'state.ts').as_uri()}";
        import {{ stateFilePath, inboxPath, workerOutboxPath, appendWorkerEvent,
          readJsonlBatch }} from "{(SRC / 'statefile.ts').as_uri()}";
        import {{ publishTeamHost, registerComposedTools }} from "./tests/composed-tools.ts";
        const root = {json.dumps(str(tmp_path))};
        const reports = [];
        resetState();
        initTeamMachine({{ cwd: root }}, {{ sendUpdate: r => reports.push(r), notifyChange() {{}} }});
        try {{
          registerAgent({{ name: "reviewer", role: "reviewer", workId: "work:review",
            spawnId: "spawn-1", pid: 0, status: "working", isolation: "none",
            sequenceEnded: false, createdAt: 1, updatedAt: 1 }});
          let task, attempt;
          if ({str(owned).lower()}) {{
            const created = createTask({{ id: "work:review", subject: "Review guidance" }});
            assert.equal(created.ok, true);
            task = created.task;
            takeTask(task.id, "reviewer");
            attempt = getAgent("reviewer").assignment.id;
          }}
          const stateFile = stateFilePath(undefined, root);
          appendWorkerEvent(workerOutboxPath(stateFile, "reviewer", "spawn-1"), {{
            id: "info", type: "message", worker: "reviewer", spawnId: "spawn-1",
            assignmentId: attempt, status: "inform", body: "New evidence", timestamp: 2,
          }});
          drainTeammateOutboxes();
          const settle = () => applyProgress("reviewer", "spawn-1", {{ text: "Final evidence", turns: 1, finalResponse: true }});
          const reminders = () => readJsonlBatch(inboxPath(stateFile, "reviewer"), 0).records;
          const tools = new Map();
          registerComposedTools({{ registerTool: t => tools.set(t.name, t), getActiveTools: () => [], setActiveTools() {{}} }});
          const call = (name, params) => tools.get(name).execute("test", params, undefined, undefined, {{ cwd: root }});
          {script}
        }} finally {{ setVerifyGateRunner(undefined); shutdownTeamMachine(); resetState(); }}
    ''', env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path / "agent")})


@pytest.mark.parametrize("ordering", ["submit-first", "settle-first"])
def test_explicit_submission_delivers_one_result_without_nudges(tmp_path: Path, ordering: str) -> None:
    payload = machine_case(tmp_path, f'''
        assert.equal(attemptSubmission("reviewer", "spawn-1", task.id, "completed", "Audit evidence"), true);
        if ({json.dumps(ordering)} === "submit-first") processTaskIntents();
        settle();
        processTaskIntents();
        settle();
        processTaskIntents();
        console.log(JSON.stringify({{ state: getTask(task.id).status, result: getTask(task.id).result,
          reports: reports.filter(r => r.finished), reminders: reminders(), unfinalized: hasUnfinalizedReport("reviewer"), attempt }}));
    ''')
    assert payload["state"] == "completed"
    assert payload["result"] == "Audit evidence"
    assert payload["reminders"] == []
    assert payload["unfinalized"] is False
    assert len(payload["reports"]) == 1
    report = payload["reports"][0]
    assert report["body"] == "Audit evidence"
    assert report["workId"] == "work:review"
    assert report["assignmentId"] == payload["attempt"]
    assert report["spawnId"] == "spawn-1"
    assert report["status"] == "completed"


def test_unassigned_informational_event_needs_no_finalization(tmp_path: Path) -> None:
    payload = machine_case(tmp_path, '''
        settle();
        console.log(JSON.stringify({ reminders: reminders(), unfinalized: hasUnfinalizedReport("reviewer"),
          attention: reports.filter(r => r.harnessEvent?.type === "unfinalized-report") }));
    ''', owned=False)
    assert payload == {"reminders": [], "unfinalized": False, "attention": []}


def test_post_completion_event_does_not_create_work(tmp_path: Path) -> None:
    payload = machine_case(tmp_path, '''
        attemptSubmission("reviewer", "spawn-1", task.id, "completed", "Audit evidence");
        processTaskIntents(); settle();
        const before = JSON.stringify(getState().tasks);
        const receipt = await call("message", { to: "session:reviewer:spawn-1", body: "Acceptance recorded", kind: "inform" });
        assert.equal(JSON.stringify(getState().tasks), before);
        console.log(JSON.stringify({ receipt: receipt.content[0].text, outcome: receipt.details.outcome,
          assignment: getAgent("reviewer").assignment ?? null }));
    ''')
    assert payload["assignment"] is None
    assert payload["outcome"] == "not-sent"
    assert "Audit evidence" in payload["receipt"]


@pytest.mark.parametrize("owned", [False, True])
def test_communication_cannot_assign_or_retry_work(tmp_path: Path, owned: bool) -> None:
    """A Message is a conversation, not a control channel.

    The property survives the cutover and is worth keeping: the recipient holds a
    live task, and a message addressed to it must not touch that task's status,
    its holder, or the recipient's assignment. The two cases are a holder that
    owns an assignment and one that does not, because a message that could
    *acquire* work would show up in the second case first.
    """
    payload = machine_case(tmp_path, '''
        const before = JSON.stringify(getState().tasks);
        const message = await call("message", { to: "session:reviewer:spawn-1", body: "New evidence" });
        console.log(JSON.stringify({
          unchanged: JSON.stringify(getState().tasks) === before,
          // The mail is still delivered; refusing to act on it is not refusing it.
          delivered: message.details.outcome !== "not-sent",
          assignment: getAgent("reviewer").assignment ?? null,
        }));
    ''', owned=owned)
    assert payload["unchanged"] is True
    assert payload["delivered"] is True
    if owned:
        assert payload["assignment"] is not None
    else:
        assert payload["assignment"] is None


@pytest.mark.parametrize("channel", ["explicit", "automatic"])
def test_failure_settles_before_release_and_reports_once(tmp_path: Path, channel: str) -> None:
    payload = machine_case(tmp_path, f'''
        if ({json.dumps(channel)} === "explicit") {{
          attemptSubmission("reviewer", "spawn-1", task.id, "failed", "Provider unavailable");
          processTaskIntents();
        }} else {{
          appendWorkerEvent(workerOutboxPath(stateFile, "reviewer", "spawn-1"), {{
            id: "failed", type: "message", worker: "reviewer", spawnId: "spawn-1",
            assignmentId: attempt, status: "failed", body: "Provider unavailable", timestamp: 3,
          }});
          drainTeammateOutboxes();
        }}
        const before = getTask(task.id).status;
        settle(); processTaskIntents(); settle();
        console.log(JSON.stringify({{ before, after: getTask(task.id).status, evidence: getTask(task.id).result,
          held: getTask(task.id).status === "recovery_hold",
          reports: reports.filter(r => r.finished), reminders: reminders(), attempt }}));
    ''')
    assert payload["before"] == "in_progress"
    assert payload["after"] == "recovery_hold"
    # The failure is retained as evidence in `result`, the field the task store reads and
    # shows. It used to be written to `errorMessage`, which nothing ever read.
    assert payload["evidence"] == "Provider unavailable"
    assert payload["held"] is True
    assert payload["reminders"] == []
    assert len(payload["reports"]) == 1
    assert payload["reports"][0]["status"] == "failed"
    assert payload["reports"][0]["assignmentId"] == payload["attempt"]


@pytest.mark.parametrize("kind", ["direct", "task"])
@pytest.mark.parametrize("channel", ["automatic", "explicit"])
def test_superseded_results_use_one_submission_path(tmp_path: Path, kind: str, channel: str) -> None:
    payload = machine_case(tmp_path, f'''
        getAgent("reviewer").assignment.kind = {json.dumps(kind)};
        const replacement = createTask({{ subject: "Replacement review", supersedes: [task.id] }}).task;
        const submit = (status) => {{
          if ({json.dumps(channel)} === "explicit") {{
            attemptSubmission("reviewer", "spawn-1", task.id, status, "Obsolete evidence");
            processTaskIntents();
          }} else {{
            appendWorkerEvent(workerOutboxPath(stateFile, "reviewer", "spawn-1"), {{
              id: status, type: "message", worker: "reviewer", spawnId: "spawn-1",
              assignmentId: attempt, status, body: "Obsolete evidence", timestamp: 3,
            }});
            drainTeammateOutboxes();
          }}
        }};
        submit("completed");
        const rejected = {{ owner: getTask(task.id).claimedBy, reports: reports.filter(r => r.finished),
          feedback: reminders().map(r => r.body) }};
        submit("failed");
        const beforeSettlement = getTask(task.id).claimedBy;
        settle(); processTaskIntents();
        console.log(JSON.stringify({{ rejected, beforeSettlement, owner: getTask(task.id).claimedBy ?? null,
          state: getTask(task.id).status, replacement: getTask(replacement.id).status,
          assignment: getAgent("reviewer").assignment ?? null }}));
    ''')
    assert payload["rejected"]["owner"] == "reviewer"
    assert payload["rejected"]["reports"] == []
    assert any("superseded" in body for body in payload["rejected"]["feedback"])
    assert payload["beforeSettlement"] == "reviewer"
    assert payload["owner"] is None
    assert payload["assignment"] is None
    assert payload["state"] == "superseded"
    assert payload["replacement"] == "pending"


def test_historical_terminal_record_does_not_announce_acceptance(tmp_path: Path) -> None:
    payload = machine_case(tmp_path, '''
        appendWorkerEvent(workerOutboxPath(stateFile, "reviewer", "spawn-1"), {
          id: "historical", type: "message", worker: "reviewer", spawnId: "spawn-1",
          status: "completed", body: "Unowned historical result", timestamp: 3,
        });
        drainTeammateOutboxes();
        console.log(JSON.stringify({ reports: reports.filter(r => r.finished),
          historical: getState().leaderMailbox.find(r => r.id === "historical")?.archived,
          assignment: getAgent("reviewer").assignment ?? null }));
    ''', owned=False)
    assert payload == {"reports": [], "historical": True, "assignment": None}


def test_stale_submission_cannot_finish_reassigned_work(tmp_path: Path) -> None:
    payload = machine_case(tmp_path, '''
        attemptSubmission("reviewer", "spawn-1", task.id, "completed", "Old attempt evidence");
        revertUndeliveredTake(task.id, "reviewer", "New attempt requested");
        takeTask(task.id, "reviewer");
        const newAttempt = getAgent("reviewer").assignment.id;
        processTaskIntents(); settle();
        console.log(JSON.stringify({ state: getTask(task.id).status, attempt: getAgent("reviewer").assignment?.id,
          newAttempt, reports: reports.filter(r => r.finished) }));
    ''')
    assert payload["state"] == "in_progress"
    assert payload["attempt"] == payload["newAttempt"]
    assert payload["reports"] == []


def test_duplicate_failure_does_not_block_later_attempt(tmp_path: Path) -> None:
    payload = machine_case(tmp_path, '''
        attemptSubmission("reviewer", "spawn-1", task.id, "failed", "Failed once");
        processTaskIntents();
        attemptSubmission("reviewer", "spawn-1", task.id, "failed", "Duplicate failure");
        settle();
        bindTask(task.id, "reviewer", { id: "attempt-2", kind: "direct", resources: [] }, { from: ["recovery_hold"] });
        applyProgress("reviewer", "spawn-1", { text: "", turns: 2, finalResponse: false });
        attemptSubmission("reviewer", "spawn-1", task.id, "completed", "Recovered result");
        processTaskIntents(); settle();
        console.log(JSON.stringify({ state: getTask(task.id).status, result: getTask(task.id).result,
          reports: reports.filter(r => r.finished).map(r => [r.status, r.body]), reminders: reminders() }));
    ''')
    assert payload["state"] == "completed"
    assert payload["result"] == "Recovered result"
    assert payload["reports"] == [["failed", "Failed once"], ["completed", "Recovered result"]]
    assert payload["reminders"] == []


@pytest.mark.parametrize("verdict", ["fail", "inconclusive"])
def test_ordinary_mail_does_not_unpark_verification(tmp_path: Path, verdict: str) -> None:
    payload = machine_case(tmp_path, f'''
        getTask(task.id).verify = "Review result";
        let reviews = 0;
        setVerifyGateRunner(async () => {{ reviews++; return {{ kind: {json.dumps(verdict)}, detail: "Decision required" }}; }});
        const tick = () => new Promise(resolve => setImmediate(resolve));
        attemptSubmission("reviewer", "spawn-1", task.id, "completed", "First result");
        processTaskIntents(); settle(); await tick();
        if ({json.dumps(verdict)} === "fail") {{
          attemptSubmission("reviewer", "spawn-1", task.id, "completed", "Second result");
          processTaskIntents(); await tick();
        }}
        assert.equal(reviews, 2);
        // Ordinary mail cannot unblock work. It used to be delivered and merely
        // not authorize a resubmission; now the worker holds no assignment, so the
        // message is refused and there is nothing it could have done.
        const steer = await call("message", {{ to: "session:reviewer:spawn-1", body: "New information, not recovery authorization" }});
        attemptSubmission("reviewer", "spawn-1", task.id, "completed", "Unauthorized revision");
        processTaskIntents(); await tick();
        console.log(JSON.stringify({{
          reviews,
          steerRefused: steer.details.ok === false,
          state: getTask(task.id).status,
          owner: getTask(task.id).claimedBy ?? null,
          held: getTask(task.id).status === "recovery_hold",
          feedback: reminders().map(r => r.body),
        }}));
    ''')
    feedback = payload.pop("feedback")
    assert payload == {
        "reviews": 2,
        "steerRefused": True,
        "state": "recovery_hold",
        "owner": None,
        "held": True,
    }
    # The gate told the worker what it would take to retry, and an ordinary message
    # is not it.
    assert any("stated reason" in body for body in feedback)
    assert not any("explicit leader steer" in body for body in feedback)


def test_archived_result_is_not_returned_as_accepted_evidence(tmp_path: Path) -> None:
    payload = machine_case(tmp_path, '''
        revertUndeliveredTake(task.id, "reviewer", "Released before completion");
        appendWorkerEvent(workerOutboxPath(stateFile, "reviewer", "spawn-1"), {
          id: "late", type: "message", worker: "reviewer", spawnId: "spawn-1",
          assignmentId: attempt, status: "completed", body: "Unaccepted evidence", timestamp: 3,
        });
        drainTeammateOutboxes();
        // A released assignment cannot receive work, and the refusal has to say
        // so. Reported rather than thrown: every refusal from every tool is one
        // shape, so a caller reads one thing whatever went wrong.
        const refused = await call("message", { to: "session:reviewer:spawn-1", body: "New evidence" });
        if (refused.details.ok !== false) throw new Error("a released assignment must refuse new evidence");
        if (!/no open assignment/.test(refused.content[0].text)) throw new Error(`the refusal must name the reason: ${refused.content[0].text}`);
        console.log(JSON.stringify({ state: getTask(task.id).status, reports: reports.filter(r => r.finished) }));
    ''')
    assert payload == {"state": "pending", "reports": []}


def test_gate_delays_automatic_completion_report(tmp_path: Path) -> None:
    payload = machine_case(tmp_path, '''
        getAgent("reviewer").assignment.kind = "direct";
        getTask(task.id).verify = "Review result";
        let pass;
        setVerifyGateRunner(() => new Promise(resolve => { pass = () => resolve({ kind: "pass" }); }));
        appendWorkerEvent(workerOutboxPath(stateFile, "reviewer", "spawn-1"), {
          id: "automatic", type: "message", worker: "reviewer", spawnId: "spawn-1",
          assignmentId: attempt, status: "completed", body: "Gated evidence", timestamp: 3,
        });
        drainTeammateOutboxes(); settle();
        await new Promise(resolve => setImmediate(resolve));
        const before = reports.filter(r => r.finished);
        pass(); await new Promise(resolve => setImmediate(resolve));
        console.log(JSON.stringify({ before, after: reports.filter(r => r.finished), reminders: reminders() }));
    ''')
    assert payload["before"] == []
    assert len(payload["after"]) == 1
    assert payload["after"][0]["body"] == "Gated evidence"
    assert payload["reminders"] == []


def test_agent_tool_guidance_explains_push_delivery(tmp_path: Path) -> None:
    """The waiting discipline belongs to the tool that starts a child.

    A delegation's result arrives without being asked for. The arithmetic
    transcript showed that automatic-delivery wording alone did not prevent
    caller-side polling, sleeps and duplicate starts. The updated requirement
    in subagents/features/agent-usage.feature makes the dependent-turn action
    and excluded waiting shortcuts explicit.
    """
    payload = machine_case(tmp_path, '''
        // The push-delivery contract now lives where the family is described: the
        // intent namespace instructions plus every intent tool description.
        const family = [...tools.values()].filter((tool) => tool.name.startsWith("agent_"));
        console.log(JSON.stringify({
          guidelines: family.flatMap((tool) => tool.promptGuidelines ?? []),
          description: [...family.map((tool) => tool.description ?? ""), ...family.map((tool) => tool.namespace?.instructions ?? "")].join(" "),
        }));
    ''', owned=False)
    guidance = " ".join(payload["guidelines"]) + " " + payload["description"]
    guidance = " ".join(guidance.split()).lower()
    assert "automatically" in guidance
    assert "end the turn" in guidance or "ending the turn" in guidance
    assert "inspect" in guidance
    assert "asynchronously" in guidance
    assert "without polling" in guidance
    assert "sleep" in guidance
    assert "duplicate starts" in guidance
    assert "explicit user request" in guidance


def test_work_list_exposes_accepted_evidence_in_model_content(tmp_path: Path) -> None:
    """The list text is one line per task, and a list carries no evidence.

    A list is bounded, so the body and the evidence stay behind `get_task`.
    Dropping evidence out of `get_task` would be a real loss, so that is
    asserted directly rather than through a rendered row.
    """
    payload = machine_case(tmp_path, '''
        attemptSubmission("reviewer", "spawn-1", task.id, "completed", "Audit evidence");
        processTaskIntents(); settle();
        const listed = await call("list_tasks", {});
        const read = await call("get_task", { id: task.id });
        console.log(JSON.stringify({ content: listed.content[0].text, tasks: listed.details.tasks, result: read.details.task.result }));
    ''')
    assert "work:review" in payload["content"]
    assert "Audit evidence" not in payload["content"], "the row is one line, not an evidence dump"
    assert "result" not in payload["tasks"][0], "a bounded list omits the evidence"
    assert payload["result"] == "Audit evidence"


def test_work_list_bounds_long_evidence_without_losing_details(tmp_path: Path) -> None:
    payload = machine_case(tmp_path, '''
        const evidence = "Result evidence\\n".repeat(600);
        attemptSubmission("reviewer", "spawn-1", task.id, "completed", evidence);
        processTaskIntents(); settle();
        const listed = await call("list_tasks", {});
        const read = await call("get_task", { id: task.id });
        // Reading one task is what pays for its evidence, and it pays in full
        // whatever its length, which is what makes the bounded list safe.
        assert.equal(read.details.task.result, evidence);
        console.log(JSON.stringify({ content: listed.content[0].text, count: listed.details.count }));
    ''')
    assert payload["content"].count("\\n") == payload["count"] - 1
    assert len(payload["content"]) < 4500
