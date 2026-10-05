/** Native Pi integration: fake provider observes finalized request transcripts. */
import assert from "node:assert/strict";
import { createAssistantMessageEventStream, type AssistantMessage } from "../../../node_modules/@earendil-works/pi-ai/dist/index.js";
import { createAgentSession, DefaultResourceLoader, ModelRuntime, SessionManager, SettingsManager } from "../../../node_modules/@earendil-works/pi-coding-agent/dist/index.js";
import extension from "../index.ts";
import { registerSubagentToolActivation } from "../src/tool-activation.ts";

const requests: unknown[][] = [];
const selected = process.env.PI_ACTIVATION_EXCLUDED?.split(",").filter(Boolean);
const FAMILY = ["agent_start", "agent_input", "agent_stop", "agent_inspect", "agent_list"];
/** What the selection contract leaves active for one host selection: the family is
 *  all five members or nothing, the retired name is never active, a host tool this
 *  package does not own is untouched, and a whole family waits for the loader on a
 *  transport that can add tools mid-conversation. */
const expectedSelection = () => {
  if (!selected) return ["subagents_enable"];
  const members = selected.filter((name) => FAMILY.includes(name));
  const untouched = selected.filter((name) => !FAMILY.includes(name) && name !== "subagents_enable" && name !== "agent");
  if (members.length !== FAMILY.length) return untouched;
  // A whole family waits for the loader when one is registered; with no loader
  // nothing could ever activate it, so it is served eagerly.
  return selected.includes("subagents_enable") ? [...untouched, "subagents_enable"] : [...untouched, ...FAMILY];
};
const modelRuntime = await ModelRuntime.create({ authPath: process.env.PI_CODING_AGENT_DIR + "/auth.json", modelsPath: process.env.PI_CODING_AGENT_DIR + "/models.json" });
modelRuntime.registerProvider("activation-probe", {
  baseUrl: "https://invalid.example.test", apiKey: "unused-local-fixture", api: "openai-completions",
  models: [{ id: "activation", name: "Activation", api: "openai-completions", reasoning: false, input: ["text"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, contextWindow: 32_000, maxTokens: 128,
    compat: { supportsMidConvoSystemMessages: true, supportsMidConvoToolAdditions: true } }],
  streamSimple(model, context, options) {
    if (selected) {
      const names = (options?.tools ?? []).map(tool => tool.name);
      assert.deepEqual(new Set(names), new Set(expectedSelection()),
        `The provider sees only what the selection contract allows: ${JSON.stringify(selected)}`);
    }
    requests.push(structuredClone(context.messages));
    const callLoader = requests.length === 1;
    const stream = createAssistantMessageEventStream();
    const message: AssistantMessage = {
      role: "assistant", api: model.api, provider: model.provider, model: model.id,
      content: callLoader ? [{ type: "toolCall", id: "enable-1", name: "subagents_enable", arguments: {} }] : [{ type: "text", text: "ACTIVATION_OK" }],
      usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      stopReason: callLoader ? "toolUse" : "stop", timestamp: Date.now(),
    };
    stream.push({ type: "start", partial: message });
    stream.push({ type: "done", reason: message.stopReason, message });
    return stream;
  },
});
const resourceLoader = new DefaultResourceLoader({ cwd: process.cwd(), agentDir: process.env.PI_CODING_AGENT_DIR,
  noExtensions: true, noSkills: true, noPromptTemplates: true, extensionFactories: [extension],
});
await resourceLoader.reload();
const model = modelRuntime.getModel("activation-probe", "activation");
assert.ok(model);
const family = ["agent_start", "agent_input", "agent_stop", "agent_inspect", "agent_list"];
const { session } = await createAgentSession({ cwd: process.cwd(), agentDir: process.env.PI_CODING_AGENT_DIR,
  resourceLoader, modelRuntime, model, settingsManager: SettingsManager.inMemory({ compaction: { enabled: false } }),
  sessionManager: SessionManager.inMemory(), tools: selected
    ?? ["subagents_enable", ...family],
});
try {
  await session.bindExtensions({});
  if (selected) {
    // The family is all five members or nothing, the retired name is never
    // selectable, and an anchored transport keeps a whole family off the wire
    // until the loader runs. So the expected active set follows from the
    // selection rather than repeating it.
    const legacy = selected.filter((name) => name === "agent");
    const members = selected.filter((name) => family.includes(name));
    const complete = members.length === family.length;
    const loaderSelected = selected.includes("subagents_enable");
    // Tools the host selected that this package does not own stay untouched: this
    // package withdraws only its own family and the retired name.
    const expected = expectedSelection();
    assert.deepEqual(new Set(session.getActiveToolNames()), new Set(expected),
      `A partial or unrecorded family stays off the wire: ${JSON.stringify({ selected, expected })}`);
    assert.equal(session.getActiveToolNames().includes("agent"), false, "the retired tool is never selectable");
    const loader = session.getToolDefinition("subagents_enable");
    if (loader && loaderSelected) {
      const enabled = await loader.execute("limited-enable", {}, undefined, undefined, session.createReplacedSessionContext());
      if (complete) {
        assert.notEqual(enabled.isError, true);
        for (const name of family) assert.ok(session.getCallableToolNames().includes(name), `the loader activates ${name}`);
      } else {
        // A host that excluded a member cannot be handed half a family.
        assert.equal(enabled.isError, true, "a partial registration refuses activation");
        assert.deepEqual(new Set(session.getCallableToolNames()), new Set(expected),
          "a refused activation leaves the selection untouched");
      }
    }
    console.log(JSON.stringify({ ok: true, excludedPreserved: true, expected }));
  } else {
  assert.deepEqual(session.getActiveToolNames(), ["subagents_enable"], "native startup applies lazy selection");
  await session.prompt("Delegation is explicitly authorized; enable the agent tool only. Do not start a child.");
  assert.equal(requests.length, 2, JSON.stringify({ active: session.getActiveToolNames(), text: session.getLastAssistantText(), messages: session.messages }));
  assert.deepEqual(requests[1].slice(0, requests[0].length), requests[0], "activation preserves every previously sent transcript message");
  assert.ok(session.getActiveToolNames().includes("agent_start"));
  assert.ok(!session.getActiveToolNames().includes("agent"));
  const manager = session.sessionManager;
  const messages = manager.buildSessionContext().messages;
  const system = messages.filter(message => message.role === "system");
  assert.ok(system[0].toolsAdded.some(tool => tool.name === "subagents_enable"), "native initial tool record supplies the restore baseline");
  assert.ok(system.slice(1).some(message => message.toolsAdded?.some(tool => tool.name === "agent_start")), "later activation is an anchored delta");
  let restored: string[] = [];
  const handlers = new Map();
  registerSubagentToolActivation({ registerTool() {}, on: (name, handler) => handlers.set(name, handler),
    getAllTools: () => ["agent", "subagents_enable", "agent_start", "agent_input", "agent_stop", "agent_inspect", "agent_list"].map(name=>({name})), getActiveTools: () => restored,
    setActiveTools: names => {restored=names;} } as never);
  handlers.get("session_start")({}, {sessionManager:manager,model});
  assert.deepEqual(new Set(restored), new Set(["agent_start","agent_input","agent_stop","agent_inspect","agent_list","subagents_enable"]), "native restore retains unchanged loader and newly added agent");
  assert.equal(session.getLastAssistantText(), "ACTIVATION_OK");
  console.log(JSON.stringify({ ok: true, requests: requests.length, prefixPreserved: true, noChild: true }));
  }
} finally { session.dispose(); }
