"""Pure guard checks for the real-model observer; no model or Pi process is started."""
from __future__ import annotations

import json
import stat
from pathlib import Path

from matt_pocock_helpers import run_typescript


def test_project_guard_resolves_relative_paths_and_rejects_escapes(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "verify.test.mjs").write_text("// fixed")
    (tmp_path / "tests-alias").symlink_to(tmp_path / "tests", target_is_directory=True)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    result = run_typescript(f'''
        import {{ guardToolInput, selfCheck }} from "./packages/matt-pocock/tests/real-model-observer.ts";
        const root = {str(tmp_path)!r};
        console.log(JSON.stringify({{
          read: guardToolInput(root, "read", {{ path: "tests/verify.test.mjs" }}),
          write: guardToolInput(root, "write", {{ path: ".fixture-output" }}),
          verifyWrite: guardToolInput(root, "write", {{ path: "tests/verify.test.mjs" }}),
          verifyEdit: guardToolInput(root, "edit", {{ path: "tests/verify.test.mjs" }}),
          testsDirectoryWrite: guardToolInput(root, "write", {{ path: "tests" }}),
          aliasVerifyWrite: guardToolInput(root, "write", {{ path: "tests-alias/verify.test.mjs" }}),
          aliasParentWrite: guardToolInput(root, "write", {{ path: "tests-alias" }}),
          artifactThroughProject: guardToolInput(root, "write", {{ path: ".fixture-output" }}),
          parent: guardToolInput(root, "read", {{ path: "../outside/file" }}),
          symlink: guardToolInput(root, "read", {{ path: "link/secret" }}),
          self: selfCheck(root),
        }}));
    ''')
    assert result["read"] == {"allowed": True}
    assert result["write"] == {"allowed": True}
    assert result["verifyWrite"]["allowed"] is False
    assert result["verifyEdit"]["allowed"] is False
    assert result["testsDirectoryWrite"]["allowed"] is False
    assert result["aliasVerifyWrite"]["allowed"] is False
    assert result["aliasParentWrite"]["allowed"] is False
    assert result["artifactThroughProject"] == {"allowed": True}
    assert result["parent"]["allowed"] is False
    assert result["symlink"]["allowed"] is False
    assert result["self"] == {"allowedRead": True, "allowedWrite": True, "parentEscapeRejected": True}


def test_non_file_tools_and_missing_optional_paths_remain_unrestricted(tmp_path: Path) -> None:
    result = run_typescript(f'''
        import {{ guardToolInput }} from "./packages/matt-pocock/tests/real-model-observer.ts";
        const root = {str(tmp_path)!r};
        console.log(JSON.stringify({{
          custom: guardToolInput(root, "fixture_checks", {{ value: "ignored" }}),
          optional: guardToolInput(root, "grep", {{ pattern: "x" }}),
          invalidRoot: guardToolInput(undefined, "read", {{ path: "x" }}),
        }}));
    ''')
    assert result["custom"] == {"allowed": True}
    assert result["optional"] == {"allowed": True}
    assert result["invalidRoot"]["allowed"] is False


def test_fixture_checks_runs_real_sandbox_self_checks_without_a_model(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "verify.test.mjs").write_text("import test from 'node:test'; console.log('x'.repeat(10000)); test('fixed', () => {});\n")
    (tmp_path.parent / f"{tmp_path.name}-external-secret.txt").write_text("must stay outside the fixture sandbox")
    evidence = tmp_path / "evidence.jsonl"
    result = run_typescript(f'''
        process.env.MP_REAL_PROJECT = {str(tmp_path)!r};
        process.env.MP_REAL_EVIDENCE = {str(evidence)!r};
        import observer from "./packages/matt-pocock/tests/real-model-observer.ts";
        const tools = [];
        observer({{ on() {{ return () => {{}}; }}, registerTool(tool) {{ tools.push(tool); }}, getActiveTools() {{ return []; }} }});
        const ctx = {{ signal: undefined }};
        const value = await tools[0].execute("self-check", {{}}, undefined, undefined, ctx);
        console.log(JSON.stringify(value));
    ''')
    assert result["details"]["available"] is True
    assert result["details"]["sandbox"]["positive"]["code"] == 0
    assert result["details"]["sandbox"]["negative"]["code"] == 0
    assert result["details"]["passed"] is True
    assert len(result["details"]["node"]["stdout"]) <= 4_000


def test_fixture_checks_canonicalizes_var_alias_before_building_sandbox(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "verify.test.mjs").write_text("import test from 'node:test'; test('fixed', () => {});\n")
    (tmp_path.parent / f"{tmp_path.name}-external-secret.txt").write_text("must stay outside the fixture sandbox")
    alias = str(tmp_path).replace("/private/var/", "/var/", 1)
    assert alias != str(tmp_path)
    result = run_typescript(f'''
        process.env.MP_REAL_EVIDENCE = {str(tmp_path / "evidence.jsonl")!r};
        import {{ runFixtureChecks }} from "./packages/matt-pocock/tests/real-model-observer.ts";
        console.log(JSON.stringify(await runFixtureChecks({alias!r}, undefined)));
    ''')
    assert result["details"]["available"] is True
    assert result["details"]["passed"] is True


def test_agent_end_records_error_diagnostic_and_aggregates_assistant_usage(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.jsonl"
    result = run_typescript(f'''
        process.env.MP_REAL_PROJECT = {str(tmp_path)!r};
        process.env.MP_REAL_EVIDENCE = {str(evidence)!r};
        import observer from "./packages/matt-pocock/tests/real-model-observer.ts";
        const handlers = new Map();
        let aborted = false;
        const pi = {{ on(name, handler) {{ handlers.set(name, handler); }}, registerTool() {{}}, getActiveTools() {{ return ["read"]; }} }};
        observer(pi);
        const ctx = {{ mode: "json", cwd: {str(tmp_path)!r}, sessionManager: {{ getBranch: () => [] }}, abort() {{ aborted = true; }} }};
        await handlers.get("agent_end")({{ messages: [
          {{ role: "assistant", content: [{{ type: "text", text: "first" }}], usage: {{ input: 2, output: 3 }} }},
          {{ role: "assistant", content: [{{ type: "text", text: "last" }}], usage: {{ input: 5, output: 7 }}, stopReason: "error", errorMessage: "provider diagnostic" }},
        ] }}, ctx);
        console.log(JSON.stringify({{ aborted, evidence: (await import("node:fs")).readFileSync({str(evidence)!r}, "utf8") }}));
    ''')
    row = json.loads(result["evidence"].strip())
    assert result["aborted"] is False
    assert row["kind"] == "agent_end"
    assert row["stopReason"] == "error"
    assert row["errorMessage"] == "provider diagnostic"
    assert row["usage"] == {"input": 7, "output": 10}
    assert stat.S_IMODE(evidence.stat().st_mode) == 0o600


def test_matt_tool_metadata_carries_start_args_and_normalized_result_fields(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.jsonl"
    result = run_typescript(f'''
        process.env.MP_REAL_PROJECT = {str(tmp_path)!r};
        process.env.MP_REAL_EVIDENCE = {str(evidence)!r};
        import observer from "./packages/matt-pocock/tests/real-model-observer.ts";
        const handlers = new Map();
        const pi = {{ on(name, handler) {{ handlers.set(name, handler); }}, registerTool() {{}}, getActiveTools() {{ return []; }} }};
        observer(pi);
        const ctx = {{ abort() {{}} }};
        await handlers.get("tool_execution_start")({{ toolCallId: "matt-1", toolName: "matt_pocock_workflow", args: {{ mode: "workflow", route: "hard-bug" }} }}, ctx);
        await handlers.get("tool_execution_end")({{ toolCallId: "matt-1", toolName: "matt_pocock_workflow", isError: false, result: {{ content: [{{ type: "text", text: "bounded" }}], details: {{ mode: "workflow", route: "hard-bug", passed: true, available: true, node: {{ code: 0 }}, state: {{ route: "hard-bug", procedure: "investigate", phase: "reproduce", status: "active", workItemId: "w-1" }} }} }} }}, ctx);
        console.log(JSON.stringify((await import("node:fs")).readFileSync({str(evidence)!r}, "utf8")));
    ''')
    rows = [json.loads(line) for line in result.strip().splitlines()]
    start, end = rows
    assert start["args"] == {"mode": "workflow", "capability": None, "route": "hard-bug", "reference": None, "action": None, "target": None}
    assert end["args"] == start["args"]
    assert end["result"] == {
        "mode": "workflow",
        "capability": None,
        "route": "hard-bug",
        "reference": None,
        "passed": True,
        "available": True,
        "nodeCode": 0,
        "contentParts": 1,
        "textBytes": 7,
        "detailsKeys": ["available", "mode", "node", "passed", "route", "state"],
        "structuredKeys": [],
        "status": None,
        "action": None,
        "pending": None,
        "state": {"route": "hard-bug", "procedure": "investigate", "phase": "reproduce", "status": "active", "workItemId": "w-1"},
    }


def test_context_snapshot_preserves_persisted_workflow_before_agent_end(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.jsonl"
    result = run_typescript(f'''
        process.env.MP_REAL_PROJECT = {str(tmp_path)!r};
        process.env.MP_REAL_EVIDENCE = {str(evidence)!r};
        import observer from "./packages/matt-pocock/tests/real-model-observer.ts";
        const handlers = new Map();
        const pi = {{ on(name, handler) {{ handlers.set(name, handler); }}, registerTool() {{}}, getActiveTools() {{ return ["matt_pocock_workflow"]; }} }};
        observer(pi);
        const ctx = {{ mode: "json", cwd: {str(tmp_path)!r}, sessionManager: {{ getBranch: () => [{{ type: "custom", customType: "matt-pocock-workflow", data: {{ route: "hard-bug", procedure: "investigate", phase: "reproduce", status: "active", workItemId: "w-2" }} }}] }}, abort() {{}} }};
        await handlers.get("context")({{ messages: [{{ role: "user", content: "route request" }}] }}, ctx);
        console.log(JSON.stringify((await import("node:fs")).readFileSync({str(evidence)!r}, "utf8")));
    ''')
    row = json.loads(result.strip())
    assert row["kind"] == "model_context"
    assert row["activeTools"] == ["matt_pocock_workflow"]
    assert row["branch"][0]["customType"] == "matt-pocock-workflow"
    assert row["branch"][0]["state"] == {"route": "hard-bug", "procedure": "investigate", "phase": "reproduce", "status": "active", "workItemId": "w-2"}


def test_ask_metadata_is_filtered_and_error_text_is_bounded(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.jsonl"
    result = run_typescript(f'''
        process.env.MP_REAL_PROJECT = {str(tmp_path)!r};
        process.env.MP_REAL_EVIDENCE = {str(evidence)!r};
        import observer from "./packages/matt-pocock/tests/real-model-observer.ts";
        const handlers = new Map();
        const pi = {{ on(name, handler) {{ handlers.set(name, handler); }}, registerTool() {{}}, getActiveTools() {{ return []; }} }};
        observer(pi);
        const ctx = {{ abort() {{}} }};
        await handlers.get("tool_execution_start")({{ toolCallId: "ask-1", toolName: "matt_pocock_ask", args: {{ title: "t".repeat(900), question: "q".repeat(900), options: ["a".repeat(900), "b", "c", "d", "ignored"], recommended: "a".repeat(900), timeout_seconds: 12, allow_custom: false }} }}, ctx);
        await handlers.get("tool_execution_end")({{ toolCallId: "ask-1", toolName: "matt_pocock_ask", isError: true, result: {{ content: [{{ type: "text", text: "schema error: " + "x".repeat(900) }}], details: {{}} }} }}, ctx);
        console.log(JSON.stringify((await import("node:fs")).readFileSync({str(evidence)!r}, "utf8")));
    ''')
    start, end = [json.loads(line) for line in result.strip().splitlines()]
    args = start["args"]
    assert len(args["title"]) == 512
    assert len(args["question"]) == 512
    assert len(args["options"]) == 4
    assert all(len(option) <= 512 for option in args["options"])
    assert args["timeout_seconds"] == 12
    assert args["allow_custom"] is False
    assert end["args"] == args
    assert len(end["result"]["errorText"]) <= 256


def test_developer_tool_budget_is_finite_and_bounded() -> None:
    from matt_pocock_helpers import run_typescript
    result = run_typescript('''
        import { realModelToolBudget } from "./packages/matt-pocock/tests/real-model-observer.ts";
        console.log(JSON.stringify({budgets:["40", "80", "0", "81", "Infinity", "1.5", "-1", ""].map(realModelToolBudget)}));
    ''')
    assert result["budgets"] == [40, 80, 40, 40, 40, 40, 40, 40]


def test_exhausted_budget_blocks_followup_turns_before_execution(tmp_path: Path) -> None:
    result = run_typescript(f'''
        process.env.MP_REAL_PROJECT = {str(tmp_path)!r};
        process.env.MP_REAL_EVIDENCE = {str(tmp_path / "evidence.jsonl")!r};
        process.env.MP_REAL_TOOL_BUDGET = "1";
        import observer from "./packages/matt-pocock/tests/real-model-observer.ts";
        const handlers = new Map();
        let aborts = 0;
        observer({{on(name, handler) {{handlers.set(name,handler);}}, registerTool() {{}}, getActiveTools() {{return [];}}}});
        const input = {{toolName:"fixture_checks",input:{{}}}};
        const before = await handlers.get("tool_call")(input);
        await handlers.get("tool_execution_start")({{toolCallId:"one",toolName:"fixture_checks",args:{{}}}}, {{abort() {{aborts++;}}}});
        const after = await handlers.get("tool_call")(input);
        console.log(JSON.stringify({{before:before ?? null,after:after ?? null,aborts}}));
    ''')
    assert result["before"] is None
    assert result["aborts"] == 1
    assert result["after"]["block"] is True
    assert result["after"]["terminate"] is True


def test_fixture_diagnostics_are_visible_and_redacted(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/verify.test.mjs").write_text("import test from 'node:test'; test('observed failure',()=>{throw new Error('diagnostic sentinel-private-token');});")
    (tmp_path.parent / f"{tmp_path.name}-external-secret.txt").write_text("public sentinel")
    result = run_typescript(f'''
        process.env.OPENAI_API_KEY = "sentinel-private-token";
        import {{ runFixtureChecks }} from "./packages/matt-pocock/tests/real-model-observer.ts";
        console.log(JSON.stringify(await runFixtureChecks({str(tmp_path)!r}, undefined)));
    ''')
    content = result["content"][0]["text"]
    assert "observed failure" in content
    assert "diagnostic [REDACTED]" in content
    assert "sentinel-private-token" not in content
    assert len(content) < 17000


def test_fixture_diagnostics_redact_secrets_across_output_limit(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    token = "sentinel-sensitive-token"
    (tmp_path / "tests/verify.test.mjs").write_text("console.log('x'.repeat(3980)+'" + token + "');")
    (tmp_path.parent / f"{tmp_path.name}-external-secret.txt").write_text("public sentinel")
    result = run_typescript(f'''
        process.env.OPENAI_API_KEY = {token!r};
        import {{ runFixtureChecks }} from "./packages/matt-pocock/tests/real-model-observer.ts";
        console.log(JSON.stringify(await runFixtureChecks({str(tmp_path)!r}, undefined)));
    ''')
    assert "sentinel-sensitive" not in result["content"][0]["text"]
    assert "sentinel-sensitive" not in result["details"]["node"]["stdout"]


def test_completion_tracker_preserves_line_boundaries_across_chunks() -> None:
    result=run_typescript(r'''
        import {acceptanceCompletionTracker} from "./packages/matt-pocock/tests/real-model-observer.ts";
        const marker='MP_ACCEPTANCE_COMPLETE_abcdef';
        const comment='# ok 99 - '+marker+'\n'+'# '.repeat(100)+'\n';
        const checks=[];
        for(let split=0;split<=comment.length;split++) {
          const track=acceptanceCompletionTracker(marker);
          checks.push(track(comment.slice(0,split)),track(comment.slice(split)));
        }
        const track=acceptanceCompletionTracker(marker);
        const actual=[track('x'.repeat(2000)+'\nok 1 - '+marker.slice(0,20)),track(marker.slice(20)+'\n')];
        console.log(JSON.stringify({checks,actual}));
    ''')
    assert not any(result['checks'])
    assert result['actual'] == [False,True]
