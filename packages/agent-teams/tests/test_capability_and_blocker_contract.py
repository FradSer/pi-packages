from pathlib import Path

import pytest

from test_teammate_package import SRC, PACKAGE, run_node
from test_accepted_work_reporting import machine_case


@pytest.mark.parametrize("requested", ["undefined", "[]", '["read", "bash"]'])
def test_public_lifecycle_content_discloses_recorded_grant(tmp_path: Path, requested: str) -> None:
    run_node(f'''
      import assert from "node:assert/strict";
      import {{ publishTeamHost, registerComposedTools }} from "./tests/composed-tools.ts";
      import {{ registerTeammate, resetState }} from "{(SRC / 'state.ts').as_uri()}";
      import {{ resolveWorkerTools }} from "@fradser/pi-subagents";
      import {{ WORKER_CAPABILITY_TOOLS }} from "{(SRC / 'capability-tools.ts').as_uri()}";
      resetState();
      const tools = new Map();
      const requested = {requested};
      const grant = resolveWorkerTools(requested, WORKER_CAPABILITY_TOOLS);
      const runtime = {{
        spawnTeammate(input) {{
          const teammate = {{ name: input.name, agent: input.name, spawnId: "s1", status: "starting",
            workId: input.workId, tools: grant, pid: 0, isolation: "none", createdAt: 1, updatedAt: 1 }};
          registerTeammate(teammate);
          return {{ ok: true, teammate }};
        }},
      }};
      registerComposedTools({{ registerTool: t => tools.set(t.name, t) }}, runtime);
      publishTeamHost(runtime);
      const call = p => tools.get("agent").execute("test", p, undefined, undefined, {{ cwd: {str(tmp_path)!r} }});
      {{
        resetState();
        const result = await call({{ action: "start", name: "capability-test", prompt: "Check evidence",
          description: "Check", role_prompt: "Check", tools: requested }});
        // The tool now answers with a structured result, and a handle rather than
        // a projection, so the projection is read back through `inspect`.
        assert.equal(result.details.ok, true, result.content[0].text);
        assert.match(result.details.session, /^session:capability-test:/);
        const inspected = await call({{ action: "inspect", session: result.details.session }});
        // The effective grant is the one thing a caller routinely gets wrong by
        // assumption, so it is reported on the roster entry rather than inferred.
        assert.deepEqual(inspected.details.sessions[0].tools, grant);
        if (grant.length === 2) {{
          assert.deepEqual(grant, ["message", "task"],
            "an empty request is coordination-only: the two coordination tools and nothing else");
        }}
      }}
      // A name with no definition, no prompt and no grant is the idle-resident
      // case: a child that waits for work assigned to it. It succeeds, and reports
      // the grant the roster actually recorded rather than the empty one asked
      // for — a caller that assumed file access it did not get is the failure
      // this prevents.
      const idle = await call({{ action: "start", name: "unknown-capability-test" }});
      assert.equal(idle.details.ok, true, idle.content[0].text);
      assert.equal(idle.details.prompted, false);
      assert.deepEqual(idle.details.grant, grant, "the reported grant is the recorded one");
      assert.match(idle.content[0].text, /ROLE · none/);
      // Half a role is the case worth refusing: the missing half would produce a
      // child that silently has no instructions.
      const halfRole = await call({{ action: "start", name: "half-role", description: "only one half" }});
      assert.equal(halfRole.details.ok, false);
      assert.match(halfRole.content[0].text, /both/);
      console.log(JSON.stringify({{ ok: true }}));
    ''', env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path / "agent")})


@pytest.mark.parametrize("recorded", ["undefined", '["read", "task", "message"]'])
def test_inspect_uses_recorded_grant_not_current_definition(tmp_path: Path, recorded: str) -> None:
    run_node(f'''
      import assert from "node:assert/strict";
      import {{ publishTeamHost, registerComposedTools }} from "./tests/composed-tools.ts";
      import {{ registerTeammate, resetState }} from "{(SRC / 'state.ts').as_uri()}";
      const {{ registerSessionAgent }} = await import("@fradser/pi-subagents");
      resetState();
      registerSessionAgent({{ name: "historical", description: "Changed role", prompt: "Changed role", tools: ["bash"] }});
      const tools = new Map();
      registerComposedTools({{ registerTool: t => tools.set(t.name, t) }});
      registerTeammate({{ name: "historical", agent: "historical", spawnId: "s1", status: "idle",
        tools: {recorded}, pid: 0, isolation: "none", createdAt: 1, updatedAt: 1 }});
      const result = await tools.get("agent").execute("test", {{ action: "inspect", name: "historical",
        session: "session:historical:s1" }}, undefined, undefined, {{ cwd: {str(tmp_path)!r} }});
      const session = result.details.sessions[0];
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
      const {{ boardFilePath, submissionsDir }} = await import("@fradser/pi-tasks");
      const path = await import("node:path");
      const fixture = createWorkerFixture(root, "direct", "reviewer");
      const boardSubmissions = submissionsDir(path.dirname(boardFilePath(undefined, root)));
      fixture.binding.submissionsDir = boardSubmissions;
      process.env.PI_TEAMMATE_SUBMISSIONS_DIR = boardSubmissions;
      const teammate = getTeammate("reviewer");
      fixture.roster(teammate.assignment, teammate.spawnId, "working", task.id);
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
      const {{ renderTaskBoard }} = await import("{(SRC / 'worker.ts').as_uri()}");
      console.log(JSON.stringify({{ status: getTask(task.id).status,
        reports: reports.filter(r => r.finished).map(r => r.status),
        board: renderTaskBoard([getTask(task.id), dependent]) }}));
    ''')
    assert payload["status"] != "completed"
    assert payload["reports"] == (["failed"] if outcome == "failed" else [])
    assert "dependent · pending/blocked" in payload["board"]


def test_inline_tools_schema_explains_least_privilege() -> None:
    text = (SRC / "types.ts").read_text()
    assert "coordination-only" in text
    run_node(f'''
      import assert from "node:assert/strict";
      import {{ InlineAgentDefinitionParams }} from "{(SRC / 'types.ts').as_uri()}";
      import {{ WORKER_BUILTIN_TOOLS }} from "@fradser/pi-subagents";
      import {{ buildIdleLeaderGuidance }} from "{(SRC / 'guidance.ts').as_uri()}";
      for (const tool of WORKER_BUILTIN_TOOLS) {{
        assert.ok(InlineAgentDefinitionParams.properties.tools.description.includes(tool), `Schema missing ${{tool}}`);
        assert.ok(buildIdleLeaderGuidance().includes(tool), `Guidance missing ${{tool}}`);
      }}
      console.log(JSON.stringify({{ ok: true }}));
    ''')
