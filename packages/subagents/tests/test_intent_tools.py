"""Observable contract for features/intent-tools.feature."""
from __future__ import annotations

import json
from pathlib import Path

from subagents_helpers import SRC, run_node

PREAMBLE = f"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {{ executeIntentTool, INTENT_TOOL_NAMES, INTENT_OUTPUT_SCHEMA }} from {json.dumps((SRC / 'intent-tools.ts').as_uri())};
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
