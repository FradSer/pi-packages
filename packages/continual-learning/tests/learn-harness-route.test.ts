/** Option B: an explicit Harness request opens the guarded /harness procedure,
 * never the Memory pipeline. The write itself stays in the follow-up turn. */
import { expect, test } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

interface Message { customType?: string; content?: unknown; display?: boolean; details?: unknown }
interface RegisteredTool { name: string; execute: (...args: any[]) => any }

async function setup() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cl-learn-route-"));
  const cwd = path.join(root, "project");
  fs.mkdirSync(cwd, { recursive: true });
  fs.mkdirSync(path.join(root, "agent", "memory"), { recursive: true });
  fs.writeFileSync(path.join(root, "agent", "continual-learning.json"), JSON.stringify({ autoContinualLearning: true, autoSettledLearning: false }));
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
  const { default: registerGuardrails } = await import("../extensions/guardrails.ts");
  injectMemory(pi);
  registerGuardrails(pi);
  return { root, cwd, hooks, tools, messages, activeTools };
}

function ctx(cwd: string, prompt: string): Record<string, unknown> {
  const rows = [
    { type: "message", id: "u", message: { role: "user", content: [{ type: "text", text: prompt }] } },
    { type: "message", id: "a", message: { role: "assistant", content: "Acknowledged." } },
  ];
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

test("exactly one learning tool named learn is registered in this slice", async () => {
  const { tools } = await setup();
  expect(tools.has("learn")).toBe(true);
  expect(tools.has("learn_current_memory")).toBe(false);
});

test("an in-process organize outcome renders as a success, not a failure", async () => {
  const { learningOutcomeSpec } = await import("../extensions/inject-memory.ts");
  const spec = learningOutcomeSpec({ details: { status: "organized" }, content: [] } as never) as Record<string, unknown>;
  expect(spec.label).toBe("settled");
  expect(spec.tone).toBe("success");
  expect(String(spec.subject)).not.toContain("failed");
});

test("two hosts in one process cannot share a Harness procedure bridge", async () => {
  const first = await setup();
  const second = await setup();
  try {
    // Both hosts register guardrails. A module-global bridge would let the
    // second host's procedure receive the first host's learn() request.
    const firstMessages: Message[] = first.messages;
    const secondMessages: Message[] = second.messages;
    const tool = first.tools.get("learn")!;
    await tool.execute("call", {}, undefined, undefined, ctx(first.cwd, "纠正旧规则"));
    expect(firstMessages.some(m => m.customType === "harness-procedure")).toBe(true);
    expect(secondMessages.some(m => m.customType === "harness-procedure")).toBe(false);
  } finally {
    fs.rmSync(first.root, { recursive: true, force: true });
    fs.rmSync(second.root, { recursive: true, force: true });
  }
});

test("a Harness request returns authoring-started and never starts a Memory pipeline", async () => {
  const { tools, messages, cwd, root } = await setup();
  try {
    const tool = tools.get("learn")!;
    const result = await tool.execute("call", {}, undefined, undefined, ctx(cwd, "以后禁止 npm"));
    expect(result.details.status).toBe("authoring-started");
    expect(result.isError).toBe(false);
    expect(result.content[0].text).toContain("Harness authoring started");
    expect(messages.some(m => m.customType === "harness-procedure")).toBe(true);
    // No learning-pipeline receipt was produced: the Memory pipeline never ran.
    const runsDir = path.join(root, "agent", "memory", "runs");
    const receipts = fs.existsSync(runsDir) ? fs.readdirSync(runsDir, { recursive: true })
      .filter(name => String(name).endsWith("learning-pipeline-receipt.json")) : [];
    expect(receipts).toEqual([]);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test("a Memory request keeps the existing Memory-only pipeline outcome", async () => {
  const { tools, cwd, root } = await setup();
  try {
    const tool = tools.get("learn")!;
    const result = await tool.execute("call", {}, undefined, undefined, ctx(cwd, "整理记忆"));
    // Memory route still reaches the existing agent-pipeline result object.
    expect(["organized", "applied", "proposed", "no-change", "held", "disabled", "failed"]).toContain(result.details.status);
    expect(result.content[0].text).not.toContain("Harness authoring started");
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test("an applied outcome names its real operation count", async () => {
  const { learningOutcomeSpec } = await import("../extensions/inject-memory.ts");
  const spec = learningOutcomeSpec({ details: { status: "applied", operations: 2 }, content: [] } as never) as Record<string, unknown>;
  expect(spec.label).toBe("settled");
  expect(spec.tone).toBe("success");
  expect(String(spec.subject)).toBe("learned 2 Memory changes");
});

test("an applied outcome with no operation count reports zero honestly", async () => {
  const { learningOutcomeSpec } = await import("../extensions/inject-memory.ts");
  const spec = learningOutcomeSpec({ details: { status: "applied" }, content: [] } as never) as Record<string, unknown>;
  expect(String(spec.subject)).toBe("learned 0 Memory changes");
});

test("a no-change settled row stays short, factual and jargon-free", async () => {
  const { learningOutcomeSpec } = await import("../extensions/inject-memory.ts");
  const spec = learningOutcomeSpec({ details: { status: "no-change" }, content: [] } as never) as Record<string, unknown>;
  expect(spec.label).toBe("settled");
  expect(spec.tone).toBe("success");
  expect(String(spec.subject)).toBe("no Memory changes written");
  expect(String(spec.subject)).not.toContain("durable");
});
