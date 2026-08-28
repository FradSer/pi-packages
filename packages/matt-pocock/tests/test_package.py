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
        "A user manually transitions between phases",
        "Active work receives concise phase guidance",
        "Inactive sessions receive workflow routing guidance",
        "Agent autonomously starts or transitions a workflow via tool",
        "The package has no recursively discoverable child skills",
        "Deferred automation remains documented",
    ):
        assert scenario in feature


def test_manifest_declares_one_package_root_extension() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text())
    assert manifest["name"] == "pi-matt-pocock"
    assert manifest["version"] == "0.0.0"
    assert manifest["pi"] == {"extensions": ["./index.ts"]}
    assert manifest["peerDependencies"] == {"@earendil-works/pi-coding-agent": "*"}
    assert {"index.ts", "src", "procedures", "TODO.md"} <= set(manifest["files"])
    assert "skills" not in manifest["pi"]
    assert (PACKAGE / "index.ts").is_file()


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
    assert result["statuses"] == ["Matt Pocock: hard-bug · feedback-loop"]
    assert "# Diagnosing Bugs" in result["restored"][0]["message"]["content"]
    assert result["restored"][0]["options"] == {"deliverAs": "nextTurn"}
    assert "Matt Pocock workflow active: hard-bug · feedback-loop." in result["prompt"]["systemPrompt"]


def test_invalid_tool_procedure_does_not_persist_a_broken_workflow() -> None:
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
        };
        const ctx = { ui: { setStatus() {} } };

        mattPocock(pi);
        let error;
        try {
          await tools.get("matt_pocock_workflow").execute("call-1", {
            route: "hard-bug",
            procedure: "missing-procedure",
          }, undefined, undefined, ctx);
        } catch (caught) {
          error = String(caught);
        }
        console.log(JSON.stringify({ entries, error }));
    """)
    assert result["entries"] == []
    assert "not available for route hard-bug" in result["error"]


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
    assert result["statuses"][-1] == "Matt Pocock: hard-bug · feedback-loop"
    assert "Matt Pocock workflow active: hard-bug · feedback-loop." in result["prompt"]["systemPrompt"]
    assert "# Diagnosing Bugs" not in result["prompt"]["systemPrompt"]


def test_transition_is_manual_and_injects_only_the_selected_procedure() -> None:
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
    assert result["statuses"][-1] == "Matt Pocock: hard-bug · feedback-loop"
    assert "Matt Pocock workflow active: hard-bug · feedback-loop." in result["prompt"]["systemPrompt"]


def test_todo_records_deferred_automation() -> None:
    todo = (PACKAGE / "TODO.md").read_text()
    for deferred in (
        "Automatically infer workflow phase completion",
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
