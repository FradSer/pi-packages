"""A user-invocation capability must be reachable when the user asks for it.

Before this contract, `modelStandaloneCapabilities()` was the only source for the
gateway capability enum and the injected guidance, so every `invocation: "user"`
capability — grill-me among them — was invisible to the model. The user said "grill
me" and the package was never called.

These cases assert the observable seams only: the public tool schema, the injected
system prompt, and the tool result. They do not assert private helper calls.
"""
from __future__ import annotations

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