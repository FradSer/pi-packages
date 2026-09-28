"""The `task` tool surface registered by @fradser/pi-tasks.

Contract: features/tool-surface.feature

This loads the package's *extension entry* rather than its barrel, because the
structural claim under test is that the manifest points at a file Pi can load: a
barrel re-exports the store and exports no `default`, so a manifest pointing at
`index.ts` would fail at load time.
"""

from __future__ import annotations

import json
from pathlib import Path

from task_helpers import PACKAGE, run_node

EXTENSION = (PACKAGE / "index.ts").as_uri()
MANIFEST = PACKAGE / "package.json"


def run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(
        f"""\
        import piTasksExtension from {json.dumps(EXTENSION)};
        import {{ executeTaskTool, callerIdentity }} from {json.dumps((PACKAGE / "index.ts").as_uri())};
        const tools = new Map();
        const pi = {{ registerTool: (tool) => tools.set(tool.name, tool), on() {{}}, events: {{ emit() {{}} }} }};
        piTasksExtension(pi);
        const tasks = new Map();
        const ROSTER = {{ alpha: {{ name: "alpha", spawnId: "s1", status: "idle" }} }};
        import * as store from {json.dumps((PACKAGE / "index.ts").as_uri())};
        const HELD = new Map();
        store.configureBoardStore({{
          get: (name) => ROSTER[name],
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


def test_the_extension_registers_exactly_one_tool_and_nothing_else() -> None:
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
    assert body.count("registerTaskTool(") == 1
    # No other tool's name may appear in a package that registers one tool: that
    # would be a second registrant for a tool it does not own.
    assert '"message"' not in body
    assert '"agent"' not in body


# ── The action set is closed ──


def test_the_action_set_is_exactly_five_actions() -> None:
    params = run_node(
            f"""
            import {{ TASK_TOOL_PARAMS }} from {json.dumps((PACKAGE / "index.ts").as_uri())};
            console.log(JSON.stringify(TASK_TOOL_PARAMS.properties.action.enum));
            """,
            env_overrides={"PI_CODING_AGENT_DIR": "/tmp"},
    )
    assert params == ["create", "list", "update", "complete", "reopen"]


def test_the_schema_exposes_no_assignee_or_participant_name(tmp_path: Path) -> None:
    result = run(
        """
        const tool = tools.get("task");
        const keys = Object.keys(tool.parameters.properties);
        console.log(JSON.stringify({
          keys,
          assigneeAbsent: !keys.some((k) => /assign|owner|agent|participant|spawn/i.test(k)),
        }));
        """,
        tmp_path,
    )
    assert result["assigneeAbsent"] is True
    for key in result["keys"]:
        assert key not in {"assign", "assignee", "owner", "target", "worker", "agent"}


def test_an_unknown_action_is_refused_with_the_valid_set(tmp_path: Path) -> None:
    result = run(
        """
        const tool = tools.get("task");
        const bad = await tool.execute("1", { action: "assign", id: "t1" }, undefined, undefined, {});
        const nope = await tool.execute("2", { action: "teleport" }, undefined, undefined, {});
        console.log(JSON.stringify({
          assignError: bad.details.ok === false,
          listed: bad.content[0].text,
          unknownNames: nope.content[0].text,
        }));
        """,
        tmp_path,
    )
    assert result["assignError"] is True
    for action in ("create", "list", "update", "complete", "reopen"):
        assert action in result["listed"]
    assert "teleport" in result["unknownNames"]


# ── Behaviour ──


def test_the_full_lifecycle_runs_through_the_tool(tmp_path: Path) -> None:
    result = run(
        """
        const tool = tools.get("task");
        const call = (params) => tool.execute("c", params, undefined, undefined, {});
        const created = await call({ action: "create", subject: "Ship the release", resources: ["firmware"] });
        const id = created.details.id;
        const listed = await call({ action: "list" });
        const taken = await call({ action: "update", id, status: "in_progress" });
        const done = await call({ action: "complete", id, outcome: "success", result: "released" });
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
        const tool = tools.get("task");
        const call = (params) => tool.execute("c", params, undefined, undefined, {});
        const created = await call({ action: "create", subject: "flaky" });
        const id = created.details.id;
        await call({ action: "update", id, status: "in_progress" });
        await call({ action: "complete", id, outcome: "failed", result: "flaky upstream" });
        const listed = await call({ action: "list" });
        const claimable = await call({ action: "list", claimable: true });
        const silent = await call({ action: "update", id, status: "in_progress" });
        const spoken = await call({ action: "update", id, status: "in_progress", reason: "pinned the upstream" });
        console.log(JSON.stringify({
          holdVisible: listed.details.tasks[0].recoveryRequired === true,
          evidence: listed.details.tasks[0].result,
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
        const tool = tools.get("task");
        const call = (params) => tool.execute("c", params, undefined, undefined, {});
        const created = await call({ action: "create", subject: "owned elsewhere" });
        const id = created.details.id;
        await executeTaskTool({ action: "update", id, status: "in_progress" }, { env: { PI_TEAMMATE_WORKER_NAME: "alpha" } });
        const stolen = await call({ action: "complete", id, outcome: "success", result: "not mine" });
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
        const tool = tools.get("task");
        const call = (params) => tool.execute("c", params, undefined, undefined, {});
        const created = await call({ action: "create", subject: "blocked work" });
        const id = created.details.id;
        await call({ action: "update", id, status: "in_progress" });
        const prose = await call({ action: "complete", id, result: "I could not do it" });
        const stillHeld = await call({ action: "list" });
        const explicit = await call({ action: "complete", id, outcome: "failed", result: "missing credentials" });
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
    assert result["explicitRecorded"] == "pending"


def test_the_caller_is_derived_and_never_supplied(tmp_path: Path) -> None:
    result = run(
        """
        const asMain = callerIdentity({});
        const asWorker = callerIdentity({ PI_TEAMMATE_WORKER_NAME: "alpha" });
        const spoofed = await tools.get("task").execute(
          "c", { action: "update", id: "nope", status: "in_progress", worker: "someone-else", spawnId: "s9" },
          undefined, undefined, {},
        );
        console.log(JSON.stringify({
          asMain,
          asWorker,
          extraFieldsRefused: spoofed.details.ok === false,
        }));
        """,
        tmp_path,
    )
    assert result["asMain"] == "main"
    assert result["asWorker"] == "alpha"
    assert result["extraFieldsRefused"] is True
