export interface FollowUpReport {
  subject: string;
  body: string;
  runId?: string;
}

export interface FollowUpQueueOptions {
  isIdle: () => boolean;
  dispatch: (content: string) => void;
  onFailure?: (message: string) => void;
  agentStartTimeoutMs?: number;
  retryBaseDelayMs?: number;
  retryMaxDelayMs?: number;
}

interface PendingDispatch {
  reports: FollowUpReport[];
  content: string;
  prepared: boolean;
  started: boolean;
}

/**
 * Serializes automatic reports sent through Pi's void sendUserMessage API.
 *
 * The API reports asynchronous preflight failures through the runtime error
 * channel, so this queue uses agent lifecycle events for success and a bounded
 * watchdog for attempts that never reach agent_start.
 */
export class FollowUpQueue {
  private readonly isIdle: FollowUpQueueOptions["isIdle"];
  private readonly dispatch: FollowUpQueueOptions["dispatch"];
  private readonly onFailure: (message: string) => void;
  private readonly agentStartTimeoutMs: number;
  private readonly retryBaseDelayMs: number;
  private readonly retryMaxDelayMs: number;
  private pending: FollowUpReport[] = [];
  private active: PendingDispatch | undefined;
  private pumpScheduled = false;
  private retryTimer: ReturnType<typeof setTimeout> | undefined;
  private watchdogTimer: ReturnType<typeof setTimeout> | undefined;
  private generation = 0;
  private failureCount = 0;

  constructor(options: FollowUpQueueOptions) {
    this.isIdle = options.isIdle;
    this.dispatch = options.dispatch;
    this.onFailure = options.onFailure ?? (() => {});
    this.agentStartTimeoutMs = options.agentStartTimeoutMs ?? 30_000;
    this.retryBaseDelayMs = options.retryBaseDelayMs ?? 1_000;
    this.retryMaxDelayMs = options.retryMaxDelayMs ?? 30_000;
  }

  enqueue(report: FollowUpReport): void {
    this.pending.push(report);
    this.schedulePump();
  }

  /** Match the active dispatch to the prompt that Pi is about to start. */
  onBeforeAgentStart(prompt: string): void {
    if (!this.active || this.active.prepared || prompt !== this.active.content) return;
    this.active.prepared = true;
  }

  /** Mark the matching dispatch started after before_agent_start completes. */
  onAgentStart(): void {
    if (!this.active || !this.active.prepared || this.active.started) return;
    this.active.started = true;
    this.clearWatchdog();
    this.failureCount = 0;
  }

  /** Release a completed dispatch; unrelated settled events are ignored. */
  onAgentSettled(): void {
    if (this.active && !this.active.started) return;
    if (this.active) {
      this.active = undefined;
      this.failureCount = 0;
    }
    this.schedulePump();
  }

  /** Drop all reports and invalidate callbacks from the previous session. */
  reset(): void {
    this.generation++;
    this.pending = [];
    this.active = undefined;
    this.pumpScheduled = false;
    this.failureCount = 0;
    this.clearRetryTimer();
    this.clearWatchdog();
  }

  get pendingCount(): number {
    return this.pending.length + (this.active?.reports.length ?? 0);
  }

  private schedulePump(): void {
    if (this.pumpScheduled) return;
    this.pumpScheduled = true;
    const generation = this.generation;
    setTimeout(() => {
      this.pumpScheduled = false;
      if (generation !== this.generation) return;
      this.pump();
    }, 0);
  }

  private pump(): void {
    if (this.active || this.retryTimer || this.pending.length === 0 || !this.isIdle()) return;
    const reports = this.pending.splice(0);
    const content = formatReports(reports);
    const queuedIntoActiveRun = !this.isIdle();
    this.active = {
      reports,
      content,
      prepared: queuedIntoActiveRun,
      started: queuedIntoActiveRun,
    };
    const generation = this.generation;
    try {
      this.dispatch(content);
    } catch (error) {
      this.failActive(generation, error instanceof Error ? error.message : String(error));
      return;
    }
    if (!queuedIntoActiveRun) {
      this.watchdogTimer = setTimeout(() => {
        if (generation !== this.generation || !this.active || this.active.started) return;
        this.failActive(generation, "Pi did not start the automatic teammate follow-up.");
      }, this.agentStartTimeoutMs);
    }
  }

  private failActive(generation: number, message: string): void {
    if (generation !== this.generation || !this.active) return;
    const failed = this.active;
    this.active = undefined;
    this.pending.unshift(...failed.reports);
    this.clearWatchdog();
    this.failureCount++;
    const delay = Math.min(
      this.retryMaxDelayMs,
      this.retryBaseDelayMs * 2 ** Math.max(0, this.failureCount - 1),
    );
    this.onFailure(`${message} Retrying in ${Math.ceil(delay / 1000)}s.`);
    this.retryTimer = setTimeout(() => {
      this.retryTimer = undefined;
      if (generation === this.generation) this.schedulePump();
    }, delay);
  }

  private clearRetryTimer(): void {
    if (!this.retryTimer) return;
    clearTimeout(this.retryTimer);
    this.retryTimer = undefined;
  }

  private clearWatchdog(): void {
    if (!this.watchdogTimer) return;
    clearTimeout(this.watchdogTimer);
    this.watchdogTimer = undefined;
  }
}

function formatReports(reports: FollowUpReport[]): string {
  return reports
    .map(({ subject, body }) => `Teammate update: ${subject}\n${body}`)
    .join("\n\n");
}
