export const TEAMMATE_REPORT_MESSAGE_TYPE = "agent-teams-report";
export const TEAMMATE_HARNESS_MESSAGE_TYPE = "agent-teams-harness";

export interface FollowUpReport {
  teammate?: string;
  agent?: string;
  spawnId?: string;
  body: string;
  /** Worker-authored reports are the default; harness events use a separate envelope. */
  origin?: "teammate" | "harness";
  harnessEvent?: {
    type: string;
    subject: string;
  };
  finished?: boolean;
  /** Original append-only outbox event identifier, retained for session forensics. */
  eventId?: string;
  /** Original worker status, including omitted status, retained for session forensics. */
  status?: "in_progress" | "completed" | "failed";
  health?: {
    state: "stalled";
    silenceMs: number;
  };
  runId?: string;
  /** Wall-clock time the message was authored; rendered in the envelope so a
   *  report delivered after a busy period keeps its original timestamp. */
  timestamp?: number;
}

export interface FollowUpReportGroup {
  teammate: string;
  reports: FollowUpReport[];
}

export function groupReportsByTeammate(reports: FollowUpReport[]): FollowUpReportGroup[] {
  const groups = new Map<string, FollowUpReportGroup>();
  for (const report of reports) {
    const teammate = report.teammate ?? report.agent ?? "teammate";
    if (report.health) {
      groups.set(`health:${groups.size}:${teammate}`, { teammate, reports: [report] });
      continue;
    }
    if (report.origin === "harness" || report.harnessEvent) {
      groups.set(`harness:${groups.size}:${teammate}`, { teammate, reports: [report] });
      continue;
    }
    const key = `message:${teammate}`;
    const group = groups.get(key);
    if (group) {
      group.reports.push(report);
    } else {
      groups.set(key, { teammate, reports: [report] });
    }
  }
  return [...groups.values()];
}

export interface FollowUpQueueOptions {
  isIdle: () => boolean;
  dispatch: (reports: FollowUpReport[], content: string) => void;
  /** Set when dispatch itself starts the agent run without before_agent_start. */
  prepareOnDispatch?: boolean;
  onFailure?: (message: string) => void;
  agentStartTimeoutMs?: number;
  retryBaseDelayMs?: number;
  retryMaxDelayMs?: number;
  maxAttempts?: number;
}

interface PendingBatch {
  reports: FollowUpReport[];
  attempts: number;
  retrying: boolean;
}

interface PendingDispatch {
  reports: FollowUpReport[];
  content: string;
  attempts: number;
  prepared: boolean;
  started: boolean;
}

/**
 * Serializes automatic reports sent through Pi's void sendMessage API.
 *
 * The API reports asynchronous preflight failures through the runtime error
 * channel, so this queue uses agent lifecycle events for success and a bounded
 * watchdog for attempts that never reach agent_start. A report arriving during
 * an active leader run is dispatched to Pi's native follow-up queue; this
 * queue still serializes later reports until that run settles.
 */
export class FollowUpQueue {
  private readonly isIdle: FollowUpQueueOptions["isIdle"];
  private readonly dispatch: FollowUpQueueOptions["dispatch"];
  private readonly onFailure: (message: string) => void;
  private readonly prepareOnDispatch: boolean;
  private readonly agentStartTimeoutMs: number;
  private readonly retryBaseDelayMs: number;
  private readonly retryMaxDelayMs: number;
  private readonly maxAttempts: number;
  private pending: PendingBatch[] = [];
  private active: PendingDispatch | undefined;
  private pumpScheduled = false;
  private retryTimer: ReturnType<typeof setTimeout> | undefined;
  private watchdogTimer: ReturnType<typeof setTimeout> | undefined;
  private generation = 0;
  private deadLetter: FollowUpReport[] = [];
  /** Reports suppressed after their teammate was intentionally stopped. They
   * remain inspectable in runtime diagnostics but never begin a leader turn. */
  private archived: FollowUpReport[] = [];
  private archivedSpawnIds = new Set<string>();

  constructor(options: FollowUpQueueOptions) {
    this.isIdle = options.isIdle;
    this.dispatch = options.dispatch;
    this.onFailure = options.onFailure ?? (() => {});
    this.prepareOnDispatch = options.prepareOnDispatch ?? false;
    this.agentStartTimeoutMs = options.agentStartTimeoutMs ?? 30_000;
    this.retryBaseDelayMs = options.retryBaseDelayMs ?? 1_000;
    this.retryMaxDelayMs = options.retryMaxDelayMs ?? 30_000;
    this.maxAttempts = Math.max(1, options.maxAttempts ?? 5);
  }

  enqueue(report: FollowUpReport): void {
    if (report.spawnId && this.archivedSpawnIds.has(report.spawnId)) {
      this.archived.push(report);
      return;
    }
    this.pending.push({ reports: [report], attempts: 0, retrying: false });
    this.schedulePump();
  }

  /** Archive pending reports from one stopped spawn before they can wake the leader.
   * A dispatch already accepted by Pi cannot be retracted, so it is deliberately
   * left alone; this method only changes transitions the harness still owns. */
  archiveSpawn(spawnId: string): FollowUpReport[] {
    this.archivedSpawnIds.add(spawnId);
    const moved: FollowUpReport[] = [];
    for (const batch of this.pending) {
      const retained = batch.reports.filter((report) => report.spawnId !== spawnId);
      const archived = batch.reports.filter((report) => report.spawnId === spawnId);
      this.archived.push(...archived);
      moved.push(...archived);
      batch.reports = retained;
    }
    this.pending = this.pending.filter((batch) => batch.reports.length > 0);
    return moved;
  }

  /** Match the active dispatch to the prompt that Pi is about to start. */
  onBeforeAgentStart(prompt: string): void {
    if (!this.active || this.active.prepared || prompt !== this.active.content) return;
    this.active.prepared = true;
  }

  /** Mark the matching dispatch started after Pi accepts the message. */
  onAgentStart(): void {
    if (!this.active || !this.active.prepared || this.active.started) return;
    this.active.started = true;
    this.clearWatchdog();
  }

  /** Release a completed dispatch; unrelated settled events are ignored. */
  onAgentSettled(): void {
    if (this.active && !this.active.started) return;
    if (this.active) this.active = undefined;
    this.schedulePump();
  }

  /** Drop all reports and invalidate callbacks from the previous session. */
  reset(): void {
    this.generation++;
    this.pending = [];
    this.deadLetter = [];
    this.archived = [];
    this.archivedSpawnIds.clear();
    this.active = undefined;
    this.pumpScheduled = false;
    this.clearRetryTimer();
    this.clearWatchdog();
  }

  get pendingCount(): number {
    return this.pending.reduce((count, batch) => count + batch.reports.length, 0)
      + (this.active?.reports.length ?? 0);
  }

  get deadLetterCount(): number {
    return this.deadLetter.length;
  }

  get archivedCount(): number {
    return this.archived.length;
  }

  archivedReportsFor(spawnId: string): FollowUpReport[] {
    return this.archived.filter((report) => report.spawnId === spawnId);
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
    if (this.active || this.retryTimer || this.pending.length === 0) return;
    const first = this.pending.shift();
    if (!first) return;
    // One report per dispatch: every teammate-authored message becomes its own
    // leader turn, in arrival order. Coalescing would blur when each message
    // was sent and what the leader was expected to do about each one.
    const reports = first.reports;
    const content = formatReports(reports);
    const queuedIntoActiveRun = !this.isIdle();
    this.active = {
      reports,
      content,
      attempts: first.attempts,
      prepared: queuedIntoActiveRun || this.prepareOnDispatch,
      started: queuedIntoActiveRun,
    };
    const generation = this.generation;
    if (!queuedIntoActiveRun) {
      this.watchdogTimer = setTimeout(() => {
        if (generation !== this.generation || !this.active || this.active.started) return;
        this.failActive(generation, "Pi did not start the automatic teammate follow-up.");
      }, this.agentStartTimeoutMs);
      this.watchdogTimer.unref?.();
    }
    try {
      this.dispatch(reports, content);
    } catch (error) {
      this.failActive(generation, error instanceof Error ? error.message : String(error));
    }
  }

  private failActive(generation: number, message: string): void {
    if (generation !== this.generation || !this.active) return;
    const failed = this.active;
    this.active = undefined;
    this.clearWatchdog();
    failed.attempts++;
    if (failed.attempts >= this.maxAttempts) {
      this.deadLetter.push(...failed.reports);
      this.onFailure(`${message} Maximum retry attempts (${this.maxAttempts}) exhausted; report moved to dead letter.`);
      return;
    }
    this.pending.unshift({ reports: failed.reports, attempts: failed.attempts, retrying: true });
    const delay = Math.min(
      this.retryMaxDelayMs,
      this.retryBaseDelayMs * 2 ** Math.max(0, failed.attempts - 1),
    );
    this.onFailure(`${message} Retrying in ${Math.ceil(delay / 1000)}s.`);
    this.retryTimer = setTimeout(() => {
      this.retryTimer = undefined;
      if (generation === this.generation) this.schedulePump();
    }, delay);
    this.retryTimer.unref?.();
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

export function formatReports(reports: FollowUpReport[]): string {
  return reports
    .map((report) => {
      const { teammate, body, timestamp, origin, harnessEvent } = report;
      const at = timestamp !== undefined && Number.isFinite(timestamp)
        ? ` at="${new Date(timestamp).toISOString()}"`
        : "";
      if (origin === "harness" || harnessEvent) {
        const type = escapeAttribute(harnessEvent?.type ?? "event");
        const subject = escapeAttribute(harnessEvent?.subject ?? "Agent Teams event");
        return `<harness-event type="${type}" subject="${subject}"${at}>\n${body}\n</harness-event>`;
      }
      const name = teammate ?? "teammate";
      return `<agent-message from="${escapeAttribute(name)}"${at}>\n${body}\n</agent-message>`;
    })
    .join("\n\n");
}

function escapeAttribute(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}
