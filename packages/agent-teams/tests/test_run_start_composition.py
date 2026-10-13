from test_worker_attempt_lifecycle import attempt_case


def test_absent_prompt_does_not_disclose_tasks_or_throw(tmp_path):
    result = attempt_case(tmp_path, '''
      const { default: register } = await import("./src/index.ts");
      const events = new Map();
      let active = ["read", "message", "task"];
      register({ on(name, handler) { events.set(name, handler); }, registerTool() {},
        getActiveTools() { return active; }, setActiveTools(names) { active = names; } });
      const options = { sections: { peer: "Peer section" }, promptGuidelines: ["Peer guideline"] };
      const returned = await events.get("before_agent_start")({ messageType: "custom", systemPromptOptions: options });
      assert.equal(returned, undefined);
      assert.equal(options.sections.peer, "Peer section");
      assert.equal(options.promptGuidelines[0], "Peer guideline");
      assert.deepEqual(options.promptGuidelines, ["Peer guideline"]);
      assert.ok(options.sections.agent_teams_worker.includes("assigned checks"));
      console.log(JSON.stringify({ active }));
    ''', "none")
    assert "task" not in result["active"]
