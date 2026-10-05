"""Public standalone child contract: features/resident-execution.feature."""
from __future__ import annotations

import json
from pathlib import Path

from resident_support import role, run
from subagents_helpers import SRC


def test_shared_launch_applies_directory_and_inherited_model(tmp_path: Path) -> None:
    result = run("""
      const result = await call({operation:"start",name:"shared",prompt:"Inspect",tools:["read"]});
      console.log(JSON.stringify({ok:result.details.ok,cwd:spawns[0].cwd,model:spawns[0].model,thinking:spawns[0].thinking,session:spawns[0].session,listed:roster.getAgent("shared")}));
    """, tmp_path)
    assert result["ok"] is True
    assert result["cwd"] == str(tmp_path)
    assert result["model"] == "test/parent"
    assert result["thinking"] == "low"
    assert result["session"] == "none"
    assert result["listed"]["model"] == "test/parent"


def test_disk_definition_wires_private_data_memory_and_original_project(tmp_path: Path) -> None:
    role(tmp_path, "durable", "tools: read\n")
    result = run("""
      const start=await call({name:"durable",prompt:"Inspect"});
      const options=spawns[0];
      const stopped=await call({operation:"stop",session:start.details.session});
      console.log(JSON.stringify({cwd:options.cwd,session:options.session,extensions:options.extensions,
        capabilities:options.capabilityTools,env:options.env,workspaces,stopped:stopped.details.ok,
        entry:roster.getAgent("durable"),body:options.description}));
    """, tmp_path)
    assert result["cwd"] == str(tmp_path)
    assert result["session"] == "persist"
    # The recovery contribution has no tools or storage; disk Memory stays separate.
    assert [Path(value).name for value in result["extensions"]] == ["stream-recovery.ts", "agent-extension.ts"]
    assert result["capabilities"] == ["agent_memory"]
    assert result["env"]["PI_SUBAGENT_ROLE"] == "durable"
    assert result["env"]["PI_SUBAGENT_SCOPE"] == "project"
    assert result["env"]["PI_SUBAGENT_DEFINITION"] == str(tmp_path / ".pi" / "agents" / "durable" / "agent.md")
    assert "PI_SUBAGENT_MEMORY" not in result["env"]
    assert result["env"]["PI_SUBAGENT_TOOLS"] == "read,agent_memory"
    assert result["env"]["PI_SUBAGENT_PROJECT_CWD"] == str(tmp_path)
    assert result["env"]["PI_SUBAGENT_WORKSPACE_PATH"] == result["entry"]["workspacePath"]
    assert result["entry"]["scope"] == "project"
    assert "isolation" not in result["entry"]
    assert result["workspaces"] == [{"agentName": "durable", "cwd": str(tmp_path), "parentSessionId": "resident-parent"}]
    assert str(tmp_path) in result["body"] and result["entry"]["workspacePath"] in result["body"]
    assert result["stopped"] is True


def test_call_cannot_widen_an_existing_role(tmp_path: Path) -> None:
    role(tmp_path, "reader", "tools: read\n")
    result = run("""
      const result=await call({operation:"start",name:"reader",prompt:"Inspect",tools:["bash"]});
      console.log(JSON.stringify({ok:result.details.ok,error:result.details.error,spawns:spawns.length,living:roster.livingAgents().length}));
    """, tmp_path)
    assert result["ok"] is False
    assert "bash" in result["error"]
    assert result["spawns"] == 0
    assert result["living"] == 0


def test_empty_grant_narrows_and_is_recorded(tmp_path: Path) -> None:
    role(tmp_path, "reader", "tools: read, bash\n")
    result = run("""
      const result=await call({operation:"start",name:"reader",prompt:"Inspect",tools:[]});
      console.log(JSON.stringify({ok:result.details.ok,grant:result.details.grant,spawn:spawns[0].tools,recorded:roster.getAgent("reader").tools}));
    """, tmp_path)
    assert result == {"ok": True, "grant": ["agent_memory"], "spawn": [], "recorded": ["agent_memory"]}


def test_stop_observes_close_after_recording_intent(tmp_path: Path) -> None:
    result = run("""
      const start=await call({operation:"start",name:"working",prompt:"Inspect",tools:[]});
      spawns[0].onUpdate({text:"in flight",turns:1,finalResponse:false});
      let planned;
      const result=await call({operation:"stop",session:start.details.session},{terminate:async()=>{
        planned=roster.getAgent("working").leaderRequestedEnd;
        spawns[0].onExit({pid:42,exitCode:null,signal:"SIGTERM",stdout:"",stderr:""});
        return {outcome:"closed"};
      }});
      console.log(JSON.stringify({ok:result.details.ok,planned,interrupted:result.details.interrupted,ended:notices.filter(n=>n.kind==="ended").length,error:roster.getAgent("working").error??null}));
    """, tmp_path)
    assert result["ok"] is True
    assert result["planned"] is True
    assert result["ended"] == 0
    assert result["error"] is None
    assert "working" in result["interrupted"] or "work" in result["interrupted"]


def test_unconfirmed_stop_retains_authority_and_can_retry(tmp_path: Path) -> None:
    result = run("""
      const start=await call({operation:"start",name:"waiting",prompt:"Inspect"});
      const refused=await call({operation:"stop",session:start.details.session},{terminate:async()=>({outcome:"unconfirmed"})});
      const held=roster.getAgent("waiting").status,planned=roster.getAgent("waiting").leaderRequestedEnd;
      final(0,"late result");
      const send=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"Unsafe retry"});
      const steer=await call({operation:"input",delivery:"steer",session:start.details.session,prompt:"Unsafe steer"});
      const retried=await call({operation:"stop",session:start.details.session});
      console.log(JSON.stringify({refused:refused.details.ok,held,planned,send:send.details.ok,steer:steer.details.ok,retried:retried.details.ok}));
    """, tmp_path)
    assert result["refused"] is False
    assert result["held"] != "stopped"
    assert result["planned"] is True
    assert result["send"] is result["steer"] is False
    assert result["retried"] is True


def test_resident_send_pins_role_once_and_reuses_session(tmp_path: Path) -> None:
    role(tmp_path, "resident", "tools: read\n")
    result = run("""
      const start=await call({operation:"start",name:"resident"});
      const first=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"FIRST"});
      final(0,"one");
      const second=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"SECOND"});
      final(0,"two");
      console.log(JSON.stringify({first:first.details.ok,second:second.details.ok,spawns:spawns.length,prompts,results:notices.filter(n=>n.kind==="result").map(n=>({text:n.text,turn:n.turn,session:n.session}))}));
    """, tmp_path)
    assert result["first"] is True
    assert result["second"] is True
    assert result["spawns"] == 1
    assert "PINNED ROLE BODY" in result["prompts"][0]["message"]
    assert result["prompts"][1]["message"] == "SECOND"
    assert [r["text"] for r in result["results"]] == ["one", "two"]
    assert [r["turn"] for r in result["results"]] == [1, 2]
    assert len({r["session"] for r in result["results"]}) == 1


def test_resident_busy_and_retired_handles_refuse_input(tmp_path: Path) -> None:
    result = run("""
      const start=await call({operation:"start",name:"resident",prompt:"FIRST"});
      const busy=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"busy"});
      await call({operation:"stop",session:start.details.session});
      const next=await call({operation:"start",name:"resident"});
      const stale=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"old"});
      console.log(JSON.stringify({busy:busy.details.ok,stale:stale.details.ok,prompts:prompts.length}));
    """, tmp_path)
    assert result == {"busy": False, "stale": False, "prompts": 0}


def test_rejected_resident_input_keeps_idle_and_role_unread(tmp_path: Path) -> None:
    role(tmp_path, "resident", "tools: read\n")
    result = run("""
      const start=await call({operation:"start",name:"resident"});
      accepted=false;
      const rejected=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"reject"});
      const status=roster.getAgent("resident").status;
      accepted=true;
      const retried=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"retry"});
      console.log(JSON.stringify({rejected:rejected.details.ok,status,retried:retried.details.ok,prompts}));
    """, tmp_path)
    assert result["rejected"] is False
    assert result["status"] == "idle"
    assert result["retried"] is True
    assert "PINNED ROLE BODY" in result["prompts"][1]["message"]


def test_interrupt_steers_a_working_child_without_opening_a_turn(tmp_path: Path) -> None:
    """A steer is the one input a busy child accepts. It has to reach the same
    process, leave the turn in flight, and not consume the turn's result."""
    result = run("""
      const start=await call({operation:"start",name:"working",prompt:"First"});
      // A turn in flight: the child has streamed something and not settled.
      spawns[0].onUpdate({text:"partial",turns:1,finalResponse:false});
      const steered=await call({operation:"input",delivery:"steer",session:start.details.session,prompt:"STOP AND CHECK THE SECOND FILE"});
      const statusDuring=roster.getAgent("working").status;
      const sent=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"late"});
      final(0,"steady");
      console.log(JSON.stringify({steered:steered.details.ok,outcome:steered.details.outcome,statusDuring,sent:sent.details.ok,steers,lateRefused:prompts.length,results:notices.filter(n=>n.kind==="result").map(n=>n.text)}));
    """, tmp_path)
    assert result["steered"] is True
    assert result["outcome"] == "interrupted"
    assert result["statusDuring"] == "working"
    assert result["steers"] == [{"name": "working", "message": "STOP AND CHECK THE SECOND FILE"}]
    # The steer did not become a queued prompt, and the turn still settled once.
    assert result["lateRefused"] == 0
    assert result["results"] == ["steady"]
    assert result["sent"] is False


def test_interrupt_receipt_waits_for_acknowledged_steer(tmp_path: Path) -> None:
    result = run("""
      let acknowledge,returned=false,immediate=false;
      const start=await call({name:"ack-steer",prompt:"First"},
        {steer:async()=>immediate || await new Promise(resolve=>acknowledge=resolve)});
      const pending=call({operation:"input",delivery:"steer",session:start.details.session,prompt:"Check"}).then(result=>(returned=true,result));
      await Promise.resolve();const before=returned;
      acknowledge(false);const refused=await pending;immediate=true;
      const steered=await call({operation:"input",delivery:"steer",session:start.details.session,prompt:"Check again"});
      console.log(JSON.stringify({before,refused:refused.details.ok,accepted:steered.details.ok,status:roster.getAgent("ack-steer").status}));
    """, tmp_path)
    assert result == {"before": False, "refused": False, "accepted": True, "status": "starting"}


def test_uncertain_steer_does_not_claim_accepted_input(tmp_path: Path) -> None:
    result = run("""
      const start=await call({name:"uncertain-steer",prompt:"First"},
        {steer:async()=>{throw new Error("Steer acknowledgement timed out; delivery may have occurred");}});
      spawns[0].onUpdate({text:"draft",turns:1,finalResponse:false});
      const refused=await call({operation:"input",delivery:"steer",session:start.details.session,prompt:"Check"});
      final(0,"answer");
      console.log(JSON.stringify({ok:refused.details.ok,text:refused.content[0].text,
        status:roster.getAgent("uncertain-steer").status,results:notices.filter(n=>n.kind==="result").length}));
    """, tmp_path)
    assert result["ok"] is False and "timed out" in result["text"]
    assert result["status"] == "idle" and result["results"] == 1


def test_interrupt_refuses_an_idle_or_retired_handle(tmp_path: Path) -> None:
    result = run("""
      const start=await call({operation:"start",name:"idle"});
      const idle=await call({operation:"input",delivery:"steer",session:start.details.session,prompt:"go"});
      await call({operation:"stop",session:start.details.session});
      const next=await call({operation:"start",name:"idle"});
      const retired=await call({operation:"input",delivery:"steer",session:start.details.session,prompt:"go"});
      console.log(JSON.stringify({idle:idle.details.ok,idleNamesSend:idle.content[0].text.includes("agent_input"),retired:retired.details.ok,steers}));
    """, tmp_path)
    assert result["idle"] is False
    assert result["idleNamesSend"] is True
    assert result["retired"] is False
    assert result["steers"] == []


def test_a_rejected_steer_leaves_the_child_working(tmp_path: Path) -> None:
    result = run("""
      const start=await call({operation:"start",name:"unsteerable",prompt:"First"});
      spawns[0].onUpdate({text:"partial",turns:1,finalResponse:false});
      steerAccepted=false;
      const refused=await call({operation:"input",delivery:"steer",session:start.details.session,prompt:"go"});
      console.log(JSON.stringify({refused:refused.details.ok,status:roster.getAgent("unsteerable").status,text:refused.content[0].text}));
    """, tmp_path)
    assert result["refused"] is False
    # A steer that never landed must not claim the child was redirected.
    assert result["status"] == "working"
    assert "did not accept" in result["text"]


def test_settlements_and_stop_never_reprovision_scratch_or_commit(tmp_path: Path) -> None:
    role(tmp_path, "durable", "tools: read\n")
    result = run("""
      const start=await call({name:"durable",prompt:"First"});
      final(0,"one");
      const second=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"Second"});
      final(0,"two");
      await call({operation:"stop",session:start.details.session});
      console.log(JSON.stringify({second:second.details.ok,workspaces:workspaces.length,spawns:spawns.length,
        results:notices.filter(n=>n.kind==="result").length}));
    """, tmp_path)
    assert result == {"second": True, "workspaces": 1, "spawns": 1, "results": 2}


def test_late_progress_cannot_revive_confirmed_stopped_child(tmp_path: Path) -> None:
    result = run("""
      const start=await call({name:"late",prompt:"First"});
      await call({operation:"stop",session:start.details.session});
      spawns[0].onUpdate({text:"late partial",turns:1,finalResponse:false});
      const streamed=roster.getAgent("late").status;
      final(0,"late settled result");
      const settled=roster.getAgent("late").status;
      const sent=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"Another"});
      console.log(JSON.stringify({streamed,settled,sent:sent.details.ok,results:notices.filter(n=>n.kind==="result").length}));
    """, tmp_path)
    assert result == {"streamed": "stopped", "settled": "stopped", "sent": False, "results": 1}


def test_hosted_resident_controls_fail_honestly_without_standalone_input(tmp_path: Path) -> None:
    result = run(f"""
      const {{setAgentHost}}=await import({json.dumps((SRC / 'child-execution.ts').as_uri())});
      setAgentHost({{start:()=>({{ok:true,session:"session:hosted:s1"}}),stop:async()=>({{ok:true}})}});
      roster.registerAgent({{name:"hosted",role:"hosted",spawnId:"s1",pid:8,status:"idle",scope:"session",standalone:false,createdAt:1,updatedAt:1}});
      const send=await call({{operation:"input",delivery:"next",session:"session:hosted:s1",prompt:"Run"}});
      roster.updateAgent("hosted",{{status:"working"}});
      const steer=await call({{operation:"input",delivery:"steer",session:"session:hosted:s1",prompt:"Check"}});
      console.log(JSON.stringify({{send:send.details.ok,steer:steer.details.ok,text:[send.content[0].text,steer.content[0].text],prompts:prompts.length,steers:steers.length}}));
    """, tmp_path)
    assert result["send"] is result["steer"] is False
    assert all("host" in text.lower() and "support" in text.lower() for text in result["text"])
    assert result["prompts"] == result["steers"] == 0


def test_hosted_temporary_keeps_acknowledged_controls_and_result_owner(tmp_path: Path) -> None:
    result = run(f"""
      const {{setAgentHost}}=await import({json.dumps((SRC / 'child-execution.ts').as_uri())});
      const hosted=[],inputs=[],interrupts=[],hostResults=[];
      let acknowledge;
      setAgentHost({{
        start(request){{hosted.push(request);roster.registerAgent({{name:request.name,role:request.name,spawnId:"host-id",
          pid:8,status:"working",scope:"session",standalone:false,createdAt:1,updatedAt:1}});
          return {{ok:true,session:`session:${{request.name}}:host-id`}};}},
        async send(name,spawnId,message){{
          assert.equal(roster.getAgent(name).status,"idle","The host owns reservation, not the tool router");
          inputs.push({{name,spawnId,message}});roster.updateAgent(name,{{status:"working",sequenceEnded:false}});
          return await new Promise(resolve=>acknowledge=resolve);
        }},
        async interrupt(name,spawnId,message){{interrupts.push({{name,spawnId,message}});return {{ok:true}};}},
        stop:async()=>({{ok:true}}),
      }});
      const start=await call({{name:"host-loop",prompt:"First"}});
      roster.updateAgent("host-loop",{{status:"idle",sequenceEnded:true}});hostResults.push("one");
      let returned=false;
      const pending=call({{operation:"input",delivery:"next",session:start.details.session,prompt:"Second"}}).then(result=>(returned=true,result));
      await Promise.resolve();const beforeAck=returned;acknowledge({{ok:true}});const send=await pending;
      const busy=roster.getAgent("host-loop").status;
      // Republish a different host: this incarnation still belongs to its first one.
      setAgentHost({{start:()=>{{throw new Error("replacement host start");}},send:async()=>{{throw new Error("wrong host send");}},
        interrupt:async()=>{{throw new Error("wrong host steer");}},stop:async()=>{{throw new Error("wrong host stop");}}}});
      const steer=await call({{operation:"input",delivery:"steer",session:start.details.session,prompt:"Check"}});
      roster.updateAgent("host-loop",{{status:"idle",sequenceEnded:true}});hostResults.push("two");
      const stop=await call({{operation:"stop",session:start.details.session}});
      console.log(JSON.stringify({{start:start.details.ok,send:send.details.ok,steer:steer.details.ok,stop:stop.details.ok,
        beforeAck,busy,hosted:hosted.length,inputs,interrupts,hostResults,standaloneSpawns:spawns.length,
        standaloneResults:notices.length,status:roster.getAgent("host-loop").status}}));
    """, tmp_path)
    assert result["start"] is result["send"] is result["steer"] is result["stop"] is True
    assert result["beforeAck"] is False and result["busy"] == "working"
    assert result["hosted"] == 1 and result["standaloneSpawns"] == result["standaloneResults"] == 0
    assert result["inputs"] == [{"name": "host-loop", "spawnId": "host-id", "message": "Second"}]
    assert result["interrupts"] == [{"name": "host-loop", "spawnId": "host-id", "message": "Check"}]
    assert result["hostResults"] == ["one", "two"] and result["status"] == "stopped"


def test_hosted_uncertain_input_retains_host_reserved_state(tmp_path: Path) -> None:
    result = run(f"""
      const {{setAgentHost}}=await import({json.dumps((SRC / 'child-execution.ts').as_uri())});
      let before;
      setAgentHost({{
        start(request){{roster.registerAgent({{name:request.name,role:request.name,spawnId:"uncertain",pid:8,status:"idle",scope:"session",createdAt:1,updatedAt:1}});return {{ok:true,session:`session:${{request.name}}:uncertain`}};}},
        async send(name){{before=roster.getAgent(name).status;roster.updateAgent(name,{{status:"working",error:"Acknowledgement timed out"}});return {{ok:false,error:"Acknowledgement timed out; execution may have started"}};}},
        interrupt:async()=>({{ok:true}}),stop:async()=>({{ok:true}}),
      }});
      const start=await call({{name:"host-uncertain"}});
      const sent=await call({{operation:"input",delivery:"next",session:start.details.session,prompt:"Run"}});
      const second=await call({{operation:"input",delivery:"next",session:start.details.session,prompt:"Duplicate"}});
      console.log(JSON.stringify({{before,sent:sent.details.ok,second:second.details.ok,status:roster.getAgent("host-uncertain").status,error:roster.getAgent("host-uncertain").error}}));
    """, tmp_path)
    assert result == {"before": "idle", "sent": False, "second": False, "status": "working", "error": "Acknowledgement timed out"}


def test_host_without_resident_controls_refuses_start_before_effects(tmp_path: Path) -> None:
    result = run(f"""
      const {{setAgentHost}}=await import({json.dumps((SRC / 'child-execution.ts').as_uri())});
      let starts=0;setAgentHost({{start:()=>{{starts++;return {{ok:true,session:"session:old:s1"}};}},stop:async()=>({{ok:true}})}});
      const start=await call({{name:"old",prompt:"Run"}});
      console.log(JSON.stringify({{ok:start.details.ok,text:start.content[0].text,starts,spawns:spawns.length}}));
    """, tmp_path)
    assert result["ok"] is False
    assert "send" in result["text"] and "interrupt" in result["text"]
    assert result["starts"] == result["spawns"] == 0


def test_confirmed_shutdown_retires_only_exact_controls(tmp_path: Path) -> None:
    result = run(f"""
      const {{retireAgentControls}}=await import({json.dumps((SRC / 'child-execution.ts').as_uri())});
      const first=await call({{name:"cleanup"}});
      const handle=first.details.session;
      const liveRefused=retireAgentControls(handle);
      roster.updateAgent("cleanup",{{status:"stopped",leaderRequestedEnd:true}});
      const next=await call({{name:"cleanup"}});
      const residentBindings=globalThis[Symbol.for("fradser.pi-subagents.resident-bindings")];
      const hostBindings=globalThis[Symbol.for("fradser.pi-subagents.host-bindings")];
      hostBindings.set(handle,{{}});
      const retired=retireAgentControls(handle);
      const sent=await call({{operation:"input",delivery:"next",session:next.details.session,prompt:"Continue"}});
      console.log(JSON.stringify({{liveRefused,retired,sent:sent.details.ok,oldResident:residentBindings.has(handle),
        oldHost:hostBindings.has(handle),nextResident:residentBindings.has(next.details.session)}}));
    """, tmp_path)
    assert result == {"liveRefused": False, "retired": True, "sent": True,
                      "oldResident": False, "oldHost": False, "nextResident": True}


def test_throwing_spawn_releases_only_its_reservation(tmp_path: Path) -> None:
    result = run("""
      let returned;
      try { returned=await call({operation:"start",name:"failure",prompt:"Run"},{spawn:()=>{throw new Error("spawn refused");}}); }
      catch { returned={details:{ok:"threw"}}; }
      const retry=await call({operation:"start",name:"failure",prompt:"Retry"});
      console.log(JSON.stringify({ok:returned.details.ok,retry:retry.details.ok}));
    """, tmp_path)
    assert result == {"ok": False, "retry": True}


def test_throwing_termination_retains_stop_intent_and_can_retry(tmp_path: Path) -> None:
    result = run("""
      const start=await call({operation:"start",name:"waiting"});
      let result;
      try { result=await call({operation:"stop",session:start.details.session},{terminate:async()=>{throw new Error("terminate refused");}}); }
      catch { result={details:{ok:"threw"}}; }
      const prompted=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"Continue"});
      const stopped=await call({operation:"stop",session:start.details.session});
      console.log(JSON.stringify({ok:result.details.ok,prompted:prompted.details.ok,stopped:stopped.details.ok}));
    """, tmp_path)
    assert result == {"ok": False, "prompted": False, "stopped": True}


def test_successful_ack_after_close_cannot_report_a_living_start(tmp_path: Path) -> None:
    result = run("""
      let acknowledge;
      const pending=call({name:"exited"},{spawn:o=>(spawns.push(o),{pid:42,readiness:new Promise(resolve=>acknowledge=resolve)})});
      spawns[0].onExit({pid:42,exitCode:0,signal:null,stdout:"",stderr:""});
      acknowledge(true);const start=await pending;
      console.log(JSON.stringify({ok:start.details.ok,status:roster.getAgent("exited").status}));
    """, tmp_path)
    assert result == {"ok": False, "status": "stopped"}


def test_old_positive_ack_cannot_report_or_modify_successor(tmp_path: Path) -> None:
    result = run("""
      let acknowledge;
      const pending=call({name:"same"},{spawn:o=>(spawns.push(o),{pid:42,readiness:new Promise(resolve=>acknowledge=resolve)})});
      spawns[0].onExit({pid:42,exitCode:0,signal:null,stdout:"",stderr:""});
      const successor=await call({name:"same",prompt:"New work"});
      const handle=roster.getAgent("same").spawnId;
      acknowledge(true);const old=await pending;
      console.log(JSON.stringify({old:old.details.ok,new:successor.details.ok,status:roster.getAgent("same").status,
        preserved:handle===roster.getAgent("same").spawnId,error:roster.getAgent("same").error??null}));
    """, tmp_path)
    assert result == {"old": False, "new": True, "status": "starting", "preserved": True, "error": None}


def test_idle_readiness_is_confirmed_before_start_returns(tmp_path: Path) -> None:
    result = run("""
      ready=false;
      let terminated=0;
      const start=await call({operation:"start",name:"resident"},{terminate:async()=>{terminated++;return {outcome:"closed"};}});
      console.log(JSON.stringify({ok:start.details.ok,terminated,status:roster.getAgent("resident").status}));
    """, tmp_path)
    assert result == {"ok": False, "terminated": 1, "status": "stopped"}
