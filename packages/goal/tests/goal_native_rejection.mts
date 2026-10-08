/** Native SDK preflight rejection: no network or real user project. */
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import type { JsonObject } from "@earendil-works/pi-ai";
import { fauxProvider, fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai/providers/faux";
import { createAgentSessionFromServices, createAgentSessionRuntime, createAgentSessionServices, ModelRuntime, SessionManager } from "@earendil-works/pi-coding-agent";
import { GoalStore } from "../src/store.ts";

const root = mkdtempSync(join(tmpdir(), "goal-native-rejection-"));
const agentDir = join(root, "agent"), cwd = join(root, "project");
mkdirSync(agentDir); mkdirSync(cwd);
const previous = process.env.PI_CODING_AGENT_DIR;
process.env.PI_CODING_AGENT_DIR = agentDir;
const extension = join(root, "fixture.mts");
writeFileSync(extension, `import goal from ${JSON.stringify(resolve("packages/goal/src/index.ts"))};
export default pi => goal(pi, { projectRoot: ${JSON.stringify(cwd)}, runCheck: async () => ({met:false,report:"Not yet."}) });`);
const tool = (name: string, args: JsonObject) => fauxAssistantMessage(fauxToolCall(name, args), { stopReason: "toolUse" });
const provider = fauxProvider({ provider: "goal-native-rejection", models: [{ id: "worker" }] });
provider.setResponses([
  tool("create_goal", { objective: "Old goal" }),
  tool("update_goal", { status: "paused", reason: "Initially paused" }),
  fauxAssistantMessage("Paused"),
  tool("update_goal", { objective: "Unrelated later edit" }),
  tool("update_goal", { status: "paused", reason: "End probe" }),
  fauxAssistantMessage("End"),
]);
const models = await ModelRuntime.create({ modelsPath: null, refreshOnCreate: false });
models.registerNativeProvider(provider.provider);
const runtime = await createAgentSessionRuntime(async ({ cwd, sessionManager, sessionStartEvent }) => {
  const services = await createAgentSessionServices({ cwd, agentDir, modelRuntime: models,
    resourceLoaderOptions: { additionalExtensionPaths: [extension], noSkills: true, noPromptTemplates: true } });
  return { ...await createAgentSessionFromServices({ services, sessionManager, sessionStartEvent, model: provider.getModel("worker") }), services, diagnostics: services.diagnostics };
}, { cwd, agentDir, sessionManager: SessionManager.inMemory(cwd) });
try {
  const session = runtime.session;
  const errors: string[] = [];
  await session.bindExtensions({ mode: "print", onError: (error: {error?: string}) => errors.push(error.error ?? ""),
    uiContext: { ...session.extensionRunner.getUIContext(), notify() {}, setWidget() {} },
    commandContextActions: { waitForIdle: () => session.waitForIdle(), newSession: async () => ({cancelled:true}),
      fork: () => { throw Error("Unused"); }, switchSession: () => { throw Error("Unused"); },
      navigateTree: () => { throw Error("Unused"); }, reload: async () => {} } } as never);
  await session.prompt("Start then pause");
  const store = new GoalStore({ projectRoot: cwd });
  const goal = store.readPool()[0]!;
  assert.equal(goal.status, "paused");
  // The model is cleared to force Pi's preflight to reject the request. The
  // typed state forbids undefined, so the removal is asserted and cast once.
  const model = session.agent.state.model;
  assert.ok(model, "the fixture session must have a model before removing it");
  session.agent.state.model = undefined as unknown as typeof model;
  await session.prompt("/goal Rejected setting request");
  await new Promise(resolve => setTimeout(resolve, 25));
  assert.ok(errors.some(error => /No model selected|reading .api./.test(error)), JSON.stringify(errors));
  session.agent.state.model = model;
  await session.prompt("Only an ordinary internal text edit");
  assert.equal(store.readGoalFromDisk(goal.id)?.status, "paused");
  console.log("GOAL_NATIVE_REJECTION_OK");
} finally {
  runtime.session.dispose();
  if (previous === undefined) delete process.env.PI_CODING_AGENT_DIR;
  else process.env.PI_CODING_AGENT_DIR = previous;
  rmSync(root, { recursive: true, force: true });
}
