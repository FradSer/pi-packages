from __future__ import annotations

import json
import re
import tarfile
from pathlib import Path

from matt_pocock_helpers import PACKAGE, PROCEDURES, REPO, RUNTIME_HARNESS, run_typescript


def test_capability_mode_targets_are_model_standalone() -> None:
    catalog = json.loads((PACKAGE / "src" / "catalog.json").read_text())
    model_capabilities = {
        definition["id"]
        for definition in catalog
        if definition.get("standalone") and definition.get("invocation") == "model"
    }
    procedures = PACKAGE / "procedures"
    for entry in catalog:
        text = (procedures / entry["file"]).read_text()
        for lineno, line in enumerate(text.splitlines(), 1):
            if "mode `capability`" in line:
                for target in re.findall(r"\[([A-Za-z0-9-]+)\]\(", line):
                    assert target in model_capabilities, f"{entry['file']}:{lineno}: {target}"


def test_manifest_declares_one_package_root_extension() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text())
    assert manifest["name"] == "pi-matt-pocock"
    # The released version belongs to package.json alone; pinning it here would
    # fail the release gate on the version PR that ships it.
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
    assert manifest["type"] == "module"
    assert manifest["pi"] == {"extensions": ["./index.ts"]}
    assert "@earendil-works/pi-coding-agent" in manifest["peerDependencies"]
    assert manifest["dependencies"] == {"@fradser/pi-kit": "workspace:*"}
    assert {"index.ts", "src", "procedures", "TODO.md"} <= set(manifest["files"])
    assert "skills" not in manifest["pi"]
    assert (PACKAGE / "index.ts").is_file()


def test_packed_package_resolves_workspace_dependency(packed_package: Path) -> None:
    with tarfile.open(packed_package) as archive:
        manifest = archive.extractfile("package/package.json")
        assert manifest is not None
        dep = json.load(manifest)["dependencies"]["@fradser/pi-kit"]
    assert not dep.startswith("workspace:")
    assert re.fullmatch(r"\d+\.\d+\.\d+", dep)


def test_gateway_schema_is_compact_and_catalog_backed() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        import { modelStandaloneCapabilities, userStandaloneCapabilities } from "./packages/matt-pocock/src/catalog.ts";
        import { workflowRoutes } from "./packages/matt-pocock/src/workflow.ts";
        const variants = runtime().tools.get("matt_pocock_workflow").parameters.anyOf;
        const byMode = Object.fromEntries(variants.map((item) => [item.properties.mode.const, item]));
        console.log(JSON.stringify({
          modes: variants.map((item) => item.properties.mode.const),
          routes: byMode.workflow.properties.route.enum,
          capabilities: byMode.capability.properties.capability.enum,
          userCapabilities: byMode["user-capability"].properties.capability.enum,
          expectedRoutes: workflowRoutes().map((item) => item.route),
          expectedCapabilities: modelStandaloneCapabilities().map((item) => item.id),
          expectedUserCapabilities: userStandaloneCapabilities().map((item) => item.id),
        }));
    """)
    assert result["modes"] == ["workflow", "capability", "user-capability", "reference"]
    assert result["routes"] == result["expectedRoutes"]
    assert result["capabilities"] == result["expectedCapabilities"]
    assert result["userCapabilities"] == result["expectedUserCapabilities"]
    assert "writing-for-agents" in result["capabilities"]
    assert "deslop" in result["capabilities"]


def test_gateway_starts_workflow_with_versioned_work_item_state() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime();
        const execution = await r.call("matt_pocock_workflow", { mode: "workflow", route: "architecture" });
        const prompt = await r.events.get("before_agent_start")({ systemPrompt: "base" }, r.ctx);
        console.log(JSON.stringify({ entries: r.entries, execution, activeTools: r.active(), prompt }));
    """)
    state = result["entries"][0]["data"]
    assert state["version"] == 1
    assert re.fullmatch(r"[0-9a-f-]{36}", state["workItemId"])
    assert state == {
        "version": 1, "workItemId": state["workItemId"], "route": "architecture",
        "procedure": "improve-codebase-architecture", "phase": "survey",
        "status": "active", "loadedReferences": [],
        # The first step's delivery set is part of the persisted state: a restore
        # reads it to know what this session has already been shown.
        "deliveredProcedures": ["improve-codebase-architecture", "codebase-design"],
    }
    text = result["execution"]["content"][0]["text"]
    assert 'source="procedure/improve-codebase-architecture"' in text
    assert 'source="procedure/codebase-design"' in text
    assert "Allowed next: codebase-design, implement, code-review" in text
    assert "matt_pocock_active" in result["activeTools"]
    assert "matt_pocock_ask" in result["activeTools"]
    assert state["workItemId"] in result["prompt"]["systemPrompt"]


def test_model_standalone_writing_for_agents_has_no_persistent_state() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime();
        const execution = await r.call("matt_pocock_workflow", { mode: "capability", capability: "writing-for-agents" });
        console.log(JSON.stringify({ entries: r.entries, execution }));
    """)
    assert result["entries"] == []
    assert result["execution"]["details"] == {"mode": "capability", "capability": "writing-for-agents"}
    text = result["execution"]["content"][0]["text"]
    assert "Persistent workflow state: none" in text
    assert 'source="procedure/writing-for-agents"' in text
    assert 'source="procedure/SKILL-MECHANICS"' not in text
    assert "SKILL-MECHANICS" in text


def test_user_invoked_standalone_capability_can_load_its_disclosed_reference() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime();
        await r.commands.get("matt-pocock").handler("setup-matt-pocock-skills", r.ctx);
        console.log(JSON.stringify(await r.call("matt_pocock_workflow", {
          mode: "reference", capability: "setup-matt-pocock-skills", reference: "domain",
        })));
    """)
    assert result["details"] == {
        "mode": "reference", "capability": "setup-matt-pocock-skills", "reference": "domain",
    }
    assert 'source="procedure/domain"' in result["content"][0]["text"]


def test_active_gateway_allows_catalog_transition_and_rejects_illegal_transition() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime();
        await r.call("matt_pocock_workflow", { mode: "workflow", route: "architecture" });
        let illegal;
        try { await r.call("matt_pocock_active", { action: "transition", target: "research" }); }
        catch (error) { illegal = String(error); }
        const legal = await r.call("matt_pocock_active", { action: "transition", target: "implement" });
        console.log(JSON.stringify({ illegal, legal, entries: r.entries }));
    """)
    assert "Allowed next procedures: codebase-design, implement, code-review" in result["illegal"]
    assert len(result["entries"]) == 2
    transitioned = result["entries"][-1]["data"]
    assert transitioned["procedure"] == "implement"
    assert transitioned["phase"] == "implement"
    assert result["legal"]["details"]["state"] == transitioned


def test_active_gateway_loads_only_disclosed_references() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime();
        await r.call("matt_pocock_workflow", { mode: "workflow", route: "architecture" });
        const loaded = await r.call("matt_pocock_active", { action: "load", reference: "HTML-REPORT" });
        let rejected;
        try { await r.call("matt_pocock_active", { action: "load", reference: "ADR-FORMAT" }); }
        catch (error) { rejected = String(error); }
        console.log(JSON.stringify({ loaded, rejected, entries: r.entries }));
    """)
    assert 'source="procedure/HTML-REPORT"' in result["loaded"]["content"][0]["text"]
    assert result["entries"][-1]["data"]["loadedReferences"] == ["HTML-REPORT"]
    assert "ADR-FORMAT is not disclosed" in result["rejected"]


def test_complete_and_cancel_persist_explicit_terminal_records_and_disable_active_tools() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime(); await r.start();
        const completed = await r.call("matt_pocock_active", { action: "complete" });
        const afterComplete = [...r.active()];
        await r.call("matt_pocock_workflow", { mode: "workflow", route: "wayfinding" });
        const cancelled = await r.call("matt_pocock_active", { action: "cancel", reason: "blocked externally" });
        console.log(JSON.stringify({ entries: r.entries, completed, cancelled, afterComplete, afterCancel: r.active() }));
    """)
    complete_state = result["completed"]["details"]["state"]
    cancel_state = result["cancelled"]["details"]["state"]
    assert complete_state["version"] == 1 and complete_state["status"] == "completed"
    assert cancel_state["version"] == 1 and cancel_state["status"] == "cancelled"
    assert cancel_state["reason"] == "blocked externally"
    assert complete_state["workItemId"] == result["entries"][0]["data"]["workItemId"]
    assert cancel_state["workItemId"] == result["entries"][2]["data"]["workItemId"]
    assert "matt_pocock_active" not in result["afterComplete"]
    assert "matt_pocock_ask" not in result["afterComplete"]
    assert "matt_pocock_active" not in result["afterCancel"]
    assert "matt_pocock_ask" not in result["afterCancel"]


def test_latest_record_restores_active_and_respects_terminal_state() -> None:
    result = run_typescript("""
        import { latestWorkflowRecord, latestWorkflowState } from "./packages/matt-pocock/src/workflow.ts";
        const active = { version: 1, workItemId: "work-1", route: "hard-bug", procedure: "diagnosing-bugs", phase: "feedback-loop", status: "active", loadedReferences: [] };
        const terminal = { version: 1, workItemId: "work-1", route: "hard-bug", procedure: "diagnosing-bugs", phase: "feedback-loop", status: "completed" };
        const entry = (data) => ({ type: "custom", customType: "matt-pocock-workflow", data });
        console.log(JSON.stringify({
          activeRecord: latestWorkflowRecord([entry(active)]),
          activeState: latestWorkflowState([entry(active)]),
          terminalRecord: latestWorkflowRecord([entry(active), entry(terminal)]),
          terminalState: latestWorkflowState([entry(active), entry(terminal)]) ?? null,
        }));
    """)
    # The live state is the record with the delivery default applied, so a record
    # written before delivery tracking still reads as a complete state.
    assert result["activeState"] == {**result["activeRecord"], "deliveredProcedures": []}
    assert result["activeState"]["status"] == "active"
    assert result["terminalRecord"]["status"] == "completed"
    assert result["terminalState"] is None


def test_session_start_restores_active_record_but_not_terminal_record() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime();
        const active = { version: 1, workItemId: "work-1", route: "hard-bug", procedure: "diagnosing-bugs", phase: "feedback-loop", status: "active", loadedReferences: [] };
        const terminal = { ...active, status: "completed" }; delete terminal.loadedReferences;
        const entry = (data) => ({ type: "custom", customType: "matt-pocock-workflow", data });
        r.setBranch([entry(active)]); await r.events.get("session_start")({}, r.ctx);
        const afterActive = [...r.active()];
        r.setBranch([entry(active), entry(terminal)]); await r.events.get("session_start")({}, r.ctx);
        console.log(JSON.stringify({ restored: r.deliveries(), afterActive, afterTerminal: r.active() }));
    """)
    assert len(result["restored"]) == 1
    assert result["restored"][0]["message"]["display"] is False
    assert result["restored"][0]["options"] == {"triggerTurn": False}
    assert 'source="procedure/diagnosing-bugs"' in result["restored"][0]["message"]["content"]
    assert "matt_pocock_active" in result["afterActive"]
    assert "matt_pocock_ask" in result["afterActive"]
    assert "matt_pocock_active" not in result["afterTerminal"]
    assert "matt_pocock_ask" not in result["afterTerminal"]


def test_invalid_restored_active_record_is_explicitly_cancelled() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime(["matt_pocock_workflow", "matt_pocock_active", "matt_pocock_ask"]);
        const stale = { version: 1, workItemId: "stale-1", route: "wayfinding", procedure: "missing-procedure", phase: "mapping", status: "active", loadedReferences: [] };
        r.setBranch([{ type: "custom", customType: "matt-pocock-workflow", data: stale }]);
        await r.events.get("session_start")({}, r.ctx);
        console.log(JSON.stringify({ entries: r.entries, notices: r.notices, activeTools: r.active() }));
    """)
    terminal = result["entries"][0]["data"]
    assert terminal["version"] == 1
    assert terminal["workItemId"] == "stale-1"
    assert terminal["status"] == "cancelled"
    assert "Restore validation failed" in terminal["reason"]
    assert result["notices"][0]["level"] == "warning"
    assert "missing-procedure" in result["notices"][0]["message"]
    warning = result["notices"][0]["message"]
    assert "Valid procedures for wayfinding:" in warning
    for procedure in ("wayfinder", "research", "prototype", "to-spec", "to-tickets", "implement", "code-review"):
        assert procedure in warning
    assert "matt_pocock_active" not in result["activeTools"]
    assert "matt_pocock_ask" not in result["activeTools"]


def test_menu_includes_standalone_capabilities() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime(), menus = [];
        r.ctx.ui.select = async (title, choices) => { menus.push({ title, choices }); };
        await r.commands.get("matt-pocock").handler("", r.ctx);
        console.log(JSON.stringify({ commands: [...r.commands.keys()], menus }));
    """)
    assert result["commands"] == ["matt-pocock"]
    assert result["menus"] == [{
        "title": "Matt Pocock",
        "choices": ["Start a task", "Start a workflow", "Run a standalone capability", "View current workflow"],
    }]


def test_menu_context_auto_start_forwards_conversation_context() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime();
        r.ctx.ui.select = async () => "Start a task";
        await r.commands.get("matt-pocock").handler("", r.ctx);
        console.log(JSON.stringify({ entries: r.entries, sent: r.deliveries(), userMessages: r.userMessages }));
    """)
    assert result["entries"] == []
    assert result["userMessages"] == []
    assert len(result["sent"]) == 1
    delivery = result["sent"][0]
    assert "recent conversation context" in delivery["message"]["content"]
    assert "matt_pocock_workflow" in delivery["message"]["content"]
    assert "Begin immediately once the route is clear" in delivery["message"]["content"]
    assert delivery["message"]["customType"] == "matt-pocock-procedure"
    assert delivery["message"]["details"] == {"request": ""}
    assert delivery["options"] == {"deliverAs": "followUp", "triggerTurn": True}


def test_menu_context_auto_start_supersedes_active_workflow() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime(); await r.start();
        r.ctx.ui.select = async () => "Start a task";
        await r.commands.get("matt-pocock").handler("", r.ctx);
        console.log(JSON.stringify({ entries: r.entries, sent: r.deliveries(), userMessages: r.userMessages }));
    """)
    assert len(result["entries"]) == 2
    assert result["entries"][0]["data"]["status"] == "active"
    terminal = result["entries"][1]["data"]
    assert terminal["status"] == "cancelled"
    assert terminal["workItemId"] == result["entries"][0]["data"]["workItemId"]
    assert "Superseded" in terminal["reason"]
    assert result["userMessages"] == []
    assert len(result["sent"]) == 1
    content = result["sent"][0]["message"]["content"]
    assert "previous active workflow has been cancelled" in content
    assert "recent conversation context" in content


def test_inactive_guidance_advertises_workflows_and_model_capabilities() -> None:
    result = run_typescript("""
        import { availableWorkflowsGuidance } from "./packages/matt-pocock/src/workflow.ts";
        console.log(JSON.stringify({ guidance: availableWorkflowsGuidance() }));
    """)
    guidance = result["guidance"]
    assert "## Available Matt Pocock Workflows and Capabilities" in guidance
    assert "matt_pocock_workflow" in guidance
    assert "writing-for-agents" in guidance
    assert "Do not activate a workflow for routine work" in guidance
    assert "start a workflow first with matt_pocock_workflow" in guidance
    assert "matt_pocock_active" not in guidance
    assert "matt_pocock_ask" not in guidance


def test_matt_pocock_ask_selection_custom_input_pending_cases() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime(); await r.start();
        let selectChoice = "Option A", inputChoice = "", lastTimeout;
        const select = async (_title, _choices, options) => { lastTimeout = options?.timeout ?? null; return selectChoice; };
        r.ctx.ui.select = select; r.ctx.ui.input = async () => inputChoice;
        const question = { question: "Which scope?", options: ["Option A", "Option B"] };
        const selected = await r.call("matt_pocock_ask", { ...question, recommended: "Option A", timeout_seconds: 30 });
        const timeoutWithSec = lastTimeout;
        selectChoice = undefined;
        await r.call("matt_pocock_ask", { ...question, recommended: "Option A" });
        const timeoutDefaultSec = lastTimeout;
        r.ctx.ui.select = (_title, _choices, { signal }) => new Promise(resolve => signal.addEventListener("abort", () => resolve(undefined), { once: true }));
        const timeoutRecommended = await r.call("matt_pocock_ask", { ...question, recommended: "Option A", timeout_seconds: 0.01 });
        r.ctx.ui.select = select;
        const noRecommendedCancel = await r.call("matt_pocock_ask", question);
        const noRecommendedTimeout = lastTimeout;
        selectChoice = "Type custom answer..."; inputChoice = "Custom";
        const custom = await r.call("matt_pocock_ask", question);
        r.ctx.hasUI = false;
        const noUi = await r.call("matt_pocock_ask", question);
        console.log(JSON.stringify({ selected, timeoutRecommended, noRecommendedCancel, custom, noUi, timeoutWithSec, timeoutDefaultSec, noRecommendedTimeout }));
    """)
    assert result["selected"]["details"]["answer"] == "Option A"
    assert result["timeoutWithSec"] == 30000
    assert result["timeoutDefaultSec"] == 60000
    assert result["timeoutRecommended"]["details"]["answer"] == "Option A"
    assert result["timeoutRecommended"]["details"]["pending"] is False
    assert result["timeoutRecommended"]["details"]["timed_out"] is True
    assert result["timeoutRecommended"]["details"]["source"] == "timeout_recommended"
    assert "User selected (timeout default): Option A" in result["timeoutRecommended"]["content"][0]["text"]
    assert result["noRecommendedTimeout"] is None
    assert result["noRecommendedCancel"]["details"]["pending"] is True
    assert "Do not proceed" in result["noRecommendedCancel"]["content"][0]["text"]
    assert result["custom"]["details"] == {"answer": "Custom", "is_custom": True, "source": "custom_input"}
    assert result["noUi"]["details"] == {"pending": True, "source": "no_ui"}


def test_tool_and_message_rendering_preserves_compact_lifecycle_rows() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const { tools, renderers } = runtime();
        const theme = { fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text };
        const askRows = tools.get("matt_pocock_ask").renderResult(
          { content: [{ type: "text", text: "User selected: A\\nB" }], details: { answer: "A\\nB", source: "choice_selected" } },
          { expanded: false }, theme, { isError: false, args: { question: "Which scope?" } },
        ).render(80);
        const workflowRows = tools.get("matt_pocock_workflow").renderResult(
          { content: [{ type: "text", text: "Procedure body" }], details: { mode: "workflow", route: "idea-to-ship", phase: "shaping" } },
          { expanded: false }, theme, { isError: false, args: {} },
        ).render(80);
        const messageRows = renderers.get("matt-pocock-procedure")(
          { content: "Restored body", details: { route: "idea-to-ship", phase: "shaping" } }, { expanded: false }, theme,
        ).render(80);
        console.log(JSON.stringify({ askRows, workflowRows, messageRows }));
    """)
    assert any("[matt pocock] ask ·" in row for row in result["askRows"])
    assert any("Which scope?" in row for row in result["askRows"])
    assert any("Answer: A" in row for row in result["askRows"])
    assert any("B" in row for row in result["askRows"])
    assert all("\n" not in row for row in result["askRows"])
    workflow_content = next(row for row in result["workflowRows"] if "[matt pocock] started ·" in row)
    message_rows = [row.strip() for row in result["messageRows"][1:-1]]
    assert len(result["workflowRows"]) == 3
    assert "[matt pocock] started · Shaping & Requirements" in workflow_content
    assert "Procedure body" not in workflow_content
    assert message_rows == ["[matt pocock] started", "", "Shaping & Requirements"]
    assert "Restored body" not in "\n".join(result["messageRows"])


def test_ask_expands_only_genuine_decision_metadata() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const { tools, renderers } = runtime();
        const theme = { fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text };
        const cases = {
          selected: { answer: "Option A", source: "choice_selected" },
          recommended: { answer: "Option A", timed_out: true, source: "timeout_recommended" },
          pendingTimeout: { pending: true, timed_out: true, source: "cancelled" },
          noUi: { pending: true, source: "no_ui" },
          custom: { answer: "Custom choice", is_custom: true, source: "custom_input" },
        };
        console.log(JSON.stringify(Object.fromEntries(Object.entries(cases).map(([name, details]) => {
          const render = (expanded) => tools.get("matt_pocock_ask").renderResult(
            { content: [{ type: "text", text: "Model-only decision guidance" }], details }, { expanded }, theme,
            { isError: false, args: { question: "Which scope?" } },
          ).render(160);
          return [name, { rows: render(false), expanded: render(true) }];
        }))));
    """)
    metadata = {
        "recommended": "reason · selection timed out (used recommendation)",
        "pendingTimeout": "reason · selection timed out",
        "noUi": "reason · no UI available",
        "custom": "source · custom input",
    }
    for name, rendered in result.items():
        collapsed = "\n".join(rendered["rows"])
        expanded = "\n".join(rendered["expanded"])
        assert "[matt pocock] ask · Which scope?" in collapsed
        summary = "Status: pending user decision" if name in ("pendingTimeout", "noUi") else "Answer:"
        assert summary in collapsed
        assert "Model-only decision guidance" not in expanded
        if name == "selected":
            assert "to expand" not in collapsed
            assert rendered["rows"] == rendered["expanded"]
        else:
            assert "to expand" in collapsed
            assert metadata[name] not in collapsed
            assert expanded.count(metadata[name]) == 1


def test_native_macos_dialog_environment_guards() -> None:
    result = run_typescript("""
        import { isNativeDialogSupported, macosPrompt } from "./packages/matt-pocock/src/native-dialog.ts";

        const checks = {
          linux: isNativeDialogSupported({ platform: "linux", env: {} }),
          win32: isNativeDialogSupported({ platform: "win32", env: {} }),
          darwinLocal: isNativeDialogSupported({ platform: "darwin", env: {} }),
          darwinSshConnection: isNativeDialogSupported({ platform: "darwin", env: { SSH_CONNECTION: "1.1.1.1 1234 2.2.2.2 22" } }),
          darwinSshClient: isNativeDialogSupported({ platform: "darwin", env: { SSH_CLIENT: "1.1.1.1 1234 22" } }),
          darwinSshTty: isNativeDialogSupported({ platform: "darwin", env: { SSH_TTY: "/dev/pts/1" } }),
          darwinCi: isNativeDialogSupported({ platform: "darwin", env: { CI: "true" } }),
          darwinOptOut: isNativeDialogSupported({ platform: "darwin", env: { PI_NO_NATIVE_DIALOG: "1" } }),
        };

        let linuxError = false;
        try {
          await macosPrompt({ message: "Test" }, { platform: "linux", env: {} });
        } catch {
          linuxError = true;
        }

        let sshError = false;
        try {
          await macosPrompt({ message: "Test" }, { platform: "darwin", env: { SSH_CONNECTION: "true" } });
        } catch {
          sshError = true;
        }

        let buttonLimitError = false;
        try {
          await macosPrompt({ message: "Test", buttons: ["1", "2", "3", "4"] }, { platform: "darwin", env: {} });
        } catch {
          buttonLimitError = true;
        }

        console.log(JSON.stringify({ checks, linuxError, sshError, buttonLimitError }));
    """)
    assert result["checks"]["linux"] is False
    assert result["checks"]["win32"] is False
    assert result["checks"]["darwinLocal"] is True
    assert result["checks"]["darwinSshConnection"] is False
    assert result["checks"]["darwinSshClient"] is False
    assert result["checks"]["darwinSshTty"] is False
    assert result["checks"]["darwinCi"] is False
    assert result["checks"]["darwinOptOut"] is False
    assert result["linuxError"] is True
    assert result["sshError"] is True
    assert result["buttonLimitError"] is True


def test_native_dialog_config_and_ask_integration(tmp_path: Path) -> None:
    cfg_true = tmp_path / "cfg-true.json"
    cfg_true.write_text('{"useNativeDialog": true}\n')
    cfg_false = tmp_path / "cfg-false.json"
    cfg_false.write_text('{"useNativeDialog": false}\n')
    cfg_invalid = tmp_path / "cfg-invalid.json"
    cfg_invalid.write_text('{not valid json}\n')
    agent_dir = tmp_path / "agent-dir"
    agent_dir.mkdir()

    result = run_typescript(RUNTIME_HARNESS + f"""
        import {{ loadConfig, defaultConfigFile }} from "./packages/matt-pocock/src/native-dialog.ts";

        const c1 = loadConfig("{cfg_true}");
        const c2 = loadConfig("{cfg_false}");
        const c3 = loadConfig("{cfg_invalid}");
        const c4 = loadConfig("/nonexistent/file.json");

        // The package config lives in Pi's agent directory, not a hardcoded home path.
        process.env.PI_CODING_AGENT_DIR = "{agent_dir}";
        const overriddenFile = defaultConfigFile();
        const c5 = loadConfig();
        const homeFile = (() => {{
          delete process.env.PI_CODING_AGENT_DIR;
          return defaultConfigFile();
        }})();

        const r = runtime(); await r.start(); let selectCalled = false;
        r.ctx.ui.select = async () => {{ selectCalled = true; return "Option A"; }};
        process.env.PI_MATT_POCOCK_CONFIG_FILE = "{cfg_false}";
        const resTui = await r.call("matt_pocock_ask", {{ title: "Testing Title", question: "Which scope?", options: ["Option A", "Option B"] }});

        console.log(JSON.stringify({{ c1, c2, c3, c4, overriddenFile, c5, homeFile, selectCalled, resTui }}));
    """)
    assert result["c1"]["useNativeDialog"] is True
    assert result["c2"]["useNativeDialog"] is False
    assert result["c3"]["useNativeDialog"] is False
    assert result["c4"]["useNativeDialog"] is False
    assert result["overriddenFile"] == str(agent_dir / "matt-pocock.json")
    # An absent file in the configured agent directory keeps native dialogs off.
    assert result["c5"]["useNativeDialog"] is False
    assert result["homeFile"].endswith(".pi/agent/matt-pocock.json")
    assert result["selectCalled"] is True
    assert result["resTui"]["details"]["answer"] == "Option A"


def test_agent_dir_config_file_is_read_without_an_explicit_path(tmp_path: Path) -> None:
    agent_dir = tmp_path / "agent-dir"
    agent_dir.mkdir()
    (agent_dir / "matt-pocock.json").write_text('{"useNativeDialog": true}\n')

    result = run_typescript(f"""
        import {{ loadConfig }} from "./packages/matt-pocock/src/native-dialog.ts";

        process.env.PI_CODING_AGENT_DIR = "{agent_dir}";
        console.log(JSON.stringify({{ optIn: loadConfig() }}));
    """)
    assert result["optIn"]["useNativeDialog"] is True


def test_deslop_capability_and_ai_slop_baseline_are_bundled() -> None:
    deslop = (PROCEDURES / "deslop.md").read_text()
    review = (PROCEDURES / "code-review.md").read_text()
    for category in ("Fabricated evidence", "Evidence widening", "Defensive clutter", "Mock patching", "Vacuous names"):
        assert category in deslop, f"deslop.md misses {category}"
        assert category in review, f"code-review.md misses {category}"
    assert "CLEAN" in deslop and "PARTIAL" in deslop
    assert "Tests and types must stay green" in deslop
    # The AI slop baseline binds to the same repo-override and tooling-skip rules as the smell baseline.
    assert "repo overrides" in review or "repo standard overrides" in review
    assert "Skip anything tooling enforces" in review or "tooling already enforces" in review


def test_procedures_are_internal_linked_resources() -> None:
    assert not list(PACKAGE.rglob("SKILL.md"))
    for procedure in PROCEDURES.glob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", procedure.read_text()):
            if "://" in target or target.startswith(("#", "./src/")) or target == "link":
                continue
            assert (procedure.parent / target).is_file(), f"{procedure.name}: {target}"


def test_package_documents_installation_and_deferred_automation() -> None:
    readme = (PACKAGE / "README.md").read_text()
    root_readmes = "\n".join((REPO / name).read_text() for name in ("README.md", "README.zh-CN.md"))
    guide = (PACKAGE / "ARCHITECTURE.zh-CN.md").read_text()
    todo = (PACKAGE / "TODO.md").read_text()
    assert "pi install npm:pi-matt-pocock" in readme
    assert "pi install npm:pi-matt-pocock" in root_readmes
    assert "[中文架构说明](ARCHITECTURE.zh-CN.md)" in readme
    for term in ("procedureCatalog", "按需", "workItemId", "schema", "source:procedure/<id>"):
        assert term in guide
    for deferred in ("Automatically create a new Pi session", "Automatically create teammates", "tool-level production-write blocking"):
        assert deferred in todo


def test_tool_descriptions_stay_under_char_budget() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        console.log(JSON.stringify({ description: runtime().tools.get("matt_pocock_workflow").description }));
    """)
    assert len(result["description"]) <= 345


def test_session_start_never_deactivates_the_gateway_tool() -> None:
    """Regression: setActiveTools is an allowlist write, and the tool snapshot a
    session reads at session_start does not necessarily contain this extension's
    own registrations yet. Filtering the snapshot and writing it back therefore
    erased matt_pocock_workflow for the whole session, while /matt-pocock kept
    delivering routing prompts that name it. The seed below omits the gateway
    deliberately: no other fixture can represent the real harness at that point.
    """
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime(["bash", "read"]);
        await r.events.get("session_start")({}, r.ctx);
        const afterIdleStart = [...r.active()]; await r.start();
        const afterStart = [...r.active()];
        await r.call("matt_pocock_active", { action: "complete" });
        console.log(JSON.stringify({ afterIdleStart, afterStart, afterComplete: r.active() }));
    """)
    # Idle session: the gateway is the entry point every routing prompt names, so
    # it must be present even when the snapshot never reported it. The two
    # workflow-state tools stay hidden, and unrelated tools are untouched.
    assert "matt_pocock_workflow" in result["afterIdleStart"]
    assert "matt_pocock_active" not in result["afterIdleStart"]
    assert "matt_pocock_ask" not in result["afterIdleStart"]
    assert result["afterIdleStart"].count("bash") == 1
    assert result["afterIdleStart"].count("read") == 1
    # Active workflow: the two state tools appear, the gateway is not consumed.
    assert {"matt_pocock_workflow", "matt_pocock_active", "matt_pocock_ask"} <= set(result["afterStart"])
    # Terminal state: the two state tools go away, the gateway stays.
    assert "matt_pocock_workflow" in result["afterComplete"]
    assert "matt_pocock_active" not in result["afterComplete"]
    assert "matt_pocock_ask" not in result["afterComplete"]
