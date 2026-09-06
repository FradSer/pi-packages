from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
PROCEDURES = PACKAGE / "procedures"


def run_typescript(script: str) -> dict[str, object]:
    result = subprocess.run(
        ["node", "--import", "tsx/esm", "--input-type=module"],
        cwd=REPO,
        input=textwrap.dedent(script),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_feature_covers_the_catalog_gateway_contract() -> None:
    feature = (PACKAGE / "features" / "matt-pocock.feature").read_text()
    for scenario in (
        "The catalog is the single source of procedure truth",
        "Starting a workflow loads its mandatory dependency closure",
        "A workflow advertises only legal next transitions",
        "The agent explicitly completes or cancels a workflow",
        "Standalone capabilities are reachable without child skills",
        "Conditional references load through the active gateway",
        "The active gateway is progressively disclosed",
        "A prompt cancels active workflow before rerouting",
        "A user explicitly selects a legal next procedure",
        "Agent-document work uses a standalone capability without workflow state",
        "Agent autonomously starts a workflow through the baseline gateway",
        "Known procedure aliases normalize through the catalog",
        "A stale restored workflow explicitly cancels after validation fails",
        "Structured interview questions are available only during an active workflow",
        "Matt Pocock tool rows use operation-specific prefixes",
        "Packed package resolves workspace dependency protocols",
        "Upstream synchronization metadata is verifiable",
    ):
        assert scenario in feature


def test_manifest_declares_one_package_root_extension() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text())
    assert manifest["name"] == "pi-matt-pocock"
    assert manifest["version"] == "0.1.1"
    assert manifest["type"] == "module"
    assert manifest["pi"] == {"extensions": ["./index.ts"]}
    assert "@earendil-works/pi-coding-agent" in manifest["peerDependencies"]
    assert manifest["dependencies"] == {"@fradser/pi-kit": "workspace:*"}
    assert {"index.ts", "src", "procedures", "TODO.md"} <= set(manifest["files"])
    assert "skills" not in manifest["pi"]
    assert (PACKAGE / "index.ts").is_file()


def test_packed_package_resolves_workspace_dependency() -> None:
    temp_dir = tempfile.mkdtemp(prefix="pack-test-")
    try:
        output = subprocess.check_output(
            ["pnpm", "--dir", str(PACKAGE), "pack", "--pack-destination", temp_dir],
            text=True,
        )
        tarball_match = re.search(r"([^\s]+\.tgz)", output)
        assert tarball_match, f"Could not find tarball in output: {output}"
        pkg_json = subprocess.check_output(
            ["tar", "-xOf", tarball_match.group(1), "package/package.json"],
            text=True,
        )
        dep = json.loads(pkg_json)["dependencies"]["@fradser/pi-kit"]
        assert not dep.startswith("workspace:")
        assert re.match(r"^\d+\.\d+\.\d+", dep)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_catalog_classifies_every_resource_and_resolves_all_edges() -> None:
    result = run_typescript("""
        import { readdirSync } from "node:fs";
        import {
          catalogFiles, findProcedure, procedureCatalog, validateProcedureCatalog,
        } from "./packages/matt-pocock/src/catalog.ts";
        const disk = readdirSync("./packages/matt-pocock/procedures").sort();
        const catalog = catalogFiles().sort();
        console.log(JSON.stringify({
          errors: validateProcedureCatalog(), disk, catalog,
          uniqueIds: new Set(procedureCatalog.map((item) => item.id)).size,
          count: procedureCatalog.length,
          aliases: [findProcedure("tight-red-loop")?.id, findProcedure("clarify-goal")?.id],
        }));
    """)
    assert result["errors"] == []
    assert result["disk"] == result["catalog"]
    assert result["uniqueIds"] == result["count"]
    assert result["aliases"] == ["diagnosing-bugs", "wayfinder"]


def test_resolver_loads_dependency_bundle_with_stable_sources_and_size_limit() -> None:
    result = run_typescript("""
        import { MAX_PROCEDURE_BUNDLE_BYTES, resolveProcedureBundle } from "./packages/matt-pocock/src/resolver.ts";
        const bundle = resolveProcedureBundle("improve-codebase-architecture");
        console.log(JSON.stringify({ bundle, maximum: MAX_PROCEDURE_BUNDLE_BYTES }));
    """)
    bundle = result["bundle"]
    assert bundle["root"] == "improve-codebase-architecture"
    assert bundle["loaded"] == ["improve-codebase-architecture", "codebase-design"]
    assert 'source="procedure/improve-codebase-architecture"' in bundle["content"]
    assert 'source="procedure/codebase-design"' in bundle["content"]
    assert "HTML-REPORT" in bundle["availableReferences"]
    assert bundle["byteLength"] <= result["maximum"]


def test_gateway_schema_is_compact_and_catalog_backed() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        import { modelStandaloneCapabilities } from "./packages/matt-pocock/src/catalog.ts";
        import { workflowRoutes } from "./packages/matt-pocock/src/workflow.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;
        const tools = new Map();
        mattPocock({ on() {}, registerCommand() {}, registerTool(tool) { tools.set(tool.name, tool); }, appendEntry() {}, sendUserMessage() {} });
        const variants = tools.get("matt_pocock_workflow").parameters.anyOf;
        console.log(JSON.stringify({
          modes: variants.map((item) => item.properties.mode.const),
          routes: variants[0].properties.route.enum,
          capabilities: variants[1].properties.capability.enum,
          expectedRoutes: workflowRoutes().map((item) => item.route),
          expectedCapabilities: modelStandaloneCapabilities().map((item) => item.id),
        }));
    """)
    assert result["modes"] == ["workflow", "capability", "reference"]
    assert result["routes"] == result["expectedRoutes"]
    assert result["capabilities"] == result["expectedCapabilities"]
    assert "writing-for-agents" in result["capabilities"]


def test_gateway_starts_workflow_with_versioned_work_item_state() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;
        const events = new Map(), tools = new Map(), entries = [];
        let activeTools = ["bash", "matt_pocock_workflow"];
        const pi = {
          on(name, handler) { events.set(name, handler); }, registerCommand() {},
          registerTool(tool) { tools.set(tool.name, tool); },
          appendEntry(customType, data) { entries.push({ customType, data }); }, sendUserMessage() {},
          getActiveTools() { return activeTools; }, setActiveTools(names) { activeTools = names; },
        };
        mattPocock(pi);
        const execution = await tools.get("matt_pocock_workflow").execute(
          "call-1", { mode: "workflow", route: "architecture" }, undefined, undefined, { ui: { setStatus() {} } },
        );
        const prompt = await events.get("before_agent_start")({ systemPrompt: "base" }, {});
        console.log(JSON.stringify({ entries, execution, activeTools, prompt }));
    """)
    state = result["entries"][0]["data"]
    assert state["version"] == 1
    assert re.fullmatch(r"[0-9a-f-]{36}", state["workItemId"])
    assert state | {"workItemId": state["workItemId"]} == {
        "version": 1, "workItemId": state["workItemId"], "route": "architecture",
        "procedure": "improve-codebase-architecture", "phase": "survey",
        "status": "active", "loadedReferences": [],
    }
    text = result["execution"]["content"][0]["text"]
    assert 'source="procedure/improve-codebase-architecture"' in text
    assert 'source="procedure/codebase-design"' in text
    assert "Allowed next: implement, code-review" in text
    assert "matt_pocock_active" in result["activeTools"]
    assert "matt_pocock_ask" in result["activeTools"]
    assert state["workItemId"] in result["prompt"]["systemPrompt"]


def test_model_standalone_writing_for_agents_has_no_persistent_state() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;
        const tools = new Map(), entries = [];
        mattPocock({
          on() {}, registerCommand() {}, registerTool(tool) { tools.set(tool.name, tool); },
          appendEntry(customType, data) { entries.push({ customType, data }); }, sendUserMessage() {},
          getActiveTools() { return ["bash", "matt_pocock_workflow"]; }, setActiveTools() {},
        });
        const execution = await tools.get("matt_pocock_workflow").execute(
          "call-1", { mode: "capability", capability: "writing-for-agents" }, undefined, undefined, { ui: { setStatus() {} } },
        );
        console.log(JSON.stringify({ entries, execution }));
    """)
    assert result["entries"] == []
    assert result["execution"]["details"] == {"mode": "capability", "capability": "writing-for-agents"}
    text = result["execution"]["content"][0]["text"]
    assert "Persistent workflow state: none" in text
    assert 'source="procedure/writing-for-agents"' in text
    assert 'source="procedure/SKILL-MECHANICS"' not in text
    assert "SKILL-MECHANICS" in text


def test_user_invoked_standalone_capability_can_load_its_disclosed_reference() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;
        const tools = new Map();
        mattPocock({
          on() {}, registerCommand() {}, registerTool(tool) { tools.set(tool.name, tool); },
          appendEntry() {}, sendUserMessage() {},
        });
        const execution = await tools.get("matt_pocock_workflow").execute(
          "call-1", { mode: "reference", capability: "setup-matt-pocock-skills", reference: "domain" },
          undefined, undefined, { ui: { setStatus() {} } },
        );
        console.log(JSON.stringify(execution));
    """)
    assert result["details"] == {
        "mode": "reference", "capability": "setup-matt-pocock-skills", "reference": "domain",
    }
    assert 'source="procedure/domain"' in result["content"][0]["text"]


def test_active_gateway_allows_catalog_transition_and_rejects_illegal_transition() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;
        const tools = new Map(), entries = [];
        let activeTools = ["matt_pocock_workflow"];
        const pi = {
          on() {}, registerCommand() {}, registerTool(tool) { tools.set(tool.name, tool); },
          appendEntry(customType, data) { entries.push({ customType, data }); }, sendUserMessage() {},
          getActiveTools() { return activeTools; }, setActiveTools(names) { activeTools = names; },
        };
        mattPocock(pi);
        const ctx = { ui: { setStatus() {} } };
        await tools.get("matt_pocock_workflow").execute("start", { mode: "workflow", route: "architecture" }, undefined, undefined, ctx);
        let illegal;
        try {
          await tools.get("matt_pocock_active").execute("bad", { action: "transition", target: "research" }, undefined, undefined, ctx);
        } catch (error) { illegal = String(error); }
        const legal = await tools.get("matt_pocock_active").execute("good", { action: "transition", target: "implement" }, undefined, undefined, ctx);
        console.log(JSON.stringify({ illegal, legal, entries }));
    """)
    assert "Allowed next procedures: implement, code-review" in result["illegal"]
    assert len(result["entries"]) == 2
    transitioned = result["entries"][-1]["data"]
    assert transitioned["procedure"] == "implement"
    assert transitioned["phase"] == "implement"
    assert result["legal"]["details"]["state"] == transitioned


def test_active_gateway_loads_only_disclosed_references() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;
        const tools = new Map(), entries = [];
        const pi = {
          on() {}, registerCommand() {}, registerTool(tool) { tools.set(tool.name, tool); },
          appendEntry(customType, data) { entries.push({ customType, data }); }, sendUserMessage() {},
          getActiveTools() { return ["matt_pocock_workflow"]; }, setActiveTools() {},
        };
        mattPocock(pi);
        const ctx = { ui: { setStatus() {} } };
        await tools.get("matt_pocock_workflow").execute("start", { mode: "workflow", route: "architecture" }, undefined, undefined, ctx);
        const loaded = await tools.get("matt_pocock_active").execute("load", { action: "load", reference: "HTML-REPORT" }, undefined, undefined, ctx);
        let rejected;
        try {
          await tools.get("matt_pocock_active").execute("bad", { action: "load", reference: "ADR-FORMAT" }, undefined, undefined, ctx);
        } catch (error) { rejected = String(error); }
        console.log(JSON.stringify({ loaded, rejected, entries }));
    """)
    assert 'source="procedure/HTML-REPORT"' in result["loaded"]["content"][0]["text"]
    assert result["entries"][-1]["data"]["loadedReferences"] == ["HTML-REPORT"]
    assert "ADR-FORMAT is not disclosed" in result["rejected"]


def test_complete_and_cancel_persist_explicit_terminal_records_and_disable_active_tools() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;
        const tools = new Map(), entries = [];
        let activeTools = ["bash", "matt_pocock_workflow"];
        const pi = {
          on() {}, registerCommand() {}, registerTool(tool) { tools.set(tool.name, tool); },
          appendEntry(customType, data) { entries.push({ customType, data }); }, sendUserMessage() {},
          getActiveTools() { return activeTools; }, setActiveTools(names) { activeTools = names; },
        };
        mattPocock(pi);
        const ctx = { ui: { setStatus() {} } };
        await tools.get("matt_pocock_workflow").execute("s1", { mode: "workflow", route: "hard-bug" }, undefined, undefined, ctx);
        const completed = await tools.get("matt_pocock_active").execute("c1", { action: "complete" }, undefined, undefined, ctx);
        const afterComplete = [...activeTools];
        await tools.get("matt_pocock_workflow").execute("s2", { mode: "workflow", route: "wayfinding" }, undefined, undefined, ctx);
        const cancelled = await tools.get("matt_pocock_active").execute("c2", { action: "cancel", reason: "blocked externally" }, undefined, undefined, ctx);
        console.log(JSON.stringify({ entries, completed, cancelled, afterComplete, afterCancel: activeTools }));
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
    assert result["activeRecord"] == result["activeState"]
    assert result["activeState"]["status"] == "active"
    assert result["terminalRecord"]["status"] == "completed"
    assert result["terminalState"] is None


def test_session_start_restores_active_record_but_not_terminal_record() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;
        const events = new Map(), restored = [];
        let activeTools = ["bash", "matt_pocock_workflow"];
        const pi = {
          on(name, handler) { events.set(name, handler); }, registerCommand() {}, registerTool() {}, appendEntry() {},
          sendMessage(message, options) { restored.push({ message, options }); }, sendUserMessage() {},
          getActiveTools() { return activeTools; }, setActiveTools(names) { activeTools = names; },
        };
        const active = { version: 1, workItemId: "work-1", route: "hard-bug", procedure: "diagnosing-bugs", phase: "feedback-loop", status: "active", loadedReferences: [] };
        const terminal = { ...active, status: "completed" }; delete terminal.loadedReferences;
        const entry = (data) => ({ type: "custom", customType: "matt-pocock-workflow", data });
        mattPocock(pi);
        const ctx = (records) => ({ sessionManager: { getBranch: () => records }, ui: { setStatus() {}, notify() {} } });
        await events.get("session_start")({}, ctx([entry(active)]));
        const afterActive = [...activeTools];
        await events.get("session_start")({}, ctx([entry(active), entry(terminal)]));
        console.log(JSON.stringify({ restored, afterActive, afterTerminal: activeTools }));
    """)
    assert len(result["restored"]) == 1
    assert result["restored"][0]["message"]["display"] is False
    assert result["restored"][0]["options"] == {"deliverAs": "nextTurn"}
    assert 'source="procedure/diagnosing-bugs"' in result["restored"][0]["message"]["content"]
    assert "matt_pocock_active" in result["afterActive"]
    assert "matt_pocock_ask" in result["afterActive"]
    assert "matt_pocock_active" not in result["afterTerminal"]
    assert "matt_pocock_ask" not in result["afterTerminal"]


def test_invalid_restored_active_record_is_explicitly_cancelled() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;
        const events = new Map(), entries = [], notices = [];
        let activeTools = ["matt_pocock_workflow", "matt_pocock_active", "matt_pocock_ask"];
        const stale = { version: 1, workItemId: "stale-1", route: "wayfinding", procedure: "missing-procedure", phase: "mapping", status: "active", loadedReferences: [] };
        const pi = {
          on(name, handler) { events.set(name, handler); }, registerCommand() {}, registerTool() {},
          appendEntry(customType, data) { entries.push({ customType, data }); }, sendMessage() {}, sendUserMessage() {},
          getActiveTools() { return activeTools; }, setActiveTools(names) { activeTools = names; },
        };
        mattPocock(pi);
        await events.get("session_start")({}, {
          sessionManager: { getBranch: () => [{ type: "custom", customType: "matt-pocock-workflow", data: stale }] },
          ui: { setStatus() {}, notify(message, level) { notices.push({ message, level }); } },
        });
        console.log(JSON.stringify({ entries, notices, activeTools }));
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
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;
        const commands = new Map(), menus = [];
        mattPocock({
          on() {}, registerCommand(name, command) { commands.set(name, command); }, registerTool() {},
          appendEntry() {}, sendUserMessage() {},
        });
        await commands.get("matt-pocock").handler("", {
          hasUI: true,
          ui: { setStatus() {}, notify() {}, select: async (title, choices) => { menus.push({ title, choices }); } },
        });
        console.log(JSON.stringify({ commands: [...commands.keys()], menus }));
    """)
    assert result["commands"] == ["matt-pocock"]
    assert result["menus"] == [{
        "title": "Matt Pocock",
        "choices": ["Start a workflow", "Run a standalone capability", "View current workflow"],
    }]


def test_inactive_guidance_advertises_workflows_and_model_capabilities() -> None:
    result = run_typescript("""
        import { availableWorkflowsGuidance } from "./packages/matt-pocock/src/workflow.ts";
        console.log(JSON.stringify({ guidance: availableWorkflowsGuidance() }));
    """)
    guidance = result["guidance"]
    assert "## Available Matt Pocock Workflows and Capabilities" in guidance
    assert "matt_pocock_workflow" in guidance
    assert "writing-for-agents" in guidance
    assert "matt_pocock_active" in guidance
    assert "Do not activate a workflow for routine work" in guidance


def test_matt_pocock_ask_selection_custom_input_pending_cases() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;
        const tools = new Map();
        let activeTools = ["matt_pocock_workflow"];
        const pi = {
          on() {}, registerCommand() {}, registerTool(tool) { tools.set(tool.name, tool); }, appendEntry() {}, sendUserMessage() {},
          getActiveTools() { return activeTools; }, setActiveTools(names) { activeTools = names; },
        };
        let selectChoice = "Option A", inputChoice = "", lastTimeout = null;
        const ctx = { hasUI: true, ui: {
          setStatus() {}, notify() {},
          select: async (_title, _choices, options) => { lastTimeout = options?.timeout ?? null; return selectChoice; },
          input: async () => inputChoice,
        }};
        mattPocock(pi);
        await tools.get("matt_pocock_workflow").execute("start", { mode: "workflow", route: "hard-bug" }, undefined, undefined, ctx);
        const ask = tools.get("matt_pocock_ask");
        // Case 1: with recommendation and selection
        const selected = await ask.execute("a", { question: "Which scope?", options: ["Option A", "Option B"], recommended: "Option A", timeout_seconds: 30 }, undefined, undefined, ctx);
        const timeoutWithSec = lastTimeout;
        // Case 2: with recommendation and timeout -> automatically adopts recommended
        selectChoice = undefined;
        const timeoutRecommended = await ask.execute("b", { question: "Which scope?", options: ["Option A", "Option B"], recommended: "Option A" }, undefined, undefined, ctx);
        const timeoutDefaultSec = lastTimeout;
        // Case 3: without recommendation -> NO timeout (timeout is null/undefined) and cancel remains pending
        lastTimeout = "not-cleared";
        const noRecommendedCancel = await ask.execute("c", { question: "Which scope?", options: ["Option A", "Option B"] }, undefined, undefined, ctx);
        const noRecommendedTimeout = lastTimeout;
        // Case 4: custom answer
        selectChoice = "Type custom answer..."; inputChoice = "Custom";
        const custom = await ask.execute("d", { question: "Which scope?", options: ["Option A", "Option B"] }, undefined, undefined, ctx);
        // Case 5: no UI
        const noUi = await ask.execute("e", { question: "Which scope?", options: ["Option A", "Option B"] }, undefined, undefined, { hasUI: false, ui: { setStatus() {} } });
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
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;
        const tools = new Map(), renderers = new Map();
        mattPocock({
          on() {}, registerCommand() {}, registerTool(tool) { tools.set(tool.name, tool); },
          registerMessageRenderer(name, renderer) { renderers.set(name, renderer); }, appendEntry() {}, sendUserMessage() {},
        });
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
    assert len(result["workflowRows"]) == 1
    assert "[matt pocock] started · Idea to Ship · Shaping & Requirements" in result["workflowRows"][0]
    assert "Procedure body" not in result["workflowRows"][0]
    assert "[matt pocock] started · Idea to Ship · Shaping & Requirements" in result["messageRows"][0]
    assert "Restored body" not in result["messageRows"][0]


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
