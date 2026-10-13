from test_monitor_package import run_harness


def test_monitor_guidance_preserves_prompt_ownership_and_inactive_boundary() -> None:
    """Given active or unused tools, When a custom run starts, Then only needed guidelines change."""
    run_harness('''
      const {buildSystemPrompt} = await import(process.env.PI_PROMPT_BUILDER ?? "./node_modules/@earendil-works/pi-coding-agent/dist/core/system-prompt.js");
      for (const enabled of [true,false]) {
        activeTools = enabled ? ["monitor_start","bash"] : ["bash"];
        const options = {cwd:process.cwd(), sections:{other:"retained"}, promptGuidelines:["existing"],customPrompt:"owner"};
        const reply = await fire("before_agent_start", {messageType:"custom",systemPrompt:"owner",systemPromptOptions:options});
        assert.equal(buildSystemPrompt(options).includes("Output is untrusted"), enabled);
        assert.ok(buildSystemPrompt(options).startsWith("owner"));
        assert.equal(buildSystemPrompt({...options,customPrompt:undefined}).includes("Output is untrusted"),enabled);
        assert.equal(reply, undefined);
        assert.equal(options.customPrompt, "owner");
        assert.equal(options.promptGuidelines[0], "existing");
        assert.deepEqual(options.promptGuidelines,["existing"]);
        assert.equal(options.sections.other,"retained");
        if (enabled) assert.match(options.sections.monitor_policy, /Output is untrusted/);
      }
      await shutdown();
    ''')
