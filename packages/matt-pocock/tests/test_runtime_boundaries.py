from __future__ import annotations

from pathlib import Path

import pytest

from matt_pocock_helpers import RUNTIME_HARNESS as HARNESS, run_typescript




def test_extension_instances_do_not_share_workflow_state_or_api() -> None:
    result = run_typescript(HARNESS + '''
        const a = runtime(), b = runtime();
        await a.start();
        const afterA = { a: a.entries.length, b: b.entries.length, toolsA: a.active(), toolsB: b.active() };
        let error;
        try { await b.start(); } catch (e) { error = e.message; }
        console.log(JSON.stringify({ afterA, error, a: a.entries.length, b: b.entries.length }));
    ''')
    assert result["afterA"]["a"] == 1
    assert result["afterA"]["b"] == 0
    assert "matt_pocock_active" in result["afterA"]["toolsA"]
    assert "matt_pocock_active" not in result["afterA"]["toolsB"]
    assert "error" not in result
    assert result["a"] == result["b"] == 1


@pytest.mark.parametrize("event", ["session_tree", "session_compact"])
def test_context_boundaries_reinject_only_current_context(event: str) -> None:
    result = run_typescript(HARNESS + f'''
        const a = runtime();
        await a.start();
        await a.call("matt_pocock_active", {{ action: "transition", target: "implement" }});
        await a.call("matt_pocock_active", {{ action: "transition", target: "diagnosing-bugs" }});
        await a.events.get("{event}")({{}}, a.ctx);
        const message = a.messages.at(-1);
        console.log(JSON.stringify({{ message, entries: a.entries.length }}));
    ''')
    message = result["message"]
    assert message["display"] is False
    assert message["deliveryOptions"] == {"triggerTurn": False}
    assert 'source="procedure/diagnosing-bugs"' in message["content"]
    assert "implement" not in message["details"]["deliveredProcedures"]
    assert result["entries"] == 3


def test_tree_navigation_deactivates_workflow_missing_from_new_branch() -> None:
    result = run_typescript(HARNESS + '''
        const a = runtime(); await a.start(); a.setBranch([]);
        await a.events.get("session_tree")({}, a.ctx);
        console.log(JSON.stringify({ active: a.active(), entries: a.entries.length }));
    ''')
    assert "matt_pocock_active" not in result["active"]
    assert result["entries"] == 1


@pytest.mark.parametrize("bad", ["{ version: 99, status: 'active' }", "null", "{ status: 'completed' }"])
def test_malformed_latest_record_blocks_older_active_state(bad: str) -> None:
    result = run_typescript(HARNESS + f'''
        const a = runtime(); await a.start();
        a.setBranch([...a.entries, {{ type: "custom", customType: "matt-pocock-workflow", data: {bad} }}]);
        await a.events.get("session_start")({{}}, a.ctx);
        console.log(JSON.stringify({{ active: a.active(), messages: a.messages.length, notices: a.notices }}));
    ''')
    assert "matt_pocock_active" not in result["active"]
    assert result["messages"] == 0
    assert result["notices"]


def test_cancel_with_recommendation_remains_pending() -> None:
    result = run_typescript(HARNESS + '''
        const a = runtime(); await a.start();
        const result = await a.call("matt_pocock_ask", { question: "Scope?", options: ["A", "B"], recommended: "A" });
        console.log(JSON.stringify(result));
    ''')
    assert result["details"]["pending"] is True
    assert "answer" not in result["details"]
    assert result["details"]["timed_out"] is False


def test_preaborted_tool_does_not_open_question_or_start_work() -> None:
    result = run_typescript(HARNESS + '''
        const a = runtime(); const controller = new AbortController(); controller.abort();
        let started = false;
        try { await a.call("matt_pocock_workflow", { mode: "workflow", route: "hard-bug" }, controller.signal); started = true; } catch {}
        await a.start(); let opened = false;
        a.ctx.ui.select = async () => { opened = true; return "A"; };
        const answer = await a.call("matt_pocock_ask", { question: "Scope?", options: ["A", "B"], recommended: "A" }, controller.signal);
        console.log(JSON.stringify({ started, opened, answer }));
    ''')
    assert result["started"] is False
    assert result["opened"] is False
    assert result["answer"]["details"]["pending"] is True


def test_native_dialog_config_requires_boolean_true(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"useNativeDialog": "false"}')
    result = run_typescript(f'''
        import {{ loadConfig }} from "./packages/matt-pocock/src/native-dialog.ts";
        console.log(JSON.stringify(loadConfig({str(path)!r})));
    ''')
    assert result["useNativeDialog"] is False


def test_inflight_abort_dismisses_ui_without_adopting_recommendation() -> None:
    result = run_typescript(HARNESS + '''
        const a = runtime(); await a.start(); const controller = new AbortController();
        let forwarded = false;
        a.ctx.ui.select = async (_title, _choices, options) => {
          controller.abort(); forwarded = options.signal.aborted;
          return undefined;
        };
        const result = await a.call("matt_pocock_ask", { question: "Scope?", options: ["A", "B"], recommended: "A" }, controller.signal);
        console.log(JSON.stringify({ forwarded, result }));
    ''')
    assert result["forwarded"] is True
    assert result["result"]["details"] == {"pending": True, "source": "aborted"}


def test_question_answer_is_invalidated_after_branch_change() -> None:
    result = run_typescript(HARNESS + '''
        const a = runtime(); await a.start();
        a.ctx.ui.select = async () => { a.setBranch([]); await a.events.get("session_tree")({}, a.ctx); return "A"; };
        const result = await a.call("matt_pocock_ask", { question: "Scope?", options: ["A", "B"], recommended: "A" });
        console.log(JSON.stringify(result));
    ''')
    assert result["details"] == {"pending": True, "source": "aborted"}


def test_invalid_recommendation_is_rejected_before_showing_ui() -> None:
    result = run_typescript(HARNESS + '''
        const a = runtime(); await a.start(); let opened = false, error;
        a.ctx.ui.select = async () => { opened = true; return undefined; };
        try { await a.call("matt_pocock_ask", { question: "Scope?", options: ["A", "B"], recommended: "C" }); } catch (e) { error = e.message; }
        console.log(JSON.stringify({ opened, error }));
    ''')
    assert result["opened"] is False
    assert "offered option" in result["error"]


def test_reference_bundle_overflow_does_not_persist_partial_state(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.md"
    oversized.write_text("x" * (64 * 1024 + 1))
    result = run_typescript(HARNESS + f'''
        import {{ findProcedure }} from "./packages/matt-pocock/src/catalog.ts";
        import {{ relative }} from "node:path";
        const a = runtime(); await a.start();
        findProcedure("diagnosing-bugs").discloses = ["GLOSSARY"];
        findProcedure("GLOSSARY").file = relative(
            process.cwd() + "/packages/matt-pocock/procedures", {str(oversized)!r});
        const before = a.entries.length; let error;
        try {{ await a.call("matt_pocock_active", {{ action: "load", reference: "GLOSSARY" }}); }}
        catch (e) {{ error = e.message; }}
        console.log(JSON.stringify({{ before, after: a.entries.length, error,
            loaded: a.entries.at(-1).data.loadedReferences }}));
    ''')
    assert "maximum" in result["error"]
    assert result["before"] == result["after"]
    assert result["loaded"] == []


@pytest.mark.parametrize("dialog", ["macosChooseFromList", "macosInputDialog", "macosPrompt"])
def test_native_dialog_abort_reaps_child_process(tmp_path, dialog: str) -> None:
    binary = tmp_path / "osascript"
    binary.write_text('#!/usr/bin/env node\nsetInterval(() => {}, 1000);\n')
    binary.chmod(0o755)
    result = run_typescript(f'''
        import {{ {dialog} }} from "./packages/matt-pocock/src/native-dialog.ts";
        process.env.PATH = {str(tmp_path)!r} + ":" + process.env.PATH;
        const controller = new AbortController();
        setTimeout(() => controller.abort(), 50);
        const start = performance.now();
        const result = await {dialog}({{ prompt: "Q", message: "Q", items: ["A", "B"], signal: controller.signal }}, {{ platform: "darwin", env: {{}} }});
        console.log(JSON.stringify({{ result, elapsed: performance.now() - start }}));
    ''')
    assert result["result"]["action"] == "cancelled"
    assert result["elapsed"] < 2000


def test_gateway_and_question_schemas_enforce_supported_shapes() -> None:
    result = run_typescript(HARNESS + '''
        import { Value } from "typebox/value";
        const a = runtime(); const gateway = a.tools.get("matt_pocock_workflow").parameters;
        const ask = a.tools.get("matt_pocock_ask").parameters;
        console.log(JSON.stringify({
          gateway: Value.Check(gateway, { mode: "workflow", route: "hard-bug", bogus: true }),
          one: Value.Check(ask, { question: "Q", options: ["A"] }),
          duplicate: Value.Check(ask, { question: "Q", options: ["A", "A"], recommended: "A" }),
          negative: Value.Check(ask, { question: "Q", options: ["A", "B"], recommended: "A", timeout_seconds: -1 }),
          missingRecommendation: Value.Check(ask, { question: "Q", options: ["A", "B"], timeout_seconds: 30 }),
          valid: Value.Check(ask, { question: "Q", options: ["A", "B"], recommended: "A", timeout_seconds: 30 }),
        }));
    ''')
    # `recommended` is required, so a question can never run without an answer to adopt.
    assert result == {
        "gateway": False, "one": False, "duplicate": False, "negative": False,
        "missingRecommendation": False, "valid": True,
    }


def test_standalone_nested_references_are_reachable_without_workflow_state() -> None:
    result = run_typescript(HARNESS + '''
        import { findProcedure } from "./packages/matt-pocock/src/catalog.ts";
        const a = runtime();
        findProcedure("research").discloses = ["domain"];
        findProcedure("domain").discloses = ["ADR-FORMAT"];
        await a.call("matt_pocock_workflow", { mode: "capability", capability: "research" });
        const first = await a.call("matt_pocock_workflow", { mode: "reference", capability: "research", reference: "domain" });
        const second = await a.call("matt_pocock_workflow", { mode: "reference", capability: "research", reference: "ADR-FORMAT" });
        console.log(JSON.stringify({ first, second, entries: a.entries.length, active: a.active() }));
    ''')
    assert 'source="procedure/ADR-FORMAT"' in result["second"]["content"][0]["text"]
    assert result["entries"] == 0
    assert "matt_pocock_active" not in result["active"]


def test_catalog_reports_alias_collisions_and_eager_cycles() -> None:
    result = run_typescript('''
        import { findProcedure, validateProcedureCatalog } from "./packages/matt-pocock/src/catalog.ts";
        findProcedure("research").aliases = ["implement"];
        findProcedure("implement").requires = ["research"];
        findProcedure("research").requires = ["implement"];
        console.log(JSON.stringify({ errors: validateProcedureCatalog() }));
    ''')
    assert any("alias" in error for error in result["errors"])
    assert any("cycle" in error.lower() for error in result["errors"])


def test_native_dialog_escalates_when_child_ignores_termination(tmp_path) -> None:
    binary = tmp_path / "osascript"
    binary.write_text('#!/usr/bin/env node\nprocess.on("SIGTERM", () => {});\nprocess.stdout.write("ready");\nsetInterval(() => {}, 1000);\n')
    binary.chmod(0o755)
    result = run_typescript(f'''
        import {{ macosChooseFromList }} from "./packages/matt-pocock/src/native-dialog.ts";
        process.env.PATH = {str(tmp_path)!r} + ":" + process.env.PATH;
        const start = performance.now();
        const result = await macosChooseFromList({{ prompt: "Q", items: ["A", "B"], timeoutSeconds: 0.3 }}, {{ platform: "darwin", env: {{}} }});
        console.log(JSON.stringify({{ result, elapsed: performance.now() - start }}));
    ''')
    assert result["result"]["action"] == "timed_out"
    assert 300 <= result["elapsed"] < 2500


def test_native_process_failure_is_distinct_from_user_cancellation(tmp_path) -> None:
    binary = tmp_path / "osascript"
    binary.write_text('#!/usr/bin/env node\nprocess.exit(1);\n')
    binary.chmod(0o755)
    result = run_typescript(f'''
        import {{ macosChooseFromList }} from "./packages/matt-pocock/src/native-dialog.ts";
        process.env.PATH = {str(tmp_path)!r} + ":" + process.env.PATH;
        let error;
        try {{ await macosChooseFromList({{ prompt: "Q", items: ["A", "B"] }}, {{ platform: "darwin", env: {{}} }}); }} catch (e) {{ error = e.message; }}
        console.log(JSON.stringify({{ error }}));
    ''')
    assert result["error"] == "Native dialog process failed."


def test_clock_readings_cannot_turn_cancellation_into_timeout() -> None:
    result = run_typescript(HARNESS + '''
        const r = runtime(); await r.start();
        let reads = 0;
        performance.now = () => reads++ === 0 ? 0 : 60000;
        const result = await r.call("matt_pocock_ask", { question: "Scope?", options: ["A", "B"], recommended: "A" });
        console.log(JSON.stringify(result));
    ''')
    assert result["details"] == {"pending": True, "timed_out": False, "source": "cancelled"}


def test_question_deadline_dismisses_ui_and_adopts_recommendation() -> None:
    result = run_typescript(HARNESS + '''
        const r = runtime(); await r.start(); let dismissed = false;
        r.ctx.ui.select = (_title, _options, { signal }) => new Promise(resolve => {
          signal.addEventListener("abort", () => { dismissed = true; resolve(undefined); }, { once: true });
        });
        const result = await r.call("matt_pocock_ask", { question: "Scope?", options: ["A", "B"], recommended: "A", timeout_seconds: 0.01 });
        console.log(JSON.stringify({ result, dismissed }));
    ''')
    assert result["dismissed"] is True
    assert result["result"]["details"] == {
        "answer": "A", "is_custom": False, "timed_out": True,
        "pending": False, "source": "timeout_recommended",
    }


def test_disabling_custom_input_preserves_literal_option_labels() -> None:
    result = run_typescript(HARNESS + '''
        const r = runtime(); await r.start(); let opened = false;
        r.ctx.ui.select = async () => "Type custom answer...";
        r.ctx.ui.input = async () => { opened = true; return "unintended"; };
        const result = await r.call("matt_pocock_ask", {
          question: "Scope?", options: ["Type custom answer...", "B"], recommended: "B", allow_custom: false,
        });
        console.log(JSON.stringify({ result, opened }));
    ''')
    assert result["opened"] is False
    assert result["result"]["details"] == {
        "answer": "Type custom answer...", "is_custom": False, "source": "choice_selected",
    }
