from __future__ import annotations

# --- Merged from test_intent_tools.py ---
"""Observable contract for features/intent-tools.feature."""

import json
from pathlib import Path

import pytest
from subagents_helpers import SRC, run_node

PREAMBLE = f"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {{ executeIntentTool, registerIntentTools, INTENT_TOOL_NAMES, INTENT_OUTPUT_SCHEMA }} from {json.dumps((SRC / 'intent-tools.ts').as_uri())};
import * as roster from {json.dumps((SRC / 'roster.ts').as_uri())};
roster.resetRoster();
const spawns=[],prompts=[],steers=[],notices=[];
const options={{
  cwd:process.env.PI_TEST_CWD,
  spawn:(value)=>{{spawns.push(value);return {{pid:42,accepted:Promise.resolve(true),readiness:Promise.resolve(true)}};}},
  prompt:async(name,prompt)=>{{prompts.push({{name,prompt}});return true;}},
  steer:async(name,prompt)=>{{steers.push({{name,prompt}});return true;}},
  terminate:async()=>({{outcome:'closed'}}),
  deliverSessionResult:notice=>notices.push(notice),
}};
const {{ Check }} = await import('typebox/value');
const call=async(name,args,extra={{}})=>{{
  const result=await executeIntentTool(name,args,{{...options,...extra}});
  assert.equal(Check(INTENT_OUTPUT_SCHEMA,result.structuredContent),true,JSON.stringify(result.structuredContent));
  return result;
}};
const tick=async()=>{{for(let i=0;i<15;i++)await Promise.resolve();}};
const final=(text)=>spawns[0].onUpdate({{text,turns:1,finalResponse:true,answerComplete:true,stopReason:'stop'}});
const capture=()=>{{const defs={{}};registerIntentTools({{registerTool:t=>defs[t.name]=t}},options);return defs;}};
"""


def run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(PREAMBLE + script, env_overrides={
        "PI_TEST_CWD": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "HOME": str(tmp_path),
    })


def test_start_identity_and_label_are_independent(tmp_path: Path) -> None:
    directory = tmp_path / ".pi" / "agents" / "reader"
    directory.mkdir(parents=True)
    (directory / "agent.md").write_text("---\nname: reader\ndescription: saved\ntools: read\n---\nSAVED ROLE\n")
    result = run("""
      const temporary=await call('agent_start',{label:'reader',prompt:'FIRST',instructions:'TEMP ROLE',tools:[]});
      const controller=new AbortController();controller.abort();
      const aborted=await call('agent_start',{identity:'reader',prompt:'NO'},{signal:controller.signal});
      const missing=await call('agent_start',{identity:'missing',prompt:'NO'});
      const conflict=await call('agent_start',{identity:'reader',instructions:'NO',prompt:'NO'});
      const saved=await call('agent_start',{identity:'reader',label:'other-display',prompt:'SECOND'});
      console.log(JSON.stringify({temporary:temporary.structuredContent,saved:saved.structuredContent,
        missing:missing.structuredContent.ok,conflict:conflict.structuredContent.ok,aborted:aborted.structuredContent.ok,
        spawns:spawns.map(value=>({body:value.description,policy:value.session,env:value.env}))}));
    """, tmp_path)
    assert result["temporary"]["ok"] is True
    assert result["temporary"]["label"] == "reader"
    assert result["temporary"]["scope"] == "session"
    assert result["saved"]["identity"] == "reader"
    assert result["saved"]["label"] == "other-display"
    assert result["missing"] is result["conflict"] is result["aborted"] is False
    assert len(result["spawns"]) == 2
    assert "TEMP ROLE" in result["spawns"][0]["body"]
    assert "SAVED ROLE" not in result["spawns"][0]["body"]
    assert result["spawns"][0]["policy"] == "none"
    assert result["spawns"][1]["env"]["PI_SUBAGENT_ROLE"] == "reader"


@pytest.mark.parametrize("authored,display", [
    ("File Review", "file-review"),
    ("Task SQL measured optimization", "task-sql-measured-optimization"),
    ("Fix OAuth 2.0!", "fix-oauth-2-0"),
])
def test_an_authored_label_becomes_one_identifier_shaped_display_name(tmp_path: Path, authored: str, display: str) -> None:
    """features/intent-tools.feature: a label is one identifier-shaped display name.

    A person reads the child's name in a row, so `Xxx Xxx` is not a name a row can
    carry: the same word list with hyphens is. Every surface that paints or
    addresses the child reads that one projected name, and the authored text stays
    the temporary role's purpose.
    """
    result = run(f"""
      const {{ formatSessionResult }} = await import({json.dumps((SRC / 'session-result.ts').as_uri())});
      const started=await call('agent_start',{{label:{json.dumps(authored)},prompt:'FIRST'}});
      final('ANSWER');await tick();
      const notice=notices.find(value=>value.kind==='result');
      const name=started.structuredContent.name;
      console.log(JSON.stringify({{receipt:started.structuredContent.label,
        roster:roster.getAgent(name).label,notice:notice.name,
        envelope:formatSessionResult(notice).split('\\n')[0],role:started.structuredContent.role,
        content:started.content.map(part=>part.text).join('\\n')}}));
    """, tmp_path)
    assert result["receipt"] == display
    assert result["roster"] == display
    assert result["notice"] == display
    assert f'from="{display}"' in result["envelope"]
    assert f"Label: {display}." in result["content"]
    # The temporary role keeps the authored text; only the display name is projected.
    assert result["role"] == authored


def test_a_label_with_no_identifier_character_keeps_the_childs_own_name(tmp_path: Path) -> None:
    """A display name stays one token, so a label no identifier can carry is absent."""
    result = run("""
      const started=await call('agent_start',{label:'任务 🛠',prompt:'FIRST'});
      const name=started.structuredContent.name;
      console.log(JSON.stringify({label:started.structuredContent.label,name,
        roster:roster.getAgent(name).label}));
    """, tmp_path)
    assert result["name"].startswith("subagent-"), result["name"]
    assert result["label"] == result["name"] == result["roster"]


def test_fifo_results_and_fast_settlement_wait_for_ack(tmp_path: Path) -> None:
    result = run("""
      let ack;
      options.prompt=async(name,prompt)=>{prompts.push({name,prompt});if(prompt==='SECOND'){final('two');return await new Promise(resolve=>ack=resolve);}return true;};
      const start=await call('agent_start',{prompt:'FIRST'});
      const second=await call('agent_input',{session:start.structuredContent.session,prompt:'SECOND',delivery:'next'});
      const third=await call('agent_input',{session:start.structuredContent.session,prompt:'THIRD',delivery:'next'});
      const before=prompts.length;
      final('one');await tick();
      const during=prompts.map(value=>value.prompt);
      ack(true);await tick();final('three');await tick();
      console.log(JSON.stringify({before,during,prompts:prompts.map(value=>value.prompt),
        ids:[start,second,third].map(value=>value.structuredContent.inputId),
        results:notices.filter(value=>value.kind==='result').map(value=>({text:value.text,id:value.inputId}))}));
    """, tmp_path)
    assert result["before"] == 0
    assert result["during"] == ["SECOND"]
    assert result["prompts"] == ["SECOND", "THIRD"]
    assert [notice["text"] for notice in result["results"]] == ["one", "two", "three"]
    assert [notice["id"] for notice in result["results"]] == result["ids"]
    assert len(set(result["ids"])) == 3


def test_cancelled_wait_and_stop_preserve_reserved_inputs(tmp_path: Path) -> None:
    result = run("""
      const start=await call('agent_start',{prompt:'FIRST'});final('one');await tick();
      let ack;const controller=new AbortController();
      options.prompt=async()=>await new Promise(resolve=>ack=resolve);
      // The original start pins resident controls; later caller options cannot replace them.
      await call('agent_stop',{session:start.structuredContent.session});
      const live=await call('agent_start',{prompt:'FIRST'});spawns[1].onUpdate({text:'one',turns:1,finalResponse:true,answerComplete:true,stopReason:'stop'});await tick();
      const pending=call('agent_input',{session:live.structuredContent.session,prompt:'SECOND',delivery:'next'},
        {signal:controller.signal});
      await tick();controller.abort();const cancelled=await pending;
      ack(true);await tick();
      const third=await call('agent_input',{session:live.structuredContent.session,prompt:'THIRD',delivery:'next'});
      const stopped=await call('agent_stop',{session:live.structuredContent.session});
      const stale=await call('agent_input',{session:live.structuredContent.session,prompt:'NO',delivery:'next'});
      console.log(JSON.stringify({cancelled:cancelled.structuredContent,stopped:stopped.structuredContent.ok,
        stale:stale.structuredContent.ok,third:third.structuredContent.inputId,
        notices:notices.filter(value=>value.kind==='input-cancelled').map(value=>value.inputId)}));
    """, tmp_path)
    assert result["cancelled"]["disposition"] == "uncertain"
    assert result["cancelled"]["inputId"]
    assert result["stopped"] is True
    assert result["stale"] is False
    assert result["third"] in result["notices"]


def test_schema_refusals_steer_and_queue_limits(tmp_path: Path) -> None:
    result = run("""
      const invalid=await call('agent_start',{label:'only-name'});
      const start=await call('agent_start',{prompt:'FIRST'});
      const wrong=await call('agent_input',{session:start.structuredContent.session,prompt:'NO',delivery:'auto'});
      const extra=await call('agent_list',{prompt:'NO'});
      const steer=await call('agent_input',{session:start.structuredContent.session,prompt:'ADJUST',delivery:'steer'});
      for(let index=0;index<8;index++)await call('agent_input',{session:start.structuredContent.session,prompt:String(index),delivery:'next'});
      const full=await call('agent_input',{session:start.structuredContent.session,prompt:'overflow',delivery:'next'});
      await call('agent_stop',{session:start.structuredContent.session});
      const idle=await call('agent_start',{prompt:'FINISH'});spawns[1].onUpdate({text:'done',turns:1,finalResponse:true,answerComplete:true,stopReason:'stop'});await tick();
      const idleSteer=await call('agent_input',{session:idle.structuredContent.session,prompt:'NO',delivery:'steer'});
      const bytes=await call('agent_input',{session:idle.structuredContent.session,prompt:'x'.repeat(256*1024+1),delivery:'next'});
      const inspected=await call('agent_list',{});
      console.log(JSON.stringify({invalid:invalid.structuredContent.ok,wrong:wrong.structuredContent.ok,
        extra:extra.structuredContent.ok,steer:steer.structuredContent.ok,steers,full:full.structuredContent,
        idleSteer:idleSteer.structuredContent.ok,bytes:bytes.structuredContent.code,inspect:inspected.structuredContent,
        tools:INTENT_TOOL_NAMES}));
    """, tmp_path)
    assert result["invalid"] is result["wrong"] is result["extra"] is False
    assert result["steer"] is True
    assert len(result["steers"]) == 1
    assert result["full"]["ok"] is False
    assert result["full"]["code"] == "queue-full"
    assert result["idleSteer"] is False
    assert result["bytes"] == "queue-full"
    assert result["inspect"]["sessions"][0]["inputId"]
    assert result["inspect"]["sessions"][0]["pendingInputs"] == 0
    assert result["tools"] == ["agent_start", "agent_input", "agent_stop", "agent_list"]


def test_start_requires_a_prompt_even_when_an_identity_is_named(tmp_path: Path) -> None:
    result = run("""
      const missing=await call('agent_start',{identity:'reader'});
      console.log(JSON.stringify({ok:missing.structuredContent.ok,code:missing.structuredContent.code,spawns:spawns.length}));
    """, tmp_path)
    assert result == {"ok": False, "code": "invalid-parameters", "spawns": 0}


def test_startup_receipt_is_one_title_plus_compact_facts(tmp_path: Path) -> None:
    """features/intent-tools.feature: a short receipt says each fact once.

    One Title: line names the child; model and tools are two labeled rows; the
    exact handles share one compact line; one line closes with the async guard.
    No blank section, no fact repeated.
    """
    result = run("""
      const started=await call('agent_start',{label:'reader',prompt:'FIRST',model:'p/m',tools:['read']});
      console.log(JSON.stringify({text:started.content.map(part=>part.text).join('\\n')}));
    """, tmp_path)
    text = result["text"]
    lines = text.split("\n")
    assert "\r" not in text, text
    assert len(lines) == 5, lines
    assert lines[0].startswith("Title: ") and "reader" in lines[0], lines[0]
    assert lines[1] == "Model: p/m", lines[1]
    assert lines[2] == "Tools: read", lines[2]
    assert all(line.strip() for line in lines), lines
    # The exact handles and role share one line below the three headline facts.
    assert "session:" in lines[3] and "Input:" in lines[3] and "Label: reader." in lines[3], lines[3]
    assert text.count("reader") == 2, text  # once in Title, once in Label
    assert "arrives asynchronously" in lines[4], lines[4]


def test_the_guardrail_reaches_the_model_and_has_one_wording(tmp_path: Path) -> None:
    """features/intent-tools.feature: the delegation rule is model-visible.

    Pi injects a direct tool's `description` into the model's tool listing on
    every call, but `namespace.instructions` is NOT part of tool listings (it is
    returned only to codemode's describeNamespace). Moving the no-poll rule
    solely into namespace.instructions would hide it from the model. Keep one
    authoritative guardrail, reachable through the visible agent_start
    description, with the namespace copy sourced from the same string.
    """
    result = run("""
      const defs=capture();
      const names=['agent_start','agent_input','agent_stop','agent_list'];
      const rule=/never poll|do not poll|never sleep|duplicate child|repeat uncertain input/i;
      const descriptions=Object.fromEntries(names.map(name=>[name,defs[name].description]));
      const instruction=defs.agent_start.namespace.instructions;
      console.log(JSON.stringify({
        startVisibleRule:rule.test(descriptions.agent_start),
        namespaceHasRule:rule.test(instruction),
        otherDescriptionsRepeat:['agent_input','agent_stop','agent_list'].filter(n=>rule.test(descriptions[n])),
        startMentionsAsync:/asynchronously|later turn/i.test(descriptions.agent_start),
        sharedWording:descriptions.agent_start.includes('The result arrives asynchronously')
          && instruction.includes('The result arrives asynchronously'),
        noAutomatically:!names.some(n=>/automatically/.test(descriptions[n])) && !/automatically/.test(instruction),
      }));
    """, tmp_path)
    assert result["startVisibleRule"] is True, result
    assert result["namespaceHasRule"] is True, result
    assert result["otherDescriptionsRepeat"] == [], result
    assert result["startMentionsAsync"] is True, result
    assert result["sharedWording"] is True, result
    assert result["noAutomatically"] is True, result


# --- Merged from test_intent_activation.py ---
"""Selection and schema contracts for the intent family (ADR-0008)."""

import json
import os
from pathlib import Path
import subprocess

import pytest

from subagents_helpers import PACKAGE, run_node

_m1_PREAMBLE = f"""
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
    result = run_node(_m1_PREAMBLE + """
      await emit();const fresh=[...active];
      pi.getAllTools=()=>registered.filter(tool=>tool.name!=='agent_input');await emit();
      console.log(JSON.stringify({fresh,excluded:active,required:registered.filter(tool=>family.includes(tool.name)).map(tool=>[tool.name,tool.parameters.required])}));
    """)
    assert result["fresh"] == ["read", "agent_start", "agent_input", "agent_stop", "agent_list"]
    assert result["excluded"] == ["read"], "a partial family is not offered"
    assert result["required"] == [["agent_start", ["prompt"]], ["agent_input", ["session", "prompt", "delivery"]],
                                   ["agent_stop", ["session"]], ["agent_list", []]]


def test_partial_host_selection_keeps_recorded_branch_removals() -> None:
    result = run_node(_m1_PREAMBLE + """
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
    result = run_node(_m1_PREAMBLE + """
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
    result = run_node(_m1_PREAMBLE + """
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
    result = run_node(_m1_PREAMBLE + """
      sessionManager.appendMessage({role:'user',content:'Existing history',timestamp:1});
      active=['read','agent','agent_inspect',...family,'subagents_enable'];
      await emit();const restored=[...active];
      // Excluding one family member withdraws the whole family rather than half of it.
      pi.getAllTools=()=>registered.filter(tool=>tool.name!=='agent_input');
      await emit();console.log(JSON.stringify({restored,excluded:active}));
    """)
    assert result["restored"] == ["read", "agent_start", "agent_input", "agent_stop", "agent_list"]
    assert result["excluded"] == ["read"], "a partial family is not offered"


# --- Merged from test_intent_host.py ---
"""Exact hosted input authority through the five-tool surface."""

import json
from pathlib import Path

import pytest
from subagents_helpers import SRC, run_node

_m2_PREAMBLE = f"""
import {{ executeIntentTool }} from {json.dumps((SRC / 'intent-tools.ts').as_uri())};
import {{ setAgentHost }} from {json.dumps((SRC / 'child-execution.ts').as_uri())};
import * as roster from {json.dumps((SRC / 'roster.ts').as_uri())};
roster.resetRoster();
let active='',allow=true;const sends=[],notices=[];
const host={{
  start(request){{active=request.name;roster.registerAgent({{name:active,role:active,spawnId:'pinned',pid:1,
    status:'working',sequenceEnded:false,standalone:false,scope:'session',createdAt:1,updatedAt:1}});
    return {{ok:true,session:`session:${{active}}:pinned`}};}},
  authorizeInput(){{return allow?{{ok:true}}:{{ok:false,error:'Task verification is frozen'}};}},
  async send(name,id,prompt){{sends.push({{name,id,prompt}});roster.updateAgent(name,{{status:'working',sequenceEnded:false}});return {{ok:true}};}},
  async interrupt(){{return {{ok:true}};}},
  async stop(name){{roster.updateAgent(name,{{status:'stopped'}});return {{ok:true}};}},
}};
setAgentHost(host);
const call=(tool,args)=>executeIntentTool(tool,args,{{cwd:process.env.PI_TEST_CWD,deliverSessionResult:notice=>notices.push(notice)}});
const tick=async()=>{{for(let i=0;i<15;i++)await Promise.resolve();}};
"""


def test_original_host_and_policy_are_rechecked_before_queued_dispatch(tmp_path: Path) -> None:
    result = run_node(_m2_PREAMBLE + """
      const start=await call('agent_start',{label:'team-child',prompt:'FIRST'});
      const queued=await call('agent_input',{session:start.structuredContent.session,prompt:'NEXT',delivery:'next'});
      allow=false;roster.updateAgent(active,{status:'idle',sequenceEnded:true});await tick();
      const denied=notices.map(notice=>notice.inputId);
      allow=true;
      setAgentHost({...host,send:async()=>{throw new Error('Replacement global host must not receive input');}});
      const accepted=await call('agent_input',{session:start.structuredContent.session,prompt:'AFTER',delivery:'next'});
      console.log(JSON.stringify({queued:queued.structuredContent.inputId,denied,sends,accepted:accepted.structuredContent.ok}));
    """, env_overrides={"PI_TEST_CWD": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"), "HOME": str(tmp_path)})
    assert result["queued"] in result["denied"]
    assert result["accepted"] is True
    assert [entry["prompt"] for entry in result["sends"]] == ["AFTER"]


def test_temporary_label_reaches_the_host_as_a_session_role(tmp_path: Path) -> None:
    result = run_node(_m2_PREAMBLE + """
      let definition;
      setAgentHost({...host,start(request){definition=request.definition;return host.start(request);}});
      const start=await call('agent_start',{label:'friendly label',prompt:'FIRST',tools:['read']});
      console.log(JSON.stringify({definition,receipt:start.structuredContent}));
    """, env_overrides={"PI_TEST_CWD": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"), "HOME": str(tmp_path)})
    assert result["definition"]["description"] == "friendly label"
    assert result["definition"]["tools"] == ["read"]
    # The role keeps the authored purpose; the display name is its projected token.
    assert result["receipt"]["label"] == "friendly-label"


def test_steer_receipt_keeps_predecessor_id_after_late_ack(tmp_path: Path) -> None:
    result = run_node(_m2_PREAMBLE + """
      let ack;
      setAgentHost({...host,interrupt:async()=>await new Promise(resolve=>ack=resolve)});
      const start=await call('agent_start',{prompt:'FIRST'});
      const first=start.structuredContent.inputId;
      const steering=call('agent_input',{session:start.structuredContent.session,prompt:'ADJUST',delivery:'steer'});
      await tick();
      const next=await call('agent_input',{session:start.structuredContent.session,prompt:'SECOND',delivery:'next'});
      roster.updateAgent(active,{status:'idle',sequenceEnded:true});await tick();
      const during=roster.getAgent(active).inputId;
      ack({ok:true});const receipt=await steering;
      console.log(JSON.stringify({first,second:next.structuredContent.inputId,during,steered:receipt.structuredContent.inputId}));
    """, env_overrides={"PI_TEST_CWD": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"), "HOME": str(tmp_path)})
    assert result["during"] == result["second"]
    assert result["steered"] == result["first"]


@pytest.mark.parametrize("failure", ["negative", "rejected-promise"])
def test_negative_hosted_startup_never_grants_steer_or_next_authority(tmp_path: Path, failure: str) -> None:
    result = run_node(_m2_PREAMBLE + """
      let interrupts=0;
      setAgentHost({...host,start(request){host.start(request);
        if(process.env.PI_HOST_FAILURE==='rejected-promise')return Promise.reject(new Error('Kickoff acknowledgement missing'));
        return {ok:false,error:'Kickoff rejected'};},
        interrupt:async()=>{interrupts++;return {ok:true};}});
      const start=await call('agent_start',{prompt:'FIRST'});
      const session=`session:${active}:pinned`;
      const steer=await call('agent_input',{session,prompt:'NO',delivery:'steer'});
      const next=await call('agent_input',{session,prompt:'NO',delivery:'next'});
      const stopped=await call('agent_stop',{session});
      console.log(JSON.stringify({start:start.structuredContent.ok,steer:steer.structuredContent.ok,
        next:next.structuredContent.ok,interrupts,stopped:stopped.structuredContent.ok}));
    """, env_overrides={"PI_TEST_CWD": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"), "HOME": str(tmp_path),
                        "PI_HOST_FAILURE": failure})
    assert result == {"start": False, "steer": False, "next": False, "interrupts": 0, "stopped": True}
