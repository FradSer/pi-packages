from pathlib import Path

import pytest

from test_teammate_package import SRC, PACKAGE, run_node
from test_accepted_work_reporting import machine_case


@pytest.mark.parametrize("requested", ["undefined", "[]", '["read", "bash"]'])
def test_public_lifecycle_content_discloses_recorded_grant(tmp_path: Path, requested: str) -> None:
    run_node(f'''
      import assert from "node:assert/strict";
      import {{ registerLeaderTools }} from "{(SRC / 'tools.ts').as_uri()}";
      import {{ registerTeammate, resetState }} from "{(SRC / 'state.ts').as_uri()}";
      import {{ resolveWorkerTools }} from "{(SRC / 'spawner.ts').as_uri()}";
      resetState();
      const tools = new Map();
      const requested = {requested};
      const grant = resolveWorkerTools(requested);
      const runtime = {{
        spawnTeammate(input) {{
          const teammate = {{ name: input.name, agent: input.name, spawnId: "s1", status: "starting",
            workId: input.workId, tools: grant, pid: 0, isolation: "none", createdAt: 1, updatedAt: 1 }};
          registerTeammate(teammate);
          return {{ ok: true, teammate }};
        }},
      }};
      registerLeaderTools({{ registerTool: t => tools.set(t.name, t) }}, runtime);
      const call = p => tools.get("agent").execute("test", p, undefined, undefined, {{ cwd: {str(tmp_path)!r} }});
      for (const action of ["delegate", "start"]) {{
        resetState();
        const result = await call({{ action, name: "capability-test", prompt: "Check evidence",
          definition: {{ description: "Check", prompt: "Check", tools: requested }} }});
        const content = JSON.parse(result.content[0].text);
        assert.deepEqual(content.session.tools, grant);
        assert.equal(Boolean(content.session.warning?.includes("coordination-only")), grant.length === 2);
        const inspected = JSON.parse((await call({{ action: "inspect", name: "capability-test", session: content.session.id }})).content[0].text);
        assert.deepEqual(inspected.sessions[0], content.session);
      }}
      await assert.rejects(call({{ action: "delegate", name: "unknown-capability-test", prompt: "Check" }}), /definition.*tools.*read.*powershell/);
      console.log(JSON.stringify({{ ok: true }}));
    ''', env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path / "agent")})


@pytest.mark.parametrize("recorded", ["undefined", '["read", "work", "agent_event"]'])
def test_inspect_uses_recorded_grant_not_current_definition(tmp_path: Path, recorded: str) -> None:
    run_node(f'''
      import assert from "node:assert/strict";
      import {{ registerLeaderTools }} from "{(SRC / 'tools.ts').as_uri()}";
      import {{ registerTeammate, resetState }} from "{(SRC / 'state.ts').as_uri()}";
      const {{ registerSessionAgent }} = await import("{(SRC / 'agents.ts').as_uri()}");
      resetState();
      registerSessionAgent({{ name: "historical", description: "Changed role", prompt: "Changed role", tools: ["bash"] }});
      const tools = new Map();
      registerLeaderTools({{ registerTool: t => tools.set(t.name, t) }});
      registerTeammate({{ name: "historical", agent: "historical", spawnId: "s1", status: "idle",
        tools: {recorded}, pid: 0, isolation: "none", createdAt: 1, updatedAt: 1 }});
      const result = await tools.get("agent").execute("test", {{ action: "inspect", name: "historical",
        session: "session:historical:s1" }}, undefined, undefined, {{ cwd: {str(tmp_path)!r} }});
      const session = JSON.parse(result.content[0].text).sessions[0];
      assert.deepEqual(session.tools, {recorded});
      assert.equal(session.warning, undefined);
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
      const {{ boardFilePath, submissionsDir }} = await import("{(SRC / 'statefile.ts').as_uri()}");
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
      const submitted = await fixture.call("work", {{ action: "submit", outcome: {outcome!r}, result: "Missing required tools" }});
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
      import {{ WORKER_BUILTIN_TOOLS }} from "{(SRC / 'spawner.ts').as_uri()}";
      import {{ buildIdleLeaderGuidance }} from "{(SRC / 'guidance.ts').as_uri()}";
      for (const tool of WORKER_BUILTIN_TOOLS) {{
        assert.ok(InlineAgentDefinitionParams.properties.tools.description.includes(tool), `Schema missing ${{tool}}`);
        assert.ok(buildIdleLeaderGuidance().includes(tool), `Guidance missing ${{tool}}`);
      }}
      console.log(JSON.stringify({{ ok: true }}));
    ''')
