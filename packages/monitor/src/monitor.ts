import { spawn, type ChildProcess } from "node:child_process";

export const KILL_GRACE_MS = 1000;
export const MAX_LINE_LENGTH = 10 * 1024;
export const MAX_LINE_BUFFER = 64 * 1024;
export const MAX_LOG_LINES = 2000;
export const MAX_LOG_BYTES = 256 * 1024;
export const MAX_RESULT_OUTPUT_LINES = 100;
export const MAX_RESULT_OUTPUT_BYTES = 32 * 1024;
export const MAX_HISTORY = 20;
export const MAX_RESULT_TEXT = 4096;
export const MAX_RESULT_JSON_BYTES = 32 * 1024;
export const DRAIN_GRACE_MS = 1000;
export const DEFAULT_TIMEOUT_MS = 10 * 60 * 1000;
export const MAX_TIMEOUT_MS = 2_147_483_647;

export type MonitorStatus =
  | "running"
  | "success"
  | "failure"
  | "result_missing"
  | "timeout"
  | "stopped";

export type MonitorLogSource = "stdout" | "stderr";

export interface MonitorTerminalResult {
  status: Exclude<MonitorStatus, "running">;
  elapsedMs: number;
  output?: string[];
  outputTruncated?: boolean;
  matched?: string;
  captures?: Record<string, string>;
  result?: unknown;
  resultParseError?: string;
  expected?: string;
  exitCode?: number | null;
  signal?: NodeJS.Signals | null;
  reason?: string;
  timeoutMs?: number;
}

export interface Monitor {
  id: string;
  description: string;
  command: string;
  resultPattern: string;
  failurePattern?: string;
  timeoutMs: number;
  startedAt: number;
  completedAt?: number;
  status: MonitorStatus;
  terminal?: MonitorTerminalResult;
  /** Whether a terminal result should be injected into the agent as a custom message. */
  notifyTerminal: boolean;
  retainedLogLines: number;
  droppedLogLines: number;
}

export interface MonitorOutput {
  lines: string[];
  truncated: boolean;
}

interface MonitorLogEntry {
  source: MonitorLogSource;
  text: string;
  bytes: number;
}

interface InternalMonitor extends Monitor {
  child?: ChildProcess;
  killTimer?: ReturnType<typeof setTimeout>;
  killPromise?: Promise<void>;
  killResolver?: () => void;
  resultMatcher: RegExp;
  failureMatcher?: RegExp;
  buffers: Record<MonitorLogSource, string>;
  logs: MonitorLogEntry[];
  logBytes: number;
  pendingTerminal?: MonitorTerminalResult;
  drainTimer?: ReturnType<typeof setTimeout>;
  timeoutTimer?: ReturnType<typeof setTimeout>;
}

interface ArchivedMonitor {
  monitor: Monitor;
  logs: MonitorLogEntry[];
}

export interface MonitorEvents {
  onTerminal: (monitor: Monitor, result: MonitorTerminalResult) => void;
}

export interface StartMonitorArgs {
  command: string;
  description: string;
  resultPattern: string;
  failurePattern?: string;
  timeoutMs?: number;
  cwd?: string;
  notifyTerminal?: boolean;
}

export interface MonitorTerminalEvent {
  monitor: Monitor;
  result: MonitorTerminalResult;
}

/** Session-scoped result-contract monitors with bounded terminal diagnostics. */
export class MonitorManager {
  private active = new Map<string, InternalMonitor>();
  private history: ArchivedMonitor[] = [];
  private terminalWaiters = new Map<string, Array<(event: MonitorTerminalEvent) => void>>();
  private counter = 0;

  constructor(private readonly events: MonitorEvents) {}

  start(args: StartMonitorArgs): Monitor {
    const resultMatcher = compilePattern("result_pattern", args.resultPattern);
    const failureMatcher = args.failurePattern
      ? compilePattern("failure_pattern", args.failurePattern)
      : undefined;
    const monitor = this.createMonitor(args, resultMatcher, failureMatcher);
    const child = spawn(args.command, {
      shell: true,
      cwd: args.cwd,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
    });

    monitor.child = child;
    this.active.set(monitor.id, monitor);
    this.attachProcessHandlers(monitor);
    this.scheduleTimeout(monitor);
    return this.public(monitor);
  }

  stop(id?: string): { stopped: string[] } {
    const monitors = id
      ? [this.active.get(id)].filter((monitor): monitor is InternalMonitor => monitor !== undefined)
      : [...this.active.values()];
    for (const monitor of monitors) {
      this.clearDrain(monitor);
      this.complete(
        monitor,
        { status: "stopped", elapsedMs: this.elapsed(monitor), reason: "manual_stop" },
        true,
        false,
      );
    }
    return { stopped: monitors.map((monitor) => monitor.id) };
  }

  list(): Monitor[] {
    return [...this.active.values()].map((monitor) => this.public(monitor));
  }

  listAll(): Monitor[] {
    return [
      ...this.list(),
      ...this.history.map((entry) => entry.monitor),
    ];
  }

  waitForTerminal(id: string, signal?: AbortSignal): Promise<MonitorTerminalEvent> {
    const archived = this.history.find((entry) => entry.monitor.id === id)?.monitor;
    if (archived?.terminal) return Promise.resolve({ monitor: archived, result: archived.terminal });
    if (!this.active.has(id)) return Promise.reject(new Error(`No monitor with id ${id}.`));
    return new Promise((resolve, reject) => {
      const onAbort = () => {
        this.removeTerminalWaiter(id, waiter);
        reject(signal?.reason ?? new Error("Monitor wait aborted."));
      };
      const waiter = (event: MonitorTerminalEvent) => {
        signal?.removeEventListener("abort", onAbort);
        resolve(event);
      };
      if (signal?.aborted) {
        onAbort();
        return;
      }
      signal?.addEventListener("abort", onAbort, { once: true });
      const waiters = this.terminalWaiters.get(id) ?? [];
      waiters.push(waiter);
      this.terminalWaiters.set(id, waiters);
    });
  }

  tail(id: string, tailLines = MAX_RESULT_OUTPUT_LINES): MonitorOutput | undefined {
    const active = this.active.get(id);
    const archived = this.history.find((entry) => entry.monitor.id === id);
    const logs = active?.logs ?? archived?.logs;
    if (!logs) return undefined;

    const requested = Math.min(Math.max(tailLines, 1), MAX_RESULT_OUTPUT_LINES);
    const selected = boundedTail(logs.slice(-requested), MAX_RESULT_OUTPUT_BYTES);
    return {
      lines: selected.map((entry) => `[${entry.source}] ${entry.text}`),
      truncated: logs.length > requested
        || selected.length < Math.min(requested, logs.length)
        || (active?.droppedLogLines ?? archived?.monitor.droppedLogLines ?? 0) > 0,
    };
  }

  async stopAllOnShutdown(): Promise<void> {
    const waits = [...this.active.values()].map((monitor) => {
      this.clearDrain(monitor);
      this.complete(
        monitor,
        { status: "stopped", elapsedMs: this.elapsed(monitor), reason: "session_shutdown" },
        true,
        false,
        true,
      );
      return monitor.killPromise;
    });
    await Promise.all(waits);
  }

  private clearDrain(monitor: InternalMonitor): void {
    if (monitor.drainTimer) {
      clearTimeout(monitor.drainTimer);
      monitor.drainTimer = undefined;
    }
    this.clearTimeout(monitor);
    monitor.pendingTerminal = undefined;
  }

  private createMonitor(
    args: StartMonitorArgs,
    resultMatcher: RegExp,
    failureMatcher?: RegExp,
  ): InternalMonitor {
    return {
      id: `monitor_${++this.counter}`,
      description: args.description,
      command: args.command,
      resultPattern: args.resultPattern,
      failurePattern: args.failurePattern,
      timeoutMs: normalizeTimeout(args.timeoutMs),
      startedAt: Date.now(),
      status: "running",
      notifyTerminal: args.notifyTerminal ?? true,
      retainedLogLines: 0,
      droppedLogLines: 0,
      resultMatcher,
      failureMatcher,
      buffers: { stdout: "", stderr: "" },
      logs: [],
      logBytes: 0,
    };
  }

  private scheduleTimeout(monitor: InternalMonitor): void {
    monitor.timeoutTimer = setTimeout(() => {
      if (monitor.status !== "running" || monitor.pendingTerminal) return;
      this.complete(
        monitor,
        {
          status: "timeout",
          elapsedMs: this.elapsed(monitor),
          reason: "timeout",
          timeoutMs: monitor.timeoutMs,
        },
        true,
      );
    }, monitor.timeoutMs);
    monitor.timeoutTimer.unref();
  }

  private clearTimeout(monitor: InternalMonitor): void {
    if (monitor.timeoutTimer) {
      clearTimeout(monitor.timeoutTimer);
      monitor.timeoutTimer = undefined;
    }
  }

  private attachProcessHandlers(monitor: InternalMonitor): void {
    const child = monitor.child;
    child?.stdout?.setEncoding("utf8");
    child?.stderr?.setEncoding("utf8");
    child?.stdout?.on("data", (chunk: string) => this.handleChunk(monitor, "stdout", chunk));
    child?.stderr?.on("data", (chunk: string) => this.handleChunk(monitor, "stderr", chunk));
    child?.on("error", (error) => {
      if (monitor.status !== "running") return;
      this.complete(monitor, {
        status: "failure",
        elapsedMs: this.elapsed(monitor),
        reason: `spawn_error: ${error.message}`,
      });
    });
    child?.on("close", (code, signal) => this.handleClose(monitor, code, signal));
  }

  private handleChunk(monitor: InternalMonitor, source: MonitorLogSource, text: string): void {
    if (monitor.status !== "running") return;
    monitor.buffers[source] += text;
    this.drainCompleteLines(monitor, source);
    while (monitor.status === "running" && monitor.buffers[source].length > MAX_LINE_BUFFER) {
      const fragment = monitor.buffers[source].slice(0, MAX_LINE_BUFFER);
      monitor.buffers[source] = monitor.buffers[source].slice(MAX_LINE_BUFFER);
      this.handleLine(monitor, source, fragment, true);
    }
  }

  private drainCompleteLines(monitor: InternalMonitor, source: MonitorLogSource): void {
    let newline: number;
    while (
      monitor.status === "running"
      && (newline = monitor.buffers[source].indexOf("\n")) !== -1
    ) {
      const line = monitor.buffers[source].slice(0, newline).replace(/\r$/, "");
      monitor.buffers[source] = monitor.buffers[source].slice(newline + 1);
      this.handleLine(monitor, source, line, false);
    }
  }

  private handleLine(
    monitor: InternalMonitor,
    source: MonitorLogSource,
    rawLine: string,
    continued: boolean,
    _processAlreadyClosed = false,
  ): void {
    if (monitor.status !== "running") return;
    this.appendLog(monitor, source, rawLine, continued);

    // During drain, accumulate lines but do not check for further matches.
    if (monitor.pendingTerminal) return;

    const failure = monitor.failureMatcher?.exec(rawLine);
    if (failure) {
      this.beginDrain(monitor, buildMatchedResult("failure", monitor, failure));
      return;
    }
    const success = monitor.resultMatcher.exec(rawLine);
    if (success) {
      this.beginDrain(monitor, buildMatchedResult("success", monitor, success));
    }
  }

  private beginDrain(monitor: InternalMonitor, terminal: MonitorTerminalResult): void {
    monitor.pendingTerminal = terminal;
    monitor.drainTimer = setTimeout(() => this.finalizeDrain(monitor), DRAIN_GRACE_MS);
    monitor.drainTimer.unref();
  }

  private finalizeDrain(monitor: InternalMonitor): void {
    if (!monitor.pendingTerminal || monitor.status !== "running") return;
    this.drainFinalBuffers(monitor, true);
    if (monitor.status !== "running") return;
    this.complete(monitor, monitor.pendingTerminal, true);
  }

  private appendLog(
    monitor: InternalMonitor,
    source: MonitorLogSource,
    rawLine: string,
    continued: boolean,
  ): void {
    if (rawLine.length === 0) return;
    const truncated = rawLine.length > MAX_LINE_LENGTH || continued;
    const suffix = truncated ? "...[truncated]" : "";
    const text = `${rawLine.slice(0, MAX_LINE_LENGTH)}${suffix}`;
    const entry: MonitorLogEntry = {
      source,
      text,
      bytes: Buffer.byteLength(text, "utf8") + source.length + 3,
    };
    monitor.logs.push(entry);
    monitor.logBytes += entry.bytes;
    this.trimLogs(monitor);
  }

  private trimLogs(monitor: InternalMonitor): void {
    while (monitor.logs.length > MAX_LOG_LINES || monitor.logBytes > MAX_LOG_BYTES) {
      const removed = monitor.logs.shift();
      if (!removed) break;
      monitor.logBytes -= removed.bytes;
      monitor.droppedLogLines += 1;
    }
    monitor.retainedLogLines = monitor.logs.length;
  }

  private handleClose(
    monitor: InternalMonitor,
    code: number | null,
    signal: NodeJS.Signals | null,
  ): void {
    if (monitor.status !== "running") return;
    this.drainFinalBuffers(monitor, true);
    if (monitor.status !== "running") return;

    // If a pattern match is draining, finalize with the pending result now.
    if (monitor.pendingTerminal) {
      if (monitor.drainTimer) {
        clearTimeout(monitor.drainTimer);
        monitor.drainTimer = undefined;
      }
      this.complete(monitor, monitor.pendingTerminal, false);
      return;
    }

    if (code === 0) {
      this.complete(monitor, {
        status: "result_missing",
        elapsedMs: this.elapsed(monitor),
        expected: monitor.resultPattern,
        exitCode: code,
        signal,
      });
      return;
    }
    this.complete(monitor, {
      status: "failure",
      elapsedMs: this.elapsed(monitor),
      exitCode: code,
      signal,
      reason: "process_exit",
    });
  }

  private drainFinalBuffers(monitor: InternalMonitor, processAlreadyClosed: boolean): void {
    for (const source of ["stdout", "stderr"] as const) {
      const line = monitor.buffers[source].replace(/\r$/, "");
      monitor.buffers[source] = "";
      if (line.length > 0) {
        this.handleLine(monitor, source, line, false, processAlreadyClosed);
      }
      if (monitor.status !== "running") return;
    }
  }

  private complete(
    monitor: InternalMonitor,
    terminal: MonitorTerminalResult,
    killProcess = false,
    notify = true,
    keepKillTimerAlive = false,
  ): void {
    if (monitor.status !== "running") return;
    this.clearTimeout(monitor);
    if (terminal.status !== "success") {
      const output = this.tail(monitor.id);
      terminal.output = collapseRepeatedLines(output?.lines ?? []);
      terminal.outputTruncated = output?.truncated ?? false;
    }
    if (killProcess) this.killTree(monitor, keepKillTimerAlive);
    monitor.status = terminal.status;
    monitor.completedAt = Date.now();
    monitor.terminal = terminal;
    this.detachOutput(monitor);
    this.active.delete(monitor.id);
    const publicMonitor = this.public(monitor);
    this.archive(publicMonitor, monitor.logs);
    this.resolveTerminalWaiters(publicMonitor, terminal);
    if (notify) this.events.onTerminal(publicMonitor, terminal);
  }

  private removeTerminalWaiter(
    id: string,
    waiter: (event: MonitorTerminalEvent) => void,
  ): void {
    const waiters = this.terminalWaiters.get(id);
    if (!waiters) return;
    const remaining = waiters.filter((entry) => entry !== waiter);
    if (remaining.length === 0) this.terminalWaiters.delete(id);
    else this.terminalWaiters.set(id, remaining);
  }

  private resolveTerminalWaiters(monitor: Monitor, result: MonitorTerminalResult): void {
    const waiters = this.terminalWaiters.get(monitor.id);
    this.terminalWaiters.delete(monitor.id);
    for (const resolve of waiters ?? []) resolve({ monitor, result });
  }

  private detachOutput(monitor: InternalMonitor): void {
    monitor.child?.stdout?.removeAllListeners("data");
    monitor.child?.stderr?.removeAllListeners("data");
    monitor.child?.removeAllListeners("error");
    monitor.child?.stdout?.destroy();
    monitor.child?.stderr?.destroy();
  }

  private archive(monitor: Monitor, logs: MonitorLogEntry[]): void {
    this.history.unshift({ monitor, logs: [...logs] });
    if (this.history.length > MAX_HISTORY) this.history.length = MAX_HISTORY;
  }

  private killTree(monitor: InternalMonitor, keepTimerAlive = false): void {
    const child = monitor.child;
    if (!child?.pid || monitor.killTimer) return;
    const pid = child.pid;
    const signalGroup = (signal: NodeJS.Signals): void => {
      try {
        process.kill(-pid, signal);
      } catch {
        try {
          child.kill(signal);
        } catch {
          // Process already exited.
        }
      }
    };
    signalGroup("SIGTERM");
    monitor.killPromise = new Promise<void>((resolve) => {
      monitor.killResolver = resolve;
      monitor.killTimer = setTimeout(() => {
        monitor.killTimer = undefined;
        signalGroup("SIGKILL");
        monitor.killResolver = undefined;
        resolve();
      }, KILL_GRACE_MS);
      if (!keepTimerAlive) monitor.killTimer.unref();
    });
  }

  private elapsed(monitor: Monitor): number {
    return Date.now() - monitor.startedAt;
  }

  private public(monitor: InternalMonitor): Monitor {
    return {
      id: monitor.id,
      description: monitor.description,
      command: monitor.command,
      resultPattern: monitor.resultPattern,
      failurePattern: monitor.failurePattern,
      timeoutMs: monitor.timeoutMs,
      startedAt: monitor.startedAt,
      completedAt: monitor.completedAt,
      status: monitor.status,
      terminal: monitor.terminal,
      notifyTerminal: monitor.notifyTerminal,
      retainedLogLines: monitor.logs.length,
      droppedLogLines: monitor.droppedLogLines,
    };
  }
}

function normalizeTimeout(timeoutMs: number | undefined): number {
  const timeout = timeoutMs ?? DEFAULT_TIMEOUT_MS;
  if (!Number.isInteger(timeout) || timeout < 1 || timeout > MAX_TIMEOUT_MS) {
    throw new Error(`timeout_ms must be an integer between 1 and ${MAX_TIMEOUT_MS}.`);
  }
  return timeout;
}

function compilePattern(name: string, pattern: string): RegExp {
  if (!pattern.trim()) throw new Error(`${name} must be a non-empty regular expression.`);
  try {
    return new RegExp(pattern);
  } catch (error) {
    throw new Error(`invalid ${name}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function buildMatchedResult(
  status: "success" | "failure",
  monitor: Monitor,
  match: RegExpExecArray,
): MonitorTerminalResult {
  const captures = match.groups
    ? Object.fromEntries(
      Object.entries(match.groups).map(([name, value]) => [
        name,
        value.slice(0, name === "json" ? MAX_RESULT_JSON_BYTES : MAX_RESULT_TEXT),
      ]),
    )
    : undefined;
  const terminal: MonitorTerminalResult = {
    status,
    elapsedMs: Date.now() - monitor.startedAt,
    matched: match[0].slice(0, MAX_RESULT_TEXT),
    captures,
  };
  if (!captures?.json) return terminal;

  if (Buffer.byteLength(match.groups?.json ?? "", "utf8") > MAX_RESULT_JSON_BYTES) {
    terminal.resultParseError = `json capture exceeds ${MAX_RESULT_JSON_BYTES} bytes`;
    return terminal;
  }
  try {
    terminal.result = JSON.parse(captures.json);
  } catch (error) {
    terminal.resultParseError = error instanceof Error ? error.message : String(error);
  }
  return terminal;
}

function boundedTail(logs: MonitorLogEntry[], maxBytes: number): MonitorLogEntry[] {
  const selected: MonitorLogEntry[] = [];
  let bytes = 0;
  for (let index = logs.length - 1; index >= 0; index -= 1) {
    const entry = logs[index];
    if (selected.length > 0 && bytes + entry.bytes > maxBytes) break;
    selected.unshift(entry);
    bytes += entry.bytes;
  }
  return selected;
}

function collapseRepeatedLines(lines: string[]): string[] {
  const counts = new Map<string, number>();
  const order: string[] = [];
  for (const line of lines) {
    if (!counts.has(line)) order.push(line);
    counts.set(line, (counts.get(line) ?? 0) + 1);
  }
  return order.map((line) => formatRepeatedLine(line, counts.get(line) ?? 1));
}

function formatRepeatedLine(line: string, count: number): string {
  return count > 1 ? `${line} (repeated ${count} times)` : line;
}
