from __future__ import annotations

from pathlib import Path

import pytest

from test_accepted_work_reporting import machine_case


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
        const { createTaskIntent, submissionsDir, tasksFilePath } = await import("@fradser/pi-tasks");
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
