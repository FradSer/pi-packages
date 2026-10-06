"""Selection and schema contracts for the intent family (ADR-0008)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from subagents_helpers import PACKAGE, run_node

PREAMBLE = f"""
import {{ SessionManager }} from '@earendil-works/pi-coding-agent';
import {{ Check }} from 'typebox/value';
import extension from {json.dumps((PACKAGE / 'index.ts').as_uri())};
const registered=[],handlers=new Map();let active=['read','agent'];
const pi={{registerTool:tool=>registered.push(tool),registerMessageRenderer(){{}},events:{{emit(){{}}}},
  on:(name,handler)=>{{const list=handlers.get(name)??[];list.push(handler);handlers.set(name,list);}},
  getAllTools:()=>registered,getActiveTools:()=>active,setActiveTools:names=>active=names}};
extension(pi);
const sessionManager=SessionManager.inMemory();const ctx={{sessionManager,model:{{api:'unknown'}}}};
const emit=async()=>{{for(const handler of handlers.get('session_start')??[])await handler({{}},ctx);}};
const family=['agent_start','agent_input','agent_stop','agent_list'];
"""

@pytest.mark.parametrize("selected", ["agent_list", "agent", "agent_inspect", "read",
    "agent_list,subagents_enable", "agent_start,agent_input,agent_stop,agent_inspect",
    "agent_start,agent_input,agent_stop,agent_inspect,subagents_enable"])
def test_native_explicit_intent_selection_is_not_widened(tmp_path: Path, selected: str) -> None:
    # Each case pairs one host selection with what the contract must leave active.
    # A selection that names a retired tool is scrubbed, not widened into a family
    # and not left on the wire, exactly like the retired `agent` selection.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "PI_OFFLINE": "1",
        "PI_SKIP_VERSION_CHECK": "1",
        "PI_TELEMETRY": "0",
        "PI_ACTIVATION_EXCLUDED": selected,
    }
    result = subprocess.run(["node", str(PACKAGE / "tests" / "activation-transcript-fixture.ts")],
                            cwd=PACKAGE, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"excludedPreserved":true' in result.stdout


def test_fresh_selection_and_explicit_exclusion() -> None:
    """A host that registers one member short of the family is offered none of it.
    Every member addresses the same exact sessions, so a half family would make a
    caller guess which controls survived."""
    result = run_node(PREAMBLE + """
      await emit();const fresh=[...active];
      pi.getAllTools=()=>registered.filter(tool=>tool.name!=='agent_input');await emit();
      console.log(JSON.stringify({fresh,excluded:active,required:registered.filter(tool=>family.includes(tool.name)).map(tool=>[tool.name,tool.parameters.required])}));
    """)
    assert result["fresh"] == ["read", "agent_start", "agent_input", "agent_stop", "agent_list"]
    assert result["excluded"] == ["read"], "a partial family is not offered"
    assert result["required"] == [["agent_start", ["prompt"]], ["agent_input", ["session", "prompt", "delivery"]],
                                   ["agent_stop", ["session"]], ["agent_list", []]]


def test_partial_host_selection_keeps_recorded_branch_removals() -> None:
    result = run_node(PREAMBLE + """
      active=['read','agent_list','subagents_enable'];
      await emit();
      const definition=name=>({name,description:name,parameters:{type:'object'}});
      sessionManager.appendMessage({role:'system',timestamp:1,content:'',toolsAdded:[definition('agent_list'),definition('subagents_enable')],toolsRemoved:[]});
      const base=sessionManager.getLeafId();
      sessionManager.appendMessage({role:'system',timestamp:2,content:'',toolsAdded:[],toolsRemoved:[definition('agent_list')]});
      await emit();const removed=[...active];
      sessionManager.branch(base);await emit();
      console.log(JSON.stringify({removed,restored:active}));
    """)
    assert result["removed"] == ["read", "subagents_enable"]
    assert result["restored"] == ["read", "agent_list", "subagents_enable"]


def test_legacy_and_new_branch_restore_cannot_mix() -> None:
    result = run_node(PREAMBLE + """
      const definition=name=>({name,description:name,parameters:{type:'object'}});
      // A branch that recorded the retired tool keeps its work and receives the intent family.
      sessionManager.appendMessage({role:'system',timestamp:1,content:'',toolsAdded:[definition('agent')],toolsRemoved:[]});
      await emit();const legacy=[...active];
      sessionManager.appendMessage({role:'system',timestamp:2,content:'',toolsAdded:family.map(definition),toolsRemoved:[definition('agent')]});
      await emit();console.log(JSON.stringify({legacy,next:active}));
    """)
    assert result["legacy"] == ["read", "agent_start", "agent_input", "agent_stop", "agent_list"]
    assert result["next"] == ["read", "agent_start", "agent_input", "agent_stop", "agent_list"]
    assert "agent" not in result["legacy"] + result["next"], "the retired tool is scrubbed from both branches"


def test_new_refusal_has_typed_structured_output() -> None:
    result = run_node(PREAMBLE + """
      const definition=name=>({name,description:name,parameters:{type:'object'}});
      sessionManager.appendMessage({role:'system',timestamp:1,content:'',toolsAdded:[definition('subagents_enable')],toolsRemoved:[]});
      await emit();
      const enabled=await registered.find(tool=>tool.name==='subagents_enable').execute('enable',{},undefined,undefined,ctx);
      const results=[];
      for(const tool of registered.filter(tool=>family.includes(tool.name))){
        const receipt=await tool.execute('invalid',{unknown:true},undefined,undefined,ctx);
        results.push({name:tool.name,valid:Check(tool.outputSchema,receipt.structuredContent),error:receipt.isError});
      }
      console.log(JSON.stringify({results,enabled:enabled.structuredContent.enabled,active}));
    """)
    assert result["enabled"] == ["agent_start", "agent_input", "agent_stop", "agent_list"]
    assert not {"agent", "agent_inspect"} & set(result["active"]), "a retired tool is never selected"
    assert all(entry["valid"] and entry["error"] for entry in result["results"])


def test_old_transcript_without_selection_keeps_one_family_without_loader() -> None:
    result = run_node(PREAMBLE + """
      sessionManager.appendMessage({role:'user',content:'Existing history',timestamp:1});
      active=['read','agent','agent_inspect',...family,'subagents_enable'];
      await emit();const restored=[...active];
      // Excluding one family member withdraws the whole family rather than half of it.
      pi.getAllTools=()=>registered.filter(tool=>tool.name!=='agent_input');
      await emit();console.log(JSON.stringify({restored,excluded:active}));
    """)
    assert result["restored"] == ["read", "agent_start", "agent_input", "agent_stop", "agent_list"]
    assert result["excluded"] == ["read"], "a partial family is not offered"
