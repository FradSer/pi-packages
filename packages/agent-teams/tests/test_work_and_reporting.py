from __future__ import annotations


# ── test_accepted_work_reporting.py ──

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
          held: getTask(task.id).status === "blocked",
          reports: reports.filter(r => r.finished), reminders: reminders(), attempt }}));
    ''')
    assert payload["before"] == "in_progress"
    assert payload["after"] == "blocked"
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
    assert payload["state"] == "in_progress"
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
        bindTask(task.id, "reviewer", { id: "attempt-2", kind: "direct", resources: [] }, { from: ["blocked"] });
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
          held: getTask(task.id).status === "blocked",
          feedback: reminders().map(r => r.body),
        }}));
    ''')
    feedback = payload.pop("feedback")
    assert payload == {
        "reviews": 2,
        "steerRefused": True,
        "state": "blocked",
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
    assert "poll" in guidance or "inspect" in guidance
    assert "asynchronously" in guidance
    assert "without polling" in guidance
    assert "sleep" in guidance
    assert "duplicate starts" in guidance
    assert "explicit user request" in guidance


def test_task_domain_retains_acceptance_evidence(tmp_path: Path) -> None:
    """No model-facing task tool remains, so evidence is checked in the domain.

    A bounded list and `get_task` were the old tool surface. The property that
    still matters is that a submission's evidence reaches the stored Work Item
    and survives settlement.
    """
    payload = machine_case(tmp_path, '''
        const evidence = "Result evidence\\n".repeat(600);
        attemptSubmission("reviewer", "spawn-1", task.id, "completed", evidence);
        processTaskIntents(); settle();
        console.log(JSON.stringify({ status: getTask(task.id).status, result: getTask(task.id).result }));
    ''')
    assert payload["status"] == "completed"
    assert payload["result"] == "Result evidence\n" * 600

# ── test_automatic_results.py ──

import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest

from test_agent_package import PACKAGE, run_node

FIXTURE = (PACKAGE / "tests" / "automatic-results-fixture.ts").as_uri()


def run_worker(tmp_path: Path, script: str, kind: str = "direct") -> dict[str, object]:
    return run_node(f'''\
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import {{ assistant, createWorkerFixture }} from "{FIXTURE}";
        const fixture = createWorkerFixture({str(tmp_path)!r}, {kind!r});
        {script}
    ''')


def test_final_answer_is_reported_once_only_after_settlement(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        await fixture.answer(assistant("Final answer with evidence"));
        await fixture.emit({ type: "agent_end", messages: [] });
        assert.deepEqual(fixture.records(), []);
        await fixture.emit({ type: "agent_settled" });
        await fixture.emit({ type: "agent_settled" });
        assert.equal(fixture.records().length, 1);
        console.log(JSON.stringify({ records: fixture.records(), roster: JSON.parse(fs.readFileSync(fixture.binding.rosterFile, "utf8")) }));
    ''')
    records = payload["records"]
    assert len(records) == 1
    assert records[0] | {"id": "ignored", "timestamp": 0} == {
        "id": "ignored", "timestamp": 0, "type": "message", "worker": "worker", "spawnId": "spawn-1",
        "assignmentId": "attempt-1", "status": "completed", "body": "Final answer with evidence",
    }
    assert "closed" not in payload["roster"]["agents"][0]["assignment"]


@pytest.mark.parametrize(("stop_reason", "error", "reason"), [
    ("error", "Provider connection failed", "Provider connection failed"),
    ("aborted", "Cancelled by leader", "Cancelled by leader"),
    ("error", None, "error"),
    ("aborted", None, "aborted"),
    ("length", None, "length"),
    ("pending", None, "incomplete"),
    ("deferred", None, "incomplete"),
    ("toolUse", None, "final answer"),
])
def test_failed_response_never_reuses_intermediate_success(tmp_path: Path, stop_reason: str, error: str | None, reason: str) -> None:
    payload = run_worker(tmp_path, f'''
        await fixture.start();
        await fixture.answer(assistant("Stale intermediate success", "stop", 20));
        await fixture.answer(assistant("Partial output is not success", {stop_reason!r}, 30, {json.dumps(error)}));
        await fixture.emit({{ type: "agent_end", messages: [] }});
        assert.deepEqual(fixture.records(), []);
        await fixture.emit({{ type: "agent_settled" }});
        console.log(JSON.stringify({{ records: fixture.records() }}));
    ''')
    assert len(payload["records"]) == 1
    report = payload["records"][0]
    assert report["status"] == "failed"
    assert reason in report["body"]
    assert "Stale intermediate success" not in report["body"]
    assert "Partial output is not success" not in report["body"]


@pytest.mark.parametrize("last_response", ["empty", "tool-call", "unfinished", "missing"])
def test_no_final_answer_is_failed_at_settlement(tmp_path: Path, last_response: str) -> None:
    script = {
        "empty": 'await fixture.answer(assistant("  ", "stop", 30));',
        "tool-call": '''const message = assistant("Tool preamble", "stop", 30);
            message.content.push({ type: "toolCall", id: "read-1", name: "read", arguments: {} });
            await fixture.answer(message);''',
        "unfinished": 'await fixture.emit({ type: "message_start", message: assistant("Partial", "pending", 30) });',
        "missing": "",
    }[last_response]
    payload = run_worker(tmp_path, f'''
        await fixture.start();
        {script}
        await fixture.emit({{ type: "agent_settled" }});
        console.log(JSON.stringify({{ records: fixture.records() }}));
    ''')
    assert len(payload["records"]) == 1
    assert payload["records"][0]["status"] == "failed"
    assert "final answer" in payload["records"][0]["body"]


def test_tools_retries_and_nonidle_settlement_do_not_close_assignment(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        await fixture.answer(assistant("Transient", "error", 20, "429 rate limit"));
        await fixture.emit({ type: "agent_end", messages: [] });
        await fixture.emit({ type: "agent_start" });
        assert.deepEqual(fixture.records(), []);
        await fixture.answer(assistant("Calling a tool", "toolUse", 30));
        await fixture.emit({ type: "message_end", message: { role: "toolResult", content: [{ type: "text", text: "Not the final answer" }],
          toolCallId: "read-1", toolName: "read", isError: false, timestamp: 35 } });
        assert.deepEqual(fixture.records(), []);
        await fixture.answer(assistant("Recovered final answer", "stop", 40));
        fixture.setIdle(false);
        await fixture.emit({ type: "agent_settled" });
        assert.deepEqual(fixture.records(), []);
        fixture.setIdle(true);
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records() }));
    ''')
    assert [(record["body"], record["status"]) for record in payload["records"]] == [("Recovered final answer", "completed")]


def test_communication_event_does_not_require_completion_bookkeeping(tmp_path: Path) -> None:
    tool = "message"
    payload = run_worker(tmp_path, f'''
        await fixture.start();
        const result = await fixture.call({tool!r}, {{ to: "leader", body: "New evidence" }});
        assert.notEqual(result.terminate, true);
        await fixture.answer(assistant("Final answer"));
        await fixture.emit({{ type: "agent_settled" }});
        console.log(JSON.stringify({{ description: fixture.tools.get({tool!r}).description,
          response: result.content[0].text, records: fixture.records() }}));
    ''')
    assert len(payload["records"]) == 2
    assert payload["records"][-1]["body"] == "Final answer"
    assert "automatically" in payload["description"]
    assert "REPORT" in payload["response"]
    assert "status=" not in payload["response"]


def test_unassigned_workers_do_not_autocomplete(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start("attempt-1");
        await fixture.answer(assistant("Unassigned answer"));
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records(), submitted: fs.existsSync(fixture.binding.submissionsDir) }));
    ''', "none")
    assert payload == {"records": [], "submitted": False}


def test_tasks_final_answer_is_submitted_once_after_settlement(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        await fixture.answer(assistant("Tasks result evidence"));
        await fixture.emit({ type: "agent_end", messages: [] });
        assert.deepEqual(fixture.records(), []);
        await fixture.emit({ type: "agent_settled" });
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records() }));
    ''', "task")
    assert len(payload["records"]) == 1
    assert payload["records"][0]["assignmentId"] == "attempt-1"
    assert payload["records"][0]["body"] == "Tasks result evidence"


@pytest.mark.parametrize("kind", ["direct", "task"])
@pytest.mark.parametrize("outcome", ["success", "failed"])
def test_explicit_submission_suppresses_automatic_duplicate(tmp_path: Path, kind: str, outcome: str) -> None:
    payload = run_worker(tmp_path, f'''
        const roster = JSON.parse(fs.readFileSync(fixture.binding.rosterFile, "utf8"));
        roster.agents[0].currentTaskId = "work-1";
        fs.writeFileSync(fixture.binding.rosterFile, JSON.stringify(roster));
        await fixture.start();
        const submitted = await fixture.call("task", {{ action: "submit", outcome: {json.dumps(outcome)}, result: "Explicit evidence" }});
        await fixture.answer(assistant("Do not duplicate the submission"));
        await fixture.emit({{ type: "agent_settled" }});
        await fixture.emit({{ type: "agent_settled" }});
        const marker = JSON.parse(fs.readFileSync(fixture.binding.submissionsDir + "/work-1.json", "utf8"));
        console.log(JSON.stringify({{ records: fixture.records(), marker, terminate: submitted.terminate }}));
    ''', kind)
    assert payload["records"] == []
    assert payload["marker"]["result"] == "Explicit evidence"
    assert payload["marker"]["assignmentId"] == "attempt-1"
    assert payload["terminate"] is True


@pytest.mark.parametrize("change", ["assignment", "spawn", "closed", "stopped", "missing", "binding"])
def test_stale_assignment_or_spawn_cannot_write_result(tmp_path: Path, change: str) -> None:
    mutate = {
        "assignment": 'fixture.roster({ id: "attempt-2", kind: "direct", resources: [] });',
        "spawn": 'fixture.roster({ id: "attempt-1", kind: "direct", resources: [] }, "spawn-2");',
        "closed": 'fixture.roster({ id: "attempt-1", kind: "direct", resources: [], closed: true });',
        "stopped": 'fixture.roster({ id: "attempt-1", kind: "direct", resources: [] }, "spawn-1", "stopped");',
        "missing": 'fs.rmSync(fixture.binding.rosterFile);',
        "binding": 'process.env.PI_TEAMMATE_SPAWN_ID = "spawn-2";',
    }[change]
    payload = run_worker(tmp_path, f'''
        await fixture.start();
        await fixture.answer(assistant("Old attempt answer"));
        {mutate}
        await fixture.emit({{ type: "agent_settled" }});
        console.log(JSON.stringify({{ records: fixture.records() }}));
    ''')
    assert payload["records"] == []


def test_reopening_discards_old_evidence_and_repeated_settlement(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        const oldMessage = assistant("Old result", "stop", 20);
        await fixture.answer(oldMessage);
        await fixture.emit({ type: "agent_settled" });
        fixture.roster({ id: "attempt-2", kind: "direct", resources: [] });
        await fixture.emit({ type: "agent_settled" });
        assert.equal(fixture.records().length, 1);
        await fixture.start("attempt-2", 30);
        await fixture.emit({ type: "message_end", message: oldMessage });
        await fixture.answer(assistant("New result", "stop", 40));
        await fixture.emit({ type: "message_end", message: oldMessage });
        await fixture.start("attempt-1", 10);
        await fixture.emit({ type: "agent_settled" });
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records() }));
    ''')
    assert [(record["assignmentId"], record["body"]) for record in payload["records"]] == [
        ("attempt-1", "Old result"), ("attempt-2", "New result"),
    ]


def test_reset_discards_unsettled_result_until_new_activity(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        await fixture.answer(assistant("Discard this result"));
        fixture.disclosure.reset();
        await fixture.emit({ type: "agent_settled" });
        assert.deepEqual(fixture.records(), []);
        await fixture.start("attempt-1", 30);
        await fixture.answer(assistant("Fresh result", "stop", 40));
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records() }));
    ''')
    assert [record["body"] for record in payload["records"]] == ["Fresh result"]


def test_outbox_write_failure_does_not_close_the_local_report_binding(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        await fixture.answer(assistant("Final result"));
        fs.mkdirSync(fixture.binding.outbox);
        await assert.rejects(fixture.emit({ type: "agent_settled" }));
        fs.rmdirSync(fixture.binding.outbox);
        await fixture.emit({ type: "agent_settled" });
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records() }));
    ''')
    assert len(payload["records"]) == 1
    assert payload["records"][0]["body"] == "Final result"


@pytest.mark.parametrize("text", ["证据与结论\n", "证据", "\x00\"\\"])
def test_large_unicode_result_keeps_full_private_artifact_and_bounded_report(tmp_path: Path, text: str) -> None:
    payload = run_worker(tmp_path, f"const full = {json.dumps(text)}.repeat(15000);" + '''
        await fixture.start();
        await fixture.answer(assistant(full));
        await fixture.emit({ type: "agent_settled" });
        await fixture.emit({ type: "agent_settled" });
        const records = fixture.records();
        assert.equal(records.length, 1);
        const artifact = /Full result: (.+)/.exec(records[0].body)?.[1];
        assert.ok(artifact, "Large report must link its full result");
        assert.equal(fs.readFileSync(artifact, "utf8"), full);
        console.log(JSON.stringify({ status: records[0].status, body: records[0].body,
          artifact, mode: fs.statSync(artifact).mode & 0o777, bytes: fs.statSync(fixture.binding.outbox).size,
          files: fs.readdirSync(new URL(".", "file://" + fixture.binding.outbox)) }));
    ''')
    assert payload["status"] == "completed"
    assert text.rstrip("\n") in payload["body"]
    assert "truncated" in payload["body"]
    assert Path(payload["artifact"]).parent == tmp_path
    assert payload["mode"] == 0o600
    assert payload["bytes"] < 64 * 1024
    assert not any(name.endswith(".tmp") for name in payload["files"])


def test_same_millisecond_old_message_cannot_supply_new_attempt_result(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        const old = assistant("Old same-millisecond answer", "stop", 20);
        await fixture.answer(old);
        await fixture.emit({ type: "agent_settled" });
        fixture.roster({ id: "attempt-2", kind: "direct", resources: [] });
        await fixture.start("attempt-2", 20);
        await fixture.emit({ type: "message_end", message: old });
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records() }));
    ''')
    assert len(payload["records"]) == 2
    assert payload["records"][1]["status"] == "failed"
    assert "Old same-millisecond answer" not in payload["records"][1]["body"]


def test_retry_start_clears_stale_success_before_any_new_response(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        await fixture.answer(assistant("Previous low-level success"));
        await fixture.emit({ type: "agent_end", messages: [] });
        await fixture.emit({ type: "agent_start" });
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records() }));
    ''')
    assert len(payload["records"]) == 1
    assert payload["records"][0]["status"] == "failed"
    assert "Previous low-level success" not in payload["records"][0]["body"]


def test_agent_event_requires_precise_route_for_concurrent_peer_sessions(tmp_path: Path) -> None:
    tool = "message"
    payload = run_worker(tmp_path, f'const messageTool = {json.dumps(tool)};' + '''
        const peers = [
          { name: "reviewer-one", role: "peer-reviewer", status: "working" },
          { name: "reviewer-two", role: "peer-reviewer", status: "idle" },
        ];
        const self = JSON.parse(fs.readFileSync(fixture.binding.rosterFile, "utf8")).agents[0];
        const write = (agents) => fs.writeFileSync(fixture.binding.rosterFile, JSON.stringify({ agents: [self, ...agents] }));
        write(peers);
        await assert.rejects(fixture.call(messageTool, { to: "peer-reviewer", body: "Ambiguous" }),
          /Ambiguous Agent.*reviewer-one.*reviewer-two/);
        assert.equal(fs.existsSync(fixture.binding.inbox.replace("inbox-worker", "inbox-reviewer-one")), false);
        const exact = await fixture.call(messageTool, { to: "session:reviewer-two", body: "Exact route" });
        write([peers[0], { ...peers[1], status: "stopped" }]);
        const unique = await fixture.call(messageTool, { to: "peer-reviewer", body: "Only living route" });
        self.role = "self-role";
        write([]);
        await assert.rejects(fixture.call(messageTool, { to: "self-role", body: "Self alias" }), /yourself/);
        const first = JSON.parse(fs.readFileSync(fixture.binding.inbox.replace("inbox-worker", "inbox-reviewer-one"), "utf8"));
        const second = JSON.parse(fs.readFileSync(fixture.binding.inbox.replace("inbox-worker", "inbox-reviewer-two"), "utf8"));
        console.log(JSON.stringify({ exact: exact.details.to, unique: unique.details.to, first: first.body, second: second.body }));
    ''')
    assert payload == {"exact": "reviewer-two", "unique": "reviewer-one", "first": "Only living route", "second": "Exact route"}


@pytest.mark.parametrize("outcome", [None, "success", "failed"], ids=["retry", "explicit-success", "explicit-failed"])
def test_native_pi_reports_only_after_settlement(tmp_path: Path, outcome: str | None) -> None:
    explicit = outcome is not None
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("Pi CLI is required for native settlement verification")
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "settings.json").write_text(json.dumps({"retry": {"enabled": True, "maxRetries": 1, "baseDelayMs": 1}}))
    roster = tmp_path / "roster.json"
    roster.write_text(json.dumps({"agents": [{"name": "worker", "agent": "reviewer", "spawnId": "spawn-1", "status": "working",
        "currentTaskId": "work-1", "assignment": {"id": "attempt-1", "kind": "direct", "resources": []}}]}))
    outbox = tmp_path / "events.jsonl"
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update({
        "PI_CODING_AGENT_DIR": str(agent_dir), "PI_OFFLINE": "1", "PI_AUTOMATIC_RESULTS_AUTH": secrets.token_hex(16),
        "PI_TEAMMATE_WORKER_NAME": "worker", "PI_TEAMMATE_SPAWN_ID": "spawn-1", "PI_TEAMMATE_OUTBOX_FILE": str(outbox),
        "PI_TEAMMATE_ROSTER_FILE": str(roster), "PI_TEAMMATE_INBOX_FILE": str(tmp_path / "inbox.jsonl"),
        "PI_TEAMMATE_TASKS_FILE": str(tmp_path / "tasks.json"), "PI_TEAMMATE_CLAIMS_DIR": str(tmp_path / "claims"),
        "PI_TEAMMATE_SUBMISSIONS_DIR": str(tmp_path / "submissions"),
    })
    env["PI_SUBMISSION_AUTH"] = secrets.token_hex(16)
    if outcome:
        env["PI_SUBMISSION_OUTCOME"] = outcome
    fixture = "explicit-submission-live-fixture" if explicit else "automatic-results-fixture"
    provider = "explicit-submission-fixture" if explicit else "automatic-results-fixture"
    result = subprocess.run(
        [pi, "--print", "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes",
         "--no-context-files", "--no-approve", "--extension", str(PACKAGE / "tests" / f"{fixture}.ts"),
         "--provider", provider, "--model", "deterministic", "--thinking", "off", "--no-builtin-tools",
         "[agent-teams-assignment:attempt-1]\nRun the automatic result fixture"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    sentinel = "NATIVE_EXPLICIT_SUBMISSION_OK" if explicit else "PI_AUTOMATIC_RESULTS_OK"
    assert sentinel in result.stdout + result.stderr, result.stdout + result.stderr
    assert "AssertionError" not in result.stderr
    if explicit:
        marker = json.loads((tmp_path / "submissions" / "work-1.json").read_text())
        assert marker["assignmentId"] == "attempt-1"
        assert marker["result"] == "Native submission evidence"
        assert marker["status"] == ("completed" if outcome == "success" else "failed")
        assert not outbox.exists() or outbox.read_text() == ""
    else:
        assert outbox.exists(), result.stdout + result.stderr
        records = [json.loads(line) for line in outbox.read_text().splitlines()]
        assert [(record["status"], record["body"]) for record in records] == [("completed", "PI_AUTOMATIC_RESULTS_OK")]

# ── test_completion_refusal.py ──

from pathlib import Path

import pytest



@pytest.mark.parametrize("outcome", ["completed", "failed"])
def test_refused_settled_submission_retains_authority_and_accepts_explicit_correction(tmp_path: Path, outcome: str) -> None:
    payload = machine_case(tmp_path, f'''
        getTask(task.id).context = {{ budgetBytes: 1024 }};
        const oversized = "e".repeat(2048);
        attemptSubmission("reviewer", "spawn-1", task.id, "{outcome}", oversized);
        processTaskIntents(); settle();
        const refused = {{ status: getTask(task.id).status, holder: getTask(task.id).claimedBy,
          assignment: getAgent("reviewer").assignment?.id ?? null,
          reports: reports.filter(r => r.finished), feedback: reminders().map(r => r.body) }};
        // Repeated settlement and intent processing must not retry a refused candidate.
        settle(); processTaskIntents(); settle();
        const feedbackAfterRepeatedSettlement = reminders().map(r => r.body);
        const {{ authorizeResidentInput, sendResidentSequence, routePeerInboxes }} = await import("./src/team-machine.ts");
        const input = authorizeResidentInput("reviewer", "spawn-1");
        assert.equal(input.ok, true, "refusal must permit corrective input");
        const childProcess = (await import("node:child_process")).default;
        const {{ EventEmitter }} = await import("node:events");
        const {{ PassThrough, Writable }} = await import("node:stream");
        const {{ mock }} = await import("node:test");
        const {{ syncBuiltinESMExports }} = await import("node:module");
        const commands = [];
        const child = Object.assign(new EventEmitter(), {{ pid: 0,
          stdout: new PassThrough(), stderr: new PassThrough(),
          stdin: new Writable({{ write(chunk, encoding, done) {{
            const command = JSON.parse(String(chunk));
            commands.push(command); done();
            setImmediate(() => child.stdout.write(JSON.stringify({{ type: "response", id: command.id,
              command: command.type, success: true, data: {{ disposition: "started", isStreaming: false }} }}) + "\\n"));
          }} }}) }});
        mock.method(childProcess, "spawn", () => child);
        syncBuiltinESMExports();
        const {{ spawnResident }} = await import("@fradser/pi-subagents");
        spawnResident({{ agentName: "reviewer", onUpdate() {{}}, onExit() {{}} }});
        let correction;
        try {{
          correction = await sendResidentSequence("reviewer", "spawn-1", "Correct the refused evidence");
          assert.equal(correction.ok, true);
          routePeerInboxes();
          assert.ok(commands.some(c => c.message?.includes("byte budget")), "rejection must reach the resident");
        }} finally {{ child.emit("close", 0, null); mock.restoreAll(); }}
        attemptSubmission("reviewer", "spawn-1", task.id, "{outcome}", "Corrected evidence");
        processTaskIntents(); settle();
        console.log(JSON.stringify({{ refused, feedbackAfterRepeatedSettlement, input,
          correction, finalStatus: getTask(task.id).status, finalResult: getTask(task.id).result,
          reports: reports.filter(r => r.finished), attempt }}));
    ''')
    assert payload["refused"]["status"] == "in_progress"
    assert payload["refused"]["holder"] == "reviewer"
    assert payload["refused"]["assignment"] == payload["attempt"]
    assert payload["refused"]["reports"] == []
    assert len(payload["refused"]["feedback"]) == 1
    assert "byte budget" in payload["refused"]["feedback"][0]
    assert payload["feedbackAfterRepeatedSettlement"] == payload["refused"]["feedback"]
    assert payload["input"]["ok"] is True
    assert payload["correction"]["ok"] is True
    assert payload["finalStatus"] == ("completed" if outcome == "completed" else "blocked")
    assert payload["finalResult"] == "Corrected evidence"
    assert len(payload["reports"]) == 1
    assert payload["reports"][0]["body"] == "Corrected evidence"


def test_refused_failure_keeps_active_verification(tmp_path: Path) -> None:
    payload = machine_case(tmp_path, '''
        getTask(task.id).context = { budgetBytes: 1024 };
        getTask(task.id).verify = "Check evidence";
        let pass;
        setVerifyGateRunner(() => new Promise(resolve => { pass = () => resolve({ kind: "pass" }); }));
        attemptSubmission("reviewer", "spawn-1", task.id, "completed", "Verified evidence");
        processTaskIntents(); settle();
        await new Promise(resolve => setImmediate(resolve));
        attemptSubmission("reviewer", "spawn-1", task.id, "failed", "e".repeat(2048));
        processTaskIntents();
        const before = { status: getTask(task.id).status,
          assignment: getAgent("reviewer").assignment?.id ?? null, reports: reports.filter(r => r.finished) };
        attemptSubmission("reviewer", "spawn-1", task.id, "completed", "Competing evidence");
        processTaskIntents();
        const feedback = reminders().map(r => r.body);
        pass(); await new Promise(resolve => setImmediate(resolve));
        console.log(JSON.stringify({ before, feedback, status: getTask(task.id).status,
          result: getTask(task.id).result, verdict: getTask(task.id).completionVerdict,
          gate: getTask(task.id).completionGate, reports: reports.filter(r => r.finished), attempt }));
    ''')
    assert payload["before"] == {"status": "in_progress", "assignment": payload["attempt"], "reports": []}
    assert any("already has a completion review" in body for body in payload["feedback"])
    assert payload["status"] == "completed"
    assert payload["result"] == "Verified evidence"
    assert payload["verdict"] == "pass"
    assert payload["gate"] == "Check evidence"
    assert len(payload["reports"]) == 1
    assert payload["reports"][0]["status"] == "completed"


def test_worker_pass_verdict_cannot_bypass_independent_review(tmp_path: Path) -> None:
    payload = machine_case(tmp_path, '''
        getTask(task.id).verify = "Check evidence";
        const { createTaskIntent, submissionsDir, tasksFilePath } = await import("./src/task-domain/index.ts");
        const path = await import("node:path");
        let fail;
        let reviews = 0;
        setVerifyGateRunner(() => { reviews++; return new Promise(resolve => {
          fail = () => resolve({ kind: "fail", detail: "Evidence does not satisfy the gate" });
        }); });
        assert.equal(createTaskIntent(submissionsDir(path.dirname(tasksFilePath(undefined, root))), task.id, {
          taskId: task.id, participant: "reviewer", spawnId: "spawn-1", assignmentId: attempt,
          status: "completed", result: "Unverified evidence", verdict: "pass", timestamp: 3,
        }), true);
        processTaskIntents(); settle();
        await new Promise(resolve => setImmediate(resolve));
        const before = { status: getTask(task.id).status, reports: reports.filter(r => r.finished) };
        fail(); await new Promise(resolve => setImmediate(resolve));
        console.log(JSON.stringify({ before, reviews, status: getTask(task.id).status,
          verdict: getTask(task.id).completionVerdict ?? null,
          gate: getTask(task.id).completionGate ?? null, reports: reports.filter(r => r.finished) }));
    ''')
    assert payload == {
        "before": {"status": "in_progress", "reports": []},
        "reviews": 1, "status": "in_progress", "verdict": None, "gate": None, "reports": [],
    }

# ── test_capability_and_blocker_contract.py ──
from pathlib import Path

import pytest

from test_agent_package import SRC, PACKAGE, run_node


@pytest.mark.parametrize("requested", ["undefined", "[]", '["read", "bash"]'])
def test_public_lifecycle_content_discloses_recorded_grant(tmp_path: Path, requested: str) -> None:
    run_node(f'''
      import assert from "node:assert/strict";
      import {{ publishTeamHost, registerComposedTools }} from "./tests/composed-tools.ts";
      import {{ registerAgent, resetState }} from "{(SRC / 'state.ts').as_uri()}";
      import {{ exactSessionRoute, resolveAgentTools }} from "@fradser/pi-subagents";
      import {{ WORKER_CAPABILITY_TOOLS }} from "{(SRC / 'capability-tools.ts').as_uri()}";
      resetState();
      const tools = new Map();
      const requested = {requested};
      const grant = resolveAgentTools(requested, WORKER_CAPABILITY_TOOLS);
      const runtime = {{
        spawnAgent(input) {{
          const agent = {{ name: input.name, role: input.role, spawnId: "s1", status: "starting",
            workId: input.workId, tools: grant, pid: 0, isolation: "none", createdAt: 1, updatedAt: 1 }};
          registerAgent(agent);
          return {{ ok: true, agent }};
        }},
      }};
      registerComposedTools({{ registerTool: t => tools.set(t.name, t) }}, runtime);
      publishTeamHost(runtime);
      const start = p => tools.get("agent_start").execute("test", p, undefined, undefined, {{ cwd: {str(tmp_path)!r} }});
      // ADR-0008 left no inspection operation: the roster read is the one that
      // survives, and it takes no session handle.
      const roster = () => tools.get("agent_list").execute("test", {{}}, undefined, undefined, {{ cwd: {str(tmp_path)!r} }});
      // The roster name is minted by the start and only the label is authored, so
      // every later lookup resolves the handle the receipt returned.
      {{ 
        resetState();
        const result = await start({{ prompt: "Check evidence", label: "capability-test",
          ...(requested === undefined ? {{}} : {{ tools: requested }}) }});
        assert.equal(result.details.operation, "agent_start");
        assert.equal(result.details.disposition, "started", result.content[0].text);
        assert.match(result.details.session, /^session:subagent-[0-9a-f]+:s1$/);
        // The label is display only: it never becomes the roster key.
        assert.equal(result.details.label, "capability-test");
        assert.ok(!result.details.session.includes("capability-test"),
          `label leaked into the roster handle ${{result.details.session}}`);
        const listed = await roster();
        assert.equal(listed.details.operation, "agent_list");
        assert.equal(listed.details.disposition, "listed");
        // The effective grant is the one thing a caller routinely gets wrong by
        // assumption, so it is reported on the roster entry rather than inferred.
        const entry = listed.details.sessions.find((row) => row.session === result.details.session);
        assert.ok(entry, `the roster must hold the minted incarnation:\n${{JSON.stringify(listed.details.sessions)}}`);
        assert.deepEqual(entry.tools, grant);
        if (grant.length === 2) {{
          assert.deepEqual(grant, ["message", "task"],
            "an empty request is coordination-only: the two coordination tools and nothing else");
        }}
      }}
      // A name with no definition, no prompt and no grant is the idle-resident
      // case: a child that waits for work assigned to it. It has no model surface
      // any more, so the coordinator spawns it, and the roster still reports the
      // grant actually recorded rather than the empty one asked for — a caller
      // that assumed file access it did not get is the failure this prevents.
      // An idle resident no longer has a model-facing start, so the coordinator
      // creates it, and the roster still reports the grant actually recorded
      // rather than the empty one asked for.
      const idle = runtime.spawnAgent({{ name: "unknown-capability-test", role: "unknown-capability-test" }});
      assert.equal(idle.ok, true);
      assert.equal(idle.agent.status, "starting");
      assert.deepEqual(idle.agent.tools, grant, "the recorded grant is the one asked for");
      // The roster readback for a resident belongs to the harness that registers the
      // child with the execution layer; here the claim is that the coordinator
      // records the resolved grant rather than the empty one the caller asked for.
      assert.deepEqual(idle.agent.tools, grant, "the recorded grant is the one asked for");
      // A description with no instructions is a role with a purpose and no
      // standing instructions. It spawns, and the receipt says the difference,
      // because a role that teaches nothing must not read as one that does. The
      // model surface always supplies both halves, so this is the executor's own
      // half-role path, driven with the intent operation.
      const {{ executeChildIntent }} = await import("@fradser/pi-subagents");
      const halfRole = await executeChildIntent({{ operation: "start", name: "half-role",
        description: "only one half" }}, {{ cwd: {str(tmp_path)!r} }});
      assert.equal(halfRole.structuredContent.operation, "start");
      assert.equal(halfRole.structuredContent.outcome, "started", halfRole.content[0].text);
      assert.equal(halfRole.structuredContent.role, "only one half");
      assert.match(halfRole.content[0].text, /no standing instructions/);
      console.log(JSON.stringify({{ ok: true }}));
    ''', env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path / "agent")})


@pytest.mark.parametrize("recorded", ["undefined", '["read", "task", "message"]'])
def test_roster_read_uses_recorded_grant_not_current_definition(tmp_path: Path, recorded: str) -> None:
    run_node(f'''
      import assert from "node:assert/strict";
      import {{ publishTeamHost, registerComposedTools }} from "./tests/composed-tools.ts";
      import {{ registerAgent, resetState }} from "{(SRC / 'state.ts').as_uri()}";
      const {{ registerSessionAgent }} = await import("@fradser/pi-subagents");
      resetState();
      registerSessionAgent({{ name: "historical", description: "Changed role", prompt: "Changed role", tools: ["bash"] }});
      const tools = new Map();
      registerComposedTools({{ registerTool: t => tools.set(t.name, t) }});
      registerAgent({{ name: "historical", role: "historical", spawnId: "s1", status: "idle",
        tools: {recorded}, pid: 0, isolation: "none", createdAt: 1, updatedAt: 1 }});
      // Strict intent inputs take no session: the roster read is the surviving
      // way to look a recorded incarnation up, and it takes no handle.
      const result = await tools.get("agent_list").execute("test", {{}},
        undefined, undefined, {{ cwd: {str(tmp_path)!r} }});
      assert.equal(result.details.operation, "agent_list");
      assert.equal(result.details.disposition, "listed");
      const session = result.details.sessions[0];
      assert.equal(session.session, "session:historical:s1");
      assert.deepEqual(session.tools, {recorded});
      console.log(JSON.stringify({{ ok: true }}));
    ''', env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path / "agent")})


def test_guidance_requires_failed_blockers_and_quiet_leader_handling() -> None:
    guidance = (SRC / "guidance.ts").read_text()
    roles = (PACKAGE / "references" / "agent-roles.md").read_text()
    for text in [guidance, roles]:
        assert 'outcome: "failed"' in text
        assert "successful candidate" in text
        assert "independently verified" in text
    assert "no acknowledgment" in guidance
    assert "acceptance criteria" in guidance
    assert "verification gate" in guidance
    assert "repeated reports" in guidance


@pytest.mark.parametrize("outcome", ["failed", "success"])
def test_public_submit_settlement_keeps_blocked_dependents(tmp_path: Path, outcome: str) -> None:
    payload = machine_case(tmp_path, f'''
      const {{ createWorkerFixture, assistant }} = await import("{(PACKAGE / 'tests' / 'automatic-results-fixture.ts').as_uri()}");
      const {{ tasksFilePath, submissionsDir }} = await import("./src/task-domain/index.ts");
      const path = await import("node:path");
      const fixture = createWorkerFixture(root, "direct", "reviewer");
      const tasksSubmissions = submissionsDir(path.dirname(tasksFilePath(undefined, root)));
      fixture.binding.submissionsDir = tasksSubmissions;
      process.env.PI_TEAMMATE_SUBMISSIONS_DIR = tasksSubmissions;
      const agent = getAgent("reviewer");
      fixture.roster(agent.assignment, agent.spawnId, "working", task.id);
      const dependent = createTask({{ id: "dependent", subject: "Use verified evidence", dependsOn: [task.id] }}).task;
      getTask(task.id).verify = "Require actual execution evidence";
      setVerifyGateRunner(async () => ({{ kind: "fail", detail: "No execution evidence" }}));
      await fixture.start(attempt);
      const submitted = await fixture.call("task", {{ action: "submit", outcome: {outcome!r}, result: "Missing required tools" }});
      assert.equal(submitted.terminate, true);
      await fixture.answer(assistant("Blocked: cannot perform requested work"));
      await fixture.emit({{ type: "agent_settled" }});
      await fixture.emit({{ type: "agent_settled" }});
      assert.deepEqual(fixture.records(), [], "Explicit outcome suppresses automatic success");
      processTaskIntents(); settle();
      await new Promise(resolve => setImmediate(resolve));
      processTaskIntents(); settle();
      const {{ renderTaskList }} = await import("{(SRC / 'worker.ts').as_uri()}");
      console.log(JSON.stringify({{ status: getTask(task.id).status,
        reports: reports.filter(r => r.finished).map(r => r.status),
        task: renderTaskList([getTask(task.id), dependent]) }}));
    ''')
    assert payload["status"] != "completed"
    assert payload["reports"] == (["failed"] if outcome == "failed" else [])
    assert "dependent · pending/blocked" in payload["task"]


def test_inline_tools_schema_explains_least_privilege() -> None:
    text = (SRC / "types.ts").read_text()
    assert "coordination-only" in text
    run_node(f'''
      import assert from "node:assert/strict";
      import {{ InlineAgentDefinitionParams }} from "{(SRC / 'types.ts').as_uri()}";
      import {{ AGENT_BUILTIN_TOOLS }} from "@fradser/pi-subagents";
      import {{ buildIdleLeaderGuidance }} from "{(SRC / 'guidance.ts').as_uri()}";
      for (const tool of AGENT_BUILTIN_TOOLS) {{
        assert.ok(InlineAgentDefinitionParams.properties.tools.description.includes(tool), `Schema missing ${{tool}}`);
        assert.ok(buildIdleLeaderGuidance().includes(tool), `Guidance missing ${{tool}}`);
      }}
      console.log(JSON.stringify({{ ok: true }}));
    ''')


def _write_agent(path: Path, name: str, frontmatter: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ndescription: A test role\ntools: read, bash\n{frontmatter}\n---\n\nRole body.\n",
        encoding="utf-8",
    )


def test_agent_memory_reaches_only_a_fixed_agents_spawn(tmp_path: Path) -> None:
    """Agent Memory is a persisted Agent's own capability, so only its spawn
    carries the tool and the worker extension that registers it.

    A Temporary Agent owns no folder to write, so a grant it cannot use is a
    receipt that lies: the row would say the child may record capability lessons
    and the child would find no such tool.
    """
    # VISION.md supersedes opt-in: every canonical disk identity has Memory.
    _write_agent(tmp_path / ".pi" / "agents" / "fixed" / "agent.md", "fixed", "")
    _write_agent(tmp_path / ".pi" / "agents" / "plain" / "agent.md", "plain", "")
    payload = run_node(
        f'''
        import childProcess from "node:child_process";
        import {{ EventEmitter }} from "node:events";
        import {{ syncBuiltinESMExports }} from "node:module";
        import {{ PassThrough }} from "node:stream";
        import {{ mock }} from "node:test";
        import * as kit from "@fradser/pi-kit";
        const children = [];
        mock.module("@fradser/pi-kit", {{
          namedExports: {{
            ...kit,
            resolvePiCli: () => ({{ command: "unused-mock", args: [] }}),
            spawnPiChild: (command, args) => {{
              const child = Object.assign(new EventEmitter(), {{
                pid: 100, stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(),
              }});
              children.push({{ command, args, child }});
              return child;
            }},
            terminateChildProcess: async () => true,
          }},
        }});
        const {{ initTeamMachine, shutdownTeamMachine, spawnAgent }} = await import({(SRC / "team-machine.ts").as_uri()!r});
        const {{ getAgent, resetState }} = await import({(SRC / "state.ts").as_uri()!r});
        const root = {str(tmp_path)!r};
        resetState();
        initTeamMachine({{ sessionManager: undefined, cwd: root }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        const fixed = spawnAgent({{ name: "fixed-child", role: "fixed" }});
        const plain = spawnAgent({{ name: "plain-child", role: "plain" }});
        const temporary = spawnAgent({{ name: "temp-child", role: "temp-role",
          definition: {{ description: "One answer", prompt: "Answer once.", tools: ["read"] }} }});
        const refused = spawnAgent({{ name: "memory-child", role: "memory-role",
          definition: {{ description: "Wants memory", prompt: "Remember this.", tools: ["agent_memory"] }} }});
        const toolsOf = (spawn) => spawn.ok ? getAgent(spawn.agent.name)?.tools : null;
        // Spawns are sequential, so child N is the argv of spawn N — and a
        // refused spawn contributing no child is itself the assertion.
        const toolArgv = (args) => args[args.indexOf("--tools") + 1];
        const extensionsOf = (args) => args.reduce((all, value, index) =>
          args[index - 1] === "--extension" ? [...all, value] : all, []);
        const argvOf = (index) => children[index].args;
        console.log(JSON.stringify({{
          fixed: {{ ok: fixed.ok, tools: toolsOf(fixed), argv: toolArgv(argvOf(0)),
            extensions: extensionsOf(argvOf(0)) }},
          plain: {{ ok: plain.ok, tools: toolsOf(plain), argv: toolArgv(argvOf(1)),
            extensions: extensionsOf(argvOf(1)) }},
          temporary: {{ ok: temporary.ok, tools: toolsOf(temporary), argv: toolArgv(argvOf(2)),
            extensions: extensionsOf(argvOf(2)) }},
          refused: {{ ok: refused.ok, error: refused.ok ? null : refused.error }},
          spawned: children.length,
        }}));
        shutdownTeamMachine();
        for (const entry of children) entry.child.emit("close", 0, null);
        ''',
        module_mocks=True,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path / "agent")},
    )

    assert payload["spawned"] == 3, "a refused spawn must not start a child"
    # A fixed Agent: the memory tool is real, and something registers it.
    assert payload["fixed"]["ok"] is True
    assert "agent_memory" in payload["fixed"]["tools"]
    assert payload["fixed"]["argv"].split(",") == payload["fixed"]["tools"]
    assert any("agent-extension" in path for path in payload["fixed"]["extensions"]), payload["fixed"]["extensions"]
    # A disk identity without flags still gets Memory; temporary roles do not.
    assert payload["plain"]["ok"] is True
    assert payload["plain"]["tools"] == ["read", "bash", "agent_memory", "message", "task"]
    assert payload["plain"]["argv"].split(",") == payload["plain"]["tools"]
    assert any("agent-extension" in path for path in payload["plain"]["extensions"])
    assert payload["temporary"]["ok"] is True
    assert "agent_memory" not in payload["temporary"]["tools"]
    assert payload["temporary"]["argv"].split(",") == payload["temporary"]["tools"]
    assert not any("agent-extension" in path for path in payload["temporary"]["extensions"])
    assert payload["temporary"]["tools"] == ["read", "message", "task"]
    # Asking for the tool with no folder is refused rather than silently dropped.
    assert payload["refused"]["ok"] is False
    assert "memory" in str(payload["refused"]["error"])

# ── test_orchestration_discipline.py ──
"""Contract checks on the actual prompt projection, not a new scheduling engine."""


import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest

from test_agent_package import PACKAGE, SRC, run_node


@pytest.fixture(scope="module")
def prompts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    root = tmp_path_factory.mktemp("orchestration-prompts")
    return run_node(f'''
      import {{ buildIdleLeaderGuidance, buildTeamLeaderGuidance, WORKER_GUIDANCE }} from "{(SRC / 'guidance.ts').as_uri()}";
      console.log(JSON.stringify({{
        idle: buildIdleLeaderGuidance({str(root)!r}),
        active: buildTeamLeaderGuidance({str(root)!r}),
        worker: WORKER_GUIDANCE,
      }}));
    ''', env_overrides={"HOME": str(root), "PI_CODING_AGENT_DIR": str(root / "agent")})


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text)


@pytest.mark.parametrize("state", ["idle", "active"])
def test_leader_prompts_expose_candidate_bound_completion(prompts: dict[str, str], state: str) -> None:
    guidance = normalized(prompts[state])
    for rule in (
        "one integration owner",
        "same candidate",
        "blocking reviews",
        "findings resolved",
        "completed review Work is not a PASS verdict",
        "yield without declaring completion",
        "resources",
        "dependsOn",
        "independent reviewer prompt, not a shell command",
        "reopen",
        "closed assignment",
    ):
        assert rule in guidance, (state, rule)
    assert "coordination-only" in guidance
    assert "verification gate" in guidance


@pytest.mark.parametrize("state", ["idle", "active"])
def test_leader_preserves_findings_and_refreshes_review_context_before_assignment(prompts: dict[str, str], state: str) -> None:
    text = normalized(prompts[state])
    for rule in ("preserve prior findings", "authoritative brief", "before reopening", "does not update the description", "candidate fingerprint", "correction delta", "bounded follow-up", "dependsOn"):
        assert rule in text, (state, rule)


def test_worker_prompt_keeps_local_scope_and_review_verdict_distinct(prompts: dict[str, str]) -> None:
    worker = normalized(prompts["worker"])
    for rule in ("assigned checks", "candidate", "REWORK", "implementation acceptance", 'outcome: "failed"', "without editing", "without waiting for repairs", "authoritative brief"):
        assert rule in worker


def test_packaged_role_reference_discloses_bounded_assignment_contract() -> None:
    roles = (PACKAGE / "references" / "agent-roles.md").read_text()
    for rule in ("baseline", "dependencies", "verification owner", "candidate", "REWORK", "reviewer prompt"):
        assert rule.lower() in roles.lower(), rule


def test_work_recheck_needs_explicit_refreshed_context(tmp_path: Path) -> None:

    payload = machine_case(tmp_path, '''
      const { completeTaskWithOutcome, reopenTask } = await import("''' + (SRC / "state.ts").as_uri() + '''");
      task.description = "Inspect candidate v1 against baseline B0";
      const priorReport = "Spec REWORK: reviewer scope and stale candidate brief";
      assert.ok(completeTaskWithOutcome(task.id, "reviewer", "success", priorReport).ok);
      const savedResult = getTask(task.id).result;
      assert.equal(savedResult, priorReport);
      assert.equal(reopenTask(task.id).ok, true);
      const reopened = getTask(task.id);
      assert.equal(reopened.description, "Inspect candidate v1 against baseline B0");
      assert.equal(reopened.result, priorReport);
      // This synthetic original is completed again only to exercise a linked follow-up.
      assert.ok(takeTask(task.id, "reviewer").ok);
      assert.ok(completeTaskWithOutcome(task.id, "reviewer", "success", savedResult).ok);
      const description = `Bounded recheck: baseline B0; candidate v2; delta fixes two findings. Prior findings: ${savedResult}. Safe checks: prompt contract only.`;
      const followUp = createTask({ subject: "Recheck review corrections",
        description, dependsOn: [task.id] });
      // A created task is pending; whether it can be taken right now is a task set
      // question answered by `claimableTasks`, not a property of the creation.
      assert.equal(followUp.ok, true);
      assert.equal(followUp.task.status, "pending");
      console.log(JSON.stringify({ oldDescription: reopened.description, retainedResult: reopened.result ?? null,
        followUp: followUp.task }));
    ''')
    assert payload["retainedResult"] == "Spec REWORK: reviewer scope and stale candidate brief"
    assert payload["oldDescription"].startswith("Inspect candidate v1")
    assert "candidate v2" in payload["followUp"]["description"]
    assert "reviewer scope and stale candidate brief" in payload["followUp"]["description"]
    assert payload["followUp"]["dependsOn"] == ["work:review"]


def test_registered_extension_injects_contract_in_idle_and_active_contexts(tmp_path: Path) -> None:
    payload = run_node(f'''
      import register from "{(SRC / 'index.ts').as_uri()}";
      import {{ createTask, resetState }} from "{(SRC / 'state.ts').as_uri()}";
      const events = new Map();
      register({{
        on(name, handler) {{ events.set(name, handler); }}, registerTool() {{}}, registerCommand() {{}},
        registerMessageRenderer() {{}}, registerEntryRenderer() {{}},
      }});
      const ctx = {{ cwd: {str(tmp_path)!r} }};
      resetState();
      const options = {{ sections: {{ peer: "Peer section" }}, promptGuidelines: ["Peer guideline"] }};
      const idle = await events.get("before_agent_start")({{ messageType: "custom", systemPrompt: "base", systemPromptOptions: options }}, ctx);
      const idleText = options.sections.agent_teams_leader;
      options.promptGuidelines = ["Peer guideline"];
      createTask({{ subject: "candidate review" }});
      const active = await events.get("before_agent_start")({{ messageType: "custom", systemPrompt: "base", systemPromptOptions: options }}, ctx);
      if (idle !== undefined || active !== undefined) throw new Error("No prompt override or custom injection message is permitted");
      if (options.sections.peer !== "Peer section" || options.promptGuidelines[0] !== "Peer guideline") throw new Error("Peer contributions changed");
      console.log(JSON.stringify({{ idle: idleText, active: options.sections.agent_teams_leader }}));
    ''', env_overrides={"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent")})
    for text in payload.values():
        assert not text.startswith("base")
        assert text.count("### Delivery contract") == 1
        assert "yield without declaring completion" in text


def test_real_pi_receives_orchestration_and_review_instructions(tmp_path: Path) -> None:
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("Pi CLI is required for live prompt-delivery verification")
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "settings.json").write_text(json.dumps({"quietStartup": True}))
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update({"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1",
                "PI_ORCHESTRATION_AUTH": secrets.token_hex(16)})
    result = subprocess.run([
        pi, "--print", "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates",
        "--no-themes", "--no-context-files", "--no-approve", "--no-builtin-tools",
        "--extension", str(PACKAGE / "tests" / "orchestration-live-fixture.ts"),
        "--provider", "orchestration-guidance-fixture", "--model", "deterministic", "--thinking", "off",
        "Verify instruction delivery without delegating or changing source files.",
    ], cwd=tmp_path, env=env, input="", text=True, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ORCHESTRATION_PROMPT_DELIVERY_OK" in result.stdout, result.stdout + result.stderr
    assert "Extension error" not in result.stderr

# ── test_session_history_regressions.py ──

from pathlib import Path



def test_failed_work_is_not_automatically_claimable_again(tmp_path: Path) -> None:
    payload = machine_case(tmp_path, '''
        const { claimableTasks, applyClaimIntent } = await import("./src/state.ts");
        const dependent = createTask({ id: "dependent", subject: "Use evidence", dependsOn: [task.id] }).task;
        attemptSubmission("reviewer", "spawn-1", task.id, "failed", "External parser rejected both authorized attempts");
        processTaskIntents(); settle(); processTaskIntents();
        const available = claimableTasks().map(t => t.id);
        const reclaimed = applyClaimIntent({ taskId: task.id, participant: "reviewer", spawnId: "spawn-1", timestamp: 40 });
        console.log(JSON.stringify({ available, reclaimed, reports: reports.filter(r => r.finished).length,
          dependent: getTask(dependent.id).status }));
    ''')
    assert payload["reports"] == 1
    assert payload["dependent"] == "pending"
    assert "work:review" not in payload["available"]
    assert payload["reclaimed"]["applied"] is False


def test_superseded_holder_keeps_cancellation_tool(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        const { registerChildCapabilities } = await import("./src/worker.ts");
        let active = ["read", "agent_event", "work"];
        const registered = new Map();
        const hooks = new Map();
        const disclosure = registerChildCapabilities({
          registerTool: t => registered.set(t.name, t),
          on: (name, handler) => hooks.set(name, [...(hooks.get(name) ?? []), handler]),
          getActiveTools: () => [...active], setActiveTools: names => { active = [...names]; },
        });
        const roster = JSON.parse(fs.readFileSync(fixture.binding.rosterFile, "utf8"));
        roster.agents[0].currentTaskId = "cancelled-work";
        roster.agents[0].assignment.closed = true;
        fs.writeFileSync(fixture.binding.rosterFile, JSON.stringify(roster));
        disclosure.update("Task superseded. Stop and acknowledge cancellation.");
        console.log(JSON.stringify({ active }));
    ''')
    assert "work" in payload["active"], "A retained cancellation holder must be able to submit/release"


def test_old_turn_cannot_send_as_reassigned_work(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start("attempt-1");
        fixture.roster({ id: "attempt-2", kind: "task", resources: [] });
        const roster = JSON.parse(fs.readFileSync(fixture.binding.rosterFile, "utf8"));
        roster.agents[0].currentTaskId = "work-2";
        fs.writeFileSync(fixture.binding.rosterFile, JSON.stringify(roster));
        let rejection;
        try { await fixture.call("message", { to: "leader", body: "Old cancellation acknowledgement" }); }
        catch (error) { rejection = error.message; }
        console.log(JSON.stringify({ records: fixture.records(), rejection }));
    ''')
    assert not any(record.get("assignmentId") == "attempt-2" for record in payload["records"])
    assert "different assignment" in str(payload["rejection"]), "The stale turn must be actively rejected, not silently ignored"
    assert payload["records"] == [], "A stale turn must write no report at all"


def test_old_turn_cannot_submit_new_roster_work(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start("attempt-1");
        fixture.roster({ id: "attempt-2", kind: "task", resources: [] });
        const roster = JSON.parse(fs.readFileSync(fixture.binding.rosterFile, "utf8"));
        roster.agents[0].currentTaskId = "work-2";
        fs.writeFileSync(fixture.binding.rosterFile, JSON.stringify(roster));
        let rejection;
        try { await fixture.call("task", { action: "submit", outcome: "failed", result: "Old task was cancelled" }); }
        catch (error) { rejection = error.message; }
        const markerPath = fixture.binding.submissionsDir + "/work-2.json";
        console.log(JSON.stringify({ rejection, marker: fs.existsSync(markerPath) ? JSON.parse(fs.readFileSync(markerPath, "utf8")) : null }));
    ''')
    assert payload["marker"] is None, "An old turn must never submit the current roster's replacement work"


def test_submission_does_not_leave_a_communication_loop(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        const roster = JSON.parse(fs.readFileSync(fixture.binding.rosterFile, "utf8"));
        roster.agents[0].currentTaskId = "work-1";
        fs.writeFileSync(fixture.binding.rosterFile, JSON.stringify(roster));
        await fixture.start();
        const result = await fixture.call("task", { action: "submit", outcome: "failed", result: "Cancelled" });
        let rejection;
        try { await fixture.call("message", { to: "leader", body: "Please settle cancellation again" }); }
        catch (error) { rejection = error.message; }
        console.log(JSON.stringify({ terminate: result.terminate, records: fixture.records(), rejection }));
    ''')
    assert payload["terminate"] is True
    assert payload["records"] == [], "Closed attempt must not keep emitting cancellation requests"
    assert "terminal report or is closed" in str(payload["rejection"]), "The closed attempt must reject the repeat, not silently ignore it"

# ── test_historical_report_delivery.py ──

import os
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest

from test_agent_package import PACKAGE


@pytest.mark.parametrize("transition", ["stopped", "released", "superseded", "completed", "replacement", "active"])
def test_real_pi_excludes_retired_attempt_reports_but_preserves_history(tmp_path: Path, transition: str) -> None:
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("Pi CLI is required for the native report delivery regression")
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update({
        "HOME": str(tmp_path),
        "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "PI_OFFLINE": "1",
        "PI_REPORT_FIXTURE_AUTH": secrets.token_hex(16),
        "PI_REPORT_HISTORY_TRANSITION": transition,
    })
    result = subprocess.run(
        [pi, "--print", "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates",
         "--no-themes", "--no-context-files", "--no-approve",
         "--extension", str(PACKAGE / "tests/historical-report-fixture.ts"),
         "--provider", "historical-report-fixture", "--model", "deterministic", "--thinking", "off",
         "--tools", "produce_historical_reports,check_historical_reports", "Run the historical report fixture"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stderr
    assert "PI_HISTORICAL_REPORT_OK" in result.stdout, result.stdout + result.stderr
    assert "PI_HISTORICAL_REPORT_FAILED" not in result.stdout

# ── test_immediate_reports.py ──

import os
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest

from test_agent_package import PACKAGE, SRC, run_node


@pytest.mark.parametrize("leader_idle", [False, True])
def test_reports_are_handed_off_without_waiting(tmp_path: Path, leader_idle: bool) -> None:
    payload = run_node(
        f'''\
        import extension from "{(SRC / 'index.ts').as_uri()}";
        import {{ drainTeammateOutboxes, shutdownTeamMachine, applyProgress }} from "{(SRC / 'team-machine.ts').as_uri()}";
        import {{ registerAgent, createTask, takeTask, getAgent }} from "{(SRC / 'state.ts').as_uri()}";
        import {{ appendWorkerEvent, stateFilePath, workerOutboxPath }} from "{(SRC / 'statefile.ts').as_uri()}";
        const hooks = new Map();
        const sent = [];
        const pi = {{
          on(event, handler) {{ hooks.set(event, handler); }},
          registerTool() {{}}, registerCommand() {{}},
          registerEntryRenderer() {{}}, registerMessageRenderer() {{}},
          getActiveTools: () => [], getAllTools: () => [], setActiveTools() {{}},
          sendMessage(message, options) {{ sent.push({{ message, options }}); }},
        }};
        const cwd = {str(tmp_path)!r};
        const ctx = {{ cwd, mode: 'print', hasUI: false, isIdle: () => {str(leader_idle).lower()},
          sessionManager: {{ getSessionFile: () => undefined }},
          ui: {{ setWidget() {{}}, setStatus() {{}}, notify() {{}} }},
        }};
        extension(pi);
        await hooks.get('session_start')({{}}, ctx);
        try {{
          registerAgent({{ name: 'author', role: 'worker', spawnId: 's1', pid: 0,
            status: 'working', isolation: 'none', createdAt: 1, updatedAt: 1 }});
          const task = createTask({{ subject: 'Validate work' }}).task;
          takeTask(task.id, 'author');
          const assignmentId = getAgent('author').assignment.id;
          applyProgress('author', 's1', {{ text: '', turns: 1, finalResponse: false }});
          const outbox = workerOutboxPath(stateFilePath(undefined, cwd), 'author', 's1');
          for (const [id, body, status] of [
            ['e1', 'New evidence changes the scope', 'in_progress'],
            ['e2', 'Assignment complete with validation', 'completed'],
          ]) {{
            appendWorkerEvent(outbox, {{ id, type: 'message', worker: 'author', spawnId: 's1', assignmentId, body, status, timestamp: 100 }});
            drainTeammateOutboxes();
            if (status === 'completed') applyProgress('author', 's1', {{ text: body, turns: 1, finalResponse: true }});
          }}
          const beforeSettlement = sent.map((entry) => ({{
            eventId: entry.message.details.eventId,
            status: entry.message.details.status,
            deliverAs: entry.options.deliverAs,
            triggerTurn: entry.options.triggerTurn,
            stamped: entry.message.content.includes('1970-01-01T00:00:00.100Z'),
          }}));
          await hooks.get('agent_settled')?.({{}}, ctx);
          await new Promise((resolve) => setTimeout(resolve, 10));
          console.log(JSON.stringify({{ beforeSettlement, afterSettlement: sent.length }}));
        }} finally {{
          await hooks.get('session_shutdown')({{}}, ctx);
          shutdownTeamMachine();
        }}
        ''',
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path / "agent")},
    )
    reports = payload["beforeSettlement"]
    assert reports[0] == {"eventId": "e1", "status": "in_progress", "deliverAs": "steer", "triggerTurn": True, "stamped": True}
    assert reports[1]["eventId"]
    assert reports[1] | {"eventId": "accepted"} == {
        "eventId": "accepted", "status": "completed", "deliverAs": "steer", "triggerTurn": True, "stamped": True,
    }
    assert payload["afterSettlement"] == 2


def test_leader_guidance_limits_steering_to_new_information() -> None:
    payload = run_node(
        f'''\
        import {{ buildTeamLeaderGuidance }} from "{(SRC / 'guidance.ts').as_uri()}";
        const guidance = buildTeamLeaderGuidance().replace(/\\s+/g, ' ');
        console.log(JSON.stringify({{ guidance }}));
        '''
    )
    guidance = str(payload["guidance"])
    assert "new information that changes its assignment" in guidance
    # Positive form: what a message is for, rather than what asking again is not.
    assert "each message is the whole update" in guidance
    assert "The worker autonomously completes its assignment" in guidance
    assert "keep working on your own assignment while they come" in guidance


def test_real_pi_delivers_reports_before_the_next_tool(tmp_path: Path) -> None:
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("Pi CLI is required for the native delivery integration test")
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update({
        "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "PI_OFFLINE": "1",
        "PI_REPORT_FIXTURE_AUTH": secrets.token_hex(16),
    })
    result = subprocess.run(
        [pi, "--print", "--no-session", "--no-extensions", "--no-skills",
         "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-approve",
         "--extension", str(PACKAGE / "tests" / "immediate-reports-fixture.ts"),
         "--provider", "report-fixture", "--model", "deterministic",
         "--thinking", "off", "--tools", "produce_reports,check_reports", "Run the report fixture"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stderr
    assert "PI_IMMEDIATE_REPORTS_OK" in result.stdout, result.stdout + result.stderr
    assert "PI_IMMEDIATE_REPORTS_FAILED" not in result.stdout

# ── test_late_report_delivery.py ──

import errno
import os
import pty
import select
import secrets
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from test_agent_package import PACKAGE, SRC, run_node


def test_finish_entry_describes_assignment_not_process() -> None:
    payload = run_node(f'''
        import extension, {{ TEAMMATE_FINISHED_ENTRY_TYPE }} from "{(SRC / 'index.ts').as_uri()}";
        const renderers = new Map();
        extension({{
          on() {{}}, registerTool() {{}}, registerCommand() {{}}, registerMessageRenderer() {{}},
          registerEntryRenderer(type, renderer) {{ renderers.set(type, renderer); }},
          getActiveTools: () => [], getAllTools: () => [], setActiveTools() {{}},
        }});
        const theme = {{ fg: (_color, text) => text }};
        const output = renderers.get(TEAMMATE_FINISHED_ENTRY_TYPE)({{ data: {{ agent: 'worker' }} }}, {{}}, theme).render(100).join('');
        console.log(JSON.stringify({{ output }}));
    ''')
    assert "Assignment" in payload["output"]
    assert "Agent @worker finished" not in payload["output"]


def test_late_report_label_is_visible_collapsed_and_expanded() -> None:
    payload = run_node(f'''
        import extension from "{(SRC / 'index.ts').as_uri()}";
        import {{ initTheme }} from "@earendil-works/pi-coding-agent";
        import {{ visibleWidth }} from "@earendil-works/pi-tui";
        initTheme('dark');
        const renderers = new Map();
        extension({{
          on() {{}}, registerTool() {{}}, registerCommand() {{}}, registerEntryRenderer() {{}},
          registerMessageRenderer(type, renderer) {{ renderers.set(type, renderer); }},
        }});
        const theme = {{ fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text }};
        const renderer = renderers.get('agent-teams-report');
        const message = {{ details: {{ agent: 'role', agent: 'worker', body: 'Original report body.', deliveredAfterStop: true }} }};
        const outputs = [false, true].map((expanded) => renderer(message, {{ expanded, outputPad: 0 }}, theme).render(100).join('\\n'));
        const narrow = renderer(message, {{ expanded: false, outputPad: 0 }}, theme).render(24);
        const normal = renderer({{ details: {{ agent: 'role', agent: 'worker', body: 'Normal.' }} }}, {{ expanded: false, outputPad: 0 }}, theme).render(100).join('\\n');
        console.log(JSON.stringify({{ outputs, narrowFits: narrow.every((line) => visibleWidth(line) <= 24), normal }}));
    ''')
    assert all("late delivery" in output.lower() for output in payload["outputs"])
    assert "Original report body." in payload["outputs"][1]
    assert payload["narrowFits"]
    assert "late delivery" not in payload["normal"].lower()


def test_normal_report_keeps_authored_time_without_after_stop_marker() -> None:
    payload = run_node(f'''
        import {{ annotateReportDelivery, formatReports }} from "@fradser/pi-subagents";
        const original = {{ agent: 'role', agent: 'worker', body: 'Original.', timestamp: 100 }};
        const report = annotateReportDelivery(original, 200);
        console.log(JSON.stringify({{ original, report, content: formatReports([report]) }}));
    ''')
    assert payload["report"]["timestamp"] == 100
    assert payload["report"]["deliveredAt"] == 200
    assert "deliveredAfterStop" not in payload["report"]
    assert "deliveredAt" not in payload["original"]
    assert 'delivery="after-stop"' not in payload["content"]


def run_pi_in_terminal(command: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    master, slave = pty.openpty()
    output = bytearray()
    sent_exit = False
    try:
        with subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, cwd=cwd, env=env) as process:
            os.close(slave)
            deadline = time.monotonic() + 20
            try:
                while True:
                    assert time.monotonic() < deadline, "Pi terminal fixture timed out"
                    if select.select([master], [], [], 0.1)[0]:
                        try:
                            chunk = os.read(master, 65536)
                        except OSError as error:
                            if error.errno != errno.EIO:
                                raise
                            break
                        if not chunk:
                            break
                        output.extend(chunk)
                    elif process.poll() is not None:
                        break
                    if not sent_exit and b"PI_LATE_REPORT_" in output:
                        os.write(master, b"\x04")
                        sent_exit = True
                return subprocess.CompletedProcess(command, process.wait(timeout=2), output.decode(errors="replace"), "")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    finally:
        os.close(master)


@pytest.mark.parametrize("mode", ["print", "tui"])
@pytest.mark.parametrize("stop_boundary", ["before-delivery", "during-delivery"])
def test_real_pi_classifies_delivery_boundary(tmp_path: Path, mode: str, stop_boundary: str) -> None:
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("Pi CLI is required for native delivery integration")
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update({
        "HOME": str(tmp_path),
        "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "PI_OFFLINE": "1",
        "PI_REPORT_STOP_BOUNDARY": stop_boundary,
        "PI_REPORT_FIXTURE_AUTH": secrets.token_hex(16),
    })
    command = [
        pi, *(["--print"] if mode == "print" else []), "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates",
        "--no-themes", "--no-context-files", "--no-approve",
        "--extension", str(PACKAGE / "tests/late-report-fixture.ts"),
        "--provider", "late-report-fixture", "--model", "deterministic", "--thinking", "off",
        "--tools", "queue_and_stop,check_late_report", "Run the late report fixture",
    ]
    result = (run_pi_in_terminal(command, env, tmp_path) if mode == "tui" else
              subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=25))
    assert result.returncode == 0, result.stderr
    assert "PI_LATE_REPORT_OK" in result.stdout, result.stdout + result.stderr
    assert "PI_LATE_REPORT_FAILED" not in result.stdout
    if mode == "tui":
        assert ("Late delivery: process already stopped." in result.stdout) == (stop_boundary == "before-delivery")
