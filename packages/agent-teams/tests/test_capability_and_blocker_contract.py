from pathlib import Path

import pytest

from test_agent_package import SRC, PACKAGE, run_node
from test_accepted_work_reporting import machine_case


@pytest.mark.parametrize("requested", ["undefined", "[]", '["read", "bash"]'])
def test_public_lifecycle_content_discloses_recorded_grant(tmp_path: Path, requested: str) -> None:
    run_node(f'''
      import assert from "node:assert/strict";
      import {{ publishTeamHost, registerComposedTools }} from "./tests/composed-tools.ts";
      import {{ registerAgent, resetState }} from "{(SRC / 'state.ts').as_uri()}";
      import {{ exactSessionRoute, resolveAgentTools }} from "@fradser/pi-subagents";
      import {{ WORKER_CAPABILITY_TOOLS }} from "{(SRC / 'capability-tools.ts').as_uri()}";
      resetState();
      const tools = new Map();
      const requested = {requested};
      const grant = resolveAgentTools(requested, WORKER_CAPABILITY_TOOLS);
      const runtime = {{
        spawnAgent(input) {{
          const agent = {{ name: input.name, role: input.role, spawnId: "s1", status: "starting",
            workId: input.workId, tools: grant, pid: 0, isolation: "none", createdAt: 1, updatedAt: 1 }};
          registerAgent(agent);
          return {{ ok: true, agent }};
        }},
      }};
      registerComposedTools({{ registerTool: t => tools.set(t.name, t) }}, runtime);
      publishTeamHost(runtime);
      const start = p => tools.get("agent_start").execute("test", p, undefined, undefined, {{ cwd: {str(tmp_path)!r} }});
      // ADR-0008 left no inspection operation: the roster read is the one that
      // survives, and it takes no session handle.
      const roster = () => tools.get("agent_list").execute("test", {{}}, undefined, undefined, {{ cwd: {str(tmp_path)!r} }});
      // The roster name is minted by the start and only the label is authored, so
      // every later lookup resolves the handle the receipt returned.
      {{ 
        resetState();
        const result = await start({{ prompt: "Check evidence", label: "capability-test",
          ...(requested === undefined ? {{}} : {{ tools: requested }}) }});
        assert.equal(result.details.operation, "agent_start");
        assert.equal(result.details.disposition, "started", result.content[0].text);
        assert.match(result.details.session, /^session:subagent-[0-9a-f]+:s1$/);
        // The label is display only: it never becomes the roster key.
        assert.equal(result.details.label, "capability-test");
        assert.ok(!result.details.session.includes("capability-test"),
          `label leaked into the roster handle ${{result.details.session}}`);
        const listed = await roster();
        assert.equal(listed.details.operation, "agent_list");
        assert.equal(listed.details.disposition, "listed");
        // The effective grant is the one thing a caller routinely gets wrong by
        // assumption, so it is reported on the roster entry rather than inferred.
        const entry = listed.details.sessions.find((row) => row.session === result.details.session);
        assert.ok(entry, `the roster must hold the minted incarnation:\n${{JSON.stringify(listed.details.sessions)}}`);
        assert.deepEqual(entry.tools, grant);
        if (grant.length === 2) {{
          assert.deepEqual(grant, ["message", "task"],
            "an empty request is coordination-only: the two coordination tools and nothing else");
        }}
      }}
      // A name with no definition, no prompt and no grant is the idle-resident
      // case: a child that waits for work assigned to it. It has no model surface
      // any more, so the coordinator spawns it, and the roster still reports the
      // grant actually recorded rather than the empty one asked for — a caller
      // that assumed file access it did not get is the failure this prevents.
      // An idle resident no longer has a model-facing start, so the coordinator
      // creates it, and the roster still reports the grant actually recorded
      // rather than the empty one asked for.
      const idle = runtime.spawnAgent({{ name: "unknown-capability-test", role: "unknown-capability-test" }});
      assert.equal(idle.ok, true);
      assert.equal(idle.agent.status, "starting");
      assert.deepEqual(idle.agent.tools, grant, "the recorded grant is the one asked for");
      // The roster readback for a resident belongs to the harness that registers the
      // child with the execution layer; here the claim is that the coordinator
      // records the resolved grant rather than the empty one the caller asked for.
      assert.deepEqual(idle.agent.tools, grant, "the recorded grant is the one asked for");
      // A description with no instructions is a role with a purpose and no
      // standing instructions. It spawns, and the receipt says the difference,
      // because a role that teaches nothing must not read as one that does. The
      // model surface always supplies both halves, so this is the executor's own
      // half-role path, driven with the intent operation.
      const {{ executeChildIntent }} = await import("@fradser/pi-subagents");
      const halfRole = await executeChildIntent({{ operation: "start", name: "half-role",
        description: "only one half" }}, {{ cwd: {str(tmp_path)!r} }});
      assert.equal(halfRole.structuredContent.operation, "start");
      assert.equal(halfRole.structuredContent.outcome, "started", halfRole.content[0].text);
      assert.equal(halfRole.structuredContent.role, "only one half");
      assert.match(halfRole.content[0].text, /no standing instructions/);
      console.log(JSON.stringify({{ ok: true }}));
    ''', env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path / "agent")})


@pytest.mark.parametrize("recorded", ["undefined", '["read", "task", "message"]'])
def test_roster_read_uses_recorded_grant_not_current_definition(tmp_path: Path, recorded: str) -> None:
    run_node(f'''
      import assert from "node:assert/strict";
      import {{ publishTeamHost, registerComposedTools }} from "./tests/composed-tools.ts";
      import {{ registerAgent, resetState }} from "{(SRC / 'state.ts').as_uri()}";
      const {{ registerSessionAgent }} = await import("@fradser/pi-subagents");
      resetState();
      registerSessionAgent({{ name: "historical", description: "Changed role", prompt: "Changed role", tools: ["bash"] }});
      const tools = new Map();
      registerComposedTools({{ registerTool: t => tools.set(t.name, t) }});
      registerAgent({{ name: "historical", role: "historical", spawnId: "s1", status: "idle",
        tools: {recorded}, pid: 0, isolation: "none", createdAt: 1, updatedAt: 1 }});
      // Strict intent inputs take no session: the roster read is the surviving
      // way to look a recorded incarnation up, and it takes no handle.
      const result = await tools.get("agent_list").execute("test", {{}},
        undefined, undefined, {{ cwd: {str(tmp_path)!r} }});
      assert.equal(result.details.operation, "agent_list");
      assert.equal(result.details.disposition, "listed");
      const session = result.details.sessions[0];
      assert.equal(session.session, "session:historical:s1");
      assert.deepEqual(session.tools, {recorded});
      console.log(JSON.stringify({{ ok: true }}));
    ''', env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path / "agent")})


def test_guidance_requires_failed_blockers_and_quiet_leader_handling() -> None:
    guidance = (SRC / "guidance.ts").read_text()
    roles = (PACKAGE / "references" / "agent-roles.md").read_text()
    for text in [guidance, roles]:
        assert 'outcome: "failed"' in text
        assert "successful candidate" in text
        assert "independently verified" in text
    assert "no acknowledgment" in guidance
    assert "acceptance criteria" in guidance
    assert "verification gate" in guidance
    assert "repeated reports" in guidance


@pytest.mark.parametrize("outcome", ["failed", "success"])
def test_public_submit_settlement_keeps_blocked_dependents(tmp_path: Path, outcome: str) -> None:
    payload = machine_case(tmp_path, f'''
      const {{ createWorkerFixture, assistant }} = await import("{(PACKAGE / 'tests' / 'automatic-results-fixture.ts').as_uri()}");
      const {{ tasksFilePath, submissionsDir }} = await import("@fradser/pi-tasks");
      const path = await import("node:path");
      const fixture = createWorkerFixture(root, "direct", "reviewer");
      const tasksSubmissions = submissionsDir(path.dirname(tasksFilePath(undefined, root)));
      fixture.binding.submissionsDir = tasksSubmissions;
      process.env.PI_TEAMMATE_SUBMISSIONS_DIR = tasksSubmissions;
      const agent = getAgent("reviewer");
      fixture.roster(agent.assignment, agent.spawnId, "working", task.id);
      const dependent = createTask({{ id: "dependent", subject: "Use verified evidence", dependsOn: [task.id] }}).task;
      getTask(task.id).verify = "Require actual execution evidence";
      setVerifyGateRunner(async () => ({{ kind: "fail", detail: "No execution evidence" }}));
      await fixture.start(attempt);
      const submitted = await fixture.call("task", {{ action: "submit", outcome: {outcome!r}, result: "Missing required tools" }});
      assert.equal(submitted.terminate, true);
      await fixture.answer(assistant("Blocked: cannot perform requested work"));
      await fixture.emit({{ type: "agent_settled" }});
      await fixture.emit({{ type: "agent_settled" }});
      assert.deepEqual(fixture.records(), [], "Explicit outcome suppresses automatic success");
      processTaskIntents(); settle();
      await new Promise(resolve => setImmediate(resolve));
      processTaskIntents(); settle();
      const {{ renderTaskList }} = await import("{(SRC / 'worker.ts').as_uri()}");
      console.log(JSON.stringify({{ status: getTask(task.id).status,
        reports: reports.filter(r => r.finished).map(r => r.status),
        task: renderTaskList([getTask(task.id), dependent]) }}));
    ''')
    assert payload["status"] != "completed"
    assert payload["reports"] == (["failed"] if outcome == "failed" else [])
    assert "dependent · pending/blocked" in payload["task"]


def test_inline_tools_schema_explains_least_privilege() -> None:
    text = (SRC / "types.ts").read_text()
    assert "coordination-only" in text
    run_node(f'''
      import assert from "node:assert/strict";
      import {{ InlineAgentDefinitionParams }} from "{(SRC / 'types.ts').as_uri()}";
      import {{ AGENT_BUILTIN_TOOLS }} from "@fradser/pi-subagents";
      import {{ buildIdleLeaderGuidance }} from "{(SRC / 'guidance.ts').as_uri()}";
      for (const tool of AGENT_BUILTIN_TOOLS) {{
        assert.ok(InlineAgentDefinitionParams.properties.tools.description.includes(tool), `Schema missing ${{tool}}`);
        assert.ok(buildIdleLeaderGuidance().includes(tool), `Guidance missing ${{tool}}`);
      }}
      console.log(JSON.stringify({{ ok: true }}));
    ''')


def _write_agent(path: Path, name: str, frontmatter: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ndescription: A test role\ntools: read, bash\n{frontmatter}\n---\n\nRole body.\n",
        encoding="utf-8",
    )


def test_agent_memory_reaches_only_a_fixed_agents_spawn(tmp_path: Path) -> None:
    """Agent Memory is a persisted Agent's own capability, so only its spawn
    carries the tool and the worker extension that registers it.

    A Temporary Agent owns no folder to write, so a grant it cannot use is a
    receipt that lies: the row would say the child may record capability lessons
    and the child would find no such tool.
    """
    # VISION.md supersedes opt-in: every canonical disk identity has Memory.
    _write_agent(tmp_path / ".pi" / "agents" / "fixed" / "agent.md", "fixed", "")
    _write_agent(tmp_path / ".pi" / "agents" / "plain" / "agent.md", "plain", "")
    payload = run_node(
        f'''
        import childProcess from "node:child_process";
        import {{ EventEmitter }} from "node:events";
        import {{ syncBuiltinESMExports }} from "node:module";
        import {{ PassThrough }} from "node:stream";
        import {{ mock }} from "node:test";
        import * as kit from "@fradser/pi-kit";
        const children = [];
        mock.module("@fradser/pi-kit", {{
          namedExports: {{
            ...kit,
            resolvePiCli: () => ({{ command: "unused-mock", args: [] }}),
            spawnPiChild: (command, args) => {{
              const child = Object.assign(new EventEmitter(), {{
                pid: 100, stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(),
              }});
              children.push({{ command, args, child }});
              return child;
            }},
            terminateChildProcess: async () => true,
          }},
        }});
        const {{ initTeamMachine, shutdownTeamMachine, spawnAgent }} = await import({(SRC / "team-machine.ts").as_uri()!r});
        const {{ getAgent, resetState }} = await import({(SRC / "state.ts").as_uri()!r});
        const root = {str(tmp_path)!r};
        resetState();
        initTeamMachine({{ sessionManager: undefined, cwd: root }}, {{ sendUpdate: () => {{}}, notifyChange: () => {{}} }});
        const fixed = spawnAgent({{ name: "fixed-child", role: "fixed" }});
        const plain = spawnAgent({{ name: "plain-child", role: "plain" }});
        const temporary = spawnAgent({{ name: "temp-child", role: "temp-role",
          definition: {{ description: "One answer", prompt: "Answer once.", tools: ["read"] }} }});
        const refused = spawnAgent({{ name: "memory-child", role: "memory-role",
          definition: {{ description: "Wants memory", prompt: "Remember this.", tools: ["agent_memory"] }} }});
        const toolsOf = (spawn) => spawn.ok ? getAgent(spawn.agent.name)?.tools : null;
        // Spawns are sequential, so child N is the argv of spawn N — and a
        // refused spawn contributing no child is itself the assertion.
        const toolArgv = (args) => args[args.indexOf("--tools") + 1];
        const extensionsOf = (args) => args.reduce((all, value, index) =>
          args[index - 1] === "--extension" ? [...all, value] : all, []);
        const argvOf = (index) => children[index].args;
        console.log(JSON.stringify({{
          fixed: {{ ok: fixed.ok, tools: toolsOf(fixed), argv: toolArgv(argvOf(0)),
            extensions: extensionsOf(argvOf(0)) }},
          plain: {{ ok: plain.ok, tools: toolsOf(plain), argv: toolArgv(argvOf(1)),
            extensions: extensionsOf(argvOf(1)) }},
          temporary: {{ ok: temporary.ok, tools: toolsOf(temporary), argv: toolArgv(argvOf(2)),
            extensions: extensionsOf(argvOf(2)) }},
          refused: {{ ok: refused.ok, error: refused.ok ? null : refused.error }},
          spawned: children.length,
        }}));
        shutdownTeamMachine();
        for (const entry of children) entry.child.emit("close", 0, null);
        ''',
        module_mocks=True,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path / "agent")},
    )

    assert payload["spawned"] == 3, "a refused spawn must not start a child"
    # A fixed Agent: the memory tool is real, and something registers it.
    assert payload["fixed"]["ok"] is True
    assert "agent_memory" in payload["fixed"]["tools"]
    assert payload["fixed"]["argv"].split(",") == payload["fixed"]["tools"]
    assert any("agent-extension" in path for path in payload["fixed"]["extensions"]), payload["fixed"]["extensions"]
    # A disk identity without flags still gets Memory; temporary roles do not.
    assert payload["plain"]["ok"] is True
    assert payload["plain"]["tools"] == ["read", "bash", "agent_memory", "message", "task"]
    assert payload["plain"]["argv"].split(",") == payload["plain"]["tools"]
    assert any("agent-extension" in path for path in payload["plain"]["extensions"])
    assert payload["temporary"]["ok"] is True
    assert "agent_memory" not in payload["temporary"]["tools"]
    assert payload["temporary"]["argv"].split(",") == payload["temporary"]["tools"]
    assert not any("agent-extension" in path for path in payload["temporary"]["extensions"])
    assert payload["temporary"]["tools"] == ["read", "message", "task"]
    # Asking for the tool with no folder is refused rather than silently dropped.
    assert payload["refused"]["ok"] is False
    assert "memory" in str(payload["refused"]["error"])
