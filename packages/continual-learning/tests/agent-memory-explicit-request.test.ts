/** An explicit Memory or Harness request routes through the one learn tool. */
import { expect, test } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

interface FakePi {
  on(name: string, handler: (...args: any[]) => any): void;
  registerCommand(): void;
  registerTool(tool: unknown): void;
  registerEntryRenderer(): void;
  registerMessageRenderer?(): void;
  sendMessage(): void;
  appendEntry(): void;
  getCommands(): unknown[];
  getActiveTools(): string[];
  setActiveTools(names: string[]): void;
  exec(): Promise<{ stdout: string; stderr: string; code: number }>;
}

async function setup(config: Record<string, unknown>): Promise<{
  hooks: Map<string, (...args: any[]) => any>;
  activeTools: string[];
  cwd: string;
  root: string;
}> {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cl-explicit-"));
  const cwd = path.join(root, "project");
  fs.mkdirSync(cwd, { recursive: true });
  fs.mkdirSync(path.join(root, "agent", "memory"), { recursive: true });
  fs.writeFileSync(path.join(root, "agent", "continual-learning.json"), JSON.stringify(config));
  process.env.PI_CODING_AGENT_DIR = path.join(root, "agent");

  const hooks = new Map<string, (...args: any[]) => any>();
  const activeTools = ["read", "bash", "edit", "write"];
  const pi: FakePi = {
    on: (name, handler) => { hooks.set(name, handler); },
    registerCommand() {},
    registerTool() {},
    registerEntryRenderer() {},
    registerMessageRenderer() {},
    sendMessage() {},
    appendEntry() {},
    getCommands: () => [],
    getActiveTools: () => [...activeTools],
    setActiveTools: (names) => { activeTools.splice(0, activeTools.length, ...names); },
    exec: async () => ({ stdout: "", stderr: "", code: 0 }),
  };
  const { default: register } = await import("../extensions/inject-memory.ts");
  register(pi as never);
  return { hooks, activeTools, cwd, root };
}

function ctx(cwd: string): Record<string, unknown> {
  return {
    cwd,
    hasUI: false,
    ui: { notify() {} },
    sessionManager: {
      getSessionId: () => "session", getLeafId: () => "leaf",
      getBranch: () => [], buildContextEntries: () => [],
    },
    model: { provider: "fixture", id: "model" },
    modelRegistry: { getAll: () => [], getAvailable: () => [] },
  };
}

test("an explicit organize-Memory request requires the agent tool before answering", async () => {
  const { hooks, cwd } = await setup({ autoSettledLearning: true, autoContinualLearning: true });
  const options = { sections: {} as Record<string, string>, promptGuidelines: [] as string[], skills: [] };
  await hooks.get("input")?.({ source: "interactive", text: "整理记忆" }, ctx(cwd));
  await hooks.get("before_agent_start")?.(
    { prompt: "整理记忆", systemPrompt: "", systemPromptOptions: options }, ctx(cwd));
  const guidance = options.sections.project_memory_auto_learning ?? "";
  const protocol = options.sections.project_memory_protocol ?? "";
  expect(guidance).toContain("`learn`");
  expect(guidance).toContain("整理记忆");
  expect(guidance).toMatch(/even when|regardless/);
  expect(guidance).toContain("以后禁止 npm");
  expect(guidance).toContain("纠正旧规则");
  expect(guidance).not.toContain("learn_current_memory");
  expect(guidance).toContain("Do not\nanswer such a request by telling the user to type");
  expect(protocol).not.toContain("The user can request maintenance with /memory or /consolidate");
  expect(protocol).toContain("learn tool");
});

test("the agent tool is active synchronously when the prompt is built", async () => {
  const { hooks, activeTools, cwd } = await setup({ autoSettledLearning: true, autoContinualLearning: true });
  const options = { sections: {} as Record<string, string>, promptGuidelines: [] as string[], skills: [] };
  await hooks.get("before_agent_start")?.(
    { prompt: "整理记忆", systemPrompt: "", systemPromptOptions: options }, ctx(cwd));
  expect(activeTools).toContain("learn");
});

test("a disabled agent trigger does not advertise the tool", async () => {
  const { hooks, activeTools, cwd } = await setup({ autoSettledLearning: false, autoContinualLearning: false });
  const options = { sections: {} as Record<string, string>, promptGuidelines: [] as string[], skills: [] };
  await hooks.get("before_agent_start")?.(
    { prompt: "整理记忆", systemPrompt: "", systemPromptOptions: options }, ctx(cwd));
  expect(activeTools).not.toContain("learn");
});
