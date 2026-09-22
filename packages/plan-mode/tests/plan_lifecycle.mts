import assert from "node:assert/strict";
import { existsSync, readFileSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fauxAssistantMessage, fauxProvider } from "@earendil-works/pi-ai/providers/faux";
import { createAgentSessionFromServices, createAgentSessionServices, createAgentSessionRuntime,
  ModelRuntime, SessionManager, SettingsManager, type CreateAgentSessionRuntimeFactory,
  type ExtensionUIDialogOptions } from "@earendil-works/pi-coding-agent";

const root = mkdtempSync(join(tmpdir(), "plan-lifecycle-"));
const originalArgv = process.argv[1];
const originalAgentDir = process.env.PI_CODING_AGENT_DIR;
let dispose: (() => void) | undefined;
type Review = { choices: string[]; choose: (choice?: string) => void; signal?: AbortSignal };
const reviews: Review[] = [];
try {
  process.env.PI_CODING_AGENT_DIR = root;
  writeFileSync(join(root, "plan-mode.json"), JSON.stringify({ provider: "plan-test", model: "child" }));
  const scenario = process.argv[2] ?? "dismiss";
  const bin = join(root, "bin"); mkdirSync(bin);
  writeFileSync(join(bin, "package.json"), JSON.stringify({ name: "@earendil-works/pi-coding-agent" }));
  const capture = join(root, "calls.jsonl"), started = join(root, "started"), stopped = join(root, "stopped");
  const cli = join(bin, "cli.cjs");
  writeFileSync(cli, `const fs = require("node:fs");
const args = process.argv.slice(2);
fs.appendFileSync(${JSON.stringify(capture)}, JSON.stringify(args) + "\\n");
const finish = (text) => console.log(JSON.stringify({type: "message_end", message: {role: "assistant", content: [{type: "text", text}]}}));
if (${JSON.stringify(scenario === "headless-failed")}) {
  console.error("Planner fixture failed"); process.exit(2);
} else if (${JSON.stringify(scenario === "headless-empty")}) {
  process.exit(0);
} else if (${JSON.stringify(scenario.startsWith("worker-"))} && args.at(-1).includes("repair completion")) {
  fs.writeFileSync(${JSON.stringify(started)}, String(process.pid));
  process.on("SIGTERM", () => { fs.writeFileSync(${JSON.stringify(stopped)}, "stopped"); finish("obsolete result"); process.exit(0); });
  setInterval(() => {}, 1000);
} else finish("# Verified child plan\\nImplement the requested change after approval.");
`);
  process.argv[1] = cli;
  const provider = fauxProvider({ provider: "plan-test", models: [{ id: "parent" }] });
  provider.setResponses(Array.from({ length: 12 }, () => fauxAssistantMessage("Parent response")));
  const modelRuntime = await ModelRuntime.create({ modelsPath: null, refreshOnCreate: false });
  modelRuntime.registerNativeProvider(provider.provider);
  const settings = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
  const factory: CreateAgentSessionRuntimeFactory = async ({ cwd, sessionManager, sessionStartEvent }) => {
    const services = await createAgentSessionServices({ cwd, agentDir: root, modelRuntime, settingsManager: settings,
      resourceLoaderOptions: { additionalExtensionPaths: [resolve("packages/plan-mode/index.ts")], noSkills: true, noPromptTemplates: true } });
    return { ...await createAgentSessionFromServices({ services, sessionManager, sessionStartEvent, model: provider.getModel("parent") }), services, diagnostics: services.diagnostics };
  };
  const runtime = await createAgentSessionRuntime(factory, { cwd: root, agentDir: root,
    sessionManager: scenario === "naming" ? SessionManager.create(root, join(root, "sessions")) : SessionManager.inMemory(root) });
  dispose = () => runtime.session.dispose();
  const original = runtime.session;
  const errors: string[] = [], notifications: string[] = [];
  const bind = async () => {
    const session = runtime.session;
    await session.bindExtensions({ mode: scenario.startsWith("headless") ? "print" : "tui", onError: (e) => errors.push(e.error),
      commandContextActions: {
        waitForIdle: () => session.waitForIdle(),
        newSession: async (options) => {
          if (scenario === "fresh-cancelled") return { cancelled: true };
          if (scenario === "fresh-unavailable") throw new Error("Session creation unavailable");
          return runtime.newSession(options);
        },
        fork: (id, options) => runtime.fork(id, options), switchSession: (file, options) => runtime.switchSession(file, options),
        navigateTree: (id, options) => session.navigateTree(id, options), reload: async () => {},
      },
      uiContext: scenario.startsWith("headless") ? undefined : { ...session.extensionRunner.getUIContext(), notify(message) { notifications.push(message); }, setWidget() {},
        select: async (_title: string, choices: string[], options?: ExtensionUIDialogOptions) => new Promise<string | undefined>((choose) => {
          reviews.push({ choices, choose, signal: options?.signal });
          options?.signal?.addEventListener("abort", () => choose(undefined), { once: true });
        }),
      },
    });
  };
  runtime.setRebindSession(bind); await bind();
  const until = async (predicate: () => boolean) => {
    for (let i = 0; i < 300 && !predicate(); i++) await new Promise((r) => setTimeout(r, 10));
    assert.ok(predicate(), `condition did not settle: ${scenario}; ${errors.join("; ")}`);
  };
  const planPath = join(root, "plans", "repair-completion.md");
  if (scenario === "headless-failed" || scenario === "headless-empty") {
    mkdirSync(join(root, "plans"));
    writeFileSync(planPath, "# Previous plan\n");
    original.sessionManager.appendCustomEntry("plan-mode-path", { path: planPath });
    await original.extensionRunner.emit({ type: "session_start", reason: "reload" });
  }
  let pending: Promise<void>;
  if (scenario === "start-review") {
    await original.prompt("/plan start");
    provider.setResponses([() => { writeFileSync(planPath, "# Manual plan"); return fauxAssistantMessage("Ready"); }]);
    pending = original.prompt("repair completion");
  } else pending = original.prompt("/plan repair completion");
  if (scenario === "headless-failed" || scenario === "headless-empty") {
    await pending;
    assert.equal(readFileSync(planPath, "utf8"), "# Previous plan\n");
    assert.equal(provider.state.callCount, 0);
    assert.equal(reviews.length, 0);
  } else if (scenario === "headless") {
    await pending;
    assert.ok(readFileSync(planPath, "utf8").includes("Verified child plan"));
    assert.equal(provider.state.callCount, 0); assert.equal(reviews.length, 0);
    const calls: string[][] = readFileSync(capture, "utf8").trim().split("\n").map((s) => JSON.parse(s));
    assert.equal(calls.length, 1, "default planning uses exactly one child");
    const args = calls[0];
    for (const flag of ["--print", "--no-session", "-ne", "-ns", "-np", "-nc", "--no-themes"]) assert.ok(args.includes(flag), flag);
    assert.equal(args[args.indexOf("--tools") + 1], "read,grep,find,ls");
    assert.equal(args[args.indexOf("--mode") + 1], "json");
    assert.equal(args[args.indexOf("--model") + 1], "plan-test/child");
    assert.equal(original.model?.id, "parent");
  } else if (scenario.startsWith("worker-")) {
    await until(() => existsSync(started));
    let replacement: Promise<void> | undefined;
    if (scenario === "worker-new") await runtime.newSession();
    else if (scenario === "worker-replace") replacement = original.prompt("/plan replacement request");
    else await original.prompt("/plan exit");
    await pending; await until(() => existsSync(stopped));
    assert.ok(!readFileSync(planPath, "utf8").includes("obsolete result"));
    if (replacement) { await until(() => reviews.length === 1); reviews[0].choose(); await replacement; }
    else assert.equal(reviews.length, 0);
  } else {
    await until(() => reviews.length === 1);
    assert.equal(original.isStreaming, false);
    if (scenario !== "start-review") assert.equal(provider.state.callCount, 0, "parent must not generate the plan");
    assert.ok(reviews[0].choices.includes("Implement in current session"));
    assert.ok(reviews[0].choices.includes("Implement in new session"));
    if (scenario === "here" || scenario.startsWith("fresh")) {
      reviews[0].choose(scenario === "here" ? "Implement in current session" : "Implement in new session"); await pending;
      if (scenario === "fresh-unavailable" || scenario === "fresh-cancelled") {
        assert.equal(runtime.session, original); assert.equal(provider.state.callCount, 0);
        assert.ok(notifications.some((n) => /unavailable|cancel/i.test(n)));
      } else {
        await until(() => provider.state.callCount === 1);
        assert.equal(runtime.session === original, scenario === "here");
        assert.ok(JSON.stringify(runtime.session.messages).includes("Implement this plan:"));
        if (scenario === "fresh") assert.ok(!JSON.stringify(original.messages).includes("Implement this plan:"));
      }
    } else if (scenario.startsWith("review-") || scenario.startsWith("manual-")) {
      if (scenario.startsWith("manual-")) { reviews[0].choose(); await pending; pending = original.prompt("/plan review"); await until(() => reviews.length === 2); }
      const stale = reviews.at(-1)!, count = reviews.length;
      let replacement: Promise<void> | undefined;
      if (scenario.endsWith("-new")) await runtime.newSession();
      else if (scenario.endsWith("-replace")) replacement = original.prompt("/plan replacement request");
      else await original.prompt("/plan exit");
      await pending; assert.ok(stale.signal?.aborted); stale.choose("Implement in current session");
      if (replacement) { await until(() => reviews.length === count + 1); reviews.at(-1)!.choose(); await replacement; }
      assert.equal(provider.state.callCount, 0);
    } else {
      reviews[0].choose(); await pending;
      if (scenario === "start-review") await until(() => notifications.some((message) => message.includes("Plan kept.")));
      if (scenario === "naming") {
        const originalFile = original.sessionManager.getSessionFile()!;
        await runtime.newSession();
        const second = runtime.session.prompt("/plan repair completion");
        await until(() => reviews.length === 2); reviews[1].choose(); await second;
        assert.ok(existsSync(join(root, "plans", "repair-completion-2.md")));
        await runtime.switchSession(originalFile);
        const restored = runtime.session.prompt("/plan revised request");
        await until(() => reviews.length === 3); reviews[2].choose(); await restored;
        assert.equal(runtime.session.sessionManager.getBranch().filter((e) => e.type === "custom" && e.customType === "plan-mode-path").length, 1);
      } else if (scenario === "dismiss") {
        assert.equal((await original.extensionRunner.emitToolCall({ type: "tool_call", toolCallId: "guard", toolName: "write", input: { path: join(root, "project.ts"), content: "no" } }))?.block, true);
        await original.prompt("Another prompt"); assert.equal(reviews.length, 1);
      }
    }
  }
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ scenario, status: "passed" }));
} finally {
  for (const review of reviews) review.choose();
  dispose?.();
  const marker = join(root, "started");
  if (existsSync(marker) && !existsSync(join(root, "stopped"))) {
    try { process.kill(Number(readFileSync(marker, "utf8")), "SIGTERM"); } catch {}
  }
  process.argv[1] = originalArgv;
  if (originalAgentDir === undefined) delete process.env.PI_CODING_AGENT_DIR;
  else process.env.PI_CODING_AGENT_DIR = originalAgentDir;
  rmSync(root, { recursive: true, force: true });
}
