"""Given existing guidelines, additive research guidance preserves prompt ownership."""
import subprocess
from pathlib import Path


def test_research_guidance_preserves_structured_prompt() -> None:
    script = '''
import assert from "node:assert/strict";
import { registerContextGuidance as register } from "./packages/context/extensions/context-command.ts";
const {buildSystemPrompt} = await import(process.env.PI_PROMPT_BUILDER ?? "./node_modules/@earendil-works/pi-coding-agent/dist/core/system-prompt.js");
let hook;
register({on(name, handler) { hook = handler; }});
for (const start of [{prompt:"research", messageType:"user"}, {messageType:"custom"}]) {
  const options = {cwd:process.cwd(), sections:{other:"retained"}, promptGuidelines:["existing"], customPrompt:"owner"};
  const result = await hook({...start, systemPrompt:"forced owner", systemPromptOptions:options});
  const rendered = buildSystemPrompt(options);
  assert.ok(rendered.startsWith("owner"));
  assert.match(rendered, /context_get/);
  assert.match(buildSystemPrompt({...options, customPrompt:undefined}), /context_get/);
  assert.equal(options.sections.other,"retained");
  assert.equal(result, undefined);
  assert.equal(options.promptGuidelines[0], "existing");
  assert.deepEqual(options.promptGuidelines, ["existing"]);
  assert.match(options.sections.context_research, /context_get/);
  assert.equal(options.customPrompt, "owner");
}
await assert.rejects(() => hook({messageType:"custom", systemPromptOptions:{}}), /structured prompt sections/);
'''
    result = subprocess.run(["node", "--import", "tsx", "--input-type=module"], input=script,
                            cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
