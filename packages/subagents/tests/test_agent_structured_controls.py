"""Observed state, pending intent and failure codes never imply another outcome."""
from __future__ import annotations

from pathlib import Path

import pytest

from resident_support import run


def test_immediate_settled_answer_has_no_invented_pending_result(tmp_path: Path) -> None:
    run("""
      const result=await call({name:"coalesced-machine",prompt:"Run",tools:[]},{spawn:options=>{
        spawns.push(options);options.onUpdate({text:"2",turns:1,finalResponse:true,answerComplete:true});
        return {pid:42,accepted:Promise.resolve(true)};
      }});
      assert.equal(result.structuredContent.ok,true);assert.equal(result.structuredContent.state,"idle");
      assert.equal(result.structuredContent.nextActor,"caller");assert.equal(result.structuredContent.pendingIntent,undefined);
      assert.equal(notices.length,1);console.log(JSON.stringify({ok:true}));
    """,tmp_path)


@pytest.mark.parametrize("kind", ["rejected", "uncertain"])
def test_control_failure_distinguishes_rejection_from_uncertainty(tmp_path: Path, kind: str) -> None:
    run("""
      const started=await call({name:"control-machine",prompt:"First",tools:[]},{prompt:async()=>{
        if(KIND==="uncertain")throw new Error("No ACK");return false;
      }});final(0,"2");
      const result=await call({operation:"input",delivery:"next",session:started.details.session,prompt:"Next"});
      assert.equal(result.isError,true);assert.equal(result.structuredContent.operation,"input");
      assert.equal(result.structuredContent.session,started.details.session);assert.equal(result.structuredContent.dispatched,true);
      assert.equal(result.structuredContent.code,KIND==="uncertain"?"delivery-failed":"input-rejected");
      assert.equal(result.structuredContent.controlOutcome,KIND);
      assert.equal(result.structuredContent.pendingIntent,KIND==="uncertain"?"input":undefined);
      assert.equal(result.structuredContent.state,KIND==="uncertain"?"starting":"idle");
      assert.equal(result.structuredContent.nextActor,"caller");console.log(JSON.stringify({ok:true}));
    """.replace("KIND",f'"{kind}"'),tmp_path)


def test_start_failure_keeps_its_exact_stopped_record_in_machine_data(tmp_path: Path) -> None:
    run("""
      const result=await call({name:"failed-machine",prompt:"Run",tools:[]},{spawn:()=>({error:"LOCAL_SPAWN_FAILURE"})});
      assert.equal(result.isError,true);assert.equal(result.structuredContent.code,"spawn-failed");
      assert.equal(result.structuredContent.operation,"start");assert.equal(result.structuredContent.state,"stopped");
      assert.equal(result.structuredContent.controlOutcome,"rejected");
      const page=await call({ operation:"list" });
      const stopped=page.details.sessions.find((row)=>row.session===result.structuredContent.session);
      assert.equal(page.details.ok,true);assert.ok(stopped,"the failed start keeps its exact stopped record");
      assert.equal(stopped.error,"LOCAL_SPAWN_FAILURE");
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)
