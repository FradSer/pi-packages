from matt_pocock_helpers import RUNTIME_HARNESS, run_typescript


def test_workflow_guidance_appends_without_prompt_override() -> None:
    """Given either run type, When guidance is added, Then owner text stays intact."""
    result = run_typescript(RUNTIME_HARNESS + '''
      const {buildSystemPrompt} = await import(process.env.PI_PROMPT_BUILDER ?? "./node_modules/@earendil-works/pi-coding-agent/dist/core/system-prompt.js");
      const r = runtime();
      const observations = [];
      for (const active of [false, true]) {
        if (active) await r.start();
        for (const start of [{messageType:"user",prompt:"hello"},{messageType:"custom"}]) {
          const options = {cwd:process.cwd(), sections:{other:"retained"}, promptGuidelines:["existing"],customPrompt:"owner"};
          const reply = await r.events.get("before_agent_start")({...start,systemPrompt:"owner",systemPromptOptions:options},r.ctx);
          observations.push({reply:reply ?? null,options,active,rendered:buildSystemPrompt(options),defaultRendered:buildSystemPrompt({...options,customPrompt:undefined})});
        }
      }
      console.log(JSON.stringify({observations}));
    ''')
    for row in result["observations"]:
        assert "Matt Pocock" in row["rendered"]
        assert "Matt Pocock" in row["defaultRendered"]
        assert row["rendered"].startswith("owner")
        assert row["reply"] is None
        assert row["options"]["customPrompt"] == "owner"
        guidelines = row["options"]["promptGuidelines"]
        assert guidelines[0] == "existing"
        assert guidelines == ["existing"]
        assert row["options"]["sections"]["other"] == "retained"
        assert ("workflow active:" in row["options"]["sections"]["matt_pocock_workflow"]) == row["active"]
