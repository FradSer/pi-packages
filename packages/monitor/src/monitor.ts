import { spawn, type ChildProcess } from "node:child_process";

export const DEFAULT_TIMEOUT_MS = 5 * 60 * 1000;
export const MAX_TIMEOUT_MS = 60 * 60 * 1000;
export const KILL_GRACE_MS = 1000;
export const MAX_LINE_LENGTH = 10 * 1024;
export const MAX_LINE_BUFFER = 64 * 1024;
export const MAX_LOG_LINES = 2000;
export const MAX_LOG_BYTES = 256 * 1024;
export const MAX_READ_LINES = 500;
export const MAX_READ_BYTES = 64 * 1024;
export const MAX_HISTORY = 20;
export const MAX_RESULT_TEXT = 4096;
export const MAX_RESULT_JSON_BYTES = 32 * 1024;

export type MonitorStatus =
  | "running"
  | "success"
  | "failure"
  | "timeout"
  | "result_missing"
  | "stopped";

export type MonitorLogSource = "stdout" | "stderr";

export interface MonitorTerminalResult {
  status: Exclude<MonitorStatus, "running">;
  elapsedMs: number;
  matched?: string;
  captures?: Record<string, string>;
  result?: unknown;
  resultParseError?: string;
  expected?: string;
  exitCode?: number | null;
  signal?: NodeJS.Signals | null;
  reason?: string;
}

export interface Monitor {
  id: string;
  description: string;
  command: string;
  resultPattern: string;
  failurePattern?: string;
  persistent: boolean;
  timeoutMs: number;
  startedAt: number;
  completedAt?: number;
  status: MonitorStatus;
  terminal?: MonitorTerminalResult;
  retainedLogLines: number;
  droppedLogLines: number;
}

export interface MonitorReadResult {
  monitor: Monitor;
  lines: string[];
  droppedLines: number;
  truncated: boolean;
}

interface MonitorLogEntry {
  source: MonitorLogSource;
  text: string;
  bytes: number;
}

interface InternalMonitor extends Monitor {
  child?: ChildProcess;
  timeoutTimer?: ReturnType<typeof setTimeout>;
  killTimer?: ReturnType<typeof setTimeout>;
  killPromise?: Promise<void>;
  killResolver?: () => void;
  resultMatcher: RegExp;
  failureMatcher?: RegExp;
  buffers: Record<MonitorLogSource, string>;
  logs: MonitorLogEntry[];
  logBytes: number;
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
  persistent?: boolean;
  cwd?: string;
}

/** Session-scoped result-contract monitors with bounded, on-demand raw logs. */
export class MonitorManager {
  private active = new Map<string, InternalMonitor>();
  private history: ArchivedMonitor[] = [];
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
    this.startTimeout(monitor);
    return this.public(monitor);
  }

  stop(id?: string): { stopped: string[] } {
    const monitors = id
      ? [this.active.get(id)].filter((monitor): monitor is InternalMonitor => monitor !== undefined)
      : [...this.active.values()];
    for (const monitor of monitors) {
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

  read(id: string, tailLines = 100): MonitorReadResult | undefined {
    const active = this.active.get(id);
    const archived = this.history.find((entry) => entry.monitor.id === id);
    const monitor = active ? this.public(active) : archived?.monitor;
    const logs = active?.logs ?? archived?.logs;
    if (!monitor || !logs) return undefined;

    const requested = Math.min(Math.max(tailLines, 1), MAX_READ_LINES);
    const selected = boundedTail(logs.slice(-requested));
    return {
      monitor,
      lines: selected.map((entry) => `[${entry.source}] ${entry.text}`),
      droppedLines: monitor.droppedLogLines,
      truncated: selected.length < Math.min(requested, logs.length) || monitor.droppedLogLines > 0,
    };
  }

  async stopAllOnShutdown(): Promise<void> {
    const waits = [...this.active.values()].map((monitor) => {
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

  private createMonitor(
    args: StartMonitorArgs,
    resultMatcher: RegExp,
    failureMatcher?: RegExp,
  ): InternalMonitor {
    const persistent = args.persistent === true;
    return {
      id: `monitor_${++this.counter}`,
      description: args.description,
      command: args.command,
      resultPattern: args.resultPattern,
      failurePattern: args.failurePattern,
      persistent,
      timeoutMs: Math.min(Math.max(args.timeoutMs ?? DEFAULT_TIMEOUT_MS, 1), MAX_TIMEOUT_MS),
      startedAt: Date.now(),
      status: "running",
      retainedLogLines: 0,
      droppedLogLines: 0,
      resultMatcher,
      failureMatcher,
      buffers: { stdout: "", stderr: "" },
      logs: [],
      logBytes: 0,
    };
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

  private startTimeout(monitor: InternalMonitor): void {
    if (monitor.persistent) return;
    monitor.timeoutTimer = setTimeout(() => {
      this.drainFinalBuffers(monitor, false);
      if (monitor.status !== "running") return;
      this.complete(
        monitor,
        {
          status: "timeout",
          elapsedMs: this.elapsed(monitor),
          expected: monitor.resultPattern,
        },
        true,
      );
    }, monitor.timeoutMs);
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
    processAlreadyClosed = false,
  ): void {
    if (monitor.status !== "running") return;
    this.appendLog(monitor, source, rawLine, continued);

    const failure = monitor.failureMatcher?.exec(rawLine);
    if (failure) {
      this.complete(
        monitor,
        buildMatchedResult("failure", monitor, failure),
        !processAlreadyClosed,
      );
      return;
    }
    const success = monitor.resultMatcher.exec(rawLine);
    if (success) {
      this.complete(
        monitor,
        buildMatchedResult("success", monitor, success),
        !processAlreadyClosed,
      );
    }
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
    if (killProcess) this.killTree(monitor, keepKillTimerAlive);
    monitor.status = terminal.status;
    monitor.completedAt = Date.now();
    monitor.terminal = terminal;
    if (monitor.timeoutTimer) clearTimeout(monitor.timeoutTimer);
    this.detachOutput(monitor);
    this.active.delete(monitor.id);
    const publicMonitor = this.public(monitor);
    this.archive(publicMonitor, monitor.logs);
    if (notify) this.events.onTerminal(publicMonitor, terminal);
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
      persistent: monitor.persistent,
      timeoutMs: monitor.timeoutMs,
      startedAt: monitor.startedAt,
      completedAt: monitor.completedAt,
      status: monitor.status,
      terminal: monitor.terminal,
      retainedLogLines: monitor.logs.length,
      droppedLogLines: monitor.droppedLogLines,
    };
  }
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

function boundedTail(logs: MonitorLogEntry[]): MonitorLogEntry[] {
  const selected: MonitorLogEntry[] = [];
  let bytes = 0;
  for (let index = logs.length - 1; index >= 0; index -= 1) {
    const entry = logs[index];
    if (selected.length > 0 && bytes + entry.bytes > MAX_READ_BYTES) break;
    selected.unshift(entry);
    bytes += entry.bytes;
  }
  return selected;
}
