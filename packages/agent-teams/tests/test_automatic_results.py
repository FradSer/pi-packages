from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest

from test_teammate_package import PACKAGE, run_node

FIXTURE = (PACKAGE / "tests" / "automatic-results-fixture.ts").as_uri()


def run_worker(tmp_path: Path, script: str, kind: str = "direct") -> dict[str, object]:
    return run_node(f'''\
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import {{ assistant, createWorkerFixture }} from "{FIXTURE}";
        const fixture = createWorkerFixture({str(tmp_path)!r}, {kind!r});
        {script}
    ''')


def test_final_answer_is_reported_once_only_after_settlement(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        await fixture.answer(assistant("Final answer with evidence"));
        await fixture.emit({ type: "agent_end", messages: [] });
        assert.deepEqual(fixture.records(), []);
        await fixture.emit({ type: "agent_settled" });
        await fixture.emit({ type: "agent_settled" });
        assert.equal(fixture.records().length, 1);
        console.log(JSON.stringify({ records: fixture.records(), roster: JSON.parse(fs.readFileSync(fixture.binding.rosterFile, "utf8")) }));
    ''')
    records = payload["records"]
    assert len(records) == 1
    assert records[0] | {"id": "ignored", "timestamp": 0} == {
        "id": "ignored", "timestamp": 0, "type": "message", "worker": "worker", "spawnId": "spawn-1",
        "assignmentId": "attempt-1", "status": "completed", "body": "Final answer with evidence",
    }
    assert "closed" not in payload["roster"]["teammates"][0]["assignment"]


@pytest.mark.parametrize(("stop_reason", "error", "reason"), [
    ("error", "Provider connection failed", "Provider connection failed"),
    ("aborted", "Cancelled by leader", "Cancelled by leader"),
    ("error", None, "error"),
    ("aborted", None, "aborted"),
    ("length", None, "length"),
    ("pending", None, "incomplete"),
    ("deferred", None, "incomplete"),
    ("toolUse", None, "final answer"),
])
def test_failed_response_never_reuses_intermediate_success(tmp_path: Path, stop_reason: str, error: str | None, reason: str) -> None:
    payload = run_worker(tmp_path, f'''
        await fixture.start();
        await fixture.answer(assistant("Stale intermediate success", "stop", 20));
        await fixture.answer(assistant("Partial output is not success", {stop_reason!r}, 30, {json.dumps(error)}));
        await fixture.emit({{ type: "agent_end", messages: [] }});
        assert.deepEqual(fixture.records(), []);
        await fixture.emit({{ type: "agent_settled" }});
        console.log(JSON.stringify({{ records: fixture.records() }}));
    ''')
    assert len(payload["records"]) == 1
    report = payload["records"][0]
    assert report["status"] == "failed"
    assert reason in report["body"]
    assert "Stale intermediate success" not in report["body"]
    assert "Partial output is not success" not in report["body"]


@pytest.mark.parametrize("last_response", ["empty", "tool-call", "unfinished", "missing"])
def test_no_final_answer_is_failed_at_settlement(tmp_path: Path, last_response: str) -> None:
    script = {
        "empty": 'await fixture.answer(assistant("  ", "stop", 30));',
        "tool-call": '''const message = assistant("Tool preamble", "stop", 30);
            message.content.push({ type: "toolCall", id: "read-1", name: "read", arguments: {} });
            await fixture.answer(message);''',
        "unfinished": 'await fixture.emit({ type: "message_start", message: assistant("Partial", "pending", 30) });',
        "missing": "",
    }[last_response]
    payload = run_worker(tmp_path, f'''
        await fixture.start();
        {script}
        await fixture.emit({{ type: "agent_settled" }});
        console.log(JSON.stringify({{ records: fixture.records() }}));
    ''')
    assert len(payload["records"]) == 1
    assert payload["records"][0]["status"] == "failed"
    assert "final answer" in payload["records"][0]["body"]


def test_tools_retries_and_nonidle_settlement_do_not_close_assignment(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        await fixture.answer(assistant("Transient", "error", 20, "429 rate limit"));
        await fixture.emit({ type: "agent_end", messages: [] });
        await fixture.emit({ type: "agent_start" });
        assert.deepEqual(fixture.records(), []);
        await fixture.answer(assistant("Calling a tool", "toolUse", 30));
        await fixture.emit({ type: "message_end", message: { role: "toolResult", content: [{ type: "text", text: "Not the final answer" }],
          toolCallId: "read-1", toolName: "read", isError: false, timestamp: 35 } });
        assert.deepEqual(fixture.records(), []);
        await fixture.answer(assistant("Recovered final answer", "stop", 40));
        fixture.setIdle(false);
        await fixture.emit({ type: "agent_settled" });
        assert.deepEqual(fixture.records(), []);
        fixture.setIdle(true);
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records() }));
    ''')
    assert [(record["body"], record["status"]) for record in payload["records"]] == [("Recovered final answer", "completed")]


def test_communication_event_does_not_require_completion_bookkeeping(tmp_path: Path) -> None:
    tool = "agent_event"
    payload = run_worker(tmp_path, f'''
        await fixture.start();
        const result = await fixture.call({tool!r}, {{ to: "leader", message: "New evidence" }});
        assert.notEqual(result.terminate, true);
        await fixture.answer(assistant("Final answer"));
        await fixture.emit({{ type: "agent_settled" }});
        console.log(JSON.stringify({{ description: fixture.tools.get({tool!r}).description,
          response: result.content[0].text, records: fixture.records() }}));
    ''')
    assert len(payload["records"]) == 2
    assert payload["records"][-1]["body"] == "Final answer"
    assert "automatically" in payload["description"]
    assert "REPORT" in payload["response"]
    assert "status=" not in payload["response"]


@pytest.mark.parametrize("kind", ["board", "none"])
def test_board_holders_and_unassigned_workers_do_not_autocomplete(tmp_path: Path, kind: str) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start("attempt-1");
        await fixture.answer(assistant("An answer does not submit board work"));
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records(), submitted: fs.existsSync(fixture.binding.submissionsDir) }));
    ''', kind)
    assert payload == {"records": [], "submitted": False}


@pytest.mark.parametrize("change", ["assignment", "spawn", "closed", "stopped", "missing", "binding"])
def test_stale_assignment_or_spawn_cannot_write_result(tmp_path: Path, change: str) -> None:
    mutate = {
        "assignment": 'fixture.roster({ id: "attempt-2", kind: "direct", resources: [] });',
        "spawn": 'fixture.roster({ id: "attempt-1", kind: "direct", resources: [] }, "spawn-2");',
        "closed": 'fixture.roster({ id: "attempt-1", kind: "direct", resources: [], closed: true });',
        "stopped": 'fixture.roster({ id: "attempt-1", kind: "direct", resources: [] }, "spawn-1", "stopped");',
        "missing": 'fs.rmSync(fixture.binding.rosterFile);',
        "binding": 'process.env.PI_TEAMMATE_SPAWN_ID = "spawn-2";',
    }[change]
    payload = run_worker(tmp_path, f'''
        await fixture.start();
        await fixture.answer(assistant("Old attempt answer"));
        {mutate}
        await fixture.emit({{ type: "agent_settled" }});
        console.log(JSON.stringify({{ records: fixture.records() }}));
    ''')
    assert payload["records"] == []


def test_reopening_discards_old_evidence_and_repeated_settlement(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        const oldMessage = assistant("Old result", "stop", 20);
        await fixture.answer(oldMessage);
        await fixture.emit({ type: "agent_settled" });
        fixture.roster({ id: "attempt-2", kind: "direct", resources: [] });
        await fixture.emit({ type: "agent_settled" });
        assert.equal(fixture.records().length, 1);
        await fixture.start("attempt-2", 30);
        await fixture.emit({ type: "message_end", message: oldMessage });
        await fixture.answer(assistant("New result", "stop", 40));
        await fixture.emit({ type: "message_end", message: oldMessage });
        await fixture.start("attempt-1", 10);
        await fixture.emit({ type: "agent_settled" });
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records() }));
    ''')
    assert [(record["assignmentId"], record["body"]) for record in payload["records"]] == [
        ("attempt-1", "Old result"), ("attempt-2", "New result"),
    ]


def test_reset_discards_unsettled_result_until_new_activity(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        await fixture.answer(assistant("Discard this result"));
        fixture.disclosure.reset();
        await fixture.emit({ type: "agent_settled" });
        assert.deepEqual(fixture.records(), []);
        await fixture.start("attempt-1", 30);
        await fixture.answer(assistant("Fresh result", "stop", 40));
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records() }));
    ''')
    assert [record["body"] for record in payload["records"]] == ["Fresh result"]


def test_outbox_write_failure_does_not_close_the_local_report_binding(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        await fixture.answer(assistant("Final result"));
        fs.mkdirSync(fixture.binding.outbox);
        await assert.rejects(fixture.emit({ type: "agent_settled" }));
        fs.rmdirSync(fixture.binding.outbox);
        await fixture.emit({ type: "agent_settled" });
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records() }));
    ''')
    assert len(payload["records"]) == 1
    assert payload["records"][0]["body"] == "Final result"


@pytest.mark.parametrize("text", ["证据与结论\n", "证据", "\x00\"\\"])
def test_large_unicode_result_keeps_full_private_artifact_and_bounded_report(tmp_path: Path, text: str) -> None:
    payload = run_worker(tmp_path, f"const full = {json.dumps(text)}.repeat(15000);" + '''
        await fixture.start();
        await fixture.answer(assistant(full));
        await fixture.emit({ type: "agent_settled" });
        await fixture.emit({ type: "agent_settled" });
        const records = fixture.records();
        assert.equal(records.length, 1);
        const artifact = /Full result: (.+)/.exec(records[0].body)?.[1];
        assert.ok(artifact, "Large report must link its full result");
        assert.equal(fs.readFileSync(artifact, "utf8"), full);
        console.log(JSON.stringify({ status: records[0].status, body: records[0].body,
          artifact, mode: fs.statSync(artifact).mode & 0o777, bytes: fs.statSync(fixture.binding.outbox).size,
          files: fs.readdirSync(new URL(".", "file://" + fixture.binding.outbox)) }));
    ''')
    assert payload["status"] == "completed"
    assert text.rstrip("\n") in payload["body"]
    assert "truncated" in payload["body"]
    assert Path(payload["artifact"]).parent == tmp_path
    assert payload["mode"] == 0o600
    assert payload["bytes"] < 64 * 1024
    assert not any(name.endswith(".tmp") for name in payload["files"])


def test_same_millisecond_old_message_cannot_supply_new_attempt_result(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        const old = assistant("Old same-millisecond answer", "stop", 20);
        await fixture.answer(old);
        await fixture.emit({ type: "agent_settled" });
        fixture.roster({ id: "attempt-2", kind: "direct", resources: [] });
        await fixture.start("attempt-2", 20);
        await fixture.emit({ type: "message_end", message: old });
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records() }));
    ''')
    assert len(payload["records"]) == 2
    assert payload["records"][1]["status"] == "failed"
    assert "Old same-millisecond answer" not in payload["records"][1]["body"]


def test_retry_start_clears_stale_success_before_any_new_response(tmp_path: Path) -> None:
    payload = run_worker(tmp_path, '''
        await fixture.start();
        await fixture.answer(assistant("Previous low-level success"));
        await fixture.emit({ type: "agent_end", messages: [] });
        await fixture.emit({ type: "agent_start" });
        await fixture.emit({ type: "agent_settled" });
        console.log(JSON.stringify({ records: fixture.records() }));
    ''')
    assert len(payload["records"]) == 1
    assert payload["records"][0]["status"] == "failed"
    assert "Previous low-level success" not in payload["records"][0]["body"]


def test_agent_event_requires_precise_route_for_concurrent_peer_sessions(tmp_path: Path) -> None:
    tool = "agent_event"
    payload = run_worker(tmp_path, f'const messageTool = {json.dumps(tool)};' + '''
        const peers = [
          { name: "reviewer-one", agent: "peer-reviewer", status: "working" },
          { name: "reviewer-two", agent: "peer-reviewer", status: "idle" },
        ];
        const write = (teammates) => fs.writeFileSync(fixture.binding.rosterFile, JSON.stringify({ teammates }));
        write(peers);
        await assert.rejects(fixture.call(messageTool, { to: "peer-reviewer", message: "Ambiguous" }),
          /Ambiguous Agent.*reviewer-one.*reviewer-two/);
        assert.equal(fs.existsSync(fixture.binding.inbox.replace("inbox-worker", "inbox-reviewer-one")), false);
        const exact = await fixture.call(messageTool, { to: "session:reviewer-two", message: "Exact route" });
        write([peers[0], { ...peers[1], status: "stopped" }]);
        const unique = await fixture.call(messageTool, { to: "peer-reviewer", message: "Only living route" });
        write([{ name: "worker", agent: "self-role", status: "working" }]);
        await assert.rejects(fixture.call(messageTool, { to: "self-role", message: "Self alias" }), /yourself/);
        const first = JSON.parse(fs.readFileSync(fixture.binding.inbox.replace("inbox-worker", "inbox-reviewer-one"), "utf8"));
        const second = JSON.parse(fs.readFileSync(fixture.binding.inbox.replace("inbox-worker", "inbox-reviewer-two"), "utf8"));
        console.log(JSON.stringify({ exact: exact.details.to, unique: unique.details.to, first: first.body, second: second.body }));
    ''')
    assert payload == {"exact": "reviewer-two", "unique": "reviewer-one", "first": "Only living route", "second": "Exact route"}


def test_native_pi_retry_reports_only_after_settlement(tmp_path: Path) -> None:
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("Pi CLI is required for native settlement verification")
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "settings.json").write_text(json.dumps({"retry": {"enabled": True, "maxRetries": 1, "baseDelayMs": 1}}))
    roster = tmp_path / "roster.json"
    roster.write_text(json.dumps({"teammates": [{"name": "worker", "agent": "reviewer", "spawnId": "spawn-1", "status": "working",
        "assignment": {"id": "attempt-1", "kind": "direct", "resources": []}}]}))
    outbox = tmp_path / "events.jsonl"
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update({
        "PI_CODING_AGENT_DIR": str(agent_dir), "PI_OFFLINE": "1", "PI_AUTOMATIC_RESULTS_AUTH": secrets.token_hex(16),
        "PI_TEAMMATE_WORKER_NAME": "worker", "PI_TEAMMATE_SPAWN_ID": "spawn-1", "PI_TEAMMATE_OUTBOX_FILE": str(outbox),
        "PI_TEAMMATE_ROSTER_FILE": str(roster), "PI_TEAMMATE_INBOX_FILE": str(tmp_path / "inbox.jsonl"),
        "PI_TEAMMATE_BOARD_FILE": str(tmp_path / "board.json"), "PI_TEAMMATE_CLAIMS_DIR": str(tmp_path / "claims"),
        "PI_TEAMMATE_SUBMISSIONS_DIR": str(tmp_path / "submissions"),
    })
    result = subprocess.run(
        [pi, "--print", "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes",
         "--no-context-files", "--no-approve", "--extension", str(PACKAGE / "tests" / "automatic-results-fixture.ts"),
         "--provider", "automatic-results-fixture", "--model", "deterministic", "--thinking", "off", "--no-builtin-tools",
         "[agent-teams-assignment:attempt-1]\nRun the automatic result fixture"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PI_AUTOMATIC_RESULTS_OK" in result.stdout, result.stdout + result.stderr
    assert "AssertionError" not in result.stderr
    assert outbox.exists(), result.stdout + result.stderr
    records = [json.loads(line) for line in outbox.read_text().splitlines()]
    assert [(record["status"], record["body"]) for record in records] == [("completed", "PI_AUTOMATIC_RESULTS_OK")]
