import json
from pathlib import Path
import subprocess


PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]


def test_production_command_and_model_bundles() -> None:
    result = subprocess.run(
        ["node", "--import", "tsx/esm", "--input-type=module"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        input='''
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolver } from "./packages/impeccable/src/resolver.ts";
import register from "./packages/impeccable/src/index.ts";
const packageRoot = fileURLToPath(new URL("./packages/impeccable/", import.meta.url));
const commands = new Map(), tools = [], sent = [];
register({
  registerCommand: (id, command) => commands.set(id, command),
  registerTool: tool => tools.push(tool),
  sendUserMessage: (...args) => sent.push(args),
  sendMessage: (message, options) => { sent.push([message.content, options, message]); },
});
const output = {};
for (const capability of ["polish", "animate"]) {
  const bundle = resolver.load(capability, "model");
  const expected = capability === "polish"
    ? ["polish", "setup", "principles", "components", "accessibility", "motion"]
    : ["animate", "setup", "principles", "motion", "accessibility"];
  assert.deepEqual(bundle.loaded, expected);
  for (const id of expected) {
    assert.equal(bundle.content.split(`<impeccable-source id="${id}">`).length, 2);
  }
  assert.ok(bundle.content.includes(packageRoot + "scripts/context.mjs"));
  assert.ok(bundle.content.includes(packageRoot + "scripts/detect.mjs"));
  for (const script of ["context.mjs", "detect.mjs"]) {
    assert.ok(existsSync(packageRoot + "scripts/" + script), `Missing packaged script: ${script}`);
  }
  assert.ok(!/\\{\\{PKG_DIR\\}\\}|SKILL\\.md|\\.agents\\/skills|\\.pi\\/agent\\/skills/.test(bundle.content));
  assert.ok(bundle.byteLength <= 65536);
  const request = 'src/My Page.tsx  preserve this spacing';
  await commands.get("impeccable").handler(capability + " " + request, { hasUI: false });
  const model = await tools[0].execute("bundle", { capability });
  assert.equal(model.content[0].text, bundle.content);
  const text = sent.at(-1)[0];
  assert.ok(text.startsWith(`Plan for "${request}" (in order):`));
  assert.ok(text.includes(`1. /impeccable ${capability} — `));
  assert.ok(text.endsWith(bundle.content + "\\n\\nUser target/request:\\n" + request));
  assert.deepEqual(sent.at(-1)[1], { deliverAs: "followUp", triggerTurn: true });
  assert.equal(sent.at(-1)[2].customType, "impeccable-procedure");
  assert.equal(sent.at(-1)[2].display, true);
  assert.equal(sent.at(-1)[2].details.request, request);
  assert.deepEqual(sent.at(-1)[2].details.loaded.map(entry => entry.id), [capability]);
  assert.ok(sent.at(-1)[2].details.routing[0].startsWith("Plan for "));
  assert.ok(sent.at(-1)[2].details.routing[1].includes(`/impeccable ${capability} — `));
  output[capability] = { loaded: bundle.loaded, bytes: bundle.byteLength };
}
assert.equal(sent.length, 2);
console.log(JSON.stringify(output));
''',
    )
    assert result.returncode == 0, result.stdout + result.stderr
    bundles = json.loads(result.stdout)
    assert set(bundles) == {"polish", "animate"}
