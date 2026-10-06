"""Public handler enforces the operation contract and machine output budget."""
from __future__ import annotations

from pathlib import Path

from resident_support import run


def test_exported_handler_refuses_invalid_types_and_misplaced_fields_before_effects(tmp_path: Path) -> None:
    run("""
      const invalid=[null,[],{operation:true,name:"must-not-start"},{operation:""},{name:"bad-tools",tools:["read",7]},
        {name:"bad-fork",fork:"true"},{operation:"list",prompt:"ignored"},{operation:"list",tools:["bash"]},
        { operation:"list", session:"session:none:exact",prompt:"ignored"},
        {operation:"stop",session:"session:none:exact",tools:["bash"]},
        {operation:"input",delivery:"next",session:"session:none:exact",prompt:"Run",model:"fake/model"}];
      for(const input of invalid){
        const out=await call(input);assert.equal(out.details.ok,false,JSON.stringify(input));
        assert.equal(out.isError,true);
      }
      assert.deepEqual([spawns.length,prompts.length,steers.length,notices.length,workspaces.length],[0,0,0,0,0]);
      assert.deepEqual(roster.listAgents(),[]);console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_validation_failure_keeps_known_operation_without_guessing_an_invalid_start(tmp_path: Path) -> None:
    run("""
      const list=await call({operation:"list",prompt:"misplaced"});
      const start=await call({name:"invalid",tools:[7]});
      const wrong=await call({operation:"nonsense",name:"never"});
      assert.equal(list.structuredContent.operation,"list");assert.equal(start.structuredContent.operation,"start");
      assert.equal(wrong.structuredContent.operation,"invalid");
      assert.equal(wrong.structuredContent.requestedOperation,"nonsense");
      assert.deepEqual(roster.listAgents(),[]);assert.equal(spawns.length,0);
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_handler_preserves_authored_prompt_and_role_bytes(tmp_path: Path) -> None:
    run("""
      const prompt="  user input\\n\\n";const role="  standing role\\n";const description="  role purpose  ";
      const start=await call({name:"authored",prompt,role_prompt:role,description,tools:[]});
      assert.equal(start.details.ok,true);assert.equal(start.details.prompt,prompt);
      assert.ok(spawns[0].description.endsWith(prompt));
      assert.ok(spawns[0].description.includes(role));
      const {resolveAgent}=await import("file://"+process.cwd()+"/src/agents.ts");
      assert.equal(resolveAgent("authored",cwd).prompt,role,"session role registry must retain authored instructions");
      assert.equal(resolveAgent("authored",cwd).description,description);
      final(0,"2");const input="  next input\\n";
      const sent=await call({operation:"input",delivery:"next",session:start.details.session,prompt:input});
      assert.equal(sent.details.ok,true);assert.equal(prompts[0].message,input);assert.equal(sent.details.prompt,input);
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_all_operation_results_are_machine_readable_and_schema_valid(tmp_path: Path) -> None:
    run("""
      const {registerIntentTools}=await import("file://"+process.cwd()+"/src/intent-tools.ts");
      const {Value}=await import("typebox/value");
      const intentOptions={cwd,parentSessionId:"resident-parent",leaderModel:()=>"test/parent",thinking:()=>"low",
        spawn:input=>{spawns.push(input);return {pid:42,readiness:Promise.resolve(ready)}},
        prompt:async(name,message)=>{prompts.push({name,message});return accepted;},
        steer:(name,message)=>{steers.push({name,message});return steerAccepted;},
        terminate:async()=>({outcome:"closed"}),
        workspace:input=>{workspaces.push(input);return {cwd:input.cwd,
          workspacePath:process.env.PI_CODING_AGENT_DIR+"/agents/"+input.agentName+"/workspace",
          sessionDir:process.env.PI_CODING_AGENT_DIR+"/agents/"+input.agentName+"/projects/test/session",reused:false};},
        deliverSessionResult:notice=>notices.push(notice)};
      const tools=[];registerIntentTools({registerTool:tool=>tools.push(tool)},intentOptions);
      const tool=name=>{const found=tools.find(candidate=>candidate.name===name);assert.ok(found,`the intent family registers ${name}`);return found;};
      const ctx={cwd};const run=(name,params)=>tool(name).execute(name,params,undefined,undefined,ctx);
      const start=await run("agent_start",{label:"machine",prompt:"First",tools:[]});final(0,"2");
      const listed=await run("agent_list",{});
      const sent=await run("agent_input",{session:start.details.session,prompt:"Second",delivery:"next"});
      const steered=await run("agent_input",{session:start.details.session,prompt:"Only number",delivery:"steer"});
      final(0,"3");const stopped=await run("agent_stop",{session:start.details.session});
      const failed=await run("agent_input",{session:"session:missing:exact",prompt:"None",delivery:"next"});
      for(const [name,result] of [["agent_start",start],["agent_list",listed],
        ["agent_input",sent],["agent_input",steered],["agent_stop",stopped],["agent_input",failed]]){
        const definition=tool(name);assert.ok(definition.outputSchema,"data-returning tools must declare outputSchema");
        assert.ok(result.structuredContent,"structured data must reach programmatic callers");
        assert.ok(Value.Check(definition.outputSchema,result.structuredContent),JSON.stringify([...Value.Errors(definition.outputSchema,result.structuredContent)]));
        assert.equal(result.structuredContent.ok,result.details.ok);
        assert.equal(result.structuredContent.operation,result.details.operation);
        assert.equal(result.structuredContent.operation,name,"the receipt carries the operation that ran");
        assert.equal(result.structuredContent.disposition,result.details.disposition);
        assert.equal(result.structuredContent.version,1);
      }
      assert.equal(start.structuredContent.nextActor,"runtime");
      assert.equal(start.structuredContent.disposition,"started");
      assert.equal(listed.structuredContent.disposition,"listed");
      assert.equal(sent.structuredContent.disposition,"started");
      assert.equal(steered.structuredContent.disposition,"steered");
      assert.equal(stopped.structuredContent.state,"stopped");
      assert.equal(stopped.structuredContent.disposition,"stopped");
      assert.equal(failed.structuredContent.nextActor,"caller");
      assert.equal(failed.structuredContent.disposition,"rejected");
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_list_pages_and_tool_failure_have_aggregate_byte_budgets(tmp_path: Path) -> None:
    run("""
      for(let i=0;i<75;i++)roster.registerAgent({name:`retained-${i}`,role:"diagnostic",spawnId:`incarnation-${i}`,
        pid:0,status:"stopped",liveText:"证据".repeat(20000),error:"issue".repeat(30000),createdAt:i,updatedAt:i});
      const before=JSON.stringify(roster.listAgents());const seen=[];let offset=0;
      do {
        const page=await call({operation:"list",offset,limit:50});
        assert.equal(page.details.ok,true);assert.ok(Buffer.byteLength(page.content[0].text)<=16*1024);
        assert.ok(page.content[0].text.split("\\n").length<=200);
        assert.ok(Buffer.byteLength(JSON.stringify(page.details))<=32*1024);
        assert.ok(Buffer.byteLength(JSON.stringify(page.structuredContent))<=32*1024);
        for(const entry of page.details.agents){assert.ok(!seen.includes(entry.session));seen.push(entry.session);}
        assert.equal(page.details.count,75);assert.ok(page.details.page);
        offset=page.details.page.nextOffset;
      }while(offset!==undefined);
      assert.equal(seen.length,75);assert.equal(JSON.stringify(roster.listAgents()),before);
      const out=await call({name:"bounded-failure",prompt:"Run",tools:[]},{spawn:()=>({error:"\\u001b[31m"+"证".repeat(100000)})});
      assert.equal(out.isError,true);assert.ok(Buffer.byteLength(out.content[0].text)<=16*1024);
      assert.ok(Buffer.byteLength(JSON.stringify(out.details))<=32*1024);
      assert.ok(out.content[0].text.includes("truncated"));
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)
