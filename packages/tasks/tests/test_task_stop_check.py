"""The task settlement check through the shipped extension entry.

Contract: features/task-stop-check.feature
"""
from __future__ import annotations

import json
from pathlib import Path

from task_helpers import PACKAGE, run_node

ENTRY = (PACKAGE / "index.ts").as_uri()


def run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(
        f"""
        import assert from "node:assert/strict";
        import * as task from {json.dumps(ENTRY)};
        const handlers = new Map();
        const renderers = new Map();
        task.default({{
          registerTool() {{}},
          registerMessageRenderer(name, renderer) {{ renderers.set(name, renderer); }},
          on(name, handler) {{ handlers.set(name, handler); }},
          events: {{ emit() {{}} }},
        }});
        const ctx = {{
          cwd: process.cwd(), mode: "print", hasUI: false,
          sessionManager: {{ getSessionFile: () => undefined }},
          signal: undefined, hasPendingMessages: () => false,
        }};
        const settle = async (options = {{}}, context = ctx) => {{
          const handler = handlers.get("agent_before_settle");
          assert.equal(typeof handler, "function", "The shipping entry must install the task stop check");
          return await handler({{
            type: "agent_before_settle", outcome: "completed", entries: [], continue: false,
            context: {{ canContinue: true, contextEntries: [], contextMessages: [], llmMessages: [], pendingMessages: [] }},
            ...options,
          }}, context);
        }};
        {script}
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )


def test_in_progress_work_returns_to_model_context_before_settlement(tmp_path: Path) -> None:
    result = run(
        """
        const created = task.createTask({ id: "unfinished", subject: "Implement the feature" });
        const taken = task.takeTask("unfinished", "main");
        assert.equal(created.ok && taken.ok, true);
        const receipt = await settle();
        const message = receipt.entries.find((entry) => entry.type === "custom_message");
        console.log(JSON.stringify({
          continues: receipt.continue,
          type: message.customType,
          content: message.content,
          display: message.display,
          hasRenderer: renderers.has(message.customType),
          statusUnchanged: task.getTask("unfinished").status,
        }));
        """,
        tmp_path,
    )
    assert result["continues"] is True
    assert result["type"] == "pi-tasks-status"
    assert "unfinished" in result["content"]
    assert "in_progress" in result["content"]
    assert "Perform the unfinished work" in result["content"]
    assert "Do not mark a task completed only to stop" in result["content"]
    assert "Continue only within the user's authorized scope" in result["content"]
    assert result["display"] is True
    assert result["hasRenderer"] is True
    assert result["statusUnchanged"] == "in_progress"


def test_pi_boundary_handlers_retain_earlier_messages_and_edits(tmp_path: Path) -> None:
    """Pi replaces the entries array returned by each handler."""
    result = run(
        """
        import { ExtensionRunner } from "@earendil-works/pi-coding-agent";
        const earlierEntries = [
          { type: "custom_message", customType: "earlier-notice", content: "Keep the earlier instruction", display: false },
          { type: "context_edit", targetId: "existing-message", replacement: null },
        ];
        const earlier = {
          path: "earlier", handlers: new Map([["agent_before_settle", [() => ({ entries: earlierEntries, continue: false })]]]),
          tools: new Map(), commands: new Map(), shortcuts: new Map(), flags: new Map(),
        };
        const tasksExtension = {
          path: "tasks", handlers: new Map([["agent_before_settle", [handlers.get("agent_before_settle")]]]),
          tools: new Map(), commands: new Map(), shortcuts: new Map(), flags: new Map(),
        };
        const runner = new ExtensionRunner([earlier, tasksExtension], {}, process.cwd(), {}, {});
        const errors = [];
        runner.onError(error => errors.push(error.error));
        task.createTask({ id: "available", subject: "Available work" });
        const context = entries => ({
          canContinue: entries.length > 0, contextEntries: [], contextMessages: [], llmMessages: [], pendingMessages: [],
        });
        const available = await runner.emitBoundary({ type: "agent_before_settle", outcome: "completed" }, context);
        assert.equal(task.takeTask("available", "alpha").ok, true);
        const waiting = await runner.emitBoundary({ type: "agent_before_settle", outcome: "completed" }, context);
        console.log(JSON.stringify({
          earlierEntries,
          available: { entries: available.entries, continues: available.continue, valid: available.valid },
          waiting: { entries: waiting.entries, continues: waiting.continue, valid: waiting.valid },
          errors,
        }));
        """,
        tmp_path,
    )
    assert result["errors"] == []
    for receipt in (result["available"], result["waiting"]):
        assert receipt["valid"] is True
        assert receipt["entries"][:2] == result["earlierEntries"]
        assert len(receipt["entries"]) == 3
        assert receipt["entries"][-1]["customType"] == "pi-tasks-status"
    assert result["available"]["continues"] is True
    assert result["waiting"]["continues"] is True, "a blocker inspection also preserves earlier entries"


def test_malformed_saved_identity_does_not_disable_valid_task_reminders(tmp_path: Path) -> None:
    result = run(
        """
        const base = { dependsOn: [], resources: [], status: "pending", createdAt: 1, updatedAt: 1 };
        task.loadTasks({
          valid: { ...base, id: "valid", subject: "Valid unfinished work" },
          missing: { ...base, subject: "Saved without an id" },
          wrongType: { ...base, id: 123, subject: "Saved with a numeric id" },
        });
        const receipt = await settle();
        console.log(JSON.stringify({
          continues: receipt.continue,
          content: receipt.entries[0].content,
          taskIds: task.listTasks().map(task => task.id),
          validStatus: task.getTask("valid").status,
          repairedHeld: ["missing", "wrongType"].map(id => task.getTask(id).status === "recovery_hold"),
          notice: task.storeNotice(),
        }));
        """,
        tmp_path,
    )
    assert result["continues"] is True
    assert result["taskIds"] == ["missing", "valid", "wrongType"]
    assert "id=valid status=pending" in result["content"]
    assert result["validStatus"] == "pending"
    assert result["repairedHeld"] == [True, True]
    assert "missing" in result["notice"] and "wrongType" in result["notice"]


def test_dependencies_and_independent_work_are_reported(tmp_path: Path) -> None:
    result = run(
        """
        task.createTask({ id: "first", subject: "Design" });
        task.createTask({ id: "second", subject: "Implement", dependsOn: ["first"] });
        task.createTask({ id: "parallel", subject: "Independent work" });
        const receipt = await settle();
        const content = receipt.entries[0].content;
        console.log(JSON.stringify({ continues: receipt.continue, content }));
        """,
        tmp_path,
    )
    assert result["continues"] is True
    assert "second" in result["content"] and "blocked_by=first" in result["content"]
    assert "parallel" in result["content"]
    assert "claimable=first, parallel" in result["content"]
    assert "resources" not in result["content"]


def test_the_claimable_hint_names_exactly_what_the_store_will_let_a_caller_take(tmp_path: Path) -> None:
    """The hint, the list filter, and the take path must answer one question the
    same way.

    A task file can still name a claimant on `pending`. A take is what writes
    that field and every transition that undoes one clears it, so the record
    says the work was attempted: it restores as `recovery_hold`, and `pending`
    keeps its own meaning, which is never attempted. The hint must not offer it
    as claimable work, and must not omit work the store would hand out.
    """
    result = run(
        """
        task.loadTasks({
          stale: { id: "stale", subject: "Restored work", dependsOn: [], resources: [],
            status: "pending", claimedBy: "departed", createdAt: 1, updatedAt: 1 },
          fresh: { id: "fresh", subject: "Never attempted", dependsOn: [], resources: [],
            status: "pending", createdAt: 1, updatedAt: 1 },
          blocked: { id: "blocked", subject: "Waiting work", dependsOn: ["fresh"], resources: [],
            status: "pending", createdAt: 1, updatedAt: 1 },
        });
        const listed = await task.executeTaskList({ claimable: true });
        const receipt = await settle();
        console.log(JSON.stringify({
          staleStatus: task.getTask("stale").status,
          store: task.claimableTasks().map(item => item.id),
          listed: listed.details.tasks.map(item => item.id),
          holdNeedsReason: task.takeTask("stale", "main").refusal ?? null,
          freshTaken: task.takeTask("fresh", "main").ok,
          content: receipt.entries[0].content,
        }));
        """,
        tmp_path,
    )
    assert result["staleStatus"] == "recovery_hold", (
        "a restored record naming a claimant was attempted, so it is on hold rather than pending"
    )
    assert result["store"] == ["fresh"]
    assert result["listed"] == result["store"], "the list filter reads the store's own predicate"
    assert result["holdNeedsReason"] == "recovery-hold-needs-reason"
    assert result["freshTaken"] is True
    assert "claimable=fresh" in result["content"], "the reminder reports the work the store would let a caller take"
    assert "claimable=stale" not in result["content"]


def test_completed_and_superseded_tasks_do_not_request_continuation(tmp_path: Path) -> None:
    result = run(
        """
        task.createTask({ id: "complete", subject: "Finished work" });
        task.takeTask("complete", "main");
        assert.equal(task.completeTaskWithOutcome("complete", "main", "success", "Checked the output").ok, true);
        task.createTask({ id: "old", subject: "Obsolete work" });
        task.createTask({ id: "replacement", subject: "Replacement work", supersedes: ["old"] });
        task.takeTask("replacement", "main");
        assert.equal(task.completeTaskWithOutcome("replacement", "main", "success", "Replacement checked").ok, true);
        const receipt = await settle();
        console.log(JSON.stringify({ receipt: receipt ?? null, count: task.listTasks().length }));
        """,
        tmp_path,
    )
    assert result["receipt"] is None
    assert result["count"] == 3


def test_cancelled_failed_or_already_continuing_runs_are_not_restarted(tmp_path: Path) -> None:
    result = run(
        """
        task.createTask({ id: "unfinished", subject: "Unfinished" });
        task.takeTask("unfinished", "main");
        const receipts = [];
        for (const outcome of ["aborted", "error"]) receipts.push((await settle({ outcome })) ?? null);
        receipts.push((await settle({ continue: true })) ?? null);
        receipts.push((await settle({}, { ...ctx, hasPendingMessages: () => true })) ?? null);
        receipts.push((await settle({}, { ...ctx, signal: AbortSignal.abort() })) ?? null);
        const normal = await settle();
        console.log(JSON.stringify({ receipts, normalContinues: normal.continue, status: task.getTask("unfinished").status }));
        """,
        tmp_path,
    )
    assert result["receipts"] == [None] * 5
    assert result["normalContinues"] is True
    assert result["status"] == "in_progress"


def test_blocked_and_foreign_work_receive_one_inspection_without_forced_takeover(tmp_path: Path) -> None:
    result = run(
        """
        task.createTask({ id: "foreign", subject: "Other participant work" });
        task.takeTask("foreign", "alpha");
        task.createTask({ id: "blocked", subject: "Waiting on other work", dependsOn: ["foreign"] });
        task.createTask({ id: "failed", subject: "Recorded blocker" });
        task.takeTask("failed", "main");
        task.completeTaskWithOutcome("failed", "main", "failed", "Needs external access");
        // The waiting row after the inspection is a transcript row, so this
        // session drives a context that has a transcript to show it in.
        const ui = { ...ctx, hasUI: true };
        const waiting = await settle({}, ui);
        const afterInspection = await settle({}, ui);
        const again = await settle({}, ui);
        console.log(JSON.stringify({
          waitingContinues: waiting.continue ?? false,
          waitingStatus: waiting.entries[0].details.status,
          waitingContent: waiting.entries[0].content,
          inspectionContinues: afterInspection.continue ?? false,
          inspectionStatus: afterInspection.entries[0].details.status,
          inspectionContent: afterInspection.entries[0].content,
          again: again ?? null,
          statuses: task.listTasks().map((record) => [record.id, record.status]),
        }));
        """,
        tmp_path,
    )
    assert result["waitingContinues"] is True, "a displayed status must reach the model for inspection"
    assert result["waitingStatus"] == "inspect"
    assert "Read get_task" in result["waitingContent"]
    assert "Do not retry a failed attempt or take another participant's task" in result["waitingContent"]
    assert "blocked_by=foreign" in result["waitingContent"]
    assert "holder=alpha" in result["waitingContent"]
    assert "recovery hold" in result["waitingContent"], "the state is named in the status slot now"
    assert result["inspectionContinues"] is False, "unchanged blockers must not trigger repeated attempts"
    assert result["inspectionStatus"] == "waiting"
    assert "Other participant" in result["inspectionContent"]
    assert "recovery" in result["inspectionContent"].lower()
    assert result["again"] is None
    assert result["statuses"] == [["blocked", "pending"], ["failed", "recovery_hold"], ["foreign", "in_progress"]]


def test_a_headless_settlement_has_no_passive_entry(tmp_path: Path) -> None:
    """The passive notice is a transcript row. A session with no UI has no
    transcript to show it in, so the check returns no result on a settlement that
    cannot continue: returning one puts the row's draft over the final assistant
    text, and `pi --print` then prints nothing. The continuation result keeps its
    message in every mode, because that message is the instruction the model
    reads on the next request."""
    result = run(
        """
        task.createTask({ id: "unfinished", subject: "Implement the feature" });
        task.takeTask("unfinished", "main");
        const continuation = await settle();
        const headless = await settle({}, { ...ctx, hasUI: false });
        const withTranscript = await settle({}, { ...ctx, hasUI: true });
        console.log(JSON.stringify({
          continuationContinues: continuation.continue,
          continuationMessage: continuation.entries.some((entry) => entry.type === "custom_message"),
          headless: headless ?? null,
          withTranscriptContinues: withTranscript.continue ?? null,
          withTranscriptStatus: withTranscript.entries[0].details.status,
        }));
        """,
        tmp_path,
    )
    assert result["continuationContinues"] is True
    assert result["continuationMessage"] is True, "the instruction the model reads is kept headless"
    assert result["headless"] is None, "no transcript means no passive entry and no result"
    assert result["withTranscriptContinues"] is False
    assert result["withTranscriptStatus"] == "waiting"


def test_restored_interrupted_work_is_inspected_before_safe_recovery(tmp_path: Path) -> None:
    result = run(
        """
        task.loadTasks({ restored: {
          id: "restored", subject: "Continue the implementation", status: "in_progress", claimedBy: "main",
          dependsOn: [], resources: [], createdAt: 1, updatedAt: 1,
          result: "An implementation attempt started before the session ended",
        } });
        const inspected = await settle();
        const beforeTake = {
          status: task.getTask("restored").status,
          recoveryHold: task.getTask("restored").status === "recovery_hold",
          holder: task.getTask("restored").claimedBy ?? null,
        };
        const taken = await task.executeTaskUpdate({
          id: "restored", status: "in_progress", reason: "Inspected the saved output; no operation remains active",
        }, { env: {} });
        assert.equal(taken.details.ok, true);
        const resume = await settle();
        const completed = await task.executeTaskUpdate({
          id: "restored", status: "completed", outcome: "success", result: "Recovered output verified",
        }, { env: {} });
        const finished = await settle();
        console.log(JSON.stringify({
          inspectedContinues: inspected.continue,
          inspectionStatus: inspected.entries[0].details.status,
          content: inspected.entries[0].content,
          beforeTake,
          resumeContinues: resume.continue,
          resumeStatus: resume.entries[0].details.status,
          completed: completed.details.ok,
          finalStatus: task.getTask("restored").status,
          finished: finished ?? null,
        }));
        """,
        tmp_path,
    )
    assert result["inspectedContinues"] is True
    assert result["inspectionStatus"] == "inspect"
    assert "recovery hold" in result["content"]
    assert "only if recovery is safe" in result["content"]
    assert result["beforeTake"] == {"status": "recovery_hold", "recoveryHold": True, "holder": None}
    assert result["resumeContinues"] is True
    assert result["resumeStatus"] == "continue"
    assert result["completed"] is True
    assert result["finalStatus"] == "completed"
    assert result["finished"] is None


def test_progress_continuation_is_bounded_and_real_input_resets_it(tmp_path: Path) -> None:
    result = run(
        """
        task.createTask({ id: "unfinished", subject: "Unfinished" });
        task.takeTask("unfinished", "main");
        const receipts = [];
        // The paused row at the end of the allowance is a transcript row, so
        // these settlements run with a context that has a transcript.
        const ui = { ...ctx, hasUI: true };
        for (let i = 0; i < 6; i++) {
          receipts.push((await settle({}, ui)) ?? null);
          if (i < 3) task.updateTask("unfinished", { description: `Verified progress ${i}` });
        }
        const handler = handlers.get("input");
        assert.equal(typeof handler, "function");
        await handler({ type: "input", source: "extension", text: "Automatic reminder" }, ctx);
        const afterReminder = await settle({}, ui);
        await handler({ type: "input", source: "interactive", text: "Continue the work" }, ctx);
        const afterUser = await settle({}, ui);
        console.log(JSON.stringify({
          continuationCount: receipts.filter((receipt) => receipt?.continue === true).length,
          limitContent: receipts.find((receipt) => receipt?.entries?.[0]?.details?.status === "paused")?.entries[0].content,
          afterLimit: receipts.slice(4),
          afterReminder: afterReminder ?? null,
          afterUserContinues: afterUser.continue,
        }));
        """,
        tmp_path,
    )
    assert result["continuationCount"] == 3
    assert "limit" in result["limitContent"].lower()
    assert result["afterLimit"] == [None, None]
    assert result["afterReminder"] is None
    assert result["afterUserContinues"] is True


def test_unchanged_available_work_waits_without_exhausting_the_allowance(tmp_path: Path) -> None:
    result = run(
        """
        const observations = [];
        for (const active of [false, true]) {
          task.clearTasks();
          const handler = handlers.get("input");
          await handler({ type: "input", source: "interactive", text: "Check the tasks" }, ctx);
          task.createTask({ id: "needs-approval", subject: "Commit the changes", description: "Requires authorization" });
          task.loadTasks({ recovery: {
            id: "recovery", subject: "Inspect saved output", status: "in_progress", claimedBy: "main",
            dependsOn: [], resources: [], createdAt: 1, updatedAt: 1,
          } });
          if (active) assert.equal(task.takeTask("needs-approval", "main").ok, true);
          const before = JSON.stringify(task.tasks);
          // The waiting row between two unchanged snapshots is a transcript
          // row, so this session drives a context that has a transcript.
          const ui = { ...ctx, hasUI: true };
          const first = await settle({}, ui);
          const second = await settle({}, ui);
          const third = await settle({}, ui);
          const stateUnchanged = before === JSON.stringify(task.tasks);
          assert.equal(task.updateTask("needs-approval", { description: "Requires authorization" }).ok, true);
          task.getTask("needs-approval").updatedAt += 1;
          const timestampOnly = await settle({}, ui);
          assert.equal(task.updateTask("needs-approval", { description: "Authorization now granted for local work" }).ok, true);
          const progressed = await settle({}, ui);
          observations.push({
            active, first: first.continue, second: second.continue,
            status: second.entries[0].details.status, reason: second.entries[0].details.reason,
            content: second.entries[0].content, third: third ?? null, timestampOnly: timestampOnly ?? null,
            stateUnchanged, progressed: progressed.continue,
            continuation: progressed.entries[0].details.continuation,
          });
        }
        console.log(JSON.stringify({ observations }));
        """,
        tmp_path,
    )
    for observation in result["observations"]:
        assert observation["first"] is True
        assert observation["second"] is False
        assert observation["status"] == "waiting"
        assert "no task progress" in observation["reason"]
        assert "authorization" in observation["reason"]
        assert "limit is reached" not in observation["content"]
        assert observation["third"] is None
        assert observation["timestampOnly"] is None
        assert observation["stateUnchanged"] is True
        assert observation["progressed"] is True
        assert observation["continuation"] == 2


def test_status_rows_share_task_labels_and_dependency_summaries(tmp_path: Path) -> None:
    result = run(
        r"""
        task.createTask({ id: "first", subject: "First task" });
        task.takeTask("first", "main");
        task.createTask({ id: "second", subject: "Second task", dependsOn: ["first"] });
        const style = { fg: (_token, text) => text, bg: (_token, text) => text, bold: text => text };
        const paint = (entry, expanded) => renderers.get(entry.customType)(entry, { expanded }, style).render(120).join("\n");
        // The waiting row is a transcript row, so these settlements drive a
        // context that has a transcript to render it into.
        const ui = { ...ctx, hasUI: true };
        const first = await settle({}, ui);
        const message = first.entries[0];
        const collapsed = paint(message, false);
        const expanded = paint(message, true);
        const waiting = await settle({}, ui);
        const waitingText = paint(waiting.entries[0], false);
        const original = JSON.stringify(task.tasks);
        for (let index = 0; index < 60; index += 1) {
          task.createTask({ id: `extra-${index}`, subject: "中".repeat(1000) });
        }
        const bounded = await settle({}, ui);
        console.log(JSON.stringify({
          collapsed, expanded, waitingText,
          modelContent: message.content, details: message.details,
          detailBytes: Buffer.byteLength(JSON.stringify(bounded.entries[0].details), "utf8"),
          storedStatus: JSON.parse(original).first.status,
        }));
        """,
        tmp_path,
    )
    assert "[tasks] continue · 2 unfinished tasks" in result["collapsed"]
    assert "[tasks] waiting · 2 unfinished tasks" in result["waitingText"]
    assert "no task progress" in result["waitingText"]
    assert "First task · in progress" in result["expanded"]
    assert "Second task · pending" in result["expanded"]
    assert "depends · first" in result["expanded"]
    assert "blocked · first" in result["expanded"]
    assert "Task status check before settlement." in result["modelContent"]
    assert "Task status check before settlement." not in result["expanded"]
    assert "Current caller" not in result["expanded"]
    assert result["details"]["tasks"][1]["dependsOn"] == ["first"]
    assert result["storedStatus"] == "in_progress"
    assert result["detailBytes"] <= 8192


def test_status_reminders_supply_runnable_context_and_stay_bounded(tmp_path: Path) -> None:
    result = run(
        """
        for (let i = 0; i < 60; i++) task.createTask({ id: `task-${String(i).padStart(2, "0")}`, subject: "中".repeat(1000) });
        const receipt = await settle({ context: { canContinue: false, pendingMessages: [] } });
        console.log(JSON.stringify({
          continues: receipt.continue ?? false,
          content: receipt.entries[0].content,
          bytes: Buffer.byteLength(receipt.entries[0].content, "utf8"),
          count: receipt.entries[0].details.remaining,
        }));
        """,
        tmp_path,
    )
    assert result["continues"] is True, "the appended task message makes the transcript runnable"
    assert result["count"] == 60
    assert result["bytes"] <= 8192
    assert "omitted" in result["content"].lower()
    assert "task-00" in result["content"]


def test_a_status_row_names_the_work_once_rather_than_its_id_spelling() -> None:
    """The settlement row printed the name twice.

    A task id is derived from the subject, so the row read
    `- fix-the-thing · Fix the thing · pending`: one name in two spellings.
    Every other task row shows the name and the state. This row now matches,
    and the id stays in the tool result, where a caller acts on it. A task id
    that is not the subject's spelling is still machine data a reader may want,
    but a row is not where a caller addresses work.
    """
    result = run_node(
        f"""
        import {{ taskStatusSpec }} from {json.dumps(ENTRY)};
        console.log(JSON.stringify(taskStatusSpec({{
          remaining: 2, status: "continue", continuation: 1,
          tasks: [
            {{ id: "fix-the-three-audited-defects", subject: "Fix the three audited defects",
               status: "pending", dependsOn: [], blockedBy: [] }},
            {{ id: "m1", subject: "Ship the m1 path", status: "in_progress",
               dependsOn: ["fix-the-three-audited-defects"], blockedBy: ["fix-the-three-audited-defects"] }},
          ],
        }}).details));
        """,
    )
    first = result[0]
    assert first == "- Fix the three audited defects · pending", first
    assert "fix-the-three-audited-defects" not in first, first
    # Dependency relations still name the ids they refer to.
    assert "depends · fix-the-three-audited-defects" in result[1]
