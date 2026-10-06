"""Cancellation stops caller waiting, not acknowledged resident lifetime."""
from __future__ import annotations

from pathlib import Path

import pytest

from resident_support import run


# ADR-0008 retired `inspect`, so the surviving executor operations are the four
# below and nothing addresses a single child any more.
@pytest.mark.parametrize("operation", ["start", "input", "list", "stop"])
def test_aborted_signal_refuses_before_any_effect(tmp_path: Path, operation: str) -> None:
    run("""
      const controller=new AbortController();controller.abort();
      const result=await call(ACTION==="start"?{operation:"start",name:"cancelled",prompt:"Run"}
        :ACTION==="list"?{operation:"list"}
        :ACTION==="stop"?{operation:"stop",session:"session:missing:exact"}
        :{operation:"input",delivery:"next",session:"session:missing:exact",prompt:"Run"},
        {signal:controller.signal});
      assert.equal(result.details.ok,false);assert.equal(result.details.outcome,"cancelled");
      assert.equal(result.details.dispatched,false);assert.equal(result.details.controlOutcome,"not-dispatched");
      assert.deepEqual([spawns.length,prompts.length,steers.length,notices.length,workspaces.length],[0,0,0,0,0]);
      assert.deepEqual(roster.listAgents(),[]);console.log(JSON.stringify({ok:true}));
    """.replace("ACTION", f'"{operation}"'),tmp_path)


def test_cancelled_start_wait_retains_late_ack_and_result_on_original_incarnation(tmp_path: Path) -> None:
    run("""
      const controller=new AbortController();let acknowledge;
      const startupAck=new Promise(resolve=>acknowledge=resolve);
      let stops=0;
      const pending=call({name:"cancelled-start",prompt:"  authored kickoff\\n",tools:[]},{signal:controller.signal,
        spawn:options=>(spawns.push(options),{pid:42,accepted:startupAck}),
        terminate:async()=>{stops++;return {outcome:"closed"}}});
      controller.abort();
      // The race only proves the caller was not left waiting: the runtime work on this
      // path is longer than a hundred milliseconds under load, so the budget is a
      // hang detector rather than a timing assumption.
      const cancelled=await Promise.race([pending,new Promise(resolve=>setTimeout(()=>resolve({timedOut:true}),2000))]);
      assert.ok(!cancelled.timedOut,"tool cancellation must release the caller before acknowledgement");
      assert.equal(cancelled.details.outcome,"cancelled");assert.equal(cancelled.details.controlOutcome,"uncertain");
      assert.equal(cancelled.details.pendingIntent,"start");assert.equal(cancelled.details.dispatched,true);
      assert.equal(cancelled.details.session,"session:cancelled-start:"+roster.getAgent("cancelled-start").spawnId);
      assert.equal(roster.getAgent("cancelled-start").status,"starting");assert.equal(stops,0);
      acknowledge(true);await new Promise(resolve=>setImmediate(resolve));
      final(0,"2");assert.equal(roster.getAgent("cancelled-start").status,"idle");assert.equal(notices.length,1);
      const next=await call({operation:"input",delivery:"next",session:cancelled.details.session,prompt:"Next"});
      assert.equal(next.details.ok,true);assert.equal(prompts.length,1);assert.equal(spawns.length,1);
      final(0,"3");assert.equal(notices.length,2);assert.equal(stops,0);
      assert.deepEqual(notices.map(notice=>notice.session),[cancelled.details.session,cancelled.details.session]);
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


@pytest.mark.parametrize("operation", ["input", "steer", "stop"])
def test_cancelled_control_wait_preserves_late_outcome(tmp_path: Path, operation: str) -> None:
    run("""
      const controller=new AbortController();let acknowledge;let controls=0;
      const acknowledgement=new Promise(resolve=>acknowledge=resolve);
      const seam=ACTION==="input"?{prompt:async()=>{controls++;return acknowledgement}}:
        ACTION==="steer"?{steer:async()=>{controls++;return acknowledgement}}:
        {terminate:async()=>{controls++;return acknowledgement}};
      const started=await call({name:"cancelled-control",prompt:"Run",tools:[]},seam);
      // A steer addresses a working child, which the runtime reaches on the child's
      // first frame; the other deliveries address the child a settled turn leaves idle.
      if(ACTION==="steer")roster.updateAgent(started.details.name,{status:"working"});else final(0,"first");
      // One `input` operation carries both deliveries, so the pending intent a
      // cancelled wait reports is the operation, never the delivery.
      const pending=call({operation:ACTION==="stop"?"stop":"input",session:started.details.session,
        ...(ACTION==="stop"?{}:{delivery:ACTION==="steer"?"steer":"next",prompt:"  exact input\\n"})},{...seam,signal:controller.signal});
      controller.abort();
      // The race only proves the caller was not left waiting: the runtime work on this
      // path is longer than a hundred milliseconds under load, so the budget is a
      // hang detector rather than a timing assumption.
      const cancelled=await Promise.race([pending,new Promise(resolve=>setTimeout(()=>resolve({timedOut:true}),2000))]);
      assert.ok(!cancelled.timedOut);assert.equal(cancelled.details.outcome,"cancelled");
      assert.equal(cancelled.details.pendingIntent,ACTION==="stop"?"stop":"input");
      assert.equal(cancelled.details.session,started.details.session);
      assert.equal(controls,1);assert.equal(spawns.length,1);
      if(ACTION==="stop")assert.equal(roster.getAgent(started.details.name).leaderRequestedEnd,true);
      else assert.notEqual(roster.getAgent(started.details.name).status,"idle");
      acknowledge(ACTION==="stop"?{outcome:"closed"}:true);
      await new Promise(resolve=>setImmediate(resolve));
      if(ACTION==="stop")assert.equal(roster.getAgent(started.details.name).status,"stopped");
      else {final(0,"later");assert.equal(roster.getAgent(started.details.name).status,"idle");}
      assert.equal(controls,1);console.log(JSON.stringify({ok:true}));
    """.replace("ACTION", f'"{operation}"'),tmp_path)


def test_aborting_parent_turn_after_acceptance_does_not_close_child(tmp_path: Path) -> None:
    run("""
      const controller=new AbortController();let stops=0;
      const started=await call({name:"accepted",prompt:"Run",tools:[]},{signal:controller.signal,
        terminate:async()=>{stops++;return {outcome:"closed"}}});
      assert.equal(started.details.ok,true);controller.abort();
      final(0,"still valid");assert.equal(notices.length,1);assert.equal(stops,0);
      assert.equal(roster.getAgent("accepted").status,"idle");
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_reservation_callback_abort_keeps_exact_committed_start(tmp_path: Path) -> None:
    run("""
      const controller=new AbortController();let acknowledge;
      const startupAck=new Promise(resolve=>acknowledge=resolve);
      const stopObserve=roster.observeAgentRoster(()=>controller.abort());
      const pending=call({name:"reservation-cancelled",prompt:"Run",tools:[]},{signal:controller.signal,
        spawn:options=>(spawns.push(options),{pid:42,accepted:startupAck})});
      stopObserve();const cancelled=await pending;
      assert.equal(cancelled.details.outcome,"cancelled");assert.equal(cancelled.details.dispatched,true);
      assert.equal(cancelled.details.session,"session:reservation-cancelled:"+roster.getAgent("reservation-cancelled").spawnId);
      acknowledge(true);await new Promise(resolve=>setImmediate(resolve));final(0,"2");
      assert.equal(notices.length,1);assert.equal(spawns.length,1);
      assert.equal(roster.getAgent("reservation-cancelled").status,"idle");
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_cancelled_host_start_retains_its_original_exact_reservation(tmp_path: Path) -> None:
    run("""
      const {setAgentHost}=await import("file://"+process.cwd()+"/src/child-execution.ts");
      let confirm;setAgentHost({start:request=>{
        roster.registerAgent({name:request.name,role:request.name,spawnId:"host-original",pid:7,
          status:"starting",createdAt:1,updatedAt:1});
        return new Promise(resolve=>confirm=resolve);
      },send:async()=>({ok:true}),interrupt:async()=>({ok:true}),stop:async()=>({ok:true})});
      const controller=new AbortController();
      const pending=call({name:"host-cancelled",prompt:"Run"},{signal:controller.signal});controller.abort();
      const cancelled=await pending;
      assert.equal(cancelled.details.outcome,"cancelled");assert.equal(cancelled.details.session,"session:host-cancelled:host-original");
      assert.equal(cancelled.details.state,"starting");
      roster.updateAgent("host-cancelled",{status:"idle"});confirm({ok:true,session:cancelled.details.session});
      await new Promise(resolve=>setImmediate(resolve));
      const sent=await call({operation:"input",delivery:"next",session:cancelled.details.session,prompt:"Continue"});
      assert.equal(sent.details.ok,true);setAgentHost(undefined);console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_cancelled_late_host_failure_cannot_write_to_successor(tmp_path: Path) -> None:
    run("""
      const {setAgentHost}=await import("file://"+process.cwd()+"/src/child-execution.ts");
      let reject;
      setAgentHost({start:()=>new Promise((_resolve,rejectPromise)=>reject=rejectPromise),
        send:async()=>({ok:true}),interrupt:async()=>({ok:true}),stop:async()=>({ok:true})});
      const controller=new AbortController();
      const pending=call({name:"host-pending",prompt:"Run"},{signal:controller.signal});controller.abort();
      // The race only proves the caller was not left waiting: the runtime work on this
      // path is longer than a hundred milliseconds under load, so the budget is a
      // hang detector rather than a timing assumption.
      const cancelled=await Promise.race([pending,new Promise(resolve=>setTimeout(()=>resolve({timedOut:true}),2000))]);
      assert.ok(!cancelled.timedOut);assert.equal(cancelled.details.outcome,"cancelled");
      setAgentHost(undefined);const successor=await call({name:"host-pending",tools:[]});
      reject(new Error("LATE_HOST_FAILURE"));await new Promise(resolve=>setImmediate(resolve));
      assert.equal(roster.getAgent("host-pending").error,undefined);
      assert.equal(roster.getAgent("host-pending").status,"idle");
      assert.ok(successor.details.session);console.log(JSON.stringify({ok:true}));
    """,tmp_path)
