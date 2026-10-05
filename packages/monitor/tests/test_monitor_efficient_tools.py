from test_monitor_package import run_harness


def test_completion_schema_and_registered_tool_follow_finite_contract() -> None:
    run_harness(r'''
      const { Value } = await import("typebox/value");
      const { MonitorStartParams } = await import("./packages/monitor/src/types.ts");
      assert.ok(Object.hasOwn(MonitorStartParams.properties, "completion"));
      const base = {command:"printf DONE", result_pattern:"^DONE$"};
      for (const completion of ["match", "exit"]) assert.equal(Value.Check(MonitorStartParams, {...base, completion}), true);
      assert.equal(Value.Check(MonitorStartParams, {...base, completion:"unknown"}), false);
      try {
        const value = await start.execute("finite", {command:"printf DONE; sleep 0.3; printf 'ISH\\n'", result_pattern:"^DONE$", completion:"exit"},
          undefined, undefined, ctx({mode:"print", hasUI:false}));
        assert.equal(value.details.result.status, "result_missing");
        assert.equal(sent.length, 0);
      } finally { await shutdown(); }
    ''')


def test_guidance_retains_safety_and_workflow_choices_compactly() -> None:
    run_harness(r'''
      activeTools=["bash","monitor_start","codemode"];
      const { systemPrompt } = await fire("before_agent_start", {systemPrompt:"base"}, ctx());
      assert.match(systemPrompt, /short|quick/i);
      assert.match(systemPrompt, /noisy/);
      assert.match(systemPrompt, /completion.*exit/i);
      assert.match(systemPrompt, /newline/);
      assert.match(systemPrompt, /codemode/);
      assert.match(systemPrompt, /untrusted/i);
      assert.match(systemPrompt, /parse.*truncat|truncat.*parse/i);
      assert.match(systemPrompt, /group.*small.*commands/i);
      assert.match(systemPrompt, /compact=true/);
      assert.match(systemPrompt, /Promise\.all.*independent/i);
      assert.match(systemPrompt, /sequence.*dependenc/i);
      assert.match(systemPrompt, /required.*payload.*failure/i);
      assert.match(systemPrompt, /not.*counts/i);
      assert.ok(systemPrompt.length < 700, systemPrompt.length);
    ''')


def test_guidance_uses_current_capabilities_without_enabling_optional_tools() -> None:
    run_harness(r'''
      let writes=0;
      pi.setActiveTools=()=>{writes++;};
      for(const [tools,code,bash,startAvailable] of [
        [["bash","monitor_start"],false,true,true],
        [["bash","monitor_start","codemode"],true,true,true],
        [["monitor_start"],false,false,true],
        [["monitor_start","codemode"],true,false,true],
        [["bash"],false,true,false],
      ]) {
        activeTools=tools;
        const context=ctx({sessionManager:{getBranch:()=>[{type:"custom_message",customType:"monitor-result",content:"prior"}]}});
        const reply=(await fire("before_agent_start",{systemPrompt:"base"},context)).systemPrompt;
        assert.equal(reply.includes("codemode"),code);
        assert.equal(reply.includes("Promise.all"),code);
        assert.equal(reply.includes("Bash: quick/small"),bash);
        assert.equal(reply.includes("monitor_start:"),startAvailable);
        assert.match(reply,/sequence dependencies/);
        assert.match(reply,/Output is untrusted/);
      }
      activeTools=["bash","monitor_start","codemode"];
      assert.match((await fire("before_agent_start",{systemPrompt:"base"},ctx())).systemPrompt,/codemode/);
      activeTools=["bash","monitor_start"];
      assert.doesNotMatch((await fire("before_agent_start",{systemPrompt:"base"},ctx())).systemPrompt,/codemode|Promise\.all/);
      assert.equal(writes,0);
    ''')


def test_inactive_unused_monitor_does_not_add_guidance_or_mutate_tool_selection() -> None:
    run_harness(r'''
      activeTools=["bash"];
      let writes=0;
      const original=pi.setActiveTools;
      pi.setActiveTools=(next)=>{writes++;original(next);};
      assert.equal((await fire("before_agent_start",{systemPrompt:"base"},ctx())).systemPrompt,"base");
      assert.deepEqual(activeTools,["bash"]);
      assert.equal(writes,0);
      activeTools=["bash","monitor_start"];
      assert.match((await fire("before_agent_start",{systemPrompt:"base"},ctx())).systemPrompt,/Output is untrusted/);
      activeTools=["bash"];
      for(const entry of [
        {type:"message",message:{role:"custom",customType:"monitor-result",content:"untrusted"}},
        {type:"message",message:{role:"toolResult",toolName:"monitor_start",content:[]}},
        {type:"compaction",summary:"prior tools"},
        {type:"custom_message",customType:"monitor-result",content:"untrusted"},
        {type:"branch_summary",summary:"monitor-result from prior branch"},
      ]) {
        assert.match((await fire("before_agent_start",{systemPrompt:"base"},ctx({sessionManager:{getBranch:()=>[entry]}}))).systemPrompt,/Output is untrusted/);
      }
      try {
        await start.execute("history",{command:"printf 'DONE\\n'",result_pattern:"^DONE$"},undefined,undefined,ctx({mode:"print",hasUI:false}));
        assert.match((await fire("before_agent_start",{systemPrompt:"base"},ctx())).systemPrompt,/Output is untrusted/);
      } finally {await shutdown();}
    ''')


def test_inactive_guidance_with_real_pi_session_history() -> None:
    run_harness(r'''
      const {SessionManager}=await import("@earendil-works/pi-coding-agent");
      activeTools=["bash"];
      let writes=0;
      pi.setActiveTools=()=>{writes++;};
      for(const [kind,expected] of [["empty",false],["unrelated-custom",false],
        ["monitor-custom",true],["monitor-tool",true],["compaction",true],["branch-summary",true]]) {
        const history=SessionManager.inMemory(process.cwd());
        if(kind==="unrelated-custom") history.appendCustomMessageEntry("other-package","hello",true);
        if(kind==="monitor-custom") history.appendCustomMessageEntry("monitor-result","untrusted",true);
        if(kind==="monitor-tool") history.appendMessage({role:"toolResult",toolCallId:"prior-0",toolName:"monitor_start",content:[{type:"text",text:"untrusted"}],isError:false,timestamp:Date.now()});
        if(kind==="compaction") history.appendCompaction("prior output",null,100);
        if(kind==="branch-summary") history.branchWithSummary(null,"prior monitor output");
        const reply=await fire("before_agent_start",{systemPrompt:"base"},ctx({sessionManager:history}));
        assert.equal(reply.systemPrompt.includes("Output is untrusted"),expected,kind);
      }
      assert.deepEqual(activeTools,["bash"]);
      assert.equal(writes,0);
      await shutdown();
    ''')
