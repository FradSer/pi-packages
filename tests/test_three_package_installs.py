"""The three packages as four real installs, driven through a real `pi` process.

Success criteria 1 and 2 of the three-package split. Everything asserted here is
observed in a live process: the tool surface comes from the host's own registry,
and the state-machine values come from real tool executions whose results the
scripted provider read back out of the transcript. No assertion is about how a
model would phrase a turn, and nothing needs credentials — the only thing replaced
is the model.

Determinism comes from `support/scripted.ts`. Credibility comes from the fact that
the tool calls, schema validation, the coordinator seam and the tasks's own
refusals are all the shipping code paths.
"""

from __future__ import annotations

import sys
import json
import subprocess
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "e2e" / "support"))

from harness import PROBE, REPO, Run, isolated_environment, loaded_entries, run_install  # noqa: E402

SAVED_NAME = "saved-scout"
SAVED_DEFINITION = (
    "---\nname: saved-scout\ndescription: Local persistence probe\ntools: []\n"
    "---\nRead only the supplied evidence\n"
)


def seed_definition(tmp_path: Path, scope: str) -> Path:
    """Act as the fixture user before invoking any model-facing tool."""
    base = tmp_path / "agent" / "agents" if scope == "user" else tmp_path / ".pi" / "agents"
    directory = base / (f"{SAVED_NAME}.local" if scope == "project-local" else SAVED_NAME)
    directory.mkdir(parents=True, exist_ok=True)
    definition = directory / "agent.md"
    definition.write_text(SAVED_DEFINITION, encoding="utf-8")
    return definition

# The tools each package owns, and the harness's own probe, which is not one of them.
INTENT = ("agent_start", "agent_input", "agent_stop", "agent_inspect", "agent_list")
SUBAGENT_TOOLS = INTENT + ("subagents_enable",)
TASK_TOOLS = ("create_task", "get_task", "list_tasks", "update_task")
COORDINATION = SUBAGENT_TOOLS + TASK_TOOLS + ("message",)

# What each install must expose. Read as a table so a package gaining or losing a
# tool is a one-line change with a test attached, not a silent drift.
EXPECTED_SURFACE: dict[tuple[str, ...], tuple[str, ...]] = {
    ("subagents",): SUBAGENT_TOOLS,
    ("tasks",): TASK_TOOLS,
    ("subagents", "tasks"): SUBAGENT_TOOLS + TASK_TOOLS,
    ("agent-teams",): SUBAGENT_TOOLS + TASK_TOOLS + ("message",),
}

# A child is live between its start and its confirmed stop. Its state during that
# window is the runtime's to report, so a suite asserts membership, never one word.
LIVE_STATES = {"starting", "idle", "working"}


def coordination_tools(run: Run) -> list[str]:
    return [name for name in run.surfaces() if name in COORDINATION]


# ── Criterion 2: exactly one registrant per tool, per combination ──


@pytest.mark.parametrize("installed,expected", sorted(EXPECTED_SURFACE.items()))
def test_each_install_exposes_exactly_its_own_tools(
    tmp_path: Path, installed: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    run = run_install(tmp_path, list(installed))
    assert run.completed.returncode == 0, run.text
    # Asserted as a set, so a package that quietly added a second tool fails.
    assert set(coordination_tools(run)) == set(expected), run.surfaces()
    if installed == ("subagents",):
        # The loader is the only non-child tool this package owns, and selecting
        # the family must not hide it.
        assert set(run.report()["activeTools"]) & (set(INTENT) | {"agent"}) == set(INTENT)


def test_a_single_package_install_resolves_to_one_entry(tmp_path: Path) -> None:
    """The bundle is what makes one install enough; everything else must work alone."""
    assert loaded_entries(["subagents"]) == ["subagents"]
    assert loaded_entries(["tasks"]) == ["tasks"]
    # The bundle's own entry registers one tool, and its manifest is what loads the
    # other two. Resolved from the manifests, so a manifest that stopped listing a
    # dependency fails here rather than at load time.
    assert loaded_entries(["agent-teams"]) == ["agent-teams", "subagents", "tasks"]


# ── Criterion 1: each install is a working loop, not a manifest claim ──


def test_subagents_alone_runs_a_child_lifecycle(tmp_path: Path) -> None:
    """Spawn, observe and stop a child session, through the tool surface only.

    The scenario drives the four intent tools in turn: one start, one roster read,
    one inspection and one stop. `agent_start` requires a prompt, so the idle
    no-prompt startup this test used to exercise no longer has a model-facing path.
    """
    run = run_install(tmp_path, ["subagents"], scenario="agent-lifecycle")
    assert run.completed.returncode == 0, run.text

    starts = run.calls_named("agent_start")
    lists = run.calls_named("agent_list")
    inspections = run.calls_named("agent_inspect")
    stops = run.calls_named("agent_stop")
    assert [len(starts), len(lists), len(inspections), len(stops)] == [1, 1, 1, 1], run.calls()
    assert all(call["isError"] is False for call in starts + lists + inspections + stops)

    started = starts[0]["details"]
    assert run.live_children == [], "the detached RPC child must not outlive the install"
    spawn = next(event for event in run.rpc_events if event["type"] == "spawn")
    assert spawn["cwd"] == str(tmp_path)
    assert started["cwd"] == str(tmp_path)
    assert started["scope"] == "session"
    assert "source" not in started
    assert not {"persistent", "memory", "worktree", "sessionNote"}.intersection(started)
    assert "--no-session" in spawn["args"]
    assert "--no-extensions" in spawn["args"]
    extensions = [Path(spawn["args"][index + 1]).name for index, flag in enumerate(spawn["args"]) if flag == "--extension"]
    assert extensions == ["stream-recovery.ts"], "The temporary child loads only the explicit native recovery contribution"
    assert started["operation"] == "agent_start"
    assert started["disposition"] == "started"
    assert started["prompted"] is True, "intent startup always carries the prompt it accepted"
    assert started["label"] == "scout", "the display label is the only name the surface exposes"
    handle = started["session"]
    assert isinstance(handle, str) and handle.startswith("session:"), handle

    listed = lists[0]["details"]
    assert listed["count"] == 1
    assert listed["sessions"][0]["session"] == handle, "list must report the handle start returned"
    assert listed["sessions"][0]["label"] == "scout"
    assert listed["definitions"] == []
    assert not (tmp_path / "agent" / "agents").exists(), "temporary discovery/start must create no durable data"

    inspected = inspections[0]["details"]
    assert inspected["disposition"] == "inspected"
    assert inspected["sessions"][0]["session"] == handle
    assert inspected["sessions"][0]["label"] == "scout"

    stopped = stops[0]["details"]
    assert stopped["disposition"] == "stopped"
    assert stopped["session"] == handle
    assert stopped["state"] == "stopped"
    # A stopped process is not a finished task, and the receipt says so where a reader
    # would otherwise infer completion from a dead pid.
    assert "complete where its own result" in str(stopped.get("evidence", ""))


def _assert_prompted_child_closure(run: Run, pid: int) -> None:
    """The prompt reached a real child process over RPC, and it closed.

    An idle start made no model request, so this used to assert a `get_state` read.
    `agent_start` requires a prompt, so the native acknowledgement that matters now
    is the one for the prompt command: the child accepted the work it was given.
    """
    events = [event for event in run.rpc_events if event.get("pid") == pid]
    commands = [event["command"] for event in events if event["type"] == "command"]
    assert [command["type"] for command in commands] == ["prompt"], commands
    responses = [event["response"] for event in events if event["type"] == "response"]
    assert len(responses) == 1, responses
    response = responses[0]
    assert response["id"] == commands[0]["id"]
    assert response["command"] == "prompt" and response["success"] is True
    assert response["data"]["disposition"] == "started"
    assert any(event["type"] == "close" for event in events), "closure must be observed, not merely requested"


@pytest.mark.parametrize("scope", ["user", "project", "project-local"])
def test_subagents_alone_reuses_saved_sessions_without_changing_cwd(tmp_path: Path, scope: str) -> None:
    definition = seed_definition(tmp_path, scope)
    before = (definition.read_bytes(), definition.stat().st_mtime_ns)
    run = run_install(tmp_path, ["subagents"], scenario="saved-agent-lifecycle")
    assert run.completed.returncode == 0, run.text
    calls = [call for call in run.calls() if call["name"] != PROBE]
    assert [call["name"] for call in calls] == [
        "agent_list", "agent_start", "agent_list", "agent_stop", "agent_list",
        "agent_start", "agent_inspect", "agent_stop", "agent_list",
    ], [call["name"] for call in calls]
    assert all(not call["isError"] for call in calls), calls
    offline, first, live, stopped, stopped_list, reused, inspected, last_stop, final = (
        call["details"] for call in calls
    )
    for listed in (offline, stopped_list, final):
        saved_definition, = listed["definitions"]
        assert saved_definition["name"] == SAVED_NAME
        assert saved_definition["status"] == "offline"
        assert saved_definition["scope"] == scope and saved_definition["source"] == str(definition)
        assert "session" not in saved_definition
        assert saved_definition["tools"] == []
    assert offline["agents"] == []
    assert live["definitions"] == []
    live_agent, = live["sessions"]
    assert live_agent["session"] == first["session"] and live_agent["status"] in LIVE_STATES
    for listed, receipt in ((stopped_list, first), (final, reused)):
        current, = listed["sessions"]
        assert current["session"] == receipt["session"] and current["status"] == "stopped"
    for receipt in (first, reused):
        assert receipt["scope"] == scope and receipt["source"] == str(definition)
        assert receipt["grant"] == ["agent_memory"], "disk identity always receives capability Memory"
        assert not {"persistent", "memory", "worktree", "sessionNote"}.intersection(receipt)
        assert receipt["cwd"] == str(tmp_path)
    assert first["session"] != reused["session"], "reusing saved data does not reuse a process incarnation"
    assert stopped["session"] == first["session"]
    assert inspected["sessions"][0]["session"] == last_stop["session"] == reused["session"]
    assert inspected["sessions"][0]["status"] in LIVE_STATES
    assert set(coordination_tools(run)) == set(SUBAGENT_TOOLS)
    assert run.live_children == []
    spawns = [event for event in run.rpc_events if event["type"] == "spawn"]
    assert len(spawns) == 2
    workspace = tmp_path / "agent" / "agents" / SAVED_NAME / "workspace"
    for spawn in spawns:
        _assert_prompted_child_closure(run, int(spawn["pid"]))
        assert spawn["cwd"] == str(tmp_path)
        assert "--no-session" not in spawn["args"]
        assert "--no-extensions" in spawn["args"]
        args = spawn["args"]
        extensions = [args[index + 1] for index, arg in enumerate(args) if arg == "--extension"]
        assert [Path(value).name for value in extensions] == ["stream-recovery.ts", "agent-extension.ts"]
        assert args[args.index("--tools") + 1] == "agent_memory"
        assert spawn["bindings"]["PI_SUBAGENT_PROJECT_CWD"] == str(tmp_path)
        assert spawn["bindings"]["PI_SUBAGENT_WORKSPACE_PATH"] == str(workspace)
    first_args, reused_args = (spawn["args"] for spawn in spawns)
    session_dir = Path(first_args[first_args.index("--session-dir") + 1])
    assert session_dir == Path(reused_args[reused_args.index("--session-dir") + 1])
    projects = tmp_path / "agent" / "agents" / SAVED_NAME / "projects"
    assert session_dir.is_relative_to(projects), (session_dir, projects)
    # <project slug>/parents/parent-<hash>/session: the project isolation level, the
    # parent lineage and this parent session are three directories, not two.
    relative = session_dir.relative_to(projects).parts
    assert len(relative) == 4, relative
    assert relative[1] == "parents" and relative[3] == "session"
    assert session_dir.name == "session" and session_dir.parent.name
    assert "--continue" in reused_args, "the later child must resume its private saved session"
    saved = Path(first_args[first_args.index("--session") + 1])
    assert saved.is_file() and saved.parent == session_dir, "saved fork must survive both child closures"
    records = [json.loads(line) for line in saved.read_text(encoding="utf-8").split("\n") if line]
    assert records[0]["cwd"] == str(tmp_path)
    cwds = {record.get("cwd") for record in records if "cwd" in record}
    assert cwds == {str(tmp_path)}, ("the child never leaves the project cwd", cwds)
    assert "--session" not in reused_args, (
        "the resumed incarnation continues the saved session instead of naming a second one"
    )
    assert workspace.is_dir() and not (workspace / ".git").exists()
    memory = workspace.parent / "memory"
    assert memory.is_dir() and (memory / "proposals").is_dir()
    assert (memory / "MEMORY.md").is_file() and (workspace.parent / "state.json").is_file()
    assert not (tmp_path / "agent" / "workspaces").exists()
    assert not (tmp_path / "agent" / "subagent-sessions").exists()
    assert (definition.read_bytes(), definition.stat().st_mtime_ns) == before
    if scope != "user":
        assert not (workspace.parent / "agent.md").exists(), "project data must not promote a user definition"


@pytest.mark.parametrize("scope", ["user", "project", "project-local"])
def test_offline_discovery_never_provisions_durable_data(tmp_path: Path, scope: str) -> None:
    definition = seed_definition(tmp_path, scope)
    before = {path.relative_to(tmp_path): (path.read_bytes(), path.stat().st_mtime_ns)
              for path in tmp_path.rglob("agent.md")}
    run = run_install(tmp_path, ["subagents"], scenario="offline-agent")
    assert run.completed.returncode == 0, run.text
    call = run.call("agent_list")
    assert call["isError"] is False, call
    listed = call["details"]
    assert listed["sessions"] == []
    offline, = listed["definitions"]
    assert offline["name"] == SAVED_NAME and offline["status"] == "offline"
    assert offline["scope"] == scope and offline["source"] == str(definition)
    assert "session" not in offline
    assert "sessions ·" in call["text"] and "definitions ·" in call["text"]
    assert run.rpc_events == [] and run.model_requests == [] and run.live_children == []
    data_home = tmp_path / "agent" / "agents" / SAVED_NAME
    assert not data_home.exists() if scope != "user" else sorted(data_home.iterdir()) == [definition]
    after = {path.relative_to(tmp_path): (path.read_bytes(), path.stat().st_mtime_ns)
             for path in tmp_path.rglob("agent.md")}
    assert after == before


@pytest.mark.parametrize("parameter", ["persistent", "memory", "worktree"])
@pytest.mark.parametrize("value", [False, True])
def test_install_refuses_removed_controls_without_creating_identity(
    tmp_path: Path, parameter: str, value: bool
) -> None:
    run = run_install(tmp_path, ["subagents"], scenario=f"removed-{parameter}-{str(value).lower()}")
    assert run.completed.returncode == 0, run.text
    call = run.call("agent_start")
    assert call["isError"] is True, call
    assert parameter in call["text"] and "Validation failed" in call["text"], call["text"]
    assert run.rpc_events == [] and run.model_requests == [] and run.live_children == []
    assert not (tmp_path / "agent" / "agents").exists()


def test_scripted_provider_matches_local_pi_core_types(tmp_path: Path) -> None:
    tsc = REPO / "node_modules" / ".bin" / "tsc"
    assert tsc.is_file(), "the installed local TypeScript CLI is required; do not invoke Corepack"
    result = subprocess.run(
        [str(tsc), "--noEmit", "--strict", "--skipLibCheck", "--target", "ES2022",
         "--module", "ESNext", "--moduleResolution", "bundler", "--allowImportingTsExtensions",
         "--types", "node", str(REPO / "tests" / "e2e" / "support" / "scripted.ts")],
        cwd=REPO, env=isolated_environment(tmp_path), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_scripted_provider_emits_typed_events_and_checks_resolved_json(tmp_path: Path) -> None:
    helper = (REPO / "tests" / "e2e" / "support" / "scripted.ts").as_uri()
    script = f'''
      import assert from "node:assert/strict";
      import {{ installScriptedProvider }} from {json.dumps(helper)};
      function fixture(turns, resolve) {{
        let tool, provider;
        installScriptedProvider({{
          registerTool(value) {{ tool = value; }},
          registerProvider(_name, value) {{ provider = value; }},
          getAllTools() {{ return [{{ name: "agent" }}]; }},
        }}, {{ provider: "typed-fixture", probe: "probe", turns, ...(resolve ? {{ resolve }} : {{}}) }});
        const stream = (messages = []) => provider.streamSimple(
          {{ api: "typed-fixture", provider: "typed-fixture", id: "deterministic" }}, {{ messages }});
        return {{ tool, stream }};
      }}
      const f = fixture([{{ tool: "agent", args: {{ session: "$prev.session", nested: {{ value: "$prev.value" }},
        values: ["$prev.value", {{ session: "$prev.session" }}] }} }}]);
      const pending = f.tool.execute("probe", {{}});
      assert.equal(typeof pending.then, "function");
      const probe = await pending;
      assert.deepEqual(probe.details.tools, ["agent"]);
      const result = {{ role: "toolResult", toolCallId: "before", toolName: "agent", content: [],
        isError: false, timestamp: 0, details: {{ session: "session:one:exact", value: null }} }};
      // A result before the probe is not a scripted execution. Use a custom
      // resolver to exercise JSON substitutions on the first provider turn.
      const g = fixture([{{ tool: "agent", args: {{ nested: {{ session: "$prev.session" }}, value: "$prev.value" }} }}],
        value => value === "$prev.session" ? result.details.session : value === "$prev.value" ? null : value);
      const stream = g.stream();
      const events = [];
      for await (const event of stream) events.push(event);
      assert.equal(events[0].type, "start");
      assert.equal(events.at(-1).type, "done");
      assert.equal(events.at(-1).reason, "toolUse");
      assert.deepEqual((await stream.result()).content[0].arguments,
        {{ nested: {{ session: "session:one:exact" }}, value: null }});
      const reportStream = f.stream([result]);
      const reportEvents = [];
      for await (const event of reportStream) reportEvents.push(event);
      assert.equal(reportEvents.at(-1).reason, "stop");
      const report = (await reportStream.result()).content[0].text;
      assert.ok(report.startsWith("E2E_REPORT "));
      assert.deepEqual(JSON.parse(report.slice("E2E_REPORT ".length)).calls[0].details, result.details);
      for (const invalid of [undefined, () => {{}}, 1n, NaN, new Date()]) {{
        const bad = fixture([{{ tool: "agent", args: {{ session: "$prev.session" }} }}], () => invalid);
        assert.throws(() => bad.stream(), /JSON/);
      }}
      console.log("SCRIPTED_JSON_OK");
    '''
    result = subprocess.run(["node", "--input-type=module", "--eval", script], cwd=tmp_path,
                            env=isolated_environment(tmp_path), capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SCRIPTED_JSON_OK" in result.stdout


def test_tasks_alone_runs_a_board_loop(tmp_path: Path) -> None:
    """create → list → take → complete, through the four task tools in one process."""
    run = run_install(tmp_path, ["tasks"], scenario="tasks-lifecycle")
    assert run.completed.returncode == 0, run.text

    tasks = [call for call in run.calls() if call["name"] != PROBE]
    assert [call["name"] for call in tasks] == [
        "create_task", "list_tasks", "update_task", "update_task", "list_tasks",
    ], [call["name"] for call in tasks]
    assert all(call["isError"] is False for call in tasks), [call["text"] for call in tasks]

    created, claimable, taken, delivered, final = (call["details"] for call in tasks)
    task_id = created["id"]
    assert created["status"] == "pending"
    # The later calls were handed this id by the harness reading the create result,
    # so the loop acted on the same record rather than a literal in the script.
    assert claimable["count"] == 1
    assert [task["id"] for task in claimable["tasks"]] == [task_id]
    assert taken["id"] == task_id
    assert taken["status"] == "in_progress"
    assert taken["task"]["holder"] == "main", "the caller is the holder; there is no assignee"
    assert delivered["id"] == task_id
    assert delivered["status"] == "completed"
    assert final["tasks"][0]["status"] == "completed"


def test_two_packages_integrate_and_refuse_an_overlapping_take(tmp_path: Path) -> None:
    """A resident joins, a take succeeds, and an overlapping take is refused.

    This is the property that makes a resident's self-serve take safe: whoever acts
    holds the task, and two participants cannot hold overlapping resources at once.
    Without the roster being published to the tasks, the tasks would degrade to a
    single session and the overlap would go unnoticed — which is what happened
    before the execution layer published its roster as the tasks's participant
    registry.
    """
    run = run_install(tmp_path, ["subagents", "tasks"], scenario="resident-takes", host="peer")
    assert run.completed.returncode == 0, run.text

    started = run.calls_named("agent_start")[0]["details"]
    assert started["disposition"] == "started", started
    assert started["prompted"] is True, "a start with work hands that work to the child immediately"

    # create, list, take, refused take, list.
    tasks = [call for call in run.calls() if call["name"] in TASK_TOOLS]
    assert [call["name"] for call in tasks] == [
        "create_task", "list_tasks", "update_task", "update_task", "list_tasks",
    ], [call["name"] for call in tasks]
    assert all(call["isError"] is False for call in tasks[:3]), [call["text"] for call in tasks]

    first_take = tasks[2]["details"]
    assert first_take["status"] == "in_progress"

    # The seeded task carries the same resource tag the peer's assignment holds, so
    # the take must be refused and the refusal must name the holder. A refusal that
    # did not say who blocked you is a dead end rather than a conflict.
    # Asserted on the refusal's own content rather than on the transcript's error
    # flag: the flag is the harness's channel, the refusal is the tool's contract.
    refused = tasks[3]
    assert refused["isError"] is True, refused
    assert "@peer" in refused["text"], refused["text"]
    assert "conflicts with active work" in refused["text"], refused["text"]

    # Nothing moved: the refused task is still pending and still unheld, so the
    # refusal changed nothing the next read can observe.
    listed = tasks[4]["details"]["tasks"]
    blocked = [task for task in listed if task["status"] == "pending" and "holder" not in task]
    assert len(blocked) == 1, listed
    assert f'"{blocked[0]["id"]}"' in refused["text"], (blocked[0], refused["text"])
    taken, = [task for task in listed if task["id"] == first_take["id"]]
    assert taken["holder"] == "main"


def test_bundle_exposes_all_three_packages_and_delivers_peer_mail(tmp_path: Path) -> None:
    """The bundle's whole claim: one install, three packages, and mail that arrives.

    The resident is started with a prompt, which is what gives it an open
    assignment. Mail is work-bound, so a message to a participant holding nothing
    is refused — correctly, and not a delivery failure.
    """
    run = run_install(tmp_path, ["agent-teams"], scenario="bundle", host="team")
    assert run.completed.returncode == 0, run.text
    assert set(coordination_tools(run)) == set(SUBAGENT_TOOLS + TASK_TOOLS + ("message",)), run.surfaces()

    started = run.calls_named("agent_start")[0]["details"]
    assert started["disposition"] == "started", started

    tasks = [call for call in run.calls() if call["name"] in TASK_TOOLS]
    assert [call["details"]["status"] for call in tasks] == ["pending", "in_progress", "completed"], tasks

    # Mail reached the resident the start receipt named, addressed by its exact
    # route. A route resolved by guesswork would only prove the tool exists.
    delivered = run.call("message")["details"]
    assert delivered["to"] == started["name"], delivered
    # `steered` is the delivery outcome for a live recipient with an open
    # assignment, as opposed to a queue entry or a refusal.
    assert delivered["outcome"] == "steered", delivered
    assert delivered["kind"] == "request"

    # An identity with no saved definition is refused before any spawn: a label only
    # names the display, so the same call with `label` would start a synthesised
    # role instead. That difference is what proves identity selection is real.
    refused_role = run.calls_named("agent_start")[-1]
    assert refused_role["isError"] is True, refused_role
    assert "No saved identity named no-such-role-here" in refused_role["text"], refused_role["text"]
    assert refused_role["details"]["disposition"] == "rejected", refused_role["details"]


def test_a_tool_from_an_absent_package_is_refused_not_merely_absent(tmp_path: Path) -> None:
    """The negative control for every surface assertion above.

    A harness that could not start a process, or that swallowed one, would report
    an empty surface and fail these tests for the wrong reason. So this asks the
    stronger question: with only the tasks installed, a call to the communication
    tool is *refused in the transcript*, not quietly skipped. That is what makes
    "installed alone" mean the tool is really not there, rather than that the
    scenario happened not to use it.
    """
    run = run_install(tmp_path, ["tasks"], scenario="absent-tools")
    assert run.completed.returncode == 0, run.text
    # The tasks half of the negative-control scenario ran, so the process is live
    # and a refusal is a refusal rather than a process that never started.
    assert run.calls_named("create_task"), "the scenario did not reach the tasks"
    assert set(coordination_tools(run)) == set(TASK_TOOLS), run.surfaces()
    # The other two were attempted and the host refused them by name. Asserting the
    # refusal rather than the absence of a call: the script always calls, so an
    # absence would mean the transcript was truncated rather than that the tool is
    # genuinely not installed.
    for absent in ("agent_start", "message"):
        # Every attempt, not just the first: the script calls `agent_start` and
        # `message` once each, and a scenario that skipped one would pass on a tool
        # that refused only some of the time.
        refused = run.calls_named(absent)
        assert refused, f"{absent} was never called, so nothing was refused"
        for call in refused:
            assert call["isError"] is True, call
            assert f"Tool {absent} not found" in call["text"], call["text"]
        assert absent not in coordination_tools(run)


def test_the_probe_never_counts_as_a_coordination_tool(tmp_path: Path) -> None:
    """The harness's own tool must not be mistaken for one of ours, or every
    surface assertion above would be off by one."""
    run = run_install(tmp_path, ["tasks"])
    assert PROBE in run.surfaces()
    assert PROBE not in coordination_tools(run)
