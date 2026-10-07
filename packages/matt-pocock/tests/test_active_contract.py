"""Active gateway contract: exact JSON shapes in guidance and strict schemas."""

from __future__ import annotations

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
