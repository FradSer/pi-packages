import { spawn, type ChildProcess } from "node:child_process";
import { randomUUID } from "node:crypto";
import { Worker } from "node:worker_threads";
import { performance } from "node:perf_hooks";

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
export const MAX_RESULT_CAPTURE_BYTES = 32 * 1024;
export const DRAIN_GRACE_MS = 1000;
/** Idle window before an unterminated trailing line is matched against the
 * contract. Long enough that a writer pausing mid-line does not look like a
 * finished line, short enough that a sentinel printed without a trailing newline
 * resolves while the command keeps running. */
export const TAIL_MATCH_IDLE_MS = 150;
export const DEFAULT_TIMEOUT_MS = 10 * 60 * 1000;
export const MAX_TIMEOUT_MS = 2_147_483_647;
const MATCH_PAUSE_LINES = 1024;
const MATCH_PAUSE_BYTES = 256 * 1024;

export type MonitorStatus =
  | "running"
  | "success"
  | "failure"
  | "result_missing"
  | "timeout"
  | "stopped";

export type MonitorLogSource = "stdout" | "stderr";

/** How a monitor run was allowed to end. */
export type MonitorCompletion = "match" | "exit";

/** What ended a run before the process did. */
export type MonitorStopCause = "match" | "failure_match";

export interface MonitorTerminalResult {
  status: Exclude<MonitorStatus, "running">;
  elapsedMs: number;
  /** The configured completion mode that produced this result. */
  completion?: MonitorCompletion;
  /** Set when the contract, not the process, ended the run: the command never
   * reached its own end, so a `success` here can be a truncated run. */
  stoppedBy?: MonitorStopCause;
  output?: string[];
  outputTruncated?: boolean;
  matched?: string;
  captures?: Record<string, string>;
  capturesTruncated?: boolean;
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
  completion: "match" | "exit";
  compactReport?: boolean;
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
  compactReport: boolean;
  startedMonotonic: number;
  outputPaused: boolean;
  child?: ChildProcess;
  killTimer?: ReturnType<typeof setTimeout>;
  killPromise?: Promise<void>;
  killResolver?: () => void;
  buffers: Record<MonitorLogSource, string>;
  logs: MonitorLogEntry[];
  logBytes: number;
  pendingTerminal?: MonitorTerminalResult;
  successCandidate?: MonitorTerminalResult;
  drainTimer?: ReturnType<typeof setTimeout>;
  tailMatchTimers: Partial<Record<MonitorLogSource, ReturnType<typeof setTimeout>>>;
  matcher?: Worker;
  matchQueue: Array<string>;
  matchBusy: boolean;
  matchQueueBytes: number;
  closed?: { code: number | null; signal: NodeJS.Signals | null };
  outputTruncated: boolean;
  timeoutTimer?: ReturnType<typeof setTimeout>;
}

interface ArchivedMonitor {
  monitor: Monitor;
  logs: MonitorLogEntry[];
}

interface MatcherResponse {
  status: "success" | "failure";
  matched: string;
  captures?: Record<string, string>;
  capturesTruncated?: boolean;
  jsonCaptureError?: string;
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
  completion?: "match" | "exit";
  compactReport?: boolean;
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
  private cleanup = new Set<InternalMonitor>();
  private matcherCleanup = new Set<Promise<void>>();

  constructor(private readonly events: MonitorEvents) {}

  start(args: StartMonitorArgs): Monitor {
    if (args.completion !== undefined && args.completion !== "match" && args.completion !== "exit") {
      throw new Error("completion must be match or exit.");
    }
    compilePattern("result_pattern", args.resultPattern);
    if (args.failurePattern) compilePattern("failure_pattern", args.failurePattern);
    const monitor = this.createMonitor(args);
    const child = spawn(args.command, {
      shell: true,
      cwd: args.cwd,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
    });

    monitor.child = child;
    this.active.set(monitor.id, monitor);
    this.attachProcessHandlers(monitor);
    try {
      this.attachMatcher(monitor);
      this.scheduleTimeout(monitor);
    } catch (error) {
      this.complete(monitor, {
        status: "failure",
        elapsedMs: this.elapsed(monitor),
        reason: `matcher_error: ${error instanceof Error ? error.message : String(error)}`,
      }, false);
    }
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
        || (active?.droppedLogLines ?? archived?.monitor.droppedLogLines ?? 0) > 0
        || (active?.outputTruncated ?? archived?.monitor.terminal?.outputTruncated ?? logs.some((entry) => entry.text.endsWith("...[truncated]"))),
    };
  }

  async stopAllOnShutdown(): Promise<void> {
    for (const monitor of [...this.active.values()]) {
      this.clearDrain(monitor);
      this.complete(
        monitor,
        { status: "stopped", elapsedMs: this.elapsed(monitor), reason: "session_shutdown" },
        false,
        true,
      );
    }
    for (const monitor of this.cleanup) monitor.killTimer?.ref();
    await Promise.all([
      ...[...this.cleanup].map((monitor) => monitor.killPromise),
      ...this.matcherCleanup,
    ]);
  }

  private clearDrain(monitor: InternalMonitor): void {
    if (monitor.drainTimer) {
      clearTimeout(monitor.drainTimer);
      monitor.drainTimer = undefined;
    }
    this.clearTailMatch(monitor);
    this.clearTimeoutTimer(monitor);
    monitor.pendingTerminal = undefined;
  }

  private createMonitor(args: StartMonitorArgs): InternalMonitor {
    return {
      id: `monitor_${randomUUID()}`,
      description: args.description,
      command: args.command,
      resultPattern: args.resultPattern,
      failurePattern: args.failurePattern,
      completion: args.completion ?? "match",
      compactReport: args.compactReport ?? false,
      timeoutMs: normalizeTimeout(args.timeoutMs),
      startedAt: Date.now(),
      startedMonotonic: performance.now(),
      outputPaused: false,
      status: "running",
      notifyTerminal: args.notifyTerminal ?? true,
      retainedLogLines: 0,
      droppedLogLines: 0,
      buffers: { stdout: "", stderr: "" },
      logs: [],
      logBytes: 0,
      tailMatchTimers: {},
      matchQueue: [],
      matchBusy: false,
      matchQueueBytes: 0,
      outputTruncated: false,
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

  private clearTimeoutTimer(monitor: InternalMonitor): void {
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
    // A trailing CR may be the first half of a split CRLF record delimiter.
    const payloadBytes = Buffer.byteLength(monitor.buffers[source].replace(/\r$/, ""));
    if (monitor.status === "running" && !monitor.outputPaused && payloadBytes > MAX_LINE_BUFFER) {
      if (monitor.pendingTerminal) {
        this.appendLog(monitor, source, monitor.buffers[source], true);
        monitor.buffers[source] = "";
        return;
      }
      // Framing a long physical line into independent fragments changes ^/$
      // semantics. Fail explicitly rather than manufacture a matching record.
      this.complete(monitor, { status: "failure", elapsedMs: this.elapsed(monitor), reason: "matcher_line_limit" });
      return;
    }
    this.scheduleTailMatch(monitor, source);
  }

  private drainCompleteLines(monitor: InternalMonitor, source: MonitorLogSource): void {
    let newline: number;
    while (
      monitor.status === "running"
      && !monitor.outputPaused
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
  ): void {
    if (monitor.status !== "running") return;
    this.appendLog(monitor, source, rawLine, continued);

    // During drain, accumulate lines but do not check for further matches.
    if (monitor.pendingTerminal) return;

    if (Buffer.byteLength(rawLine) > MAX_LINE_BUFFER) {
      this.complete(monitor, { status: "failure", elapsedMs: this.elapsed(monitor), reason: "matcher_line_limit" });
      return;
    }

    this.queueMatch(monitor, rawLine);
  }

  /** A plain JavaScript eval worker works under Node, tsx and Pi's jiti loader.
   * Each monitor owns one interruptible matcher; only one bounded batch is in flight. */
  private attachMatcher(monitor: InternalMonitor): void {
    const worker = new Worker(`
      const { parentPort, workerData } = require('node:worker_threads');
      const success = new RegExp(workerData.success);
      const failure = workerData.failure ? new RegExp(workerData.failure) : undefined;
      const prefix = ${utf8Prefix.toString()};
      const boundedValue = (value, stringBudget, encodedBudget) => {
        const bounded = prefix(value, stringBudget);
        if (Buffer.byteLength(JSON.stringify(bounded)) <= encodedBudget) return bounded;
        let low = 0;
        let high = Buffer.byteLength(bounded);
        while (low < high) {
          const middle = Math.ceil((low + high) / 2);
          if (Buffer.byteLength(JSON.stringify(prefix(bounded, middle))) <= encodedBudget) low = middle;
          else high = middle - 1;
        }
        return prefix(bounded, low);
      };
      const projectMatch = (match, status) => {
        const response = { status, matched: prefix(match[0], workerData.textBudget) };
        if (!match.groups) return response;
        const captures = Object.create(null);
        let used = 2;
        let count = 0;
        // JSON keeps its full payload first whenever it fits. Other captures
        // retain their declaration order and share the remaining JSON budget.
        const names = Object.keys(match.groups);
        if (names.includes('json')) {
          names.splice(names.indexOf('json'), 1);
          names.unshift('json');
        }
        for (const name of names) {
          const original = match.groups[name];
          if (typeof original !== 'string') continue;
          const overhead = Buffer.byteLength(JSON.stringify(name)) + 1 + (count > 0 ? 1 : 0);
          const available = workerData.captureBudget - used - overhead;
          if (available < 2) {
            response.capturesTruncated = true;
            if (name === 'json') response.jsonCaptureError = 'json capture exceeds serialized capture budget';
            continue;
          }
          const value = boundedValue(original, name === 'json' ? workerData.jsonBudget : workerData.textBudget, available);
          if (value !== original) {
            response.capturesTruncated = true;
            if (name === 'json') response.jsonCaptureError = 'json capture exceeds ' + workerData.jsonBudget + '-byte capture or serialized budget';
          }
          captures[name] = value;
          used += overhead + Buffer.byteLength(JSON.stringify(value));
          count += 1;
        }
        response.captures = captures;
        return response;
      };
      let successFound = false;
      parentPort.on('message', lines => {
        let firstSuccess;
        for (const line of lines) {
          const failed = failure?.exec(line);
          // Exit mode has already selected its immutable first success.
          // Keep evaluating failures without re-projecting later success payloads.
          const match = failed || (workerData.waitForExit && successFound ? null : success.exec(line));
          if (match) {
            const response = projectMatch(match, failed ? 'failure' : 'success');
            if (failed || !workerData.waitForExit) {
              parentPort.postMessage(response);
              return;
            }
            firstSuccess ??= response;
            successFound = true;
          }
        }
        parentPort.postMessage(firstSuccess ?? null);
      });
    `, { eval: true, execArgv: [], workerData: {
      success: monitor.resultPattern, failure: monitor.failurePattern, waitForExit: monitor.completion === "exit",
      textBudget: MAX_RESULT_TEXT, jsonBudget: MAX_RESULT_JSON_BYTES, captureBudget: MAX_RESULT_CAPTURE_BYTES,
    } });
    monitor.matcher = worker;
    worker.on("message", (response: MatcherResponse | null) => {
      monitor.matchBusy = false;
      if (monitor.status !== "running") return;
      if (response && !monitor.pendingTerminal) {
        const terminal = buildMatchedResult(response, this.elapsed(monitor));
        if (monitor.completion === "exit" && response.status === "success") {
          monitor.successCandidate ??= terminal;
        } else {
          // The contract ends the run here, so the process never reaches its own
          // end. A success in this branch is a truncated run, not a finished one.
          terminal.stoppedBy = response.status === "success" ? "match" : "failure_match";
          this.beginDrain(monitor, terminal);
          monitor.matchQueue = [];
          monitor.matchQueueBytes = 0;
        }
      }
      this.dispatchMatch(monitor);
      this.pumpPausedOutput(monitor);
    });
    worker.on("error", (error) => {
      if (monitor.status !== "running") return;
      this.complete(monitor, { status: "failure", elapsedMs: this.elapsed(monitor), reason: `matcher_error: ${error instanceof Error ? error.message : String(error)}` }, true);
    });
    worker.on("exit", (code) => {
      if (monitor.status === "running" && monitor.matcher === worker) {
        this.complete(monitor, { status: "failure", elapsedMs: this.elapsed(monitor), reason: `matcher_exit: ${code}` }, true);
      }
    });
  }

  private queueMatch(monitor: InternalMonitor, line: string): void {
    if (monitor.pendingTerminal || monitor.status !== "running") return;
    // Never silently skip a contract evaluation when output outruns the matcher.
    if (monitor.matchQueue.length >= 16_384 || monitor.matchQueueBytes + Buffer.byteLength(line) > 4 * 1024 * 1024) {
      this.complete(monitor, { status: "failure", elapsedMs: this.elapsed(monitor), reason: "matcher_queue_limit" }, true);
      return;
    }
    monitor.matchQueue.push(line);
    monitor.matchQueueBytes += Buffer.byteLength(line);
    this.dispatchMatch(monitor);
    if (monitor.matchQueue.length >= MATCH_PAUSE_LINES || monitor.matchQueueBytes >= MATCH_PAUSE_BYTES) {
      monitor.outputPaused = true;
      monitor.child?.stdout?.pause();
      monitor.child?.stderr?.pause();
    }
  }

  private pumpPausedOutput(monitor: InternalMonitor): void {
    if (!monitor.outputPaused || monitor.status !== "running") return;
    monitor.outputPaused = false;
    for (const source of ["stdout", "stderr"] as const) {
      this.handleChunk(monitor, source, "");
    }
    if (!monitor.outputPaused && monitor.status === "running") {
      if (monitor.closed) {
        this.drainFinalBuffers(monitor);
        this.dispatchMatch(monitor);
      }
      monitor.child?.stdout?.resume();
      monitor.child?.stderr?.resume();
    }
  }

  private dispatchMatch(monitor: InternalMonitor): void {
    if (monitor.matchBusy || monitor.status !== "running") return;
    const lines = monitor.matchQueue.splice(0, 64);
    for (const line of lines) monitor.matchQueueBytes -= Buffer.byteLength(line);
    if (lines.length > 0 && !monitor.pendingTerminal) {
      monitor.matchBusy = true;
      monitor.matcher?.postMessage(lines);
      return;
    }
    if (monitor.closed && !monitor.buffers.stdout && !monitor.buffers.stderr) {
      this.finishClose(monitor, monitor.closed.code, monitor.closed.signal);
    }
  }

  private scheduleTailMatch(monitor: InternalMonitor, source: MonitorLogSource): void {
    if (monitor.tailMatchTimers[source]) clearTimeout(monitor.tailMatchTimers[source]);
    delete monitor.tailMatchTimers[source];
    if (monitor.completion === "exit" || monitor.status !== "running" || monitor.pendingTerminal || !monitor.buffers[source] || monitor.buffers[source].includes("\n")) return;
    const timer = setTimeout(() => {
      delete monitor.tailMatchTimers[source];
      if (monitor.buffers[source]) this.queueMatch(monitor, monitor.buffers[source].replace(/\r$/, ""));
    }, TAIL_MATCH_IDLE_MS);
    monitor.tailMatchTimers[source] = timer;
    timer.unref();
  }

  private clearTailMatch(monitor: InternalMonitor): void {
    for (const timer of Object.values(monitor.tailMatchTimers)) clearTimeout(timer);
    monitor.tailMatchTimers = {};
  }

  private beginDrain(monitor: InternalMonitor, terminal: MonitorTerminalResult): void {
    monitor.pendingTerminal = terminal;
    this.clearTailMatch(monitor);
    monitor.drainTimer = setTimeout(() => this.finalizeDrain(monitor), DRAIN_GRACE_MS);
    monitor.drainTimer.unref();
    this.pumpPausedOutput(monitor);
  }

  private finalizeDrain(monitor: InternalMonitor): void {
    if (!monitor.pendingTerminal || monitor.status !== "running") return;
    this.drainFinalBuffers(monitor);
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
    const truncated = Buffer.byteLength(rawLine) > MAX_LINE_LENGTH || continued;
    monitor.outputTruncated ||= truncated;
    const suffix = truncated ? "...[truncated]" : "";
    const text = `${utf8Prefix(rawLine, MAX_LINE_LENGTH - Buffer.byteLength(suffix))}${suffix}`;
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
    monitor.closed = { code, signal };
    this.clearTailMatch(monitor);
    for (const source of ["stdout", "stderr"] as const) this.drainCompleteLines(monitor, source);
    if (!monitor.outputPaused) this.drainFinalBuffers(monitor);
    if (monitor.status !== "running") return;
    this.dispatchMatch(monitor);
  }

  private finishClose(monitor: InternalMonitor, code: number | null, signal: NodeJS.Signals | null): void {
    if (monitor.status !== "running") return;
    // All complete and trailing lines have been evaluated before exit fallback.
    if (monitor.pendingTerminal) {
      if (monitor.drainTimer) {
        clearTimeout(monitor.drainTimer);
        monitor.drainTimer = undefined;
      }
      this.complete(monitor, monitor.pendingTerminal, true);
      return;
    }

    if (code === 0 && monitor.successCandidate) {
      const terminal = { ...monitor.successCandidate, elapsedMs: this.elapsed(monitor), exitCode: code, signal };
      if (terminal.resultParseError) {
        terminal.status = "failure";
        terminal.reason = "invalid_json_result";
      }
      this.complete(monitor, terminal);
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

  private drainFinalBuffers(monitor: InternalMonitor): void {
    for (const source of ["stdout", "stderr"] as const) {
      const line = monitor.buffers[source].replace(/\r$/, "");
      monitor.buffers[source] = "";
      if (line.length > 0) {
        this.handleLine(monitor, source, line, false);
      }
      if (monitor.status !== "running") return;
    }
  }

  private complete(
    monitor: InternalMonitor,
    terminal: MonitorTerminalResult,
    notify = true,
    keepKillTimerAlive = false,
  ): void {
    if (monitor.status !== "running") return;
    this.clearTimeoutTimer(monitor);
    this.clearTailMatch(monitor);
    if (monitor.drainTimer) clearTimeout(monitor.drainTimer);
    // The mode that produced this result travels with it, so every reader can
    // say whether the process or the contract ended the run.
    terminal.completion ??= monitor.completion;
    // Commit diagnostics without evaluating contracts after the terminal choice.
    for (const source of ["stdout", "stderr"] as const) {
      this.appendLog(monitor, source, monitor.buffers[source].replace(/\r$/, ""), false);
      monitor.buffers[source] = "";
    }
    const worker = monitor.matcher;
    monitor.matcher = undefined;
    if (worker) {
      const termination = worker.terminate().then(() => {}, () => {});
      this.matcherCleanup.add(termination);
      void termination.then(() => this.matcherCleanup.delete(termination));
    }
    monitor.matchQueue = [];
    monitor.matchQueueBytes = 0;
    if (terminal.status !== "success") {
      const output = this.tail(monitor.id);
      terminal.output = collapseRepeatedLines(output?.lines ?? []);
      while (Buffer.byteLength(terminal.output.join("\n")) > MAX_RESULT_OUTPUT_BYTES) {
        terminal.output.shift();
        monitor.outputTruncated = true;
      }
      terminal.outputTruncated = (output?.truncated ?? false) || monitor.outputTruncated;
    }
    // Even a naturally closed shell can leave its detached descendants alive.
    this.killTree(monitor, keepKillTimerAlive);
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
    this.cleanup.add(monitor);
    monitor.killPromise = new Promise<void>((resolve) => {
      monitor.killResolver = resolve;
      monitor.killTimer = setTimeout(() => {
        monitor.killTimer = undefined;
        signalGroup("SIGKILL");
        monitor.killResolver = undefined;
        this.cleanup.delete(monitor);
        resolve();
      }, KILL_GRACE_MS);
      if (!keepTimerAlive) monitor.killTimer.unref();
    });
  }

  private elapsed(monitor: InternalMonitor): number {
    return performance.now() - monitor.startedMonotonic;
  }

  private public(monitor: InternalMonitor): Monitor {
    return {
      id: monitor.id,
      description: monitor.description,
      command: monitor.command,
      resultPattern: monitor.resultPattern,
      failurePattern: monitor.failurePattern,
      completion: monitor.completion,
      compactReport: monitor.compactReport,
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
  if (containsPcreCaseInsensitiveFlag(pattern)) {
    throw new Error(
      `invalid ${name}: JavaScript RegExp does not support bare (?i) case-insensitive flags. ` +
        "Use (?i:error|failed) to scope case-insensitivity to that group, or explicit case alternatives such as [eE][rR][rR][oO][rR].",
    );
  }
  try {
    return new RegExp(pattern);
  } catch (error) {
    throw new Error(`invalid ${name}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function containsPcreCaseInsensitiveFlag(pattern: string): boolean {
  let inCharacterClass = false;
  for (let index = 0; index < pattern.length; index += 1) {
    if (pattern[index] === "\\") {
      index += 1;
      continue;
    }
    if (pattern[index] === "[") {
      inCharacterClass = true;
      continue;
    }
    if (pattern[index] === "]") {
      inCharacterClass = false;
      continue;
    }
    if (!inCharacterClass && pattern.startsWith("(?i)", index)) return true;
  }
  return false;
}

function buildMatchedResult(
  response: MatcherResponse,
  elapsedMs: number,
): MonitorTerminalResult {
  const captures = response.captures;
  const terminal: MonitorTerminalResult = {
    status: response.status,
    elapsedMs,
    matched: response.matched,
    captures,
    ...(response.capturesTruncated ? { capturesTruncated: true } : {}),
  };
  if (response.jsonCaptureError) {
    terminal.resultParseError = response.jsonCaptureError;
    return terminal;
  }
  if (captures?.json === undefined) return terminal;
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
    if (bytes + entry.bytes + (selected.length > 0 ? 1 : 0) > maxBytes) break;
    selected.unshift(entry);
    bytes += entry.bytes + (selected.length > 1 ? 1 : 0);
  }
  return selected;
}

function collapseRepeatedLines(lines: string[]): string[] {
  const result: string[] = [];
  for (let index = 0; index < lines.length;) {
    const line = lines[index];
    let end = index + 1;
    while (end < lines.length && lines[end] === line) end += 1;
    result.push(formatRepeatedLine(line, end - index));
    index = end;
  }
  return result;
}

function formatRepeatedLine(line: string, count: number): string {
  return count > 1 ? `${line} (repeated ${count} times)` : line;
}

/** Prefix at a Unicode code point boundary, with an exact UTF-8 byte budget. */
function utf8Prefix(text: string, maxBytes: number): string {
  if (Buffer.byteLength(text) <= maxBytes) return text;
  let bytes = 0;
  let length = 0;
  for (const character of text) {
    bytes += Buffer.byteLength(character);
    if (bytes > maxBytes) break;
    length += character.length;
  }
  return text.slice(0, length);
}
