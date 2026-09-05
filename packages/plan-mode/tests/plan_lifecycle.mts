import assert from "node:assert/strict";
import { KeybindingsManager } from "../../../node_modules/@earendil-works/pi-coding-agent/dist/core/keybindings.js";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fauxAssistantMessage, fauxProvider } from "@earendil-works/pi-ai/providers/faux";
import { TuiMainScreen, type Component } from "@earendil-works/pi-tui";
import { createAgentSessionFromServices, createAgentSessionServices, createAgentSessionRuntime,
  initTheme, ModelRuntime, SessionManager, SettingsManager, type CreateAgentSessionRuntimeFactory } from "@earendil-works/pi-coding-agent";

initTheme("dark", false);
const root = mkdtempSync(join(tmpdir(), "plan-lifecycle-"));
let disposeRuntime: (() => void) | undefined;
let component: Component | undefined;
const originalSetTimeout = globalThis.setTimeout;
const reviewTimers: Array<{ fire: () => void; timer: ReturnType<typeof setTimeout> }> = [];
globalThis.setTimeout = ((callback, ms, ...args) => {
  const timer = originalSetTimeout(callback, ms, ...args);
  if (ms === 30_000) reviewTimers.push({ fire: () => callback(...args), timer });
  return timer;
}) as typeof setTimeout;
const originalArgv = process.argv[1];
const originalAgentDir = process.env.PI_CODING_AGENT_DIR;
try {
  process.env.PI_CODING_AGENT_DIR = root;
  const scenario = process.argv[2] ?? "dismiss";
  const provider = fauxProvider({ provider: "plan-test", models: [{ id: "planner" }] });
  const modelRuntime = await ModelRuntime.create({ modelsPath: null, refreshOnCreate: false });
  modelRuntime.registerNativeProvider(provider.provider);
  const settings = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
  const factory: CreateAgentSessionRuntimeFactory = async ({ cwd, sessionManager, sessionStartEvent }) => {
    const services = await createAgentSessionServices({ cwd, agentDir: root, modelRuntime, settingsManager: settings,
      resourceLoaderOptions: { additionalExtensionPaths: [resolve("packages/plan-mode/index.ts")], noSkills: true, noPromptTemplates: true } });
    return { ...await createAgentSessionFromServices({ services, sessionManager, sessionStartEvent,
      model: provider.getModel("planner"), noTools: "all" }), services, diagnostics: services.diagnostics };
  };
  const runtime = await createAgentSessionRuntime(factory, { cwd: root, agentDir: root, sessionManager: SessionManager.inMemory(root) });
  disposeRuntime = () => runtime.session.dispose();
  const original = runtime.session;
  const key = createHash("sha256").update(root).digest("hex").slice(0, 16);
  const workerScenario = scenario.startsWith("worker-");
  const workerStarted = join(root, "worker-started");
  const workerStopped = join(root, "worker-stopped");
  if (workerScenario) {
    const bin = join(root, "bin");
    mkdirSync(bin);
    writeFileSync(join(bin, "package.json"), JSON.stringify({ name: "@earendil-works/pi-coding-agent" }));
    const workerCli = join(bin, "cli.cjs");
    writeFileSync(workerCli, `#!/usr/bin/env node
const fs = require("node:fs");
if (${JSON.stringify(scenario)} === "worker-writer-exit" && process.argv.at(-1).startsWith("# Explore Worker")) {
  process.stdout.write(JSON.stringify({type: "message_end", message: {role: "assistant", content: [{type: "text", text: "findings"}]}}) + "\\n");
  process.exit(0);
}
fs.writeFileSync(${JSON.stringify(workerStarted)}, String(process.pid));
process.on("SIGTERM", () => {
  fs.writeFileSync(${JSON.stringify(workerStopped)}, "stopped");
  process.stdout.write(JSON.stringify({type: "message_end", message: {role: "assistant", content: [{type: "text", text: "obsolete plan"}]}}) + "\\n");
  process.exit(0);
});
setInterval(() => {}, 1000);
`, { mode: 0o755 });
    process.argv[1] = workerCli;
  }
  provider.setResponses([() => {
    mkdirSync(join(root, "plans"), { recursive: true });
    writeFileSync(join(root, "plans", `${key}.md`), `# Plan\nWorker research: ${workerScenario ? "required" : "not-needed"}`);
    return fauxAssistantMessage("Plan ready");
  }, () => {
    if (workerScenario) writeFileSync(join(root, "plans", `${key}.md`), "# Replacement plan\nWorker research: not-needed");
    return fauxAssistantMessage("New prompt processed");
  }]);
  let reviewCount = 0;
  let closeCount = 0;
  let freshCompleted = false;
  const errors: string[] = [];
  const terminal = { columns: 100, rows: 30, write() {}, start() {}, stop() {}, hideCursor() {}, showCursor() {},
    moveBy() {}, clearLine() {}, clearFromCursor() {}, clearScreen() {}, setTitle() {},
    drainInput: async () => {}, kittyProtocolActive: false, setProgress() {} };
  const tui = new TuiMainScreen(terminal);
  const bind = async () => {
    const session = runtime.session;
    const baseUI = session.extensionRunner.getUIContext();
    await session.bindExtensions({ mode: "tui", onError: (error) => errors.push(error.error),
      commandContextActions: {
        waitForIdle: () => session.waitForIdle(),
        newSession: async (options) => { const result = await runtime.newSession(options); freshCompleted = true; return result; },
        fork: (id, options) => runtime.fork(id, options),
        switchSession: (file, options) => runtime.switchSession(file, options),
        navigateTree: (id, options) => session.navigateTree(id, options), reload: async () => {},
      },
      uiContext: { ...baseUI, select: async () => "Review current plan", notify(message, level) { if (level === "error") errors.push(message); }, setWidget() {}, custom: (create, options) => {
        reviewCount++;
        assert.equal(options?.overlay, true);
        return new Promise((done) => {
          const created = create(tui, baseUI.theme, KeybindingsManager.create(root), (value) => { closeCount++; done(value); });
          assert.ok(!(created instanceof Promise));
          component = created;
          const lines = component.render(100);
          assert.ok(lines.some((line) => line.includes("Yes, implement here")));
          assert.ok(lines.some((line) => line.includes("Start fresh and implement")));
        });
      } },
    });
  };
  runtime.setRebindSession(bind);
  await bind();
  const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
  await original.prompt("/plan repair completion");
  if (workerScenario) {
    for (let i = 0; i < 100 && !existsSync(workerStarted); i++) await delay(10);
    assert.ok(existsSync(workerStarted), "detached research must start");
    if (scenario === "worker-exit" || scenario === "worker-writer-exit") await original.prompt("/plan exit");
    else if (scenario === "worker-new") await runtime.newSession();
    else await original.prompt("/plan replacement request");
    for (let i = 0; i < 100 && !existsSync(workerStopped); i++) await delay(10);
    assert.ok(existsSync(workerStopped), "obsolete research child must be aborted");
    await delay(50);
    assert.equal(reviewCount, scenario === "worker-replace" ? 1 : 0, "only the replacement plan may open review");
    assert.ok(!readFileSync(join(root, "plans", `${key}.md`), "utf8").includes("obsolete plan"));
  } else {
  for (let i = 0; i < 100 && !component; i++) await delay(10);
  assert.equal(reviewCount, 1, "implementation menu must become available");
  if (scenario.startsWith("manual-")) {
    component?.handleInput?.("\x1b");
    await delay(10);
    const pending = original.prompt(scenario === "manual-menu-replace" ? "/plan" : "/plan review");
    for (let i = 0; i < 100 && reviewCount < 2; i++) await delay(10);
    assert.equal(reviewCount, 2);
    if (scenario === "manual-view-exit") {
      component?.handleInput?.("\x1b[B");
      component?.handleInput?.("\x1b[B");
      component?.handleInput?.("\r");
      await delay(10);
      assert.equal(reviewCount, 3);
    }
    const stale = component;
    const closesBefore = closeCount;
    if (scenario === "manual-new") await runtime.newSession();
    else if (scenario === "manual-menu-replace") await original.prompt("/plan replacement request");
    else await original.prompt("/plan exit");
    await delay(10);
    assert.equal(closeCount, closesBefore + 1, "invalidation must close the manual popup immediately");
    stale?.handleInput?.("\r");
    reviewTimers[1]?.fire();
    await delay(20);
    assert.equal(closeCount, closesBefore + 1, "late input and timeout must not finish the obsolete popup twice");
    await pending;
    assert.equal(freshCompleted, false, "obsolete timeout must not request a fresh implementation session");
    assert.ok(!JSON.stringify(original.messages).includes("Please implement it now"));
    assert.ok(!JSON.stringify(runtime.session.messages).includes("Implement this plan:"));
  } else if (scenario === "review-exit") {
    await original.prompt("/plan exit");
    component?.handleInput?.("\r");
    await delay(10);
    assert.equal(original.pendingMessageCount, 0);
    assert.ok(!JSON.stringify(original.messages).includes("Please implement it now"));
  } else if (scenario === "fresh") {
    component?.handleInput?.("\x1b[B");
    component?.handleInput?.("\r");
    for (let i = 0; i < 300 && !freshCompleted; i++) await delay(10);
    console.log(JSON.stringify({ scenario, freshCompleted, streaming: original.isStreaming, errors }));
    assert.equal(freshCompleted, true, "fresh replacement must not wait on its own agent_end");
    assert.notEqual(runtime.session, original);
    assert.ok(JSON.stringify(runtime.session.messages).includes("Implement this plan:"));
    assert.ok(!JSON.stringify(original.messages).includes("Implement this plan:"));
  } else {
    const settled = await Promise.race([original.waitForIdle().then(() => true), delay(100).then(() => false)]);
    console.log(JSON.stringify({ scenario, reviewCount, settled, streaming: original.isStreaming, errors }));
    assert.equal(settled, true, "planning completion must settle while review awaits input");
    assert.equal(original.isStreaming, false);
    component?.handleInput?.("\x1b");
    await delay(10);
    await original.prompt("Another prompt");
    assert.equal(original.pendingMessageCount, 0);
    assert.equal(reviewCount, 1);
  }
  }
  assert.equal(errors.length, 0);
} finally {
  try {
    component?.handleInput?.("\x1b");
    const marker = join(root, "worker-started");
    if (existsSync(marker) && !existsSync(join(root, "worker-stopped"))) {
      try { process.kill(Number(readFileSync(marker, "utf8")), "SIGTERM"); } catch {}
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    disposeRuntime?.();
  } finally {
    for (const { timer } of reviewTimers) clearTimeout(timer);
    globalThis.setTimeout = originalSetTimeout;
    process.argv[1] = originalArgv;
    if (originalAgentDir === undefined) delete process.env.PI_CODING_AGENT_DIR;
    else process.env.PI_CODING_AGENT_DIR = originalAgentDir;
    rmSync(root, { recursive: true, force: true });
  }
}
