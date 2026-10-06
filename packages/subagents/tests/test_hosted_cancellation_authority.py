"""Scoped review regressions: exact hosted owner and late cancelled failures."""
from __future__ import annotations

from pathlib import Path

import pytest

from resident_support import run

HOST_PREAMBLE = """
const {setAgentHost}=await import('file://'+process.cwd()+'/src/child-execution.ts');
const bindings=globalThis[Symbol.for('fradser.pi-subagents.host-bindings')];
const record=(name,id,status='starting')=>({name,role:name,spawnId:id,pid:7,status,scope:'session',standalone:false,createdAt:1,updatedAt:1});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
"""


@pytest.mark.parametrize('returned_handle', ['original', 'successor'])
@pytest.mark.parametrize('cancel', [False, True])
def test_late_start_cannot_retarget_successor_owner(
    tmp_path: Path, returned_handle: str, cancel: bool,
) -> None:
    run(HOST_PREAMBLE + """
      let confirm;const callsA=[],callsB=[];
      const hostA={start:request=>{
        roster.registerAgent(record(request.name,'old'));
        return new Promise(resolve=>confirm=resolve);
      },send:async()=>{callsA.push('send');return {ok:true}},interrupt:async()=>{callsA.push('interrupt');return {ok:true}},
      stop:async()=>{callsA.push('stop');return {ok:true}}};
      const hostB={start:request=>{roster.registerAgent(record(request.name,'new','idle'));return {ok:true,session:`session:${request.name}:new`}},
        send:async(name)=>{callsB.push('send');roster.updateAgent(name,{status:'working'});return {ok:true}},
        interrupt:async()=>{callsB.push('interrupt');return {ok:true}},stop:async()=>{callsB.push('stop');return {ok:true}}};
      setAgentHost(hostA);const controller=new AbortController();
      const pending=call({name:'ownership',prompt:'First'},{signal:controller.signal});
      if(CANCEL){controller.abort();const cancelled=await pending;assert.equal(cancelled.details.outcome,'cancelled');}
      roster.updateAgent('ownership',{status:'stopped'});
      setAgentHost(hostB);const second=await call({name:'ownership',tools:[]});assert.equal(second.details.ok,true);
      const before=JSON.stringify(roster.getAgent('ownership'));
      confirm({ok:true,session:RETURNED==='original'?'session:ownership:old':second.details.session});await flush();
      if(!CANCEL){const refused=await pending;assert.equal(refused.details.ok,false,'late start cannot report successor acceptance');}
      assert.equal(JSON.stringify(roster.getAgent('ownership')),before,'old confirmation cannot modify successor facts');
      const sent=await call({operation:'input',delivery:'next',session:second.details.session,prompt:'Next'});assert.equal(sent.details.ok,true);
      const steered=await call({operation:'input',delivery:'steer',session:second.details.session,prompt:'Steer'});assert.equal(steered.details.ok,true);
      const stopped=await call({operation:'stop',session:second.details.session});assert.equal(stopped.details.ok,true);
      assert.deepEqual(callsB,['send','interrupt','stop']);assert.deepEqual(callsA,[]);
      assert.equal(spawns.length,0);setAgentHost(undefined);console.log(JSON.stringify({ok:true}));
    """.replace('CANCEL','true' if cancel else 'false').replace('RETURNED',f'"{returned_handle}"'),tmp_path)


@pytest.mark.parametrize('owner', ['same-host', 'other-host'])
@pytest.mark.parametrize('cancel', [False, True])
def test_synchronous_reentrant_start_never_pins_owned_successor(
    tmp_path: Path, owner: str, cancel: bool,
) -> None:
    run(HOST_PREAMBLE + """
      const callsA=[],callsB=[];let confirm;let successorStart;let successorSnapshot;
      let calls=0;const successor='session:reentrant:new';
      const hostB={start:request=>{roster.registerAgent(record(request.name,'new','idle'));return {ok:true,session:successor}},
        send:async(name)=>{callsB.push('send');roster.updateAgent(name,{status:'working'});return {ok:true}},
        interrupt:async()=>{callsB.push('interrupt');return {ok:true}},stop:async()=>{callsB.push('stop');return {ok:true}}};
      const hostA={start:request=>{
        calls++;
        if(calls>1){roster.registerAgent(record(request.name,'new','idle'));return {ok:true,session:successor}}
        roster.registerAgent(record(request.name,'old'));roster.updateAgent(request.name,{status:'stopped'});
        setAgentHost(OWNER==='same-host'?hostA:hostB);
        successorStart=call({name:request.name,tools:[]});
        successorSnapshot=JSON.stringify(roster.getAgent(request.name));
        return new Promise(resolve=>confirm=resolve);
      },send:async(name)=>{callsA.push('send');roster.updateAgent(name,{status:'working'});return {ok:true}},
        interrupt:async()=>{callsA.push('interrupt');return {ok:true}},stop:async()=>{callsA.push('stop');return {ok:true}}};
      setAgentHost(hostA);const controller=new AbortController();
      const old=call({name:'reentrant',prompt:'Old input'},{signal:controller.signal});
      if(CANCEL){controller.abort();const cancelled=await old;assert.equal(cancelled.details.outcome,'cancelled');
        assert.notEqual(cancelled.details.session,successor,"cancellation must not advertise another start's handle");}
      const newStart=await successorStart;
      assert.equal(newStart.details.ok,true,newStart.content[0].text);assert.equal(newStart.details.session,successor);
      const expectedOwner=OWNER==='same-host'?hostA:hostB;
      assert.equal(bindings.get(successor),expectedOwner,'existing owner must survive before any confirmation');
      const before=JSON.stringify(roster.getAgent('reentrant'));
      confirm({ok:true,session:successor});await flush();
      if(!CANCEL){const failed=await old;assert.equal(failed.details.ok,false);assert.notEqual(failed.details.session,successor);}
      assert.equal(JSON.stringify(roster.getAgent('reentrant')),before);
      assert.equal(bindings.get(successor),expectedOwner);
      assert.equal((await call({operation:'input',delivery:'next',session:successor,prompt:'Next'})).details.ok,true);
      assert.equal((await call({operation:'input',delivery:'steer',session:successor,prompt:'Steer'})).details.ok,true);
      assert.equal((await call({operation:'stop',session:successor})).details.ok,true);
      assert.deepEqual(OWNER==='same-host'?callsA:callsB,['send','interrupt','stop']);
      assert.deepEqual(OWNER==='same-host'?callsB:callsA,[]);
      assert.ok(successorSnapshot);setAgentHost(undefined);console.log(JSON.stringify({ok:true}));
    """.replace('OWNER',f'"{owner}"').replace('CANCEL','true' if cancel else 'false'),tmp_path)


@pytest.mark.parametrize('owner', ['same-host', 'other-host'])
def test_start_without_an_original_reservation_cannot_claim_an_existing_session(
    tmp_path: Path, owner: str,
) -> None:
    run(HOST_PREAMBLE + """
      const stopped=[];const host={start:()=>({ok:true,session:'session:incumbent:original'}),
        send:async()=>({ok:true}),interrupt:async()=>({ok:true}),stop:async()=>{stopped.push('wrong');return {ok:true}}};
      roster.registerAgent(record('incumbent','original','idle'));
      const existingOwner=OWNER==='same-host'?host:{...host,stop:async()=>{stopped.push('original');return {ok:true}}};
      bindings.set('session:incumbent:original',existingOwner);setAgentHost(host);
      const before=JSON.stringify(roster.getAgent('incumbent'));
      const result=await call({name:'incumbent',prompt:'Must not reuse a living start'});
      assert.equal(result.details.ok,false,'a returned live handle without a new reservation is not a start');
      assert.equal(bindings.get('session:incumbent:original'),existingOwner);
      assert.equal(JSON.stringify(roster.getAgent('incumbent')),before);assert.deepEqual(stopped,[]);
      setAgentHost(undefined);console.log(JSON.stringify({ok:true}));
    """.replace('OWNER',f'"{owner}"'),tmp_path)


@pytest.mark.parametrize('cancel', [False, True])
def test_pending_hosted_start_is_explicitly_stoppable_before_ack(tmp_path: Path, cancel: bool) -> None:
    run(HOST_PREAMBLE + """
      let confirm;const stopped=[];const host={start:request=>{
        roster.registerAgent(record(request.name,'pending'));
        return new Promise(resolve=>confirm=resolve);
      },send:async()=>({ok:true}),interrupt:async()=>({ok:true}),stop:async(name,id)=>{stopped.push({name,id});return {ok:true}}};
      setAgentHost(host);const controller=new AbortController();
      const pending=call({name:'closable',prompt:'Run'},{signal:controller.signal});
      let session='session:closable:pending';
      if(CANCEL){controller.abort();const cancelled=await pending;assert.equal(cancelled.details.session,session);}
      assert.equal(bindings.get(session),host,'closure owner must be bound before confirmation');
      assert.deepEqual(stopped,[],'wait cancellation alone never closes a process');
      const closed=await call({operation:'stop',session});assert.equal(closed.details.ok,true,closed.content[0].text);
      assert.deepEqual(stopped,[{name:'closable',id:'pending'}]);assert.equal(roster.getAgent('closable').status,'stopped');
      assert.equal(bindings.has(session),false);
      confirm({ok:true,session});await flush();
      if(!CANCEL)assert.equal((await pending).details.ok,false,'stopped startup cannot report success');
      assert.equal(roster.getAgent('closable').status,'stopped');assert.equal(bindings.has(session),false,'late ACK cannot restore retired controls');
      assert.deepEqual(stopped,[{name:'closable',id:'pending'}]);setAgentHost(undefined);console.log(JSON.stringify({ok:true}));
    """.replace('CANCEL','true' if cancel else 'false'),tmp_path)


@pytest.mark.parametrize('ownership', ['standalone', 'hosted'])
@pytest.mark.parametrize('operation', ['input', 'steer', 'stop'])
@pytest.mark.parametrize('kind', ['throw', 'negative'])
def test_cancelled_returned_or_thrown_control_failure_is_readable(
    tmp_path: Path, ownership: str, operation: str, kind: str,
) -> None:
    run(HOST_PREAMBLE + """
      let settle;let count=0;const ack=new Promise(resolve=>settle=resolve);
      const control=async()=>{count++;const result=await ack;if(KIND==='throw')throw new Error(result);return result;};
      let start;
      if(OWNERSHIP==='hosted'){
        setAgentHost({start:request=>{roster.registerAgent(record(request.name,'late-error','idle'));
          return {ok:true,session:`session:${request.name}:late-error`}},
          send:async(name)=>{roster.updateAgent(name,{status:'starting'});return control()},interrupt:control,stop:control});
        start=await call({name:'diagnostic'});
        if(ACTION==='steer')roster.updateAgent('diagnostic',{status:'working'});
        roster.updateAgent('diagnostic',{liveText:'PREVIOUS_ANSWER'});
      }else{
        const seams=ACTION==='input'?{prompt:control}:ACTION==='steer'?{steer:control}:{terminate:control};
        start=await call({name:'diagnostic',prompt:'First',tools:[]},seams);final(0,'PREVIOUS_ANSWER');
        if(ACTION==='steer')roster.updateAgent('diagnostic',{status:'working'});
      }
      const controller=new AbortController();
      const pending=call(ACTION==="stop"?{operation:"stop",session:start.details.session}:{operation:"input",delivery:ACTION==="steer"?"steer":"next",session:start.details.session,prompt:'New input'},
        {signal:controller.signal,...(OWNERSHIP==='standalone'&&ACTION==='stop'?{terminate:control}:{})});
      controller.abort();const cancelled=await pending;assert.equal(cancelled.details.outcome,'cancelled');
      const status=roster.getAgent('diagnostic').status;const beforeNotices=notices.length;
      const diagnostic='LATE_ACK_ERROR';
      settle(KIND==='throw'?diagnostic:OWNERSHIP==='hosted'?{ok:false,error:diagnostic}:ACTION==='stop'?{outcome:'unconfirmed'}:false);
      await flush();const listed=await call({operation:'list'});
      // ADR-0008 left no inspection operation: the roster is the one read that
      // survives, and it keeps the exact incarnation a cancelled wait owned.
      const retained=listed.details.sessions.find(row=>row.session===start.details.session);
      assert.ok(retained,'the roster keeps the exact incarnation the cancelled wait dispatched');
      assert.ok(retained.error,'a cancelled operation failure must remain readable on the roster');
      if(KIND==='throw'||OWNERSHIP==='hosted')assert.ok(retained.error.includes(diagnostic));
      // A definitive native false reply may restore idle by the existing
      // send contract. Only uncertain/rejected promise errors retain busy state;
      // the diagnostic recorder itself never guesses a status transition.
      const expected=OWNERSHIP==='standalone'&&ACTION==='input'&&KIND==='negative'?'idle':status;
      assert.equal(roster.getAgent('diagnostic').status,expected,'diagnostic recording cannot invent a process outcome');
      if(ACTION==='stop')assert.equal(roster.getAgent('diagnostic').leaderRequestedEnd,true);
      assert.equal(count,1);assert.equal(notices.length,beforeNotices);setAgentHost(undefined);console.log(JSON.stringify({ok:true}));
    """.replace('OWNERSHIP',f'"{ownership}"').replace('ACTION',f'"{operation}"').replace('KIND',f'"{kind}"'),tmp_path)


@pytest.mark.parametrize('operation', ['input', 'steer', 'stop'])
def test_cancelled_late_failure_never_writes_to_replacement(tmp_path: Path, operation: str) -> None:
    run(HOST_PREAMBLE + """
      let reject;const ack=new Promise((_resolve,rejectPromise)=>reject=rejectPromise);
      const host={start:request=>{roster.registerAgent(record(request.name,'old','idle'));return {ok:true,session:`session:${request.name}:old`}},
        send:async(name)=>{roster.updateAgent(name,{status:'starting'});return ack},interrupt:async()=>ack,stop:async()=>ack};
      setAgentHost(host);const start=await call({name:'replacement'});
      if(ACTION==='steer')roster.updateAgent('replacement',{status:'working'});
      const controller=new AbortController();const pending=call(ACTION==="stop"?{operation:"stop",session:start.details.session}:{operation:"input",delivery:ACTION==="steer"?"steer":"next",session:start.details.session,prompt:'Run'},{signal:controller.signal});controller.abort();await pending;
      roster.updateAgent('replacement',{status:'stopped'});roster.registerAgent({...record('replacement','new','idle'),error:'SUCCESSOR_ONLY'});
      const before=JSON.stringify(roster.getAgent('replacement'));reject(new Error('PREDECESSOR_ONLY'));await flush();
      assert.equal(JSON.stringify(roster.getAgent('replacement')),before);assert.equal(roster.getAgent('replacement').error,'SUCCESSOR_ONLY');
      setAgentHost(undefined);console.log(JSON.stringify({ok:true}));
    """.replace('ACTION',f'"{operation}"'),tmp_path)
