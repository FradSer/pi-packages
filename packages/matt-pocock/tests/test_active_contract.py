"""Active gateway contract: exact JSON shapes in guidance and strict schemas."""

from __future__ import annotations

from test_package import run_typescript  # noqa: F401  (shared helper)


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
    result = run_typescript("""
        import importedMattPocock from "./packages/matt-pocock/src/index.ts";
        import { Value } from "typebox/value";
        const mattPocock = importedMattPocock.default ?? importedMattPocock;
        const tools = new Map();
        const pi = {
          on() {}, registerCommand() {}, registerMessageRenderer() {},
          registerTool(tool) { tools.set(tool.name, tool); },
          appendEntry() {}, sendUserMessage() {}, sendMessage() {},
          getActiveTools() { return []; }, setActiveTools() {},
        };
        mattPocock(pi);
        const active = tools.get("matt_pocock_active");
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
