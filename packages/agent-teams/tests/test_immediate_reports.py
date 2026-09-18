from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest

from test_teammate_package import PACKAGE, SRC, run_node


@pytest.mark.parametrize("leader_idle", [False, True])
def test_reports_are_handed_off_without_waiting(tmp_path: Path, leader_idle: bool) -> None:
    payload = run_node(
        f'''\
        import extension from "{(SRC / 'index.ts').as_uri()}";
        import {{ drainTeammateOutboxes, shutdownTeamMachine, applyProgress }} from "{(SRC / 'team-machine.ts').as_uri()}";
        import {{ registerTeammate, createTask, setTaskClaimed, getTeammate }} from "{(SRC / 'state.ts').as_uri()}";
        import {{ appendWorkerEvent, stateFilePath, workerOutboxPath }} from "{(SRC / 'statefile.ts').as_uri()}";
        const hooks = new Map();
        const sent = [];
        const pi = {{
          on(event, handler) {{ hooks.set(event, handler); }},
          registerTool() {{}}, registerCommand() {{}},
          registerEntryRenderer() {{}}, registerMessageRenderer() {{}},
          getActiveTools: () => [], getAllTools: () => [], setActiveTools() {{}},
          sendMessage(message, options) {{ sent.push({{ message, options }}); }},
        }};
        const cwd = {str(tmp_path)!r};
        const ctx = {{ cwd, mode: 'print', hasUI: false, isIdle: () => {str(leader_idle).lower()},
          sessionManager: {{ getSessionFile: () => undefined }},
          ui: {{ setWidget() {{}}, setStatus() {{}}, notify() {{}} }},
        }};
        extension(pi);
        await hooks.get('session_start')({{}}, ctx);
        try {{
          registerTeammate({{ name: 'author', agent: 'worker', spawnId: 's1', pid: 0,
            status: 'working', isolation: 'none', createdAt: 1, updatedAt: 1 }});
          const task = createTask({{ subject: 'Validate work' }}).task;
          setTaskClaimed(task.id, 'author');
          const assignmentId = getTeammate('author').assignment.id;
          applyProgress('author', 's1', {{ text: '', turns: 1, finalResponse: false }});
          const outbox = workerOutboxPath(stateFilePath(undefined, cwd), 'author', 's1');
          for (const [id, body, status] of [
            ['e1', 'New evidence changes the scope', 'in_progress'],
            ['e2', 'Assignment complete with validation', 'completed'],
          ]) {{
            appendWorkerEvent(outbox, {{ id, type: 'message', worker: 'author', spawnId: 's1', assignmentId, body, status, timestamp: 100 }});
            drainTeammateOutboxes();
            if (status === 'completed') applyProgress('author', 's1', {{ text: body, turns: 1, finalResponse: true }});
          }}
          const beforeSettlement = sent.map((entry) => ({{
            eventId: entry.message.details.eventId,
            status: entry.message.details.status,
            deliverAs: entry.options.deliverAs,
            triggerTurn: entry.options.triggerTurn,
            stamped: entry.message.content.includes('1970-01-01T00:00:00.100Z'),
          }}));
          await hooks.get('agent_settled')?.({{}}, ctx);
          await new Promise((resolve) => setTimeout(resolve, 10));
          console.log(JSON.stringify({{ beforeSettlement, afterSettlement: sent.length }}));
        }} finally {{
          await hooks.get('session_shutdown')({{}}, ctx);
          shutdownTeamMachine();
        }}
        ''',
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path / "agent")},
    )
    reports = payload["beforeSettlement"]
    assert reports[0] == {"eventId": "e1", "status": "in_progress", "deliverAs": "steer", "triggerTurn": True, "stamped": True}
    assert reports[1]["eventId"]
    assert reports[1] | {"eventId": "accepted"} == {
        "eventId": "accepted", "status": "completed", "deliverAs": "steer", "triggerTurn": True, "stamped": True,
    }
    assert payload["afterSettlement"] == 2


def test_leader_guidance_limits_steering_to_new_information() -> None:
    payload = run_node(
        f'''\
        import {{ buildTeamLeaderGuidance }} from "{(SRC / 'guidance.ts').as_uri()}";
        const guidance = buildTeamLeaderGuidance().replace(/\\s+/g, ' ');
        console.log(JSON.stringify({{ guidance }}));
        '''
    )
    guidance = str(payload["guidance"])
    assert "new information that changes the worker's assignment" in guidance
    assert "Do not ask for progress reports or repeat instructions" in guidance
    assert "The worker autonomously completes its assignment" in guidance
    assert "continue independent work or yield" in guidance


def test_real_pi_delivers_reports_before_the_next_tool(tmp_path: Path) -> None:
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("Pi CLI is required for the native delivery integration test")
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update({
        "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "PI_OFFLINE": "1",
        "PI_REPORT_FIXTURE_AUTH": secrets.token_hex(16),
    })
    result = subprocess.run(
        [pi, "--print", "--no-session", "--no-extensions", "--no-skills",
         "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-approve",
         "--extension", str(PACKAGE / "tests" / "immediate-reports-fixture.ts"),
         "--provider", "report-fixture", "--model", "deterministic",
         "--thinking", "off", "--tools", "produce_reports,check_reports", "Run the report fixture"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stderr
    assert "PI_IMMEDIATE_REPORTS_OK" in result.stdout, result.stdout + result.stderr
    assert "PI_IMMEDIATE_REPORTS_FAILED" not in result.stdout
