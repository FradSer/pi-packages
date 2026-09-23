"""User-invoked /matt-pocock starts render one impeccable-style block row."""

from __future__ import annotations

import pytest

from test_package import run_typescript


def test_a_workflow_step_does_not_re_deliver_what_is_already_in_context() -> None:
    """Re-sending a whole procedure closure every transition is what ended long tasks early."""
    result = run_typescript('''
        import { resolveProcedureDelta } from "./packages/matt-pocock/src/resolver.ts";
        const first = resolveProcedureDelta("implement", [], []);
        const repeat = resolveProcedureDelta("implement", [], first.delivered);
        const transition = resolveProcedureDelta("code-review", [], first.delivered);
        console.log(JSON.stringify({
          firstIds: first.delivered,
          firstBytes: first.content.length,
          repeatContent: repeat.content,
          repeatIds: repeat.delivered,
          transitionIds: transition.delivered,
          transitionBytes: transition.content.length,
        }));
    ''')

    # The first delivery carries the whole closure: the procedure and its dependencies.
    assert "implement" in result["firstIds"]
    assert "bdd" in result["firstIds"]
    assert result["firstBytes"] > 0

    # Nothing new is nothing re-sent, and the delivery set does not shrink.
    assert result["repeatContent"] == ""
    assert result["repeatIds"] == result["firstIds"]

    # A transition delivers only what that procedure adds, not the shared dependencies again.
    assert "code-review" in result["transitionIds"]
    assert result["transitionBytes"] > 0
    assert result["transitionBytes"] < result["firstBytes"]

HARNESS = """
        import mattPocock from "./packages/matt-pocock/src/index.ts";
        const LF = String.fromCharCode(10);
        const commands = new Map(), renderers = new Map(), entries = [], messages = [], userMessages = [];
        let activeTools = ["bash", "matt_pocock_workflow"];
        mattPocock({
          on() {}, registerCommand(name, command) { commands.set(name, command); }, registerTool() {},
          registerMessageRenderer(name, renderer) { renderers.set(name, renderer); },
          appendEntry(customType, data) { entries.push({ customType, data }); },
          sendMessage(message, options) { messages.push({ message, options }); },
          sendUserMessage(message, options) { userMessages.push({ message, options }); },
          getActiveTools() { return activeTools; }, setActiveTools(names) { activeTools = names; },
        });
        const theme = { fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text };
        const ctx = (choices = []) => ({ hasUI: true, ui: {
          setStatus() {}, notify() {}, select: async () => choices.shift(), input: async () => "",
        }});
        const command = commands.get("matt-pocock");
        const start = () => ({ messageCount: messages.length, userCount: userMessages.length, entryCount: entries.length });
        const snapshot = (before) => {
          const message = messages.at(-1).message;
          const rendered = renderers.get("matt-pocock-procedure")(message, { expanded: false }, theme).render(80);
          return {
            messages: messages.length - before.messageCount,
            userMessages: userMessages.slice(before.userCount),
            entries: entries.slice(before.entryCount),
            customType: message.customType, display: message.display, details: message.details,
            options: messages.at(-1).options, content: message.content,
            activeTools: [...activeTools],
            rows: rendered.slice(1, -1).map((row) => row.trim()),
            band: rendered,
          };
        };
"""

SCRIPT = """
        let before = start();
        await command.handler("hard-bug fix the login redirect", ctx());
        const routeTask = snapshot(before);

        await command.handler("complete", ctx());
        before = start();
        await command.handler("hard-bug", ctx());
        const routeOnly = snapshot(before);

        await command.handler("complete", ctx());
        before = start();
        await command.handler("research tighten the spacing", ctx());
        const capabilityTask = snapshot(before);

        before = start();
        await command.handler("research", ctx());
        const capabilityOnly = snapshot(before);

        before = start();
        await command.handler("", ctx(["Start a workflow", "Start an idea-to-ship flow — Shape an idea before planning and implementation."]));
        const menuRoute = snapshot(before);

        await command.handler("complete", ctx());
        before = start();
        await command.handler("", ctx(["Run a standalone capability", "Research — Primary-source research that writes a cited repository note."]));
        const menuCapability = snapshot(before);

        await command.handler("hard-bug", ctx());
        before = start();
        await command.handler("transition", ctx(["code-review"]));
        const transition = snapshot(before);

        before = start();
        await command.handler("cancel shifting scope from the user", ctx());
        const cancelled = {
          messages: messages.length - before.messageCount,
          userMessages: userMessages.slice(before.userCount),
          entries: entries.slice(before.entryCount),
        };

        before = start();
        await command.handler("", ctx(["Start a task"]));
        const menuRouting = snapshot(before);

        before = start();
        await command.handler(`aaaa${LF}zzzz`, ctx());
        const freeform = snapshot(before);

        console.log(JSON.stringify({ routeTask, routeOnly, capabilityTask, capabilityOnly, menuRoute,
          menuCapability, transition, cancelled, menuRouting, freeform, activeTools }));
"""

DELIVERIES = ("routeTask", "routeOnly", "capabilityTask", "capabilityOnly", "menuRoute",
              "menuCapability", "transition", "menuRouting", "freeform")

STATE_KEYS = ("version", "workItemId", "route", "procedure", "phase", "status", "loadedReferences")

LF = "\n"


def state_without_request(details: dict[str, object]) -> dict[str, object]:
    return {key: details[key] for key in STATE_KEYS}


@pytest.fixture(scope="module")
def delivery() -> dict[str, object]:
    return run_typescript(HARNESS + SCRIPT)


@pytest.mark.parametrize("name", DELIVERIES)
def test_procedure_starts_deliver_one_displayed_message_not_a_user_message(delivery: dict[str, object], name: str) -> None:
    item = delivery[name]
    assert item["userMessages"] == []
    assert item["messages"] == 1
    assert item["customType"] == "matt-pocock-procedure"
    assert item["display"] is True
    assert item["options"] == {"deliverAs": "followUp", "triggerTurn": True}


@pytest.mark.parametrize("name,body", [
    ("routeTask", ["fix the login redirect"]),
    ("routeOnly", ["Reproducing & Diagnostics"]),
    ("capabilityTask", ["tighten the spacing"]),
    ("capabilityOnly", ["research"]),
    ("menuRoute", ["Shaping & Requirements"]),
    ("menuCapability", ["research"]),
    ("transition", ["Code Review"]),
    ("menuRouting", []),
    ("freeform", ["aaaa", "zzzz"]),
])
def test_blocks_keep_the_head_apart_from_the_body(delivery: dict[str, object], name: str, body: list[str]) -> None:
    item = delivery[name]
    assert item["rows"] == ["[matt pocock] started"] + (["", *body] if body else [])
    assert "to expand" not in "\n".join(item["band"])
    assert all(len(row) <= 80 for row in item["band"])


@pytest.mark.parametrize("name,task", [("routeTask", "fix the login redirect"), ("capabilityTask", "tighten the spacing")])
def test_a_supplied_task_reaches_prompt_and_row(delivery: dict[str, object], name: str, task: str) -> None:
    item = delivery[name]
    assert item["details"]["request"] == task
    assert f"User target/request:{LF}{task}" in item["content"]
    assert item["content"].rstrip().endswith(task) or "## Workflow state contract" in item["content"]


def test_a_supplied_task_never_enters_persisted_state(delivery: dict[str, object]) -> None:
    route_task = delivery["routeTask"]
    assert [entry["customType"] for entry in route_task["entries"]] == ["matt-pocock-workflow"]
    record = route_task["entries"][0]["data"]
    assert record == state_without_request(route_task["details"])
    assert "request" not in record
    assert delivery["capabilityTask"]["entries"] == []


def test_freeform_routing_keeps_the_request_and_starts_no_workflow(delivery: dict[str, object]) -> None:
    freeform = delivery["freeform"]
    assert freeform["details"] == {"request": f"aaaa{LF}zzzz"}
    assert freeform["entries"] == []
    assert "Route and execute this request" in freeform["content"]
    assert f"aaaa{LF}zzzz" in freeform["content"]


def test_menu_routing_rows_stay_head_only_and_start_no_workflow(delivery: dict[str, object]) -> None:
    routing = delivery["menuRouting"]
    assert routing["details"] == {"request": ""}
    assert routing["entries"] == []
    assert "recent conversation context" in routing["content"]


def test_workflow_starts_activate_active_tools(delivery: dict[str, object]) -> None:
    assert "matt_pocock_active" in delivery["routeTask"]["activeTools"]
    assert "matt_pocock_ask" in delivery["routeTask"]["activeTools"]


def test_the_cancel_reason_comes_from_the_command_input(delivery: dict[str, object]) -> None:
    cancelled = delivery["cancelled"]
    assert cancelled["messages"] == 0
    assert cancelled["userMessages"] == []
    assert [entry["customType"] for entry in cancelled["entries"]] == ["matt-pocock-workflow"]
    terminal = cancelled["entries"][0]["data"]
    assert terminal["status"] == "cancelled"
    assert terminal["reason"] == "shifting scope from the user"