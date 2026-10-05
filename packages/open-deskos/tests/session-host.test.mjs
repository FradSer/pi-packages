import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { access, mkdir, mkdtemp, readFile, rm, stat, symlink, writeFile } from "node:fs/promises";
import net from "node:net";
import { homedir, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { SessionHost, resolveSessionEndpoint, sessionRuntimeDir } from "../src/session-host.ts";

const CLIENT = fileURLToPath(new URL("../src/session-host-client.mjs", import.meta.url));
const SESSION = "3f6b1c2a-4d5e-4f6a-8b9c-0d1e2f3a4b5c";
const PROTOCOL_INVALID = "任务协议无效";
const PROJECT_NOT_ADMITTED = "项目不在允许的开发目录内";
const UNKNOWN_COMMAND = "未知任务命令";
const TASK_NOT_FOUND = "未找到任务";
const PROMPT_INVALID = "任务 ID 或提示无效";
const NOT_A_SESSION_HOST = "此端点是当前 Pi 会话，不是 Hosted Pi 任务服务";

/** One connection carrying one frame, the way a desk's own one-shot client does. */
function exchange(socketPath, text, { end = false } = {}) {
  return new Promise((resolve, reject) => {
    const socket = net.createConnection(socketPath);
    const chunks = [];
    const deadline = setTimeout(() => {
      socket.destroy();
      reject(new Error("the host never answered"));
    }, 5000);
    socket.on("data", (chunk) => chunks.push(chunk));
    socket.on("error", (error) => { clearTimeout(deadline); reject(error); });
    socket.once("close", () => { clearTimeout(deadline); resolve(Buffer.concat(chunks).toString("utf8")); });
    socket.once("connect", () => { socket.write(text); if (end) socket.end(); });
  });
}

const projects = new Map();
const ask = async (socketPath, request) => JSON.parse(await exchange(socketPath, `${JSON.stringify({ ...(['status', 'prompt', 'cancel'].includes(request.command) && request.project === undefined && projects.has(socketPath) ? { project: projects.get(socketPath) } : {}), ...request })}\n`));

/** True when nothing is listening at the path, which is what a closed endpoint looks like. */
function refused(socketPath) {
  return new Promise((resolve) => {
    const socket = net.createConnection(socketPath);
    socket.once("connect", () => { socket.destroy(); resolve(false); });
    socket.once("error", () => resolve(true));
  });
}

const assistant = (text, stopReason) => ({ role: "assistant", content: [{ type: "text", text }], stopReason });
const user = (text) => ({ role: "user", content: [{ type: "text", text }] });

// A Unix socket path is bounded by the platform (104 bytes on macOS), so a fixture whose
// socket lives in a tmpdir needs a short root rather than the long per-user temp directory.
const ROOT = process.platform === "win32" ? tmpdir() : "/tmp";

async function fixtureRoot(t, prefix) {
  const root = await mkdtemp(join(ROOT, prefix));
  t.after(() => rm(root, { recursive: true, force: true }));
  return root;
}

/** A bound session over a real Unix socket in a tmpdir, with a fake pi and ctx. */
async function session(t, options = {}) {
  const root = await fixtureRoot(t, options.prefix ?? "odk-sh-");
  const runtimeDir = options.runtimeDir ?? join(root, "run");
  const cwd = options.cwd ?? join(root, "project");
  await mkdir(join(cwd, "src"), { recursive: true });
  const sent = [];
  const aborts = { count: 0 };
  let idle = options.idle ?? true;
  let pending = options.pending ?? 0;
  let sessionId = options.sessionId ?? SESSION;
  const pi = { sendUserMessage(content, opts) {
    sent.push({ content, options: opts === undefined ? undefined : { ...opts } });
    if (options.complete) {
      host.markRunning();
      host.observeMessage(user(content));
      host.observeMessage(assistant("completed immediately", "stop"));
      host.markSettled();
    } else if (options.observe !== false) queueMicrotask(() => host.observeMessage(user(content)));
  } };
  const ctx = {
    cwd,
    isIdle: () => idle,
    hasPendingMessages: () => pending > 0,
    abort() { aborts.count += 1; },
    sessionManager: { getSessionId: () => sessionId, getSessionName: () => options.name },
  };
  const host = new SessionHost({
    pi,
    env: { XDG_RUNTIME_DIR: runtimeDir, ...options.env },
    requestTimeoutMs: options.requestTimeoutMs ?? 1000,
  });
  const started = await host.start(ctx);
  projects.set(started.socketPath, cwd);
  t.after(() => projects.delete(started.socketPath));
  t.after(() => host.close());
  return {
    root, runtimeDir, cwd, host, started, sent, aborts, ctx,
    socketPath: started.socketPath,
    /** One frame in, the correlated frame back, over this session's own socket. */
    ask: (request) => ask(started.socketPath, request),
    /** The socket and the descriptor, which are the only two files this owns. */
    descriptorPath: started.descriptorPath,
    idle(value) { idle = value; },
    becomes(id) { sessionId = id; },
  };
}

test("building a host binds nothing until session_start", async (t) => {
  const root = await fixtureRoot(t, "odk-si-");
  const { socketPath, descriptorPath } = resolveSessionEndpoint({ XDG_RUNTIME_DIR: join(root, "run") }, process.platform, "00000000-0000-4000-8000-000000000000");
  const host = new SessionHost({ pi: { sendUserMessage() {} }, env: { XDG_RUNTIME_DIR: join(root, "run") } });
  assert.equal(host.endpoint, null, "a constructed host has no endpoint yet");
  assert.equal(await refused(socketPath), true, "and nothing is listening");
  assert.equal(await refused(descriptorPath), true, "and no descriptor was written");
  await host.close();
});

test("the endpoint is private to the user who owns it", async (t) => {
  const h = await session(t);
  assert.equal(h.started.bound, true);
  assert.equal(h.started.published, true);
  assert.equal(h.socketPath, join(h.runtimeDir, "open-deskos", "sessions", `${h.ctx.sessionManager.getSessionId()}.sock`));
  assert.equal((await stat(join(h.runtimeDir, "open-deskos", "sessions"))).mode & 0o777, 0o700, "the parent directory is private");
  assert.equal((await stat(h.socketPath)).mode & 0o777, 0o600, "the socket is private");
  assert.equal((await stat(h.descriptorPath)).mode & 0o777, 0o600, "the descriptor is private");
  const descriptor = JSON.parse(await readFile(h.descriptorPath, "utf8"));
  assert.equal(descriptor.version, 1);
  assert.equal(descriptor.socketPath, h.socketPath);
  assert.equal(descriptor.sessionId, h.ctx.sessionManager.getSessionId());
  assert.equal(descriptor.project, h.cwd, "a desk reads the project this session is in, not a configured root");
  assert.ok(descriptor.state === "settled" || descriptor.state === "running");
});

test("the socket path is the override, then the runtime directory", () => {
  const id = "11111111-1111-4111-8111-111111111111";
  const override = resolveSessionEndpoint({ XDG_RUNTIME_DIR: "/run/user/1000", ODK_SESSION_HOST_SOCKET: "/tmp/odk" }, "linux", id);
  assert.equal(override.socketPath, `/tmp/odk/${id}.sock`, "the declared directory holds this session's own socket");
  assert.equal(override.descriptorPath, `/tmp/odk/${id}.json`, "and its own descriptor beside it");
  const relative = resolveSessionEndpoint({ XDG_RUNTIME_DIR: "/run/user/1000", ODK_SESSION_HOST_SOCKET: "relative.sock" }, "linux", id);
  assert.equal(relative.socketPath, `/run/user/1000/open-deskos/sessions/${id}.sock`, "a relative override is not honored");
  assert.equal(sessionRuntimeDir({ XDG_RUNTIME_DIR: "/run/user/1000" }, "linux"), "/run/user/1000");
  assert.equal(sessionRuntimeDir({ XDG_RUNTIME_DIR: "run/user/1000" }, "linux"), join(homedir(), ".local", "run"), "a relative XDG runtime directory is not a runtime directory");
  assert.equal(sessionRuntimeDir({}, "darwin"), join(homedir(), ".local", "run"), "macOS falls back to its own run directory");
  assert.equal(sessionRuntimeDir({ LOCALAPPDATA: "C:\\Users\\me\\AppData\\Local" }, "win32"), "C:\\Users\\me\\AppData\\Local");
  const windows = resolveSessionEndpoint({ LOCALAPPDATA: "C:\\Users\\me\\AppData\\Local" }, "win32", id);
  assert.equal(windows.socketPath, `C:\\Users\\me\\AppData\\Local\\open-deskos\\sessions\\${id}.sock`);
  assert.equal(windows.descriptorPath, `C:\\Users\\me\\AppData\\Local\\open-deskos\\sessions\\${id}.json`);
});

test("list answers with this one session and nothing invented", async (t) => {
  const h = await session(t, { name: "Desk work" });
  const answer = await ask(h.socketPath, { version: 1, requestId: "r1", command: "list" });
  assert.equal(answer.ok, true);
  assert.equal(answer.requestId, "r1");
  assert.equal(answer.version, 1);
  assert.equal(answer.truncated, false);
  assert.equal(answer.tasks.length, 1);
  const [task] = answer.tasks;
  assert.equal(task.taskId, SESSION, "the session is identified as itself");
  assert.equal(task.project, h.cwd, "and answers for the directory it is in");
  assert.equal(task.name, "Desk work");
  assert.equal(task.lifecycle, "live");
  assert.equal(task.state, "settled");
  assert.equal(task.activity, "idle");
  assert.equal(task.goal, "", "nothing has been asked yet");
  assert.equal("turnOutcome" in task, false, "an unobserved turn outcome stays absent");
  assert.equal("response" in task, false, "list carries no reply body, exactly as a hosted task's list does");
  assert.equal("createdAt" in task, false, "no timestamp is invented");
});

test("status answers for this session and refuses another", async (t) => {
  const h = await session(t);
  const own = await ask(h.socketPath, { version: 1, requestId: "r2", command: "status", taskId: SESSION });
  assert.equal(own.ok, true);
  assert.equal(own.task.taskId, SESSION);
  assert.equal(own.task.state, "settled");
  assert.equal(own.task.prompt, "");
  assert.equal(own.task.response, "");
  const other = await ask(h.socketPath, { version: 1, requestId: "r3", command: "status", taskId: "9d9d4d4d-1111-2222-3333-444444444444" });
  assert.equal(other.ok, false);
  assert.equal(other.error, TASK_NOT_FOUND);
  assert.equal(other.requestId, "r3", "a refusal is still correlated");
});

test("a project scope is this project or an ancestor directory", async (t) => {
  const h = await session(t);
  const inside = await ask(h.socketPath, { version: 1, requestId: "p1", command: "list", project: h.cwd });
  assert.equal(inside.ok, true);
  const nested = await ask(h.socketPath, { version: 1, requestId: "p2", command: "list", project: h.root });
  assert.equal(nested.ok, true);
  for (const [requestId, project] of [
    ["p3", join(h.root, "other")],
    ["p4", "src"],
    ["p5", join(h.cwd, "src")],
    ["p6", "/opt/open-deskos"],
    ["p7", join(h.cwd, "missing")],
  ]) {
    const refusedProject = await ask(h.socketPath, { version: 1, requestId, command: "list", project });
    assert.equal(refusedProject.ok, false, `${project} is not this session's project`);
    assert.equal(refusedProject.error, PROJECT_NOT_ADMITTED);
  }
});

test("a prompt becomes a real user message with the requested delivery", async (t) => {
  const h = await session(t);
  const steer = await ask(h.socketPath, { version: 1, requestId: "m1", command: "prompt", taskId: SESSION, prompt: "run the tests", streamingBehavior: "steer" });
  assert.equal(steer.ok, true);
  assert.equal(steer.accepted, false);
  assert.equal(steer.submitted, true);
  assert.equal(steer.task.state, "settled", "the state right after delivery is the state that was observed");
  assert.deepEqual(h.sent[0], { content: "run the tests", options: { deliverAs: "steer", expandPromptTemplates: true } });

  await ask(h.socketPath, { version: 1, requestId: "m2", command: "prompt", taskId: SESSION, prompt: "then commit", streamingBehavior: "followUp" });
  assert.deepEqual(h.sent[1], { content: "then commit", options: { deliverAs: "followUp", expandPromptTemplates: true } });

  await ask(h.socketPath, { version: 1, requestId: "m3", command: "prompt", taskId: SESSION, prompt: "and report" });
  assert.deepEqual(h.sent[2], { content: "and report", options: { expandPromptTemplates: true, deliverAs: "steer" } }, "native Enter, commands and templates stay enabled");

  for (const [requestId, prompt] of [["m4", "   "], ["m5", '{"lone":"\ud800"}'], ["m6", 7]]) {
    const refusedPrompt = await ask(h.socketPath, { version: 1, requestId, command: "prompt", taskId: SESSION, prompt });
    assert.equal(refusedPrompt.ok, false, `${JSON.stringify(prompt)} is not a usable prompt`);
    assert.equal(refusedPrompt.error, PROMPT_INVALID);
  }
  const foreign = await ask(h.socketPath, { version: 1, requestId: "m7", command: "prompt", taskId: "9d9d4d4d-1111-2222-3333-444444444444", prompt: "not this session" });
  assert.equal(foreign.ok, false);
  assert.equal(foreign.error, TASK_NOT_FOUND);
  assert.equal(h.sent.length, 3, "nothing was delivered to a refused prompt");
});

test("cancel aborts the running turn and answers the resulting state", async (t) => {
  const h = await session(t);
  h.idle(false);
  h.host.markRunning();
  const answer = await ask(h.socketPath, { version: 1, requestId: "c1", command: "cancel", taskId: SESSION });
  assert.equal(answer.ok, true);
  assert.equal(answer.accepted, true);
  assert.equal(answer.task.state, "running", "an abort is asynchronous: the turn is still running right after it");
  assert.equal(h.aborts.count, 1, "Pi's own abort is what cancels the turn");
  h.host.markSettled();
  const settled = await ask(h.socketPath, { version: 1, requestId: "c2", command: "status", taskId: SESSION });
  assert.equal(settled.task.turnOutcome, "cancelled", "a cancelled turn is observed as cancelled");
});

test("a session cannot host sessions", async (t) => {
  const h = await session(t);
  for (const [index, command] of ["start", "launch", "end", "history"].entries()) {
    const answer = await ask(h.socketPath, { version: 1, requestId: `n${index}`, command, taskId: SESSION, prompt: "anything", project: h.cwd });
    assert.deepEqual(answer, { version: 1, requestId: `n${index}`, ok: false, error: NOT_A_SESSION_HOST });
  }
  const attach = await ask(h.socketPath, { version: 1, requestId: "n9", command: "attach", taskId: SESSION });
  assert.equal(attach.error, UNKNOWN_COMMAND, "anything outside the protocol's own vocabulary is unknown");
});

test("the protocol is the one the desk already speaks", async (t) => {
  const h = await session(t);
  const bad = await ask(h.socketPath, { version: 2, requestId: "v1", command: "list" });
  assert.equal(bad.ok, false);
  assert.equal(bad.error, PROTOCOL_INVALID);
  assert.equal(bad.requestId, "v1");
  const anonymous = await ask(h.socketPath, { version: 1, command: "list" });
  assert.deepEqual(anonymous, { version: 1, requestId: "", ok: false, error: PROTOCOL_INVALID });
  assert.equal(await exchange(h.socketPath, "this is not json\n"), "", "a line that is not JSON is refused without a frame");
  assert.equal(await exchange(h.socketPath, `{"version":1,"requestId":"d1","command":"list"}\n{"version":1,"requestId":"d2","command":"list"}\n`), "", "one connection carries one frame");
  assert.equal(await exchange(h.socketPath, `{"version":1,"requestId":"d3","command":"list","project":"${"x".repeat(70 * 1024)}"}\n`), "", "an oversize frame is refused without a frame");
  assert.equal(await exchange(h.socketPath, "", { end: true }), "", "a connection that sends no line closes without a frame");
  assert.equal((await ask(h.socketPath, { version: 1, requestId: "d4", command: "list" })).ok, true, "and the host is still serving");
});

test("a connection that never speaks is closed without a frame", async (t) => {
  const h = await session(t, { requestTimeoutMs: 150 });
  assert.equal(await exchange(h.socketPath, "", { end: false }), "");
});

test("state follows the same events the reporter uses", async (t) => {
  const h = await session(t);
  h.host.markRunning();
  h.idle(false);
  h.host.observeMessage(user("read the layout"));
  h.host.observeActivity("bash: pnpm test");
  const running = await ask(h.socketPath, { version: 1, requestId: "s1", command: "status", taskId: SESSION });
  assert.equal(running.task.state, "running");
  assert.equal(running.task.activity, "working");
  assert.equal(running.task.prompt, "read the layout", "the goal is what the session was asked");
  assert.equal(running.task.latestActivity, "bash: pnpm test", "and the activity is the tool running now");
  assert.equal("turnOutcome" in running.task, false, "a turn in flight has no outcome yet");

  // A tool call keeps the turn going, so it is not a claim about how the turn ended.
  h.host.observeMessage(assistant("Looking now.", "toolUse"));
  h.host.markSettled();
  h.idle(true);
  const settled = await ask(h.socketPath, { version: 1, requestId: "s2", command: "status", taskId: SESSION });
  assert.equal(settled.task.state, "settled");
  assert.equal(settled.task.activity, "idle");
  assert.equal(settled.task.response, "Looking now.", "the most recent assistant text is the response");
  assert.equal("turnOutcome" in settled.task, false, "a turn that only made tool calls has not ended");

  h.host.markRunning();
  h.host.observeMessage(assistant("Tests pass.", "stop"));
  h.host.markSettled();
  const finished = await ask(h.socketPath, { version: 1, requestId: "s3", command: "status", taskId: SESSION });
  assert.equal(finished.task.turnOutcome, "finished");
  assert.equal(finished.task.response, "Tests pass.");

  h.host.markRunning();
  h.host.observeMessage(assistant("", "error"));
  h.host.markSettled();
  const failed = await ask(h.socketPath, { version: 1, requestId: "s4", command: "status", taskId: SESSION });
  assert.equal(failed.task.turnOutcome, "failed", "an errored turn is observed as failed");

  h.host.markRunning();
  h.host.observeMessage(assistant("stopped", "aborted"));
  h.host.markSettled();
  const aborted = await ask(h.socketPath, { version: 1, requestId: "s5", command: "status", taskId: SESSION });
  assert.equal(aborted.task.turnOutcome, "cancelled");
  const listed = await ask(h.socketPath, { version: 1, requestId: "s6", command: "list" });
  assert.equal(listed.tasks[0].latestActivity, "bash: pnpm test", "list carries the same activity the card shows");
});

test("shutdown is idempotent and takes the endpoint with it", async (t) => {
  const h = await session(t);
  assert.equal((await ask(h.socketPath, { version: 1, requestId: "x1", command: "list" })).ok, true);
  await h.host.close();
  await h.host.close();
  assert.equal(h.host.endpoint, null);
  assert.equal(await refused(h.descriptorPath), true, "the descriptor is removed on shutdown");
  assert.equal(await refused(h.socketPath), true, "and so is the socket");
  const fresh = await session(t);
  assert.equal((await ask(fresh.socketPath, { version: 1, requestId: "x2", command: "list" })).ok, true, "the path can be bound again");
});

test("a reload replaces the previous bind instead of stacking one", async (t) => {
  const h = await session(t);
  h.host.markRunning();
  h.becomes("8a8b4c4d-5555-6666-7777-888888888888");
  const previous = h.socketPath;
  const restarted = await h.host.start(h.ctx);
  assert.equal(restarted.bound, true);
  assert.notEqual(restarted.socketPath, previous, "a different session answers at its own endpoint");
  assert.equal(await refused(previous), true, "and the endpoint it replaced is withdrawn, not left answering");
  assert.equal((await ask(restarted.socketPath, { version: 1, requestId: "l1", command: "status", taskId: h.ctx.sessionManager.getSessionId(), project: h.cwd })).task.taskId, "8a8b4c4d-5555-6666-7777-888888888888");
  const interrupted = await ask(restarted.socketPath, { version: 1, requestId: "l2", command: "status", taskId: h.ctx.sessionManager.getSessionId(), project: h.cwd });
  assert.equal(interrupted.task.turnOutcome, "interrupted", "a turn in flight when the session was replaced did not finish here");
  const descriptor = JSON.parse(await readFile(restarted.descriptorPath, "utf8"));
  assert.equal(descriptor.socketPath, restarted.socketPath);
  assert.equal(descriptor.sessionId, "8a8b4c4d-5555-6666-7777-888888888888");
  assert.equal((await ask(restarted.socketPath, { version: 1, requestId: "l3", command: "list" })).tasks.length, 1, "only one host answers");
});

test("a socket another process still owns is never taken over", async (t) => {
  const h = await session(t);
  await h.host.close();
  const squatter = net.createServer(() => {});
  await new Promise((resolve) => squatter.listen(h.socketPath, resolve));
  t.after(() => new Promise((resolve) => { squatter.close(resolve); }));
  const other = new SessionHost({ pi: { sendUserMessage() {} }, env: { XDG_RUNTIME_DIR: h.runtimeDir } });
  const refusedStart = await other.start(ctxOf(h));
  assert.equal(refusedStart.bound, false, "a live endpoint is not stolen from the session that owns it");
  assert.equal(typeof refusedStart.reason, "string");
  await other.close();
});

test("the desk relays one frame over SSH with no build step", async (t) => {
  const h = await session(t);
  const request = { version: 1, requestId: "cli-1", command: "status", taskId: SESSION, project: h.cwd };
  const relayed = await runClient(t, h.socketPath, `${JSON.stringify(request)}\n`);
  assert.equal(relayed.code, 0, relayed.stderr);
  assert.equal(relayed.stderr, "", "the client prints nothing but the reply frame");
  const answer = JSON.parse(relayed.stdout);
  assert.equal(answer.requestId, "cli-1");
  assert.equal(answer.ok, true);
  assert.equal(answer.task.taskId, SESSION);
  assert.equal(relayed.stdout.split("\n").filter(Boolean).length, 1, "exactly one frame is printed");

  h.host.markRunning();
  const prompted = await runClient(t, h.socketPath, `${JSON.stringify({ version: 1, requestId: "cli-2", command: "prompt", project: h.cwd, taskId: SESSION, prompt: "ship it", streamingBehavior: "steer" })}\n`);
  assert.equal(prompted.code, 0, prompted.stderr);
  assert.equal(JSON.parse(prompted.stdout).accepted, false);
  assert.equal(JSON.parse(prompted.stdout).submitted, true);
  assert.deepEqual(h.sent[0], { content: "ship it", options: { deliverAs: "steer", expandPromptTemplates: true } });

  const missing = await runClient(t, join(h.root, "nothing.sock"), `${JSON.stringify(request)}\n`);
  assert.notEqual(missing.code, 0, "a transport failure exits non-zero");
  assert.equal(missing.stdout, "", "and prints nothing the desk could mistake for an answer");
});

test("the client refuses a reply that is not this request's", async (t) => {
  const socketPath = join(await fixtureRoot(t, "odk-uc-"), "liar.sock");
  const liar = net.createServer((socket) => {
    socket.once("data", () => socket.end('{"version":1,"requestId":"someone-elses","ok":true}\n'));
  });
  await new Promise((resolve) => liar.listen(socketPath, resolve));
  t.after(() => new Promise((resolve) => liar.close(resolve)));
  const relayed = await runClient(t, socketPath, `${JSON.stringify({ version: 1, requestId: "mine", command: "list" })}\n`);
  assert.notEqual(relayed.code, 0, "an uncorrelated frame is not an answer");
  assert.equal(relayed.stdout, "");
  // With no socket named the client looks for the session that owns the project, and
  // answers this frame's own refusal when none does: a desk reads an answer, not a usage note.
  const unserved = await runClient(t, undefined, `${JSON.stringify({ version: 1, requestId: "mine", command: "list", project: "/nowhere" })}\n`, { env: { ...process.env, XDG_RUNTIME_DIR: await fixtureRoot(t, "odk-empty-") } });
  assert.equal(unserved.code, 0, unserved.stderr);
  assert.equal(JSON.parse(unserved.stdout).error, "项目不在允许的开发目录内");
  const usage = await runClient(t, "relative.sock", `${JSON.stringify({ version: 1, requestId: "mine", command: "list" })}\n`);
  assert.notEqual(usage.code, 0, "and a name that is not an absolute socket path is a usage failure, not an answer");
});

/** The client as a desk runs it: one frame in on stdin, one frame out on stdout. */
function runClient(t, socketPath, input, { args, env } = {}) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [CLIENT, ...(args ?? (socketPath ? [socketPath] : []))], {
      ...(env ? { env } : {}),
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("close", (code) => resolve({ code, stdout, stderr }));
    t.after(() => child.kill("SIGKILL"));
    child.stdin.end(input);
  });
}

function ctxOf(h) {
  return {
    cwd: h.cwd,
    isIdle: () => true,
    abort() {},
    sessionManager: { getSessionId: () => SESSION, getSessionName: () => undefined },
  };
}

test("the extension binds its own session and never a reported one twice", async (t) => {
  const root = await fixtureRoot(t, "odk-w-");
  const desksFile = join(root, "desks.json");
  // The default desks file is resolved from the home directory when this module is
  // first imported, so a fixture states its own list rather than reporting to the
  // host's real desks. The address is a closed port: this proves the wiring, not
  // the reporter, and its reconnect timer is unref'd.
  await writeFile(desksFile, JSON.stringify({ desks: [{ address: "127.0.0.1:1", token: "isolated-fixture" }] }));
  const saved = { ...process.env };
  t.after(() => { process.env = { ...saved }; });
  process.env.ODK_DESK_LINK_DESKS_FILE = desksFile;
  process.env.PI_DIRECTORY_SESSIONS_DIR = root;
  process.env.XDG_RUNTIME_DIR = join(root, "run");
  // The endpoint is a declared capability, so this fixture declares one inside its own
  // directory; a machine that declares none is left unreachable (pinned below).
  process.env.ODK_SESSION_HOST_SOCKET = join(root, "run");
  const { default: extension } = await import("../index.ts");
  const handlers = new Map();
  extension({ on(name, fn) { handlers.set(name, fn); }, registerCommand() {}, registerMessageRenderer() {}, registerEntryRenderer() {}, registerTool() {} });
  const cwd = join(root, "project");
  await mkdir(cwd, { recursive: true });
  const ctx = {
    cwd,
    isIdle: () => true,
    abort() {},
    sessionManager: { getSessionId: () => SESSION, getSessionName: () => undefined, getHeader: () => undefined, getBranch: () => [] },
    ui: { notify() {}, setStatus() {} },
  };
  await handlers.get("session_start")({ reason: "startup" }, ctx);
  const socketPath = join(root, "run", `${SESSION}.sock`);
  const bound = await ask(socketPath, { version: 1, requestId: "w1", command: "list" });
  assert.equal(bound.ok, true, "the extension's own session is drivable from inside its own process");
  assert.equal(bound.tasks[0].taskId, SESSION);

  await handlers.get("agent_start")({}, ctx);
  handlers.get("message_end")({ message: assistant("Working on it.", "stop") }, ctx);
  handlers.get("agent_settled")({}, ctx);
  const driven = await ask(socketPath, { version: 1, requestId: "w2", command: "status", taskId: SESSION, project: cwd });
  assert.equal(driven.task.state, "settled");
  assert.equal(driven.task.response, "Working on it.");
  assert.equal(driven.task.turnOutcome, "finished");

  await handlers.get("session_shutdown")({ reason: "quit" }, ctx);
  assert.equal(await refused(socketPath), true, "the endpoint is gone with the session");
  assert.equal(await refused(join(root, "run", `${SESSION}.json`)), true);

  // A reload brings the endpoint back rather than leaving a dead one behind.
  await handlers.get("session_start")({ reason: "reload" }, ctx);
  assert.equal((await ask(socketPath, { version: 1, requestId: "w3", command: "list" })).ok, true);
  await handlers.get("session_shutdown")({ reason: "reload" }, ctx);
});

// One endpoint per host served whichever session bound it first and refused every
// later one, so on a machine with several Pi sessions a desk reached the wrong one
// and the intended one was invisible. Each session now owns its own endpoint.
test("two sessions on one machine are both reachable and neither is refused", async (t) => {
  // One runtime directory is the point: this is one machine with two sessions, each in
  // its own project, both of which a desk must be able to reach by name.
  const machine = await fixtureRoot(t, "odk-machine-");
  const runtimeDir = join(machine, "run");
  const projectA = join(machine, "project-a");
  const projectB = join(machine, "project-b");
  const first = await session(t, { sessionId: "22222222-2222-4222-8222-222222222222", runtimeDir, cwd: projectA });
  const second = await session(t, { sessionId: "33333333-3333-4333-8333-333333333333", runtimeDir, cwd: projectB });
  await mkdir(join(projectA, "src"), { recursive: true });
  await mkdir(join(projectB, "src"), { recursive: true });
  assert.equal(first.runtimeDir, second.runtimeDir, "both sessions publish into the same machine directory");
  assert.equal(first.started.bound, true, "the first session is bound");
  assert.equal(second.started.bound, true, "and the second one is bound beside it, not refused");
  assert.notEqual(first.socketPath, second.socketPath, "each session answers at its own socket");
  assert.notEqual(first.descriptorPath, second.descriptorPath, "and publishes its own descriptor");
  const listed = SessionHost.listEndpoints({ XDG_RUNTIME_DIR: first.runtimeDir });
  assert.equal(listed.length, 2, "a desk can see both sessions");
  for (const file of listed) {
    const descriptor = JSON.parse(await readFile(file, "utf8"));
    assert.ok(typeof descriptor.sessionId === "string" && descriptor.sessionId.length > 0);
    assert.ok(typeof descriptor.project === "string" && descriptor.project.length > 0);
  }
});

test("a reload that switches sessions moves this session's own endpoint", async (t) => {
  const h = await session(t, { sessionId: "44444444-4444-4444-8444-444444444444" });
  const before = h.socketPath;
  h.becomes("55555555-5555-4555-8555-555555555555");
  const restarted = await h.host.start(h.ctx);
  assert.equal(restarted.bound, true, "the session's new identity binds");
  assert.notEqual(restarted.socketPath, before, "at its own socket, not the previous one");
  assert.equal(await refused(before), true, "and the previous socket is withdrawn");
  assert.equal(JSON.parse(await readFile(restarted.descriptorPath, "utf8")).sessionId, "55555555-5555-4555-8555-555555555555");
});

test("the client finds the session that owns a project, and refuses one none does", async (t) => {
  const machine = await fixtureRoot(t, "odk-find-");
  const runtimeDir = join(machine, "run");
  const wanted = await session(t, { sessionId: "66666666-6666-4666-8666-666666666666", runtimeDir, cwd: join(machine, "project") });
  const other = await session(t, { sessionId: "77777777-7777-4777-8777-777777777777", runtimeDir, cwd: join(machine, "elsewhere") });
  await mkdir(join(wanted.cwd, "src"), { recursive: true });
  await mkdir(join(other.cwd, "src"), { recursive: true });
  const env = { ...process.env, XDG_RUNTIME_DIR: wanted.runtimeDir };
  const find = async (request, args = ["--find"]) => {
    const relayed = await runClient(t, null, `${JSON.stringify(request)}\n`, { args, env });
    assert.equal(relayed.code, 0, relayed.stderr);
    return JSON.parse(relayed.stdout);
  };

  const listed = await find({ version: 1, requestId: "req-find-1", command: "list", project: wanted.cwd });
  assert.equal(listed.ok, true, "the session that owns the project answers");
  assert.equal(listed.tasks[0].project, wanted.cwd);
  assert.equal(listed.tasks.length, 1, "and only that session answers");

  const other_ = await find({ version: 1, requestId: "req-find-2", command: "list", project: other.cwd });
  assert.equal(other_.ok, true, "the other project reaches the other session");
  assert.equal(other_.tasks[0].project, other.cwd, "never the first session's reply");

  // The desk declares one executable and no socket, so the client finds the session itself.
  const implicit = await find({ version: 1, requestId: "req-find-4", command: "list", project: other.cwd }, []);
  assert.equal(implicit.ok, true, "with no socket named, the client still answers from the frame's project");
  assert.equal(implicit.tasks[0].project, other.cwd);

  const outside = await find({ version: 1, requestId: "req-find-3", command: "list", project: join(machine, "nowhere") });
  assert.equal(outside.ok, false, "a project no session serves is refused, not answered by another one");
  assert.equal(outside.error, "项目不在允许的开发目录内", "and the refusal is the protocol's own");
  assert.equal(outside.requestId, "req-find-3", "and it is this request's frame, so a desk can read it");
});

test("a machine that declared no endpoint has none to reach", async (t) => {
  const root = await fixtureRoot(t, "odk-optin-");
  const previous = process.env.ODK_SESSION_HOST_SOCKET;
  delete process.env.ODK_SESSION_HOST_SOCKET;
  t.after(() => { if (previous === undefined) delete process.env.ODK_SESSION_HOST_SOCKET; else process.env.ODK_SESSION_HOST_SOCKET = previous; });
  const handlers = new Map();
  const extension = (await import("../index.ts")).default;
  extension({ on(name, fn) { handlers.set(name, fn); }, registerCommand() {}, registerMessageRenderer() {}, registerEntryRenderer() {}, registerTool() {} });
  await handlers.get("session_start")({ reason: "startup" }, {
    cwd: join(root, "project"),
    isIdle: () => true,
    abort() {},
    sessionManager: { getSessionId: () => SESSION, getSessionName: () => undefined, getHeader: () => undefined, getBranch: () => [] },
    ui: { notify() {}, setStatus() {} },
  });
  assert.equal(await access(join(root, "run")).then(() => true, () => false), false, "nothing was bound without a declared endpoint");
});

// A desk reaches a session through this machine's login shell, whose PATH is not
// the one an interactive shell has. A launcher that assumed node was on it answered
// nothing at all, which is what a Windows handheld saw.
test("the desk's launcher finds a node runtime without the login shell's PATH", async (t) => {
  const launcherPath = join(dirname(fileURLToPath(import.meta.url)), "..", "session-control");
  const launcher = await readFile(launcherPath, "utf8");
  assert.match(launcher, /^#!\/bin\/sh\n/, "it is a shell script, so no build step and no runtime assumption");
  assert.match(launcher, /fnm\/aliases\/default\/bin\/node/, "a version manager's stable alias is one candidate");
  assert.match(launcher, /ODK_NODE/, "and an operator can name the runtime outright");
  assert.match(launcher, /src\/session-host-client\.mjs/, "it execs the relay beside itself");
  assert.ok((await stat(launcherPath)).mode & 0o111, "and it is executable, so a desk needs no shell quoting of its own");
});

// An instruction that Pi drops is the worst answer a desk can get: it believes
// the work was handed over. A keyword re-sent by a local extension while the agent
// is streaming arrives without a delivery, so the host verifies the queue instead
// of assuming it.
test("an unobserved offered instruction reports unknown without claiming delivery", async (t) => {
  const h = await session(t, { idle: false, pending: 0, observe: false, requestTimeoutMs: 3000 });
  const refused = await h.ask({ version: 1, requestId: "q1", command: "prompt", taskId: SESSION, prompt: "继续", streamingBehavior: "followUp" });
  assert.equal(refused.ok, true);
  assert.equal(refused.accepted, false);
  assert.equal(refused.delivery, "unknown");
  assert.deepEqual(h.sent, [{ content: "继续", options: { deliverAs: "followUp", expandPromptTemplates: true } }], "offered once, with no automatic retry");
});

test("working and idle instructions are each submitted once through native Pi", async (t) => {
  const running = await session(t, { idle: false, pending: 1 });
  assert.equal((await running.ask({ version: 1, requestId: "q2", command: "prompt", taskId: SESSION, prompt: "继续", streamingBehavior: "followUp" })).ok, true);
  assert.deepEqual(running.sent, [{ content: "继续", options: { deliverAs: "followUp", expandPromptTemplates: true } }]);

  const idle = await session(t, { idle: true, pending: 0 });
  assert.equal((await idle.ask({ version: 1, requestId: "q3", command: "prompt", taskId: SESSION, prompt: "继续", streamingBehavior: "followUp" })).ok, true);
  assert.deepEqual(idle.sent, [{ content: "继续", options: { deliverAs: "followUp", expandPromptTemplates: true } }]);
});

// A caller reporting on a session has to say whether the instruction ran or is
// waiting its turn, so the answer carries that rather than leaving it to be
// guessed from the session's state.
test("a native prompt cannot claim admission from idle or working state", async (t) => {
  const idle = await session(t, { idle: true });
  const ran = await idle.ask({ version: 1, requestId: "d1", command: "prompt", taskId: SESSION, prompt: "继续", streamingBehavior: "followUp" });
  assert.equal(ran.delivery, "unknown", "an idle session is not an identity-aware acknowledgment");

  const running = await session(t, { idle: false, pending: 1, observe: false });
  const queued = await running.ask({ version: 1, requestId: "d2", command: "prompt", taskId: SESSION, prompt: "继续", streamingBehavior: "followUp" });
  assert.equal(queued.delivery, "unknown", "a public queue boolean cannot prove this instruction was queued");
  assert.equal(queued.task.state, "running", "and the answer still states what the session is doing");
});

test("find selects the requested task among sessions sharing one project", async (t) => {
  const root = await fixtureRoot(t, "odk-id-");
  const runtimeDir = join(root, "run");
  const cwd = join(root, "project");
  await session(t, { sessionId: "11111111-1111-4111-8111-111111111111", runtimeDir, cwd });
  const second = await session(t, { sessionId: "22222222-2222-4222-8222-222222222222", runtimeDir, cwd });
  const reply = await runClient(t, undefined, `${JSON.stringify({ version: 1, requestId: "task-find", command: "status", taskId: second.ctx.sessionManager.getSessionId(), project: cwd })}\n`, { env: { ...process.env, XDG_RUNTIME_DIR: runtimeDir } });
  assert.equal(reply.code, 0, reply.stderr);
  assert.equal(JSON.parse(reply.stdout).ok, true);
  assert.equal(JSON.parse(reply.stdout).task.taskId, second.ctx.sessionManager.getSessionId());
});

test("Windows session hosting refuses before publishing an unprotected endpoint", async () => {
  const host = new SessionHost({ pi: { sendUserMessage() {} }, platform: "win32", env: { LOCALAPPDATA: "C:\\Users\\me\\AppData\\Local" } });
  const result = await host.start({ cwd: "/tmp", sessionManager: { getSessionId: () => SESSION }, isIdle: () => true });
  assert.equal(result.bound, false);
  assert.match(result.reason, /Windows/);
  assert.equal(host.endpoint, null);
  await host.close();
});

test("one connection dispatches a prompt only once despite another fragment", async (t) => {
  const h = await session(t, { idle: false });
  const wire = net.createConnection(h.socketPath);
  t.after(() => wire.destroy());
  await new Promise(resolve => wire.once("connect", resolve));
  wire.write(`${JSON.stringify({ version: 1, requestId: "once", command: "prompt", taskId: SESSION, project: h.cwd, prompt: "one instruction", streamingBehavior: "steer" })}\n`);
  while (h.sent.length === 0) await new Promise(resolve => setTimeout(resolve, 5));
  wire.write(" ");
  await new Promise(resolve => setTimeout(resolve, 40));
  assert.equal(h.sent.length, 1);
});

test("relay lists every live native session below a configured root", async (t) => {
  const root = await fixtureRoot(t, "odk-all-");
  const runtimeDir = join(root, "run");
  const first = await session(t, { cwd: join(root, "a"), runtimeDir, sessionId: "11111111-1111-4111-8111-111111111111" });
  const second = await session(t, { cwd: join(root, "b"), runtimeDir, sessionId: "22222222-2222-4222-8222-222222222222" });
  await writeFile(join(dirname(first.descriptorPath), "000-stale.json"), JSON.stringify({ version: 1, sessionId: "00000000-0000-4000-8000-000000000000", project: first.cwd, socketPath: join(root, "absent.sock") }));
  const answer = await runClient(t, undefined, `${JSON.stringify({ version: 1, requestId: "all", command: "list", project: root })}\n`, { env: { ...process.env, XDG_RUNTIME_DIR: runtimeDir } });
  assert.equal(answer.code, 0, answer.stderr);
  const frame = JSON.parse(answer.stdout);
  assert.equal(frame.ok, true);
  assert.deepEqual(frame.tasks.map(task => task.taskId).sort(), [first.ctx.sessionManager.getSessionId(), second.ctx.sessionManager.getSessionId()].sort());
});

test("native identity rejects wrong project and omitted task ID before delivery", async (t) => {
  const h = await session(t);
  for (const fields of [{ project: h.root, taskId: SESSION }, { project: h.cwd }]) {
    const frame = await h.ask({ version: 1, requestId: "identity", command: "prompt", prompt: "must not land", ...fields });
    assert.equal(frame.ok, false);
  }
  assert.equal(h.sent.length, 0);
});

test("native mutation ID is replayed once and rejects changed payload", async (t) => {
  const h = await session(t);
  const request = { version: 1, command: "prompt", project: h.cwd, taskId: SESSION, mutationId: "11111111-1111-4111-8111-111111111111", prompt: "once" };
  const first = await h.ask({ ...request, requestId: "first" });
  const replay = await h.ask({ ...request, requestId: "again" });
  assert.equal(replay.requestId, "again");
  assert.equal(replay.delivery, first.delivery);
  assert.equal(h.sent.length, 1);
  const changed = await h.ask({ ...request, requestId: "changed", prompt: "different" });
  assert.equal(changed.ok, false);
  assert.equal(h.sent.length, 1);
});

test("an existing queue is not evidence that a newly offered prompt was admitted", async (t) => {
  const h = await session(t, { idle: false, pending: 1, observe: false });
  const request = { version: 1, requestId: "unknown", command: "prompt", taskId: SESSION, project: h.cwd, prompt: "new instruction", streamingBehavior: "followUp", mutationId: "11111111-1111-4111-8111-111111111111" };
  const frame = await h.ask(request);
  assert.equal(frame.accepted, false);
  assert.equal(frame.delivery, "unknown");
  assert.equal(frame.task.lastDelivery.state, "unknown");
  h.host.observeMessage(user("new instruction"));
  const status = await h.ask({ version: 1, requestId: "observed", command: "status", taskId: SESSION, project: h.cwd });
  assert.equal(status.task.lastDelivery.state, "unknown");
});

test("an omitted streaming behavior follows native Enter with steer", async (t) => {
  const h = await session(t, { idle: false, observe: false });
  const answer = await h.ask({ version: 1, requestId: "native-enter", command: "prompt", taskId: SESSION, project: h.cwd, prompt: "continue" });
  assert.equal(answer.ok, true);
  assert.equal(answer.delivery, "unknown");
  assert.equal(h.sent[0].options.deliverAs, "steer");
});

test("multiline prompts remain intact while their admission stays unknown", async (t) => {
  const h = await session(t);
  const prompt = `继续第一行\n${"完整输入".repeat(400)}\n最后一行`;
  const answer = await h.ask({ version: 1, requestId: "multiline", command: "prompt", taskId: SESSION, project: h.cwd, prompt });
  assert.equal(answer.accepted, false);
  assert.equal(answer.submitted, true);
  assert.equal(answer.delivery, "unknown");
  assert.equal(h.sent[0].content, prompt);
});

test("status records each concurrent submission without certifying admission", async (t) => {
  const h = await session(t, { observe: false });
  const first = "11111111-1111-4111-8111-111111111111";
  const second = "22222222-2222-4222-8222-222222222222";
  await Promise.all([first, second].map((mutationId, index) => h.ask({ version: 1, requestId: `concurrent-${index}`, command: "prompt", taskId: SESSION, project: h.cwd, mutationId, prompt: `instruction ${index}` })));
  h.host.observeMessage(user("instruction 0"));
  const status = await h.ask({ version: 1, requestId: "reconcile", command: "status", taskId: SESSION, project: h.cwd });
  assert.deepEqual(status.task.deliveries, [{ mutationId: first, state: "unknown", submitted: true }, { mutationId: second, state: "unknown", submitted: true }]);
});

test("a fast observed turn retains its response and terminal outcome", async (t) => {
  const h = await session(t, { complete: true });
  const answer = await h.ask({ version: 1, requestId: "fast", command: "prompt", taskId: SESSION, project: h.cwd, prompt: "finish immediately" });
  assert.equal(answer.accepted, false);
  assert.equal(answer.submitted, true);
  assert.equal(answer.task.turnOutcome, "finished");
  assert.equal(answer.task.response, "completed immediately");
});

test("concurrent duplicates and malformed mutation IDs never add another delivery", async (t) => {
  const h = await session(t, { observe: false });
  const request = { version: 1, command: "prompt", project: h.cwd, taskId: SESSION, mutationId: "11111111-1111-4111-8111-111111111111", prompt: "one concurrent instruction" };
  const frames = await Promise.all(["one", "two"].map(requestId => h.ask({ ...request, requestId })));
  assert.equal(frames.every(frame => frame.delivery === "unknown"), true);
  assert.equal(h.sent.length, 1);
  const invalid = await h.ask({ ...request, requestId: "invalid", mutationId: "not-uuid" });
  assert.equal(invalid.ok, false);
  assert.equal(h.sent.length, 1);
});

test("identical steer consumed before follow-up cannot certify either mutation", async (t) => {
  const h = await session(t, { observe: false, idle: false });
  const ids = ["11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"];
  for (const [index, mutationId] of ids.entries()) await h.ask({ version: 1, requestId: `same-${index}`, command: "prompt", taskId: SESSION, project: h.cwd, mutationId, prompt: "identical", streamingBehavior: index === 0 ? "followUp" : "steer" });
  h.host.observeMessage(user("identical"));
  const status = await h.ask({ version: 1, requestId: "same-status", command: "status", taskId: SESSION, project: h.cwd });
  assert.deepEqual(status.task.deliveries.map(delivery => delivery.state), ["unknown", "unknown"]);
});

test("manual input with identical text cannot certify remote mutation delivery", async (t) => {
  const h = await session(t, { observe: false });
  await h.ask({ version: 1, requestId: "remote", command: "prompt", taskId: SESSION, project: h.cwd, mutationId: "11111111-1111-4111-8111-111111111111", prompt: "same as manual" });
  h.host.observeMessage(user("same as manual"));
  const status = await h.ask({ version: 1, requestId: "manual-status", command: "status", taskId: SESSION, project: h.cwd });
  assert.equal(status.task.lastDelivery.state, "unknown");
  assert.equal(status.task.prompt, "same as manual", "actual session execution remains observable separately");
});

test("a live endpoint dropping its list reply yields an incomplete inventory", async (t) => {
  const root = await fixtureRoot(t, "odk-part-");
  const runtimeDir = join(root, "run");
  const directory = join(runtimeDir, "open-deskos", "sessions");
  const project = join(root, "project");
  const socketPath = join(root, "live.sock");
  await mkdir(directory, { recursive: true });
  await mkdir(project);
  const sockets = new Set();
  const server = net.createServer(socket => {
    sockets.add(socket);
    socket.once("close", () => sockets.delete(socket));
    socket.on("data", data => {
      const request = JSON.parse(data.toString());
      if (request.command === "list") return socket.destroy();
      socket.end(`${JSON.stringify({ version: 1, requestId: request.requestId, ok: true, task: { taskId: SESSION, project, state: "settled" } })}\n`);
    });
  });
  await new Promise(resolve => server.listen(socketPath, resolve));
  t.after(async () => { for (const socket of sockets) socket.destroy(); await new Promise(resolve => server.close(resolve)); });
  await writeFile(join(directory, `${SESSION}.json`), JSON.stringify({ version: 1, sessionId: SESSION, project, socketPath }));
  const run = request => runClient(t, undefined, `${JSON.stringify({ version: 1, ...request })}\n`, { env: { ...process.env, XDG_RUNTIME_DIR: runtimeDir } });
  const status = await run({ requestId: "status-live", command: "status", taskId: SESSION, project });
  assert.equal(JSON.parse(status.stdout).task.taskId, SESSION);
  const listed = await run({ requestId: "list-drop", command: "list", project: root });
  assert.equal(listed.code, 0, listed.stderr);
  const inventory = JSON.parse(listed.stdout);
  assert.equal(inventory.ok, true);
  assert.deepEqual(inventory.tasks, []);
  assert.equal(inventory.incomplete, true);
  assert.equal(inventory.unavailable, 1);
});

test("aggregate inventory budgets the longest boolean metadata and newline", async (t) => {
  const root = await fixtureRoot(t, "odk-budget-");
  const runtimeDir = join(root, "run");
  const directory = join(runtimeDir, "open-deskos", "sessions");
  const project = join(root, "project");
  const socketPath = join(root, "budget.sock");
  await mkdir(directory, { recursive: true });
  await mkdir(project);
  let task;
  const server = net.createServer(socket => socket.once("data", data => {
    const request = JSON.parse(data.toString());
    socket.end(`${JSON.stringify({ version: 1, requestId: request.requestId, ok: true, tasks: [task], truncated: false })}\n`);
  }));
  await new Promise(resolve => server.listen(socketPath, resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  await writeFile(join(directory, `${SESSION}.json`), JSON.stringify({ version: 1, sessionId: SESSION, project, socketPath }));
  const requestId = "budget";
  const limit = 256 * 1024;
  for (const surplus of [2, 0]) {
    task = { taskId: SESSION, project, goal: "" };
    const base = Buffer.byteLength(`${JSON.stringify({ version: 1, requestId, ok: true, tasks: [task], truncated: false, unavailable: 0, incomplete: false })}\n`);
    task.goal = "x".repeat(limit - base + surplus);
    const answer = await runClient(t, undefined, `${JSON.stringify({ version: 1, requestId, command: "list", project: root })}\n`, { env: { ...process.env, XDG_RUNTIME_DIR: runtimeDir } });
    assert.equal(answer.code, 0, `surplus=${surplus}: ${answer.stderr}`);
    assert.ok(Buffer.byteLength(answer.stdout) <= limit);
    const inventory = JSON.parse(answer.stdout);
    assert.equal(inventory.tasks.length, surplus === 0 ? 1 : 0);
    assert.equal(inventory.truncated, surplus !== 0);
    assert.equal(inventory.incomplete, surplus !== 0);
  }
});

test("restricted relay refuses outside, broad, symlink and invalid requests before socket contact", async (t) => {
  const root = await fixtureRoot(t, "odk-guard-");
  const approved = join(root, "approved");
  const inside = join(approved, "project");
  const outside = join(root, "outside");
  const runtimeDir = join(root, "run");
  const directory = join(runtimeDir, "open-deskos", "sessions");
  await mkdir(inside, { recursive: true });
  await mkdir(outside);
  await mkdir(directory, { recursive: true });
  await symlink(outside, join(approved, "escape"));
  await symlink(inside, join(approved, "alias"));
  let contacts = 0;
  let forwarded;
  const socketPath = join(root, "guard.sock");
  const server = net.createServer(socket => {
    contacts += 1;
    socket.once("data", data => {
      const request = JSON.parse(data.toString());
      forwarded = request.project;
      socket.end(`${JSON.stringify({ version: 1, requestId: request.requestId, ok: true, task: { taskId: SESSION, project: request.project } })}\n`);
    });
  });
  await new Promise(resolve => server.listen(socketPath, resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const publish = project => writeFile(join(directory, `${SESSION}.json`), JSON.stringify({ version: 1, sessionId: SESSION, project, socketPath }));
  const invoke = (fields, args = ["--find", "--allow-root", approved]) => runClient(t, undefined, `${JSON.stringify({ version: 1, requestId: "guard", command: "status", taskId: SESSION, project: inside, ...fields })}\n`, { args, env: { ...process.env, XDG_RUNTIME_DIR: runtimeDir, SSH_ORIGINAL_COMMAND: "arbitrary command must be ignored" } });
  for (const fields of [
    { project: outside }, { project: root }, { project: join(approved, "escape") },
    { command: "end" }, { command: "launch", prompt: "anything" },
    { version: 2 }, { taskId: "invalid" }, { command: "prompt", prompt: "" }, { command: "status", unexpected: true },
    { taskId: [SESSION] }, { command: "cancel", mutationId: [SESSION] },
  ]) {
    await publish(fields.project ?? inside);
    const result = await invoke(fields);
    assert.equal(result.code, 0, result.stderr);
    const frame = JSON.parse(result.stdout);
    assert.equal(frame.requestId, "guard");
    assert.equal(frame.ok, false);
    assert.equal(contacts, 0, JSON.stringify(fields));
  }
  for (const args of [["--find", "--allow-root"], ["--find", `--allow-root=${approved}`], ["--find", "--allow-root", join(root, "missing")], ["--find", ...Array.from({ length: 17 }, () => ["--allow-root", approved]).flat()]]) {
    const result = await invoke({}, args);
    assert.equal(JSON.parse(result.stdout).ok, false);
    assert.equal(contacts, 0, "invalid operator root configuration fails closed");
  }
  const malformed = await runClient(t, undefined, "not JSON\n", { args: ["--find", "--allow-root", approved], env: { ...process.env, XDG_RUNTIME_DIR: runtimeDir } });
  assert.equal(JSON.parse(malformed.stdout).ok, false);
  assert.equal(contacts, 0, "malformed stdin cannot reach a socket");
  for (const project of [inside, join(approved, "alias")]) {
    await publish(project);
    const result = await invoke({ project });
    assert.equal(JSON.parse(result.stdout).ok, true);
    assert.equal(forwarded, project, "identity string is never rewritten after canonical admission");
  }
  await publish(outside);
  const unrestricted = await invoke({ project: outside }, ["--find"]);
  assert.equal(JSON.parse(unrestricted.stdout).ok, true, "ordinary legacy CLI remains unrestricted");
});

test("an explicitly approved filesystem root admits a controlled descendant", async (t) => {
  const h = await session(t);
  const reply = await runClient(t, undefined, `${JSON.stringify({ version: 1, requestId: "filesystem-root", command: "status", taskId: SESSION, project: h.cwd })}\n`, {
    args: ["--find", "--allow-root", "/"], env: { ...process.env, XDG_RUNTIME_DIR: h.runtimeDir },
  });
  assert.equal(reply.code, 0, reply.stderr);
  assert.equal(JSON.parse(reply.stdout).ok, true);
});
