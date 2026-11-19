"""Task content and dependency edits through the four registered tools.

Contract: features/task-tool.feature
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
        import {{ Value }} from "typebox/value";
        import {{ visibleWidth }} from "@earendil-works/pi-tui";
        import * as task from {json.dumps(ENTRY)};
        const tools = new Map();
        task.default({{
          registerTool(tool) {{ tools.set(tool.name, tool); }},
          on() {{}}, events: {{ emit() {{}} }},
        }});
        const call = async (name, params) => {{
          const tool = tools.get(name);
          assert.equal(Value.Check(tool.parameters, params), true, `${{name}} parameters are not declared`);
          const result = await tool.execute("case", params, undefined, undefined, {{}});
          assert.equal(Value.Check(tool.outputSchema, result.structuredContent), true, `${{name}} result is not declared`);
          return result;
        }};
        const checked = async (name, params) => {{
          const result = await call(name, params);
          assert.equal(result.details.ok, true, result.content[0].text);
          return result;
        }};
        const style = {{ fg: (_token, text) => text, bg: (_token, text) => text, bold: text => text }};
        const render = (name, result, expanded, width = 80) => tools.get(name).renderResult(
          result, {{ expanded, isPartial: false }}, style, {{ isError: result.isError === true }},
        ).render(width);
        {script}
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )


def test_task_rows_show_content_and_dependencies_without_holder_metadata(tmp_path: Path) -> None:
    result = run(
        r"""
        const plain = await checked("create_task", { subject: "A simple task" });
        const progress = await checked("update_task", { id: plain.details.id, status: "in_progress" });
        const collapsed = render("update_task", progress, false).join("\n");
        const expanded = render("update_task", progress, true).join("\n");
        await checked("create_task", { subject: "A prerequisite" });
        const description = "Inspect the current interaction.\nCheck the input handling and report failures.";
        const verify = "Confirm input handling works.\nCheck cancellation before acceptance.";
        const detailed = await checked("create_task", {
          subject: "Review the interaction", description, verify, dependsOn: ["a-prerequisite"],
        });
        const createCollapsed = render("create_task", detailed, false, 120).join("\n");
        const createExpanded = render("create_task", detailed, true).join("\n");
        const got = await checked("get_task", { id: detailed.details.id });
        const getExpanded = render("get_task", got, true).join("\n");
        const listed = await checked("list_tasks", {});
        const listExpanded = render("list_tasks", listed, true).join("\n");
        const operations = [["create_task", detailed], ["get_task", got], ["list_tasks", listed], ["update_task", progress]]
          .map(([name, result]) => ({
            name, display: render(name, result, false, 120).join("\n"),
            structuredTool: result.details.tool, structuredStatus: result.details.status ?? null,
          }));
        const refused = await call("get_task", { id: "missing" });
        const refusal = render("get_task", refused, true).join("\n");
        const narrowWidths = [16, 32].flatMap(width => render("get_task", got, true, width)
          .map(line => ({ width, actual: visibleWidth(line) })));
        const spec = task.TASK_ROW_SPEC(progress);
        console.log(JSON.stringify({
          collapsed, expanded, createCollapsed, createExpanded, getExpanded, listExpanded, narrowWidths, operations, refusal,
          hiddenLines: [...spec.summary, ...spec.details],
          storedHolder: task.getTask(plain.details.id).claimedBy,
          resultHolder: progress.details.task.holder,
        }));
        """,
        tmp_path,
    )
    assert result["storedHolder"] == result["resultHolder"] == "main", "ownership remains runtime evidence"
    assert "[tasks] update · #1 A simple task (in progress)" in result["collapsed"]
    for operation in result["operations"]:
        action = operation["name"].removesuffix("_task").removesuffix("_tasks")
        assert f"[tasks] {action} ·" in operation["display"]
        assert operation["structuredTool"] == operation["name"]
        assert "in_progress" not in operation["display"]
    assert result["operations"][-1]["structuredStatus"] == "in_progress"
    assert "[tasks] get not applied" in result["refusal"], "Refusals use the full shared lifecycle row"
    assert "The task does not exist." in result["refusal"]
    # Collapsed by default: each row keeps its headline and reveals its body only on expansion.
    assert "Depends on #2" not in result["createCollapsed"]
    assert "Blocked by #2" not in result["createCollapsed"]
    assert "Description:" not in result["createCollapsed"]
    assert "to expand" in result["createCollapsed"]
    assert "Depends on #2" in result["createExpanded"]
    assert "Blocked by #2" in result["createExpanded"]
    assert "Description:" in result["createExpanded"]
    assert "A prerequisite #1" not in result["createCollapsed"]
    assert "(pending, blocked)" not in result["createCollapsed"]
    assert result["hiddenLines"] == ["Required at completion: a result recording the evidence"], "requirements are visible without ownership metadata"
    assert result["collapsed"].strip() != result["expanded"].strip()
    assert "to expand" in result["collapsed"]
    assert "Required at completion" not in result["collapsed"]
    assert "Required at completion" in result["expanded"]
    assert all(item["actual"] <= item["width"] for item in result["narrowWidths"])
    assert "Depends on #2" in result["listExpanded"]
    assert "Blocked by #2" in result["listExpanded"]
    for key in ("collapsed", "expanded", "createExpanded", "getExpanded", "listExpanded"):
        assert "holder ·" not in result[key], key
        assert "HELD BY" not in result[key], key
        assert "@main" not in result[key], key
    for key in ("createExpanded", "getExpanded"):
        lines = [line.strip() for line in result[key].splitlines()]
        assert lines.count("Description:") == 1
        assert lines.count("Verify:") == 1
        assert lines.index("Description:") < lines.index("Inspect the current interaction.")
        assert lines.index("Check the input handling and report failures.") < lines.index("Verify:")
        assert lines.index("Verify:") < lines.index("Confirm input handling works.")
        assert lines.index("Check cancellation before acceptance.") < lines.index("Depends on #2")
        assert lines.count("Inspect the current interaction.") == 1
        assert lines.count("Depends on #2") == 1
        assert lines.count("Blocked by #2") == 1
        assert "(pending, blocked)" not in result[key]
        assert "verify ·" not in result[key]
    for key in ("collapsed", "expanded", "listExpanded"):
        assert "Description:" not in result[key], "Absent fields have no empty section"
        assert "Verify:" not in result[key]


def test_task_tui_uses_numbered_dependency_relations(tmp_path: Path) -> None:
    result = run(
        r"""
        const prerequisite = await checked("create_task", {
          subject: "Build database", description: "Prepare the storage layer",
        });
        const dependent = await checked("create_task", {
          subject: "Configure application",
          description: "Wire the application to storage",
          dependsOn: [prerequisite.details.id],
        });
        const documentation = await checked("create_task", {
          subject: "Document several independent storage adapters",
          description: "Explain the storage adapter choices",
        });
        const listed = await checked("list_tasks", {});
        const listCollapsed = render("list_tasks", listed, false, 100).join("\n");
        const listExpandedWide = render("list_tasks", listed, true, 100).join("\n");
        const listExpanded = render("list_tasks", listed, true, 32).join("\n");
        const narrowCollapsed = render("list_tasks", listed, false, 32).join("\n");
        const narrowExpanded = render("list_tasks", listed, true, 32).join("\n");
        const got = await checked("get_task", { id: dependent.details.id });
        const getCollapsed = render("get_task", got, false, 100).join("\n");
        const getExpanded = render("get_task", got, true, 100).join("\n");
        const createCollapsed = render("create_task", prerequisite, false, 100).join("\n");
        const createExpanded = render("create_task", prerequisite, true, 100).join("\n");
        const refused = await call("update_task", {
          id: dependent.details.id, status: "completed", outcome: "success", result: "Not started",
        });
        const refusal = render("update_task", refused, false, 100).join("\n");
        const refusalExpanded = render("update_task", refused, true, 100).join("\n");
        const invalidDependency = await call("create_task", {
          subject: "Rejected task", dependsOn: ["opaque.reference"],
        });
        const invalidDependencyRow = render("create_task", invalidDependency, false, 100).join("\n");
        const invalidDependencyExpanded = render("create_task", invalidDependency, true, 100).join("\n");
        const empty = await checked("list_tasks", { statusFilter: ["completed"] });
        const emptyRow = render("list_tasks", empty, false, 100).join("\n");
        console.log(JSON.stringify({
          ids: [prerequisite.details.id, dependent.details.id, documentation.details.id],
          listCollapsed, listExpandedWide, listExpanded, narrowCollapsed, narrowExpanded,
          getCollapsed, getExpanded, createCollapsed, createExpanded, refusal, refusalExpanded,
          narrowWidths: narrowExpanded.split("\n").map(line => visibleWidth(line)),
          invalidDependencyRow, invalidDependencyExpanded, emptyRow,
        }));
        """,
        tmp_path,
    )
    # Collapsed by default: the list row shows its count, not the task bodies.
    assert "3 tasks" in result["listCollapsed"]
    assert "to expand" in result["listCollapsed"]
    assert "#" not in result["listCollapsed"]
    assert "Build database" not in result["listCollapsed"]
    assert "#1 Build database (pending)" in result["listExpandedWide"]
    assert "#2 Configure application (pending) · Depends on #1; Blocked by #1" in result["listExpandedWide"]
    assert "Depends on #1" in result["listExpandedWide"]
    assert "Blocked by #1" in result["listExpandedWide"]
    assert "to expand" in result["narrowCollapsed"]
    narrow_expanded = " ".join(result["narrowExpanded"].split())
    assert "Document several independent storage adapters" in narrow_expanded
    assert "Depends on #1" in narrow_expanded
    assert "Blocked by #1" in narrow_expanded
    assert all(width <= 32 for width in result["narrowWidths"])
    assert "to expand" in result["getCollapsed"]
    assert "#2 Configure application (pending)" in result["getExpanded"]
    assert "Depends on #1" in result["getExpanded"]
    assert "Blocked by #1" in result["getExpanded"]
    assert "to expand" in result["createCollapsed"]
    assert "#1 Build database (pending)" in result["createExpanded"]
    assert "Configure application #2" in result["refusalExpanded"]
    assert result["ids"][1] not in result["refusalExpanded"]
    assert "to expand" in result["refusal"]
    assert "to expand" in result["invalidDependencyRow"]
    assert "dependency refers to a task that does not exist" in result["invalidDependencyExpanded"]
    assert "opaque.reference" not in result["invalidDependencyExpanded"]
    assert "reference." not in result["invalidDependencyExpanded"]
    expanded_list_text = " ".join(result["listExpanded"].split())
    assert "Document several independent storage adapters" in expanded_list_text
    assert "Wire the application to storage" not in result["listExpanded"]
    assert all(task_id not in "\n".join(
        (result["listCollapsed"], result["listExpandedWide"], result["getExpanded"], result["createExpanded"])
    ) for task_id in result["ids"])
    assert "No tasks" in result["emptyRow"]
    assert "0 tasks" not in result["emptyRow"]
    assert "to expand" not in result["emptyRow"]


def test_blocked_by_lists_only_unfinished_dependencies(tmp_path: Path) -> None:
    result = run(
        r"""
        const completed = await checked("create_task", { subject: "Build schema" });
        await checked("update_task", { id: completed.details.id, status: "in_progress" });
        await checked("update_task", {
          id: completed.details.id, status: "completed", outcome: "success", result: "Schema verified",
        });
        const pending = await checked("create_task", { subject: "Build cache" });
        await checked("create_task", {
          subject: "Wire service", dependsOn: [completed.details.id, pending.details.id],
        });
        const listed = await checked("list_tasks", {});
        console.log(JSON.stringify({
          collapsed: render("list_tasks", listed, false, 120).join("\n"),
          row: render("list_tasks", listed, true, 120).join("\n"),
        }));
        """,
        tmp_path,
    )
    assert "3 tasks" in result["collapsed"]
    assert "to expand" in result["collapsed"]
    assert "Build schema" not in result["collapsed"]
    assert "#1 Build schema (completed)" in result["row"]
    assert "#2 Build cache (pending)" in result["row"]
    assert "#3 Wire service (pending)" in result["row"]
    assert "#3 Wire service (pending) · Depends on #1, #2; Blocked by #2" in result["row"]
    assert "Blocked by #1" not in result["row"]


def test_display_numbers_follow_creation_order_and_stay_stable(tmp_path: Path) -> None:
    result = run(
        r"""
        const originalNow = Date.now;
        Date.now = () => 1_800_000_000_000;
        const zebra = await checked("create_task", { subject: "Zebra task" });
        const maple = await checked("create_task", { subject: "Maple task" });
        Date.now = originalNow;
        const firstList = await checked("list_tasks", {});
        const before = render("list_tasks", firstList, true, 120).join("\n");
        const beforeCollapsed = render("list_tasks", firstList, false, 120).join("\n");
        Date.now = () => 1_800_000_000_000;
        const aardvark = await checked("create_task", { subject: "Aardvark task" });
        Date.now = originalNow;
        const secondList = await checked("list_tasks", {});
        const after = render("list_tasks", secondList, true, 120).join("\n");
        console.log(JSON.stringify({
          before, beforeCollapsed, after,
          createdAt: [zebra, maple, aardvark].map(result => task.getTask(result.details.id).createdAt),
        }));
        """,
        tmp_path,
    )
    assert "to expand" in result["beforeCollapsed"]
    assert "Zebra task" not in result["beforeCollapsed"]
    assert "#1 Zebra task (pending)" in result["before"]
    assert "#2 Maple task (pending)" in result["before"]
    assert "#1 Zebra task (pending)" in result["after"]
    assert "#2 Maple task (pending)" in result["after"]
    assert "#3 Aardvark task (pending)" in result["after"]
    assert result["createdAt"][0] < result["createdAt"][1] < result["createdAt"][2]


def test_task_list_is_a_summary_and_task_get_returns_the_full_body(tmp_path: Path) -> None:
    result = run(
        r"""
        const description = "Implement the input handling.\nInclude cancellation and keyboard checks.";
        const created = await checked("create_task", {
          subject: "Implement interaction", description, verify: "Confirm cancellation works",
        });
        await checked("update_task", { id: created.details.id, status: "in_progress" });
        await checked("update_task", {
          id: created.details.id, status: "completed", outcome: "success", result: "Cancellation checked", verdict: "pass",
        });
        const listed = await checked("list_tasks", {});
        const got = await checked("get_task", { id: created.details.id });
        console.log(JSON.stringify({
          summary: listed.details.tasks[0],
          listText: listed.content[0].text,
          full: got.details.task,
          fullText: got.content[0].text,
        }));
        """,
        tmp_path,
    )
    assert result["summary"]["subject"] == "Implement interaction"
    assert result["summary"]["status"] == "completed"
    assert result["summary"]["dependsOn"] == []
    assert not {"description", "verify", "result", "completionVerdict"} & set(result["summary"])
    assert "Implement the input handling." not in result["listText"]
    assert result["full"]["description"] == "Implement the input handling.\nInclude cancellation and keyboard checks."
    assert result["full"]["verify"] == "Confirm cancellation works"
    assert result["full"]["result"] == "Cancellation checked"
    assert "Include cancellation and keyboard checks." in result["fullText"]


def test_updating_name_and_details_preserves_the_task_id_and_refuses_empty_names(tmp_path: Path) -> None:
    result = run(
        """
        const created = await checked("create_task", { subject: "Initial title", description: "Initial details" });
        const id = created.details.id;
        const renamed = await checked("update_task", {
          id, subject: " Updated title ", description: "Inspect the live flow before changing it.",
        });
        const beforeRejected = JSON.stringify(task.getTask(id));
        const empty = await call("update_task", { id, subject: "   ", description: "Do not keep this" });
        const oversized = await call("update_task", { id, subject: "x".repeat(70000) });
        console.log(JSON.stringify({
          id, renamed: renamed.details.task,
          emptyAccepted: empty.details.ok, oversizedAccepted: oversized.details.ok,
          unchanged: JSON.stringify(task.getTask(id)) === beforeRejected,
          renamedIdExists: task.getTask("updated-title") !== undefined,
        }));
        """,
        tmp_path,
    )
    assert result["renamed"]["id"] == result["id"] == "initial-title"
    assert result["renamed"]["subject"] == "Updated title"
    assert result["renamed"]["description"] == "Inspect the live flow before changing it."
    assert result["emptyAccepted"] is False
    assert result["oversizedAccepted"] is False
    assert result["unchanged"] is True
    assert result["renamedIdExists"] is False


def test_dependency_edits_validate_the_graph_before_recording_any_content(tmp_path: Path) -> None:
    result = run(
        """
        const prerequisite = await checked("create_task", { subject: "Prerequisite" });
        const dependent = await checked("create_task", { subject: "Dependent" });
        await checked("create_task", { subject: "Tail", dependsOn: [dependent.details.id] });
        const updated = await checked("update_task", {
          id: dependent.details.id, dependsOn: [prerequisite.details.id, prerequisite.details.id],
        });
        const early = await call("update_task", { id: dependent.details.id, status: "in_progress" });
        const capacityIds = [];
        for (let index = 0; index < 33; index += 1) {
          const capacity = await checked("create_task", { subject: `Extra ${index}` });
          capacityIds.push(capacity.details.id);
        }
        const replaced = await checked("create_task", { subject: "Replaced", description: "Original task body" });
        const replacement = await checked("create_task", { subject: "Replacement", supersedes: [replaced.details.id] });
        const rejected = [];
        for (const [id, dependsOn] of [
          [dependent.details.id, ["missing"]],
          [dependent.details.id, [dependent.details.id]],
          [replaced.details.id, [replaced.details.id]],
          [replacement.details.id, [replaced.details.id]],
          [prerequisite.details.id, ["tail"]],
          [dependent.details.id, capacityIds],
        ]) {
          const before = JSON.stringify(task.tasks);
          const receipt = await call("update_task", { id, dependsOn, description: "Invalid edit" });
          rejected.push({ ok: receipt.details.ok, unchanged: before === JSON.stringify(task.tasks) });
        }
        const aliasEdit = await checked("update_task", {
          id: "tail", dependsOn: [replaced.details.id, replacement.details.id],
        });
        const cleared = await checked("update_task", { id: "tail", dependsOn: [] });
        const clearIsClaimable = (await checked("list_tasks", { claimable: true })).details.tasks.some(item => item.id === "tail");
        await checked("update_task", { id: prerequisite.details.id, status: "in_progress" });
        await checked("update_task", {
          id: prerequisite.details.id, status: "completed", outcome: "success", result: "Prerequisite checked",
        });
        await checked("create_task", { subject: "Unfinished extra" });
        const taken = await checked("update_task", { id: dependent.details.id, status: "in_progress" });
        const activeEdit = await call("update_task", { id: dependent.details.id, dependsOn: ["unfinished-extra"] });
        await checked("update_task", {
          id: dependent.details.id, status: "completed", outcome: "success", result: "Dependent checked",
        });
        const completedEdit = await call("update_task", { id: dependent.details.id, dependsOn: ["unfinished-extra"] });
        console.log(JSON.stringify({
          edges: updated.details.task.dependsOn, blocked: updated.details.task.blockedBy,
          earlyAccepted: early.details.ok, rejected,
          aliasEdges: aliasEdit.details.task.dependsOn,
          clearedEdges: cleared.details.task.dependsOn,
          clearedBlocked: cleared.details.task.blockedBy ?? [], clearIsClaimable,
          taken: taken.details.status,
          activeEditAccepted: activeEdit.details.ok,
          completedEditAccepted: completedEdit.details.ok,
          finalEdges: task.getTask(dependent.details.id).dependsOn,
        }));
        """,
        tmp_path,
    )
    assert result["edges"] == ["prerequisite"]
    assert result["blocked"] == ["prerequisite"]
    assert result["earlyAccepted"] is False
    assert result["rejected"] == [{"ok": False, "unchanged": True}] * 6
    assert result["aliasEdges"] == ["replacement"]
    assert result["clearedEdges"] == result["clearedBlocked"] == []
    assert result["clearIsClaimable"] is True
    assert result["taken"] == "in_progress"
    assert result["activeEditAccepted"] is False
    assert result["completedEditAccepted"] is False
    assert result["finalEdges"] == ["prerequisite"]


def test_content_edits_are_recorded_when_a_status_change_is_refused(tmp_path: Path) -> None:
    """R4. Contract: features/task-tool.feature, "Content edits are recorded when a
    status change is refused".

    This test used to pin the opposite: the whole call was refused and the task
    stayed unchanged. The recorded cost of that rule was real. A session wrote a
    diagnosis through one mixed call, lost the entire evidence body to the
    refusal, resent it, and then decided the task list was not worth the round
    trips. The edit is now kept and the status is reported as the half to retry.
    """
    result = run(
        """
        const created = await checked("create_task", { subject: "Original title" });
        // A status the task set refuses: a completion by a caller that never took
        // the task, carrying no evidence either.
        const mixed = await call("update_task", {
          id: created.details.id, status: "completed", outcome: "success", subject: "Recorded title",
        });
        const after = task.getTask(created.details.id);
        console.log(JSON.stringify({
          mixedAccepted: mixed.details.ok, error: mixed.content[0].text,
          subject: after.subject, status: after.status, carriedTask: Boolean(mixed.details.task),
        }));
        """,
        tmp_path,
    )
    assert result["mixedAccepted"] is False
    # The edit stands.
    assert result["subject"] == "Recorded title"
    # The status did not, and the caller is told what to retry.
    assert result["status"] == "pending"
    assert "separate call" in result["error"]
    # What was kept travels with the refusal, so the caller does not resend it.
    assert result["carriedTask"] is True


def test_a_mixed_call_whose_content_is_refused_records_neither_half(tmp_path: Path) -> None:
    """The other half of R4: content is validated before anything is applied."""
    result = run(
        """
        const created = await checked("create_task", { subject: "Original title" });
        const mixed = await call("update_task", {
          id: created.details.id, status: "in_progress", subject: "Should not land",
          context: { nonsense: "no layer of this context owns it" },
        });
        const after = task.getTask(created.details.id);
        console.log(JSON.stringify({
          mixedAccepted: mixed.details.ok, error: mixed.content[0].text,
          subject: after.subject, status: after.status,
        }));
        """,
        tmp_path,
    )
    assert result["mixedAccepted"] is False
    assert "nonsense" in result["error"]
    assert result["subject"] == "Original title"
    assert result["status"] == "pending"


def test_a_mixed_call_whose_status_is_accepted_records_both_halves(tmp_path: Path) -> None:
    """One call is enough when neither half is refused."""
    result = run(
        """
        const created = await checked("create_task", { subject: "Original title" });
        const mixed = await checked("update_task", {
          id: created.details.id, status: "in_progress", subject: "Taken and renamed",
        });
        const after = task.getTask(created.details.id);
        console.log(JSON.stringify({ status: mixed.details.status, subject: after.subject, held: after.claimedBy }));
        """,
        tmp_path,
    )
    assert result["status"] == "in_progress"
    assert result["subject"] == "Taken and renamed"
    assert result["held"] == "main"


def test_collapsed_headline_wraps_in_full_and_keeps_the_hint_on_its_last_line(tmp_path: Path) -> None:
    """Contract: features/task-tool.feature, "Every tool result and status row collapses by default".

    A collapsed row never elides its headline. A headline wider than the row wraps
    over more lines, and the native expansion hint follows on the last line, so the
    full task name and its status stay readable.
    """
    result = run(
        r"""
        const created = await checked("create_task", {
          subject: "Remove the expand hint from the Matt Pocock row", description: "A long body.",
        });
        const done = await checked("update_task", {
          id: created.details.id, status: "completed", outcome: "success", result: "Done",
        });
        const lines = (rows) => rows.map(line => line.trim()).filter(Boolean);
        const wide = lines(render("update_task", done, false, 120));
        const narrow = lines(render("update_task", done, false, 48));
        const narrowText = narrow.join(" ").split(/\s+/).join(" ");
        console.log(JSON.stringify({
          wide, narrow, narrowText,
          narrowFirstWidth: visibleWidth(narrow[0] ?? ""),
          narrowWidths: render("update_task", done, false, 48).map(visibleWidth),
        }));
        """,
        tmp_path,
    )
    subject = "Remove the expand hint from the Matt Pocock row"
    assert len(result["wide"]) == 1, "a headline that fits keeps the hint on its line"
    assert subject in result["wide"][0]
    assert "(completed)" in result["wide"][0]
    assert "to expand" in result["wide"][0]
    assert 1 <= len(result["narrow"]) <= 3, "a narrow row wraps instead of eliding"
    assert result["narrow"][-1].endswith("to expand"), "the hint follows the wrapped headline"
    assert subject in result["narrowText"], "the full task name stays visible"
    assert result["narrowFirstWidth"] >= 40, "every line but the last wraps at the full width"
    assert "(completed)" in result["narrowText"], "the trailing status stays visible"
    assert "..." not in result["narrowText"] and "\u2026" not in result["narrowText"], "the headline is never elided"
    assert all(width <= 48 for width in result["narrowWidths"])


def test_the_model_facing_subject_is_capped_at_sixty_characters(tmp_path: Path) -> None:
    """Contract: features/discoverability.feature, "The surface states what a subject is".

    A subject names the row a reader sees. A long brief in the subject field makes
    the transcript unreadable and the derived id a sentence, so the tool refuses it
    and points at description. The store stays permissive for internal callers.
    """
    result = run(
        r"""
        const created = await call("create_task", { subject: "x".repeat(61), description: "Detail" });
        const updated = await call("update_task", { id: "task", subject: "y".repeat(61) });
        const allowed = await call("create_task", { subject: "x".repeat(60) });
        console.log(JSON.stringify({
          createdOk: created.details.ok, createdText: created.content[0].text,
          updatedOk: updated.details.ok, updatedText: updated.content[0].text,
          allowedOk: allowed.details.ok,
        }));
        """,
        tmp_path,
    )
    assert result["createdOk"] is False
    assert "60" in str(result["createdText"]) and "description" in str(result["createdText"])
    assert result["updatedOk"] is False
    assert "60" in str(result["updatedText"])
    assert result["allowedOk"] is True, "60 characters is accepted"
