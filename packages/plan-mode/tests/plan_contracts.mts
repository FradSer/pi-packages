import assert from "node:assert/strict";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fauxAssistantMessage, fauxProvider, fauxToolCall } from "@earendil-works/pi-ai/providers/faux";
import { createAgentSessionFromServices, createAgentSessionServices, ModelRuntime, SessionManager, SettingsManager } from "@earendil-works/pi-coding-agent";

const root = mkdtempSync(join(tmpdir(), "plan-contract-"));
const originalAgentDir = process.env.PI_CODING_AGENT_DIR;
let dispose: (() => void) | undefined;
try {
  process.env.PI_CODING_AGENT_DIR = root;
  const scenario = process.argv[2];
  {
    const provider = fauxProvider({ provider: "plan-contract", models: [{ id: "implementation" }, { id: "planner" }] });
    const modelRuntime = await ModelRuntime.create({ modelsPath: null, refreshOnCreate: false });
    modelRuntime.registerNativeProvider(provider.provider);
    if (scenario === "model-restore") {
      writeFileSync(join(root, "plan-mode.json"), JSON.stringify({ provider: "plan-contract", model: "planner" }));
    }
    const extensions = [resolve("packages/plan-mode/index.ts")];
    const collidingNames = ["read", "grep", "find", "ls", "bash", "write", "edit"];
    const sentinel = join(root, "unexpected-tool-execution");
    if (scenario === "guard-collisions") {
      const extension = join(root, "overrides.mjs");
      writeFileSync(extension, `import { writeFileSync } from "node:fs";
export default function (pi) {
  for (const name of ${JSON.stringify(collidingNames)}) pi.registerTool({
    name, label: name, description: "Mutating override of a builtin",
    parameters: {type: "object", properties: {path: {type: "string"}, command: {type: "string"}}},
    async execute() {
      writeFileSync(${JSON.stringify(sentinel)}, name);
      return {content: [{type: "text", text: "unexpected execution"}], details: {}};
    }
  });
}
`);
      extensions.push(extension);
    }
    const services = await createAgentSessionServices({ cwd: root, agentDir: root, modelRuntime,
      settingsManager: SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } }),
      resourceLoaderOptions: { additionalExtensionPaths: extensions, noSkills: true, noPromptTemplates: true } });
    const { session } = await createAgentSessionFromServices({ services, sessionManager: SessionManager.inMemory(root),
      model: provider.getModel("implementation") });
    dispose = () => session.dispose();
    const errors: string[] = [];
    await session.bindExtensions({ mode: "print", onError: (e) => errors.push(e.error) });
    provider.setResponses(Array.from({ length: 30 }, () => fauxAssistantMessage("Continue planning")));
    const toolDecision = (toolName: string, input: Record<string, unknown> = {}) => session.extensionRunner.emitToolCall({
      type: "tool_call", toolCallId: "contract", toolName, input,
    });
    const projectWrite = () => toolDecision("write", { path: join(root, "project.ts"), content: "unwanted" });

    if (scenario === "model-command") {
      await session.prompt("/plan model plan-contract/planner");
      assert.ok(existsSync(join(root, "plan-mode.json")), "model argument must save configuration");
      assert.deepEqual(JSON.parse(readFileSync(join(root, "plan-mode.json"), "utf8")), { provider: "plan-contract", model: "planner" });
      await session.prompt("/plan model missing/model");
      await session.prompt("/plan model invalid");
      assert.equal(session.messages.length, 0, "model commands must never reach the provider");
      assert.ok(!existsSync(join(root, "plans")), "model commands must not allocate a plan");
      assert.equal(session.model?.id, "implementation");
      assert.ok(!(await projectWrite())?.block, "configuration alone must not enter plan mode");
    } else if (scenario === "model-restore") {
      await session.prompt("/plan start");
      assert.equal(session.model?.id, "planner");
      await session.prompt("/plan start");
      await session.prompt("another planning request");
      await session.prompt("/plan exit");
      assert.equal(session.model?.id, "implementation", "re-entry must preserve the original model");
    } else if (scenario === "guard-input") {
      await session.prompt("/plan start");
      for (const text of ["不要执行计划，继续分析风险", "请不要开始执行", "是否应该执行计划？", "Explain how to implement the plan", "Do not implement the plan", 'The text says "exit plan mode"', "implement the plan?"]) {
        await session.prompt(text);
        assert.equal((await projectWrite())?.block, true, `discussion must stay read-only: ${text}`);
      }
      await session.extensionRunner.emitInput("implement the plan", undefined, "extension");
      assert.equal((await projectWrite())?.block, true, "extension input cannot authorize execution");
      for (const text of ["implement the plan", "请执行这个计划。", "exit plan mode"]) {
        await session.prompt(text);
        assert.ok(!(await projectWrite())?.block, `explicit request must release the guard: ${text}`);
        await session.prompt("/plan start");
      }
    } else if (scenario === "guard-collisions") {
      provider.setResponses([
        ...collidingNames.map((name) => () => {
          const entry = session.sessionManager.getBranch().find((e) => e.type === "custom" && e.customType === "plan-mode-path");
          assert.ok(entry?.type === "custom");
          const path = (entry.data as { path: string }).path;
          return fauxAssistantMessage(fauxToolCall(name, { path, command: "git status" }), { stopReason: "toolUse" });
        }),
        fauxAssistantMessage("Overrides checked"),
      ]);
      await session.prompt("/plan start");
      await session.prompt("inspect overrides");
      const results = session.messages.filter((m) => m.role === "toolResult");
      assert.equal(results.length, collidingNames.length);
      assert.ok(results.every((r) => r.isError), "all extension overrides must be blocked");
      assert.ok(!existsSync(sentinel), "extension execute callbacks must never run");
    } else if (scenario === "guard-tools") {
      await session.prompt("/plan start");
      await session.prompt("inspect files");
      for (const tool of ["custom_mutating_tool", "agent", "work"]) {
        assert.equal((await toolDecision(tool))?.block, true, `extension tool must be blocked: ${tool}`);
      }
      for (const tool of ["read", "grep", "find", "ls"]) assert.ok(!(await toolDecision(tool))?.block);
      assert.ok(!(await toolDecision("bash", { command: "git status" }))?.block);
      assert.equal((await toolDecision("bash", { command: "touch project.ts" }))?.block, true);
      const entry = session.sessionManager.getBranch().find((e) => e.type === "custom" && e.customType === "plan-mode-path");
      assert.ok(entry?.type === "custom");
      const planPath = (entry.data as { path: string }).path;
      for (const tool of ["write", "edit"]) {
        assert.ok(!(await toolDecision(tool, { path: planPath }))?.block);
        assert.equal((await toolDecision(tool, { path: join(root, "project.ts") }))?.block, true);
      }
      await session.prompt("/plan exit");
      assert.ok(!(await toolDecision("custom_mutating_tool"))?.block);
    } else {
      assert.fail(`Unknown scenario: ${scenario}`);
    }
    assert.deepEqual(errors, []);
  }
  console.log(JSON.stringify({ scenario, status: "passed" }));
} finally {
  dispose?.();
  if (originalAgentDir === undefined) delete process.env.PI_CODING_AGENT_DIR;
  else process.env.PI_CODING_AGENT_DIR = originalAgentDir;
  rmSync(root, { recursive: true, force: true });
}
