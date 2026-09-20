import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, readFile, readdir, symlink, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { DeskReporter, MAX_SESSIONS_PER_MACHINE } from "../src/reporter.ts";

// Dynamic import keeps the baseline regression failure an assertion, not a loader error.
async function discovery() {
  const module = await import("../src/discovery.ts").catch(() => null);
  assert.ok(module, "machine-wide metadata discovery is missing");
  return module;
}

async function registry(t) {
  const root = await mkdtemp(join(tmpdir(), "desk-metadata-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  async function put(workspace, file, value) {
    const dir = join(root, workspace);
    await mkdir(dir, { recursive: true });
    await writeFile(join(dir, file), typeof value === "string" ? value : JSON.stringify(value));
  }
  return { root, put };
}

const config = { machine: "fixture", host: "127.0.0.1", port: 1, token: "fixture-only" };
function reporterHarness() {
  const transports = [], timers = [];
  const reporter = new DeskReporter({
    config,
    now: () => 9000,
    schedule(run) { timers.push(run); },
    createTransport() {
      let open, close;
      const sent = [];
      const transport = {
        sent,
        open() { open?.(); },
        drop() { close?.("fixture drop"); },
        send(record) { sent.push(record); },
        close() { close?.("fixture close"); },
        onOpen(handler) { open = handler; },
        onClose(handler) { close = handler; },
        onRecord() {},
      };
      transports.push(transport);
      return transport;
    },
  });
  return { reporter, transports, timers, latest: () => transports.at(-1).sent.filter((r) => r.type === "sessions").at(-1).sessions };
}

function session(sessionId, status = "settled", updatedAt = 10) {
  return { sessionId, status, cwd: "/fixture/work", workspaceName: "work", startedAt: 1, updatedAt };
}
const tick = () => new Promise((resolve) => setImmediate(resolve));
// Synthetic Pi process identities keep metadata unit tests off the host process table.
const fixtureProcesses = async () => Array.from({ length: 3000 }, (_, i) => ({ pid: i + 1, startedAt: 1 }));

// Given multiple old registry states, when scanned, then only live working records run.
test("discovers all metadata states across workspaces using original timestamps", async (t) => {
  const { scanDirectorySessions } = await discovery();
  const { root, put } = await registry(t);
  const states = ["running", "idle", "settled", "exited", "error", "need_approval"];
  for (const [index, status] of states.entries()) {
    await put(`workspace-${index}`, `${status}.json`, { sessionId: status, pid: 100 + index, cwd: "/fixture/one", status, startedAt: 12, updatedAt: 34 });
  }
  await put("workspace-other", "dead.json", { sessionId: "dead", pid: 900, status: "running", updatedAt: 55 });
  await put("workspace-other", "invalid-pid.json", { sessionId: "invalid-pid", pid: -1, status: "running", updatedAt: 56 });
  const checked = [];
  const sessions = await scanDirectorySessions({ registryDir: root, listProcesses: fixtureProcesses, checkProcessAlive: (pid) => { checked.push(pid); return pid < 900; } });
  assert.equal(sessions.length, 8);
  const byId = new Map(sessions.map((s) => [s.sessionId, s]));
  assert.equal(byId.get("running").status, "running");
  for (const id of ["idle", "settled", "error", "need_approval"]) assert.equal(byId.get(id).status, "settled");
  for (const id of ["dead", "invalid-pid", "exited"]) assert.equal(byId.get(id).status, "exited");
  assert.equal(byId.get("running").startedAt, 12);
  assert.equal(byId.get("running").updatedAt, 34);
  assert.ok(checked.every((pid) => pid > 0));
  assert.equal(JSON.parse(await readFile(join(root, "workspace-other/dead.json"), "utf8")).status, "running", "discovery is read-only");
});

test("default PID check detects a real terminated process without promoting explicit exits", async (t) => {
  const { spawn } = await import("node:child_process");
  const { once } = await import("node:events");
  const { scanDirectorySessions } = await discovery();
  const { root, put } = await registry(t);
  const child = spawn(process.execPath, ["-e", ""], { stdio: "ignore" });
  const pid = child.pid;
  await once(child, "exit");
  await put("w", "dead.json", { sessionId: "dead", pid, status: "running", updatedAt: 1 });
  await put("w", "own.json", { sessionId: "own", pid: process.pid, status: "idle", updatedAt: 2 });
  assert.deepEqual((await scanDirectorySessions({ registryDir: root })).map((s) => [s.sessionId, s.status]), [["own", "exited"], ["dead", "exited"]]);
});

test("merges UUID aliases and partial fields, preserves old sessions of one live PID as exited", async (t) => {
  const { scanDirectorySessions } = await discovery();
  const { root, put } = await registry(t);
  const id = "a1234567-1234-1234-1234-123456789abc";
  await put("w1", `${id}.json`, { sessionId: id, pid: "80", cwd: "/fixture/project", sessionName: "Long name", status: "running", startedAt: 2, updatedAt: 4, latestGoal: "goal", recap: "recap" });
  await put("w2", `alias.json`, { sessionId: `2026-01-01T00-00-00_${id}`, status: "idle", updatedAt: "5", activity: "new activity" });
  await put("w2", "old-process-session.json", { sessionId: "older", pid: 80, status: "running", startedAt: 1, updatedAt: 1 });
  await put("w2", "partial.json", { name: "Only name", status: "running" });
  const sessions = await scanDirectorySessions({ registryDir: root, listProcesses: fixtureProcesses, checkProcessAlive: () => true });
  assert.equal(sessions.length, 3);
  const merged = sessions.find((s) => s.sessionId === id);
  assert.deepEqual(merged, { sessionId: id, name: "Long name", cwd: "/fixture/project", workspaceName: "project", status: "settled", startedAt: 2, updatedAt: 5, latestGoal: "goal", activity: "new activity" });
  assert.equal(sessions.find((s) => s.sessionId === "older").status, "exited");
  const partial = sessions.find((s) => s.sessionId === "partial");
  assert.deepEqual([partial.startedAt, partial.updatedAt, partial.cwd, partial.name, partial.status], [0, 0, "", "Only name", "exited"]);
});

test("long workspace paths remain exact and distinct instead of collapsing after character 200", async (t) => {
  const { scanDirectorySessions } = await discovery();
  const { root, put } = await registry(t);
  const prefix = `/fixture/${"segment/".repeat(35)}`;
  for (const id of ["a", "b"]) await put("w", `${id}.json`, { sessionId: id, cwd: `${prefix}${id}`, pid: 0 });
  const sessions = await scanDirectorySessions({ registryDir: root });
  assert.deepEqual(sessions.map((s) => [s.cwd, s.workspaceName]), [[`${prefix}a`, "a"], [`${prefix}b`, "b"]]);
});

test("PID reuse never promotes stale metadata, and process snapshots are read just once", async (t) => {
  const { scanDirectorySessions } = await discovery();
  const { root, put } = await registry(t);
  for (const [id, pid, updatedAt] of [["not-pi", 1, 10000], ["reused-pi", 2, 100], ["current-pi", 3, 21000], ["missing-times", 4, 0]]) {
    await put("w", `${id}.json`, { sessionId: id, pid, status: "running", updatedAt });
  }
  let snapshots = 0;
  const sessions = await scanDirectorySessions({
    registryDir: root, checkProcessAlive: () => true,
    listProcesses: async () => { snapshots += 1; return [{ pid: 2, startedAt: 20000 }, { pid: 3, startedAt: 20000 }, { pid: 4, startedAt: 20000 }]; },
  });
  assert.equal(snapshots, 1);
  const statuses = Object.fromEntries(sessions.map((s) => [s.sessionId, s.status]));
  assert.deepEqual(statuses, { "current-pi": "running", "not-pi": "exited", "reused-pi": "exited", "missing-times": "exited" });
});

test("process parser recognizes Pi titles and launchers but never a command merely mentioning pi", async () => {
  const { parsePiProcesses } = await discovery();
  assert.equal(typeof parsePiProcesses, "function");
  const processes = parsePiProcesses([
    "10 60 S pi pi", "11 60 S node node /opt/pi/dist/cli.js", "12 60 S node node /opt/node_modules/@earendil-works/pi-coding-agent/dist/rpc-entry.js",
    "13 60 S bash bash -c echo pi", "14 60 S node node app.js pi", "15 01:00 S pi-rpc pi-rpc", "16 1-00:00:00 S pi pi",
    "17 60 Z pi pi", "18 60 X pi pi", "19 60 Z+ pi-rpc pi-rpc",
  ].join("\n"), 100000000);
  assert.deepEqual(processes.map((p) => p.pid), [10, 12, 15, 16]);
  assert.equal(processes[0].startedAt, 99940000);
});

test("default process snapshot never revives a real non-Pi process from stale metadata", async (t) => {
  const { scanDirectorySessions } = await discovery();
  const { root, put } = await registry(t);
  await put("w", "stale.json", { sessionId: "stale", pid: process.pid, status: "running", updatedAt: Date.now() });
  assert.equal((await scanDirectorySessions({ registryDir: root }))[0].status, "exited");
});

test("invalid surrogate identities are rejected without truncating valid identities", async (t) => {
  const { scanDirectorySessions } = await discovery();
  const { root, put } = await registry(t);
  await put("w", "bad.json", { sessionId: `bad${String.fromCharCode(0xd800)}`, status: "running" });
  assert.deepEqual(await scanDirectorySessions({ registryDir: root }), []);
});

test("never treats two equally recent sessions of one PID as unambiguously running", async (t) => {
  const { scanDirectorySessions } = await discovery();
  const { root, put } = await registry(t);
  for (const id of ["a", "b"]) await put("w", `${id}.json`, { sessionId: id, pid: 42, status: "running", updatedAt: 3 });
  assert.ok((await scanDirectorySessions({ registryDir: root, listProcesses: fixtureProcesses, checkProcessAlive: () => true })).every((s) => s.status === "exited"));
});

test("skips malformed, oversized, linked and non-regular metadata without exposing extra fields", async (t) => {
  const { scanDirectorySessions, MAX_METADATA_BYTES } = await discovery();
  const { root, put } = await registry(t);
  await put("w", "good.json", { sessionId: "good", pid: 42, status: "running", updatedAt: 1, name: "n".repeat(500), latestGoal: "g".repeat(500) + "\nignored", recap: "first line\nnot a transcript", sessionFile: "/never/read/history.jsonl", auth: "fixture-private-field" });
  for (const [name, value] of [["bad.json", "{"], ["null.json", "null"], ["array.json", "[]"], ["big.json", " ".repeat(MAX_METADATA_BYTES + 1)], ["ignored.jsonl", "not metadata"]]) await put("w", name, value);
  await mkdir(join(root, "w/not-a-file.json"));
  await symlink(join(root, "w/good.json"), join(root, "w/link.json"));
  await symlink(join(root, "w"), join(root, "linked-workspace"));
  const sessions = await scanDirectorySessions({ registryDir: root, listProcesses: fixtureProcesses, checkProcessAlive: () => true });
  assert.equal(sessions.length, 1);
  assert.equal(sessions[0].name.length, 200);
  assert.equal(sessions[0].latestGoal.length, 200);
  assert.equal(sessions[0].activity, "first line");
  assert.ok(!JSON.stringify(sessions).includes("fixture-private-field"));
  assert.ok(!JSON.stringify(sessions).includes("history.jsonl"));
  assert.equal((await readdir(join(root, "w"))).length, 8, "no registry cleanup writes");
  assert.deepEqual(await scanDirectorySessions({ registryDir: join(root, "missing") }), []);
});

test("bounds scanned entries and prioritizes running then recent sessions within the 64 cap", async (t) => {
  const { scanDirectorySessions, MAX_SCAN_ENTRIES, MAX_METADATA_FILES, MAX_WORKSPACES } = await discovery();
  assert.ok(MAX_SCAN_ENTRIES > 0 && MAX_SCAN_ENTRIES <= 8192);
  assert.ok(MAX_METADATA_FILES > 0 && MAX_METADATA_FILES <= 2048);
  assert.ok(MAX_WORKSPACES > 0 && MAX_WORKSPACES <= 256);
  const { root, put } = await registry(t);
  for (let index = 0; index < 90; index += 1) await put("w", `${index}.json`, { sessionId: `s${index}`, pid: index + 1, status: index === 0 ? "running" : "idle", updatedAt: index + 1 });
  const sessions = await scanDirectorySessions({ registryDir: root, listProcesses: fixtureProcesses, checkProcessAlive: () => true });
  assert.equal(sessions.length, MAX_SESSIONS_PER_MACHINE);
  assert.equal(sessions[0].sessionId, "s0");
  assert.equal(sessions[1].sessionId, "s89");
  assert.ok(!sessions.some((s) => s.sessionId === "s1"));
});

test("metadata file and workspace traversal budgets stop reads before unbounded inventories", async (t) => {
  const { scanDirectorySessions, MAX_METADATA_FILES, MAX_WORKSPACES } = await discovery();
  for (const [limit, grouped] of [[MAX_METADATA_FILES, true], [MAX_WORKSPACES, false]]) {
    const { root, put } = await registry(t);
    for (let index = 0; index < limit + 3; index += 1) {
      await put(grouped ? "w" : `w${index}`, `${index}.json`, { sessionId: `s${index}`, pid: index + 1, status: "running", updatedAt: 1 });
    }
    let checked = 0;
    const sessions = await scanDirectorySessions({ registryDir: root, listProcesses: fixtureProcesses, checkProcessAlive: () => { checked += 1; return true; } });
    assert.equal(checked, limit);
    assert.equal(sessions.length, 64);
  }
});

test("discovery honors explicit registry and official agent-directory overrides", async () => {
  const { directorySessionsPath } = await discovery();
  assert.equal(directorySessionsPath({ PI_DIRECTORY_SESSIONS_DIR: "/fixture/direct", PI_CODING_AGENT_DIR: "/fixture/agent" }), "/fixture/direct");
  assert.equal(directorySessionsPath({ PI_CODING_AGENT_DIR: "/fixture/agent" }), "/fixture/agent/directory-sessions");
  assert.equal(directorySessionsPath({ PI_AGENT_DIR: "/fixture/legacy" }), "/fixture/legacy/directory-sessions");
});

test("discovered replacements retain live identity, status, events, and current session under pressure", () => {
  const { reporter, transports, latest } = reporterHarness();
  const id = "a1234567-1234-1234-1234-123456789abc";
  reporter.recordSession({ sessionId: id, name: "Live", cwd: "/live", workspaceName: "live", status: "settled", startedAt: 7, latestGoal: "live goal" });
  reporter.recordEvents(id, Array.from({ length: 80 }, (_, i) => ({ kind: "tool", text: `live ${i}` })));
  reporter.start();
  transports[0].open();
  assert.equal(typeof reporter.replaceDiscoveredSessions, "function", "reporter cannot replace discovered snapshots");
  const discovered = Array.from({ length: 90 }, (_, i) => session(`s${i}`, "running", 10000 + i));
  discovered.push({ ...session(`2026-01-01_${id}`, "exited", 9999999), name: "stale alias" });
  reporter.replaceDiscoveredSessions(discovered);
  assert.equal(reporter.snapshot().sessions, 64);
  const live = latest().find((s) => s.sessionId === id);
  assert.deepEqual([live.name, live.status, live.cwd, live.startedAt, live.latestGoal, live.updatedAt], ["Live", "settled", "/live", 7, "live goal", 9000]);
  assert.equal(reporter.eventsFor(id).length, 80);
  assert.ok(!latest().some((s) => s.sessionId.includes("2026-01-01_")));
  reporter.replaceDiscoveredSessions([session("s89", "exited", 88)]);
  assert.equal(reporter.snapshot().sessions, 2);
  assert.equal(latest().find((s) => s.sessionId === "s89").updatedAt, 88);
  reporter.replaceDiscoveredSessions([]);
  assert.deepEqual(latest().map((s) => s.sessionId), [id]);
  assert.equal(reporter.eventsFor(id).at(-1).text, "live 79");
  reporter.stop();
});

test("55 and 64 session snapshots with multi-byte metadata fit the complete LF record budget", () => {
  const sizes = [];
  for (const count of [55, 64]) {
    const { reporter, transports } = reporterHarness();
    const own = { sessionId: "own", name: "Live name", cwd: "/live/current", workspaceName: "current", status: "settled", startedAt: 5 };
    reporter.recordSession(own);
    reporter.start(); transports[0].open();
    const records = Array.from({ length: count - 1 }, (_, i) => ({
      ...session(`${"界".repeat(70)}-${i}`, "running", i + 1),
      name: "界".repeat(200), cwd: `/fixture/${"界".repeat(60)}/w${i}`, workspaceName: `w${i}`,
      latestGoal: "界".repeat(200), activity: "界".repeat(200),
    }));
    reporter.replaceDiscoveredSessions(records);
    const wire = transports[0].sent.filter((r) => r.type === "sessions").at(-1);
    const bytes = Buffer.byteLength(`${JSON.stringify(wire)}\n`);
    assert.ok(bytes <= 65536, `${count} sessions exceeds frame limit: ${bytes}`);
    assert.equal(wire.sessions.length, count);
    assert.deepEqual(wire.sessions.find((s) => s.sessionId === "own"), { ...own, updatedAt: 9000 });
    for (const expected of records) {
      const actual = wire.sessions.find((s) => s.sessionId === expected.sessionId);
      assert.ok(actual, "identity is never shortened");
      assert.equal(actual.startedAt, expected.startedAt);
      assert.equal(actual.updatedAt, expected.updatedAt);
      assert.equal(actual.cwd, expected.cwd, "workspace identity is never shortened");
      assert.equal(actual.workspaceName, expected.workspaceName);
    }
    sizes.push({ sessions: count, bytes });
    reporter.stop();
  }
  console.log(`synthetic-snapshot-bytes ${JSON.stringify(sizes)}`);
});

test("oversized identity-only inventories omit whole low-priority records and diagnose the count", () => {
  const { reporter, transports, latest } = reporterHarness();
  reporter.recordSession({ sessionId: "current", status: "settled", cwd: "/current" });
  reporter.start(); transports[0].open();
  const inventory = Array.from({ length: 63 }, (_, i) => ({ ...session(`long-${i}`, i < 30 ? "running" : "exited", i + 1), cwd: `/${"x".repeat(1100)}/${i}`, workspaceName: `${i}` }));
  reporter.replaceDiscoveredSessions(inventory);
  const wire = transports[0].sent.filter((r) => r.type === "sessions").at(-1);
  assert.ok(Buffer.byteLength(`${JSON.stringify(wire)}\n`) <= 65536);
  assert.ok(latest().some((s) => s.sessionId === "current"));
  assert.equal(reporter.snapshot().omittedSessions, 64 - latest().length);
  assert.ok(reporter.snapshot().omittedSessions > 0);
  for (const actual of latest().filter((s) => s.sessionId !== "current")) assert.equal(actual.cwd, inventory.find((s) => s.sessionId === actual.sessionId).cwd);
  assert.equal(latest().filter((s) => s.status === "running").length, 30);
  reporter.replaceDiscoveredSessions([]);
  assert.equal(reporter.snapshot().omittedSessions, 0);
  reporter.stop();
});

test("observed exited history cannot crowd out running discovery at the cap", () => {
  const { reporter, transports, latest } = reporterHarness();
  for (let i = 0; i < 64; i += 1) reporter.recordSession({ sessionId: `old-${i}`, status: "exited" });
  reporter.recordSession({ sessionId: "current", status: "settled" });
  reporter.start(); transports[0].open();
  reporter.replaceDiscoveredSessions(Array.from({ length: 63 }, (_, i) => session(`work-${i}`, "running", i + 1)));
  assert.equal(latest().length, 64);
  assert.equal(latest().filter((s) => s.status === "running").length, 63);
  assert.ok(latest().some((s) => s.sessionId === "current"));
  reporter.stop();
});

test("wire provenance distinguishes inventory from the authoritative current reporter", () => {
  const { reporter, transports, latest } = reporterHarness();
  reporter.recordSession({ sessionId: "current", status: "running" });
  reporter.start(); transports[0].open();
  reporter.replaceDiscoveredSessions([session("found", "running")]);
  assert.equal(latest().find((s) => s.sessionId === "found").discovered, true);
  assert.notEqual(latest().find((s) => s.sessionId === "current").discovered, true);
  reporter.recordSession({ sessionId: "found", status: "settled" });
  assert.notEqual(latest().find((s) => s.sessionId === "found").discovered, true);
  reporter.stop();
});

test("formerly observed exited sessions may resume elsewhere without losing their events", () => {
  const { reporter, transports, latest } = reporterHarness();
  reporter.recordSession({ sessionId: "old", status: "running" });
  reporter.recordEvents("old", [{ kind: "assistant", text: "retained" }]);
  reporter.markStatus("old", "exited");
  reporter.recordSession({ sessionId: "current", status: "settled" });
  reporter.start(); transports[0].open();
  reporter.replaceDiscoveredSessions([{ ...session("old", "running", 10000), name: "resumed elsewhere" }]);
  assert.equal(latest().find((s) => s.sessionId === "old").status, "running");
  assert.equal(latest().find((s) => s.sessionId === "old").name, "resumed elsewhere");
  assert.equal(latest().find((s) => s.sessionId === "old").discovered, true);
  assert.equal(reporter.eventsFor("old")[0].text, "retained");
  reporter.replaceDiscoveredSessions([]);
  assert.ok(latest().some((s) => s.sessionId === "old"), "observed history is retained");
  assert.equal(latest().find((s) => s.sessionId === "old").status, "exited");
  assert.equal(latest().find((s) => s.sessionId === "old").updatedAt, 10000);
  assert.equal(reporter.eventsFor("old")[0].text, "retained");
  reporter.stop();
});

test("a discovered session promoted to live is never removed by refresh", () => {
  const { reporter, transports, latest } = reporterHarness();
  reporter.start();
  transports[0].open();
  assert.equal(typeof reporter.replaceDiscoveredSessions, "function");
  reporter.replaceDiscoveredSessions([session("resumed")]);
  reporter.recordSession({ sessionId: "resumed", status: "running", name: "resumed live" });
  reporter.recordEvents("resumed", [{ kind: "assistant", text: "observed" }]);
  reporter.replaceDiscoveredSessions([]);
  assert.equal(latest()[0].name, "resumed live");
  assert.equal(reporter.eventsFor("resumed").length, 1);
  reporter.stop();
});

test("refresh is non-overlapping, ignores stopped results, cancels timers and restarts once", async () => {
  const { SessionDiscovery, DISCOVERY_INTERVAL_MS } = await discovery();
  const results = [], timers = [];
  let resolveScan, calls = 0;
  const refresh = new SessionDiscovery({
    discover: () => { calls += 1; return new Promise((resolve) => { resolveScan = resolve; }); },
    onSnapshot: (sessions) => results.push(sessions),
    schedule(run, delay) { const timer = { run, delay, cancelled: false }; timers.push(timer); return () => { timer.cancelled = true; }; },
  });
  assert.equal(calls, 0, "constructing an extension must not start resources");
  refresh.start(); refresh.start();
  assert.equal(calls, 1);
  resolveScan([session("one")]);
  await tick();
  assert.equal(timers[0].delay, DISCOVERY_INTERVAL_MS);
  timers[0].run();
  assert.equal(calls, 2);
  refresh.stop(); refresh.stop(); refresh.start();
  assert.equal(calls, 2, "the old in-flight scan is still the only scan");
  resolveScan([session("stale")]);
  await tick();
  assert.deepEqual(results.map((r) => r[0].sessionId), ["one"]);
  timers.at(-1).run();
  assert.equal(calls, 3);
  resolveScan([session("new")]);
  await tick();
  assert.deepEqual(results.map((r) => r[0].sessionId), ["one", "new"]);
  refresh.stop();
  assert.equal(timers.at(-1).cancelled, true);
  timers.at(-1).run();
  assert.equal(calls, 3);
});

test("rejected refreshes are handled and a later periodic scan recovers", async () => {
  const { SessionDiscovery } = await discovery();
  const timers = [], snapshots = [];
  let calls = 0;
  const refresh = new SessionDiscovery({
    discover: async () => { if (++calls === 1) throw new Error("fixture unreadable"); return []; },
    onSnapshot: (s) => snapshots.push(s),
    schedule(run) { timers.push(run); return () => {}; },
  });
  refresh.start();
  await tick();
  assert.equal(timers.length, 1);
  timers[0]();
  await tick();
  assert.deepEqual(snapshots, [[]]);
  refresh.stop();
});

test("disconnect and stop invalidate stale reconnect and socket callbacks", () => {
  const { reporter, transports, timers } = reporterHarness();
  reporter.start(); transports[0].open(); transports[0].drop();
  reporter.disconnect();
  timers[0]();
  assert.equal(transports.length, 1, "shutdown must not reconnect behind the next session");
  reporter.start();
  transports[0].open();
  assert.equal(reporter.snapshot().link, "connecting", "old socket callbacks are invalidated");
  transports[1].open(); transports[1].drop(); reporter.stop();
  timers.at(-1)();
  assert.equal(transports.length, 2, "stop must invalidate pending reconnect callbacks");
});
