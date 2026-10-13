from test_plan_mode import run_typescript


def test_planning_custom_run_does_not_consume_first_user_request(tmp_path, monkeypatch) -> None:
    """Given plan start, When a promptless custom run occurs, Then the user still selects the plan topic."""
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    result = run_typescript('''
      import assert from "node:assert/strict";
      import imported from "./packages/plan-mode/src/index.ts";
      const register = imported.default ?? imported;
      const {buildSystemPrompt} = await import(process.env.PI_PROMPT_BUILDER ?? "./node_modules/@earendil-works/pi-coding-agent/dist/core/system-prompt.js");
      const hooks = new Map(), commands = new Map(), entries = [];
      register({on:(n,h)=>hooks.set(n,h),registerCommand:(n,c)=>commands.set(n,c),appendEntry:(n,data)=>entries.push({n,data})});
      const ctx = {mode:"print",hasUI:false,ui:{notify(){}},model:undefined};
      const options = () => ({cwd:process.cwd(), sections:{other:"retained"}, promptGuidelines:["existing"],customPrompt:"owner"});
      await commands.get("plan").handler("start",ctx);
      const custom = options();
      assert.equal(await hooks.get("before_agent_start")({messageType:"custom",systemPrompt:"owner",systemPromptOptions:custom},ctx),undefined);
      assert.equal(entries.length,0,"custom runs must not allocate a plan topic");
      const user = options();
      assert.equal(await hooks.get("before_agent_start")({messageType:"user",prompt:"inspect widgets",systemPrompt:"owner",systemPromptOptions:user},ctx),undefined);
      assert.ok(buildSystemPrompt(user).startsWith("owner"));
      assert.match(buildSystemPrompt(user),/inspect-widgets/);
      assert.match(buildSystemPrompt({...user,customPrompt:undefined}),/inspect-widgets/);
      assert.equal(user.sections.other,"retained");
      assert.equal(user.customPrompt,"owner");
      assert.equal(user.promptGuidelines[0],"existing");
      assert.deepEqual(user.promptGuidelines,["existing"]);
      assert.match(entries[0].data.path,/inspect-widgets/);
      const resumed = options();
      await hooks.get("before_agent_start")({messageType:"custom",systemPromptOptions:resumed},ctx);
      assert.equal(entries.length,1);
      assert.deepEqual(resumed.promptGuidelines,["existing"]);
      assert.equal(resumed.sections.plan_mode,user.sections.plan_mode);
      await commands.get("plan").handler("exit",ctx);
      const inactive = options();
      await hooks.get("before_agent_start")({messageType:"custom",systemPromptOptions:inactive},ctx);
      assert.deepEqual(inactive.promptGuidelines,["existing"]);
      console.log(JSON.stringify({ok:true}));
    ''')
    assert result["ok"]
