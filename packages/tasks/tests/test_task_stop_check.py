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
        let workSequence = 0;
        const performWork = async () => {{
          const toolCallId = `work-${{++workSequence}}`;
          await handlers.get("tool_execution_start")({{toolCallId, toolName:"write",args:{{path:"output",content:toolCallId}}}},ctx);
          await handlers.get("tool_execution_end")({{toolCallId,toolName:"write",result:{{content:[{{type:"text",text:"Written"}}]}},isError:false}},ctx);
        }};
        await performWork();
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
    assert "Continue in dependency order" in result["content"]
    assert "Do not complete a task to stop" in result["content"]
    assert "stay inside the user's authorized scope" in result["content"]
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
    assert len(result["available"]["entries"]) == 3
    assert result["available"]["entries"][-1]["customType"] == "pi-tasks-status"
    assert len(result["waiting"]["entries"]) == 2, "headless waiting preserves earlier entries without a passive row"
    assert result["available"]["continues"] is True
    assert result["waiting"]["continues"] is False, "blocked snapshots wait while preserving earlier entries"


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
          repairedHeld: ["missing", "wrongType"].map(id => task.getTask(id).status === "blocked"),
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
    assert result["staleStatus"] == "blocked", (
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


def test_blocked_and_foreign_work_wait_without_forced_takeover(tmp_path: Path) -> None:
    """One snapshot, one continuation, whatever the state.

    The check used to ask a second kind of round: when nothing was immediately
    claimable it requested an inspection turn of its own. That is a settlement
    round per blocked snapshot on top of the continuation, so the blocker is now
    named in the waiting reason instead and the round count is one.
    """
    result = run(
        """
        task.createTask({ id: "foreign", subject: "Other participant work" });
        task.takeTask("foreign", "alpha");
        task.createTask({ id: "blocked", subject: "Waiting on other work", dependsOn: ["foreign"] });
        task.createTask({ id: "failed", subject: "Recorded blocker" });
        task.takeTask("failed", "main");
        task.completeTaskWithOutcome("failed", "main", "failed", "Needs external access");
        // The waiting row after the continuation is a transcript row, so this
        // session drives a context that has a transcript to show it in.
        const ui = { ...ctx, hasUI: true };
        const waiting = await settle({}, ui);
        const afterInspection = await settle({}, ui);
        const again = await settle({}, ui);
        console.log(JSON.stringify({
          waitingContinues: waiting.continue ?? false,
          waitingStatus: waiting.entries[0].details.status,
          waitingContent: waiting.entries[0].content,
          inspectionContinues: afterInspection?.continue ?? false,
          inspectionStatus: afterInspection?.entries[0].details.status ?? null,
          inspectionContent: afterInspection?.entries[0].content ?? "",
          again: again ?? null,
          statuses: task.listTasks().map((record) => [record.id, record.status]),
        }));
        """,
        tmp_path,
    )
    assert result["waitingContinues"] is False, "no runnable task means no continuation"
    assert result["waitingStatus"] == "waiting"
    assert "Read get_task" in result["waitingContent"]
    assert "inspect the saved evidence" in result["waitingContent"], "a recovery hold is present, so its instruction is emitted"
    assert "blocked_by=foreign" in result["waitingContent"]
    assert "holder=alpha" in result["waitingContent"]
    assert "Waiting reason" in result["waitingContent"], "the blocker is named instead of a status slot"
    assert result["inspectionContinues"] is False, "unchanged blockers must not trigger repeated attempts"
    assert result["inspectionStatus"] is None
    assert "Other participant" in result["waitingContent"]
    assert "recovery" in result["waitingContent"].lower()
    assert result["again"] is None
    assert result["statuses"] == [["foreign", "in_progress"], ["blocked", "pending"], ["failed", "blocked"]]


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
        const inspected = await settle({}, {...ctx,hasUI:true});
        const beforeTake = {
          status: task.getTask("restored").status,
          recoveryHold: task.getTask("restored").status === "blocked",
          holder: task.getTask("restored").claimedBy ?? null,
        };
        const taken = await task.executeTaskUpdate({
          id: "restored", status: "in_progress", reason: "Inspected the saved output; no operation remains active",
        }, { env: {} });
        assert.equal(taken.details.ok, true);
        await performWork();
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
    assert result["inspectedContinues"] is False
    assert result["inspectionStatus"] == "waiting"
    assert "Blocked work" in result["content"]
    assert "recover only if that is safe" in result["content"]
    assert result["beforeTake"] == {"status": "blocked", "recoveryHold": True, "holder": None}
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
          if (i < 3) await performWork();
        }
        const handler = handlers.get("input");
        assert.equal(typeof handler, "function");
        await handler({ type: "input", source: "extension", text: "Automatic reminder" }, ctx);
        const afterReminder = await settle({}, ui);
        await handler({ type: "input", source: "interactive", text: "Continue the work" }, ctx);
        await performWork();
        const afterUser = await settle({}, ui);
        console.log(JSON.stringify({
          continuationCount: receipts.filter((receipt) => receipt?.continue === true).length,
          limitContent: receipts.find((receipt) => receipt?.entries?.[0]?.details?.status === "waiting")?.entries[0].content,
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
          await performWork();
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
        assert "no new successful tool result" in observation["reason"]
        assert "limit is reached" not in observation["content"]
        assert observation["third"] is None
        assert observation["timestampOnly"] is None
        assert observation["stateUnchanged"] is True
        assert observation["progressed"] is False
        assert observation["continuation"] == 1


def test_status_rows_share_task_labels_and_dependency_summaries(tmp_path: Path) -> None:
    result = run(
        r"""
        import { ToolExecutionComponent } from "@earendil-works/pi-coding-agent";
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
        const waitingExpanded = paint(waiting.entries[0], true);
        const statusComponent = renderers.get(waiting.entries[0].customType)(
          waiting.entries[0], { expanded: false }, style,
        );
        const clickHint = statusComponent.render(120).join("\n");
        const clickResult = statusComponent.handleMouse?.({ type: "click", button: "left", x: 5, y: 2, width: 120, height: 12 }) ?? {handled:false};
        const clickedExpanded = statusComponent.render(120).join("\n");
        const original = JSON.stringify(task.tasks);
        for (let index = 0; index < 60; index += 1) {
          task.createTask({ id: `extra-${index}`, subject: "中".repeat(1000) });
        }
        const bounded = await settle({}, ui);
        console.log(JSON.stringify({
          collapsed, expanded, waitingText, waitingExpanded, clickHint, clickResult, clickedExpanded,
          modelContent: message.content, details: message.details,
          detailBytes: Buffer.byteLength(JSON.stringify(bounded.entries[0].details), "utf8"),
          storedStatus: JSON.parse(original).first.status,
        }));
        """,
        tmp_path,
    )
    assert "[tasks] continue · 2 unfinished tasks" in result["collapsed"]
    assert "[tasks] waiting · 2 unfinished tasks" in result["waitingText"]
    assert "Reason:" not in result["waitingText"]
    assert "First task" not in result["waitingText"]
    assert "Reason: no new successful tool result" in result["waitingExpanded"]
    # The native PTY runner verifies the key; this harness has no initialized host theme.
    assert "to expand" in result["clickHint"]
    assert result["clickResult"]["handled"] is True
    assert result["clickedExpanded"] != result["clickHint"]
    assert "Reason: no new successful tool result" in result["clickedExpanded"]
    assert "Depends on #1" in result["clickedExpanded"]
    assert "Blocked by #1" in result["clickedExpanded"]
    assert "#1 First task (in progress)" in result["expanded"]
    assert "#2 Second task (pending)" in result["expanded"]
    assert "Depends on #1" in result["expanded"]
    assert "Blocked by #1" in result["expanded"]
    assert "Task status check before settlement." in result["modelContent"]
    assert "Task status check before settlement." not in result["expanded"]
    assert "Current caller" not in result["expanded"]
    assert result["details"]["tasks"][1]["dependencies"] == ["#1"]
    assert result["details"]["tasks"][1]["blockedBy"] == ["#1"]
    assert all("id" not in task for task in result["details"]["tasks"])
    assert result["storedStatus"] == "in_progress"
    assert result["detailBytes"] > 8192, "full visible titles are independent of the bounded model instructions"


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


def test_evidence_history_refreshes_waiting_without_another_continuation(tmp_path: Path) -> None:
    result = run(
        """
        task.createTask({ id: "history", subject: "Recover saved work" });
        task.takeTask("history", "main");
        const ui = { ...ctx, hasUI: true };
        const continued = await settle({}, ui);
        await settle({}, ui);
        const unchanged = await settle({}, ui);
        task.getTask("history").evidenceHistory = ["Earlier failed check"];
        const refreshed = await settle({}, ui);
        const repeated = await settle({}, ui);
        const message = refreshed?.entries[0];
        const style = { fg: (_token, text) => text, bg: (_token, text) => text, bold: text => text };
        console.log(JSON.stringify({
          continued: continued.continue, unchanged: unchanged ?? null,
          refreshed: refreshed?.continue ?? null,
          continuation: message?.details.continuation,
          history: message?.details.tasks[0].evidenceHistory,
          expanded: message ? renderers.get(message.customType)(message, { expanded: true }, style).render(120).join("\\n") : "",
          collapsed: message ? renderers.get(message.customType)(message, { expanded: false }, style).render(120).join("\\n") : "",
          repeated: repeated ?? null,
        }));
        """,
        tmp_path,
    )
    assert result["continued"] is True
    assert result["unchanged"] is None
    assert result["refreshed"] is False
    assert result["continuation"] == 1
    assert result["history"] == ["Earlier failed check"]
    assert "Previous evidence: Earlier failed check" in result["expanded"]
    assert "Earlier failed check" not in result["collapsed"]
    assert result["repeated"] is None


def test_expanded_recovery_orders_current_state_before_the_original_plan() -> None:
    result = run_node(
        f"""
        import {{ taskStatusSpec }} from {json.dumps(ENTRY)};
        console.log(JSON.stringify(taskStatusSpec({{
          remaining: 1, status: "waiting", tasks: [{{
            number: 1, subject: "Recover", status: "blocked", dependencies: [], blockedBy: [],
            blockedReason: "Access required", description: "Original work", recoveryNote: "Earlier inspection",
            handoff: {{ candidate: "Checked implementation", delta: "Saved delta", verification: "Checks passed", priorFindings: ["Earlier finding"], outstanding: ["Approval"] }},
            evidenceHistory: ["Older failed attempt"],
          }}],
        }})));
        """,
    )
    assert result["expandedSummary"] is True
    assert result["fullSummary"] is False
    assert result["summary"][1:] == [
        "Current blocker: Access required", "Candidate checked: Checked implementation", "Latest delta: Saved delta",
        "Latest verification: Checks passed", "Prior findings: Earlier finding", "Outstanding: Approval",
        "Original plan: Original work", "Previous evidence: Older failed attempt",
        "Previous recovery: Earlier inspection",
    ]


def test_status_rows_use_numbered_dependency_relations_without_storage_ids() -> None:
    """Settlement rows use the same task numbers and relation labels as tool rows."""
    result = run_node(
        f"""
        import {{ taskStatusSpec }} from {json.dumps(ENTRY)};
        console.log(JSON.stringify(taskStatusSpec({{
          remaining: 2, status: "continue", continuation: 1,
          tasks: [
            {{ number: 1, subject: "Fix the three audited defects",
               status: "pending", blockedBy: [], dependencies: [] }},
            {{ number: 2, subject: "Ship the m1 path", status: "in_progress",
               blockedBy: ["#1"], dependencies: ["#1"] }},
          ],
        }}).summary));
        """,
    )
    first = result[0]
    assert first == "- #1 Fix the three audited defects (pending)", first
    assert "fix-the-three-audited-defects" not in first, first
    assert result[1] == "- #2 Ship the m1 path (in progress) · Depends on #1; Blocked by #1"
    assert len(result) == 2


def test_a_context_only_edit_does_not_buy_another_continuation(tmp_path: Path) -> None:
    """The brief is not progress.

    A context edit records what a successor needs; it changes nothing about the
    work. Counting it as progress bought an extra automatic continuation, which is
    what the continuation allowance exists to bound. A content edit is the
    contrast that keeps this from becoming "no edit counts".
    """
    result = run(
        """
        task.createTask({ id: "briefed", subject: "Implement the feature" });
        task.takeTask("briefed", "main");
        const uiCtx = { ...ctx, hasUI: true };
        const first = await settle({}, uiCtx);
        const brief = task.updateTask("briefed", {
          context: { handoff: { delta: "Recorded what the attempt found." } },
        });
        assert.equal(brief.ok, true);
        const afterBrief = await settle({}, uiCtx);
        const duplicate = await settle({}, uiCtx);
        task.updateTask("briefed", { context: { handoff: {
          delta: "Latest saved delta", verification: "Affected checks pass", outstanding: ["Native terminal check"],
        } } });
        const refreshed = await settle({}, uiCtx);
        const renamed = task.updateTask("briefed", { subject: "Implement the feature properly" });
        assert.equal(renamed.ok, true);
        const afterRename = await settle({}, uiCtx);
        console.log(JSON.stringify({
          first: first.continue,
          afterBrief: afterBrief.continue,
          duplicate: duplicate ?? null,
          refreshed: refreshed?.continue ?? null,
          continuation: refreshed?.entries[0].details.continuation,
          handoff: refreshed?.entries[0].details.tasks[0].handoff,
          afterRename: afterRename.continue,
        }));
        """,
        tmp_path,
    )
    assert result["first"] is True
    assert result["afterBrief"] is False, "a context-only write is not task progress"
    assert result["duplicate"] is None
    assert result["refreshed"] is False, "visible handoff changes refresh waiting without another turn"
    assert result["continuation"] == 1
    assert result["handoff"]["delta"] == "Latest saved delta"
    assert result["afterRename"] is False, "a rename is metadata, not effective work"


def test_the_reminder_body_is_bounded_and_pays_only_for_what_is_present(tmp_path: Path) -> None:
    """Every line is repeated at every settlement.

    The body carried fourteen instruction lines, and one recorded session spent
    three of these messages on a single task. The instruction that is not always
    true — what a recovery hold requires — is emitted only when a hold is present,
    and the body stays short enough that this cannot grow back unnoticed.
    """
    result = run(
        """
        task.createTask({ id: "plain", subject: "Ordinary unfinished work" });
        task.takeTask("plain", "main");
        const plain = await settle();
        const plainMessage = plain.entries[0].content;
        const bodyLines = plainMessage.split("\\n").filter((line) => (
          !line.startsWith("- id=") && !/^claimable=|^Current caller=/.test(line)
        ));
        task.createTask({ id: "held", subject: "Attempted and did not stand" });
        task.takeTask("held", "main");
        task.completeTaskWithOutcome("held", "main", "failed", "Needs access");
        const withHold = await settle({}, {...ctx,hasUI:true});
        console.log(JSON.stringify({
          plainLines: bodyLines,
          holdMentionsRecovery: /Blocked work needs a stated reason/.test(withHold.entries[0].content),
        }));
        """,
        tmp_path,
    )
    lines = result["plainLines"]
    assert len(lines) <= 6, f"the reminder body stays bounded: {lines}"
    assert not any("Blocked work needs a stated reason" in line for line in lines), (
        "no recovery instruction without a recovery hold"
    )
    assert result["holdMentionsRecovery"] is True, "the instruction is emitted when a hold is present"
