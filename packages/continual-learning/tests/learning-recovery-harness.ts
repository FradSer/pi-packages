import { mock } from "bun:test";
import fs from "node:fs";
import promises from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const root = fs.mkdtempSync(path.join(os.tmpdir(), "learning-recovery-"));
process.env.PI_CODING_AGENT_DIR = path.join(root, "agent");
fs.mkdirSync(process.env.PI_CODING_AGENT_DIR);
const scenario = process.argv[2];
if (scenario === "dossier-read-error") {
  const read = promises.readFile.bind(promises);
  promises.readFile = ((file, ...args) => {
    if (String(file).endsWith("incremental-learning-dossier.json")) throw new Error("fixture dossier became unreadable");
    return read(file, ...args);
  }) as typeof promises.readFile;
}
const kit = await import("../../kit/src/index.ts");
let selectors = 0;
let planners = 0;
mock.module("../../kit/src/index.ts", () => ({
  ...kit,
  runPiWorker: async ({ prompt }: { prompt: string }) => {
    selectors += 1;
    if (scenario === "throw") throw new Error("selector fixture threw");
    if (scenario === "invalid") return { text: "not JSON", exitCode: 0, stderr: "" };
    if (scenario === "cancelled") return { text: "", exitCode: 0, stderr: "cancelled", cancelled: true };
    if (scenario === "failed") return { text: "", exitCode: 1, stderr: "provider fixture failed" };
    return {
      text: JSON.stringify({
        kind: "incremental-memory-selection", version: 1,
        contextDigest: /Context digest: ([a-f0-9]+)/.exec(prompt)![1],
        selected: [], memory: false, harness: false, agents: false, reason: "no durable delta",
      }),
      exitCode: 0, stderr: "",
    };
  },
  spawnPiChild: () => { planners += 1; throw new Error("no delta planner expected"); },
}));

try {
  const { default: register, resolveMemoryPaths } = await import("../extensions/inject-memory.ts");
  const cwd = path.join(root, "project");
  fs.mkdirSync(cwd);
  const hooks = new Map<string, Array<(event: unknown, ctx: unknown) => unknown>>();
  const commands = new Map();
  const notices: string[] = [];
  const receipts: unknown[] = [];
  register({
    on: (name, fn) => hooks.set(name, [...(hooks.get(name) ?? []), fn]),
    registerCommand: (name, command) => commands.set(name, command),
    getCommands: () => [], registerMessageRenderer: () => {},
    sendMessage: message => receipts.push(message.details),
  } as Parameters<typeof register>[0]);
  const entries = [
    { message: { role: "user", content: scenario === "noop" ? "修复这个构建错误。" : "Never use the retired compiler." } },
    { message: { role: "assistant", content: "Completed." } },
  ];
  const ctx = {
    cwd, mode: "json", hasUI: false,
    ui: { notify: (text: string) => notices.push(text), setWidget: () => {} },
    sessionManager: { getBranch: () => entries, buildContextEntries: () => entries },
  };
  const emit = async (name: string) => { for (const fn of hooks.get(name) ?? []) await fn({}, ctx); };
  await emit("session_start");
  const locks: boolean[] = [];
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await commands.get("consolidate").handler("", ctx);
    locks.push(fs.existsSync(resolveMemoryPaths(cwd).lockFile));
  }
  await emit("session_shutdown");
  console.log(JSON.stringify({ selectors, planners, locks, shutdownLock: fs.existsSync(resolveMemoryPaths(cwd).lockFile), notices, receipts }));
} finally {
  fs.rmSync(root, { recursive: true, force: true });
}
