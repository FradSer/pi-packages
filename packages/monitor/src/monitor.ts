import { spawn, type ChildProcess } from "node:child_process";

export const DEFAULT_TIMEOUT_MS = 5 * 60 * 1000;
export const MAX_TIMEOUT_MS = 60 * 60 * 1000;
export const BATCH_WINDOW_MS = 200;
export const MAX_EVENTS = 40;
export const KILL_GRACE_MS = 1000;

export type MonitorStatus = "running" | "stopped" | "completed" | "timeout" | "error" | "event_limit";

export interface Monitor {
  id: string;
  description: string;
  command: string;
  persistent: boolean;
  timeoutMs: number;
  startedAt: number;
  events: number;
  status: MonitorStatus;
  /** Captured stderr; reported when the monitor ends. */
  stderr: string;
  /** Reason detail for non-"running" monitors (error message or event-limit note). */
  finalOutput: string;
  /** Number of stdout lines suppressed by the match filter. */
  skipped: number;
}

interface InternalMonitor extends Monitor {
  child?: ChildProcess;
  timeoutTimer?: ReturnType<typeof setTimeout>;
  flushTimer?: ReturnType<typeof setTimeout>;
  pending: string[];
  lineBuffer: string;
  matcher?: RegExp;
}

export interface MonitorEvents {
  /** A batch of stdout lines arrived; the agent should be woken with them. */
  onEvent: (monitor: Monitor, lines: string[]) => void;
  /** The monitor ended (any reason except a manual stop from the agent). */
  onStop: (monitor: Monitor, reason: MonitorStatus) => void;
}

export interface StartMonitorArgs {
  command: string;
  description: string;
  timeoutMs?: number;
  persistent?: boolean;
  match?: string;
  cwd?: string;
}

/** Session-scoped background monitors: spawn, stream stdout in batches, cap events, stop. */
export class MonitorManager {
  private monitors = new Map<string, InternalMonitor>();
  private counter = 0;
  private events: MonitorEvents;

  constructor(events: MonitorEvents) {
    this.events = events;
  }

  start(args: StartMonitorArgs): Monitor {
    const id = `monitor_${++this.counter}`;
    const persistent = args.persistent === true;
    const timeoutMs = Math.min(Math.max(args.timeoutMs ?? DEFAULT_TIMEOUT_MS, 1), MAX_TIMEOUT_MS);

    let matcher: RegExp | undefined;
    if (args.match) {
      try {
        matcher = new RegExp(args.match, "i");
      } catch (err) {
        throw new Error(`invalid match pattern: ${err instanceof Error ? err.message : String(err)}`);
      }
    }

    const monitor: InternalMonitor = {
      id,
      description: args.description,
      command: args.command,
      persistent,
      timeoutMs,
      startedAt: Date.now(),
      events: 0,
      status: "running",
      stderr: "",
      finalOutput: "",
      skipped: 0,
      pending: [],
      lineBuffer: "",
      matcher,
    };

    const child = spawn(args.command, {
      shell: true,
      cwd: args.cwd,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    monitor.child = child;

    child.stdout?.on("data", (chunk: Buffer) => this.handleStdout(monitor, chunk.toString()));
    child.stderr?.on("data", (chunk: Buffer) => {
      monitor.stderr += chunk.toString();
    });
    child.on("error", (err) => {
      monitor.finalOutput = err.message;
      this.finalize(monitor, "error");
    });
    child.on("exit", (code) => {
      this.drainBuffer(monitor);
      this.flush(monitor);
      if (monitor.status !== "running") return; // already finalized (e.g. timeout)
      monitor.finalOutput = monitor.stderr.trim();
      this.finalize(monitor, code === 0 ? "completed" : "error");
    });

    if (!persistent) {
      monitor.timeoutTimer = setTimeout(() => {
        this.killTree(monitor.child);
        this.drainBuffer(monitor);
        this.flush(monitor);
        monitor.finalOutput = monitor.stderr.trim();
        this.finalize(monitor, "timeout");
      }, timeoutMs);
    }

    this.monitors.set(id, monitor);
    return this.public(monitor);
  }

  /** Stop one monitor by id, or all of them when id is omitted. */
  stop(id?: string): { stopped: string[] } {
    if (id) {
      const monitor = this.monitors.get(id);
      if (!monitor) return { stopped: [] };
      this.killTree(monitor.child);
      this.finalize(monitor, "stopped");
      return { stopped: [id] };
    }
    const ids = [...this.monitors.keys()];
    for (const monitorId of ids) {
      const monitor = this.monitors.get(monitorId);
      if (monitor) {
        this.killTree(monitor.child);
        this.finalize(monitor, "stopped");
      }
    }
    return { stopped: ids };
  }

  list(): Monitor[] {
    return [...this.monitors.values()].map((monitor) => this.public(monitor));
  }

  stopAllOnShutdown(): void {
    this.stop();
  }

  private handleStdout(monitor: InternalMonitor, text: string): void {
    if (monitor.status !== "running") return;
    monitor.lineBuffer += text;
    let idx: number;
    while ((idx = monitor.lineBuffer.indexOf("\n")) !== -1) {
      const line = monitor.lineBuffer.slice(0, idx).replace(/\r$/, "");
      monitor.lineBuffer = monitor.lineBuffer.slice(idx + 1);
      if (line.trim() === "") continue;
      if (monitor.matcher && !monitor.matcher.test(line)) {
        monitor.skipped += 1;
        continue;
      }
      monitor.pending.push(line);
      this.scheduleFlush(monitor);
    }
  }

  private scheduleFlush(monitor: InternalMonitor): void {
    if (monitor.flushTimer) return;
    monitor.flushTimer = setTimeout(() => this.flush(monitor), BATCH_WINDOW_MS);
  }

  /** Move a trailing, unterminated line into pending so final output is not lost. */
  private drainBuffer(monitor: InternalMonitor): void {
    const rest = monitor.lineBuffer.replace(/\r$/, "");
    monitor.lineBuffer = "";
    if (rest.trim() !== "") monitor.pending.push(rest);
  }

  private flush(monitor: InternalMonitor): void {
    if (monitor.status !== "running") return;
    if (monitor.flushTimer) {
      clearTimeout(monitor.flushTimer);
      monitor.flushTimer = undefined;
    }
    const lines = monitor.pending;
    monitor.pending = [];
    if (lines.length === 0) return;

    if (monitor.events + 1 > MAX_EVENTS) {
      this.killTree(monitor.child);
      this.finalize(monitor, "event_limit");
      return;
    }
    monitor.events += 1;
    this.events.onEvent(this.public(monitor), lines);
  }

  private finalize(monitor: InternalMonitor, status: MonitorStatus): void {
    if (monitor.status !== "running") return;
    monitor.status = status;
    if (monitor.timeoutTimer) clearTimeout(monitor.timeoutTimer);
    if (monitor.flushTimer) clearTimeout(monitor.flushTimer);
    monitor.pending = [];
    if (monitor.skipped > 0) {
      const note = `[suppressed ${monitor.skipped} non-matching stdout line(s)]`;
      monitor.finalOutput = monitor.finalOutput ? `${monitor.finalOutput}\n${note}` : note;
    }
    this.monitors.delete(monitor.id);
    this.events.onStop(this.public(monitor), status);
  }

  /** Kill the whole process group (spawned detached, so the child leads its own group). */
  private killTree(child?: ChildProcess): void {
    if (!child || !child.pid) return;
    const pid = child.pid;
    const signalGroup = (sig: NodeJS.Signals): void => {
      try {
        process.kill(-pid, sig);
      } catch {
        try {
          child.kill(sig);
        } catch {
          // already gone
        }
      }
    };
    signalGroup("SIGTERM");
    // Escalate to SIGKILL if the process group survives the graceful signal.
    setTimeout(() => signalGroup("SIGKILL"), KILL_GRACE_MS).unref?.();
  }

  private public(monitor: InternalMonitor): Monitor {
    return {
      id: monitor.id,
      description: monitor.description,
      command: monitor.command,
      persistent: monitor.persistent,
      timeoutMs: monitor.timeoutMs,
      startedAt: monitor.startedAt,
      events: monitor.events,
      status: monitor.status,
      stderr: monitor.stderr,
      finalOutput: monitor.finalOutput,
      skipped: monitor.skipped,
    };
  }
}
