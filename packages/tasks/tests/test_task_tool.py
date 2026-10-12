"""The `task` tool surface registered by @fradser/pi-tasks.

Contracts: features/task-tool.feature and features/completion-checks.feature

This loads the package's *extension entry* rather than its barrel, because the
structural claim under test is that the manifest points at a file Pi can load: a
barrel re-exports the store and exports no `default`, so a manifest pointing at
`index.ts` would fail at load time.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from task_helpers import PACKAGE, run_node, source

EXTENSION = (PACKAGE / "index.ts").as_uri()
MANIFEST = PACKAGE / "package.json"


def run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(
        f"""\
        import piTasksExtension from {json.dumps(EXTENSION)};
        import {{ executeTaskCreate, executeTaskGet, executeTaskList, executeTaskUpdate, callerIdentity, TASK_CAPABILITY_TOOLS }} from {json.dumps((PACKAGE / "index.ts").as_uri())};
        import assert from "node:assert/strict";
        import {{ Value }} from "typebox/value";
        const TASK_TOOL_NAMES = [...TASK_CAPABILITY_TOOLS];
        const tools = new Map();
        const pi = {{ registerTool: (tool) => {{
          assert.equal(tools.has(tool.name), false, `Duplicate tool registration: ${{tool.name}}`);
          tools.set(tool.name, tool);
        }}, on() {{}}, events: {{ emit() {{}} }} }};
        piTasksExtension(pi);
        const tasks = new Map();
        const ROSTER = {{ alpha: {{ name: "alpha", spawnId: "s1", status: "idle" }} }};
        import * as store from {json.dumps((PACKAGE / "index.ts").as_uri())};
        const HELD = new Map();
        store.configureTaskStore({{
          get: (name) => ROSTER[name],
          current: (name, incarnation) => {{
            const entry = ROSTER[name];
            if (!entry) return false;
            return incarnation === undefined || entry.spawnId === incarnation;
          }},
          conflicting: (resources, except) => {{
            for (const [name, held] of HELD) {{
              if (name === except) continue;
              if (store.resourcesConflict(resources, held)) return {{ ...ROSTER[name] }};
            }}
            return undefined;
          }},
          sync: (name, assignment) => {{ if (assignment) HELD.set(name, assignment.resources); else HELD.delete(name); }},
          changed: () => {{}},
        }});
        {script}
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )


# ── The manifest points at a loadable entry, not the barrel ──


def test_the_manifest_declares_a_loadable_extension_entry() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    declared = manifest["pi"]["extensions"]
    assert declared == ["./index.ts"]
    for relative in declared:
        assert (PACKAGE / relative.removeprefix("./")).is_file()
    assert "index.ts" in manifest["files"]


def test_the_extension_registers_exactly_four_tools_and_nothing_else() -> None:
    """The root index is both the library surface and the extension Pi loads.

    That is why it carries a default export. One file per package means the
    manifest names one path, and a bundle references a dependency's root index
    rather than reaching into its source — which would break whenever that
    dependency's layout or packing changed.
    """
    index = (PACKAGE / "index.ts").read_text(encoding="utf-8")
    body = (PACKAGE / "src" / "extension.ts").read_text(encoding="utf-8")
    assert 'export { default } from "./src/extension.ts"' in index
    assert "default function" in body
    # One registration call, whichever of the four tools it registers.
    assert body.count("registerTaskTools(") == 1
    # The names live in tool.ts, next to the parameters they belong to, and not
    # in the entry: a name repeated in two files is a name that can drift.
    for name in ("create_task", "get_task", "list_tasks", "update_task"):
        assert name in (PACKAGE / "src" / "tool.ts").read_text(encoding="utf-8"), name
    # No other tool's name may appear in a package that registers these four:
    # that would be a second registrant for a tool it does not own.
    assert '"message"' not in body
    assert '"agent"' not in body


# ── The action set is closed ──


def test_dependency_tools_hide_resource_locks_in_schemas_results_and_rows(tmp_path: Path) -> None:
    result = run(
        """
        const rejected = TASK_TOOL_NAMES.map((name) => {
          const schema = tools.get(name).parameters;
          const valid = name === "create_task" ? { subject: "valid" }
            : name === "list_tasks" ? {} : { id: "legacy" };
          return {
            name, hasParameter: "resources" in schema.properties,
            acceptedResourceArgument: Value.Check(schema, { ...valid, resources: ["packages/btw", "packages/kit"] }),
            promptMentionsResources: /resources/i.test(tools.get(name).description + tools.get(name).promptSnippet),
          };
        });
        const created = store.createTask({ id: "legacy", subject: "Review the interaction", resources: ["packages/btw", "packages/kit"] });
        assert.equal(created.ok, true);
        const retrieved = await tools.get("get_task").execute("get", { id: "legacy" }, undefined, undefined, {});
        const listed = await tools.get("list_tasks").execute("list", {}, undefined, undefined, {});
        const createResult = await tools.get("create_task").execute("create", { subject: "A new task" }, undefined, undefined, {});
        const createRow = store.TASK_ROW_SPEC(createResult);
        const getRow = store.TASK_ROW_SPEC(retrieved);
        console.log(JSON.stringify({
          rejected,
          legacyPreserved: store.getTask("legacy").resources,
          resultHasResources: "resources" in retrieved.details.task,
          listHasResources: listed.details.tasks.some((task) => "resources" in task),
          schemaHasResources: "resources" in tools.get("get_task").outputSchema.properties.task.properties,
          text: retrieved.content.map((part) => part.text).join("\\n"),
          rowDetails: [...createRow.details, ...getRow.details],
        }));
        """,
        tmp_path,
    )
    for tool in result["rejected"]:
        assert tool["hasParameter"] is False, tool["name"]
        assert tool["acceptedResourceArgument"] is False, tool["name"]
        assert tool["promptMentionsResources"] is False, tool["name"]
    assert result["legacyPreserved"] == ["packages/btw", "packages/kit"]
    assert result["resultHasResources"] is False
    assert result["listHasResources"] is False
    assert result["schemaHasResources"] is False
    assert "RESOURCES" not in result["text"]
    assert not any(line.startswith("resources") for line in result["rowDetails"])


def test_independent_tasks_run_in_parallel_and_a_join_waits_for_both(tmp_path: Path) -> None:
    result = run(
        """
        const call = async (name, params) => {
          const receipt = await tools.get(name).execute("c", params, undefined, undefined, {});
          return receipt;
        };
        const first = await call("create_task", { subject: "Research" });
        const second = await call("create_task", { subject: "Tests" });
        const joined = await call("create_task", { subject: "Integrate", dependsOn: [first.details.id, second.details.id] });
        const held = await Promise.all([first, second].map((result) => call("update_task", { id: result.details.id, status: "in_progress" })));
        const statesWhileWorking = store.listTasks().filter((task) => task.status === "in_progress").map((task) => task.id);
        const premature = await call("update_task", { id: joined.details.id, status: "in_progress" });
        const completed = await Promise.all([first, second].map((result) => call("update_task", {
          id: result.details.id, status: "completed", outcome: "success", result: "Work checked",
        })));
        const claimable = await call("list_tasks", { claimable: true });
        const joinTaken = await call("update_task", { id: joined.details.id, status: "in_progress" });
        const joinCompleted = await call("update_task", {
          id: joined.details.id, status: "completed", outcome: "success", result: "Integration checked",
        });
        console.log(JSON.stringify({
          held: held.map((result) => result.details.ok),
          statesWhileWorking,
          prematureAccepted: premature.details.ok,
          unfinished: store.blockedDependencies(store.getTask(joined.details.id)),
          completed: completed.map((result) => result.details.ok),
          joinClaimable: claimable.details.tasks.map((task) => task.id),
          joinTaken: joinTaken.details.ok,
          joinCompleted: joinCompleted.details.ok,
          statuses: store.listTasks().map((task) => task.status),
        }));
        """,
        tmp_path,
    )
    assert result["held"] == [True, True]
    assert result["statesWhileWorking"] == ["research", "tests"]
    assert result["prematureAccepted"] is False
    assert result["completed"] == [True, True]
    assert result["joinClaimable"] == ["integrate"]
    assert result["joinTaken"] is True and result["joinCompleted"] is True
    assert result["statuses"] == ["completed"] * 3


def test_four_tools_and_nothing_else(tmp_path: Path) -> None:
    """One tool per operation, after Claude Code's shape. The single `task` tool
    this replaced had five actions and one of them was a parameterization of
    another, so a lifecycle position had two spellings and a refusal could not
    name which call earned it."""
    result = run(
        """
        const names = [...tools.keys()];
        const granted = [...store.TASK_CAPABILITY_TOOLS];
        console.log(JSON.stringify({
          names,
          granted,
          oneParameterObjectEach: names.every((name) => typeof tools.get(name).parameters === "object"),
          noSingleTaskTool: !names.includes("task"),
        }));
        """,
        tmp_path,
    )
    assert result["names"] == ["create_task", "get_task", "list_tasks", "update_task"], (
        f"the four tools, in the order a model meets them: {result['names']}"
    )
    assert result["granted"] == result["names"], "the grantable list is the registered one"
    assert result["oneParameterObjectEach"] is True
    assert result["noSingleTaskTool"] is True, "the removed single tool must not still register"


def test_task_get_takes_an_id_and_nothing_else(tmp_path: Path) -> None:
    """A read that accepted anything else would be a write wearing a read's name."""
    result = run(
        """
        const keys = Object.keys(tools.get("get_task").parameters.properties);
        console.log(JSON.stringify({ keys, required: tools.get("get_task").parameters.required }));
        """,
        tmp_path,
    )
    assert result["keys"] == ["id"]
    assert result["required"] == ["id"]


def test_every_lifecycle_position_is_reachable_exactly_one_way(tmp_path: Path) -> None:
    """`update_task` carries a `status`, the fat field this design inherits from
    Claude Code. What it must not become is a second way in: the field routes to
    the three named store transitions rather than assigning a value, so every
    precondition still applies and each position still has one spelling."""
    result = run(
        """
        const call = (name, params) => tools.get(name).execute("c", params, undefined, undefined, {});
        const created = await call("create_task", { subject: "one route each" });
        const id = created.details.id;
        const took = await call("update_task", { id, status: "in_progress" });
        const silentTake = await call("update_task", { id, status: "in_progress" });
        const edited = await call("update_task", { id, description: "edited" });
        const noOutcome = await call("update_task", { id, status: "completed" });
        const completed = await call("update_task", { id, status: "completed", outcome: "success", result: "done" });
        const reopened = await call("update_task", { id, status: "pending" });
        const badStatus = await call("update_task", { id, status: "teleport" });
        console.log(JSON.stringify({
          statusEnum: tools.get("update_task").parameters.properties.status.enum,
          reasonDescribed: tools.get("update_task").parameters.properties.reason.description,
          took: took.details.status,
          heldByCaller: took.details.task.holder,
          secondTakeRefused: silentTake.details.ok === false,
          editedWithoutStatus: edited.details.ok,
          completionNeedsOutcome: noOutcome.details.ok === false,
          completionRefusal: noOutcome.content[0].text,
          completed: completed.details.status,
          reopened: reopened.details.status,
          badStatusRefused: badStatus.details.ok === false,
        }));
        """,
        tmp_path,
    )
    assert result["statusEnum"] == ["in_progress", "completed", "pending", "blocked"], (
        "four transitions, and `pending` is the only way back from completed"
    )
    assert "status=in_progress" in str(result["reasonDescribed"]), (
        "`reason` is documented for the take route, which is the only one that reads it. "
        "It used to be documented for reopen too, and reopen never received it."
    )
    assert result["took"] == "in_progress"
    assert result["heldByCaller"] == "main"
    assert result["secondTakeRefused"] is True, "the take precondition still applies"
    assert result["editedWithoutStatus"] is True
    assert result["completionNeedsOutcome"] is True, "a completion is a judgement, not a field assignment"
    assert "outcome is required" in str(result["completionRefusal"])
    assert result["completed"] == "completed"
    assert result["reopened"] == "pending"
    assert result["badStatusRefused"] is True, "a status outside the enum never reaches a handler"


def test_the_schema_exposes_no_assignee_or_participant_name(tmp_path: Path) -> None:
    result = run(
        """
        const checked = TASK_TOOL_NAMES.map((name) => {
          const schema = tools.get(name).parameters;
          const keys = Object.keys(schema.properties);
          const valid = name === "create_task" ? { subject: "valid task" }
            : name === "list_tasks" ? {} : { id: "valid-task" };
          return {
            name, keys,
            validAccepted: Value.Check(schema, valid),
            rejectedFields: ["assignee", "participant", "target", "action"]
              .filter((key) => !Value.Check(schema, { ...valid, [key]: "someone-else" })),
          };
        });
        console.log(JSON.stringify({ checked }));
        """,
        tmp_path,
    )
    assert len(result["checked"]) == 4
    for tool in result["checked"]:
        assert tool["validAccepted"] is True, tool["name"]
        assert tool["rejectedFields"] == ["assignee", "participant", "target", "action"], tool["name"]
        assert not set(tool["keys"]) & {"assignee", "owner", "target", "worker", "agent", "participant"}


def test_a_refusal_says_what_was_asked_and_what_is_valid(tmp_path: Path) -> None:
    """There is no action parameter to misname any more, so the two refusals a
    caller can earn by guessing are a field that does not exist and a status
    outside the enum. Each names what it wanted."""
    result = run(
        """
        const call = (name, params) => tools.get(name).execute("c", params, undefined, undefined, {});
        const dispatch = await call("update_task", { id: "t1", assign: "someone" });
        const nonsense = await call("update_task", { id: "t1", status: "teleport" });
        const listed = await call("list_tasks", {});
        console.log(JSON.stringify({
          dispatchRefused: dispatch.details.ok === false,
          dispatchText: dispatch.content[0].text,
          nonsenseRefused: nonsense.details.ok === false,
          nonsenseText: nonsense.content[0].text,
          listed: listed.content[0].text,
        }));
        """,
        tmp_path,
    )
    assert result["dispatchRefused"] is True
    for field in ("status", "subject", "description", "dependsOn", "verify", "context"):
        assert field in str(result["dispatchText"]), f"The refusal must name the supported edit field: {field}"
    assert result["nonsenseRefused"] is True
    assert "teleport" in str(result["nonsenseText"]), "the refusal quotes the status it was given"


# ── A list is bounded by the cap the caller asked for ──


def test_the_list_answers_what_can_be_finished_and_what_blocks_the_rest(tmp_path: Path) -> None:
    """The read side, through the surface a model actually uses. Without it a
    model that just finished one of a split has to attempt every remaining
    completion to learn which are still blocked."""
    result = run(
        """
        const call = (name, params) => tools.get(name).execute("c", params, undefined, undefined, {});
        await call("create_task", { subject: "Design" });
        await call("create_task", { subject: "Implement", dependsOn: ["design"] });
        await call("create_task", { subject: "Document", dependsOn: ["implement"] });
        const blocked = await call("list_tasks", {});
        await call("update_task", { id: "design", status: "in_progress" });
        await call("update_task", { id: "design", status: "completed", outcome: "success", result: "wrote the spec" });
        await call("update_task", { id: "implement", status: "in_progress" });
        const ready = await call("list_tasks", { ready: true });
        const stillBlocked = await call("list_tasks", {});
        const named = Object.fromEntries(stillBlocked.details.tasks.map((task) => [task.id, task.blockedBy ?? null]));
        console.log(JSON.stringify({
          readyIds: ready.details.tasks.map((task) => task.id),
          readyCount: ready.details.count,
          blockedBefore: Object.fromEntries(blocked.details.tasks.map((task) => [task.id, task.blockedBy ?? null])),
          blockedAfter: named,
          schemaHasBlockedBy: Boolean(tools.get("list_tasks").outputSchema.properties.task.properties.blockedBy),
          listHasReady: "ready" in tools.get("list_tasks").parameters.properties,
        }));
        """,
        tmp_path,
    )
    assert result["blockedBefore"] == {"design": None, "implement": ["design"], "document": ["implement"]}, (
        "each task says what is unfinished, so nothing has to be attempted to find out"
    )
    assert result["readyIds"] == ["implement"], "exactly the newly-unblocked, being-worked-on task"
    assert result["readyCount"] == 1
    assert result["blockedAfter"] == {"design": None, "implement": None, "document": ["implement"]}
    assert result["schemaHasBlockedBy"] is True, "and the declared result says so too"
    assert result["listHasReady"] is True


def test_the_limit_a_caller_supplied_is_the_limit_that_applies(tmp_path: Path) -> None:
    """The `limit` a caller sends is the only thing standing between a long-lived
    tasks and a tool result that is the whole context. A declared parameter that
    the tool never reads is a bound nobody has."""
    result = run(
        """
        // One of four tools, named per call. A closure bound to a single tool
        // would quietly drive the wrong operation, which is the failure the
        // single-tool surface made impossible to write.
        const tool = (name) => tools.get(name);
        const call = (name, params) => tool(name).execute("c", params, undefined, undefined, {});
        for (let i = 0; i < 60; i++) await call("create_task", { subject: `work ${i}` });
        const asked = await call("list_tasks", { limit: 3 });
        const host = await tool("list_tasks").execute("h", {}, undefined, undefined, {});
        const uncapped = await tool("list_tasks").execute("u", {}, undefined, undefined, {});
        console.log(JSON.stringify({
          askedShown: asked.details.shown,
          askedCount: asked.details.count,
          askedTruncated: asked.details.truncated,
          tasksReturned: asked.details.tasks.length,
          hostDefaultShown: host.details.shown,
          hostCeiling: store.MAX_LISTED_TASKS,
          neverUnbounded: uncapped.details.shown <= store.MAX_LISTED_TASKS,
        }));
        """,
        tmp_path,
    )
    assert result["askedShown"] == 3, "a caller's own limit is the cap that applies"
    assert result["tasksReturned"] == 3
    assert result["askedCount"] == 60, "the result still says how much the tasks holds"
    assert result["askedTruncated"] is True
    assert result["hostDefaultShown"] == int(str(result["hostCeiling"]))
    assert result["neverUnbounded"] is True


def test_a_result_carries_structured_content_a_caller_can_read(tmp_path: Path) -> None:
    """`details` was already the whole answer; a caller had to know that and read
    a text blob instead. The declared output schema is what makes the data the
    result rather than a rendering of it."""
    result = run(
        """
        // One of four tools, named per call. A closure bound to a single tool
        // would quietly drive the wrong operation, which is the failure the
        // single-tool surface made impossible to write.
        const tool = (name) => tools.get(name);
        const call = (name, params) => tool(name).execute("c", params, undefined, undefined, {});
        const results = [];
        const checkedCall = async (name, params, expectedOk) => {
          const result = await call(name, params);
          assert.equal(result.details.ok, expectedOk, `${name}: ${JSON.stringify(params)}`);
          results.push({ name, result });
          return result;
        };
        const created = await checkedCall("create_task", {
          subject: "Ship the release", verify: "Confirm the release checks pass",
        }, true);
        const id = created.details.id;
        await checkedCall("get_task", { id }, true);
        await checkedCall("get_task", { id: "missing" }, false);
        const listed = await checkedCall("list_tasks", {}, true);
        await checkedCall("list_tasks", { limit: -1 }, false);
        await checkedCall("update_task", { id, status: "in_progress" }, true);
        const refused = await checkedCall("update_task", { id, status: "in_progress" }, false);
        await checkedCall("update_task", { id, context: { handoff: { delta: "updated files" } } }, true);
        await checkedCall("get_task", { id }, true);
        await checkedCall("update_task", { id, status: "completed", outcome: "success", result: "checks pass" }, false);
        await checkedCall("update_task", { id, status: "completed", outcome: "success", result: "checks pass", verdict: "fail" }, false);
        await checkedCall("update_task", { id, status: "completed", outcome: "success", result: "checks pass", verdict: "pass" }, true);
        const dependent = await checkedCall("create_task", { subject: "Review the release", dependsOn: [id] }, true);
        await checkedCall("update_task", { id: dependent.details.id, status: "in_progress" }, true);
        await checkedCall("update_task", { id: dependent.details.id, status: "completed", outcome: "success", result: "reviewed" }, true);
        const reopened = await checkedCall("update_task", { id, status: "pending" }, true);
        await checkedCall("create_task", { subject: "Replacement release", supersedes: [id] }, true);
        const failures = results.flatMap(({ name, result }) => {
          const schema = tools.get(name).outputSchema;
          const errors = [];
          if (!schema) errors.push(`${name}: no outputSchema`);
          else if (!Value.Check(schema, result.structuredContent)) {
            errors.push(`${name}: ${JSON.stringify([...Value.Errors(schema, result.structuredContent)])}`);
          }
          if (JSON.stringify(result.structuredContent) !== JSON.stringify(result.details)) {
            errors.push(`${name}: structuredContent differs from details`);
          }
          if ((result.isError === true) !== (result.details.ok === false)) {
            errors.push(`${name}: error status differs from ok`);
          }
          return errors;
        });
        console.log(JSON.stringify({
          resultsChecked: results.length,
          failures,
          listedHasTasks: Array.isArray(listed.structuredContent?.tasks),
          listedTaskKeys: Object.keys(listed.structuredContent?.tasks?.[0] ?? {}).sort(),
          refusalIsError: refused.isError === true,
          refusalCarriesData: refused.structuredContent?.ok === false,
          withdrawn: reopened.details.withdrawn ?? [],
        }));
        """,
        tmp_path,
    )
    assert result["resultsChecked"] == 17
    assert result["failures"] == [], result["failures"]
    assert result["withdrawn"] == ["review-the-release"]
    assert result["listedHasTasks"] is True
    assert result["refusalIsError"] is True
    assert result["refusalCarriesData"] is True, "a refusal is data too, not only an error string"
    for field in ("id", "subject", "status", "dependsOn"):
        assert field in result["listedTaskKeys"], field


def test_a_cap_below_one_task_is_the_empty_list_and_a_negative_one_is_refused(tmp_path: Path) -> None:
    """A cap of `0.5` floored to zero returned an empty list that claimed to be a
    truncated one, and a negative cap was dropped as though it had never been
    sent — the same silence a parameter that does nothing produces."""
    result = run(
        """
        // One of four tools, named per call. A closure bound to a single tool
        // would quietly drive the wrong operation, which is the failure the
        // single-tool surface made impossible to write.
        const tool = (name) => tools.get(name);
        const call = (name, params) => tool(name).execute("c", params, undefined, undefined, {});
        for (let i = 0; i < 5; i++) await call("create_task", { subject: `work ${i}` });
        const zero = await call("list_tasks", { limit: 0 });
        const half = await call("list_tasks", { limit: 0.5 });
        const negative = await call("list_tasks", { limit: -5 });
        console.log(JSON.stringify({
          zeroShown: zero.details.shown,
          zeroCount: zero.details.count,
          zeroTruncated: zero.details.truncated,
          halfShown: half.details.shown,
          halfTruncated: half.details.truncated,
          negativeRefused: negative.details.ok === false,
          negativeText: negative.content[0].text,
        }));
        """,
        tmp_path,
    )
    assert result["zeroShown"] == 0, "a cap of zero is a request for no tasks, and it is honoured"
    assert result["zeroCount"] == 5, "the result still says what the tasks holds"
    assert result["zeroTruncated"] is True
    assert result["halfShown"] == 0
    assert result["halfTruncated"] is True
    assert result["negativeRefused"] is True, (
        "a negative cap is refused rather than ignored, so a caller is never told nothing about it"
    )
    assert "negative" in result["negativeText"]


def test_the_declared_result_describes_a_task_rather_than_an_untyped_bag(tmp_path: Path) -> None:
    """The consumer this exists for is a codemode script. A `task` property with
    no properties in the declared schema hands that script the same untyped bag
    the prose it replaced was."""
    result = run(
        """
        // One of four tools, named per call. A closure bound to a single tool
        // would quietly drive the wrong operation, which is the failure the
        // single-tool surface made impossible to write.
        const tool = (name) => tools.get(name);
        const call = (name, params) => tool(name).execute("c", params, undefined, undefined, {});
        const created = await call("create_task", { subject: "Ship", description: "Prepare the checked release" });
        const listed = await call("list_tasks", {});
        const schema = tools.get("list_tasks").outputSchema;
        const declaredTask = Object.keys(schema.properties.task.properties ?? {}).sort();
        const actualTask = Object.keys(created.details.task).sort();
        const declaredItem = Object.keys(schema.properties.tasks.items?.properties ?? {}).sort();
        // A projection carries only the fields a task happens to have, so the
        // declared shape is the ceiling: every field present must be named, and
        // every field the type declares must be there to be named.
        const expected = ["dependsOn", "blockedBy", "description", "holder", "id", "recoveryNote",
          "result", "status", "subject", "supersededBy", "verify", "completionVerdict"];
        console.log(JSON.stringify({
          declaredTask,
          actualTask,
          declaredItem,
          undeclaredRuntime: actualTask.filter((key) => !declaredTask.includes(key)),
          missingFromDeclaration: expected.filter((key) => !declaredTask.includes(key)),
          closedToUnknownFields: schema.properties.task.additionalProperties,
          summaryClosedToUnknownFields: schema.properties.tasks.items.additionalProperties,
          listedTaskKeys: Object.keys(listed.details.tasks[0]).sort(),
        }));
        """,
        tmp_path,
    )
    assert result["undeclaredRuntime"] == [], (
        f"a field the projection produced is missing from the declared shape: {result['undeclaredRuntime']}"
    )
    assert result["missingFromDeclaration"] == [], (
        f"the declared shape is missing fields: {result['missingFromDeclaration']}"
    )
    assert result["closedToUnknownFields"] is False
    assert result["summaryClosedToUnknownFields"] is False
    for field in ("id", "subject", "status", "dependsOn", "blockedBy", "holder"):
        assert field in result["declaredTask"], field
        assert field in result["declaredItem"], field
    assert set(result["declaredItem"]) == set(result["declaredTask"]) - {"description", "verify", "result", "completionVerdict", "failureEvidence", "evidenceHistory"}
    assert set(result["listedTaskKeys"]) == set(result["actualTask"]) - {"description"}


def test_the_tool_declares_the_reach_it_actually_has(tmp_path: Path) -> None:
    """Annotations are what a permission extension reads before it interrupts a
    user, so each one has to be a claim this surface can keep. It claims nothing
    about destructiveness: `reopen` erases the result a completion recorded, and
    `create supersedes` has no inverse verb in the closed action set."""
    result = run(
        """
        const annotations = TASK_TOOL_NAMES.map((name) => tools.get(name).annotations ?? null);
        console.log(JSON.stringify({ annotations }));
        """,
        tmp_path,
    )
    annotations = result["annotations"]
    assert isinstance(annotations, list) and len(annotations) == 4, "one declaration per tool"
    for declared in annotations:
        assert isinstance(declared, dict)
        assert declared["openWorldHint"] is False, "the tasks never leave this machine"
        assert declared["readOnlyHint"] is False, "they record work; they do not only report it"
        assert declared["idempotentHint"] is False, "a second create_task is a second task"
        assert "destructiveHint" not in declared, (
            "a completion is not reopenable — reopening erases its result — so no "
            "non-destructive claim is made"
        )


# ── Behaviour ──


def test_a_result_states_the_change_and_leaves_the_how_to_the_description(tmp_path: Path) -> None:
    """A result used to end with a line telling the model what to call next. It
    said nothing the declared description does not already say, and it was the
    only result line reaching the human row — so the one action whose row had a
    body had model-facing call syntax in it. Pinned because nothing referenced
    the line, which is why it survived three review rounds."""
    result = run(
        """
        // One of four tools, named per call. A closure bound to a single tool
        // would quietly drive the wrong operation, which is the failure the
        // single-tool surface made impossible to write.
        const tool = (name) => tools.get(name);
        const call = (name, params) => tool(name).execute("c", params, undefined, undefined, {});
        const created = await call("create_task", { subject: "Record the upgrade" });
        const superseded = await call("create_task", { subject: "Record it again", supersedes: ["record-the-upgrade"] });
        const taken = await call("update_task", { id: "record-it-again", status: "in_progress" });
        const description = TASK_TOOL_NAMES.map((name) => tools.get(name).description).join(" ");
        const specOf = (r) => {
          const spec = store.TASK_ROW_SPEC(r);
          return { subject: spec.subject, summary: spec.summary };
        };
        console.log(JSON.stringify({
          createText: created.content[0].text,
          createLines: created.content[0].text.split("\\n").length,
          createRow: specOf(created),
          supersedeText: superseded.content[0].text,
          supersedeRow: specOf(superseded),
          takeRow: specOf(taken),
          createDescribesSupersede: description.includes("supersedes"),
          updateDescribesEveryRoute: ["status=in_progress", "status=completed", "status=pending"]
            .every((usage) => tools.get("update_task").description.includes(usage)),
          outcomeIsEnumerated: tools.get("update_task").parameters.properties.outcome.enum.join(",") === "success,failed",
          listDescribesItsFilters: tools.get("list_tasks").description.includes("Filter by status"),
          getSaysWhyItExists: tools.get("get_task").description.includes("brief"),
          hasSnippet: TASK_TOOL_NAMES.every((name) => typeof tools.get(name).promptSnippet === "string" && tools.get(name).promptSnippet.length > 0),
        }));
        """,
        tmp_path,
    )
    text = str(result["createText"])
    assert "NEXT" not in text, "a result states what changed, not how to spell the next call"
    assert int(str(result["createLines"])) == 1
    assert text.startswith("TASK · record-the-upgrade · pending · ")
    create_row = result["createRow"]
    assert create_row["summary"] == [], (
        f"a plain creation leaves the human row with its headline alone: {create_row['summary']}"
    )
    supersede_row = result["supersedeRow"]
    assert supersede_row["summary"] == ["Replaced: Record the upgrade #1"], (
        "what a creation made obsolete is state a person wants on the row"
    )
    assert any("Required at completion:" in line for line in result["takeRow"]["summary"]), "taking work shows the completion requirements"
    assert result["createDescribesSupersede"] is True
    assert result["updateDescribesEveryRoute"] is True, (
        "the usage guide is the declared descriptions, which are in the prompt either way"
    )
    assert result["outcomeIsEnumerated"] is True
    assert result["listDescribesItsFilters"] is True
    assert result["getSaysWhyItExists"] is True
    assert result["hasSnippet"] is True


def test_the_full_lifecycle_runs_through_the_tool(tmp_path: Path) -> None:
    result = run(
        """
        // One of four tools, named per call. A closure bound to a single tool
        // would quietly drive the wrong operation, which is the failure the
        // single-tool surface made impossible to write.
        const tool = (name) => tools.get(name);
        const call = (name, params) => tool(name).execute("c", params, undefined, undefined, {});
        const created = await call("create_task", { subject: "Ship the release" });
        const id = created.details.id;
        const listed = await call("list_tasks", {});
        const taken = await call("update_task", { id, status: "in_progress" });
        const done = await call("update_task", { id, status: "completed", outcome: "success", result: "released" });
        console.log(JSON.stringify({
          created: created.details.status,
          listed: listed.details.count,
          taken: taken.details.status,
          holder: taken.details.task.holder,
          done: done.details.status,
        }));
        """,
        tmp_path,
    )
    assert result["created"] == "pending"
    assert result["listed"] == 1
    assert result["taken"] == "in_progress"
    assert result["holder"] == "main"
    assert result["done"] == "completed"


def test_list_reports_a_recovery_hold_rather_than_hiding_it(tmp_path: Path) -> None:
    result = run(
        """
        // One of four tools, named per call. A closure bound to a single tool
        // would quietly drive the wrong operation, which is the failure the
        // single-tool surface made impossible to write.
        const tool = (name) => tools.get(name);
        const call = (name, params) => tool(name).execute("c", params, undefined, undefined, {});
        const created = await call("create_task", { subject: "flaky" });
        const id = created.details.id;
        await call("update_task", { id, status: "in_progress" });
        await call("update_task", { id, status: "completed", outcome: "failed", result: "flaky upstream" });
        const listed = await call("list_tasks", {});
        const full = await call("get_task", { id });
        const claimable = await call("list_tasks", { claimable: true });
        const silent = await call("update_task", { id, status: "in_progress" });
        const spoken = await call("update_task", { id, status: "in_progress", reason: "pinned the upstream" });
        console.log(JSON.stringify({
          holdVisible: listed.details.tasks[0].status === "blocked",
          evidence: full.details.task.result,
          excludedFromClaimable: claimable.details.count === 0,
          silentRefused: silent.details.ok === false,
          spokenTaken: spoken.details.status,
        }));
        """,
        tmp_path,
    )
    assert result["holdVisible"] is True
    assert result["evidence"] == "flaky upstream"
    assert result["excludedFromClaimable"] is True
    assert result["silentRefused"] is True
    assert result["spokenTaken"] == "in_progress"


def test_completing_someone_elses_task_is_refused(tmp_path: Path) -> None:
    result = run(
        """
        // One of four tools, named per call. A closure bound to a single tool
        // would quietly drive the wrong operation, which is the failure the
        // single-tool surface made impossible to write.
        const tool = (name) => tools.get(name);
        const call = (name, params) => tool(name).execute("c", params, undefined, undefined, {});
        const created = await call("create_task", { subject: "owned elsewhere" });
        const id = created.details.id;
        await executeTaskUpdate({ id, status: "in_progress" }, { env: { PI_TASK_HOLDER: "alpha" } });
        const stolen = await call("update_task", { id, status: "completed", outcome: "success", result: "not mine" });
        console.log(JSON.stringify({
          refused: stolen.details.ok === false,
          names: stolen.content[0].text.includes("alpha"),
        }));
        """,
        tmp_path,
    )
    assert result["refused"] is True
    assert result["names"] is True


def test_a_failure_outcome_must_be_explicit(tmp_path: Path) -> None:
    result = run(
        """
        // One of four tools, named per call. A closure bound to a single tool
        // would quietly drive the wrong operation, which is the failure the
        // single-tool surface made impossible to write.
        const tool = (name) => tools.get(name);
        const call = (name, params) => tool(name).execute("c", params, undefined, undefined, {});
        const created = await call("create_task", { subject: "blocked work" });
        const id = created.details.id;
        await call("update_task", { id, status: "in_progress" });
        const prose = await call("update_task", { id, status: "completed", result: "I could not do it" });
        const stillHeld = await call("list_tasks", {});
        const explicit = await call("update_task", { id, status: "completed", outcome: "failed", result: "missing credentials" });
        console.log(JSON.stringify({
          proseRefused: prose.details.ok === false,
          guidesTowardOutcome: prose.content[0].text.includes("outcome"),
          stayedInProgress: stillHeld.details.tasks[0].status,
          explicitRecorded: explicit.details.status,
        }));
        """,
        tmp_path,
    )
    assert result["proseRefused"] is True
    assert result["guidesTowardOutcome"] is True
    assert result["stayedInProgress"] == "in_progress"
    assert result["explicitRecorded"] == "blocked"


def test_the_caller_is_derived_and_never_supplied(tmp_path: Path) -> None:
    result = run(
        """
        const asMain = callerIdentity({});
        const asParticipant = callerIdentity({ PI_TASK_HOLDER: "alpha" });
        const created = await executeTaskCreate({ subject: "identity check" });
        assert.equal(created.details.ok, true);
        const id = created.details.id;
        const suppliedIdentity = { id, status: "in_progress", participant: "someone-else", spawnId: "s9" };
        const schema = tools.get("update_task").parameters;
        const unknownIdentityRejected = !Value.Check(schema, suppliedIdentity);
        const bound = await executeTaskUpdate({ id, status: "in_progress" }, { env: { PI_TASK_HOLDER: "alpha" } });
        const byOther = await executeTaskUpdate({
          id, status: "completed", outcome: "success", result: "not my work",
        }, { env: {} });
        console.log(JSON.stringify({
          asMain, asParticipant, unknownIdentityRejected,
          boundOk: bound.details.ok,
          holder: store.getTask(id)?.claimedBy ?? null,
          otherRefused: byOther.details.ok === false,
          otherReason: byOther.content[0].text,
        }));
        """,
        tmp_path,
    )
    assert result["asMain"] == "main"
    assert result["asParticipant"] == "alpha"
    assert result["unknownIdentityRejected"] is True
    assert result["boundOk"] is True
    assert result["holder"] == "alpha"
    assert result["otherRefused"] is True
    assert "alpha" in result["otherReason"]


def test_a_published_participant_registry_is_picked_up_without_an_import(tmp_path: Path) -> None:
    """The tasks integrates with a roster it has never imported.

    `@fradser/pi-subagents` owns processes and this package owns Work, so neither
    imports the other: the roster publishes a holder registry on `globalThis` and
    the task store reads it. That is what makes installing the two together integrate
    them, and — unlike a claim at load time — it does not care which one loaded
    first.

    Driven by publishing the registry by hand rather than by loading the execution
    layer, so the assertion is about this package's side of the seam alone.
    """
    result = run_node(
        f"""
        import * as store from {json.dumps((PACKAGE / "index.ts").as_uri())};
        const HELD = new Map();
        const ROSTER = new Map([
          ["alpha", {{ name: "alpha", spawnId: "s1", status: "idle" }}],
          ["beta", {{ name: "beta", spawnId: "s2", status: "idle" }}],
        ]);
        globalThis[Symbol.for("pi.participant-registry")] = {{
          get: (name) => ROSTER.get(name),
          list: () => [...ROSTER.values()],
          sync: (name, assignment) => {{
            const participant = ROSTER.get(name);
            if (participant) participant.assignment = assignment;
            if (assignment) HELD.set(name, assignment.resources); else HELD.delete(name);
          }},
          current: (name, incarnation) => {{
            const entry = ROSTER.get(name);
            if (!entry) return false;
            return incarnation === undefined || entry.spawnId === incarnation;
          }},
        }};
        store.createTask({{ id: "ledger", subject: "Ledger row", resources: ["ledger"] }});
        store.createTask({{ id: "ledger-child", subject: "Ledger detail", resources: ["ledger/detail"] }});
        store.createTask({{ id: "widget", subject: "Widget spacing", resources: ["widget"] }});
        const first = store.takeTask("ledger", "alpha");
        const overlapping = store.takeTask("ledger-child", "beta");
        const unrelated = store.takeTask("widget", "beta");
        console.log(JSON.stringify({{
          coordinated: store.isCoordinated(),
          taken: first.ok === true,
          holder: first.ok ? (first.task.claimedBy ?? first.task.holder) : null,
          // The registry's holder holds "ledger", so an overlapping take is refused
          // — by this package's own conflict primitive, over a holder it never saw.
          overlapRefused: overlapping.ok === false,
          overlapRefusal: overlapping.ok ? null : overlapping.refusal,
          overlapDetail: overlapping.ok ? null : overlapping.detail,
          unrelatedTaken: unrelated.ok === true,
          // And the assignment reached the registry, not a copy this package kept.
          syncedToRegistry: HELD.get("alpha") ?? null,
        }}));
        """,
        env_overrides={"PI_TEAM_STATE_DIR": str(tmp_path)},
    )
    assert result["coordinated"] is True
    assert result["taken"] is True
    assert result["holder"] == "alpha"
    assert result["overlapRefused"] is True
    assert result["overlapRefusal"] == "resource-conflict"
    assert result["overlapDetail"] == "alpha"
    assert result["unrelatedTaken"] is True
    assert result["syncedToRegistry"] == ["ledger"]


def test_the_seam_is_one_declaration_both_sides_import() -> None:
    """The published shape is declared once, so it cannot drift.

    It used to be written out by hand on each side, precisely so that neither
    package imports the other's domain, and a mirror is exactly how that stops
    matching: a field renamed on one side showed up as a silently wrong
    assignment rather than as a type error. The contract moved into pi-kit, which
    owns no consumer and is already a dependency of both, so agreement is now by
    import. This asserts that arrangement rather than comparing two copies of it.
    """
    for package in ("subagents", "tasks"):
        registry = (PACKAGE.parent / package / "src" / "participant-registry.ts")
        source_text = (
            (PACKAGE.parent / package / "src" / "store.ts").read_text(encoding="utf-8")
            if package == "tasks"
            else registry.read_text(encoding="utf-8")
        )
        if package == "tasks":
            # store.ts reaches the registry through kit's resolver.
            assert "resolveParticipantRegistry" in source_text, "the tasks must resolve through the shared contract"
        else:
            assert "publishParticipantRegistry" in source_text, "the roster must publish through the shared contract"
        # Neither side may declare a second copy of the shape.
        assert "export interface ParticipantAssignment" not in source_text, (
            f"{package} must not redeclare the shared assignment shape"
        )
    kit = (PACKAGE.parent / "kit" / "src" / "index.ts").read_text(encoding="utf-8")
    assert "export interface ParticipantAssignment" in kit, "the shared contract has one owner"
    assert "export const PARTICIPANT_REGISTRY_KEY" in kit, "the registry key has one owner"


# ── The row is what a person reads ───────────────────────────────────────


def test_the_row_is_bound_when_the_extension_loads(tmp_path: Path) -> None:
    """A row spec nothing ever supplies is a row nobody sees.

    The tool library stays TUI-free and the entry binds the geometry, so a spec
    written here and never wired would compile, pass every behavioural test, and
    leave every real session on Pi's default rendering. Asserted by loading the
    shipped entry, not by inspecting that a spec exists.
    """
    result = run_node(
        f"""
        import entry from {json.dumps(EXTENSION)};
        const tools = new Map();
        entry({{ registerTool: (tool) => tools.set(tool.name, tool), on() {{}}, events: {{ emit() {{}} }} }});
        const tool = tools.get("update_task");
        console.log(JSON.stringify({{
          registered: tool !== undefined,
          renderResult: typeof tool.renderResult,
          renderCall: typeof tool.renderCall,
          renderShell: tool.renderShell,
        }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )
    assert result["registered"] is True
    assert result["renderResult"] == "function", "the shipped entry must bind the row renderer"
    assert result["renderCall"] == "function", "an undefined call renderer takes the terminal down on repaint"
    assert result["renderShell"] == "self"


def test_the_row_spec_leads_with_the_work_not_the_id() -> None:
    """A display number names the work while storage ids stay internal."""
    result = run_node(
        f"""
        import {{ TASK_ROW_SPEC }} from {json.dumps((PACKAGE / "index.ts").as_uri())};
        const spec = TASK_ROW_SPEC({{
          content: [{{ type: "text", text: "TASK · t1 · in_progress · @main" }}],
          details: {{ id: "t1", status: "in_progress", holder: "main",
                     task: {{ subject: "Polish the login flow", dependsOn: ["t0"], holder: "main" }} }},
        }});
        console.log(JSON.stringify({{
          subject: spec.subject,
          tool: spec.tool,
          label: spec.label,
          summary: spec.summary,
          details: spec.details,
        }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": "/tmp"},
    )
    assert result["tool"] == "tasks"
    assert result["label"] == "status"
    assert "#1 Polish the login flow (in progress)" in str(result["subject"]), "the row leads with its display number and work"
    assert "t1" not in str(result["subject"]), "storage ids stay out of the visible row"
    assert any("depends" in str(d).lower() for d in result["summary"])
    assert "in progress" in str(result["subject"])
    assert "in_progress" not in str(result["subject"])


def test_a_tasks_that_could_not_be_read_says_so() -> None:
    """A task set that is empty in memory and non-empty on disk is the failure a
    model would otherwise reason about wrongly."""
    result = run_node(
        f"""
        import * as task from {json.dumps((PACKAGE / "index.ts").as_uri())};
        task.setStoreNotice("Task tasks at /tmp/tasks.json could not be read: EACCES");
        task.createTask({{ subject: "visible task" }});
        const out = await task.executeTaskList({{}});
        console.log(JSON.stringify({{ ok: out.details.ok, notice: out.details.notice ?? null }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": "/tmp"},
    )
    assert result["ok"] is True
    assert "EACCES" in str(result["notice"]), "a task set that could not be read must say so"


def test_write_failures_are_shown_and_cleared_after_recovery(tmp_path: Path) -> None:
    result = run_node(
        f"""
        import fs from "node:fs";
        import path from "node:path";
        import * as task from {json.dumps((PACKAGE / "index.ts").as_uri())};
        const handlers = new Map();
        const tools = new Map();
        task.default({{
          registerTool(tool) {{ tools.set(tool.name, tool); }},
          registerMessageRenderer() {{}},
          on(name, handler) {{ handlers.set(name, [...(handlers.get(name) ?? []), handler]); }},
          events: {{ emit() {{}} }},
        }});
        const context = {{
          cwd: process.cwd(), mode: "interactive", hasUI: true,
          sessionManager: {{ getSessionFile: () => undefined }},
        }};
        for (const handler of handlers.get("session_start")) await handler({{}}, context);
        const file = task.tasksFilePath(undefined, process.cwd());
        const directory = path.dirname(file);
        fs.mkdirSync(path.dirname(directory), {{ recursive: true }});
        fs.writeFileSync(directory, "blocks the task directory");
        const first = await tools.get("create_task").execute("first", {{ subject: "First task" }}, undefined, undefined, {{}});
        const style = {{ fg: (_token, text) => text, bg: (_token, text) => text, bold: text => text }};
        const firstRow = tools.get("create_task").renderResult(first, {{ expanded: true, isPartial: false }}, style, {{ isError: false }}).render(120).join("\\n");
        fs.unlinkSync(directory);
        const second = await tools.get("create_task").execute("second", {{ subject: "Second task" }}, undefined, undefined, {{}});
        console.log(JSON.stringify({{
          firstNotice: first.details.notice ?? null,
          rowShowsNotice: firstRow.includes("Notice: The durable task file"),
          secondNotice: second.details.notice ?? null,
          finalNotice: task.storeNotice() ?? null,
        }}));
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )
    assert "could not be written" in str(result["firstNotice"])
    assert result["rowShowsNotice"] is True
    assert result["secondNotice"] is None
    assert result["finalNotice"] is None
