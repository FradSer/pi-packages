/** One-step declared Harness write: parent-owned gates, atomic write, and strict wire schema. */
import { describe, expect, test } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { Type } from "typebox";
import { getJsonSchemaToolParameters } from "../../../node_modules/@earendil-works/pi-coding-agent/dist/bundle/chunks/chunk-7O7QKK6A.js";
import registerGuardrails, { HARNESS_WRITE_PARAMETERS } from "../extensions/guardrails.ts";
import { withFileMutationQueue } from "@earendil-works/pi-coding-agent";
import { acquireConsolidationLock, resolveConsolidationRunPaths } from "../extensions/consolidation-run.ts";
import { checkPendingLearningMutations, listLearningHistory, previewLearningUndo } from "../extensions/learning-history.ts";

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

function receipts(h: ReturnType<typeof harness>) {
  const root = path.join(h.root, "agent", "memory", "runs");
  const files = fs.existsSync(root) ? fs.readdirSync(root, { recursive: true }).map(String) : [];
  return files.filter(name => name.endsWith("learning-pipeline-receipt.json"))
    .map(name => JSON.parse(fs.readFileSync(path.join(root, name), "utf8")));
}

for (const action of ["block", "confirm"]) test(`declared writer honors legacy ${action} on the native write projection`, async () => {
  const h = harness();
  try {
    const target = path.join(h.cwd, ".pi/harness.json");
    fs.mkdirSync(path.dirname(target));
    const prior = JSON.stringify({ policies: [{ name: "protect", tools: ["write"], pattern: "D0", action, reason: "Protected" }], rules: [] });
    fs.writeFileSync(target, prior);
    const content = JSON.stringify({ ...JSON.parse(prior), ...JSON.parse(candidate) });
    let confirmations = 0;
    const ctx = await openProcedure(h, true, { confirm: async () => { confirmations++; return false; } });
    ctx.ui.select = async () => "Block";
    const result = await h.tools.get("harness_write")!.execute("w", { path: target, content, cases: validCases }, undefined, undefined, ctx);
    expect(confirmations).toBe(action === "confirm" ? 1 : 0);
    expect(result.isError).toBe(true);
    expect(fs.readFileSync(target, "utf8")).toBe(prior);
    expect(receipts(h)).toEqual([]);
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("native authoring fails closed without UI even after a valid preview", async () => {
  const h = harness();
  try {
    const ctx = await openProcedure(h, false);
    const preview = await h.tools.get("harness_preview")!.execute("p", { content: candidate, cases: validCases }, undefined, undefined, ctx);
    expect(preview.isError).toBe(true);
    const result = await h.hooks.get("tool_call")!({ toolName: "write", toolCallId: "w", input: { path: ".pi/harness.json", content: candidate } }, ctx);
    expect(result).toMatchObject({ block: true });
    expect(fs.existsSync(path.join(h.cwd, ".pi/harness.json"))).toBe(false);
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("inherited invalid layers refuse authoring before confirmation", async () => {
  const h = harness();
  try {
    fs.writeFileSync(path.join(h.root, "agent", "harness.json"), JSON.stringify({ rules: [{ id: "bad", bash: "[", message: "invalid" }] }));
    let confirmations = 0;
    const ctx = await openProcedure(h, true, { confirm: async () => { confirmations++; return false; } });
    const result = await h.tools.get("harness_write")!.execute("w", { path: ".pi/harness.json", content: candidate, cases: validCases }, undefined, undefined, ctx);
    expect(result.isError).toBe(true);
    expect(confirmations).toBe(0);
    expect(fs.existsSync(path.join(h.cwd, ".pi/harness.json"))).toBe(false);
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("explicit writer cannot bypass an occupied project lock", async () => {
  const h = harness();
  const lock = await acquireConsolidationLock(resolveConsolidationRunPaths(h.cwd));
  try {
    const ctx = await openProcedure(h, true);
    const result = await h.tools.get("harness_write")!.execute("w", { path: ".pi/harness.json", content: candidate, cases: validCases }, undefined, undefined, ctx);
    expect(result.isError).toBe(true);
    expect(fs.existsSync(path.join(h.cwd, ".pi/harness.json"))).toBe(false);
    expect(fs.existsSync(lock.path)).toBe(true);
  } finally { await lock.release(); fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("explicit writer waits for the native target queue and rechecks its predecessor", async () => {
  const h = harness();
  let release!: () => void;
  let entered!: () => void;
  const occupied = new Promise<void>(resolve => { entered = resolve; });
  const gate = new Promise<void>(resolve => { release = resolve; });
  const target = path.join(h.cwd, ".pi/harness.json");
  const queue = withFileMutationQueue(target, async () => { entered(); await gate; });
  try {
    await occupied;
    let confirmed!: () => void;
    const approval = new Promise<void>(resolve => { confirmed = resolve; });
    const ctx = await openProcedure(h, true, { confirm: async () => { confirmed(); return true; } });
    const pending = h.tools.get("harness_write")!.execute("w", { path: target, content: candidate, cases: validCases }, undefined, undefined, ctx);
    await approval;
    await new Promise(resolve => setImmediate(resolve));
    expect(fs.existsSync(target)).toBe(false);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    const foreign = '{"rules":[],"foreign":"preserve"}';
    fs.writeFileSync(target, foreign);
    release();
    expect((await pending).isError).toBe(true);
    expect(fs.readFileSync(target, "utf8")).toBe(foreign);
    expect(await listLearningHistory(h.cwd)).toEqual([]);
  } finally { release(); await queue; fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("late predecessor drift is preserved before atomic rename", async () => {
  const h = harness();
  const original = fs.promises.lstat;
  try {
    const target = path.join(h.cwd, ".pi/harness.json");
    fs.mkdirSync(path.dirname(target));
    fs.writeFileSync(target, '{"rules":[]}');
    const foreign = '{"rules":[],"foreign":"late"}';
    const ctx = await openProcedure(h, true);
    let injected = false;
    fs.promises.lstat = (async (...args: Parameters<typeof original>) => {
      const value = await original(...args);
      if (!injected && String(args[0]) === target && args[1]?.bigint) {
        injected = true;
        fs.writeFileSync(target, foreign);
      }
      return value;
    }) as typeof original;
    const result = await h.tools.get("harness_write")!.execute("w", { path: target, content: candidate, cases: validCases }, undefined, undefined, ctx);
    expect(injected).toBe(true);
    expect(result.isError).toBe(true);
    expect(fs.readFileSync(target, "utf8")).toBe(foreign);
  } finally { fs.promises.lstat = original; fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("abort after receipt commit retains the applied file and undoable history", async () => {
  const h = harness();
  const original = fs.promises.rename;
  const controller = new AbortController();
  try {
    const target = path.join(h.cwd, ".pi/harness.json");
    const ctx = await openProcedure(h, true);
    let injected = false;
    let release!: () => void;
    const observed = new Promise<void>(resolve => { release = resolve; });
    fs.promises.rename = async (from, to) => {
      await original(from, to);
      if (!injected && path.basename(String(to)) === "learning-pipeline-receipt.json") {
        injected = true;
        release();
        controller.abort();
      }
    };
    const pending = h.tools.get("harness_write")!.execute("w", { path: target, content: candidate, cases: validCases }, controller.signal, undefined, ctx);
    await observed;
    const result = await pending;
    expect(injected).toBe(true);
    expect(controller.signal.aborted).toBe(true);
    expect(result.isError).toBe(false);
    expect(h.active).not.toContain("harness_write");
    expect(fs.readFileSync(target, "utf8")).toBe(candidate);
    const [record] = await listLearningHistory(h.cwd);
    expect(record.status).toBe("applied");
    expect(receipts(h).every(receipt => receipt.operations === 1)).toBe(true);
    expect((await previewLearningUndo(h.cwd, record.id)).digest).toBeTruthy();
  } finally { fs.promises.rename = original; fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("receipt save failure reports applied with unavailable receipt, not recorded success", async () => {
  const h = harness();
  const original = fs.promises.rename;
  try {
    const ctx = await openProcedure(h, true);
    fs.promises.rename = async (from, to) => {
      if (path.basename(String(to)) === "learning-pipeline-receipt.json") throw new Error("Fixture receipt failure");
      await original(from, to);
    };
    const result = await h.tools.get("harness_write")!.execute("w", { path: ".pi/harness.json", content: candidate, cases: validCases }, undefined, undefined, ctx);
    expect(result.isError).toBe(false);
    expect(result.content[0].text).toContain("receipt could not be saved");
    expect(result.content[0].text).not.toContain("receipt and undo recorded");
    expect(fs.readFileSync(path.join(h.cwd, ".pi/harness.json"), "utf8")).toBe(candidate);
    expect((await listLearningHistory(h.cwd))[0].status).toBe("applied");
  } finally { fs.promises.rename = original; fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("legacy path policies see the submitted relative path on both writer paths", async () => {
  const h = harness();
  try {
    const user = path.join(h.root, "agent", "harness.json");
    fs.writeFileSync(user, JSON.stringify({ policies: [{ name: "protect-path", tools: ["write"], paths: ["path"], pattern: "^\\.pi/harness\\.json$", action: "block", reason: "Protected path" }] }));
    const ctx = await openProcedure(h, true);
    await h.tools.get("harness_preview")!.execute("p", { content: candidate, cases: validCases }, undefined, undefined, ctx);
    const input = { path: ".pi/harness.json", content: candidate };
    expect(await h.hooks.get("tool_call")!({ toolName: "write", toolCallId: "native", input }, ctx)).toMatchObject({ block: true });
    const result = await h.tools.get("harness_write")!.execute("custom", { ...input, cases: validCases }, undefined, undefined, ctx);
    expect(result.isError).toBe(true);
    expect(fs.existsSync(path.join(h.cwd, input.path))).toBe(false);
    expect(receipts(h)).toEqual([]);
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});

test("an unrelated legacy confirmation does not hold a valid write", async () => {
  const h = harness();
  try {
    fs.writeFileSync(path.join(h.root, "agent", "harness.json"), JSON.stringify({ policies: [{ name: "other-path", tools: ["write"], paths: ["path"], pattern: "^unrelated.txt$", action: "confirm", reason: "Confirm another file" }] }));
    let confirmations = 0;
    const ctx = await openProcedure(h, true, { confirm: async () => ++confirmations > 1 });
    const result = await h.tools.get("harness_write")!.execute("w", { path: ".pi/harness.json", content: candidate, cases: validCases }, undefined, undefined, ctx);
    // Decline the single candidate dialog. No inherited dialog should appear.
    expect(confirmations).toBe(1);
    expect(result.isError).toBe(true);
    expect(result.content[0].text).not.toContain("Inherited write protection");
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});

for (const drift of ["block", "whitespace"]) test(`confirmation rejects inherited layer ${drift} drift`, async () => {
  const h = harness();
  try {
    const user = path.join(h.root, "agent", "harness.json");
    const before = '{"rules":[]}';
    fs.writeFileSync(user, before);
    const changed = drift === "block" ? JSON.stringify({ policies: [{ name: "late-block", tools: ["write"], pattern: "D0", action: "block", reason: "New protection" }] }) : before + " ";
    const ctx = await openProcedure(h, true, { confirm: async () => { fs.writeFileSync(user, changed); return true; } });
    const result = await h.tools.get("harness_write")!.execute("w", { path: ".pi/harness.json", content: candidate, cases: validCases }, undefined, undefined, ctx);
    expect(result.isError).toBe(true);
    expect(fs.readFileSync(user, "utf8")).toBe(changed);
    expect(fs.existsSync(path.join(h.cwd, ".pi/harness.json"))).toBe(false);
    expect(await listLearningHistory(h.cwd)).toEqual([]);
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});

for (const exists of [false, true]) test(`local readback EIO restores ${exists ? "0644 predecessor" : "missing target"} before history closes`, async () => {
  const h = harness();
  const original = fs.promises.readFile;
  try {
    const target = path.join(h.cwd, ".pi/harness.json");
    const before = ' {"rules":[]}\r\n';
    if (exists) { fs.mkdirSync(path.dirname(target)); fs.writeFileSync(target, before); fs.chmodSync(target, 0o644); }
    const ctx = await openProcedure(h, true);
    let injected = false;
    fs.promises.readFile = (async (...args: Parameters<typeof original>) => {
      if (!injected && String(args[0]) === target && fs.existsSync(target) && fs.readFileSync(target, "utf8") === candidate) {
        injected = true;
        throw Object.assign(new Error("fixture readback EIO"), { code: "EIO" });
      }
      return original(...args);
    }) as typeof original;
    const result = await h.tools.get("harness_write")!.execute("w", { path: target, content: candidate, cases: validCases }, undefined, undefined, ctx);
    expect(injected).toBe(true);
    expect(result.isError).toBe(true);
    if (exists) { expect(fs.readFileSync(target, "utf8")).toBe(before); expect(fs.statSync(target).mode & 0o777).toBe(0o644); }
    else expect(fs.existsSync(target)).toBe(false);
    expect(await listLearningHistory(h.cwd)).toEqual([]);
    expect(receipts(h)).toEqual([]);
  } finally { fs.promises.readFile = original; fs.rmSync(h.root, { recursive: true, force: true }); }
});

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

test("a readback mismatch preserves a foreign edit and leaves pending recovery evidence", async () => {
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
    const foreign = JSON.stringify({ rules: [{ id: "foreign", text: "x" }] });
    fs.promises.readFile = (async (file: fs.PathLike, ...rest: unknown[]) => {
      const value = await originalReadFile(file, ...rest as []);
      // Only corrupt AFTER the atomic write: the pre-write predecessor reads
      // must stay clean so the test reaches the readback/rollback branch.
      if (!injected && String(file) === target && value.toString("utf8") === candidate) {
        injected = true;
        fs.writeFileSync(target, foreign);
        return Buffer.from(foreign);
      }
      return value;
    }) as typeof fs.promises.readFile;
    try {
      const result = await tool.execute("w", { path: target, content: candidate, cases: validCases }, undefined, undefined, ctx);
      expect(result.isError).toBe(true);
    } finally { fs.promises.readFile = originalReadFile; }
    expect(injected).toBe(true);
    expect(fs.readFileSync(target, "utf8")).toBe(foreign);
    const history = path.join(h.root, "agent", "memory", "history");
    const pending = fs.existsSync(history) ? fs.readdirSync(history, { recursive: true }).map(String)
      .filter(name => name.endsWith(".json") && JSON.parse(fs.readFileSync(path.join(history, name), "utf8")).status === "pending") : [];
    expect(pending).toHaveLength(1);
    await expect(checkPendingLearningMutations(h.cwd)).rejects.toThrow();
  } finally { fs.rmSync(h.root, { recursive: true, force: true }); }
});

describe("harness_write strict wire schema", () => {
  const writeParameters = Type.Object({
    path: Type.String({ description: "Path to the file to write" }),
    content: Type.String({ description: "Content to write" }),
  });

  function strictWriteSchema(): Record<string, unknown> {
    return getJsonSchemaToolParameters({
      name: "write",
      parameters: writeParameters,
      constrainedSampling: { type: "json_schema", strict: "prefer" },
    }, true) as Record<string, unknown>;
  }

  test("strict sampling forbids any sibling field on native write", () => {
    const schema = strictWriteSchema();
    expect(schema.additionalProperties).toBe(false);
    expect(schema.required).toEqual(["path", "content"]);
    expect(Object.keys((schema.properties ?? {}) as Record<string, unknown>).sort()).toEqual(["content", "path"]);
  });

  test("content is an unconstrained string that can carry a case envelope", () => {
    const schema = strictWriteSchema();
    const content = (schema.properties as Record<string, Record<string, unknown>>).content;
    expect(content.type).toBe("string");
    expect(content.maxLength).toBeUndefined();
    expect(content.pattern).toBeUndefined();
    const envelope = JSON.stringify({
      rules: [{ id: "d0", text: "\\bD0\\b", action: "block" }],
      harnessCases: [{ ruleId: "d0", input: "维护 D0", matches: true }, { ruleId: "d0", input: "本地配色", matches: false }],
    });
    expect(typeof envelope).toBe("string");
    expect(JSON.parse(envelope).harnessCases).toHaveLength(2);
  });

  test("the declared harness_write tool emits cases on a strict provider wire", () => {
    const schema = getJsonSchemaToolParameters({
      name: "harness_write",
      parameters: HARNESS_WRITE_PARAMETERS,
      constrainedSampling: { type: "json_schema", strict: "prefer" },
    }, true) as Record<string, unknown>;
    expect(schema.additionalProperties).toBe(false);
    expect(schema.required).toEqual(["path", "content", "cases"]);
    const properties = schema.properties as Record<string, Record<string, unknown>>;
    expect(properties.cases.type).toBe("array");
    expect(properties.cases.items).toBeDefined();
    const items = properties.cases.items as Record<string, unknown>;
    expect(items.additionalProperties).toBe(false);
    expect((items.required as string[]).slice().sort()).toEqual(["input", "matches", "ruleId"]);
  });

  test("harness_write cases are required, not optional, so strict sampling cannot drop them", () => {
    const properties = HARNESS_WRITE_PARAMETERS.properties as Record<string, Record<string, unknown>>;
    expect(HARNESS_WRITE_PARAMETERS.required).toEqual(["path", "content", "cases"]);
    expect(properties.cases.anyOf).toBeUndefined();
    expect(properties.cases.type).toBe("array");
  });
});
