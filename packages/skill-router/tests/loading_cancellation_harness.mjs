import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { showSkillRouterMenu } from "../src/menu.ts";

const [mode, root] = process.argv.slice(2);
const upstream = join(root, "upstream");
const agent = join(root, "agent");
mkdirSync(join(upstream, "review"), { recursive: true });
writeFileSync(join(upstream, "review", "SKILL.md"), "---\nname: review\ndescription: Review project changes before shipping.\n---\nReview the changes.\n");
for (const args of [["init", "-q"], ["add", "."], ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"]]) {
  execFileSync("git", args, { cwd: upstream, stdio: "pipe" });
}
process.env.PI_CODING_AGENT_DIR = agent;

const controller = new AbortController();
let overlay;
let opened = false;
let inputCount = 0;
let doneCalls = 0;
let modelCalls = 0;
let releaseOperation;
let markPending;
const pending = new Promise((resolve) => { markPending = resolve; });
const operation = new Promise((resolve) => { releaseOperation = resolve; });
const auth = { ok: true, apiKey: "fixture", headers: {} };
const notifications = [];
const menu = showSkillRouterMenu({
  hasUI: true,
  signal: controller.signal,
  model: { provider: "test", id: "test" },
  modelRegistry: {
    async getApiKeyAndHeaders() {
      if (mode.endsWith("auth")) { markPending(); await operation; }
      return auth;
    },
    async complete() {
      modelCalls += 1;
      markPending();
      await operation;
      return { stopReason: "stop", content: [{ type: "text", text: "late result" }] };
    },
  },
  ui: {
    select: async () => opened ? undefined : (opened = true, "Add collection"),
    input: async () => inputCount++ === 0 ? upstream : "review-collection",
    confirm: async () => true,
    notify: (message, level) => { notifications.push({ message, level }); },
    custom: (factory) => new Promise((resolve) => {
      const component = factory(
        { requestRender() {} },
        { fg: (_color, text) => text, bold: (text) => text },
        {},
        (result) => { doneCalls += 1; component.dispose(); resolve(result); },
      );
      overlay = component;
    }),
  },
});

await pending;
if (mode.startsWith("escape")) overlay.handleInput("\x1b");
else controller.abort();
try {
  const settled = await Promise.race([menu.then(() => true), delay(300).then(() => false)]);
  assert.equal(settled, true, "cancelled overlay waited for a pending external operation");
  assert.deepEqual(notifications, [{ message: "Cancelled", level: "info" }]);
  assert.equal(doneCalls, 2);
  assert.equal(existsSync(join(agent, "skill-router", "collections.json")), false);
} finally {
  releaseOperation();
  await menu;
}
await delay(10);
assert.equal(doneCalls, 2, "late result completed the overlay twice");
assert.equal(modelCalls, mode.endsWith("auth") ? 0 : 1);
assert.equal(existsSync(join(agent, "skill-router", "collections.json")), false);
console.log("ok");
