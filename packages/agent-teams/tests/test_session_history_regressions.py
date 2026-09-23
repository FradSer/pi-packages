from __future__ import annotations

from pathlib import Path

from test_accepted_work_reporting import machine_case
from test_automatic_results import run_worker


def test_failed_work_is_not_automatically_claimable_again(tmp_path: Path) -> None:
    payload = machine_case(tmp_path, '''
        const { claimableTasks, applyClaimIntent } = await import("./src/state.ts");
        const dependent = createTask({ id: "dependent", subject: "Use evidence", dependsOn: [task.id] }).task;
        attemptSubmission("reviewer", "spawn-1", task.id, "failed", "External parser rejected both authorized attempts");
        processTaskIntents(); settle(); processTaskIntents();
        const available = claimableTasks().map(t => t.id);
        const reclaimed = applyClaimIntent({ taskId: task.id, worker: "reviewer", spawnId: "spawn-1", timestamp: 40 });
        console.log(JSON.stringify({ available, reclaimed, reports: reports.filter(r => r.finished).length,
          dependent: getTask(dependent.id).status }));
    ''')
    assert payload["reports"] == 1
    assert payload["dependent"] == "pending"
    assert "work:review" not in payload["available"]
    assert payload["reclaimed"]["applied"] is False


def test_superseded_holder_keeps_cancellation_tool(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        const { registerWorkerCapabilities } = await import("./src/worker.ts");
        let active = ["read", "agent_event", "work"];
        const registered = new Map();
        const hooks = new Map();
        const disclosure = registerWorkerCapabilities({
          registerTool: t => registered.set(t.name, t),
          on: (name, handler) => hooks.set(name, [...(hooks.get(name) ?? []), handler]),
          getActiveTools: () => [...active], setActiveTools: names => { active = [...names]; },
        });
        const roster = JSON.parse(fs.readFileSync(fixture.binding.rosterFile, "utf8"));
        roster.teammates[0].currentTaskId = "cancelled-work";
        roster.teammates[0].assignment.closed = true;
        fs.writeFileSync(fixture.binding.rosterFile, JSON.stringify(roster));
        disclosure.update("Task superseded. Stop and acknowledge cancellation.");
        console.log(JSON.stringify({ active }));
    ''')
    assert "work" in payload["active"], "A retained cancellation holder must be able to submit/release"


def test_old_turn_cannot_send_as_reassigned_work(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start("attempt-1");
        fixture.roster({ id: "attempt-2", kind: "board", resources: [] });
        const roster = JSON.parse(fs.readFileSync(fixture.binding.rosterFile, "utf8"));
        roster.teammates[0].currentTaskId = "work-2";
        fs.writeFileSync(fixture.binding.rosterFile, JSON.stringify(roster));
        let rejection;
        try { await fixture.call("agent_event", { to: "leader", message: "Old cancellation acknowledgement" }); }
        catch (error) { rejection = error.message; }
        console.log(JSON.stringify({ records: fixture.records(), rejection }));
    ''')
    assert not any(record.get("assignmentId") == "attempt-2" for record in payload["records"])
    assert "different assignment" in str(payload["rejection"]), "The stale turn must be actively rejected, not silently ignored"
    assert payload["records"] == [], "A stale turn must write no report at all"


def test_old_turn_cannot_submit_new_roster_work(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start("attempt-1");
        fixture.roster({ id: "attempt-2", kind: "board", resources: [] });
        const roster = JSON.parse(fs.readFileSync(fixture.binding.rosterFile, "utf8"));
        roster.teammates[0].currentTaskId = "work-2";
        fs.writeFileSync(fixture.binding.rosterFile, JSON.stringify(roster));
        let rejection;
        try { await fixture.call("work", { action: "submit", outcome: "failed", result: "Old task was cancelled" }); }
        catch (error) { rejection = error.message; }
        const markerPath = fixture.binding.submissionsDir + "/work-2.json";
        console.log(JSON.stringify({ rejection, marker: fs.existsSync(markerPath) ? JSON.parse(fs.readFileSync(markerPath, "utf8")) : null }));
    ''')
    assert payload["marker"] is None, "An old turn must never submit the current roster's replacement work"


def test_submission_does_not_leave_a_communication_loop(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        const roster = JSON.parse(fs.readFileSync(fixture.binding.rosterFile, "utf8"));
        roster.teammates[0].currentTaskId = "work-1";
        fs.writeFileSync(fixture.binding.rosterFile, JSON.stringify(roster));
        await fixture.start();
        const result = await fixture.call("work", { action: "submit", outcome: "failed", result: "Cancelled" });
        let rejection;
        try { await fixture.call("agent_event", { to: "leader", message: "Please settle cancellation again" }); }
        catch (error) { rejection = error.message; }
        console.log(JSON.stringify({ terminate: result.terminate, records: fixture.records(), rejection }));
    ''')
    assert payload["terminate"] is True
    assert payload["records"] == [], "Closed attempt must not keep emitting cancellation requests"
    assert "terminal report or is closed" in str(payload["rejection"]), "The closed attempt must reject the repeat, not silently ignore it"
