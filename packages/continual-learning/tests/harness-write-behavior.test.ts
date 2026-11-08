/** One-step declared Harness write: parent-owned gates + atomic write. */
import { expect, test } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import registerGuardrails from "../extensions/guardrails.ts";

interface Tool {
  name: string;
  execute: (id: string, params: unknown, signal: AbortSignal | undefined, update: unknown, ctx: unknown) => Promise<{ content: Array<{ text: string }>; details: { applied?: boolean }; isError: boolean }>;
}

function harness() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cl-harness-write-"));
  const cwd = path.join(root, "project");
  fs.mkdirSync(cwd, { recursive: true });
  fs.mkdirSync(path.join(root, "agent"));
  process.env.PI_CODING_AGENT_DIR = path.join(root, "agent");
  const tools = new Map<string, Tool>();
  const hooks = new Map<string, (...args: unknown[]) => unknown>();
  const commands = new Map<string, { handler: (...args: unknown[]) => unknown }>();
  let active = ["read", "write"];
  const pi: Record<string, unknown> = {
    on: (name: string, fn: (...args: unknown[]) => unknown) => { hooks.set(name, fn); },
    registerCommand: (name: string, command: { handler: (...args: unknown[]) => unknown }) => { commands.set(name, command); },
    registerTool: (tool: Tool) => { tools.set(tool.name, tool); },
    registerEntryRenderer() {},
    registerMessageRenderer() {},
    sendMessage() {},
    appendEntry() {},
    getCommands: () => [],
    getActiveTools: () => [...active],
    setActiveTools: (names: string[]) => { active = [...names]; },
  };
  registerGuardrails(pi as never);
  return { root, cwd, tools, hooks, commands, get active() { return active; } };
}

const candidate = JSON.stringify({ rules: [{ id: "traffic", text: "D0", instructions: "confirm volume first" }] });
const validCases = [
  { ruleId: "traffic", input: "维护 D0", matches: true },
  { ruleId: "traffic", input: "本地配色", matches: false },
];

async function openProcedure(h: ReturnType<typeof harness>, hasUI: boolean, options: { scope?: string; confirm?: () => Promise<boolean> } = {}) {
  const ctx = { cwd: h.cwd, hasUI, ui: { notify() {}, select: async () => "Allow once", confirm: options.confirm ?? (async () => true) }, sessionManager: { getBranch: () => [], getSessionId: () => "s" } };
  const request = `${options.scope ?? ""} 避免后续 D0 的流量被打爆`.trim();
  await h.commands.get("harness")!.handler(request, ctx);
  return ctx;
}

test("the declared tool is registered and activated with authoring", async () => {
  const h = harness();
  try {
    expect(h.tools.has("harness_write")).toBe(true);
    await openProcedure(h, true);
    expect(h.active).toContain("harness_write");
    void h.hooks.get("session_shutdown")!({}, { cwd: h.cwd });
    expect(h.active).not.toContain("harness_write");
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("headless, wrong target and incomplete cases write nothing", async () => {
  const h = harness();
  try {
    const tool = h.tools.get("harness_write")!;
    const headless = await openProcedure(h, false);
    const params = { path: path.join(h.cwd, ".pi", "harness.json"), content: candidate, cases: validCases };
    const noUI = await tool.execute("a", params, undefined, undefined, headless);
    expect(noUI.isError).toBe(true);
    const target = path.join(h.cwd, ".pi", "harness.json");
    expect(fs.existsSync(target)).toBe(false);

    const ui = { cwd: h.cwd, hasUI: true, ui: { notify() {}, select: async () => "Allow once", confirm: async () => true }, sessionManager: { getBranch: () => [], getSessionId: () => "s" } };
    await h.commands.get("harness")!.handler("维护 D0", ui);
    const wrong = await tool.execute("b", { ...params, path: path.join(h.cwd, "other.json") }, undefined, undefined, ui);
    expect(wrong.isError).toBe(true);
    const incomplete = await tool.execute("c", { ...params, cases: validCases.slice(0, 1) }, undefined, undefined, ui);
    expect(incomplete.isError).toBe(true);
    expect(fs.existsSync(target)).toBe(false);
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("two concurrent writes admit exactly one", async () => {
  const h = harness();
  try {
    const tool = h.tools.get("harness_write")!;
    const ctx = await openProcedure(h, true);
    const target = path.join(h.cwd, ".pi", "harness.json");
    const params = { path: target, content: candidate, cases: validCases };
    const results = await Promise.all([
      tool.execute("first", params, undefined, undefined, ctx),
      tool.execute("second", params, undefined, undefined, ctx),
    ]);
    expect(results.filter(result => !result.isError).length).toBe(1);
    expect(results.filter(result => result.isError).length).toBe(1);
    expect(fs.readFileSync(target, "utf8")).toBe(candidate);
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("a valid one-step write persists exact bytes and records an undoable change", async () => {
  const h = harness();
  try {
    const tool = h.tools.get("harness_write")!;
    const ctx = await openProcedure(h, true);
    const target = path.join(h.cwd, ".pi", "harness.json");
    const result = await tool.execute("write-1", { path: target, content: candidate, cases: validCases }, undefined, undefined, ctx);
    expect(result.isError).toBe(false);
    expect(result.details.applied).toBe(true);
    expect(fs.readFileSync(target, "utf8")).toBe(candidate);
    const written = JSON.parse(fs.readFileSync(target, "utf8"));
    expect(JSON.stringify(written)).not.toContain("cases");
    const runs = path.join(h.root, "agent", "memory", "runs");
    const receipts = fs.readdirSync(runs, { recursive: true }).map(String)
      .filter(name => name.endsWith("learning-pipeline-receipt.json"));
    expect(receipts.length).toBeGreaterThan(0);
    const receipt = JSON.parse(fs.readFileSync(path.join(runs, receipts[0]!), "utf8"));
    expect(receipt.kind).toBe("learning-pipeline-receipt");
    expect(receipt.operations).toBe(1);
    expect(receipt.batchId).toMatch(/^batch_[a-f0-9]{32}$/);
    const history = path.join(h.root, "agent", "memory", "history");
    const records = fs.readdirSync(history, { recursive: true }).map(String)
      .filter(name => path.basename(name).startsWith("change_") && name.endsWith(".json"));
    expect(records.length).toBe(1);
    const record = JSON.parse(fs.readFileSync(path.join(history, records[0]!), "utf8"));
    expect(record.status).toBe("applied");
    expect(receipt.batchId).toBe(record.batchId);
    expect(h.active).not.toContain("harness_write");
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("silently removing a legacy protection container is refused", async () => {
  const h = harness();
  try {
    const target = path.join(h.cwd, ".pi", "harness.json");
    fs.mkdirSync(path.dirname(target), { recursive: true });
    const prior = JSON.stringify({ policies: [{ name: "protect-prod", action: "block" }], rules: [{ id: "traffic", text: "D0", instructions: "first" }] });
    fs.writeFileSync(target, prior);
    const ctx = await openProcedure(h, true);
    const tool = h.tools.get("harness_write")!;
    const result = await tool.execute("w", { path: target, content: candidate, cases: [] }, undefined, undefined, ctx);
    expect(result.isError).toBe(true);
    expect(result.content[0].text).toContain("legacy protection");
    expect(fs.readFileSync(target, "utf8")).toBe(prior);
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("a session end or abort during confirmation writes nothing and does not re-arm", async () => {
  const h = harness();
  try {
    const tool = h.tools.get("harness_write")!;
    const target = path.join(h.cwd, ".pi", "harness.json");
    let finish!: () => void;
    const gate = new Promise<void>(resolve => { finish = resolve; });
    const ctx = await openProcedure(h, true, { confirm: async () => { await gate; return true; } });
    const pending = tool.execute("w", { path: target, content: candidate, cases: validCases }, undefined, undefined, ctx);
    await new Promise(resolve => setTimeout(resolve, 10));
    await h.hooks.get("session_shutdown")!({}, ctx);
    finish();
    const result = await pending;
    expect(result.isError).toBe(true);
    expect(fs.existsSync(target)).toBe(false);
    expect(h.active).not.toContain("harness_write");
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("global and local scopes are directed to the two-step native path", async () => {
  const h = harness();
  try {
    const tool = h.tools.get("harness_write")!;
    for (const scope of ["--global", "--local"]) {
      const ctx = await openProcedure(h, true, { scope });
      const target = scope === "--global" ? path.join(h.root, "agent", "harness.json") : path.join(h.cwd, ".pi", "harness.local.json");
      const result = await tool.execute("w", { path: target, content: candidate, cases: validCases }, undefined, undefined, ctx);
      expect(result.isError).toBe(true);
      expect(result.content[0].text).toContain("two-step native write");
      expect(fs.existsSync(target)).toBe(false);
      await h.hooks.get("session_shutdown")!({}, ctx);
    }
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("a readback mismatch restores predecessor bytes and leaves no pending history", async () => {
  const h = harness();
  try {
    const target = path.join(h.cwd, ".pi", "harness.json");
    fs.mkdirSync(path.dirname(target), { recursive: true });
    const prior = JSON.stringify({ rules: [] });
    fs.writeFileSync(target, prior);
    const ctx = await openProcedure(h, true);
    const tool = h.tools.get("harness_write")!;
    // Race the readback: rewrite the file after the atomic write completes.
    const originalReadFile = fs.promises.readFile.bind(fs.promises);
    let injected = false;
    fs.promises.readFile = (async (file: fs.PathLike, ...rest: unknown[]) => {
      const value = await originalReadFile(file, ...rest as []);
      // Only corrupt AFTER the atomic write: the pre-write predecessor reads
      // must stay clean so the test reaches the readback/rollback branch.
      if (!injected && String(file) === target && value.toString("utf8") === candidate) {
        injected = true;
        const foreign = JSON.stringify({ rules: [{ id: "foreign", text: "x" }] });
        fs.writeFileSync(target, foreign);
        return Buffer.from(foreign);
      }
      return value;
    }) as typeof fs.promises.readFile;
    try {
      const result = await tool.execute("w", { path: target, content: candidate, cases: validCases }, undefined, undefined, ctx);
      expect(result.isError).toBe(true);
    } finally { fs.promises.readFile = originalReadFile; }
    expect(fs.readFileSync(target, "utf8")).toBe(prior);
    const history = path.join(h.root, "agent", "memory", "history");
    const pending = fs.existsSync(history) ? fs.readdirSync(history, { recursive: true }).map(String)
      .filter(name => name.endsWith(".json") && JSON.parse(fs.readFileSync(path.join(history, name), "utf8")).status === "pending") : [];
    expect(pending).toEqual([]);
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});
