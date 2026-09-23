import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fauxAssistantMessage, fauxProvider, fauxToolCall } from "@earendil-works/pi-ai/providers/faux";
import { createAgentSessionFromServices, createAgentSessionServices, createAgentSessionRuntime,
  ModelRuntime, SessionManager, SettingsManager, type CreateAgentSessionRuntimeFactory } from "@earendil-works/pi-coding-agent";

const root = realpathSync(mkdtempSync(join(tmpdir(), "worktree-lifecycle-")));
const originalAgentDir = process.env.PI_CODING_AGENT_DIR;
let dispose: (() => void) | undefined;
try {
  const agentDir = join(root, "agent"); mkdirSync(agentDir);
  process.env.PI_CODING_AGENT_DIR = agentDir;
  const repo = join(root, "repo"); mkdirSync(repo);
  const git = (...args: string[]) => execFileSync("git", ["-C", repo, ...args], { stdio: "pipe" });
  git("init", "-q"); git("config", "user.name", "Test"); git("config", "user.email", "test@example.invalid");
  writeFileSync(join(repo, "tracked.txt"), "original\n");
  git("add", "tracked.txt"); git("commit", "-qm", "fixture");
  const target = join(repo, ".pi", "worktrees", "isolated");
  const provider = fauxProvider({ provider: "worktree-test", models: [{ id: "test" }] });
  const order = process.argv[2] ?? "enter-first";
  const enter = fauxToolCall("enter_worktree", { name: "isolated" });
  const write = fauxToolCall("write", order === "malformed" ? { path: "leaked.txt" } : { path: "leaked.txt", content: "wrong checkout" });
  provider.setResponses([
    fauxAssistantMessage(order === "enter-first" ? [enter, write] : [write, enter]),
    ...(order === "malformed" || order === "follow-up" ? [fauxAssistantMessage([
      fauxToolCall("edit", { path: "tracked.txt", edits: [{ oldText: "original", newText: "leaked" }] }),
    ])] : []),
    fauxAssistantMessage([
      fauxToolCall("edit", { path: "tracked.txt", edits: [{ oldText: "original", newText: "worktree" }] }),
      fauxToolCall("write", { path: "new.txt", content: "worktree only" }),
      fauxToolCall("bash", { command: "pwd > actual-cwd.txt" }),
    ]),
    fauxAssistantMessage("Finished in worktree"),
  ]);
  const modelRuntime = await ModelRuntime.create({ modelsPath: null, refreshOnCreate: false });
  modelRuntime.registerNativeProvider(provider.provider);
  const settings = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
  const factory: CreateAgentSessionRuntimeFactory = async ({ cwd, sessionManager, sessionStartEvent }) => {
    const services = await createAgentSessionServices({ cwd, agentDir, modelRuntime, settingsManager: settings,
      resourceLoaderOptions: { additionalExtensionPaths: [resolve("packages/utils/extensions/worktree-session.ts"), resolve("packages/utils/extensions/worktree-completion.ts")], noSkills: true, noPromptTemplates: true } });
    return { ...await createAgentSessionFromServices({ services, sessionManager, sessionStartEvent, model: provider.getModel("test") }), services, diagnostics: services.diagnostics };
  };
  const runtime = await createAgentSessionRuntime(factory, { cwd: repo, agentDir, sessionManager: SessionManager.create(repo, join(agentDir, "sessions")) });
  dispose = () => runtime.session.dispose();
  const errors: string[] = [];
  let resolveSwitched!: () => void;
  const switched = new Promise<void>((resolve) => { resolveSwitched = resolve; });
  const bind = async () => {
    if (order === "rebind-error" && runtime.cwd !== repo) throw new Error("simulated rebind failure");
    const session = runtime.session;
    await session.bindExtensions({ mode: "print", onError: (e) => errors.push(e.error), commandContextActions: {
      waitForIdle: () => session.waitForIdle(), newSession: (o) => runtime.newSession(o),
      fork: (id, o) => runtime.fork(id, o),
      switchSession: async (file, o) => { try { const result = await runtime.switchSession(file, o); if (order === "post-switch-error") throw new Error("simulated post-switch host failure"); return result; } finally { resolveSwitched(); } },
      navigateTree: (id, o) => session.navigateTree(id, o), reload: async () => {},
    } });
  };
  runtime.setRebindSession(bind); await bind();
  const source = runtime.session;
  if (order === "follow-up" || order === "abort") {
    source.subscribe((event) => {
      if (event.type === "tool_execution_end" && event.toolName === "enter_worktree") {
        if (order === "abort") void source.abort();
        else void source.followUp("Continue the edits");
      }
    });
  }
  await runtime.session.prompt("Enter an isolated worktree, then edit tracked.txt and create new.txt there.");
  assert.equal(existsSync(join(repo, "leaked.txt")), false, "same-batch write leaked into original checkout");
  if (order === "abort") {
    await new Promise((resolve) => setTimeout(resolve, 100));
    assert.ok(runtime.session === source, "aborted transition replaced the session");
    assert.equal(existsSync(target), false, "aborted transition created a worktree");
    console.log(JSON.stringify({ status: "passed", order }));
  } else {
  let timer: ReturnType<typeof setTimeout>;
  try {
    await Promise.race([switched, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`worktree switch timed out: ${errors.join("; ")}`)), 5000); })]);
  } finally { clearTimeout(timer!); }
  await runtime.session.waitForIdle();
  assert.equal(readFileSync(join(repo, "tracked.txt"), "utf8"), "original\n", "original tracked file changed");
  assert.equal(runtime.cwd, target);
  if (order === "rebind-error") {
    assert.equal(existsSync(target), true, "active checkout deleted after failed host rebind");
    assert.equal(readFileSync(join(target, "tracked.txt"), "utf8"), "original\n");
  } else {
  assert.equal(readFileSync(join(target, "tracked.txt"), "utf8"), "worktree\n");
  assert.equal(readFileSync(join(target, "new.txt"), "utf8"), "worktree only");
  assert.equal(readFileSync(join(target, "actual-cwd.txt"), "utf8").trim(), target);
  assert.equal(existsSync(join(repo, "new.txt")), false);
  provider.setResponses([
    fauxAssistantMessage([
      fauxToolCall("edit", { path: join(repo, "tracked.txt"), edits: [{ oldText: "original", newText: "leaked" }] }),
      fauxToolCall("write", { path: join(repo, "absolute-leak.txt"), content: "leaked" }),
    ]),
    fauxAssistantMessage("Foreign writes rejected"),
  ]);
  await runtime.session.prompt("Try the stale absolute file paths from the parent conversation.");
  assert.equal(readFileSync(join(repo, "tracked.txt"), "utf8"), "original\n", "absolute edit leaked into original checkout");
  assert.equal(existsSync(join(repo, "absolute-leak.txt")), false, "absolute write leaked into original checkout");
  assert.deepEqual(errors, []);
  }
  console.log(JSON.stringify({ status: "passed", order }));
  }
} finally {
  dispose?.();
  if (originalAgentDir === undefined) delete process.env.PI_CODING_AGENT_DIR;
  else process.env.PI_CODING_AGENT_DIR = originalAgentDir;
  rmSync(root, { recursive: true, force: true });
}
