"""Activation tested through the real package entry and a native session tree."""
from __future__ import annotations
import json
import os
import subprocess
import tempfile
from pathlib import Path
from subagents_helpers import PACKAGE, run_node
ENTRY = (PACKAGE / "index.ts").as_uri()
PREAMBLE = f"""
import assert from "node:assert/strict";
import {{ SessionManager }} from "@earendil-works/pi-coding-agent";
import extension from {json.dumps(ENTRY)};
const family=['agent_start','agent_input','agent_stop','agent_inspect','agent_list'];
const registered = [], handlers = new Map();
let active = ["read",...family,"subagents_enable"];
const pi = {{
  registerTool: t => registered.push(t),
  registerMessageRenderer() {{}},
  on: (event,h) => {{ const list=handlers.get(event)??[]; list.push(h); handlers.set(event,list); }},
  events: {{emit(){{}}}},
  getAllTools: () => registered,
  getActiveTools: () => active,
  setActiveTools: next => {{active=next;}},
}};
extension(pi);
const sessionManager=SessionManager.inMemory();
const ctx={{sessionManager,model:{{api:"anthropic-messages",compat:{{supportsMidConvoSystemMessages:true,supportsMidConvoToolChanges:true}}}}}};
const emit=async event=>{{for(const h of handlers.get(event)??[])await h({{}},ctx);}};
"""

def run(script: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="subagent-activation-") as directory:
        home = Path(directory)
        return run_node(PREAMBLE + script, env_overrides={
            **{key: "" for key in os.environ if key.startswith("PI_")},
            "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
            "PI_CODING_AGENT_DIR": str(home / "agent"),
            "PI_CODING_AGENT_SESSION_DIR": str(home / "sessions"),
            "PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "0",
        })


def test_native_pi_activation_preserves_the_transcript_prefix(tmp_path: Path) -> None:
    # The native probe must run with a controlled process environment. Inheriting
    # every non-PI variable can leak NODE_OPTIONS, provider credentials, or user
    # config into what is meant to be an isolated transcript/activation check.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "PI_OFFLINE": "1",
        "PI_SKIP_VERSION_CHECK": "1",
        "PI_TELEMETRY": "0",
    }
    result = subprocess.run(["node", str(PACKAGE / "tests" / "activation-transcript-fixture.ts")],
        cwd=PACKAGE, env=env, capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"prefixPreserved":true' in result.stdout


def test_compatible_fresh_session_loads_only_small_loader() -> None:
    result=run("""
      await emit("session_start");
      const loader=registered.find(t=>t.name==="subagents_enable");
      console.log(JSON.stringify({active,loader:!!loader,properties:loader?Object.keys(loader.parameters.properties):null}));
    """)
    assert result == {"active":["read","subagents_enable"],"loader":True,"properties":[]}


def test_provider_addition_flags_are_transport_specific() -> None:
    result=run("""
      const cases=[
        ["openai-completions",{supportsMidConvoSystemMessages:true,supportsMidConvoToolAdditions:true}],
        ["openai-responses",{supportsMidConvoSystemMessages:true,supportsAdditionalTools:true}],
        ["openai-codex-responses",{supportsMidConvoSystemMessages:true,supportsToolSearch:true}],
        ["openai-responses",{supportsToolSelection:true}],
        ["anthropic-messages",{supportsMidConvoToolChanges:true}],
      ];
      const outcomes=[];
      for(const [api,compat] of cases){ctx.model={api,compat};active=["read",...family,"subagents_enable"];await emit("session_start");outcomes.push([...active]);}
      console.log(JSON.stringify({outcomes}));
    """)
    assert result["outcomes"] == [["read","subagents_enable"]]*3 + [["read","agent_start","agent_input","agent_stop","agent_inspect","agent_list"]]*2


def test_restoring_lazy_session_without_native_system_records_keeps_loader() -> None:
    result=run("""
      await emit("session_start");
      const recorded=active.slice();
      sessionManager.appendMessage({role:"user",timestamp:1,content:"Inspect"});
      await emit("session_start");
      console.log(JSON.stringify({recorded,active}));
    """)
    assert result["recorded"] == ["read","subagents_enable"]
    assert result["active"] == result["recorded"]


def test_unrelated_tool_delta_does_not_remove_subagent_entrypoints() -> None:
    result=run("""
      await emit("session_start");
      sessionManager.appendMessage({role:"system",timestamp:1,content:"",toolsAdded:[{name:"other",description:"other",parameters:{type:"object"}}]});
      await emit("session_tree");
      console.log(JSON.stringify({active}));
    """)
    assert result["active"] == ["read","subagents_enable"]


def test_loader_enables_agent_without_launching() -> None:
    result=run("""
      await emit("session_start");
      const loader=registered.find(t=>t.name==="subagents_enable");
      const result=loader?await loader.execute("call",{},undefined,undefined,ctx):null;
      console.log(JSON.stringify({active,enabled:result?.details.enabled??null}));
    """)
    assert "agent" not in result["active"], "the retired tool is never selected"
    assert result["enabled"] == ["agent_start", "agent_input", "agent_stop", "agent_inspect", "agent_list"]


def test_incompatible_or_unknown_provider_stays_eager() -> None:
    result=run("""
      ctx.model={api:"openai-completions",compat:{supportsMidConvoSystemMessages:true}};
      await emit("session_start");
      console.log(JSON.stringify({active}));
    """)
    assert result["active"] == ["read","agent_start","agent_input","agent_stop","agent_inspect","agent_list"]


def test_native_branch_tool_selection_restores_without_model_churn() -> None:
    result=run("""
      sessionManager.appendMessage({role:"system",timestamp:1,content:"",toolsAdded:[{name:"agent",description:"x",parameters:{type:"object",properties:{}}}],toolsRemoved:[]});
      await emit("session_start");
      const before=[...active];
      ctx.model={api:"unknown"};
      await emit("model_select");
      console.log(JSON.stringify({active,before}));
    """)
    # A branch that recorded the retired tool keeps its work and receives the intent family.
    assert result["active"] == ["read","agent_start","agent_input","agent_stop","agent_inspect","agent_list"]
    assert result["before"] == result["active"]


def test_loader_has_short_selection_only_help_annotations_and_typed_schema() -> None:
    result = run('''
      const loader = registered.find(tool => tool.name === "subagents_enable");
      console.log(JSON.stringify({ description: loader.description, snippet: loader.promptSnippet,
        guidelines: loader.promptGuidelines, parameters: loader.parameters,
        annotations: loader.annotations, outputSchema: loader.outputSchema ?? null }));
    ''')
    assert len(result["description"]) <= 160 and len(result["snippet"]) <= 120
    for text in (result["description"], result["snippet"]):
        assert "agent" in text and "child" in text
    assert "selection" in result["description"].lower() and "authorization" in result["description"].lower()
    guidelines = " ".join(result["guidelines"]).lower()
    assert "user" in guidelines and "instructions" in guidelines and "authorization" in guidelines
    assert "complexity alone" in guidelines
    assert result["parameters"] == {"type": "object", "properties": {}, "additionalProperties": False}
    assert result["annotations"] == {
        "readOnlyHint": False, "destructiveHint": False,
        "idempotentHint": True, "openWorldHint": False,
    }
    assert result["outputSchema"] is not None


def test_loader_success_and_returned_errors_match_output_schema_and_keep_details() -> None:
    result = run('''
      const { Check } = await import("typebox/value");
      await emit("session_start");
      const loader = registered.find(tool => tool.name === "subagents_enable");
      const success = await loader.execute("success", {}, undefined, undefined, ctx);
      const repeated = await loader.execute("repeat", {}, undefined, undefined, ctx);
      const available = pi.getAllTools;
      pi.getAllTools = () => registered.filter(tool => tool.name !== "agent_start");
      const unavailable = await loader.execute("excluded", {}, undefined, undefined, ctx);
      pi.getAllTools = available;
      pi.setActiveTools = () => { throw new Error("fixture selection failure"); };
      const failure = await loader.execute("failure", {}, undefined, undefined, ctx);
      pi.setActiveTools = next => { active = next.filter(name => name !== "agent_input"); };
      const ignored = await loader.execute("ignored", {}, undefined, undefined, ctx);
      const receipts = [success, repeated, unavailable, failure, ignored];
      console.log(JSON.stringify({ receipts, valid: receipts.map(receipt => !!loader.outputSchema && Check(loader.outputSchema, receipt.structuredContent)) }));
    ''')
    assert result["valid"] == [True] * 5
    for index, receipt in enumerate(result["receipts"]):
        data = receipt["structuredContent"]
        assert data == receipt["details"]
        assert data["childStarted"] is False
        if index < 2:
            assert data == {"outcome": "enabled", "enabled": ["agent_start", "agent_input", "agent_stop", "agent_inspect", "agent_list"], "childStarted": False}
            assert receipt.get("isError", False) is False
        else:
            assert receipt["isError"] is True and data["outcome"] == "refused"
            assert data["code"] == ("unavailable" if index == 2 else "activation-failed")
            assert data["unavailable" if index == 2 else "missing"] == ["agent_start", "agent_input", "agent_stop", "agent_inspect", "agent_list"]
            assert data["error"]


def test_loader_bounds_native_failure_without_mutating_original_diagnostic() -> None:
    result = run(r'''
      const { Check } = await import("typebox/value");
      const loader = registered.find(tool => tool.name === "subagents_enable");
      const diagnostic = "\x1b[31mfixture\x1b[0m\x1b]0;private-title\x07\x00 " + "长".repeat(3000);
      const original = new Error(diagnostic);
      pi.setActiveTools = () => { throw original; };
      const selection = await loader.execute("selection", {}, undefined, undefined, ctx);
      pi.getAllTools = () => { throw original; };
      const availability = await loader.execute("availability", {}, undefined, undefined, ctx);
      const receipts = [selection, availability];
      console.log(JSON.stringify({ receipts, valid: receipts.map(receipt => !!loader.outputSchema && Check(loader.outputSchema, receipt.structuredContent)),
        originalUnchanged: original.message === diagnostic, originalLength: original.message.length }));
    ''')
    assert result["valid"] == [True, True]
    assert result["originalUnchanged"] is True and result["originalLength"] > 3000
    for receipt in result["receipts"]:
        assert receipt["isError"] is True
        data = receipt["structuredContent"]
        assert data == receipt["details"] and data["code"] == "activation-failed"
        assert data["childStarted"] is False and data["missing"] == ["agent_start", "agent_input", "agent_stop", "agent_inspect", "agent_list"]
        assert len(data["error"]) <= 1024 and data["error"].endswith("… [diagnostic truncated]")
        assert receipt["content"][0]["text"] == data["error"]
        for text in (data["error"], receipt["content"][0]["text"]):
            assert "\x1b" not in text and "\x07" not in text and "\x00" not in text
            assert "private-title" not in text


def test_native_branch_selection_removals_do_not_leak_between_branches() -> None:
    result = run('''
      const definition = name => ({ name, description: name, parameters: { type: "object", properties: {} } });
      sessionManager.appendMessage({ role: "system", timestamp: 1, content: "",
        toolsAdded: [definition("subagents_enable"), definition("read")], toolsRemoved: [] });
      const base = sessionManager.getLeafId();
      sessionManager.appendMessage({ role: "system", timestamp: 2, content: "",
        toolsAdded: [definition("agent_start"), definition("agent_input"), definition("agent_stop"), definition("agent_inspect"), definition("agent_list")], toolsRemoved: [definition("subagents_enable")] });
      const enabledBranch = sessionManager.getLeafId();
      await emit("session_tree");
      const enabled = [...active];
      sessionManager.branch(base);
      sessionManager.appendMessage({ role: "system", timestamp: 3, content: "",
        toolsAdded: [], toolsRemoved: [definition("subagents_enable")] });
      await emit("session_tree");
      const removed = [...active];
      sessionManager.branch(base);
      await emit("session_tree");
      const lazy = [...active];
      sessionManager.branch(enabledBranch);
      ctx.model = { api: "unknown" };
      await emit("session_tree");
      console.log(JSON.stringify({ enabled, removed, lazy, restored: active }));
    ''')
    assert result == {
        "enabled": ["read", "agent_start", "agent_input", "agent_stop", "agent_inspect", "agent_list"],
        "removed": ["read"],
        "lazy": ["read", "subagents_enable"], "restored": ["read", "agent_start", "agent_input", "agent_stop", "agent_inspect", "agent_list"],
    }


def test_activation_respects_excluded_entrypoints_on_restore_and_call() -> None:
    result = run('''
      const loader = registered.find(tool => tool.name === "subagents_enable");
      pi.getAllTools = () => registered.filter(tool => tool.name !== "agent_start");
      await emit("session_start");
      const noAgent = [...active];
      const refusal = await loader.execute("excluded", {}, undefined, undefined, ctx);
      const afterRefusal = [...active];
      pi.getAllTools = () => registered.filter(tool => tool.name !== "subagents_enable");
      active = ["read", "agent_start", "agent_input", "agent_stop", "agent_inspect", "agent_list", "subagents_enable"];
      await emit("session_tree");
      console.log(JSON.stringify({ noAgent, afterRefusal, noLoader: active, refusal }));
    ''')
    assert result["noAgent"] == result["afterRefusal"] == ["read"]
    assert result["noLoader"] == ["read", "agent_start", "agent_input", "agent_stop", "agent_inspect", "agent_list"]
    assert result["refusal"]["isError"] is True
    assert result["refusal"]["details"]["unavailable"] == ["agent_start", "agent_input", "agent_stop", "agent_inspect", "agent_list"]
