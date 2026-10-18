import assert from "node:assert/strict";
import { mkdtemp, writeFile, rm, readFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import net from "node:net";
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { createAgentSession, DefaultResourceLoader, SessionManager, SettingsManager, ModelRuntime } from "@earendil-works/pi-coding-agent";
import { createAssistantMessageEventStream } from "@earendil-works/pi-ai";
import extension from "../index.ts";
import { eventsFromMessage, boundSessionEvent } from "../src/events.ts";

async function until(predicate) {
  const deadline = Date.now() + 5000;
  while (!predicate()) {
    assert.ok(Date.now() < deadline, "owned reporter transition timed out");
    await new Promise(resolve => setTimeout(resolve, 10));
  }
}

test("persisted assistant metadata survives event bounding without inventing terminal values", () => {
  const message = { role: "assistant", stopReason: "stop", content: [{ type: "text", text: "Same reply." }] };
  const event = eventsFromMessage(message, "actual_entry-1")[0];
  assert.equal(event.eventId, "actual_entry-1");
  assert.equal(event.stopReason, "stop");
  assert.deepEqual(boundSessionEvent(event), event);
  for (const reason of ["stop", "toolUse", "length", "error", "aborted"]) {
    assert.equal(eventsFromMessage({ ...message, stopReason: reason }, "actual_entry-1")[0].stopReason, reason);
  }
  for (const id of [undefined, "", "../entry", "x".repeat(129)]) {
    assert.equal(eventsFromMessage(message, id)[0].eventId, undefined);
    assert.equal(eventsFromMessage(message, id)[0].stopReason, undefined);
  }
  assert.equal(eventsFromMessage({ ...message, stopReason: "unknown" }, "actual_entry-1")[0].stopReason, undefined);
  assert.equal(boundSessionEvent({ ...event, stopReason: "unknown", eventId: "../bad" }).eventId, undefined);
  assert.equal(boundSessionEvent({ ...event, stopReason: "unknown" }).stopReason, undefined);
});

test("actual SDK persists after message_end; only settled new entries report IDs and replay preserves them", { timeout: 30000 }, async () => {
  const root = await mkdtemp(join(tmpdir(), "odk-completion-"));
  const saved = { ...process.env };
  const originalFetch = globalThis.fetch;
  let networkCalls = 0;
  globalThis.fetch = async () => { networkCalls++; throw Error("offline fixture forbids fetch"); };
  const records = [], peers = new Set(), observed = [];
  const server = net.createServer(socket => {
    peers.add(socket); socket.on("close", () => peers.delete(socket));
    let pending = "";
    socket.on("data", chunk => {
      pending += chunk.toString();
      const lines = pending.split("\n"); pending = lines.pop();
      for (const line of lines) if (line) {
        const record = JSON.parse(line); records.push(record);
        if (record.type === "hello") socket.write('{"v":1,"type":"ack"}\n');
      }
    });
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  let session;
  const allEvents = () => records.filter(r => r.type === "events").flatMap(r => r.events);
  try {
    delete process.env.ODK_LINK_CONTROL_TOKEN;
    delete process.env.ODK_SESSION_HOST_SOCKET;
    process.env.ODK_LINK_DESKS_FILE = join(root, "desks.json");
    await writeFile(process.env.ODK_LINK_DESKS_FILE, JSON.stringify({ desks: [{ address: `127.0.0.1:${server.address().port}`, token: "synthetic-only" }] }));
    process.env.PI_DIRECTORY_SESSIONS_DIR = join(root, "directory");
    const settingsManager = SettingsManager.inMemory();
    const resourceLoader = new DefaultResourceLoader({ cwd: root, agentDir: root, settingsManager,
      noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true,
      agentsFilesOverride: () => ({ agentsFiles: [] }),
      extensionFactories: [extension, pi => {
        pi.on("message_end", (event, ctx) => {
          if (event.message.role === "assistant") observed.push({ phase: "message_end", leaf: ctx.sessionManager.getLeafId() });
        });
        pi.on("agent_settled", (_event, ctx) => {
          observed.push({ phase: "settled", entry: ctx.sessionManager.getBranch().findLast(e => e.type === "message") });
        });
      }],
    });
    await resourceLoader.reload();
    await writeFile(join(root, "models.json"), JSON.stringify({ providers: { fixture: {
      baseUrl: "http://127.0.0.1:1", api: "openai-completions", apiKey: "synthetic-only",
      models: [{ id: "fixture", name: "Fixture", reasoning: false, input: ["text"], contextWindow: 8192, maxTokens: 256,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    } } }));
    const modelRuntime = await ModelRuntime.create({ authPath: join(root, "auth.json"), modelsPath: join(root, "models.json"), allowModelNetwork: false, refreshOnCreate: false });
    ({ session } = await createAgentSession({ cwd: root, agentDir: root, resourceLoader, settingsManager,
      modelRuntime, model: modelRuntime.getModel("fixture", "fixture"), sessionManager: SessionManager.create(root, join(root, "sessions")), tools: [] }));
    let dispatches = 0;
    session.agent.streamFunction = model => {
      dispatches++;
      const stream = createAssistantMessageEventStream();
      const message = { role: "assistant", api: model.api, provider: model.provider, model: model.id,
        content: [{ type: "text", text: "Same reply." }], stopReason: "stop", timestamp: Date.now(),
        usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
      queueMicrotask(() => { stream.push({ type: "done", reason: "stop", message }); stream.end(); });
      return stream;
    };
    await session.bindExtensions({ mode: "print" });
    const ids = [];
    for (const prompt of ["First synthetic turn.", "Second synthetic turn."]) {
      await session.prompt(prompt);
      const ended = observed.filter(e => e.phase === "message_end").at(-1);
      const settled = observed.filter(e => e.phase === "settled").at(-1);
      assert.equal(settled.entry.message.stopReason, "stop");
      assert.notEqual(ended.leaf, settled.entry.id, "message_end still points at the preceding persisted entry");
      ids.push(settled.entry.id);
      await until(() => allEvents().some(e => e.eventId === settled.entry.id));
      assert.equal(allEvents().find(e => e.eventId === settled.entry.id).stopReason, "stop");
    }
    assert.notEqual(ids[0], ids[1], "identical replies are separate actual turns");
    assert.equal(dispatches, 2);
    assert.equal(networkCalls, 0);
    const before = allEvents().filter(e => e.eventId).length;
    await session.extensionRunner.emit({ type: "agent_settled", aborted: false });
    await session.extensionRunner.emit({ type: "session_shutdown", reason: "reload" });
    await until(() => peers.size === 0);
    assert.equal(allEvents().filter(e => e.eventId).length, before, "settled replay cannot manufacture another completion");
    const file = session.sessionManager.getSessionFile();
    const entries = (await readFile(file, "utf8")).trim().split("\n").map(line => JSON.parse(line));
    for (const id of ids) assert.equal(entries.find(e => e.id === id).message.role, "assistant");
    const handlers = new Map();
    extension({ on(name, fn) { handlers.set(name, fn); }, registerCommand() {}, registerMessageRenderer() {}, registerEntryRenderer() {}, registerTool() {} });
    const ctx = { cwd: root, isIdle: () => true, sessionManager: session.sessionManager };
    const offset = records.length;
    await handlers.get("session_start")({ reason: "reload" }, ctx);
    await until(() => records.slice(offset).filter(r => r.type === "events").flatMap(r => r.events).filter(e => e.eventId).length === 2);
    const replay = records.slice(offset).filter(r => r.type === "events").flatMap(r => r.events).filter(e => e.eventId);
    assert.deepEqual(replay.map(e => [e.eventId, e.stopReason]), ids.map(id => [id, "stop"]));
    // These all settle without a new successfully completed assistant turn.
    const beforeNegatives = records.length;
    const assistant = reason => ({ role: "assistant", content: [{ type: "text", text: "No completion." }],
      api: "openai-completions", provider: "fixture", model: "fixture", timestamp: Date.now(), stopReason: reason,
      usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } });
    const cases = [undefined, ...["toolUse", "length", "error", "aborted", "unknown"].map(assistant),
      { role: "user", content: "Newer user input.", timestamp: Date.now() },
      { role: "toolResult", toolCallId: "fixture", toolName: "fixture", content: [{ type: "text", text: "Newer tool result." }], isError: false, timestamp: Date.now() }];
    for (const message of cases) {
      handlers.get("agent_start")({}, ctx);
      if (message) session.sessionManager.appendMessage(message);
      handlers.get("agent_settled")({ aborted: false }, ctx);
    }
    handlers.get("agent_start")({}, ctx);
    session.sessionManager.appendMessage(assistant("stop"));
    handlers.get("agent_settled")({ aborted: true }, ctx);
    // A stale context cannot assign its latest entry to another current session.
    handlers.get("agent_start")({}, ctx);
    session.sessionManager.appendMessage(assistant("stop"));
    handlers.get("agent_settled")({ aborted: false }, { ...ctx, sessionManager: { ...ctx.sessionManager, getSessionId: () => "different-session" } });
    handlers.get("message_end")({ message: { role: "user", content: "Negative delivery barrier." } }, ctx);
    await until(() => records.slice(beforeNegatives).filter(r => r.type === "events").flatMap(r => r.events).some(e => e.text === "Negative delivery barrier."));
    assert.equal(records.slice(beforeNegatives).filter(r => r.type === "events").flatMap(r => r.events).filter(e => e.eventId).length, 0);
    await handlers.get("session_shutdown")({}, ctx);
  } finally {
    if (session) { await session.extensionRunner.emit({ type: "session_shutdown", reason: "quit" }); session.dispose(); }
    for (const peer of peers) peer.destroy();
    await new Promise(resolve => server.close(resolve));
    process.env = saved;
    globalThis.fetch = originalFetch;
    await rm(root, { recursive: true, force: true });
  }
});


test("the actual pi --print CLI loads the reporter and reports its persisted completion offline", { timeout: 30000 }, async () => {
  const root = await mkdtemp(join(tmpdir(), "odk-print-"));
  const peers = new Set(), records = [];
  const server = net.createServer(socket => {
    peers.add(socket); socket.on("close", () => peers.delete(socket));
    let pending = "";
    socket.on("data", chunk => {
      pending += chunk.toString(); const lines = pending.split("\n"); pending = lines.pop();
      for (const line of lines) if (line) { const row = JSON.parse(line); records.push(row);
        if (row.type === "sessions") writeFileSync(join(root, "connected.json"), "{}");
        if (row.type === "hello") socket.write('{"v":1,"type":"ack"}\n'); }
    });
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  let child;
  try {
    await writeFile(join(root, "desks.json"), JSON.stringify({ desks: [{ address: `127.0.0.1:${server.address().port}`, token: "synthetic-only" }] }));
    const wrapper = join(root, "fixture.mjs");
    await writeFile(wrapper, `import reporter from ${JSON.stringify(new URL("../index.ts", import.meta.url).href)};
import { createAssistantMessageEventStream } from ${JSON.stringify(import.meta.resolve("@earendil-works/pi-ai"))};
import { writeFileSync, existsSync } from 'node:fs';
globalThis.fetch = async () => { throw Error('offline fixture forbids fetch'); };
export default pi => {
  reporter(pi);
  pi.on('session_start', async () => {
    const deadline=Date.now()+5000;
    while(!existsSync(${JSON.stringify(join(root, "connected.json"))})) {
      if(Date.now()>deadline)throw Error('offline reporter handshake timed out');
      await new Promise(resolve=>setTimeout(resolve,10));
    }
  });
  pi.registerProvider('odk-fixture', { baseUrl:'http://127.0.0.1:1', api:'openai-completions', apiKey:'synthetic-only',
    models:[{id:'fixture',name:'Fixture',reasoning:false,input:['text'],contextWindow:8192,maxTokens:256,
      cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}],
    streamSimple(model) {
      writeFileSync(${JSON.stringify(join(root, "dispatch.json"))}, JSON.stringify({fixtureDispatch:1}), {flag:'wx'});
      const stream=createAssistantMessageEventStream();
      const message={role:'assistant',api:model.api,provider:model.provider,model:model.id,content:[{type:'text',text:'CLI synthetic reply.'}],stopReason:'stop',timestamp:Date.now(),
        usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}};
      queueMicrotask(()=>{stream.push({type:'done',reason:'stop',message});stream.end();});return stream;
    }
  });
};`);
    const env = { ...process.env, HOME: root, PI_CODING_AGENT_DIR: join(root, "agent"),
      XDG_CONFIG_HOME: join(root, "config"), PI_DIRECTORY_SESSIONS_DIR: join(root, "directory"),
      ODK_LINK_DESKS_FILE: join(root, "desks.json"), PI_OFFLINE: "1" };
    for (const key of ["ODK_SESSION_HOST_SOCKET", "ODK_LINK_ADDRESS", "ODK_LINK_TOKEN", "ODK_LINK_CONTROL_TOKEN"]) delete env[key];
    const cli = fileURLToPath(new URL("./bundle/cli.js", import.meta.resolve("@earendil-works/pi-coding-agent")));
    child = spawn(process.execPath, [cli, "--print", "--no-extensions", "--no-mcp", "--no-skills", "--no-prompt-templates", "--no-themes", "--tools", "", "--session-dir", join(root, "sessions"), "--extension", wrapper, "--model", "odk-fixture/fixture", "Synthetic reporter check."], { cwd: root, env, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "", stderr = "";
    child.stdout.on("data", bytes => { stdout += bytes; }); child.stderr.on("data", bytes => { stderr += bytes; });
    const timer = setTimeout(() => child.kill("SIGKILL"), 20000);
    const code = await new Promise((resolve, reject) => { child.once("error", reject); child.once("close", resolve); });
    clearTimeout(timer);
    assert.equal(code, 0, stderr);
    assert.match(stdout, /CLI synthetic reply/);
    assert.deepEqual(JSON.parse(await readFile(join(root, "dispatch.json"), "utf8")), { fixtureDispatch: 1 });
    const completed = records.filter(r => r.type === "events").flatMap(r => r.events).filter(e => e.eventId && e.stopReason === "stop");
    assert.equal(completed.length, 1, JSON.stringify(records.map(r=>({type:r.type,events:r.events}))));
    assert.equal(completed[0].text, "CLI synthetic reply.");
  } finally {
    if (child?.exitCode === null && child.signalCode === null) { child.kill("SIGKILL"); await new Promise(resolve => child.once("close", resolve)); }
    for (const peer of peers) peer.destroy();
    await new Promise(resolve => server.close(resolve));
    await rm(root, { recursive: true, force: true });
  }
});
