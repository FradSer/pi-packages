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
    directories = {"workflow": "procedures", "utility": "procedures", "reference": "references", "asset": "assets"}
    for entry in catalog:
        text = (PACKAGE / directories[entry["kind"]] / entry["file"]).read_text()
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
    assert {"index.ts", "src", "procedures", "references", "assets", "TODO.md"} <= set(manifest["files"])
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
        const prompt = {sections: {}};
        const reply = await r.events.get("before_agent_start")({ systemPrompt: "base", systemPromptOptions: prompt }, r.ctx);
        if (reply !== undefined) throw new Error("Additive guidance must not return an override");
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
    assert state["workItemId"] in result["prompt"]["sections"]["matt_pocock_workflow"]


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
        import { latestWorkflowRecord } from "./packages/matt-pocock/src/workflow.ts";
        const active = { version: 1, workItemId: "work-1", route: "hard-bug", procedure: "diagnosing-bugs", phase: "feedback-loop", status: "active", loadedReferences: [] };
        const terminal = { version: 1, workItemId: "work-1", route: "hard-bug", procedure: "diagnosing-bugs", phase: "feedback-loop", status: "completed" };
        const entry = (data) => ({ type: "custom", customType: "matt-pocock-workflow", data });
        console.log(JSON.stringify({
          activeRecord: latestWorkflowRecord([entry(active)]),
          terminalRecord: latestWorkflowRecord([entry(active), entry(terminal)]),
        }));
    """)
    assert result["activeRecord"] == {
        "version": 1,
        "workItemId": "work-1",
        "route": "hard-bug",
        "procedure": "diagnosing-bugs",
        "phase": "feedback-loop",
        "status": "active",
        "loadedReferences": [],
    }
    assert result["terminalRecord"]["status"] == "completed"


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


def test_ask_result_quotes_only_the_selected_answer_and_retains_the_question() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime(); await r.start();
        const question = "若项目没有可运行的 E2E 测试，也不能产出真实运行证据，应如何结束？";
        const recommended = "(Recommended) 允许寻找替代验证；仍无真实证据时报告 needs_review 或阻塞";
        const selectedOption = "继续寻找替代验证";
        const trailingRecommended = "允许寻找替代验证；仍无真实证据时报告 needs_review 或阻塞 (Recommended)";
        r.ctx.ui.select = async () => trailingRecommended;
        const trailingSelected = await r.call("matt_pocock_ask", {
          question, options: [trailingRecommended, selectedOption], recommended: trailingRecommended,
        });
        r.ctx.ui.select = async () => recommended;
        const selectedRecommendation = await r.call("matt_pocock_ask", {
          question, options: [recommended, selectedOption], recommended,
        });
        r.ctx.ui.select = async () => selectedOption;
        const selectedAlternative = await r.call("matt_pocock_ask", {
          question, options: [recommended, selectedOption], recommended,
        });
        r.ctx.ui.select = (_title, _choices, { signal }) =>
          new Promise(resolve => signal.addEventListener("abort", () => resolve(undefined), { once: true }));
        const timedOut = await r.call("matt_pocock_ask", {
          question, options: [recommended, selectedOption], recommended, timeout_seconds: 0.01,
        });
        console.log(JSON.stringify({ trailingSelected, selectedRecommendation, selectedAlternative, timedOut }));
    """)
    expected_question = "若项目没有可运行的 E2E 测试，也不能产出真实运行证据，应如何结束？"
    expected_recommendation = "允许寻找替代验证；仍无真实证据时报告 needs_review 或阻塞"
    assert result["trailingSelected"]["content"][0]["text"] == (
        f"{expected_question}\n\n> {expected_recommendation}"
    )
    assert result["selectedRecommendation"]["content"][0]["text"] == (
        f"{expected_question}\n\n> {expected_recommendation}"
    )
    assert result["selectedAlternative"]["content"][0]["text"] == (
        f"{expected_question}\n\n> 继续寻找替代验证"
    )
    assert result["timedOut"]["content"][0]["text"] == (
        f"{expected_question}\n\n> {expected_recommendation}"
    )
    assert "(Recommended)" not in result["trailingSelected"]["content"][0]["text"]
    assert "(Recommended)" not in result["selectedRecommendation"]["content"][0]["text"]
    assert "(Recommended)" not in result["timedOut"]["content"][0]["text"]
    assert "继续寻找替代验证" not in result["timedOut"]["content"][0]["text"]
    assert result["trailingSelected"]["details"]["answer"] == expected_recommendation + " (Recommended)"
    assert result["selectedRecommendation"]["details"]["answer"] == "(Recommended) " + expected_recommendation
    assert result["timedOut"]["details"]["answer"] == "(Recommended) " + expected_recommendation
    assert result["timedOut"]["details"]["source"] == "timeout_recommended"


def test_matt_pocock_ask_selection_custom_input_pending_cases() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime(); await r.start();
        let selectChoice = "Option A", inputChoice = "", lastTimeout;
        const select = async (_title, _choices, options) => { lastTimeout = options?.timeout ?? null; return selectChoice; };
        r.ctx.ui.select = select; r.ctx.ui.input = async () => inputChoice;
        const question = { question: "Which scope?", options: ["Option A", "Option B"], recommended: "Option A" };
        const selected = await r.call("matt_pocock_ask", { ...question, timeout_seconds: 30 });
        const timeoutWithSec = lastTimeout;
        selectChoice = undefined;
        await r.call("matt_pocock_ask", question);
        const timeoutDefaultSec = lastTimeout;
        r.ctx.ui.select = (_title, _choices, { signal }) => new Promise(resolve => signal.addEventListener("abort", () => resolve(undefined), { once: true }));
        const timeoutRecommended = await r.call("matt_pocock_ask", { ...question, timeout_seconds: 0.01 });
        r.ctx.ui.select = select;
        selectChoice = undefined;
        const cancelled = await r.call("matt_pocock_ask", question);
        selectChoice = "Type custom answer..."; inputChoice = "Custom";
        const custom = await r.call("matt_pocock_ask", question);
        inputChoice = "";
        const blankCustom = await r.call("matt_pocock_ask", question);
        r.ctx.hasUI = false;
        const noUi = await r.call("matt_pocock_ask", question);
        console.log(JSON.stringify({ selected, timeoutRecommended, cancelled, custom, blankCustom, noUi, timeoutWithSec, timeoutDefaultSec }));
    """)
    assert result["selected"]["details"]["answer"] == "Option A"
    assert result["timeoutWithSec"] == 30000
    assert result["timeoutDefaultSec"] == 60000
    assert result["timeoutRecommended"]["details"]["answer"] == "Option A"
    assert result["timeoutRecommended"]["details"]["pending"] is False
    assert result["timeoutRecommended"]["details"]["timed_out"] is True
    assert result["timeoutRecommended"]["details"]["source"] == "timeout_recommended"
    assert result["timeoutRecommended"]["content"][0]["text"] == "Which scope?\n\n> Option A"
    assert result["cancelled"]["details"] == {"pending": True, "timed_out": False, "source": "cancelled"}
    assert "Do not proceed" in result["cancelled"]["content"][0]["text"]
    assert result["custom"]["details"] == {"answer": "Custom", "is_custom": True, "source": "custom_input"}
    assert result["blankCustom"]["details"] == {"pending": True, "source": "custom_input_cancelled"}
    assert result["noUi"]["details"] == {"pending": True, "source": "no_ui"}


def test_every_ask_requires_a_recommendation_and_arms_a_default_deadline() -> None:
    """A question with no recommendation cannot exist, so no ask can wait indefinitely."""
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime(); await r.start();
        const question = { question: "Which scope?", options: ["Option A", "Option B"] };
        let opened = false, missingError = "";
        r.ctx.ui.select = async () => { opened = true; return "Option A"; };
        try { await r.call("matt_pocock_ask", question); } catch (error) { missingError = String(error); }
        let selectorTimeout = null;
        r.ctx.ui.select = (_title, _choices, options) => { selectorTimeout = options?.timeout ?? null; return Promise.resolve("Option A"); };
        const answered = await r.call("matt_pocock_ask", { ...question, recommended: "Option A" });
        r.ctx.ui.select = (_title, _choices, { signal }) => new Promise(resolve => signal.addEventListener("abort", () => resolve(undefined), { once: true }));
        const adopted = await r.call("matt_pocock_ask", { ...question, recommended: "Option B", timeout_seconds: 0.01 });
        console.log(JSON.stringify({ opened, missingError, selectorTimeout, answered, adopted }));
    """)
    assert result["opened"] is False
    assert "must match an offered option" in result["missingError"]
    assert result["selectorTimeout"] == 60000
    assert result["answered"]["details"]["answer"] == "Option A"
    assert result["adopted"]["details"] == {
        "answer": "Option B", "is_custom": False, "timed_out": True,
        "pending": False, "source": "timeout_recommended",
    }


def test_the_default_deadline_adopts_the_recommendation() -> None:
    """A question with no explicit timeout still expires and adopts, exactly like an explicit one.

    The stubbed clock only moves the armed timer's schedule: the verdict comes from that
    timer, so a clock reading can never turn a cancellation into a recommendation.
    """
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime(); await r.start();
        const base = Date.now(); let reads = 0;
        Date.now = () => reads++ === 0 ? base : base + 61_000 * reads;
        let selectorTimeout = null, aborted = false;
        r.ctx.ui.select = (_title, _choices, options) => {
          selectorTimeout = options?.timeout ?? null;
          return new Promise(resolve => options.signal.addEventListener("abort", () => { aborted = true; resolve(undefined); }, { once: true }));
        };
        const adopted = await r.call("matt_pocock_ask", { question: "Which scope?", options: ["Option A", "Option B"], recommended: "Option B" });
        console.log(JSON.stringify({ selectorTimeout, aborted, adopted }));
    """)
    assert result["selectorTimeout"] == 60000
    assert result["aborted"] is True
    assert result["adopted"]["details"] == {
        "answer": "Option B", "is_custom": False, "timed_out": True,
        "pending": False, "source": "timeout_recommended",
    }
    assert result["adopted"]["content"][0]["text"] == "Which scope?\n\n> Option B"


def test_a_custom_answer_input_keeps_the_same_deadline() -> None:
    """The custom-answer phase shares the ask deadline, so it cannot hang either."""
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime(); await r.start();
        r.ctx.ui.select = async () => "Type custom answer...";
        let inputTimeout = null;
        r.ctx.ui.input = (_question, _placeholder, options) => {
          inputTimeout = options?.timeout ?? null;
          return new Promise(resolve => options.signal.addEventListener("abort", () => resolve(undefined), { once: true }));
        };
        const adopted = await r.call("matt_pocock_ask", {
          question: "Which scope?", options: ["Option A", "Option B"], recommended: "Option B", timeout_seconds: 0.05,
        });
        console.log(JSON.stringify({ inputTimeout, adopted }));
    """)
    assert result["inputTimeout"] is not None and result["inputTimeout"] <= 50
    assert result["adopted"]["details"] == {
        "answer": "Option B", "is_custom": False, "timed_out": True,
        "pending": False, "source": "timeout_recommended",
    }


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


def test_ask_shows_decision_metadata_inline() -> None:
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
        # Every Matt Pocock row shows its facts by default: metadata is part of the
        # collapsed row and never waits behind Ctrl+O.
        assert "to expand" not in collapsed
        assert rendered["rows"] == rendered["expanded"]
        if name != "selected":
            assert collapsed.count(metadata[name]) == 1


def test_native_macos_dialog_environment_guards() -> None:
    result = run_typescript("""
        import { isNativeDialogSupported, macosInputDialog } from "./packages/matt-pocock/src/native-dialog.ts";

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
          await macosInputDialog({ prompt: "Test" }, { platform: "linux", env: {} });
        } catch {
          linuxError = true;
        }

        let sshError = false;
        try {
          await macosInputDialog({ prompt: "Test" }, { platform: "darwin", env: { SSH_CONNECTION: "true" } });
        } catch {
          sshError = true;
        }

        let buttonLimitError = false;
        try {
          await macosInputDialog({ prompt: "Test", buttons: ["1", "2", "3", "4"] }, { platform: "darwin", env: {} });
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
        const resTui = await r.call("matt_pocock_ask", {{ title: "Testing Title", question: "Which scope?", options: ["Option A", "Option B"], recommended: "Option A" }});

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
    for resource in [*PROCEDURES.glob("*.md"), *(PACKAGE / "references").glob("*.md")]:
        for target in re.findall(r"\]\(([^)]+)\)", resource.read_text()):
            if "://" in target or target.startswith(("#", "./src/")) or target == "link":
                continue
            assert (resource.parent / target).is_file(), f"{resource.name}: {target}"


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


# ── test_lifecycle_titles.py ──
"""Render real gateway results: phase titles belong in rows, ids in state."""


import pytest

from matt_pocock_helpers import PACKAGE, RUNTIME_HARNESS, run_typescript

PHASE_TITLES = {
    "shaping": "Shaping & Requirements",
    "research": "Research & Feasibility",
    "prototype": "Prototyping",
    "to-spec": "Specification Design",
    "to-tickets": "Task Decomposition",
    "implement": "Implementation",
    "code-review": "Code Review",
    "handoff": "Handoff & Summary",
    "mapping": "Initiative Mapping",
    "triage": "Task Triage",
    "feedback-loop": "Reproducing & Diagnostics",
    "survey": "Architecture Survey",
    "design-review": "Architecture Design",
}
ROUTES = ("idea-to-ship", "wayfinding", "triage", "hard-bug", "architecture")


@pytest.fixture(scope="module")
def lifecycle_results() -> dict[str, object]:
    return run_typescript(RUNTIME_HARNESS + """
        import { workflowRoutes, workflowDefinitions, workflowPlacement } from "./packages/matt-pocock/src/catalog.ts";
        import { visibleWidth } from "@earendil-works/pi-tui";
        const r = runtime(["bash", "matt_pocock_workflow"]);
        const { tools, events, renderers, entries, ctx } = r;
        const theme = { fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text };
        const gateway = tools.get("matt_pocock_workflow"), active = tools.get("matt_pocock_active");
        const execute = (tool, args) => tool.execute("test", args, undefined, undefined, ctx);
        const render = (tool, result, expanded = false, width = 160) => tool.renderResult(
          result, { expanded, isPartial: false }, theme, { isError: false, args: {} },
        ).render(width);
        const restore = (state) => events.get("session_start")({}, {
          ...ctx, sessionManager: { getBranch: () => [{ type: "custom", customType: "matt-pocock-workflow", data: state }] },
        });
        const starts = [], phases = [], transitions = [], terminals = [];
        for (const { route, title: routeTitle } of workflowRoutes()) {
          const started = await execute(gateway, { mode: "workflow", route });
          starts.push({ route, routeTitle, details: started.details, rows: render(gateway, started), expanded: render(gateway, started, true) });
          await execute(active, { action: "cancel", reason: "test reset" });
          for (const definition of workflowDefinitions(route)) {
            const placement = workflowPlacement(route, definition.id);
            const state = {
              version: 1, workItemId: `test-${route}-${definition.id}`, route,
              procedure: definition.id, phase: placement.phase, status: "active", loadedReferences: [],
            };
            await restore(state);
            const restored = r.deliveries().at(-1);
            phases.push({
              route, routeTitle, state, restored,
              rows: renderers.get("matt-pocock-procedure")(restored.message, { expanded: false }, theme).render(160),
              expanded: renderers.get("matt-pocock-procedure")(restored.message, { expanded: true }, theme).render(160),
            });
            for (const target of placement.allowedNext) {
              await restore(state);
              const result = await execute(active, { action: "transition", target });
              transitions.push({ route, routeTitle, details: result.details, rows: render(active, result), expanded: render(active, result, true) });
            }
            for (const action of ["complete", "cancel"]) {
              await restore(state);
              const result = await execute(active, action === "cancel" ? { action, reason: "test cancellation" } : { action });
              const status = action === "complete" ? "completed" : "cancelled";
              // Old persisted subjects must not override the event's recorded phase on reload.
              const historical = { ...result, details: { ...result.details, subject: `${route} ${status}` } };
              const narrow = render(active, result, false, 48);
              terminals.push({
                route, routeTitle, action, before: state, details: result.details,
                record: entries.at(-1).data, content: result.content, activeTools: [...r.active()],
                rows: render(active, result), expanded: render(active, result, true), historicalRows: render(active, historical),
                narrowBounded: narrow.every((line) => !line.includes("\\n") && visibleWidth(line) <= 48),
                result, historical,
              });
            }
          }
        }
        await execute(gateway, { mode: "workflow", route: "architecture" });
        const cancelled = terminals.find((item) => item.action === "cancel").historical;
        const cancellationsWithoutReason = [undefined, "", " \\t\\r\\n ", "\\u001b[31m\\u001b[0m", "\\u001b]52;c;QUJD\\u0007"].map((reason) => {
          const historical = { ...cancelled, details: { ...cancelled.details, state: { ...cancelled.details.state, reason } } };
          return { reason: reason ?? null, rows: render(active, historical), expanded: render(active, historical, true) };
        });
        // Rerender after another work item starts: never consult mutable active state.
        for (const item of terminals) {
          const snapshot = JSON.stringify(item.result);
          item.rerenderedRows = render(active, item.result);
          item.rerenderedExpanded = render(active, item.result, true);
          item.historicalRows = render(active, item.historical);
          item.historicalExpanded = render(active, item.historical, true);
          item.unchangedAfterRender = snapshot === JSON.stringify(item.result);
          delete item.result; delete item.historical;
        }
        const historicalTransitions = transitions.map((item) => {
          const historical = { content: [], details: { ...item.details, subject: `${item.route} · old phase title` } };
          return { ...item, rows: render(active, historical), expanded: render(active, historical, true) };
        });
        const loaded = await execute(active, { action: "load", reference: "HTML-REPORT" });
        const standalone = await execute(gateway, { mode: "capability", capability: "research" });
        const reference = await execute(gateway, { mode: "reference", capability: "writing-for-agents", reference: "SKILL-MECHANICS" });
        console.log(JSON.stringify({
          starts, phases, transitions, terminals, historicalTransitions, cancellationsWithoutReason,
          nonWorkflow: Object.fromEntries([
            ["loaded", active, loaded], ["standalone", gateway, standalone], ["reference", gateway, reference],
            ["fallback", active, { content: [{ type: "text", text: "Model-only guidance" }], details: { model: "model-only metadata" } }],
          ].map(([name, tool, result]) => [name, {
            rows: render(tool, result), expanded: render(tool, result, true), details: result.details,
          }])),
        }));
    """)


def assert_phase_row(rows: list[str], label: str, phase: str, route: str, route_title: str, suffix: str = "") -> None:
    header = next(row for row in rows if "[matt pocock]" in row)
    assert f"[matt pocock] {label} · {PHASE_TITLES[phase]}{suffix}" in header
    assert route not in header
    assert f"[matt pocock] {label} · {route_title} · {PHASE_TITLES[phase]}" not in header


def assert_phase_block(rows: list[str], phase: str, route: str) -> None:
    """Messages render the head, a blank band row, then the body."""
    content = [row.strip() for row in rows[1:-1]]
    assert content == ["[matt pocock] started", "", PHASE_TITLES[phase]]
    assert route not in "\n".join(rows)


@pytest.mark.parametrize("route", ROUTES)
def test_workflow_start_rows_use_only_entry_phase(lifecycle_results: dict[str, object], route: str) -> None:
    start = next(item for item in lifecycle_results["starts"] if item["route"] == route)
    assert_phase_row(start["rows"], "started", start["details"]["phase"], route, start["routeTitle"])
    collapsed = "\n".join(start["rows"])
    expanded = "\n".join(start["expanded"])
    # The start row is the whole message: nothing is held back for Ctrl+O, so the
    # first screen a user sees is the complete row. Phase titles of entry phases
    # are unique per route, so the row needs no route field to stay unambiguous.
    assert "to expand" not in collapsed
    assert "route ·" not in collapsed
    # The row is exactly the label and the entry phase title: no route title rides
    # along, which the triage entry would otherwise duplicate as a substring.
    assert [row.strip() for row in start["rows"]] == ["", f"[matt pocock] started · {PHASE_TITLES[start['details']['phase']]}", ""]
    assert start["expanded"] == start["rows"]
    assert "route ·" not in expanded
    assert "phase ·" not in expanded
    assert "procedure-source" not in expanded
    assert start["details"]["route"] == route


@pytest.mark.parametrize("route", ROUTES)
def test_restored_procedure_rows_use_recorded_phase(lifecycle_results: dict[str, object], route: str) -> None:
    phases = [item for item in lifecycle_results["phases"] if item["route"] == route]
    assert phases
    for item in phases:
        assert_phase_block(item["rows"], item["state"]["phase"], route)
        # A restore re-delivers the whole active closure, so its message details are
        # the recorded state plus the delivery set this restore showed.
        details = item["restored"]["message"]["details"]
        assert {key: value for key, value in details.items() if key != "deliveredProcedures"} == item["state"]
        assert item["state"]["procedure"] in details["deliveredProcedures"]
        assert item["restored"]["message"]["display"] is False
        assert item["restored"]["options"] == {"triggerTurn": False}
        assert "to expand" not in "\n".join(item["rows"])
        assert item["expanded"] == item["rows"]


@pytest.mark.parametrize("route", ROUTES)
def test_transition_rows_use_destination_phase(lifecycle_results: dict[str, object], route: str) -> None:
    for key in ("transitions", "historicalTransitions"):
        transitions = [item for item in lifecycle_results[key] if item["route"] == route]
        assert transitions
        for item in transitions:
            phase = item["details"]["state"]["phase"]
            assert_phase_row(item["rows"], "event", phase, route, item["routeTitle"])
            assert item["details"]["subject"] == PHASE_TITLES[phase]
            assert item["details"]["action"] == "transition"
            assert "to expand" not in "\n".join(item["rows"])
            assert "action ·" not in "\n".join(item["expanded"])
            assert item["expanded"] == item["rows"]


@pytest.mark.parametrize("action,status", [("complete", "completed"), ("cancel", "cancelled")])
@pytest.mark.parametrize("route", ROUTES)
def test_terminal_rows_use_actual_phase_and_keep_workflow_contract(
    lifecycle_results: dict[str, object], route: str, action: str, status: str,
) -> None:
    terminals = [item for item in lifecycle_results["terminals"] if item["route"] == route and item["action"] == action]
    assert terminals
    for item in terminals:
        before = item["before"]
        phase = before["phase"]
        assert item["details"]["subject"] == f"{PHASE_TITLES[phase]} {status}"
        for key in ("rows", "historicalRows", "rerenderedRows"):
            assert_phase_row(item[key], "event", phase, route, item["routeTitle"], f" {status}")
        terminal = item["details"]["state"]
        assert terminal == item["record"]
        assert terminal["status"] == status
        for key in ("version", "route", "phase", "procedure", "workItemId"):
            assert terminal[key] == before[key]
        if action == "cancel":
            assert terminal["reason"] == "test cancellation"
        assert item["activeTools"] == ["bash", "matt_pocock_workflow"]
        assert f"Workflow {before['workItemId']} {status}." in item["content"][0]["text"]
        assert item["narrowBounded"]
        assert item["details"]["action"] == action
        assert item["unchangedAfterRender"]
        for key in ("expanded", "historicalExpanded", "rerenderedExpanded"):
            expanded = "\n".join(item[key])
            assert "action ·" not in expanded
            assert "to expand" not in expanded
            assert_phase_row(item[key], "event", phase, route, item["routeTitle"], f" {status}")
            # Every Matt Pocock row shows its facts by default: nothing is held back
            # for Ctrl+O, so the expanded render repeats the collapsed one.
            assert item[key] == item["rows"]
        for key in ("rows", "historicalRows", "rerenderedRows"):
            collapsed = "\n".join(item[key])
            assert "to expand" not in collapsed
            if action == "cancel":
                assert collapsed.count("reason · test cancellation") == 1
                assert collapsed.count("test cancellation") == 1
            else:
                assert "test cancellation" not in collapsed


def test_cancellation_without_nonblank_reason_does_not_expand(lifecycle_results: dict[str, object]) -> None:
    cases = lifecycle_results["cancellationsWithoutReason"]
    assert [item["reason"] for item in cases] == [None, "", " \t\r\n ", "\x1b[31m\x1b[0m", "\x1b]52;c;QUJD\x07"]
    for item in cases:
        collapsed = "\n".join(item["rows"])
        assert "Shaping & Requirements cancelled" in collapsed
        assert "to expand" not in collapsed
        assert "action ·" not in "\n".join(item["expanded"])
        assert "reason ·" not in "\n".join(item["expanded"])
        assert item["expanded"] == item["rows"]


def test_non_workflow_rows_keep_their_subjects(lifecycle_results: dict[str, object]) -> None:
    expected = {
        "loaded": "event · loaded HTML Report",
        "standalone": "started · Research",
        "reference": "started · Writing For Agents · Skill Mechanics",
        "fallback": "event · workflow updated",
    }
    for key, subject in expected.items():
        result = lifecycle_results["nonWorkflow"][key]
        collapsed = "\n".join(result["rows"])
        assert f"[matt pocock] {subject}" in collapsed
        assert "to expand" not in collapsed
        assert result["expanded"] == result["rows"]
        for hidden in ("action ·", "capability ·", "reference ·", "procedure-source", "Model-only guidance", "model-only metadata"):
            assert hidden not in "\n".join(result["expanded"])
    assert lifecycle_results["nonWorkflow"]["loaded"]["details"]["action"] == "load"
    assert lifecycle_results["nonWorkflow"]["standalone"]["details"] == {"mode": "capability", "capability": "research"}
    assert lifecycle_results["nonWorkflow"]["reference"]["details"] == {
        "mode": "reference", "capability": "writing-for-agents", "reference": "SKILL-MECHANICS",
    }


def test_all_standalone_tool_and_message_names_use_catalog_labels() -> None:
    result = run_typescript(RUNTIME_HARNESS + '''
        import {standaloneCapabilities} from "./packages/matt-pocock/src/catalog.ts";
        const r=runtime();
        const theme={fg:(_c,t)=>t,bg:(_c,t)=>t,bold:t=>t};
        const tool=r.tools.get('matt_pocock_workflow');
        console.log(JSON.stringify(standaloneCapabilities().map(c=>{
          const details={mode:'capability',capability:c.id};
          const rows=tool.renderResult({content:[],details},{expanded:false,isPartial:false},theme,{isError:false,args:{}}).render(160);
          const message=r.renderers.get('matt-pocock-procedure')({content:'model only',details},{expanded:false},theme).render(160);
          const task=r.renderers.get('matt-pocock-procedure')({content:'model only',details:{...details,request:'Keep my exact_task-name'}},{expanded:false},theme).render(160);
          return {id:c.id,label:c.label,rows,message,task};
        })));
    ''')
    assert len(result) == 21
    for entry in result:
        assert f"started · {entry['label']}" in '\n'.join(entry['rows'])
        assert entry['label'] in '\n'.join(entry['message'])
        assert 'Keep my exact_task-name' in '\n'.join(entry['task'])


def test_transition_menu_uses_labels_and_keeps_internal_targets() -> None:
    result=run_typescript(RUNTIME_HARNESS + '''
        const r=runtime(); await r.start(); let menu;
        r.ctx.ui.select=async(title,choices)=>{menu={title,choices};return choices[0];};
        await r.commands.get('matt-pocock').handler('transition',r.ctx);
        console.log(JSON.stringify({menu,state:r.entries.at(-1).data}));
    ''')
    assert 'Hard Bug Diagnosis' in result['menu']['title']
    assert 'Reproducing & Diagnostics' in result['menu']['title']
    assert result['menu']['choices'] == ['Implementation', 'Code Review']
    assert result['state']['procedure'] == 'implement'


def test_all_transition_menu_choices_match_destination_lifecycle_titles() -> None:
    result = run_typescript(RUNTIME_HARNESS + '''
        import { workflowRoutes, workflowDefinitions, workflowPlacement } from "./packages/matt-pocock/src/catalog.ts";
        import { readablePhaseTitle } from "./packages/matt-pocock/src/workflow.ts";
        const menus = [];
        for (const { route } of workflowRoutes()) {
          for (const { id } of workflowDefinitions(route)) {
            const placement = workflowPlacement(route, id);
            if (!placement.allowedNext.length) continue;
            const r = runtime();
            r.setBranch([{type: "custom", customType: "matt-pocock-workflow", data: {
              version: 1, workItemId: "menu-test", route, procedure: id,
              phase: placement.phase, status: "active", loadedReferences: [],
            }}]);
            await r.events.get("session_start")({}, r.ctx);
            let choices;
            r.ctx.ui.select = async (_title, offered) => { choices = offered; return undefined; };
            await r.commands.get("matt-pocock").handler("transition", r.ctx);
            menus.push({choices, expected: placement.allowedNext.map(target => readablePhaseTitle(workflowPlacement(route, target).phase))});
          }
        }
        console.log(JSON.stringify(menus));
    ''')
    assert result
    for menu in result:
        assert menu['choices'] == menu['expected']


def test_all_reference_rows_preserve_names_and_width_including_saved_results() -> None:
    result = run_typescript(RUNTIME_HARNESS + '''
        import { procedureCatalog } from "./packages/matt-pocock/src/catalog.ts";
        import { visibleWidth } from "@earendil-works/pi-tui";
        const r = runtime();
        const theme = { fg: (_color, text) => text, bg: (_color, text) => text, bold: text => text };
        const references = procedureCatalog.filter(item => item.kind === "reference" || item.kind === "asset");
        const cases = references.flatMap(item => [
          ["matt_pocock_active", {action: "load", reference: item.id}],
          ["matt_pocock_active", {action: "load", subject: `loaded ${item.id}`}],
          ["matt_pocock_workflow", {mode: "reference", capability: "writing-for-agents", reference: item.id}],
        ].map(([name, details]) => {
          const render = (width, expanded) => r.tools.get(name).renderResult(
            {content: [{type: "text", text: "Model-only resource body"}], details},
            {expanded, isPartial: false}, theme, {isError: false, args: {}},
          ).render(width);
          return {label: item.label, rows: render(160, false), expanded: render(160, true),
            bounded: [24, 48, 80].every(width => [false, true].every(expanded => render(width, expanded).every(line => !line.includes("\\n") && visibleWidth(line) <= width)))};
        }));
        console.log(JSON.stringify(cases));
    ''')
    assert result
    for case in result:
        assert case['label'] in '\n'.join(case['rows'])
        assert case['bounded']
        assert 'Model-only resource body' not in '\n'.join(case['expanded'])


def test_all_tool_errors_use_shared_failure_style_and_pending_background() -> None:
    result = run_typescript(RUNTIME_HARNESS + r'''
        import { visibleWidth } from "@earendil-works/pi-tui";
        const r = runtime();
        const cases = [...r.tools.values()].map(tool => {
          const backgrounds = [];
          const theme = {fg: (_color, text) => text, bg: (color, text) => {backgrounds.push(color); return text;}, bold: text => text};
          const render = (width, expanded, isError, isPartial) => tool.renderResult(
            {content: [{type: "text", text: "Error: invalid target\nTry an allowed target."}], details: {}},
            {expanded, isPartial}, theme, {isError, args: {}},
          ).render(width);
          const failure = render(160, false, true, false);
          render(80, false, false, true);
          return {name: tool.name, failure, errorBackground: backgrounds.includes("toolErrorBg"), pendingBackground: backgrounds.includes("toolPendingBg"),
            bounded: [24, 48, 80].every(width => [false, true].every(expanded => render(width, expanded, true, false).every(line => !line.includes("\n") && visibleWidth(line) <= width)))};
        });
        console.log(JSON.stringify(cases));
    ''')
    assert len(result) == 3
    for case in result:
        assert '[matt pocock] failed ·' in '\n'.join(case['failure'])
        assert case['errorBackground'] and case['pendingBackground'] and case['bounded']


# ── test_matt_pocock_prompt_composition.py ──
from matt_pocock_helpers import RUNTIME_HARNESS, run_typescript


def test_workflow_guidance_appends_without_prompt_override() -> None:
    """Given either run type, When guidance is added, Then owner text stays intact."""
    result = run_typescript(RUNTIME_HARNESS + '''
      const {buildSystemPrompt} = await import(process.env.PI_PROMPT_BUILDER ?? "./node_modules/@earendil-works/pi-coding-agent/dist/core/system-prompt.js");
      const r = runtime();
      const observations = [];
      for (const active of [false, true]) {
        if (active) await r.start();
        for (const start of [{messageType:"user",prompt:"hello"},{messageType:"custom"}]) {
          const options = {cwd:process.cwd(), sections:{other:"retained"}, promptGuidelines:["existing"],customPrompt:"owner"};
          const reply = await r.events.get("before_agent_start")({...start,systemPrompt:"owner",systemPromptOptions:options},r.ctx);
          observations.push({reply:reply ?? null,options,active,rendered:buildSystemPrompt(options),defaultRendered:buildSystemPrompt({...options,customPrompt:undefined})});
        }
      }
      console.log(JSON.stringify({observations}));
    ''')
    for row in result["observations"]:
        assert "Matt Pocock" in row["rendered"]
        assert "Matt Pocock" in row["defaultRendered"]
        assert row["rendered"].startswith("owner")
        assert row["reply"] is None
        assert row["options"]["customPrompt"] == "owner"
        guidelines = row["options"]["promptGuidelines"]
        assert guidelines[0] == "existing"
        assert guidelines == ["existing"]
        assert row["options"]["sections"]["other"] == "retained"
        assert ("workflow active:" in row["options"]["sections"]["matt_pocock_workflow"]) == row["active"]


# ── test_pi_v1_resolution.py ──
"""Check package-local resolution rather than only the root Pi installation."""

import json
import subprocess
import textwrap

from matt_pocock_helpers import PACKAGE, REPO


def test_package_resolves_pi_v1_without_narrowing_published_peers() -> None:
    script = '''
        import { fileURLToPath } from "node:url";
        import { dirname, join } from "node:path";
        import { readFileSync, existsSync } from "node:fs";
        const parentUrl = new URL("./packages/matt-pocock/package.json", import.meta.url).href;
        const names = ["pi-coding-agent", "pi-ai", "pi-tui"].map(name => `@earendil-works/${name}`);
        console.log(JSON.stringify(Object.fromEntries(names.map(name => {
          let directory = dirname(fileURLToPath(import.meta.resolve(name, parentUrl)));
          while (true) {
            const file = join(directory, "package.json");
            if (existsSync(file)) {
              const manifest = JSON.parse(readFileSync(file, "utf8"));
              if (manifest.name === name) return [name, manifest.version];
            }
            const parent = dirname(directory);
            if (parent === directory) throw new Error(`No manifest for ${name}`);
            directory = parent;
          }
        }))));
    '''
    process = subprocess.run(
        ["node", "--experimental-import-meta-resolve", "--input-type=module"],
        input=textwrap.dedent(script), cwd=REPO, text=True, capture_output=True, timeout=30,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    # The root development requirement is the cohort of record; this asserts package-local
    # resolution matches it rather than pinning the version a fourth time.
    expected = json.loads((REPO / "package.json").read_text())["devDependencies"]["@earendil-works/pi-coding-agent"].lstrip("^")
    assert set(result.values()) == {expected}, result
    manifest = json.loads((PACKAGE / "package.json").read_text())
    for name in result:
        assert name not in manifest.get("dependencies", {})
    for name in ("@earendil-works/pi-coding-agent", "@earendil-works/pi-tui"):
        assert manifest["peerDependencies"][name] == "*"


def test_live_fixtures_use_valid_pi_v1_api_signatures() -> None:
    # Recursive: the real-Pi harnesses and their fixtures live in tests/live/.
    fixtures = sorted((PACKAGE / "tests").rglob("*.ts"))
    assert fixtures
    process = subprocess.run(
        ["bun", "x", "tsc", "--noEmit", "--strict", "--skipLibCheck",
         "--target", "ES2022", "--module", "ESNext", "--moduleResolution", "bundler",
         "--allowImportingTsExtensions", "--types", "node", *map(str, fixtures)],
        cwd=REPO, text=True, capture_output=True, timeout=60,
    )
    assert process.returncode == 0, process.stdout + process.stderr


# ── test_pi_schema_compatibility.py ──
"""Root provider hints must preserve Pi v1 validation and normalization."""
import pytest

from matt_pocock_helpers import RUNTIME_HARNESS, run_typescript


@pytest.fixture(scope="module")
def compatibility() -> dict[str, object]:
    return run_typescript(RUNTIME_HARNESS + '''
        import { Type } from "typebox";
        import { Value } from "typebox/value";
        import { validateToolArguments } from "@earendil-works/pi-ai";
        const r = runtime();
        const result = { count: 0, valueDifferences: 0, piDifferences: 0,
            nonNullableDifferences: 0, examples: [] };
        const values = [undefined, "implement", "", null, false, 0, 0.5, [], {}];
        function validate(tool, arguments_) {
            try { return { accepted: true, arguments: validateToolArguments(tool,
                { name: tool.name, arguments: arguments_ }) }; }
            catch { return { accepted: false }; }
        }
        for (const name of ["matt_pocock_workflow", "matt_pocock_active"]) {
            const tool = r.tools.get(name);
            const original = { ...tool, parameters: Type.Union(tool.parameters.anyOf) };
            const brokenParameters = structuredClone(tool.parameters);
            for (const [field, schema] of Object.entries(brokenParameters.properties)) {
                if (schema.anyOf) brokenParameters.properties[field] =
                    schema.anyOf.find(branch => branch.type !== "null");
            }
            const broken = { ...tool, parameters: brokenParameters };
            const gateway = name === "matt_pocock_workflow";
            const fields = gateway ? ["mode", "route", "capability", "reference"]
                : ["action", "target", "reference", "reason"];
            const choices = gateway ? ["workflow", "capability", "reference"]
                : ["transition", "load", "complete", "cancel"];
            const pools = fields.map((field, i) => i === 0
                ? [undefined, ...choices, "wrong", null, false, 0, 0.5, [], {}]
                : field === "route" ? [undefined, "hard-bug", "wrong", ...values.slice(2)]
                : field === "capability" ? [undefined, "tdd", "teach", "wrong", ...values.slice(2)]
                : values);
            function compare(arguments_) {
                result.count++;
                if (Value.Check(original.parameters, arguments_) !==
                    Value.Check(tool.parameters, arguments_)) result.valueDifferences++;
                const expected = JSON.stringify(validate(original, arguments_));
                const actual = JSON.stringify(validate(tool, arguments_));
                if (expected !== actual) {
                    result.piDifferences++;
                    if (result.examples.length < 3) result.examples.push({ name, arguments_ });
                }
                if (expected !== JSON.stringify(validate(broken, arguments_)))
                    result.nonNullableDifferences++;
            }
            function expand(index, arguments_) {
                if (index === fields.length) {
                    compare(arguments_);
                    compare({ ...arguments_, extra: "undeclared" });
                    return;
                }
                for (const value of pools[index]) expand(index + 1, value === undefined
                    ? arguments_ : { ...arguments_, [fields[index]]: value });
            }
            for (const root of [null, false, 0, 0.5, "text", [], {}]) compare(root);
            expand(0, {});
        }
        console.log(JSON.stringify(result));
    ''')


def test_pi_acceptance_and_normalized_arguments_remain_equivalent(compatibility) -> None:
    """Given root hints, Pi accepts and normalizes exactly the original branches."""
    assert compatibility["count"] > 5_000
    assert compatibility["valueDifferences"] == 0
    assert compatibility["piDifferences"] == 0, compatibility["examples"]


def test_matrix_detects_optional_null_deletion_without_nullable_hints(compatibility) -> None:
    assert compatibility["nonNullableDifferences"] > 0


# ── test_json_type_boundaries.py ──
"""Every JSON value class at the public tool boundary, not arbitrary JS values."""
import pytest

from matt_pocock_helpers import RUNTIME_HARNESS, run_typescript


@pytest.fixture(scope="module")
def boundary_results() -> dict[str, object]:
    return run_typescript(RUNTIME_HARNESS + '''
        import { Value } from "typebox/value";
        const r = runtime();
        const values = [null, false, 0, 1.5, "text", [], {}];
        const definitions = [...r.tools.values()];
        const invalidRoots = Object.fromEntries(definitions.map(tool => [tool.name,
            values.map(value => Value.Check(tool.parameters, value))]));
        const gateway = r.tools.get("matt_pocock_workflow").parameters;
        const active = r.tools.get("matt_pocock_active").parameters;
        const ask = r.tools.get("matt_pocock_ask").parameters;
        const nonStrings = values.filter(value => typeof value !== "string");
        console.log(JSON.stringify({invalidRoots,
            targets:nonStrings.map(target=>Value.Check(active,{action:"transition",target})),
            references:nonStrings.map(reference=>Value.Check(active,{action:"load",reference})),
            routes:nonStrings.map(route=>Value.Check(gateway,{mode:"workflow",route})),
            capabilities:nonStrings.map(capability=>Value.Check(gateway,{mode:"capability",capability})),
            options:nonStrings.map(option=>Value.Check(ask,{question:"Q",options:["A",option]})),
            valid:[Value.Check(gateway,{mode:"workflow",route:"hard-bug"}),
                   Value.Check(active,{action:"transition",target:"implement"}),
                   Value.Check(active,{action:"load",reference:"LOGIC"}),
                   Value.Check(active,{action:"complete"}),
                   Value.Check(active,{action:"cancel",reason:"test"}),
                   Value.Check(ask,{question:"Q",options:["A","B"],recommended:"A"})]
        }));
    ''')


def test_every_json_root_type_is_rejected_without_required_shape(boundary_results) -> None:
    assert set(boundary_results["invalidRoots"]) == {"matt_pocock_workflow", "matt_pocock_active", "matt_pocock_ask"}
    assert all(not any(values) for values in boundary_results["invalidRoots"].values())


@pytest.mark.parametrize("field", ["targets", "references", "routes", "capabilities", "options"])
def test_non_string_identifiers_and_labels_are_rejected(boundary_results, field: str) -> None:
    assert not any(boundary_results[field])


def test_valid_operation_shapes_remain_accepted(boundary_results) -> None:
    assert all(boundary_results["valid"])


# ── test_active_contract.py ──
"""Active gateway contract: exact JSON shapes in guidance and strict schemas."""


from matt_pocock_helpers import RUNTIME_HARNESS, run_typescript


def test_gateway_and_decision_guidance_disambiguate_real_model_arguments() -> None:
    result = run_typescript(RUNTIME_HARNESS + '''
        const r = runtime(); await r.start();
        const gateway = r.tools.get("matt_pocock_workflow");
        const ask = r.tools.get("matt_pocock_ask");
        let rejected = "";
        try {
          await r.call("matt_pocock_ask", {
            question: "Scope?", options: ["Whole receipt (Recommended)", "Per line"],
            recommended: "Whole receipt",
          });
        } catch (error) { rejected = String(error); }
        console.log(JSON.stringify({
          gateway: gateway.promptGuidelines.join("\\n"),
          recommendation: ask.parameters.properties.recommended.description,
          rejected,
        }));
    ''')
    gateway = str(result["gateway"])
    for shape in ('{"mode": "workflow", "route"', '{"mode": "capability", "capability"', '{"mode": "reference", "capability"'):
        assert shape in gateway
    assert "exact copy" in result["recommendation"]
    assert "including annotations" in result["recommendation"]
    assert "must match an offered option" in result["rejected"]


def test_active_guidance_states_exact_tool_contract() -> None:
    result = run_typescript("""
        import { workflowGuidance, routeEntryState } from "./packages/matt-pocock/src/workflow.ts";
        const state = routeEntryState("hard-bug", "work-1");
        console.log(JSON.stringify({ guidance: workflowGuidance(state, ["REF-A"]) }));
    """)
    guidance = str(result["guidance"])
    assert '{"action": "transition", "target"' in guidance
    assert '{"action": "load", "reference"' in guidance
    assert '{"action": "complete"}' in guidance
    assert '{"action": "cancel", "reason"' in guidance


def test_active_gateway_schemas_reject_undeclared_fields() -> None:
    result = run_typescript(RUNTIME_HARNESS + """
        import { Value } from "typebox/value";
        const active = runtime().tools.get("matt_pocock_active");
        const branches = active.parameters.anyOf ?? [];
        const strict = branches.map((branch) => branch.additionalProperties === false);
        const guidelines = (active.promptGuidelines ?? []).join("\\n");
        console.log(JSON.stringify({
          branchCount: branches.length,
          strict,
          guidelines,
          transitionExtra: Value.Check(active.parameters, { action: "transition", target: "x", bogus: 1 }),
          loadExtra: Value.Check(active.parameters, { action: "load", reference: "x", bogus: 1 }),
          completeExtra: Value.Check(active.parameters, { action: "complete", bogus: 1 }),
          cancelExtra: Value.Check(active.parameters, { action: "cancel", reason: "x", bogus: 1 }),
        }));
    """)
    assert result["branchCount"] == 4
    assert result["strict"] == [True, True, True, True]
    assert result["transitionExtra"] is False
    assert result["loadExtra"] is False
    assert result["completeExtra"] is False
    assert result["cancelExtra"] is False
    guidelines = str(result["guidelines"])
    for shape in (
        '"action": "transition"',
        '"action": "load"',
        '"action": "complete"',
        '"action": "cancel"',
    ):
        assert shape in guidelines


def test_delivered_state_contract_includes_terminal_calls() -> None:
    result = run_typescript(RUNTIME_HARNESS + '''
        const r = runtime();
        const value = await r.start();
        console.log(JSON.stringify(value));
    ''')
    text = '\n'.join(part.get('text','') for part in result['content'])
    assert '{"action":"complete"}' in text
    assert '{"action":"cancel","reason":"<why>"}' in text


def test_catalog_guidance_supplies_exact_calls_for_every_entry() -> None:
    result = run_typescript('''
        import {availableWorkflowsGuidance} from "./packages/matt-pocock/src/workflow.ts";
        import {modelStandaloneCapabilities,userStandaloneCapabilities,workflowRoutes} from "./packages/matt-pocock/src/catalog.ts";
        const guidance = availableWorkflowsGuidance();
        console.log(JSON.stringify({
          capabilities:modelStandaloneCapabilities().map(c=>guidance.includes(JSON.stringify({mode:"capability",capability:c.id}))),
          userCapabilities:userStandaloneCapabilities().map(c=>guidance.includes(`- ${c.id}:`)),
          userCapabilityCall:guidance.includes(JSON.stringify({mode:"user-capability",capability:"<id>"})),
          routes:workflowRoutes().map(r=>guidance.includes(JSON.stringify({mode:"workflow",route:r.route}))),
        }));
    ''')
    assert all(result['capabilities'])
    assert all(result['userCapabilities'])
    assert all(result['routes'])


def test_operation_schemas_expose_all_choices_at_the_object_root() -> None:
    result = run_typescript(RUNTIME_HARNESS + '''
        const r = runtime();
        console.log(JSON.stringify(Object.fromEntries(
          ['matt_pocock_workflow','matt_pocock_active'].map(name=>[name,r.tools.get(name).parameters])
        )));
    ''')
    for name,field,values in [
        ('matt_pocock_workflow','mode',['workflow','capability','user-capability','reference']),
        ('matt_pocock_active','action',['transition','load','complete','cancel']),
    ]:
        schema=result[name]
        assert schema.get('type') == 'object'
        assert schema['properties'][field]['enum'] == values
        assert schema['additionalProperties'] is False


# ── test_orchestration_contract.py ──
"""Reach the shipped engineering instructions through the real catalog resolver."""


import re

import pytest

from matt_pocock_helpers import run_typescript


@pytest.fixture(scope="module")
def instructions() -> dict[str, object]:
    return run_typescript('''
        import { resolveProcedureBundle } from "./packages/matt-pocock/src/resolver.ts";
        import { routeEntryState, workflowGuidance, workflowRoutes } from "./packages/matt-pocock/src/workflow.ts";
        const bundles = Object.fromEntries(["implement", "code-review"].map(id => [id, resolveProcedureBundle(id)]));
        const guidance = workflowRoutes().map(({ route }) => workflowGuidance(routeEntryState(route, "test-work"), []));
        console.log(JSON.stringify({ bundles, guidance }));
    ''')


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def test_every_active_workflow_drives_to_completion_and_yields_only_when_blocked(instructions: dict[str, object]) -> None:
    for text in instructions["guidance"]:
        guidance = normalized(text)
        for rule in ("integrated candidate", "blocking reviews", "findings resolved"):
            assert rule in guidance
        # Reaching the end of the work, not the end of one slice, is the finish line.
        assert "Drive the current procedure to its end" in guidance
        assert "Do not end the turn to ask whether to continue" in guidance
        # The old text told the agent to stop whenever only teammate results were out;
        # that instruction is what ended a long task partway through.
        assert "yield with the workflow still active" not in guidance
        assert "Yield only when the remaining work genuinely depends" in guidance


def test_implementation_bundle_scopes_checks_and_freezes_a_candidate(instructions: dict[str, object]) -> None:
    bundle = instructions["bundles"]["implement"]
    text = normalized(bundle["content"])
    for rule in ("one integration owner", "local checks", "safe", "same candidate", "affected evidence", "blocking reviews"):
        assert rule in text
    assert "Run typechecking regularly, single test files regularly" not in text
    assert bundle["byteLength"] <= 64 * 1024


def test_review_only_bundle_returns_findings_without_owning_repairs(instructions: dict[str, object]) -> None:
    text = normalized(instructions["bundles"]["code-review"]["content"])
    for rule in ("Review-only", "return the report", "including REWORK", "without editing", "without waiting for repairs", "Leader or implementation owner"):
        assert rule in text, rule


def test_recheck_bundle_refreshes_brief_before_work_assignment(instructions: dict[str, object]) -> None:
    text = normalized(instructions["bundles"]["code-review"]["content"])
    for rule in ("preserve the prior findings", "authoritative brief", "before reopening", "does not update the description", "candidate fingerprint", "correction delta", "bounded follow-up", "dependsOn"):
        assert rule in text, rule
    assert "with the original brief and findings" not in text


def test_review_bundle_supports_local_spec_and_proportional_review(instructions: dict[str, object]) -> None:
    bundle = instructions["bundles"]["code-review"]
    text = normalized(bundle["content"])
    for rule in ("confirmed conversation", "untracked", "unrelated", "candidate", "one fresh reviewer", "REWORK", "reopen", "root cause"):
        assert rule in text
    for obsolete in (
        "delegate the two independent axes to separate teammates",
        "If they didn't specify one, ask for it",
        "If the teammate facility is available, give each teammate one brief",
    ):
        assert obsolete not in text
    assert "Standards" in text and "Spec" in text and "Refute-before-PASS" in text
    assert bundle["byteLength"] <= 64 * 1024


def test_each_step_contract_provides_exact_callable_state_controls() -> None:
    from matt_pocock_helpers import RUNTIME_HARNESS
    result = run_typescript(RUNTIME_HARNESS + '''
        const r = runtime();
        const started = await r.call("matt_pocock_workflow", {mode:"workflow",route:"hard-bug"});
        const transitioned = await r.call("matt_pocock_active", {action:"transition",target:"implement"});
        console.log(JSON.stringify({started:started.content[0].text, transitioned:transitioned.content[0].text}));
    ''')
    assert '{"action":"transition","target":"implement"}' in result["started"]
    assert '{"action":"transition","target":"code-review"}' in result["transitioned"]
    assert "Failed controls do not change" in result["transitioned"]


# ── test_user_capability_routing.py ──
"""A user-invocation capability must be reachable when the user asks for it.

Before this contract, `modelStandaloneCapabilities()` was the only source for the
gateway capability enum and the injected guidance, so every `invocation: "user"`
capability — grill-me among them — was invisible to the model. The user said "grill
me" and the package was never called.

These cases assert the observable seams only: the public tool schema, the injected
system prompt, and the tool result. They do not assert private helper calls.
"""

from matt_pocock_helpers import RUNTIME_HARNESS, run_typescript

USER_CAPABILITIES = [
    "grill-me",
    "handoff",
    "retro",
    "improve-codebase-architecture",
    "setup-matt-pocock-skills",
    "teach",
    "to-questionnaire",
    "wait-what",
]


def _gateway_shapes() -> dict[str, object]:
    return run_typescript(RUNTIME_HARNESS + """
        const variants = runtime().tools.get("matt_pocock_workflow").parameters.anyOf;
        const byMode = Object.fromEntries(variants.map((item) => [item.properties.mode.const, item]));
        console.log(JSON.stringify({
          modes: variants.map((item) => item.properties.mode.const),
          rootModes: runtime().tools.get("matt_pocock_workflow").parameters.properties.mode.enum,
          model: byMode.capability.properties.capability.enum,
          user: byMode["user-capability"].properties.capability.enum,
        }));
    """)


def test_user_invocation_capabilities_are_offered_by_the_gateway_schema() -> None:
    """Given the gateway schema, every user-invocation capability has a branch."""
    shapes = _gateway_shapes()
    assert shapes["modes"] == ["workflow", "capability", "user-capability", "reference"]
    assert "user-capability" in shapes["rootModes"]
    assert shapes["user"] == USER_CAPABILITIES
    assert "grill-me" in shapes["user"]
    # The two enums stay disjoint: capability mode keeps autonomous model work,
    # user-capability mode carries only what the user asked for by name.
    assert not set(shapes["user"]) & set(shapes["model"])


def test_injected_guidance_names_every_user_invocation_capability() -> None:
    """Given an inactive session, the prompt tells the model what the user can ask for."""
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime();
        const options = {sections: {}};
        const reply = await r.events.get("before_agent_start")({ systemPrompt: "base", systemPromptOptions: options }, r.ctx);
        if (reply !== undefined) throw new Error("Additive guidance must not return an override");
        console.log(JSON.stringify({ prompt: Object.values(options.sections).join("\\n") }));
    """)
    prompt = result["prompt"]
    assert '"mode":"user-capability","capability":"<id>"' in prompt
    for capability in USER_CAPABILITIES:
        assert f"- {capability}:" in prompt, capability
    assert '"mode":"capability","capability":"grill-me"' not in prompt
    # The model-reachable list must not quietly absorb the user-invocation ones.
    assert '"mode":"capability","capability":"grilling"' in prompt


def test_user_requested_capability_delivers_its_dependency_closure_without_state() -> None:
    """Given an explicit user request, the capability runs and creates no workflow state."""
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime();
        const execution = await r.call("matt_pocock_workflow", {
          mode: "user-capability", capability: "grill-me",
        });
        console.log(JSON.stringify({
          execution, entries: r.entries, active: r.active(), deliveries: r.deliveries(),
        }));
    """)
    text = result["execution"]["content"][0]["text"]
    assert 'source="procedure/grill-me"' in text
    # grill-me requires grilling; the eager dependency closure must arrive with it.
    assert 'source="procedure/grilling"' in text
    assert result["execution"]["details"] == {"mode": "user-capability", "capability": "grill-me"}
    assert result["entries"] == []
    assert result["deliveries"] == []
    assert result["active"] == ["read", "matt_pocock_workflow"]


def test_user_invocation_capability_stays_closed_in_capability_mode() -> None:
    """Given the autonomous mode, a user-invocation capability is still rejected."""
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime(); let error;
        try {
          await r.call("matt_pocock_workflow", { mode: "capability", capability: "grill-me" });
        } catch (cause) { error = String(cause); }
        console.log(JSON.stringify({ error, entries: r.entries, deliveries: r.deliveries() }));
    """)
    assert "not available to the model gateway" in result.get("error", ""), result
    assert result["entries"] == []
    assert result["deliveries"] == []


def test_user_capability_mode_rejects_a_model_invocation_capability() -> None:
    """Given the user-requested mode, an autonomously callable capability is refused."""
    result = run_typescript(RUNTIME_HARNESS + """
        const r = runtime(); let error;
        try {
          await r.call("matt_pocock_workflow", { mode: "user-capability", capability: "research" });
        } catch (cause) { error = String(cause); }
        console.log(JSON.stringify({ error, entries: r.entries }));
    """)
    assert "not a user-invocation capability" in result.get("error", ""), result
    assert result["entries"] == []


def test_user_invocation_capabilities_describe_themselves() -> None:
    """Given a menu or prompt row, every user-invocation capability has a real label."""
    result = run_typescript(RUNTIME_HARNESS + """
        import { userStandaloneCapabilities } from "./packages/matt-pocock/src/catalog.ts";
        console.log(JSON.stringify(userStandaloneCapabilities().map((entry) => ({
          id: entry.id, description: entry.description ?? null,
        }))));
    """)
    assert [entry["id"] for entry in result] == USER_CAPABILITIES
    for entry in result:
        assert entry["description"], entry
        assert entry["description"] != entry["id"], entry


# ── test_runtime_boundaries.py ──

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


@pytest.mark.parametrize("dialog", ["macosChooseFromList", "macosInputDialog"])
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
