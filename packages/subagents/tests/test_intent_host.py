"""Exact hosted input authority through the five-tool surface."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from subagents_helpers import SRC, run_node

PREAMBLE = f"""
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
    result = run_node(PREAMBLE + """
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
    result = run_node(PREAMBLE + """
      let definition;
      setAgentHost({...host,start(request){definition=request.definition;return host.start(request);}});
      const start=await call('agent_start',{label:'friendly label',prompt:'FIRST',tools:['read']});
      console.log(JSON.stringify({definition,receipt:start.structuredContent}));
    """, env_overrides={"PI_TEST_CWD": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"), "HOME": str(tmp_path)})
    assert result["definition"]["description"] == "friendly label"
    assert result["definition"]["tools"] == ["read"]
    assert result["receipt"]["label"] == "friendly-label"


def test_steer_receipt_keeps_predecessor_id_after_late_ack(tmp_path: Path) -> None:
    result = run_node(PREAMBLE + """
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
    result = run_node(PREAMBLE + """
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
