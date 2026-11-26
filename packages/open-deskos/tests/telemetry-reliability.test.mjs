import assert from "node:assert/strict";
import { access, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import net from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { readOdkLinkConfig, readOdkLinkConfigs } from "../src/config.ts";
import { createTcpTransport } from "../src/transport.ts";
import { DeskReporter } from "../src/reporter.ts";
import { eventsFromMessage } from "../src/events.ts";
import { selectConsoleDesk } from "../src/desk-set.ts";
import { CurrentSessionReplay } from "../src/session-replay.ts";

const config = { machine: "fixture", host: "127.0.0.1", port: 1, token: "fixture" };

test("only an accepted v1 acknowledgement establishes reporting and silence retries", () => {
  const handshakeTimers = [], retryTimers = [], transports = [];
  const reporter = new DeskReporter({ config,
    schedule(run, delay) { retryTimers.push({ run, delay }); },
    scheduleHandshake(run, delay) { const timer = { run, delay, cancelled: false }; handshakeTimers.push(timer); return () => { timer.cancelled = true; }; },
    createTransport() { let open, record; const transport = { sent: [], closed: 0, send(value) { this.sent.push(value); }, close() { this.closed += 1; }, onOpen(handler) { open = handler; }, onClose() {}, onRecord(handler) { record = handler; }, open() { open(); }, deliver(value) { record(value); } }; transports.push(transport); return transport; },
  });
  reporter.recordSession({ sessionId: "s" });
  reporter.recordEvents("s", [{ kind: "assistant", text: "retained" }]);
  reporter.start(); transports[0].open();
  assert.equal(reporter.snapshot().link, "connecting");
  assert.deepEqual(transports[0].sent.map((record) => record.type), ["hello"]);
  transports[0].deliver({ v: 2, type: "ack" });
  assert.equal(reporter.snapshot().link, "connecting");
  handshakeTimers[0].run();
  assert.equal(reporter.snapshot().link, "offline");
  assert.equal(transports[0].closed, 1);
  assert.equal(retryTimers[0].delay, 1000);
  retryTimers[0].run(); transports[1].open();
  transports[1].deliver({ v: 1, type: "ack", at: 1 });
  assert.equal(reporter.snapshot().link, "connected");
  assert.deepEqual(transports[1].sent.map((record) => record.type), ["hello", "sessions", "events"]);
  assert.equal(handshakeTimers[1].cancelled, true);
  transports[1].deliver({ v: 1, type: "ack", at: 2 });
  assert.equal(transports[1].sent.length, 3, "duplicate ack must not replay again");
  handshakeTimers[1].run();
  assert.equal(reporter.snapshot().link, "connected", "cancelled timeout callback cannot drop accepted transport");
  reporter.stop();
});

test("console selection refuses ambiguous host preferences and accepts bracketed IPv6", () => {
  const configs = [{ ...config, host: "desk", port: 8765 }, { ...config, host: "desk", port: 9876 }];
  assert.equal(selectConsoleDesk(configs, "desk"), null);
  assert.equal(selectConsoleDesk(configs, "desk:9876"), configs[1]);
  const ipv6 = { ...config, host: "::1", port: 8765 };
  assert.equal(selectConsoleDesk([ipv6], "[::1]:8765"), ipv6);
});

test("configuration parses exact decimal ports and bracketed IPv6 endpoints", () => {
  const load = (address) => readOdkLinkConfig({ ODK_LINK_ADDRESS: address, ODK_LINK_TOKEN: "fixture" });
  assert.equal(load("[::1]:8765").host, "::1");
  for (const address of ["host:8765suffix", "host:8765.5", "host:+8765", "http://host:8765", "[::1:8765", "host:0"]) {
    assert.equal(load(address), null, address);
    assert.equal(readOdkLinkConfigs({}, { readFile: () => JSON.stringify([{ address, token: "fixture" }]) }).configs.length, 0);
  }
});

test("plain-string user content preserves pasted Markdown and user byte bounds", () => {
  const text = "# Goal\n\n- first\n- second";
  assert.deepEqual(eventsFromMessage({ role: "user", content: text }), [{ kind: "user", text }]);
  const event = eventsFromMessage({ role: "user", content: "界".repeat(3000) })[0];
  assert.ok(Buffer.byteLength(event.text) <= 8192);
  assert.equal(event.truncated, true);
});

async function tcpFixture(t, options = {}) {
  let peer;
  let onConnection;
  const connected = new Promise((resolve) => { onConnection = resolve; });
  const server = net.createServer((socket) => { peer = socket; onConnection?.(); });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const transport = createTcpTransport({ ...config, port: server.address().port }, options);
  t.after(() => { transport.close(); peer?.destroy(); server.close(); });
  await Promise.all([new Promise((resolve) => transport.onOpen(resolve)), connected]);
  return { peer, transport };
}

test("TCP decoding preserves UTF-8 across packet boundaries and fragmented long records", { timeout: 3000 }, async (t) => {
  const { peer, transport } = await tcpFixture(t);
  const records = [];
  const received = new Promise((resolve) => transport.onRecord((record) => { records.push(record); if (records.length === 2) resolve(); }));
  const first = Buffer.from(JSON.stringify({ type: "ack", text: "界" }) + "\n");
  const split = first.indexOf(Buffer.from("界")) + 1;
  peer.write(first.subarray(0, split));
  await new Promise((resolve) => setTimeout(resolve, 20));
  peer.write(first.subarray(split));
  const second = { text: "x".repeat(6000) };
  const line = JSON.stringify(second) + "\n";
  peer.write(line.slice(0, 5000));
  await new Promise((resolve) => setTimeout(resolve, 20));
  peer.write(line.slice(5000));
  await received;
  assert.deepEqual(records, [{ type: "ack", text: "界" }, second]);
});

test("oversized incoming lines close once instead of parsing a suffix", { timeout: 3000 }, async (t) => {
  const { peer, transport } = await tcpFixture(t);
  const records = [], reasons = [];
  const closed = new Promise((resolve) => transport.onClose((reason) => { reasons.push(reason); resolve(); }));
  transport.onRecord((record) => records.push(record));
  peer.write("x".repeat(1024 * 1024 + 1));
  await closed;
  assert.match(reasons[0], /frame|record/i);
  assert.deepEqual(records, []);
  assert.equal(reasons.length, 1);
});

test("synchronous socket creation failures retry instead of escaping into Pi", () => {
  const timers = [];
  const reporter = new DeskReporter({ config, schedule(run, delay) { timers.push({ run, delay }); }, createTransport() { throw new Error("fixture creation failure"); } });
  assert.doesNotThrow(() => reporter.start());
  assert.equal(reporter.snapshot().link, "offline");
  assert.equal(timers[0].delay, 1000);
  timers[0].run();
  assert.equal(timers[1].delay, 2000);
  reporter.stop();
});

test("synchronous writes close and retry once while retaining replay state", () => {
  const timers = [], transports = [];
  let fail = true;
  const reporter = new DeskReporter({ config, schedule(run) { timers.push(run); }, createTransport() {
    let opened, received;
    const transport = { sent: [], closed: 0, send(record) { if (fail) throw new Error("fixture write failure"); this.sent.push(record); }, close() { this.closed += 1; }, onOpen(handler) { opened = handler; }, onClose() {}, onRecord(handler) { received = handler; }, open() { opened(); received({ v: 1, type: "ack", at: 9000 }); } };
    transports.push(transport); return transport;
  } });
  reporter.recordSession({ sessionId: "s" });
  reporter.recordEvents("s", [{ kind: "assistant", text: "retained" }]);
  reporter.start();
  assert.doesNotThrow(() => transports[0].open());
  assert.equal(transports[0].closed, 1);
  assert.equal(timers.length, 1);
  fail = false;
  timers[0](); transports[1].open();
  assert.deepEqual(transports[1].sent.map((record) => record.type), ["hello", "sessions", "events"]);
  assert.equal(transports[1].sent.at(-1).events[0].text, "retained");
  reporter.stop();
});

test("finalized events publish changed activity without waiting for periodic discovery", () => {
  let open, receive;
  const sent = [];
  const reporter = new DeskReporter({ config, now: () => 9000, createTransport: () => ({
    send(record) { sent.push(record); }, close() {}, onOpen(handler) { open = handler; }, onClose() {}, onRecord(handler) { receive = handler; },
  }) });
  reporter.recordSession({ sessionId: "s" });
  reporter.start(); open(); receive({ v: 1, type: "ack", at: 1 });
  sent.length = 0;
  reporter.recordEvents("s", [{ kind: "assistant", text: "Tests pass.\nDetails." }]);
  assert.deepEqual(sent.map((record) => record.type), ["sessions", "events"]);
  assert.equal(sent[0].sessions[0].activity, "Tests pass.");
  assert.equal(sent[0].sessions[0].updatedAt, 9000);
  reporter.stop();
});

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function restoreEnv(saved) {
  for (const key of Object.keys(process.env)) {
    if (!(key in saved)) delete process.env[key];
  }
  Object.assign(process.env, saved);
}

test("an awaited replay delivers history before later live messages without content deduplication", async () => {
  const old = { kind: "user", text: "old" };
  const live = { kind: "assistant", text: "live" };
  const read = deferred();
  const replay = new CurrentSessionReplay(() => read.promise);
  const delivered = [];
  const start = replay.start("A", "/sessions/A.jsonl", (id, events) => delivered.push({ id, events }));

  read.resolve([old]);
  await start;
  replay.append("A", [old, live], (id, events) => delivered.push({ id, events }));

  assert.deepEqual(delivered.flatMap((batch) => batch.events), [old, old, live]);
});

test("a stale replay cannot cross an A to B to A session switch", async () => {
  const old = { kind: "user", text: "old" };
  const live = { kind: "assistant", text: "live" };
  const reads = [];
  const replay = new CurrentSessionReplay((file) => {
    const next = deferred();
    reads.push({ file, ...next });
    return next.promise;
  });
  const delivered = [];

  const oldStart = replay.start("A", "/sessions/A-old.jsonl", (id, events) => delivered.push({ id, events }));
  replay.invalidate();
  const currentStart = replay.start("A", "/sessions/A-current.jsonl", (id, events) => delivered.push({ id, events }));
  await new Promise((resolve) => setImmediate(resolve));

  reads[0].resolve([old]);
  await oldStart;
  assert.deepEqual(delivered, [], "the old A tail must not revive after B ran");

  reads[1].resolve([live]);
  await currentStart;
  assert.deepEqual(delivered, [{ id: "A", events: [live] }]);
});

async function lifecycleFixture(t, reporting = false) {
  const sessionId = "11111111-1111-4111-8111-111111111111";
  const root = await mkdtemp(join(tmpdir(), "odk-life-"));
  const saved = { ...process.env };
  const server = net.createServer((socket) => {
    socket.on("error", () => {});
    socket.on("data", () => socket.write(`${JSON.stringify({ v: 1, type: "ack" })}\n`));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  await mkdir(join(root, "project"));
  const desks = reporting ? [{ address: `127.0.0.1:${server.address().port}`, token: "fixture" }] : [];
  await writeFile(join(root, "desks.json"), JSON.stringify({ desks }));
  await writeFile(join(root, "history.jsonl"), `${JSON.stringify({ type: "message", message: { role: "user", content: "history" } })}\n`);
  process.env.ODK_LINK_DESKS_FILE = join(root, "desks.json");
  process.env.ODK_SESSION_HOST_SOCKET = join(root, "run");
  process.env.PI_DIRECTORY_SESSIONS_DIR = join(root, "registry");
  const { default: extension } = await import("../index.ts");
  const handlers = new Map();
  extension({ on(name, fn) { handlers.set(name, fn); }, registerCommand() {}, registerMessageRenderer() {}, registerEntryRenderer() {}, registerTool() {} });
  const ctx = {
    cwd: join(root, "project"),
    isIdle: () => true,
    sessionManager: {
      getSessionId: () => sessionId,
      getSessionName: () => undefined,
      getHeader: () => undefined,
      getSessionFile: () => join(root, "history.jsonl"),
    },
  };
  t.after(async () => {
    await handlers.get("session_shutdown")?.({}, ctx);
    server.closeAllConnections?.();
    server.close();
    restoreEnv(saved);
    await rm(root, { recursive: true, force: true });
  });
  return { handlers, ctx, descriptor: join(root, "run", `${sessionId}.json`) };
}

test("an explicit current-session endpoint works independently of reporting credentials", async (t) => {
  const f = await lifecycleFixture(t);
  assert.equal(typeof f.handlers.get("session_start"), "function", "the declared host has lifecycle handlers");
  await f.handlers.get("session_start")({ reason: "startup" }, f.ctx);
  await access(f.descriptor);
  await f.handlers.get("session_shutdown")({}, f.ctx);
  await assert.rejects(access(f.descriptor), { code: "ENOENT" });
});

test("a pending durable replay cannot recreate the endpoint after shutdown", async (t) => {
  const f = await lifecycleFixture(t, true);
  const startup = f.handlers.get("session_start")({ reason: "resume" }, f.ctx);
  await f.handlers.get("session_shutdown")({}, f.ctx);
  await startup;
  await assert.rejects(access(f.descriptor), { code: "ENOENT" });
});

async function waitForActivity(condition, ms = 8000) {
  const deadline = Date.now() + ms;
  while (!condition()) {
    assert.ok(Date.now() < deadline, "the desk never received the activity");
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

async function activityDesk(t) {
  const root = await mkdtemp(join(tmpdir(), "desk-activity-"));
  const sockets = [], records = [];
  const server = net.createServer((socket) => {
    sockets.push(socket);
    let pending = "";
    socket.on("data", (chunk) => {
      pending += chunk.toString("utf8");
      const lines = pending.split("\n");
      pending = lines.pop();
      for (const line of lines) if (line) {
        const record = JSON.parse(line);
        records.push(record);
        if (record.type === "hello") socket.write(JSON.stringify({ v: 1, type: "ack", at: Date.now() }) + "\n");
      }
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const saved = { ...process.env };
  await writeFile(join(root, "desks.json"), JSON.stringify({ desks: [{ address: `127.0.0.1:${server.address().port}`, token: "isolated-fixture" }] }));
  delete process.env.ODK_LINK_CONTROL_TOKEN;
  delete process.env.ODK_SESSION_HOST_SOCKET;
  process.env.ODK_LINK_DESKS_FILE = join(root, "desks.json");
  process.env.ODK_LINK_ADDRESS = `127.0.0.1:${server.address().port}`;
  process.env.ODK_LINK_TOKEN = "isolated-fixture";
  process.env.ODK_LINK_MACHINE = "isolated-machine";
  process.env.PI_DIRECTORY_SESSIONS_DIR = root;
  const ownId = "a1234567-1234-1234-1234-123456789abc";
  const { default: extension } = await import("../index.ts");
  const handlers = new Map();
  extension({ on(name, fn) { handlers.set(name, fn); }, registerCommand() {}, registerMessageRenderer() {}, registerEntryRenderer() {}, registerTool() {} });
  const ctx = {
    cwd: "/fixture/current",
    isIdle: () => false,
    sessionManager: { getSessionId: () => ownId, getSessionName: () => undefined, getHeader: () => undefined, getSessionFile: () => undefined, getBranch: () => [] },
  };
  t.after(async () => {
    await handlers.get("session_shutdown")?.({}, ctx);
    for (const socket of sockets) socket.destroy();
    server.close();
    restoreEnv(saved);
    await rm(root, { recursive: true, force: true });
  });
  await handlers.get("session_start")({ reason: "startup" }, ctx);
  await waitForActivity(() => records.some((record) => record.type === "hello"));
  return { handlers, ctx, records };
}

const activities = (records) => records.flatMap((record) => record.sessions ?? []).map((session) => session.activity).filter(Boolean);

test("the card's activity becomes the tool that is running now", async (t) => {
  const { handlers, ctx, records } = await activityDesk(t);
  await handlers.get("tool_execution_start")({ toolCallId: "t1", toolName: "bash", args: { command: "bun test" } }, ctx);
  await waitForActivity(() => activities(records).includes("bash: bun test"));

  await handlers.get("tool_execution_start")({ toolCallId: "t2", toolName: "read", args: { path: "src/example.js" } }, ctx);
  await waitForActivity(() => activities(records).includes("read: src/example.js"));

  await handlers.get("tool_execution_start")({ toolCallId: "t3", toolName: "webfetch", args: { url: "https://example.com/very/long/path" } }, ctx);
  await waitForActivity(() => activities(records).some((activity) => activity.startsWith("webfetch")));

  const newest = activities(records).at(-1);
  assert.ok(newest.length <= 200, `the activity stays a short summary, saw ${newest.length} characters`);
  assert.equal(newest.includes("\n"), false, "and stays one line");
});

test("a finished tool is replaced by the message that follows it", async (t) => {
  const { handlers, ctx, records } = await activityDesk(t);
  await handlers.get("tool_execution_start")({ toolCallId: "t1", toolName: "bash", args: { command: "bun test" } }, ctx);
  await waitForActivity(() => activities(records).includes("bash: bun test"));

  await handlers.get("message_end")({ message: { role: "assistant", content: [{ type: "text", text: "Tests pass." }] } }, ctx);
  await waitForActivity(() => activities(records).includes("Tests pass."));
});
