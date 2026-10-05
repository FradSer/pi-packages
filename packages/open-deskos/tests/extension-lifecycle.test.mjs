import assert from "node:assert/strict";
import { access, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import net from "node:net";
import { join } from "node:path";
import test from "node:test";

const sessionId = "11111111-1111-4111-8111-111111111111";

async function fixture(t, reporting = false) {
  const root = await mkdtemp("/tmp/odk-life-");
  const saved = { ...process.env };
  t.after(() => { process.env = saved; });
  const server = net.createServer((socket) => {
    socket.on("error", () => {});
    socket.on("data", () => socket.write(`${JSON.stringify({ v: 1, type: "ack" })}\n`));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => { server.closeAllConnections?.(); server.close(); });
  await mkdir(join(root, "project"));
  const desks = reporting ? [{ address: `127.0.0.1:${server.address().port}`, token: "fixture" }] : [];
  await writeFile(join(root, "desks.json"), JSON.stringify({ desks }));
  await writeFile(join(root, "history.jsonl"), `${JSON.stringify({ type: "message", message: { role: "user", content: "history" } })}\n`);
  process.env.ODK_DESK_LINK_DESKS_FILE = join(root, "desks.json");
  process.env.ODK_SESSION_HOST_SOCKET = join(root, "run");
  process.env.PI_DIRECTORY_SESSIONS_DIR = join(root, "registry");
  const { default: extension } = await import("../index.ts");
  const handlers = new Map();
  extension({ on(name, fn) { handlers.set(name, fn); }, registerCommand() {}, registerMessageRenderer() {}, registerEntryRenderer() {}, registerTool() {} });
  const ctx = {
    cwd: join(root, "project"), isIdle: () => true,
    sessionManager: {
      getSessionId: () => sessionId, getSessionName: () => undefined, getHeader: () => undefined,
      getSessionFile: () => join(root, "history.jsonl"),
    },
  };
  t.after(async () => {
    await handlers.get("session_shutdown")?.({}, ctx);
    await rm(root, { recursive: true, force: true });
  });
  return { handlers, ctx, descriptor: join(root, "run", `${sessionId}.json`) };
}

test("an explicit current-session endpoint works independently of reporting credentials", async (t) => {
  const f = await fixture(t);
  assert.equal(typeof f.handlers.get("session_start"), "function", "the declared host has lifecycle handlers");
  await f.handlers.get("session_start")({ reason: "startup" }, f.ctx);
  await access(f.descriptor);
  await f.handlers.get("session_shutdown")({}, f.ctx);
  await assert.rejects(access(f.descriptor), { code: "ENOENT" });
});

test("a pending durable replay cannot recreate the endpoint after shutdown", async (t) => {
  const f = await fixture(t, true);
  const startup = f.handlers.get("session_start")({ reason: "resume" }, f.ctx);
  await f.handlers.get("session_shutdown")({}, f.ctx);
  await startup;
  await assert.rejects(access(f.descriptor), { code: "ENOENT" });
});
