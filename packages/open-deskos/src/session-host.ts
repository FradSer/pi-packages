import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { randomUUID } from "node:crypto";
import { chmod, lstat, mkdir, open, readFile, realpath, rename, stat, unlink } from "node:fs/promises";
import { readdirSync } from "node:fs";
import { createConnection, createServer, type Server, type Socket } from "node:net";
import { homedir } from "node:os";
import { dirname, isAbsolute, posix, relative, sep, win32 } from "node:path";
import { StringDecoder } from "node:string_decoder";
import { boundEventText, eventsFromMessage, promptFromMessage } from "./events.ts";
import type { HostedPiTurnOutcome } from "./types.ts";

/**
 * Make the session this process is drivable by a desk's voice agent, from inside that same
 * process.
 *
 * A reported session is read-only, and the only session a desk's voice agent can drive today is
 * a Hosted Pi that a separate daemon process started. This host is the third path: no new
 * process, no second credential, and nothing reachable over the network. The desk reaches it
 * over the user's own SSH session, and ownership of the file is the only gate.
 *
 * The wire contract is `integrations/voice-agent/src/task-protocol.mjs` in the Open DeskOS
 * repository: version 1, one bounded JSON line in, one correlated frame out, one frame per
 * connection, and a connection that sends no line closed without a frame. It is spoken here
 * rather than forked, and the Hosted Pi descriptor (`hosted-pi/endpoint.json`) is deliberately
 * never written, because a desk reads that path as a session host it can also start and end,
 * and this host can do neither.
 */

/** The protocol's own version and bounds, as `task-protocol.mjs` fixes them. */
export const SESSION_PROTOCOL_VERSION = 1;
export const SESSION_REQUEST_LIMIT = 64 * 1024;
export const SESSION_RESPONSE_LIMIT = 256 * 1024;
export const SESSION_REQUEST_TIMEOUT = 8000;

/** The protocol's own refusal vocabulary, so a desk reads what it already reads. */
const PROTOCOL_INVALID = "任务协议无效";
const REQUEST_TOO_LARGE = "请求过大";
const PROJECT_NOT_ADMITTED = "项目不在允许的开发目录内";
const UNKNOWN_COMMAND = "未知任务命令";
const TASK_NOT_FOUND = "未找到任务";
const PROMPT_INVALID = "任务 ID 或提示无效";
// Pi drops a user message that arrives while the agent is streaming unless the
// delivery says how to queue it, and an extension that re-sends a keyword can
// drop it even when the desk asked for a queue. Reporting that as accepted would
// tell a desk its instruction arrived when nothing did, so the delivery is
// verified here and an instruction that did not land is refused with this reason.
const DELIVERY_NOT_ACCEPTED = "指令未送达：该会话正在运行，且这条消息没有被排队";
/** One fixed reason for the four verbs a session host cannot serve at all. */
export const NOT_A_SESSION_HOST = "此端点是当前 Pi 会话，不是 Hosted Pi 任务服务";

/** Where this session answers, once it is bound. */
export interface SessionEndpointPaths {
  socketPath: string;
  descriptorPath: string;
}

export interface SessionEndpoint extends SessionEndpointPaths {
  /** False when the socket is served but the desk cannot find it. */
  published: boolean;
}

/** The outcome of a bind, so a caller can see a refusal instead of a silent endpoint. */
export interface SessionHostStart {
  bound: boolean;
  socketPath: string;
  descriptorPath: string;
  published: boolean;
  reason?: string;
}

export type SessionHostState = "running" | "settled";

/**
 * One session as a desk's voice agent reads it, in the same record shape a Hosted Pi answers
 * with, so one desk reads both without a second vocabulary. Nothing here is inferred: a field is
 * present only once it has been observed.
 */
export interface SessionHostTask {
  taskId: string;
  project: string;
  name?: string;
  lifecycle: "live";
  state: SessionHostState;
  activity: "working" | "idle";
  turnOutcome?: HostedPiTurnOutcome;
  /** The last thing this session was asked. */
  prompt: string;
  /** The most recent assistant text, when there is one. */
  response: string;
  /** What this session is doing right now, as the session card already names it. */
  latestActivity?: string;
  /** This host runs no verification step of its own. */
  verification: "not_run";
}

export interface SessionHostOptions {
  pi: Pick<ExtensionAPI, "sendUserMessage">;
  env?: NodeJS.ProcessEnv;
  platform?: NodeJS.Platform;
  /** The protocol's own request timeout, overridable so a test need not wait eight seconds. */
  requestTimeoutMs?: number;
}

/**
 * The one absolute path a desk and this session can both derive without configuring anything:
 * the session's runtime directory, which on Linux is the one the session manager itself owns.
 * The path flavour follows the platform this session runs on, so a Windows host gets a Windows
 * path from the same rule rather than a POSIX one.
 */
export function sessionRuntimeDir(env: NodeJS.ProcessEnv = process.env, platform: NodeJS.Platform = process.platform): string {
  const flavour = platform === "win32" ? win32 : posix;
  const runtimeDir = env.XDG_RUNTIME_DIR;
  if (typeof runtimeDir === "string" && runtimeDir.length > 0 && flavour.isAbsolute(runtimeDir)) return runtimeDir;
  if (platform === "win32") return env.LOCALAPPDATA && env.LOCALAPPDATA.length > 0 ? env.LOCALAPPDATA : flavour.join(homedir(), "AppData", "Local");
  return flavour.join(homedir(), ".local", "run");
}

/**
 * Where this session listens, and where it publishes that fact, both named after this
 * session so two sessions on one machine never collide. A single fixed endpoint per host
 * served whichever session bound it first and refused every later one, which is the
 * opposite of what a desk needs when the operator has several sessions and means one of
 * them by its project. The descriptor sits beside the socket, so a desk finds every
 * session's own path without reading this process's configuration.
 */
export function resolveSessionEndpoint(
  env: NodeJS.ProcessEnv = process.env,
  platform: NodeJS.Platform = process.platform,
  sessionId: string,
): SessionEndpointPaths {
  const runtimeDir = sessionRuntimeDir(env, platform);
  const override = env.ODK_SESSION_HOST_SOCKET ?? "";
  const flavour = platform === "win32" ? win32 : posix;
  // The variable names the directory, which is what keeps two sessions apart inside it.
  const directory = flavour.isAbsolute(override) ? override : flavour.join(runtimeDir, "open-deskos", "sessions");
  return {
    socketPath: flavour.join(directory, `${sessionId}.sock`),
    descriptorPath: flavour.join(directory, `${sessionId}.json`),
  };
}

function isRequest(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const request = value as Record<string, unknown>;
  return request.version === SESSION_PROTOCOL_VERSION
    && typeof request.requestId === "string"
    && request.requestId.length > 0
    && request.requestId.length <= 128;
}

/** The protocol's own text rule: bounded bytes that survive a UTF-8 round trip. */
function validText(value: unknown, limit: number): value is string {
  return typeof value === "string" && Buffer.byteLength(value) <= limit && Buffer.from(value).toString("utf8") === value;
}

function within(root: string, path: string): boolean {
  const suffix = relative(root, path);
  return suffix === "" || (suffix !== ".." && !suffix.startsWith(`..${sep}`) && !isAbsolute(suffix));
}

async function privateDirectory(directory: string): Promise<void> {
  await mkdir(directory, { recursive: true, mode: 0o700 });
  // Best effort: a platform without mode bits has nothing to enforce here.
  await chmod(directory, 0o700).catch(() => {});
}

/** True when something is still listening at the path, which is what makes a socket live. */
function liveSocket(socketPath: string): Promise<boolean> {
  return new Promise((resolve, reject) => {
    const probe = createConnection(socketPath);
    const timer = setTimeout(() => { probe.destroy(); reject(new Error("无法确定任务服务是否运行")); }, 1000);
    probe.once("connect", () => { clearTimeout(timer); probe.destroy(); resolve(true); });
    probe.once("error", (error: NodeJS.ErrnoException) => {
      clearTimeout(timer);
      probe.destroy();
      if (error.code === "ECONNREFUSED") resolve(false);
      else reject(error);
    });
  });
}

/**
 * A socket file left by a session that is gone is removed before this one binds; one that another
 * live host still owns is never taken over, because two hosts answering on one path would each
 * look like half an answer.
 */
async function clearStaleSocket(socketPath: string): Promise<void> {
  let info;
  try {
    info = await lstat(socketPath);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
    throw error;
  }
  if (!info.isSocket() || info.uid !== process.getuid?.()) throw new Error("任务套接字路径已占用");
  if (await liveSocket(socketPath)) throw new Error("任务服务已运行");
  await unlink(socketPath);
}

/** Remove this host's own socket once nothing answers at it any more. */
async function removeOwnSocket(socketPath: string): Promise<void> {
  try {
    const info = await lstat(socketPath);
    if (!info.isSocket() || info.uid !== process.getuid?.()) return;
    if (await liveSocket(socketPath)) return;
    await unlink(socketPath);
  } catch {
    // A socket that is already gone is the state this wants.
  }
}

export class SessionHost {
  readonly #pi: Pick<ExtensionAPI, "sendUserMessage">;
  readonly #env: NodeJS.ProcessEnv;
  readonly #platform: NodeJS.Platform;
  #paths: SessionEndpointPaths;
  readonly #timeoutMs: number;
  readonly #sockets = new Set<Socket>();
  /** Serializes bind and unbind, so a reload cannot leave two hosts on one path. */
  #lifecycle: Promise<void> = Promise.resolve();
  #ctx: ExtensionContext | null = null;
  #server: Server | null = null;
  #bound: SessionEndpoint | null = null;
  #realProject = "";
  #sessionId = "";
  #state: SessionHostState = "settled";
  #outcome: HostedPiTurnOutcome | undefined = undefined;
  /** Whether an assistant message has already stated how the current turn ended. */
  #observed = false;
  #cancelRequested = false;
  /** Set when a bind replaced a session whose turn was still running here. */
  #interrupted = false;
  #goal = "";
  #response = "";
  #latestActivity: string | undefined = undefined;

  constructor(options: SessionHostOptions) {
    this.#pi = options.pi;
    this.#env = options.env ?? process.env;
    this.#platform = options.platform ?? process.platform;
    this.#paths = resolveSessionEndpoint(this.#env, this.#platform, "unbound");
    this.#timeoutMs = options.requestTimeoutMs ?? SESSION_REQUEST_TIMEOUT;
  }

  /** Where this session answers, or null while it is not bound. */
  get endpoint(): SessionEndpoint | null {
    return this.#bound;
  }

  /**
   * Bind the endpoint for the session that is starting, replacing any previous bind. A reload
   * arrives here like every other session start, and a failure is a returned reason rather than
   * a thrown error, because a session must survive a machine that cannot spare an endpoint.
   */
  start(ctx: ExtensionContext): Promise<SessionHostStart> {
    const bind = this.#lifecycle.then(() => this.#bind(ctx), () => this.#bind(ctx));
    this.#lifecycle = bind.then(() => {}, () => {});
    return bind;
  }

  /** Close the endpoint. Idempotent, and safe before any bind or after a failed one. */
  close(): Promise<void> {
    const unbind = this.#lifecycle.then(() => this.#unbind(), () => this.#unbind());
    this.#lifecycle = unbind.then(() => {}, () => {});
    return unbind;
  }

  /** `agent_start`: a turn is running now, so the previous outcome no longer answers for it. */
  markRunning(): void {
    this.#state = "running";
    this.#outcome = undefined;
    this.#observed = false;
    this.#cancelRequested = false;
    this.#interrupted = false;
    this.#response = "";
  }

  /** `agent_settled`: the turn ended. Only an abort this host asked for is claimed here. */
  markSettled(): void {
    this.#state = "settled";
    if (!this.#observed && this.#cancelRequested) this.#outcome = "cancelled";
  }

  /** `message_end`: the prompt that was sent, or the reply that came back. */
  observeMessage(message: unknown): void {
    const goal = promptFromMessage(message);
    if (goal.length > 0) this.#goal = goal;
    if ((message as { role?: unknown } | null)?.role !== "assistant") return;
    for (const event of eventsFromMessage(message)) {
      if (event.kind === "assistant") this.#response = event.text;
    }
    // The stop reason belongs to the message, whether or not it carried text: a turn the
    // provider failed has no reply and must still be observed as failed.
    const stopReason = (message as { stopReason?: unknown }).stopReason;
    if (stopReason === "stop") this.#stateOutcome("finished");
    else if (stopReason === "aborted") this.#stateOutcome("cancelled");
    // A tool call, a pending, or a deferred message means the turn continues, so it says
    // nothing about how the turn ends and nothing is claimed for it.
    else if (typeof stopReason === "string" && !["toolUse", "pending", "deferred"].includes(stopReason)) this.#stateOutcome("failed");
  }

  /** `tool_execution_start`: the newest thing the session is doing, as a short summary. */
  observeActivity(activity: string): void {
    const summary = boundEventText(activity);
    if (summary.length > 0) this.#latestActivity = summary;
  }

  async #bind(ctx: ExtensionContext): Promise<SessionHostStart> {
    await this.#unbind();
    const previousSessionId = this.#sessionId;
    this.#interrupted = this.#state === "running";
    if (previousSessionId !== ctx.sessionManager.getSessionId()) {
      // A different session has never been asked or answered anything, so the previous
      // session's goal and reply would be a claim about the wrong session.
      this.#goal = "";
      this.#response = "";
      this.#latestActivity = undefined;
    }
    this.#ctx = ctx;
    this.#sessionId = ctx.sessionManager.getSessionId();
    // The endpoint belongs to this session, so it is resolved here rather than once for
    // the process: a reload that switches sessions moves this session's own socket.
    this.#paths = resolveSessionEndpoint(this.#env, this.#platform, this.#sessionId);
    this.#state = ctx.isIdle() ? "settled" : "running";
    this.#outcome = undefined;
    this.#observed = false;
    this.#cancelRequested = false;
    this.#realProject = await this.#resolve(ctx.cwd);
    const socketPath = this.#paths.socketPath;
    try {
      await privateDirectory(dirname(socketPath));
      await clearStaleSocket(socketPath);
      this.#server = await this.#listen(socketPath);
      this.#bound = { ...this.#paths, published: false };
    } catch (error) {
      this.#ctx = null;
      this.#server = null;
      this.#bound = null;
      return { bound: false, socketPath, descriptorPath: this.#paths.descriptorPath, published: false, reason: reasonOf(error) };
    }
    // A host that cannot publish keeps answering, and says so, rather than failing both the
    // voice path and the discovery path over one file.
    let published = false;
    let reason: string | undefined;
    try {
      await this.#publish(socketPath);
      published = true;
    } catch (error) {
      reason = reasonOf(error);
    }
    this.#bound = { ...this.#paths, published };
    return { bound: true, socketPath, descriptorPath: this.#paths.descriptorPath, published, ...(reason === undefined ? {} : { reason }) };
  }

  async #unbind(): Promise<void> {
    const server = this.#server;
    const bound = this.#bound;
    this.#server = null;
    this.#bound = null;
    this.#ctx = null;
    for (const socket of this.#sockets) socket.destroy();
    this.#sockets.clear();
    if (server) {
      await new Promise<void>((resolve) => { server.close(() => resolve()); });
    }
    if (!bound) return;
    await this.#removeOwnDescriptor(bound.descriptorPath, bound.socketPath);
    await removeOwnSocket(bound.socketPath);
  }

  /** Publish where this session listens, beside itself, so a desk never reads this process's configuration. */
  async #publish(socketPath: string): Promise<void> {
    const file = this.#paths.descriptorPath;
    await privateDirectory(dirname(file));
    const temporary = `${file}.${randomUUID()}.tmp`;
    const handle = await open(temporary, "wx", 0o600);
    try {
      await handle.writeFile(JSON.stringify({
        version: SESSION_PROTOCOL_VERSION,
        sessionId: this.#sessionId,
        socketPath,
        project: this.#ctx?.cwd ?? "",
        state: this.#state,
      }));
      await handle.sync();
    } finally {
      await handle.close();
    }
    try {
      await rename(temporary, file);
    } finally {
      await unlink(temporary).catch((error: NodeJS.ErrnoException) => { if (error.code !== "ENOENT") throw error; });
    }
    await chmod(file, 0o600).catch(() => {});
  }

  /** Remove the descriptor only when it is still the one this bind wrote. */
  async #removeOwnDescriptor(file: string, socketPath: string): Promise<void> {
    try {
      const descriptor = JSON.parse(await readFile(file, "utf8")) as { version?: unknown; socketPath?: unknown };
      if (descriptor?.version !== SESSION_PROTOCOL_VERSION || descriptor.socketPath !== socketPath) return;
    } catch {
      return;
    }
    await unlink(file).catch(() => {});
  }

  /** Every session on this machine, as its own descriptor, so a desk can choose one. */
  static listEndpoints(env: NodeJS.ProcessEnv = process.env, platform: NodeJS.Platform = process.platform): string[] {
    const flavour = platform === "win32" ? win32 : posix;
    const override = env.ODK_SESSION_HOST_SOCKET ?? "";
    const directory = flavour.isAbsolute(override) && !override.endsWith(".sock") ? override : flavour.join(sessionRuntimeDir(env, platform), "open-deskos", "sessions");
    try {
      return readdirSync(directory).filter((name) => name.endsWith(".json")).map((name) => flavour.join(directory, name));
    } catch {
      return [];
    }
  }

  async #resolve(path: string): Promise<string> {
    try {
      return await realpath(path);
    } catch {
      return path;
    }
  }

  #listen(socketPath: string): Promise<Server> {
    return new Promise<Server>((resolve, reject) => {
      const server = createServer((socket) => { this.#serve(socket); });
      server.once("error", reject);
      // The endpoint must never be the reason a Pi process stays alive: a desk
      // reaching this session is not a reason this session cannot be closed.
      server.unref();
      server.listen(socketPath, () => {
        server.off("error", reject);
        resolve(server);
      });
    }).then(async (server) => {
      // Ownership is the gate, so the socket is nobody else's to connect to.
      await chmod(socketPath, 0o600).catch(() => {});
      return server;
    });
  }

  /** One connection carries one bounded line in and one frame out, and nothing else. */
  #serve(socket: Socket): void {
    this.#sockets.add(socket);
    socket.on("error", () => {});
    socket.once("close", () => { this.#sockets.delete(socket); });
    socket.setTimeout(this.#timeoutMs, () => socket.destroy());
    const decoder = new StringDecoder("utf8");
    let pending = "";
    let answered = false;
    const close = (frame?: string): void => {
      if (answered) return;
      answered = true;
      if (frame === undefined) socket.destroy();
      else socket.end(frame);
    };
    socket.on("data", (chunk) => {
      if (answered) return;
      pending += decoder.write(chunk);
      if (Buffer.byteLength(pending) > SESSION_REQUEST_LIMIT) return close();
      const newline = pending.indexOf("\n");
      if (newline < 0) return;
      // One frame per connection: a second line is not a second request.
      if (pending.slice(newline + 1).trim().length > 0) return close();
      let request: unknown;
      try {
        request = JSON.parse(pending.slice(0, newline));
      } catch {
        return close();
      }
      this.#respond(request).then((response) => {
        const frame = `${JSON.stringify(response)}\n`;
        close(Buffer.byteLength(frame) > SESSION_RESPONSE_LIMIT ? undefined : frame);
      }, () => close());
    });
    // A connection that ends without a line is closed without a frame, rather than held
    // open until the request timeout.
    socket.once("end", () => close());
  }

  async #respond(request: unknown): Promise<object> {
    const base = { version: SESSION_PROTOCOL_VERSION, requestId: typeof (request as { requestId?: unknown } | null)?.requestId === "string" ? (request as { requestId: string }).requestId : "" };
    try {
      return { ...base, ok: true, ...(await this.#dispatch(request)) };
    } catch (error) {
      return { ...base, ok: false, error: reasonOf(error) };
    }
  }

  async #dispatch(request: unknown): Promise<Record<string, unknown>> {
    if (!isRequest(request)) throw new Error(PROTOCOL_INVALID);
    if (Buffer.byteLength(JSON.stringify(request)) > SESSION_REQUEST_LIMIT) throw new Error(REQUEST_TOO_LARGE);
    const ctx = this.#ctx;
    if (!ctx) throw new Error(TASK_NOT_FOUND);
    if (request.command === "list") {
      await this.#admit(request.project);
      const { prompt, response, ...entry } = this.#task();
      return { tasks: [{ ...entry, goal: prompt }], truncated: false };
    }
    if (request.command === "status") {
      this.#ownTask(request.taskId);
      return { task: this.#task() };
    }
    if (request.command === "prompt") {
      this.#ownTask(request.taskId);
      this.#deliver(request.prompt, request.streamingBehavior);
      return { task: this.#task(), accepted: true };
    }
    if (request.command === "cancel") {
      this.#ownTask(request.taskId);
      this.#cancelRequested = true;
      ctx.abort();
      return { task: this.#task(), accepted: true };
    }
    if (["start", "launch", "end", "history"].includes(request.command as string)) throw new Error(NOT_A_SESSION_HOST);
    throw new Error(UNKNOWN_COMMAND);
  }

  /** This process is one session, so any other task identity is a task this host does not have. */
  #ownTask(taskId: unknown): void {
    if (taskId !== undefined && taskId !== this.#sessionId) throw new Error(TASK_NOT_FOUND);
  }

  /**
   * A project scope covers this session's own project and everything inside it, which is the
   * only tree this process can answer for.
   */
  async #admit(project: unknown): Promise<void> {
    if (project === undefined || project === null) return;
    if (typeof project !== "string" || !isAbsolute(project) || /[\x00-\x1f\x7f]/.test(project)) throw new Error(PROJECT_NOT_ADMITTED);
    let resolved: string;
    try {
      resolved = await realpath(project);
      if (!(await stat(resolved)).isDirectory()) throw new Error(PROJECT_NOT_ADMITTED);
    } catch {
      throw new Error(PROJECT_NOT_ADMITTED);
    }
    if (!within(this.#realProject, resolved)) throw new Error(PROJECT_NOT_ADMITTED);
  }

  /** Refuse an unusable instruction before anything is delivered into the session. */
  #deliver(prompt: unknown, streamingBehavior: unknown): void {
    if (!validText(prompt, SESSION_REQUEST_LIMIT) || prompt.trim().length === 0) throw new Error(PROMPT_INVALID);
    const ctx = this.#ctx;
    if (!ctx) throw new Error(TASK_NOT_FOUND);
    // Only the two behaviors the protocol names are delivered as a behavior; anything else is
    // delivered as an ordinary message rather than guessed into a delivery mode.
    const behavior: "steer" | "followUp" | undefined =
      streamingBehavior === "steer" || streamingBehavior === "followUp" ? streamingBehavior : undefined;
    const wasIdle = ctx.isIdle();
    this.#pi.sendUserMessage(prompt, behavior === undefined ? undefined : { deliverAs: behavior });
    // An idle session runs the message at once, and a running one either queues it
    // or loses it. Only the queue is observable from here, so that is what decides
    // whether this desk may report the instruction as delivered.
    if (!wasIdle && !ctx.hasPendingMessages()) throw new Error(DELIVERY_NOT_ACCEPTED);
    this.#outcome = undefined;
    this.#observed = false;
    this.#cancelRequested = false;
    this.#interrupted = false;
    this.#response = "";
  }

  #stateOutcome(outcome: HostedPiTurnOutcome): void {
    this.#outcome = outcome;
    this.#observed = true;
  }

  #task(): SessionHostTask {
    const ctx = this.#ctx;
    const name = ctx?.sessionManager.getSessionName();
    const turnOutcome = this.#outcome ?? (this.#interrupted ? "interrupted" : undefined);
    return {
      taskId: ctx?.sessionManager.getSessionId() ?? this.#sessionId,
      project: ctx?.cwd ?? "",
      ...(name === undefined ? {} : { name }),
      lifecycle: "live",
      state: this.#state,
      activity: this.#state === "running" ? "working" : "idle",
      ...(turnOutcome === undefined ? {} : { turnOutcome }),
      prompt: this.#goal,
      response: this.#response,
      ...(this.#latestActivity === undefined ? {} : { latestActivity: this.#latestActivity }),
      verification: "not_run",
    };
  }
}

function reasonOf(error: unknown): string {
  return error instanceof Error && !("code" in error) ? error.message : "任务请求失败";
}
