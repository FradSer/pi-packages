import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import net from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

async function waitFor(condition, ms = 8000) {
  const deadline = Date.now() + ms;
  while (!condition()) {
    assert.ok(Date.now() < deadline, "the desk never received the activity");
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

/** A desk on a local port, plus the extension wired to it, as the other tests do. */
async function desk(t) {
  const root = await mkdtemp(join(tmpdir(), "desk-activity-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const sockets = [], records = [];
  const server = net.createServer((socket) => {
    sockets.push(socket);
    let pending = "";
    socket.on("data", (chunk) => {
      pending += chunk.toString("utf8");
      const lines = pending.split("\n");
      pending = lines.pop();
      for (const line of lines) if (line) records.push(JSON.parse(line));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => { for (const socket of sockets) socket.destroy(); server.close(); });
  const saved = { ...process.env };
  t.after(() => { process.env = saved; });
  await writeFile(join(root, "desks.json"), JSON.stringify({ desks: [{ address: `127.0.0.1:${server.address().port}`, token: "isolated-fixture" }] }));
  delete process.env.ODK_DESK_LINK_CONTROL_TOKEN;
  process.env.ODK_DESK_LINK_DESKS_FILE = join(root, "desks.json");
  process.env.ODK_DESK_LINK_ADDRESS = `127.0.0.1:${server.address().port}`;
  process.env.ODK_DESK_LINK_TOKEN = "isolated-fixture";
  process.env.ODK_DESK_LINK_MACHINE = "isolated-machine";
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
  await handlers.get("session_start")({ reason: "startup" }, ctx);
  // The reporter only sends while its link is up, so the desk's hello is the
  // point at which an activity update can reach it.
  await waitFor(() => records.some((record) => record.type === "hello"));
  return { handlers, ctx, records, ownId };
}

const activities = (records) => records.flatMap((record) => record.sessions ?? []).map((session) => session.activity).filter(Boolean);

test("the card's activity becomes the tool that is running now", async (t) => {
  const { handlers, ctx, records } = await desk(t)

  // Mid-turn the newest thing a running session is doing is the tool it is
  // executing, not the prompt that started the turn: the card showed that prompt
  // for the whole turn, which is the report the desk owner made.
  await handlers.get("tool_execution_start")({ toolCallId: "t1", toolName: "bash", args: { command: "pnpm test" } }, ctx)
  await waitFor(() => activities(records).includes("bash: pnpm test"))

  await handlers.get("tool_execution_start")({ toolCallId: "t2", toolName: "read", args: { path: "src/example.js" } }, ctx)
  await waitFor(() => activities(records).includes("read: src/example.js"))

  // A tool whose arguments are not a short line still names the tool and nothing
  // more, and no argument is echoed beyond the summary the card shows.
  await handlers.get("tool_execution_start")({ toolCallId: "t3", toolName: "webfetch", args: { url: "https://example.com/very/long/path" } }, ctx)
  await waitFor(() => activities(records).some((activity) => activity.startsWith("webfetch")))

  const newest = activities(records).at(-1)
  assert.ok(newest.length <= 200, `the activity stays a short summary, saw ${newest.length} characters`)
  assert.equal(newest.includes("\n"), false, "and stays one line")
})

test("a finished tool is replaced by the message that follows it", async (t) => {
  const { handlers, ctx, records } = await desk(t)
  await handlers.get("tool_execution_start")({ toolCallId: "t1", toolName: "bash", args: { command: "pnpm test" } }, ctx)
  await waitFor(() => activities(records).includes("bash: pnpm test"))

  await handlers.get("message_end")({ message: { role: "assistant", content: [{ type: "text", text: "Tests pass." }] } }, ctx)
  await waitFor(() => activities(records).includes("Tests pass."))
})