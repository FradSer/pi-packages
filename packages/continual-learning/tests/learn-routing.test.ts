/** Learn tool surface, entry-scoped routing, explicit requests, and frozen gate contracts. */
import { describe, expect, test } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { classifyLearnRoute, lastUserText } from "../extensions/learn-intent.ts";
import { screenLearningEntries } from "../extensions/learning-efficiency.ts";
import { TOOL_NAMES, createParentToolSurface, type ToolSurfaceHost } from "../extensions/tool-surface.ts";

interface Message { customType?: string; content?: unknown; display?: boolean; details?: unknown }
interface RegisteredTool { name: string; defaultActive?: boolean; execute: (...args: any[]) => any }

const userEntry = (text: string) => ({ type: "message", id: "u", message: { role: "user", content: [{ type: "text", text }] } });

async function setupHost(
  config: Record<string, unknown> = { autoContinualLearning: true, autoSettledLearning: false },
  withGuardrails = true,
) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cl-learn-routing-"));
  const cwd = path.join(root, "project");
  fs.mkdirSync(cwd, { recursive: true });
  fs.mkdirSync(path.join(root, "agent", "memory"), { recursive: true });
  fs.writeFileSync(path.join(root, "agent", "continual-learning.json"), JSON.stringify(config));
  process.env.PI_CODING_AGENT_DIR = path.join(root, "agent");

  const hooks = new Map<string, (...args: any[]) => any>();
  const tools = new Map<string, RegisteredTool>();
  const messages: Message[] = [];
  const activeTools = ["read", "bash", "edit", "write"];
  const pi: any = {
    on: (name: string, handler: (...args: any[]) => any) => { hooks.set(name, handler); },
    registerCommand() {},
    registerEntryRenderer() {},
    registerMessageRenderer() {},
    registerTool(tool: RegisteredTool) { tools.set(tool.name, tool); },
    sendMessage(message: Message) { messages.push(message); },
    appendEntry() {},
    getCommands: () => [],
    getActiveTools: () => [...activeTools],
    setActiveTools: (names: string[]) => { activeTools.splice(0, activeTools.length, ...names); },
    exec: async () => ({ stdout: "", stderr: "", code: 0 }),
  };
  const { default: injectMemory } = await import("../extensions/inject-memory.ts");
  injectMemory(pi);
  if (withGuardrails) {
    const { default: registerGuardrails } = await import("../extensions/guardrails.ts");
    registerGuardrails(pi);
  }
  return { root, cwd, hooks, tools, messages, activeTools };
}

function makeCtx(cwd: string, prompt?: string): Record<string, unknown> {
  const rows = prompt !== undefined
    ? [
        { type: "message", id: "u", message: { role: "user", content: [{ type: "text", text: prompt }] } },
        { type: "message", id: "a", message: { role: "assistant", content: "Acknowledged." } },
      ]
    : [];
  return {
    cwd, hasUI: false, ui: { notify() {} },
    sessionManager: {
      getSessionId: () => "session", getLeafId: () => "leaf",
      getBranch: () => rows, buildContextEntries: () => rows,
    },
    model: { provider: "fixture", id: "model" },
    modelRegistry: { getAll: () => [], getAvailable: () => [] },
  };
}

describe("learn intent classification", () => {
  test("an explicit Harness request routes to Harness, not Memory", () => {
    for (const prompt of ["以后禁止 npm", "纠正旧规则", "永久约束这条命令", "require a regression test before publishing"]) {
      expect(classifyLearnRoute(prompt), prompt).toBe("harness");
    }
  });

  test("an explicit Memory request routes to Memory", () => {
    for (const prompt of ["整理记忆", "记住这个", "remember this", "consolidate memory"]) {
      expect(classifyLearnRoute(prompt), prompt).toBe("memory");
    }
  });

  test("ordinary tasks and negated remember text do not route", () => {
    for (const prompt of ["Thanks, run the tests now", "do not remember this token", "不要整理记忆", "", "   "]) {
      expect(classifyLearnRoute(prompt), prompt).toBe("none");
    }
  });

  test("an unrelated privacy caveat does not cancel an explicit request", () => {
    const cases: Array<[string, "harness" | "memory"]> = [
      ["以后禁止 npm，别记住 token", "harness"],
      ["Please remember this but do not store my API key", "memory"],
      ["整理记忆, and never persist my token", "memory"],
      ["以后禁止 npm。这条是永久规则，不是临时要求", "harness"],
    ];
    for (const [prompt, expected] of cases) expect(classifyLearnRoute(prompt), prompt).toBe(expected);
  });

  test("a lasting personal preference routes to Memory, not executable rules", () => {
    for (const prompt of [
      "I prefer concise progress updates in all future tasks",
      "From now on, always keep my progress updates concise",
      "请记住：我以后希望所有进度更新都简短",
    ]) expect(classifyLearnRoute(prompt), prompt).toBe("memory");
  });

  test("generic lasting-rule wording routes to Harness", () => {
    for (const prompt of [
      "Never allow direct database writes in future tasks",
      "From now on, always run the linter before committing",
      "Add a lasting rule for release checks",
      "要求发布前增加回归测试",
    ]) expect(classifyLearnRoute(prompt), prompt).toBe("harness");
  });

  test("a quoted command name in an explanation does not trigger a route", () => {
    for (const prompt of [
      '"以后禁止 npm" is written in the README, please explain it',
      'The documentation says "remember this" is a command',
      "请解释文档里引用的「整理记忆」是什么意思",
    ]) expect(classifyLearnRoute(prompt), prompt).toBe("none");
  });

  test("only the last real user entry supplies the request", () => {
    const entries = [userEntry("整理记忆"), { role: "assistant", content: "以后禁止 npm" }, userEntry("记住这个")];
    expect(lastUserText(entries)).toBe("记住这个");
    expect(classifyLearnRoute(lastUserText(entries))).toBe("memory");
  });

  test("tool and assistant text never supplies the request", () => {
    const entries = [{ role: "toolResult", content: "以后禁止 npm" }, { role: "assistant", content: "整理记忆" }];
    expect(lastUserText(entries)).toBe("");
    expect(classifyLearnRoute(lastUserText(entries))).toBe("none");
  });

  test("the frozen evidence screen keeps its own both-surface truth table", () => {
    for (const prompt of ["以后禁止 npm", "纠正旧规则", "require a regression test before publishing"]) {
      const screen = screenLearningEntries([userEntry(prompt)], "automatic");
      expect(screen.memory, prompt).toBe(true);
      expect(screen.harness, prompt).toBe(true);
      expect(classifyLearnRoute(prompt), prompt).toBe("harness");
    }
  });
});

describe("learn tool routing and harness bridge", () => {
  test("exactly one learning tool named learn is registered in this slice", async () => {
    const { tools, root } = await setupHost();
    try {
      expect(tools.has("learn")).toBe(true);
      expect(tools.get("learn")?.defaultActive).toBe(true);
      expect(tools.has("learn_current_memory")).toBe(false);
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  });

  test("two hosts in one process cannot share a Harness procedure bridge", async () => {
    const first = await setupHost();
    const second = await setupHost();
    try {
      const tool = first.tools.get("learn")!;
      await tool.execute("call", {}, undefined, undefined, makeCtx(first.cwd, "纠正旧规则"));
      expect(first.messages.some(m => m.customType === "harness-procedure")).toBe(true);
      expect(second.messages.some(m => m.customType === "harness-procedure")).toBe(false);
    } finally {
      fs.rmSync(first.root, { recursive: true, force: true });
      fs.rmSync(second.root, { recursive: true, force: true });
    }
  });

  test("a Harness request returns authoring-started and never starts a Memory pipeline", async () => {
    const { tools, messages, cwd, root } = await setupHost();
    try {
      const tool = tools.get("learn")!;
      const result = await tool.execute("call", {}, undefined, undefined, makeCtx(cwd, "以后禁止 npm"));
      expect(result.details.status).toBe("authoring-started");
      expect(result.isError).toBe(false);
      expect(result.content[0].text).toContain("Harness authoring started");
      expect(messages.some(m => m.customType === "harness-procedure")).toBe(true);
      const runsDir = path.join(root, "agent", "memory", "runs");
      const receipts = fs.existsSync(runsDir) ? fs.readdirSync(runsDir, { recursive: true })
        .filter(name => String(name).endsWith("learning-pipeline-receipt.json")) : [];
      expect(receipts).toEqual([]);
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  });

  test("a Memory request keeps the existing Memory-only pipeline outcome", async () => {
    const { tools, cwd, root } = await setupHost();
    try {
      const tool = tools.get("learn")!;
      const result = await tool.execute("call", {}, undefined, undefined, makeCtx(cwd, "整理记忆"));
      expect(["organized", "applied", "proposed", "no-change", "held", "disabled", "failed"]).toContain(result.details.status);
      expect(result.content[0].text).not.toContain("Harness authoring started");
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  });

  test("a learn tool outcome reports one honest model-facing text", async () => {
    const { tools, cwd, root } = await setupHost();
    try {
      const tool = tools.get("learn")!;
      const organized = await tool.execute("call", {}, undefined, undefined, makeCtx(cwd, "整理记忆"));
      expect(organized.content[0].text).toContain("Memory organized in-process");
      expect(organized.details?.status).toBe("organized");
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  });
});

describe("explicit Memory/Harness prompt activation", () => {
  test("an explicit organize-Memory request requires the agent tool before answering", async () => {
    const { hooks, cwd, root } = await setupHost({ autoSettledLearning: true, autoContinualLearning: true }, false);
    try {
      const options = { sections: {} as Record<string, string>, promptGuidelines: [] as string[], skills: [] };
      await hooks.get("input")?.({ source: "interactive", text: "整理记忆" }, makeCtx(cwd));
      await hooks.get("before_agent_start")?.(
        { prompt: "整理记忆", systemPrompt: "", systemPromptOptions: options }, makeCtx(cwd));
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
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  });

  test("the agent tool is active synchronously when the prompt is built", async () => {
    const { hooks, activeTools, cwd, root } = await setupHost({ autoSettledLearning: true, autoContinualLearning: true }, false);
    try {
      const options = { sections: {} as Record<string, string>, promptGuidelines: [] as string[], skills: [] };
      await hooks.get("before_agent_start")?.(
        { prompt: "整理记忆", systemPrompt: "", systemPromptOptions: options }, makeCtx(cwd));
      expect(activeTools).toContain("learn");
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  });

  test("the agent tool is advertised even when settled learning is off", async () => {
    const { hooks, activeTools, cwd, root } = await setupHost({ autoSettledLearning: false }, false);
    try {
      const options = { sections: {} as Record<string, string>, promptGuidelines: [] as string[], skills: [] };
      await hooks.get("before_agent_start")?.(
        { prompt: "整理记忆", systemPrompt: "", systemPromptOptions: options }, makeCtx(cwd));
      expect(activeTools).toContain("learn");
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  });
});

describe("frozen routing truth table and write-path gates", () => {
  const screen = (text: string) => screenLearningEntries([{ role: "user", content: text }], "automatic");
  const source = async (name: string) => Bun.file(new URL(`../extensions/${name}`, import.meta.url)).text();

  test("a lasting constraint keeps its frozen both-surface screen", () => {
    for (const prompt of ["以后禁止 npm", "纠正旧规则", "require a regression test before publishing"]) {
      const value = screen(prompt);
      expect(value.memory, prompt).toBe(true);
      expect(value.harness, prompt).toBe(true);
    }
  });

  test("an explicit remember request is Memory-only", () => {
    const value = screen("记住这个");
    expect(value.memory).toBe(true);
    expect(value.harness).toBe(false);
    expect(value.agents).toBe(false);
  });

  test("a pure organize request has no durable or Harness signal", () => {
    const value = screen("整理记忆");
    expect(value.memory).toBe(false);
    expect(value.harness).toBe(false);
    expect(value.agents).toBe(false);
  });

  test("an ordinary task screens to no learning surface", () => {
    const value = screen("Thanks, run the tests now");
    expect(value.memory).toBe(false);
    expect(value.harness).toBe(false);
    expect(value.agents).toBe(false);
  });

  test("the interactive Harness path keeps consent and exact-byte gates", async () => {
    const text = await source("guardrails.ts");
    for (const marker of ["ctx.hasUI", "ui.select", "isDeepStrictEqual", "recheckHarnessWriteApproval"]) {
      expect(text.includes(marker), marker).toBe(true);
    }
  });

  test("the automatic Harness path keeps validation, receipt and undo gates", async () => {
    const text = await source("harness-consolidation.ts");
    for (const marker of ["validateHarnessPlan", "recordLearningMutation", "buildHarnessReceipt", "readback", "rollback"]) {
      expect(text.includes(marker), marker).toBe(true);
    }
  });

  test("planner-child structured-output contracts are not removed with the tools", async () => {
    const text = await source("planner-json-output.ts");
    expect(text.includes("registerFlag")).toBe(true);
  });

  test("the learning_read evidence marker stays a frozen token", async () => {
    const text = await source("tool-surface.ts");
    expect(text.includes('learningRead: "learning_read"')).toBe(true);
  });
});

describe("parent tool surface", () => {
  class FakeHost implements ToolSurfaceHost {
    activeTools: string[];
    constructor(activeTools: readonly string[] = []) { this.activeTools = [...activeTools]; }
    getActiveTools(): string[] { return [...this.activeTools]; }
    setActiveTools(names: string[]): void { this.activeTools = [...names]; }
  }
  const PARENT_TOOLS = ["read", "bash", "edit", "write"];

  test("parent learning activation preserves foreign tools", () => {
    const host = new FakeHost(PARENT_TOOLS);
    const surface = createParentToolSurface(host);
    surface.refreshAgentMemory(true);
    expect(host.activeTools).toEqual([...PARENT_TOOLS, TOOL_NAMES.learn]);
    surface.refreshAgentMemory(false);
    expect(host.activeTools).toEqual(PARENT_TOOLS);
  });

  test("parent learning tool is active on session start", () => {
    const host = new FakeHost(PARENT_TOOLS);
    const surface = createParentToolSurface(host);
    surface.resetSession();
    surface.refreshAgentMemory(true);
    expect(host.activeTools).toContain(TOOL_NAMES.learn);
  });

  test("Harness authoring activates and resets its declared tools", () => {
    const host = new FakeHost(["read", "write"]);
    const surface = createParentToolSurface(host);
    surface.beginHarnessAuthoring();
    expect(host.activeTools).toEqual(["read", "write", TOOL_NAMES.harnessPreview, TOOL_NAMES.harnessWrite]);
    surface.resetSession();
    expect(host.activeTools).toEqual(["read", "write"]);
  });

  test("retired worker loadouts and case tools are not exported", async () => {
    const module = await import("../extensions/tool-surface.ts");
    expect("workerCliArgs" in module).toBe(false);
    expect("WORKER_LOADOUTS" in module).toBe(false);
    expect("harnessCheckCases" in TOOL_NAMES).toBe(false);
    expect(TOOL_NAMES.learningRead).toBe("learning_read");
    expect(TOOL_NAMES.learn).toBe("learn");
  });
});
