"""Use the installed Pi 1.2 renderer, not a string-concatenation surrogate."""
import json
from pathlib import Path

import pytest

from test_agent_package import REPO, SRC, run_node
from test_worker_attempt_lifecycle import attempt_case


@pytest.mark.parametrize("custom", [False, True])
@pytest.mark.parametrize("worker", [False, True])
def test_pi12_renders_owned_guidance_with_default_and_custom_prompt(tmp_path, custom, worker):
    # The root development cohort is the renderer of record: the pinned 1.2
    # package this checkout resolves, not a machine's global Pi install.
    sdk = REPO / "node_modules" / "@earendil-works" / "pi-coding-agent"
    manifest = json.loads((sdk / "package.json").read_text())
    assert manifest["version"].startswith(("1.2.", "1.3.")), manifest["version"]
    script = '''
      const events = new Map();
      register({ on(name, handler) { events.set(name, handler); }, registerTool() {},
        registerCommand() {}, registerMessageRenderer() {}, registerEntryRenderer() {},
        getActiveTools() { return []; }, setActiveTools() {} });
      const options = normalizeBuildSystemPromptOptions({ cwd: process.cwd(), sections: { peer: "Peer section" },
        promptGuidelines: ["Peer guideline"], CUSTOM });
      const returned = await events.get("before_agent_start")({ messageType: "custom", systemPromptOptions: options }, { cwd: process.cwd() });
      const rendered = buildSystemPromptSections(options);
      console.log(JSON.stringify({ returned: returned ?? null, rendered, options }));
    '''.replace("CUSTOM", 'customPrompt: "Authored preamble"' if custom else '')
    imports = f'''
      import register from "{(SRC / 'index.ts').as_uri()}";
      import {{ buildSystemPromptSections, normalizeBuildSystemPromptOptions }} from "{(sdk / 'dist/core/system-prompt.js').as_uri()}";
    '''
    result = attempt_case(tmp_path, imports + script, "none") if worker else run_node(imports + script)
    assert result["returned"] is None
    key = "agent_teams_worker" if worker else "agent_teams_leader"
    assert key in result["rendered"]
    assert "assigned checks" in result["rendered"][key] if worker else "one integration owner" in result["rendered"][key]
    assert result["rendered"]["peer"] == "<peer>\nPeer section\n</peer>"
    assert result["options"]["promptGuidelines"] == ["Peer guideline"]
    if custom:
        assert result["rendered"]["preamble"] == "Authored preamble"
    else:
        assert result["rendered"]["preamble"].startswith("You are an expert coding assistant")
