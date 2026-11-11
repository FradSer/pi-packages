import { AsyncLocalStorage } from "node:async_hooks";
import { createHash, randomUUID } from "node:crypto";
import { closeSync, constants, fstatSync, lstatSync, mkdirSync, openSync, readdirSync, writeSync } from "node:fs";
import path from "node:path";
import { isPromise } from "node:util/types";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { containsSensitiveMemoryMaterial } from "./consolidation-run.ts";
import { memoryConfigPath, readDebugConfigState, writeUnifiedConfig } from "./config.ts";
import { canonicalProjectCwd } from "./memory-paths.ts";

const MAX_RECORD_BYTES = 64 * 1024;
const SEGMENT_BYTES = 4 * 1024 * 1024;
const CONTEXT_ENTRIES = 12;
const STORAGE_NOTICE = "[continual-learning] Debug logging unavailable; plugin behavior is unchanged. Use /learning debug to inspect the private log location.";
type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
type Phase = "started" | "completed" | "failed" | "observed";
interface Binding {
  journal: LearningDebug;
  invocationId: string;
  source: string;
  context: Record<string, unknown>;
  nativeContext: unknown;
  projectCwd: string;
  parentInvocationId: string | null;
}
const active = new AsyncLocalStorage<Binding>();
interface LifecycleBatch { key: string; event: string; sessionId: unknown; rows: Array<Record<string, unknown>>; timer: ReturnType<typeof setTimeout>; sources: Set<string>; cwd: string; contextRef: string }
const lifecycleBatches = new Map<string, LifecycleBatch>();
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object";
const sha256 = (text: string | Uint8Array): string => createHash("sha256").update(text).digest("hex");

function omitted(value: string, reason: string): Json {
  return { omitted: reason, sha256: sha256(value), bytes: Buffer.byteLength(value) };
}

export function sanitizeDebugValue(value: unknown): Json {
  let remaining = 24 * 1024, nodes = 256;
  const seen = new Set<object>();
  const string = (text: string): Json => {
    if (text.length > 1024 * 1024) return omitted(text, "oversized");
    if (containsSensitiveMemoryMaterial(text)) return omitted(text, "redacted");
    const bytes = Buffer.byteLength(text), available = Math.min(4096, remaining);
    remaining -= Math.min(bytes, available);
    if (bytes <= available) return text;
    return { preview: Buffer.from(text).subarray(0, available).toString("utf8"), omitted: "truncated", bytes, sha256: sha256(text) };
  };
  const visit = (current: unknown, depth: number): Json => {
    if (current === null || current === undefined) return null;
    if (typeof current === "boolean") return current;
    if (typeof current === "number") return Number.isFinite(current) ? current : String(current);
    if (typeof current === "bigint") return String(current);
    if (typeof current === "string") return string(current);
    if (typeof current !== "object") return { omitted: typeof current };
    if (seen.has(current)) return { omitted: "cycle" };
    if (depth > 8 || nodes-- <= 0) return { omitted: "structure-bound" };
    if (current instanceof Uint8Array) return { omitted: "binary", bytes: current.byteLength, sha256: sha256(current) };
    if (current instanceof Error) return { name: string(current.name), message: string(current.message), stack: string(current.stack ?? "") };
    seen.add(current);
    try {
      const descriptors = Object.getOwnPropertyDescriptors(current);
      if (descriptors.type?.value === "image" || descriptors.type?.value === "audio") return { omitted: "binary-content", type: descriptors.type.value };
      if (Array.isArray(current)) {
        const count = Math.min(current.length, 48), rows: Json[] = [];
        for (let i = 0; i < count; i++) rows.push(visit(descriptors[String(i)]?.value, depth + 1));
        if (current.length > count) rows.push({ omitted: "array-bound", omittedItems: current.length - count });
        return rows;
      }
      const entries = Object.entries(descriptors), result: { [key: string]: Json } = {};
      for (const [key, descriptor] of entries.slice(0, 48)) {
        const safeKey = key.length <= 128 && !containsSensitiveMemoryMaterial(key) ? key : `key-sha256:${sha256(key)}`;
        if (!Object.hasOwn(descriptor, "value")) { result[safeKey] = { omitted: "accessor" }; continue; }
        const numericUsage = /^(?:inputTokens|outputTokens|totalTokens|cacheReadTokens|cacheWriteTokens|tokenCount|maxTokens)$/i.test(key)
          && typeof descriptor.value === "number" && Number.isFinite(descriptor.value);
        if (/(?:headers|^auth$|authorization|credentials?|password|passwd|secret|token|api[_-]?key|environment|^env$)/i.test(key)
          && !numericUsage) {
          result[safeKey] = typeof descriptor.value === "string" ? omitted(descriptor.value, "redacted") : { omitted: "redacted" };
        } else result[safeKey] = visit(descriptor.value, depth + 1);
      }
      if (entries.length > 48) result.debugOmittedFields = entries.length - 48;
      return result;
    } finally { seen.delete(current); }
  };
  return visit(value, 0);
}

export function debugDirectory(cwd: string, agentDir = getAgentDir()): string {
  return path.join(canonicalProjectCwd(agentDir), "continual-learning", "debug", sha256(canonicalProjectCwd(cwd)));
}

function callMethod(target: unknown, name: string): unknown {
  if (!object(target)) return undefined;
  const method = target[name];
  return typeof method === "function" ? Reflect.apply(method, target, []) : undefined;
}

function captureContext(ctx: unknown): Record<string, unknown> {
  const source = object(ctx) ? ctx : {};
  const manager = source.sessionManager;
  const branch = callMethod(manager, "getBranch");
  const entries = Array.isArray(branch) ? branch : [];
  const model = object(source.model) ? { provider: source.model.provider, id: source.model.id } : undefined;
  const cwd = canonicalProjectCwd(typeof source.cwd === "string" ? source.cwd : process.cwd());
  return {
    cwd, projectId: sha256(cwd),
    sessionId: callMethod(manager, "getSessionId") ?? null,
    sessionFile: callMethod(manager, "getSessionFile") ?? null,
    parentEntryId: callMethod(manager, "getLeafId") ?? null,
    mode: source.mode ?? null, model,
    entryCount: entries.length, omittedEntries: Math.max(0, entries.length - CONTEXT_ENTRIES),
    entries: entries.slice(-CONTEXT_ENTRIES),
  };
}

function outcome(value: unknown): string {
  if (!object(value)) return "completed";
  try {
    const fields = Object.getOwnPropertyDescriptors(value);
    if (fields.block?.value === true) return "blocked";
    if (fields.isError?.value === true) return "failed";
    const details = fields.details?.value;
    const status = object(details) ? Object.getOwnPropertyDescriptor(details, "status")?.value : undefined;
    if (fields.cancelled?.value === true || status === "cancelled") return "cancelled";
    return typeof status === "string" ? status : "completed";
  } catch { return "completed"; }
}

function compactToolDefinitions(entries: unknown[]): unknown[] {
  return entries.map(entry => {
    if (!object(entry)) return entry;
    const message = entry.message;
    if (!object(message) || !Array.isArray(message.toolsAdded)) return entry;
    return { ...entry, message: { ...message, toolsAdded: message.toolsAdded.map(tool => {
      if (!object(tool)) return tool;
      const parameters = object(tool.parameters) ? tool.parameters : undefined;
      const properties = parameters && object(parameters.properties) ? Object.keys(parameters.properties) : [];
      return { name: tool.name, description: typeof tool.description === "string" ? tool.description.slice(0, 300) : undefined,
        parameterNames: properties, parameterCount: properties.length };
    }) } };
  });
}

function asynchronous(value: unknown): boolean {
  if (isPromise(value)) return true;
  if (!object(value)) return false;
  try { return typeof Object.getOwnPropertyDescriptor(value, "then")?.value === "function"; }
  catch { return false; }
}

interface Segment { file: string; dev: number; ino: number; bytes: number }

export class LearningDebug {
  private readonly agentDir = canonicalProjectCwd(getAgentDir());
  private readonly writerId = `${new Date().toISOString().replace(/[:.]/g, "-")}-${process.pid}-${randomUUID()}`;
  private readonly segments = new Map<string, Segment>();
  private readonly hosts = new WeakMap<object, { proxy: object; source: string }>();
  private readonly contextDigests = new Set<string>();
  private readonly inFlight = new Set<string>();
  private sequence = 0;
  private warned = false;
  private unavailable = false;

  status(cwd: string): { enabled: boolean; directory: string; unavailable: boolean; segmentCount: number; totalBytes: number; retention: string; invalid?: string } {
    let files: string[] = [], totalBytes = 0;
    try {
      const directory = debugDirectory(cwd, this.agentDir);
      files = readdirSync(directory).filter(name => name.endsWith(".jsonl"));
      for (const name of files) totalBytes += lstatSync(path.join(directory, name)).size;
    } catch { /* 缺目录视为零分段。 */ }
    return { ...readDebugConfigState(), directory: debugDirectory(cwd, this.agentDir), unavailable: this.unavailable,
      segmentCount: files.length, totalBytes, retention: "manual" };
  }

  noteProcessExit(reason: string, exitCode: number | null, ctx?: unknown, cwd = process.cwd()): void {
    const binding = active.getStore(), projectCwd = binding?.projectCwd ?? canonicalProjectCwd(cwd);
    const context = { projectId: sha256(projectCwd), sessionId: binding?.context.sessionId ?? null,
      cwd: projectCwd };
    if (!readDebugConfigState().enabled) return;
    try { this.append(projectCwd, { kind: "continual-learning-debug", version: 1, timestamp: new Date().toISOString(),
      pid: process.pid, source: "extensions/debug.ts", event: "process:exit", phase: "observed", outcome: "exited",
      invocationId: randomUUID(), parentInvocationId: binding?.invocationId ?? null, context,
      data: { reason, exitCode } }); }
    catch { this.warn(ctx); }
  }

  private emitContextSnapshot(cwd: string, context: Record<string, unknown>, digest: string, parentInvocationId: string | null, ctx?: unknown): void {
    if (this.contextDigests.has(digest)) return;
    const compact = { ...context, entries: compactToolDefinitions(Array.isArray(context.entries) ? context.entries : []) };
    try {
      this.append(cwd, { kind: "continual-learning-debug", version: 1, timestamp: new Date().toISOString(),
        pid: process.pid, source: "extensions/debug.ts", event: "context:snapshot", phase: "observed", outcome: "observed",
        invocationId: randomUUID(), parentInvocationId, contextDigest: digest,
        context: { projectId: sha256(cwd), sessionId: context.sessionId }, data: { context: compact } });
      this.contextDigests.add(digest);
    } catch { this.warn(ctx); }
  }

  private compactContext(context: Record<string, unknown>, cwd: string): { context: Record<string, unknown>; contextRef: string } {
    const projectId = typeof context.projectId === "string" ? context.projectId : sha256(cwd);
    const digest = sha256(JSON.stringify({ ...context, entries: compactToolDefinitions(Array.isArray(context.entries) ? context.entries : []) }));
    return { context: { cwd: projectId, projectId, sessionId: context.sessionId ?? null,
      sessionFile: context.sessionFile ?? null, parentEntryId: context.parentEntryId ?? null,
      mode: context.mode ?? null, model: context.model ?? null,
      entryCount: context.entryCount ?? 0, omittedEntries: context.omittedEntries ?? 0, entries: { omitted: "contextRef" } },
      contextRef: digest };
  }

  private compactRecord(cwd: string, value: Record<string, unknown>, context: Record<string, unknown>): Record<string, unknown> {
    const compact = this.compactContext(context, cwd);
    return { ...value, context: compact.context, contextRef: compact.contextRef, contextDigest: compact.contextRef };
  }

  private warn(ctx: unknown): void {
    this.unavailable = true;
    if (this.warned) return;
    this.warned = true;
    try {
      const ui = object(ctx) && object(ctx.ui) ? ctx.ui : undefined;
      if (typeof ui?.notify === "function") Reflect.apply(ui.notify, ui, [STORAGE_NOTICE, "warning"]);
      else process.stderr.write(STORAGE_NOTICE + "\n");
    } catch { /* 观测失败不能影响原操作。 */ }
  }

  private ensureDirectory(cwd: string): string {
    mkdirSync(this.agentDir, { recursive: true, mode: 0o700 });
    const directory = debugDirectory(cwd, this.agentDir);
    for (const child of [this.agentDir, path.join(this.agentDir, "continual-learning"), path.join(this.agentDir, "continual-learning", "debug"), directory]) {
      try { mkdirSync(child, { mode: 0o700 }); }
      catch (error) { if (!object(error) || error.code !== "EEXIST") throw error; }
      const stat = lstatSync(child);
      if (stat.isSymbolicLink() || !stat.isDirectory() || (child !== this.agentDir && (stat.mode & 0o077) !== 0)) throw Error("Unsafe debug directory");
    }
    return directory;
  }

  private append(cwd: string, value: Record<string, unknown>): void {
    if (value.event !== "context:snapshot" && typeof value.contextRef === "string" && object(value.contextSnapshot)) {
      try { this.emitContextSnapshot(cwd, value.contextSnapshot, value.contextRef, null); }
      catch { /* 快照缺失在检查器里显式报告，不改变原操作。 */ }
    }
    const safeContext = sanitizeDebugValue(value.context);
    const safeData = sanitizeDebugValue(value.data);
    const envelope = sanitizeDebugValue({ ...value, context: null, data: null });
    const safe = object(envelope) ? { ...envelope, context: safeContext, data: safeData } : envelope;
    let line = JSON.stringify(safe) + "\n";
    if (Buffer.byteLength(line) > MAX_RECORD_BYTES && object(safe)) {
      const compactContext = object(safe.context) ? { ...safe.context, entries: { omitted: "record-bound" } } : safe.context;
      line = JSON.stringify({ ...safe, context: compactContext }) + "\n";
      if (Buffer.byteLength(line) > MAX_RECORD_BYTES) {
        line = JSON.stringify({ ...safe, context: compactContext, data: omitted(JSON.stringify(safe.data), "record-bound") }) + "\n";
      }
    }
    if (Buffer.byteLength(line) > MAX_RECORD_BYTES) throw Error("Debug record exceeds bound");
    const directory = this.ensureDirectory(cwd);
    let segment = this.segments.get(directory), fd: number | undefined;
    try {
      if (!segment || segment.bytes + Buffer.byteLength(line) > SEGMENT_BYTES) {
        const file = path.join(directory, `${this.writerId}-${String(this.sequence++).padStart(5, "0")}.jsonl`);
        fd = openSync(file, constants.O_WRONLY | constants.O_APPEND | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW | constants.O_NONBLOCK, 0o600);
        const stat = fstatSync(fd);
        segment = { file, dev: stat.dev, ino: stat.ino, bytes: 0 };
        this.segments.set(directory, segment);
      } else {
        const stat = lstatSync(segment.file);
        if (!stat.isFile() || stat.isSymbolicLink() || stat.dev !== segment.dev || stat.ino !== segment.ino || stat.size !== segment.bytes) throw Error("Debug log changed");
        fd = openSync(segment.file, constants.O_WRONLY | constants.O_APPEND | constants.O_NOFOLLOW | constants.O_NONBLOCK);
      }
      const opened = fstatSync(fd);
      if (!opened.isFile() || opened.dev !== segment.dev || opened.ino !== segment.ino || opened.nlink !== 1 || (opened.mode & 0o077) !== 0) throw Error("Unsafe debug log");
      this.ensureDirectory(cwd);
      const named = lstatSync(segment.file);
      if (named.dev !== opened.dev || named.ino !== opened.ino || named.isSymbolicLink()) throw Error("Debug log replaced");
      const bytes = Buffer.from(line);
      let offset = 0;
      while (offset < bytes.length) {
        const count = writeSync(fd, bytes, offset, bytes.length - offset);
        if (count <= 0) throw Error("Debug append made no progress");
        offset += count;
      }
      segment.bytes += bytes.length;
      this.unavailable = false;
    } finally { if (fd !== undefined) closeSync(fd); }
  }

  record(source: string, event: string, data: unknown, phase: Phase = "observed", result = "observed", binding = active.getStore()): void {
    try {
      if (!readDebugConfigState().enabled) return;
      const context = binding?.context ?? captureContext({ cwd: process.cwd() });
      const cwd = binding?.projectCwd ?? (typeof context.cwd === "string" ? context.cwd : process.cwd());
      const row = { kind: "continual-learning-debug", version: 1, timestamp: new Date().toISOString(),
        pid: process.pid, source, event, phase, outcome: result,
        invocationId: randomUUID(),
        parentInvocationId: binding?.invocationId ?? null, context, data };
      const compact = this.compactRecord(cwd, row, context);
      this.emitContextSnapshot(cwd, context, compact.contextRef as string, row.parentInvocationId as string | null, binding?.nativeContext);
      this.append(cwd, compact);
    } catch { this.warn(binding?.nativeContext); }
  }

  private observe(source: string, event: string, args: unknown[], ctx: unknown, invoke: (args: unknown[]) => unknown): unknown {
    const control = event === "command:learning" && typeof args[0] === "string" && /^debug(?:\s|$)/.test(args[0].trim());
    if (!readDebugConfigState().enabled && !control) return invoke(args);
    const parent = active.getStore();
    let context: Record<string, unknown>, projectCwd = parent?.projectCwd ?? canonicalProjectCwd(process.cwd());
    try {
      const raw = ctx ? captureContext(ctx) : parent?.context ?? captureContext(undefined);
      if (typeof raw.cwd === "string") projectCwd = raw.cwd;
      const captured = sanitizeDebugValue(raw);
      context = object(captured) ? captured : { projectId: sha256(projectCwd), omitted: "context-unavailable" };
    } catch { context = { projectId: sha256(projectCwd), omitted: "context-unavailable" }; }
    const binding: Binding = { journal: this, invocationId: randomUUID(), source, context, projectCwd,
      nativeContext: ctx ?? parent?.nativeContext, parentInvocationId: parent?.invocationId ?? null };
    const started = performance.now();
    const compact = this.compactContext(context, projectCwd);
    const lifecycle = !parent && /^event:session_(?:start|shutdown)$/.test(event);
    const batchKey = lifecycle ? `${projectCwd}:${context.sessionId ?? "unknown"}:${event}` : undefined;
    if (lifecycle) {
      const key = `${projectCwd}:${context.sessionId ?? "unknown"}:${event}`;
      let batch = lifecycleBatches.get(key);
      if (!batch) {
        batch = { key, event, sessionId: context.sessionId, rows: [], sources: new Set(), cwd: projectCwd, contextRef: compact.contextRef,
          timer: setTimeout(() => this.flushLifecycle(key, projectCwd, compact.contextRef), 0) };
        lifecycleBatches.set(key, batch);
      }
      batch.sources.add(source);
      batch.rows.push({ invocationId: binding.invocationId, source, phase: "started", outcome: "started", durationMs: 0 });
    }
    this.emitContextSnapshot(projectCwd, context, compact.contextRef, null, binding.nativeContext);
    const emit = (phase: Phase, result: string, data: unknown) => {
      if (phase === "started") this.inFlight.add(binding.invocationId);
      else this.inFlight.delete(binding.invocationId);
      try {
        if (!readDebugConfigState().enabled) return;
        const row = { kind: "continual-learning-debug", version: 1, timestamp: new Date().toISOString(),
          pid: process.pid, source, event, phase, outcome: result, invocationId: binding.invocationId,
          parentInvocationId: parent?.invocationId ?? null, durationMs: Math.round(performance.now() - started),
          context: compact.context, contextRef: compact.contextRef, data };
        this.emitContextSnapshot(projectCwd, context, compact.contextRef, row.parentInvocationId as string | null);
        if (batchKey && phase !== "failed") {
          const batch = lifecycleBatches.get(batchKey);
          if (batch) {
            batch.sources.add(source);
            batch.rows.push({ invocationId: binding.invocationId, source, phase, outcome: result, durationMs: row.durationMs });
            return;
          }
        }
        this.append(projectCwd, row);
      } catch { this.warn(binding.nativeContext); }
    };
    if (!lifecycle) emit("started", "started", args);
    const finish = (value: unknown) => { if (readDebugConfigState().enabled) emit("completed", outcome(value), { result: value }); return value; };
    const fail = (error: unknown) => { emit("failed", "failed", { error }); throw error; };
    return active.run(binding, () => {
      try {
        const value = invoke(args);
        if (asynchronous(value)) return Promise.resolve(value).then(value => active.run(binding, () => finish(value)), error => active.run(binding, () => fail(error)));
        return finish(value);
      } catch (error) { return fail(error); }
    });
  }

  private flushLifecycle(key: string, cwd: string, contextRef: string): void {
    const batch = lifecycleBatches.get(key);
    if (!batch) return;
    lifecycleBatches.delete(key);
    // 关闭后的待刷新批量不再落盘；其中只包含关闭前已捕获的 handler 观测。
    if (!readDebugConfigState().enabled) return;
    const root = batch.rows.find(row => row.phase === "started");
    try {
      this.append(cwd, { kind: "continual-learning-debug", version: 1, timestamp: new Date().toISOString(),
        pid: process.pid, source: "extensions/debug.ts", event: "lifecycle:batch", phase: "completed", outcome: "completed",
        invocationId: root?.invocationId as string ?? randomUUID(), parentInvocationId: null,
        context: { projectId: sha256(cwd), sessionId: batch.sessionId },
        data: { event: batch.event,
          handlerCount: new Set(batch.rows.map(row => row.invocationId)).size,
          handlers: batch.rows, sources: [...batch.sources] },
      });
      void contextRef;
    } catch { /* 生命周期观测失败不改变插件行为。 */ }
  }

  private contextProxy(ctx: unknown): unknown {
    if (!object(ctx)) return ctx;
    const journal = this;
    return new Proxy(ctx, { get(target, key, receiver) {
      const value = Reflect.get(target, key, receiver);
      if (key !== "ui" || !object(value)) return typeof value === "function" ? value.bind(target) : value;
      return new Proxy(value, { get(ui, method, uiReceiver) {
        const original = Reflect.get(ui, method, uiReceiver);
        if (typeof original !== "function" || !["notify", "select", "confirm", "input", "editor", "custom"].includes(String(method))) return typeof original === "function" ? original.bind(ui) : original;
        return (...args: unknown[]) => {
          const binding = active.getStore();
          if (method === "notify") {
            const result = Reflect.apply(original, ui, args);
            journal.record(binding?.source ?? "ui", "ui:notify", args, "observed", args[1] === "error" ? "failed" : "observed");
            return result;
          }
          return journal.observe(binding?.source ?? "ui", `ui:${String(method)}`, args, undefined, () => Reflect.apply(original, ui, args));
        };
      } });
    } });
  }

  private debugCommand(args: string, ctx: unknown): void {
    const mode = args.trim().split(/\s+/).slice(1);
    const ui = object(ctx) && object(ctx.ui) ? ctx.ui : undefined;
    const notify = (text: string, level: string) => { if (typeof ui?.notify === "function") Reflect.apply(ui.notify, ui, [text, level]); };
    if (mode.length > 1 || mode[0] && !["on", "off", "status"].includes(mode[0])) {
      notify("Usage: /learning debug [on|off|status]", "error"); return;
    }
    try {
      if (mode[0] === "on" || mode[0] === "off") {
        const wasEnabled = readDebugConfigState().enabled, enabled = mode[0] === "on";
        // 关闭时显式列出此刻仍在途的调用；检查器只能据此收束，不能按时间戳推断。
        // 命令自身的调用会由这条 configuration 记录给出终态，不算被截断。
        const ownId = active.getStore()?.invocationId;
        const truncatedInvocations = enabled ? [] : [...this.inFlight].filter(id => id !== ownId);
        writeUnifiedConfig({ debug: enabled });
        if (!enabled) this.inFlight.clear();
        const binding = active.getStore();
        if (binding && (wasEnabled || enabled)) {
          try {
            this.append(binding.projectCwd, { kind: "continual-learning-debug", version: 1, timestamp: new Date().toISOString(),
              pid: process.pid, source: "extensions/debug.ts", event: "debug:configuration", phase: "completed", outcome: enabled ? "enabled" : "disabled",
              invocationId: binding.invocationId, parentInvocationId: binding.parentInvocationId,
              context: { projectId: sha256(binding.projectCwd), sessionId: binding.context.sessionId },
              data: { enabled, file: memoryConfigPath(), truncatedInvocations } });
          } catch { this.warn(ctx); }
        }
      }
      const status = this.status(object(ctx) && typeof ctx.cwd === "string" ? ctx.cwd : process.cwd());
      notify(`Continual-learning debug: ${status.enabled ? "on" : "off"}\nDirectory: ${status.directory}\nConfig: ${memoryConfigPath()}${status.invalid ? "\nInvalid debug configuration; default on remains active." : ""}${status.unavailable ? "\nLogging unavailable; inspect directory permissions and file types." : ""}\nPrivate, sanitized, bounded context; earlier log segments are retained.`, "info");
    } catch { notify("Debug settings could not be changed safely. Repair continual-learning.json before changing debug.", "error"); }
  }

  wrap<T extends object>(host: T, source: string): T {
    const cached = this.hosts.get(host);
    if (cached) { cached.source = source; return cached.proxy as T; }
    const journal = this;
    const registration = { source, proxy: host };
    const proxy = new Proxy(host, { get(target, property, receiver) {
      const original = Reflect.get(target, property, receiver);
      if (typeof original !== "function") return original;
      if (property === "on") return (event: string, handler: unknown) => {
        const owner = registration.source;
        if (typeof handler !== "function") return Reflect.apply(original, target, [event, handler]);
        return Reflect.apply(original, target, [event, (...args: unknown[]) => journal.observe(owner, `event:${event}`, [args[0]], args[1], () => Reflect.apply(handler, target, [args[0], journal.contextProxy(args[1])]))]);
      };
      if (property === "registerTool" || property === "registerCommand") return (...args: unknown[]) => {
        const index = property === "registerTool" ? 0 : 1, definition = args[index], owner = registration.source;
        if (!object(definition)) return Reflect.apply(original, target, args);
        const field = property === "registerTool" ? "execute" : "handler", handler = definition[field];
        if (typeof handler !== "function") return Reflect.apply(original, target, args);
        const name = property === "registerTool" ? definition.name : args[0];
        args[index] = { ...definition, [field]: (...input: unknown[]) => {
          const ctxIndex = property === "registerTool" ? 4 : 1, ctx = input[ctxIndex];
          return journal.observe(owner, `${property === "registerTool" ? "tool" : "command"}:${String(name)}`, input.filter((_, i) => i !== ctxIndex && i !== 2 && i !== 3), ctx, () => {
            if (property === "registerCommand" && name === "learning" && typeof input[0] === "string" && /^debug(?:\s|$)/.test(input[0].trim())) return journal.debugCommand(input[0], journal.contextProxy(ctx));
            const forwarded = [...input]; forwarded[ctxIndex] = journal.contextProxy(ctx);
            return Reflect.apply(handler, definition, forwarded);
          });
        } };
        return Reflect.apply(original, target, args);
      };
      if (["sendMessage", "appendEntry", "setActiveTools", "sendUserMessage", "exec"].includes(String(property))) return (...args: unknown[]) => {
        const binding = active.getStore(), owner = binding?.source ?? registration.source;
        if (property === "exec") return journal.observe(owner, "exec", args, undefined, () => Reflect.apply(original, target, args));
        const value = Reflect.apply(original, target, args);
        journal.record(owner, String(property), args);
        return value;
      };
      return original.bind(target);
    } });
    // 所有模块共用同一 API 身份，保留现有 WeakMap 桥接。
    registration.proxy = proxy;
    this.hosts.set(host, registration);
    this.hosts.set(proxy, registration);
    return proxy;
  }
}

export function createLearningDebug(): LearningDebug { return new LearningDebug(); }

export function recordLearningDebug(source: string, event: string, data: unknown): void {
  const binding = active.getStore();
  binding?.journal.record(source, event, data);
}
