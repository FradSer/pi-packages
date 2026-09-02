from __future__ import annotations

import json
import re
import subprocess
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


def test_feature_covers_the_workflow_harness_contract() -> None:
    feature = (PACKAGE / "features" / "matt-pocock.feature").read_text()
    for scenario in (
        "The harness opens one workflow-routing menu",
        "Selecting a route injects its procedure",
        "Active workflow state survives a session restart",
        "A prompt routes to and begins the relevant workflow",
        "A prompt ends active workflow before rerouting",
        "A user explicitly overrides the automatic phase transition",
        "An agent automatically transitions after completing a procedure",
        "Active work receives concise phase guidance",
        "Inactive sessions receive workflow routing guidance",
        "Agent autonomously starts or transitions a workflow via tool",
        "A hard-bug workflow accepts the tight-red-loop entry point",
        "A wayfinding workflow accepts the clarify-goal entry point",
        "The workflow tool advertises every valid procedure name",
        "An unknown procedure soft-lands on the route default",
        "A stale restored workflow explicitly ends after validation fails",
        "Workflows advance through every non-user-owned next step",
        "Structured interview questions are available only during an active workflow",
        "Agent asks the user questions via interactive selection tool",
        "A user-owned decision remains pending without an answer",
        "Matt Pocock tool rows use operation-specific prefixes",
        "Workflow activation uses the monitor-style started row",
        "A structured answer keeps question and answer visible in the collapsed row",
        "The package has no recursively discoverable child skills",
        "Deferred lifecycle automation remains documented",
    ):
        assert scenario in feature


def test_manifest_declares_one_package_root_extension() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text())
    assert manifest["name"] == "pi-matt-pocock"
    assert manifest["version"] == "0.0.0"
    assert manifest["type"] == "module"
    assert manifest["pi"] == {"extensions": ["./index.ts"]}
    assert "@earendil-works/pi-coding-agent" in manifest["peerDependencies"]
    assert manifest["dependencies"] == {"@fradser/pi-kit": "workspace:*"}
    assert {"index.ts", "src", "procedures", "TODO.md"} <= set(manifest["files"])
    assert "skills" not in manifest["pi"]
    assert (PACKAGE / "index.ts").is_file()


def test_workflow_status_clears_use_pi_kit_transient_status_adapter() -> None:
    source = (PACKAGE / "src" / "index.ts").read_text(encoding="utf-8")
    feature = (PACKAGE / "features" / "matt-pocock.feature").read_text(encoding="utf-8")
    assert "Workflow status clears use the shared Pi-kit transient-status adapter" in feature
    assert 'clearPiStatus(ctx.ui, "matt-pocock")' in source
    assert 'ctx.ui.setStatus("matt-pocock", undefined)' not in source


def test_workflow_guidance_transitions_and_advances_without_redundant_confirmation() -> None:
    result = run_typescript("""
        import { workflowGuidance } from "./packages/matt-pocock/src/workflow.ts";
        console.log(JSON.stringify({
          guidance: workflowGuidance({ route: "wayfinding", procedure: "to-tickets", phase: "to-tickets" }),
        }));
    """)
    assert "do not stop to recommend, ask whether to continue" in result["guidance"]
    assert "call matt_pocock_workflow to transition immediately" in result["guidance"]
    assert "Continue through every newly unblocked AFK ticket or task" in result["guidance"]
    assert "closed decision ticket" in result["guidance"]


def test_procedures_auto_advance_non_user_owned_work() -> None:
    wayfinder = (PROCEDURES / "wayfinder.md").read_text()
    tickets = (PROCEDURES / "to-tickets.md").read_text()
    triage = (PROCEDURES / "triage.md").read_text()
    bugs = (PROCEDURES / "diagnosing-bugs.md").read_text()

    assert "A closed decision ticket is a trigger to advance the map" in wayfinder
    assert "Continue directly into the first unblocked AFK research or task ticket" in wayfinder
    assert "immediately claim and execute the next unblocked AFK ticket" in tickets
    assert "never ask merely for permission to perform the next triage step" in triage
    assert "apply the role and agent brief directly" in triage
    assert "determine from the evidence what would have prevented this bug" in bugs
    assert "run [code-review](code-review.md) over the fix immediately" in bugs


def test_non_user_owned_test_and_spec_progression_does_not_require_confirmation() -> None:
    bdd = (PROCEDURES / "bdd.md").read_text()
    tdd = (PROCEDURES / "tdd.md").read_text()
    spec = (PROCEDURES / "to-spec.md").read_text()

    assert "Test at the highest established seam" in bdd
    assert "begin the red-green loop immediately" in bdd
    assert "inspect the repository and conversation for Gherkin scenarios first" in tdd
    assert "do not ask for confirmation of facts that repository exploration can establish" in tdd
    assert "Ask only when the public contract is genuinely ambiguous" in tdd
    assert "Ask only if the existing context leaves the public contract genuinely ambiguous" in spec
    assert "Record the selected seams in the spec and continue directly" in spec


def test_procedures_are_internal_markdown_resources() -> None:
    procedures = {path.name for path in PROCEDURES.glob("*.md")}
    expected = {
        "grill-with-docs.md",
        "diagnosing-bugs.md",
        "triage.md",
        "wayfinder.md",
        "improve-codebase-architecture.md",
        "implement.md",
        "code-review.md",
    }
    assert expected <= procedures
    assert not list(PACKAGE.rglob("SKILL.md"))
    assert "/skill:" not in "\n".join(path.read_text() for path in PROCEDURES.glob("*.md"))


def test_procedure_links_and_hitl_template_resolve_within_the_package() -> None:
    for procedure in PROCEDURES.glob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", procedure.read_text()):
            if "://" in target or target.startswith(("#", "./src/")) or target == "link":
                continue
            assert (procedure.parent / target).is_file(), f"{procedure.name}: {target}"

    debugging = (PROCEDURES / "diagnosing-bugs.md").read_text()
    assert "hitl-loop.template.sh" in debugging
    assert "scripts/hitl-loop.template.sh" not in debugging
    assert (PROCEDURES / "hitl-loop.template.sh").is_file()


def test_workflow_tool_schema_advertises_every_registered_procedure_and_alias() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        import { procedurePath } from "./packages/matt-pocock/src/procedures.ts";
        import { normalizeProcedureName, transitionProcedures, workflowRoutes } from "./packages/matt-pocock/src/workflow.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const tools = new Map();
        const pi = {
          on() {},
          registerCommand() {},
          registerTool(tool) { tools.set(tool.name, tool); },
          appendEntry() {},
          sendUserMessage() {},
          getActiveTools() { return ["matt_pocock_ask"]; },
          setActiveTools() {},
        };
        mattPocock(pi);

        const tool = tools.get("matt_pocock_workflow");
        const routes = workflowRoutes().map(({ route }) => route);
        const registered = routes.flatMap((route) => transitionProcedures(route));
        const schema = tool.parameters;
        console.log(JSON.stringify({
          variants: schema.anyOf.map((variant) => ({
            route: variant.properties.route.const,
            procedures: variant.properties.procedure.enum,
          })),
          registered,
          resolved: registered.map((procedure) => procedurePath(normalizeProcedureName(procedure))),
        }));
    """)
    assert {variant["route"] for variant in result["variants"]} == {
        "idea-to-ship", "hard-bug", "triage", "wayfinding", "architecture",
    }
    procedures_by_route = {variant["route"]: set(variant["procedures"]) for variant in result["variants"]}
    assert procedures_by_route["hard-bug"] == {"diagnosing-bugs", "implement", "code-review", "tight-red-loop"}
    assert procedures_by_route["wayfinding"] == {
        "wayfinder", "research", "prototype", "to-spec", "to-tickets", "implement", "code-review", "clarify-goal",
    }
    assert all(set(procedures) <= set(result["registered"]) | {"tight-red-loop", "clarify-goal"}
               for procedures in procedures_by_route.values())
    assert len(result["resolved"]) == len(result["registered"])
    assert all(path.endswith(".md") for path in result["resolved"])


def test_bare_command_opens_one_workflow_router_menu() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const commands = new Map();
        const menus = [];
        const pi = {
          on() {},
          registerCommand(name, command) { commands.set(name, command); },
          registerTool() {},
          appendEntry() {},
          sendUserMessage() {},
        };
        const ctx = {
          hasUI: true,
          ui: {
            setStatus() {},
            notify() {},
            select: async (title, choices) => { menus.push({ title, choices }); },
          },
        };

        mattPocock(pi);
        await commands.get("matt-pocock").handler("", ctx);
        console.log(JSON.stringify({ commands: [...commands.keys()], menus }));
    """)
    assert result["commands"] == ["matt-pocock"]
    assert result["menus"] == [{
        "title": "Matt Pocock workflow",
        "choices": [
            "Start a workflow",
            "View current workflow",
            "Transition current workflow",
            "End current workflow",
        ],
    }]


def test_workflow_state_restores_the_latest_active_entry_and_respects_end() -> None:
    result = run_typescript("""
        import { latestWorkflowState } from "./packages/matt-pocock/src/workflow.ts";

        const active = {
          type: "custom",
          customType: "matt-pocock-workflow",
          data: { route: "hard-bug", procedure: "diagnosing-bugs", phase: "feedback-loop" },
        };
        const ended = {
          type: "custom",
          customType: "matt-pocock-workflow",
          data: { active: false },
        };
        console.log(JSON.stringify({
          restores: latestWorkflowState([active]),
          ends: latestWorkflowState([active, ended]) ?? null,
        }));
    """)
    assert result["restores"] == {
        "route": "hard-bug",
        "procedure": "diagnosing-bugs",
        "phase": "feedback-loop",
    }
    assert result["ends"] is None


def test_session_start_restores_persisted_workflow_and_visible_status() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const events = new Map();
        const statuses = [];
        const restored = [];
        const pi = {
          on(name, handler) { events.set(name, handler); },
          registerCommand() {},
          registerTool() {},
          appendEntry() {},
          sendMessage(message, options) { restored.push({ message, options }); },
          sendUserMessage() {},
          getActiveTools() { return ["matt_pocock_ask"]; },
          setActiveTools() {},
        };
        const ctx = {
          sessionManager: {
            getBranch: () => [{
              type: "custom",
              customType: "matt-pocock-workflow",
              data: { route: "hard-bug", procedure: "diagnosing-bugs", phase: "feedback-loop" },
            }],
          },
          ui: {
            setStatus(_name, value) { statuses.push(value); },
            notify() {},
          },
        };

        mattPocock(pi);
        await events.get("session_start")({}, ctx);
        const prompt = await events.get("before_agent_start")({ systemPrompt: "base" }, ctx);
        console.log(JSON.stringify({ statuses, restored, prompt }));
    """)
    assert result["statuses"] == [None]
    assert len(result["restored"]) == 1
    assert "# Diagnosing Bugs" in result["restored"][0]["message"]["content"]
    assert result["restored"][0]["message"]["display"] is False
    assert result["restored"][0]["options"] == {"deliverAs": "nextTurn"}
    assert "Matt Pocock workflow active: hard-bug · feedback-loop." in result["prompt"]["systemPrompt"]


def test_session_start_with_an_unavailable_procedure_clears_state_with_actionable_warning() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const events = new Map();
        const notices = [];
        const entries = [];
        const pi = {
          on(name, handler) { events.set(name, handler); },
          registerCommand() {},
          registerTool() {},
          appendEntry(customType, data) { entries.push({ customType, data }); },
          sendMessage() {},
          sendUserMessage() {},
          getActiveTools() { return ["matt_pocock_ask"]; },
          setActiveTools() {},
        };
        const ctx = {
          sessionManager: {
            getBranch: () => [{
              type: "custom",
              customType: "matt-pocock-workflow",
              data: { route: "wayfinding", procedure: "missing-procedure", phase: "discovery" },
            }],
          },
          ui: { setStatus() {}, notify(message, level) { notices.push({ message, level }); } },
        };

        mattPocock(pi);
        await events.get("session_start")({}, ctx);
        const prompt = await events.get("before_agent_start")({ systemPrompt: "base" }, ctx);
        console.log(JSON.stringify({ notices, entries, prompt }));
    """)
    assert result["notices"][0]["level"] == "warning"
    warning = result["notices"][0]["message"]
    assert "Valid procedures: wayfinder, research, prototype" in warning
    assert "Do not switch routes" in warning
    assert result["entries"] == [{
        "customType": "matt-pocock-workflow",
        "data": {"active": False},
    }]
    assert "## Available Engineering Workflows" in result["prompt"]["systemPrompt"]


def test_unknown_tool_procedure_soft_lands_on_the_route_default() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const tools = new Map();
        const entries = [];
        const pi = {
          on() {},
          registerCommand() {},
          registerTool(tool) { tools.set(tool.name, tool); },
          appendEntry(customType, data) { entries.push({ customType, data }); },
          sendUserMessage() {},
          getActiveTools() { return ["matt_pocock_ask"]; },
          setActiveTools() {},
        };
        const ctx = { ui: { setStatus() {} } };

        mattPocock(pi);
        const execution = await tools.get("matt_pocock_workflow").execute("call-1", {
          route: "wayfinding",
          procedure: "missing-procedure",
          phase: "discovery",
        }, undefined, undefined, ctx);
        console.log(JSON.stringify({ entries, execution }));
    """)
    assert result["entries"] == [{
        "customType": "matt-pocock-workflow",
        "data": {
            "route": "wayfinding",
            "procedure": "wayfinder",
            "phase": "mapping",
        },
    }]
    result_text = result["execution"]["content"][0]["text"]
    assert 'requested procedure "missing-procedure"' in result_text
    assert "Valid procedures for wayfinding: wayfinder, research, prototype" in result_text
    assert "Do not switch routes" in result_text
    assert "Wayfinder" in result_text


def test_command_activates_a_route_injects_a_procedure_and_adds_compact_guidance() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const events = new Map();
        const commands = new Map();
        const entries = [];
        const messages = [];
        const statuses = [];
        const pi = {
          on(name, handler) { events.set(name, handler); },
          registerCommand(name, command) { commands.set(name, command); },
          registerTool() {},
          appendEntry(customType, data) { entries.push({ customType, data }); },
          sendUserMessage(content, options) { messages.push({ content, options }); },
          getActiveTools() { return ["matt_pocock_ask"]; },
          setActiveTools() {},
        };
        const ctx = {
          sessionManager: { getBranch: () => [] },
          ui: {
            setStatus(_name, value) { statuses.push(value); },
            notify() {},
            select: async () => undefined,
          },
        };

        mattPocock(pi);
        await commands.get("matt-pocock").handler("hard-bug", ctx);
        const prompt = await events.get("before_agent_start")({ systemPrompt: "base" }, ctx);
        console.log(JSON.stringify({ entries, messages, statuses, prompt }));
    """)
    assert result["entries"] == [{
        "customType": "matt-pocock-workflow",
        "data": {
            "route": "hard-bug",
            "procedure": "diagnosing-bugs",
            "phase": "feedback-loop",
        },
    }]
    assert len(result["messages"]) == 1
    assert "# Diagnosing Bugs" in result["messages"][0]["content"]
    assert result["messages"][0]["options"] == {"deliverAs": "followUp"}
    assert result["statuses"][-1] is None
    assert "Matt Pocock workflow active: hard-bug · feedback-loop." in result["prompt"]["systemPrompt"]
    assert "# Diagnosing Bugs" not in result["prompt"]["systemPrompt"]


def test_arbitrary_prompt_ends_active_workflow_and_forwards_autonomous_routing_request() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const commands = new Map();
        const entries = [];
        const messages = [];
        const pi = {
          on() {},
          registerCommand(name, command) { commands.set(name, command); },
          registerTool() {},
          appendEntry(customType, data) { entries.push({ customType, data }); },
          sendUserMessage(content, options) { messages.push({ content, options }); },
          getActiveTools() { return ["matt_pocock_ask"]; },
          setActiveTools() {},
        };
        const ctx = { ui: { setStatus() {}, notify() {} } };

        mattPocock(pi);
        await commands.get("matt-pocock").handler("hard-bug", ctx);
        await commands.get("matt-pocock").handler("Investigate why reconnecting loses queued reports", ctx);
        console.log(JSON.stringify({ entries, messages }));
    """)
    assert result["entries"][-1] == {
        "customType": "matt-pocock-workflow",
        "data": {"active": False},
    }
    assert result["messages"][-1]["options"] == {"deliverAs": "followUp"}
    assert "Investigate why reconnecting loses queued reports" in result["messages"][-1]["content"]
    assert "End any active Matt Pocock workflow first" in result["messages"][-1]["content"]
    assert "matt_pocock_workflow" in result["messages"][-1]["content"]


def test_explicit_user_override_remains_available_and_injects_only_the_selected_procedure() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const events = new Map();
        const commands = new Map();
        const entries = [];
        const messages = [];
        const pi = {
          on(name, handler) { events.set(name, handler); },
          registerCommand(name, command) { commands.set(name, command); },
          registerTool() {},
          appendEntry(customType, data) { entries.push({ customType, data }); },
          sendUserMessage(content, options) { messages.push({ content, options }); },
          getActiveTools() { return ["matt_pocock_ask"]; },
          setActiveTools() {},
        };
        let selection = "code-review";
        const ctx = {
          hasUI: true,
          sessionManager: { getBranch: () => [] },
          ui: {
            setStatus() {},
            notify() {},
            select: async () => selection,
          },
        };

        mattPocock(pi);
        await commands.get("matt-pocock").handler("hard-bug", ctx);
        await commands.get("matt-pocock").handler("transition", ctx);
        console.log(JSON.stringify({ entries, messages }));
    """)
    assert result["entries"][-1]["data"] == {
        "route": "hard-bug",
        "procedure": "code-review",
        "phase": "code-review",
    }
    assert "Route: hard-bug\nPhase: code-review" in result["messages"][-1]["content"]
    assert "Two-axis review of the diff" in result["messages"][-1]["content"]
    assert result["messages"][-1]["options"] == {"deliverAs": "followUp"}


def test_inactive_session_receives_workflow_routing_guidance() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const events = new Map();
        const pi = {
          on(name, handler) { events.set(name, handler); },
          registerCommand() {},
          registerTool() {},
          appendEntry() {},
          sendUserMessage() {},
          getActiveTools() { return ["matt_pocock_ask"]; },
          setActiveTools() {},
        };
        const ctx = {
          sessionManager: { getBranch: () => [] },
          ui: { setStatus() {} },
        };

        mattPocock(pi);
        await events.get("session_start")({}, ctx);
        const prompt = await events.get("before_agent_start")({ systemPrompt: "base" }, ctx);
        console.log(JSON.stringify(prompt));
    """)
    assert "## Available Engineering Workflows" in result["systemPrompt"]
    assert "matt_pocock_workflow" in result["systemPrompt"]
    assert "idea-to-ship" in result["systemPrompt"]
    assert "hard-bug" in result["systemPrompt"]
    assert "Do not activate it for routine work, document creation" in result["systemPrompt"]
    assert "When that task is finished or the user changes to unrelated work" in result["systemPrompt"]


def test_agent_can_autonomously_activate_workflow_via_tool() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const events = new Map();
        const tools = new Map();
        const entries = [];
        const messages = [];
        const statuses = [];
        const pi = {
          on(name, handler) { events.set(name, handler); },
          registerCommand() {},
          registerTool(tool) { tools.set(tool.name, tool); },
          appendEntry(customType, data) { entries.push({ customType, data }); },
          sendUserMessage(content, options) { messages.push({ content, options }); },
          getActiveTools() { return ["matt_pocock_ask"]; },
          setActiveTools() {},
        };
        const ctx = {
          sessionManager: { getBranch: () => [] },
          ui: {
            setStatus(_name, value) { statuses.push(value); },
            notify() {},
          },
        };

        mattPocock(pi);
        const tool = tools.get("matt_pocock_workflow");
        const execution = await tool.execute("call-1", { route: "hard-bug" }, undefined, undefined, ctx);
        const prompt = await events.get("before_agent_start")({ systemPrompt: "base" }, ctx);
        console.log(JSON.stringify({ entries, messages, statuses, execution, prompt }));
    """)
    assert result["entries"] == [{
        "customType": "matt-pocock-workflow",
        "data": {
            "route": "hard-bug",
            "procedure": "diagnosing-bugs",
            "phase": "feedback-loop",
        },
    }]
    assert "# Diagnosing Bugs" in result["execution"]["content"][0]["text"]
    assert result["statuses"][-1] is None
    assert "Matt Pocock workflow active: hard-bug · feedback-loop." in result["prompt"]["systemPrompt"]


def test_hard_bug_tight_red_loop_alias_activates_diagnosing_bugs_at_reproduce() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const tools = new Map();
        const entries = [];
        const pi = {
          on() {},
          registerCommand() {},
          registerTool(tool) { tools.set(tool.name, tool); },
          appendEntry(customType, data) { entries.push({ customType, data }); },
          sendUserMessage() {},
          getActiveTools() { return ["matt_pocock_ask"]; },
          setActiveTools() {},
        };
        const ctx = { ui: { setStatus() {} } };

        mattPocock(pi);
        const execution = await tools.get("matt_pocock_workflow").execute("call-1", {
          route: "hard-bug",
          procedure: "tight-red-loop",
          phase: "reproduce",
        }, undefined, undefined, ctx);
        console.log(JSON.stringify({ entries, execution }));
    """)
    assert result["entries"] == [{
        "customType": "matt-pocock-workflow",
        "data": {
            "route": "hard-bug",
            "procedure": "diagnosing-bugs",
            "phase": "reproduce",
        },
    }]
    assert "# Diagnosing Bugs" in result["execution"]["content"][0]["text"]
    assert "Route: hard-bug\nPhase: reproduce" in result["execution"]["content"][0]["text"]


def test_wayfinding_clarify_goal_alias_activates_wayfinder() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const tools = new Map();
        const entries = [];
        const pi = {
          on() {},
          registerCommand() {},
          registerTool(tool) { tools.set(tool.name, tool); },
          appendEntry(customType, data) { entries.push({ customType, data }); },
          sendUserMessage() {},
          getActiveTools() { return ["matt_pocock_ask"]; },
          setActiveTools() {},
        };
        const ctx = { ui: { setStatus() {} } };

        mattPocock(pi);
        const execution = await tools.get("matt_pocock_workflow").execute("call-1", {
          route: "wayfinding",
          procedure: "clarify-goal",
          phase: "discovery",
        }, undefined, undefined, ctx);
        console.log(JSON.stringify({ entries, execution }));
    """)
    assert result["entries"] == [{
        "customType": "matt-pocock-workflow",
        "data": {
            "route": "wayfinding",
            "procedure": "wayfinder",
            "phase": "discovery",
        },
    }]
    assert "Wayfinder" in result["execution"]["content"][0]["text"]
    assert "Route: wayfinding\nPhase: discovery" in result["execution"]["content"][0]["text"]


def test_matt_pocock_ask_is_inactive_outside_a_workflow_and_removed_on_exit() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const events = new Map();
        const commands = new Map();
        const tools = new Map();
        let activeTools = ["bash", "matt_pocock_workflow", "matt_pocock_ask"];
        const pi = {
          on(name, handler) { events.set(name, handler); },
          registerCommand(name, command) { commands.set(name, command); },
          registerTool(tool) { tools.set(tool.name, tool); },
          appendEntry() {},
          sendMessage() {},
          sendUserMessage() {},
          getActiveTools() { return activeTools; },
          setActiveTools(names) { activeTools = names; },
        };
        const inactiveContext = {
          hasUI: true,
          sessionManager: { getBranch: () => [] },
          ui: { setStatus() {}, notify() {} },
        };
        const restoredContext = {
          hasUI: true,
          sessionManager: {
            getBranch: () => [{
              type: "custom",
              customType: "matt-pocock-workflow",
              data: { route: "hard-bug", procedure: "diagnosing-bugs", phase: "feedback-loop" },
            }],
          },
          ui: { setStatus() {}, notify() {} },
        };

        mattPocock(pi);
        await events.get("session_start")({}, inactiveContext);
        const inactive = [...activeTools];
        await tools.get("matt_pocock_workflow").execute("call-1", { route: "hard-bug" }, undefined, undefined, inactiveContext);
        const workflowActive = [...activeTools];
        await commands.get("matt-pocock").handler("end", inactiveContext);
        const ended = [...activeTools];
        activeTools = ["bash", "matt_pocock_workflow"];
        await events.get("session_start")({}, restoredContext);
        console.log(JSON.stringify({ inactive, workflowActive, ended, restored: activeTools }));
    """)
    assert "matt_pocock_ask" not in result["inactive"]
    assert "matt_pocock_ask" in result["workflowActive"]
    assert "matt_pocock_ask" not in result["ended"]
    assert "matt_pocock_ask" in result["restored"]


def test_matt_pocock_ask_tool_selection_custom_input_and_timeout() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const tools = new Map();
        const pi = {
          on() {},
          registerCommand() {},
          registerTool(tool) { tools.set(tool.name, tool); },
          appendEntry() {},
          sendUserMessage() {},
          getActiveTools() { return ["matt_pocock_ask"]; },
          setActiveTools() {},
        };

        let selectChoice = "Option A (Recommended)";
        let inputChoice = "";
        let lastSelectTimeout = null;

        const ctx = {
          hasUI: true,
          sessionManager: { getBranch: () => [] },
          ui: {
            setStatus() {},
            notify() {},
            select: async (title, choices, opts) => {
              lastSelectTimeout = opts?.timeout;
              return selectChoice;
            },
            input: async (title, placeholder) => inputChoice,
          },
        };

        mattPocock(pi);
        const askTool = tools.get("matt_pocock_ask");

        // 1. Regular selection
        const res1 = await askTool.execute("call-1", {
          question: "Which scope?",
          options: ["Option A (Recommended)", "Option B"],
          timeout_seconds: 30,
        }, undefined, undefined, ctx);

        // 2. Custom input selection
        selectChoice = "Type custom answer...";
        inputChoice = "My custom answer";
        const res2 = await askTool.execute("call-2", {
          question: "Which scope?",
          options: ["Option A (Recommended)", "Option B"],
        }, undefined, undefined, ctx);

        // 3. Timeout preserves the user-owned decision as pending.
        selectChoice = undefined;
        const res3 = await askTool.execute("call-3", {
          question: "Which scope?",
          options: ["Option A (Recommended)", "Option B"],
          timeout_seconds: 45,
        }, undefined, undefined, ctx);

        const noUiResult = await askTool.execute("call-4", {
          question: "Which scope?",
          options: ["Option A (Recommended)", "Option B"],
        }, undefined, undefined, { hasUI: false, ui: { setStatus() {} } });

        // 4. Dismissed or blank custom input must not choose the recommendation.
        selectChoice = "Type custom answer...";
        inputChoice = "   ";
        const blankCustomResult = await askTool.execute("call-5", {
          question: "Which scope?",
          options: ["Option A (Recommended)", "Option B"],
        }, undefined, undefined, ctx);

        console.log(JSON.stringify({
          res1,
          res2,
          res3,
          noUiResult,
          blankCustomResult,
          lastSelectTimeout,
          recommendedDescription: askTool.parameters.properties.recommended.description,
          timeoutDescription: askTool.parameters.properties.timeout_seconds.description,
        }));
    """)
    assert result["res1"]["details"]["answer"] == "Option A (Recommended)"
    assert result["res1"]["details"]["is_custom"] is False
    assert result["res2"]["details"]["answer"] == "My custom answer"
    assert result["res2"]["details"]["is_custom"] is True
    assert result["res3"]["details"]["pending"] is True
    assert result["res3"]["details"]["timed_out"] is True
    assert "Do not proceed" in result["res3"]["content"][0]["text"]
    assert result["noUiResult"]["details"] == {"pending": True, "source": "no_ui"}
    assert "Do not proceed" in result["noUiResult"]["content"][0]["text"]
    assert result["blankCustomResult"]["details"] == {
        "pending": True,
        "source": "custom_input_cancelled",
    }
    assert "Do not proceed" in result["blankCustomResult"]["content"][0]["text"]
    assert "timeout fallback" not in result["recommendedDescription"]
    assert "leaves the decision pending" in result["timeoutDescription"]
    assert result["lastSelectTimeout"] == 60000


def test_matt_pocock_ask_tui_rendering_uses_pi_kit_lifecycle() -> None:
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;

        const tools = new Map();
        const renderers = new Map();
        const pi = {
          on() {},
          registerCommand() {},
          registerTool(tool) { tools.set(tool.name, tool); },
          registerMessageRenderer(name, renderer) { renderers.set(name, renderer); },
          appendEntry() {},
          sendUserMessage() {},
          getActiveTools() { return ["matt_pocock_ask"]; },
          setActiveTools() {},
        };

        mattPocock(pi);
        const askTool = tools.get("matt_pocock_ask");
        const workflowTool = tools.get("matt_pocock_workflow");

        const theme = {
          fg: (_color, text) => text,
          bg: (_color, text) => text,
          bold: (text) => text,
        };

        const renderCall = askTool.renderCall({});
        const renderedAsk = askTool.renderResult(
          {
            content: [{ type: "text", text: "User selected: Option A" }],
            details: { answer: "Option A", is_custom: false, source: "choice_selected" },
          },
          { expanded: false },
          theme,
          { isError: false, args: { question: "Which scope?", options: ["Option A", "Option B"] } },
        );

        const renderedWorkflow = workflowTool.renderResult(
          {
            content: [{ type: "text", text: "Procedure content" }],
            details: { route: "idea-to-ship", procedure: "grill-me", phase: "shaping" },
          },
          { expanded: false },
          theme,
          { isError: false, args: { route: "idea-to-ship" } },
        );

        const procedureRenderer = renderers.get("matt-pocock-procedure");
        const renderedMsg = procedureRenderer(
          { content: "Restored procedure", details: { route: "idea-to-ship", phase: "shaping" } },
          { expanded: false },
          theme,
        );

        console.log(JSON.stringify({
          renderShell: askTool.renderShell,
          callText: typeof renderCall.render === "function" ? renderCall.render(80) : renderCall,
          askRows: renderedAsk.render(80),
          workflowRows: renderedWorkflow.render(80),
          msgRows: renderedMsg.render(80),
        }));
    """)
    assert result["renderShell"] == "self"
    assert any("[matt pocock] ask ·" in row for row in result["askRows"])
    assert not any("[matt pocock] · ask" in row for row in result["askRows"])
    assert not any("[matt pocock · ask]" in row for row in result["askRows"])
    assert not any("event ·" in row for row in result["askRows"])
    assert any("Which scope?" in row for row in result["askRows"])
    assert any("Answer: Option A" in row for row in result["askRows"])
    assert not any("Options:" in row for row in result["askRows"])

    assert len(result["workflowRows"]) == 1
    assert any("[matt pocock] started ·" in row for row in result["workflowRows"])
    assert not any("[matt pocock] workflow ·" in row for row in result["workflowRows"])
    assert any("Idea to Ship · Shaping & Requirements" in row for row in result["workflowRows"])
    assert not any("Procedure content" in row for row in result["workflowRows"])
    assert not any("ctrl+o to expand" in row for row in result["workflowRows"])

    assert any("[matt pocock] started ·" in row for row in result["msgRows"])
    assert not any("[matt pocock] workflow ·" in row for row in result["msgRows"])
    assert any("Idea to Ship · Shaping & Requirements" in row for row in result["msgRows"])
    assert not any("Restored procedure" in row for row in result["msgRows"])
    assert not any("ctrl+o to expand" in row for row in result["msgRows"])


def test_todo_records_remaining_deferred_lifecycle_automation() -> None:
    todo = (PACKAGE / "TODO.md").read_text()
    assert "Automatically infer workflow phase completion" not in todo
    for deferred in (
        "Automatically create a new Pi session",
        "Automatically create teammates",
        "tool-level production-write blocking",
        "one Pi command per workflow",
        "second public `/skill:matt-pocock` surface",
    ):
        assert deferred in todo


def test_unreleased_package_documents_local_installation() -> None:
    readme = (PACKAGE / "README.md").read_text()
    root_readmes = "\n".join((REPO / name).read_text() for name in ("README.md", "README.zh-CN.md"))

    assert "has not yet been released to npm" in readme
    assert "pi install /path/to/pi-packages/packages/matt-pocock" in readme
    assert "npm:pi-matt-pocock" not in root_readmes
    assert "pi install /path/to/pi-packages/packages/matt-pocock" in root_readmes


def test_release_changeset_bootstraps_version_zero_one_zero() -> None:
    changeset = (REPO / ".changeset" / "matt-pocock-router.md").read_text()
    assert '"pi-matt-pocock": minor' in changeset
