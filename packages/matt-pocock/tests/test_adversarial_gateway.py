"""Adversarial gateway, command, and in-flight decision contracts.

These cases deliberately exercise the public Pi tool/command seams rather than
calling private workflow helpers.  The bounded races are important: a decision
that is no longer valid must dismiss its adapter, not merely return a pending
result after the user eventually answers.
"""
from __future__ import annotations

import pytest

from matt_pocock_helpers import RUNTIME_HARNESS as HARNESS, run_typescript


def test_model_gateway_rejects_user_only_capability_without_writes() -> None:
    """Given a model gateway call, a user-only capability remains untouched."""
    result = run_typescript(HARNESS + """
        const r = runtime(); let error;
        try {
          await r.call("matt_pocock_workflow", {
            mode: "capability", capability: "setup-matt-pocock-skills",
          });
        } catch (cause) { error = String(cause); }
        console.log(JSON.stringify({ error, entries: r.entries.length, active: r.active(), deliveries: r.deliveries() }));
    """)
    assert "not available to the model gateway" in result.get("error", ""), result
    assert result["entries"] == 0
    assert result["active"] == ["read", "matt_pocock_workflow"]
    assert result["deliveries"] == []


def test_model_gateway_reads_reference_without_invoking_user_only_root() -> None:
    """Given a disclosed reference, reading it does not invoke its user-only root."""
    result = run_typescript(HARNESS + """
        const r = runtime(); let error; let value;
        try {
          value = await r.call("matt_pocock_workflow", {
            mode: "reference", capability: "setup-matt-pocock-skills", reference: "domain",
          });
        } catch (cause) { error = String(cause); }
        console.log(JSON.stringify({ error, value, entries: r.entries.length, active: r.active(), deliveries: r.deliveries() }));
    """)
    assert "error" not in result, result
    text = result["value"]["content"][0]["text"]
    assert 'source="procedure/domain"' in text
    assert 'source="procedure/setup-matt-pocock-skills"' not in text
    assert result["entries"] == 0
    assert result["active"] == ["read", "matt_pocock_workflow"]
    assert result["deliveries"] == []


def test_repeated_start_reference_and_terminal_operations_are_atomic() -> None:
    """Given one work item, repeats do not append state or revive active tools."""
    result = run_typescript(HARNESS + """
        const r = runtime(); await r.start();
        let duplicateStart; let duplicateReference;
        try { await r.start(); } catch (cause) { duplicateStart = String(cause); }
        await r.call("matt_pocock_active", { action: "load", reference: "improve-codebase-architecture" });
        const beforeDuplicateReference = r.entries.length;
        try {
          await r.call("matt_pocock_active", { action: "load", reference: "improve-codebase-architecture" });
        } catch (cause) { duplicateReference = String(cause); }
        const afterDuplicateReference = r.entries.length;
        await r.call("matt_pocock_active", { action: "complete" });
        let duplicateComplete; let duplicateCancel;
        try { await r.call("matt_pocock_active", { action: "complete" }); } catch (cause) { duplicateComplete = String(cause); }
        try { await r.call("matt_pocock_active", { action: "cancel", reason: "late retry" }); } catch (cause) { duplicateCancel = String(cause); }
        console.log(JSON.stringify({
          duplicateStart, duplicateReference, duplicateComplete, duplicateCancel,
          beforeDuplicateReference, afterDuplicateReference,
          entries: r.entries.length, active: r.active(),
        }));
    """)
    assert "already active" in result["duplicateStart"]
    assert result["beforeDuplicateReference"] == result["afterDuplicateReference"] == 2
    assert result["duplicateReference"]
    assert "No active Matt Pocock workflow" in result["duplicateComplete"]
    assert "No active Matt Pocock workflow" in result["duplicateCancel"]
    assert result["entries"] == 3
    assert result["active"] == ["read", "matt_pocock_workflow"]


def test_command_alias_and_standalone_overlap_keep_gateway_state_separate() -> None:
    """Given an active workflow, model capabilities and human aliases do not mutate it."""
    result = run_typescript(HARNESS + """
        const r = runtime(); const command = r.commands.get("matt-pocock");
        await command.handler("tight-red-loop investigate", r.ctx);
        const alias = r.deliveries().at(-1);
        await r.start(); const before = r.entries.length;
        const capability = await r.call("matt_pocock_workflow", { mode: "capability", capability: "research" });
        const after = r.entries.length;
        console.log(JSON.stringify({ alias, capability, before, after, active: r.active() }));
    """)
    assert result["alias"]["message"]["details"] == {
        "mode": "capability", "capability": "diagnosing-bugs", "request": "investigate",
    }
    assert result["before"] == result["after"] == 1
    assert result["capability"]["details"] == {"mode": "capability", "capability": "research"}
    assert "matt_pocock_active" in result["active"]


@pytest.mark.parametrize("command_text", ["complete unexpected", "status unexpected"])
def test_malformed_control_command_does_not_supersede_active_workflow(command_text: str) -> None:
    """Given an active workflow, an extra argument on a control command is rejected atomically."""
    result = run_typescript(HARNESS + f"""
        const r = runtime(); const command = r.commands.get("matt-pocock");
        await r.start();
        await command.handler({command_text!r}, r.ctx);
        const latest = r.entries.at(-1)?.data;
        console.log(JSON.stringify({{ command: {command_text!r}, entries: r.entries.length, latest, deliveries: r.deliveries(), active: r.active(), notices: r.notices }}));
    """)
    assert result["command"] == command_text
    assert result["entries"] == 1, result
    assert result["latest"]["status"] == "active", result
    assert result["deliveries"] == [], result
    assert "matt_pocock_active" in result["active"], result
    assert result["notices"], result


@pytest.mark.parametrize("selection", ["Complete current workflow", "Transition current workflow"])
def test_active_menu_result_cannot_operate_on_a_replacement_workflow(selection: str) -> None:
    """An active menu opened for A cannot complete or transition replacement B."""
    result = run_typescript(HARNESS + f"""
        const r = runtime(); const command = r.commands.get("matt-pocock");
        await r.start();
        let openedResolve; const opened = new Promise(resolve => {{ openedResolve = resolve; }});
        let releaseMenu; let selects = 0;
        r.ctx.ui.select = async (_title, choices) => {{
          selects += 1;
          if (selects === 1) {{
            openedResolve();
            return new Promise(resolve => {{ releaseMenu = () => resolve({selection!r}); }});
          }}
          return "implement";
        }};
        const pendingMenu = command.handler("", r.ctx);
        await Promise.race([opened, new Promise(resolve => setTimeout(resolve, 100))]);
        await r.call("matt_pocock_active", {{ action: "cancel", reason: "replace A" }});
        await r.start();
        releaseMenu();
        await pendingMenu;
        const latest = r.entries.at(-1)?.data;
        console.log(JSON.stringify({{ selection: {selection!r}, latest, entries: r.entries.length, selects, active: r.active() }}));
    """)
    assert result["latest"]["status"] == "active", result
    assert result["entries"] == 3, result
    assert result["selects"] == 1, result
    assert "matt_pocock_active" in result["active"]


def test_route_menu_result_cannot_overwrite_a_workflow_started_while_it_waited() -> None:
    """A delayed route choice from an inactive menu cannot replace a newer start."""
    result = run_typescript(HARNESS + """
        const r = runtime(); const command = r.commands.get("matt-pocock");
        let routeOpenedResolve; const routeOpened = new Promise(resolve => { routeOpenedResolve = resolve; });
        let releaseRoute; let selects = 0;
        r.ctx.ui.select = async (_title, choices) => {
          selects += 1;
          if (selects === 1) return "Start a workflow";
          routeOpenedResolve();
          return new Promise(resolve => { releaseRoute = () => resolve(choices[0]); });
        };
        const pendingMenu = command.handler("", r.ctx);
        await Promise.race([routeOpened, new Promise(resolve => setTimeout(resolve, 100))]);
        await r.start();
        releaseRoute();
        await pendingMenu;
        const latest = r.entries.at(-1)?.data;
        console.log(JSON.stringify({ latest, entries: r.entries.length, selects, active: r.active() }));
    """)
    assert result["latest"]["status"] == "active", result
    assert result["entries"] == 1, result
    assert result["active"].count("matt_pocock_active") == 1


def test_menu_guard_survives_microtask_state_replacement_before_selection_returns() -> None:
    """A two-microtask replacement cannot slip between menu guard and dispatch."""
    result = run_typescript(HARNESS + """
        const r = runtime(); const command = r.commands.get("matt-pocock");
        await r.start();
        const workItemA = r.entries.at(-1)?.data.workItemId;
        let replacePromise;
        r.ctx.ui.select = async () => {
          replacePromise = new Promise(resolve => {
            queueMicrotask(() => queueMicrotask(() => {
              void (async () => {
                if (r.entries.at(-1)?.data.status === "active") {
                  await r.call("matt_pocock_active", { action: "cancel", reason: "microtask replacement" });
                }
                await r.start();
                resolve();
              })();
            }));
          });
          await replacePromise;
          return "Complete current workflow";
        };
        await command.handler("", r.ctx);
        const latest = r.entries.at(-1)?.data;
        console.log(JSON.stringify({ entries: r.entries.length, workItemA, latest, active: r.active() }));
    """)
    assert result["entries"] == 3, result
    assert result["latest"]["status"] == "active", result
    assert result["latest"]["workItemId"] != result["workItemA"], result
    assert "matt_pocock_active" in result["active"], result


@pytest.mark.parametrize("replacement", ["complete", "transition", "session_tree", "session_start"])
def test_inflight_selector_is_dismissed_when_workflow_state_is_replaced(replacement: str) -> None:
    """A late answer cannot leave a selector hanging after a state replacement."""
    result = run_typescript(HARNESS + f"""
        const r = runtime(); await r.start();
        let openedResolve; const opened = new Promise(resolve => {{ openedResolve = resolve; }});
        let selectorAborted = false;
        r.ctx.ui.select = (_title, _choices, {{ signal }}) => new Promise(resolve => {{
          openedResolve();
          signal.addEventListener("abort", () => {{ selectorAborted = true; resolve(undefined); }}, {{ once: true }});
        }});
        const pending = r.call("matt_pocock_ask", {{ question: "Scope?", options: ["A", "B"], recommended: "A" }});
        await Promise.race([opened, new Promise(resolve => setTimeout(resolve, 100))]);
        if ({replacement!r} === "complete") {{
          await r.call("matt_pocock_active", {{ action: "complete" }});
        }} else if ({replacement!r} === "transition") {{
          await r.call("matt_pocock_active", {{ action: "transition", target: "implement" }});
        }} else {{
          await r.events.get({replacement!r})({{}}, r.ctx);
        }}
        const outcome = await Promise.race([
          pending.then(value => ({{ kind: "settled", value }})),
          new Promise(resolve => setTimeout(() => resolve({{ kind: "timeout" }}), 150)),
        ]);
        console.log(JSON.stringify({{ replacement: {replacement!r}, selectorAborted, outcome }}));
    """)
    assert result["selectorAborted"] is True, result
    assert result["outcome"]["kind"] == "settled", result
    assert result["outcome"]["value"]["details"] == {"pending": True, "source": "aborted"}


@pytest.mark.parametrize("replacement", ["complete", "session_tree"])
def test_inflight_custom_input_is_dismissed_when_workflow_state_is_replaced(replacement: str) -> None:
    """A replacement aborts the custom-input phase itself and settles the ask."""
    result = run_typescript(HARNESS + f"""
        const r = runtime(); await r.start();
        let inputOpenedResolve; const inputOpened = new Promise(resolve => {{ inputOpenedResolve = resolve; }});
        let inputAborted = false;
        r.ctx.ui.select = async () => "Type custom answer...";
        r.ctx.ui.input = (_question, _placeholder, {{ signal }}) => new Promise(resolve => {{
          inputOpenedResolve();
          signal.addEventListener("abort", () => {{ inputAborted = true; resolve(undefined); }}, {{ once: true }});
        }});
        const pending = r.call("matt_pocock_ask", {{ question: "Scope?", options: ["A", "B"], recommended: "A" }});
        await Promise.race([inputOpened, new Promise(resolve => setTimeout(resolve, 100))]);
        if ({replacement!r} === "complete") {{
          await r.call("matt_pocock_active", {{ action: "complete" }});
        }} else {{
          await r.events.get("session_tree")({{}}, r.ctx);
        }}
        const outcome = await Promise.race([
          pending.then(value => ({{ kind: "settled", value }})),
          new Promise(resolve => setTimeout(() => resolve({{ kind: "timeout" }}), 150)),
        ]);
        console.log(JSON.stringify({{ replacement: {replacement!r}, inputAborted, outcome }}));
    """)
    assert result["inputAborted"] is True, result
    assert result["outcome"]["kind"] == "settled", result
    assert result["outcome"]["value"]["details"] == {"pending": True, "source": "aborted"}, result
