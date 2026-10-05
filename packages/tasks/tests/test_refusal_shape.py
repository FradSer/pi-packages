"""One refusal shape across the whole task store.

The store used to return five different refusal payloads: some named an
`error`, some a `reason`, some a `refusal` code and a `detail`, and the marker
path called its text an `error` again. Every caller therefore learned a second
vocabulary per function, and a caller that wanted to branch on *why* could only
do it for one of them.

The contract now: a refusal is `{ refusal, detail?, reason }` everywhere. The
code is for a machine, the reason is for whoever reads it, and the two are
carried by one shape. A success flag stays whatever the operation's own domain
calls it — `ok` for a task write, `applied` for a marker — because that is the
operation's answer rather than a refusal.
"""

from __future__ import annotations

import json

from task_helpers import PACKAGE, run_node

ENTRY = (PACKAGE / "index.ts").as_uri()


def run(script: str) -> dict[str, object]:
    return run_node(
        f"""
        import assert from "node:assert/strict";
        import * as task from {json.dumps(ENTRY)};
        task.clearTasks();
        {script}
        """,
    )


def test_every_store_refusal_carries_one_shape(tmp_path) -> None:
    """Each refusal names a machine code, a detail when it has one, and a reason.

    The `error` assertion is the regression this replaces: a caller that reads
    `.reason` must not have to know that two of these five called it `.error`.
    """
    payload = run(
        """
        const created = task.createTask({ id: "one", subject: "First task" });
        assert.equal(created.ok, true);
        // A separate pair for the graph cases, so a dependency edge on one of
        // them never stands between the take and the completion under test.
        task.createTask({ id: "three", subject: "Third task" });
        task.createTask({ id: "four", subject: "Fourth task" });
        assert.equal(task.updateTask("three", { dependsOn: ["four"] }).ok, true);
        task.takeTask("one", "main");

        const refusals = {
          create_unknown_dependency: task.createTask({ subject: "Third", dependsOn: ["nope"] }),
          update_cycle: task.updateTask("four", { dependsOn: ["three"] }),
          update_unknown_task: task.updateTask("missing", { subject: "Renamed" }),
          update_self_dependency: task.updateTask("one", { dependsOn: ["one"] }),
          update_unknown_field: task.updateTask("one", { context: { handOff: {} } }),
          take_held: task.takeTask("one", "alpha"),
          take_unknown: task.takeTask("missing", "main"),
          complete_no_evidence: task.completeTaskWithOutcome("one", "main", "success", undefined, { checks: task.ALL_COMPLETION_CHECKS }),
          complete_wrong_holder: task.completeTaskWithOutcome("one", "alpha", "failed", "blocked"),
          reopen_pending: task.reopenTask("one"),
          bind_unknown_participant: task.bindTask("one", "ghost", { id: "task:1", kind: "task", resources: [] }),
          claim_unknown_task: task.applyClaimIntent({ taskId: "missing", participant: "alpha", spawnId: "s1", timestamp: 1 }),
          submit_not_held: task.applySubmissionIntent({ taskId: "one", participant: "alpha", spawnId: "s1", status: "completed", timestamp: 1 }),
          context_unknown_task: task.setTaskContext("missing", { workspacePath: "/tmp" }),
          context_bad_value: task.setTaskContext("one", { handoff: { priorFindings: [7] } }),
        };
        console.log(JSON.stringify(Object.fromEntries(Object.entries(refusals).map(([name, result]) => [
          name,
          {
            ok: result.ok ?? null,
            applied: result.applied ?? null,
            refusal: result.refusal ?? null,
            reason: result.reason ?? null,
            error: "error" in result,
            hasDetail: "detail" in result,
          },
        ]))));
        """
    )
    assert payload, "the script produced no refusals"
    for name, result in payload.items():
        assert result["refusal"], f"{name} returned no machine code: {result}"
        assert result["reason"], f"{name} returned no reason: {result}"
        assert result["error"] is False, f"{name} still carries a second error field: {result}"
    assert payload["take_unknown"]["refusal"] == "unknown-task"
    assert payload["reopen_pending"]["refusal"] == "not-completed"
    assert payload["complete_no_evidence"]["refusal"] == "no-evidence"
    assert payload["take_held"]["refusal"] == "held-by-other"
    assert payload["claim_unknown_task"]["applied"] is False
    assert payload["submit_not_held"]["ok"] is False


def test_the_tool_reads_one_refusal_field(tmp_path) -> None:
    """The model-facing text is the reason, whichever operation produced it.

    Before, each of the four tools translated its own refusal payload into
    model-facing text, so a field rename was a four-place edit.
    """
    payload = run(
        """
        task.createTask({ id: "one", subject: "First task" });
        const refusals = {
          create: await task.executeTaskCreate({ subject: "Second", dependsOn: ["nope"] }),
          update: await task.executeTaskUpdate({ id: "missing", status: "in_progress" }),
          list: await task.executeTaskList({ limit: -1 }),
          get: await task.executeTaskGet({ id: "missing" }),
        };
        console.log(JSON.stringify(Object.fromEntries(Object.entries(refusals).map(([name, result]) => [
          name, { text: result.content[0].text, error: result.details.error ?? null, isError: result.isError ?? false },
        ]))));
        """
    )
    for name, result in payload.items():
        assert result["isError"] is True, name
        assert result["error"], f"{name} carried no refusal text"
        assert result["error"] == result["text"], f"{name} translated the refusal twice"
