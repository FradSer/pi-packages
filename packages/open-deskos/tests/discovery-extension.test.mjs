import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile, unlink } from "node:fs/promises";
import net from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

async function waitFor(condition, ms = 8000) {
  const deadline = Date.now() + ms;
  while (!condition()) {
    assert.ok(Date.now() < deadline, "isolated extension transition timed out");
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

test("extension discovers older sessions, periodically refreshes, preserves own events and cleans up", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "desk-extension-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(join(root, "fixture"));
  const peers = [], records = [];
  const server = net.createServer((socket) => {
    peers.push(socket);
    let pending = "";
    socket.on("data", (chunk) => {
      pending += chunk.toString("utf8");
      const lines = pending.split("\n");
      pending = lines.pop();
      for (const line of lines) if (line) records.push(JSON.parse(line));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const saved = { ...process.env };
  process.env.ODK_DESK_LINK_ADDRESS = `127.0.0.1:${server.address().port}`;
  process.env.ODK_DESK_LINK_TOKEN = "isolated-fixture";
  process.env.ODK_DESK_LINK_MACHINE = "isolated-machine";
  process.env.PI_DIRECTORY_SESSIONS_DIR = root;
  const ownId = "a1234567-1234-1234-1234-123456789abc";
  const ownAlias = `2026-01-01T00-00-00_${ownId}`;
  const put = (id, record) => writeFile(join(root, "fixture", `${id}.json`), JSON.stringify(record));
  await put(ownAlias, { sessionId: ownAlias, pid: process.pid, status: "running", updatedAt: 200, sessionName: "stale alias" });
  for (let i = 0; i < 10; i += 1) await put(`old-${i}`, { sessionId: `old-${i}`, pid: 0, status: "running", startedAt: 1, updatedAt: 2 });
  const { default: extension } = await import("../index.ts");
  const handlers = new Map();
  extension({ on(name, fn) { handlers.set(name, fn); }, registerCommand() {} });
  const ctx = {
    cwd: "/fixture/current",
    isIdle: () => true,
    sessionManager: {
      getSessionId: () => ownId,
      getSessionName: () => "Live name",
      getHeader: () => ({ timestamp: "2020-01-01T00:00:00Z" }),
      getBranch: () => [
        { type: "message", message: { role: "user", content: "historical prompt" } },
        { type: "message", message: { role: "assistant", content: [{ type: "text", text: "historical reply" }] } },
      ],
    },
  };
  const latest = () => records.filter((r) => r.type === "sessions").at(-1)?.sessions ?? [];
  try {
    assert.equal(peers.length, 0, "extension factory is inert");
    handlers.get("session_start")({ reason: "resume" }, ctx);
    await waitFor(() => latest().length === 11);
    const own = latest().find((s) => s.sessionId === ownId);
    await waitFor(() => records.some((record) => record.type === "events" && record.sessionId === ownId));
    const historical = records.find((record) => record.type === "events" && record.sessionId === ownId)?.events ?? [];
    assert.deepEqual(historical.map((event) => [event.kind, event.text]), [
      ["user", "historical prompt"],
      ["assistant", "historical reply"],
    ]);
    assert.equal(own.status, "settled", "idle Pi starts settled, not working");
    assert.equal(own.name, "Live name");
    assert.equal(own.startedAt, Date.parse("2020-01-01T00:00:00Z"));
    assert.ok(latest().filter((s) => s.sessionId !== ownId).every((s) => s.status === "exited" && s.updatedAt === 2));
    handlers.get("agent_start")({}, ctx);
    handlers.get("message_end")({ message: { role: "user", content: "synthetic current goal" } }, ctx);
    handlers.get("agent_settled")({}, ctx);
    await unlink(join(root, "fixture", "old-0.json"));
    await put("later", { sessionId: "later", pid: 0, status: "running", updatedAt: 8 });
    await waitFor(() => latest().some((s) => s.sessionId === "later"));
    assert.ok(!latest().some((s) => s.sessionId === "old-0"));
    assert.equal(latest().find((s) => s.sessionId === ownId).latestGoal, "synthetic current goal");
    await waitFor(() => records.filter((record) => record.type === "events" && record.sessionId === ownId).length === 2);
    assert.deepEqual(records.filter((record) => record.type === "events" && record.sessionId === ownId).at(-1)?.events,
      [{ kind: "user", text: "synthetic current goal" }]);
    handlers.get("session_shutdown")({}, ctx);
    await waitFor(() => peers[0].destroyed);
    const count = records.length;
    await new Promise((resolve) => setTimeout(resolve, 200));
    assert.equal(records.length, count);
    assert.equal(peers.length, 1, "shutdown did not reconnect");

    // Fork is a distinct session_start reason with an already-populated branch.
    // It must replay that branch just like resume, without relying on a later
    // live message to make the Desk Link detail useful.
    const forkId = "f1234567-1234-1234-1234-123456789abc";
    const forkCtx = {
      ...ctx,
      sessionManager: {
        ...ctx.sessionManager,
        getSessionId: () => forkId,
        getBranch: () => [{ type: "message", message: { role: "assistant", content: [{ type: "text", text: "forked reply" }] } }],
      },
    };
    handlers.get("session_start")({ reason: "fork" }, forkCtx);
    await waitFor(() => records.some((record) => record.type === "events" && record.sessionId === forkId));
    assert.deepEqual(records.find((record) => record.type === "events" && record.sessionId === forkId)?.events,
      [{ kind: "assistant", text: "forked reply" }]);
    handlers.get("session_shutdown")({}, forkCtx);
  } finally {
    handlers.get("session_shutdown")({}, ctx);
    for (const peer of peers) peer.destroy();
    await new Promise((resolve) => server.close(resolve));
    for (const key of ["ODK_DESK_LINK_ADDRESS", "ODK_DESK_LINK_TOKEN", "ODK_DESK_LINK_MACHINE", "PI_DIRECTORY_SESSIONS_DIR"]) {
      if (saved[key] === undefined) delete process.env[key];
      else process.env[key] = saved[key];
    }
  }
});
