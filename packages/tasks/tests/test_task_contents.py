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
    assert "[tasks] update · A simple task · in progress" in result["collapsed"]
    for operation in result["operations"]:
        action = operation["name"].removesuffix("_task").removesuffix("_tasks")
        assert f"[tasks] {action} ·" in operation["display"]
        assert operation["structuredTool"] == operation["name"]
        assert "in_progress" not in operation["display"]
    assert result["operations"][-1]["structuredStatus"] == "in_progress"
    assert "[tasks] failed ·" in result["refusal"], "Failures retain pi-kit's shared failed band"
    assert 'Task "missing" does not exist.' in result["refusal"]
    assert "depends · a-prerequisite" in result["createCollapsed"]
    assert "blocked · a-prerequisite" in result["createCollapsed"]
    assert result["hiddenLines"] == [], "holder alone does not make a task expandable"
    assert result["collapsed"].strip() == result["expanded"].strip()
    assert "ctrl+o" not in result["collapsed"]
    assert all(item["actual"] <= item["width"] for item in result["narrowWidths"])
    assert "depends · a-prerequisite" in result["listExpanded"]
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
        assert lines.index("Check cancellation before acceptance.") < lines.index("depends · a-prerequisite")
        assert lines.count("Inspect the current interaction.") == 1
        assert lines.count("depends · a-prerequisite") == 1
        assert lines.count("blocked · a-prerequisite") == 1
        assert "verify ·" not in result[key]
    for key in ("collapsed", "expanded", "listExpanded"):
        assert "Description:" not in result[key], "Absent fields have no empty section"
        assert "Verify:" not in result[key]


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


def test_status_requests_do_not_silently_discard_content_edits(tmp_path: Path) -> None:
    result = run(
        """
        const created = await checked("create_task", { subject: "Unchanged title" });
        const before = JSON.stringify(task.getTask(created.details.id));
        const mixed = await call("update_task", {
          id: created.details.id, status: "in_progress", subject: "Discarded title", dependsOn: [],
        });
        const unchanged = before === JSON.stringify(task.getTask(created.details.id));
        await checked("update_task", { id: created.details.id, subject: "Recorded title" });
        const taken = await checked("update_task", { id: created.details.id, status: "in_progress" });
        const completed = await checked("update_task", {
          id: created.details.id, status: "completed", outcome: "success", result: "Actual work checked",
        });
        console.log(JSON.stringify({
          mixedAccepted: mixed.details.ok, error: mixed.content[0].text, unchanged,
          taken: taken.details.status, completed: completed.details.status,
          storedSubject: task.getTask(created.details.id).subject,
        }));
        """,
        tmp_path,
    )
    assert result["mixedAccepted"] is False
    assert "separate" in result["error"]
    assert result["unchanged"] is True
    assert result["taken"] == "in_progress"
    assert result["completed"] == "completed"
    assert result["storedSubject"] == "Recorded title"
