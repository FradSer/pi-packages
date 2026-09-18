import {
  DESK_LINK_PROTOCOL,
  type DeskLinkConfig,
  type DeskLinkRecord,
  type ReportedSession,
  type SessionEvent,
  type SessionStatus,
} from "./types.ts";
import { boundEventText, boundSessionEvent, retainEvents } from "./events.ts";
import { normalizeSessionId } from "./session-identity.ts";
import { type DeskTransport } from "./transport.ts";

export type LinkState = "offline" | "connecting" | "connected";

export interface DeskReporterOptions {
  config: DeskLinkConfig;
  createTransport: (config: DeskLinkConfig) => DeskTransport;
  now?: () => number;
  /** Injected so reconnect scheduling is asserted without waiting. */
  schedule?: (run: () => void, delayMs: number) => (() => void) | void;
  /** Called on every link-state change, so a surface can stop showing a stale one. */
  onChange?: (snapshot: DeskLinkSnapshot) => void;
}

export interface DeskLinkSnapshot {
  link: LinkState;
  machine: string;
  sessions: number;
  events: number;
  attempts: number;
  omittedSessions: number;
  lastError?: string;
}

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;
const MAX_RECORD_BYTES = 65536;
const MAX_EVENTS_RECORD_BYTES = 1024 * 1024;
/** Sessions one machine may report at once. */
export const MAX_SESSIONS_PER_MACHINE = 64;

/**
 * A partial session update. Identity fields are only overwritten when a caller
 * actually provides them, so a rename or a new goal never erases the cwd or
 * start time an earlier update established.
 */
export interface SessionUpdate {
  sessionId: string;
  name?: string;
  cwd?: string;
  workspaceName?: string;
  status?: SessionStatus;
  startedAt?: number;
  latestGoal?: string;
  activity?: string;
}

interface SessionEntry {
  discovered: boolean;
  session: ReportedSession;
  events: SessionEvent[];
  pending: SessionEvent[];
}

/**
 * Reports this machine's Pi sessions to Open DeskOS.
 *
 * History and unsent events each retain only the newest tail within both
 * the event-count and UTF-8 byte budgets, plus one unsent snapshot flag.
 * An outage therefore costs freshness, never an unbounded backlog.
 */
export class DeskReporter {
  readonly #config: DeskLinkConfig;
  readonly #createTransport: (config: DeskLinkConfig) => DeskTransport;
  readonly #now: () => number;
  readonly #schedule: NonNullable<DeskReporterOptions["schedule"]>;
  readonly #onChange: ((snapshot: DeskLinkSnapshot) => void) | undefined;
  readonly #sessions = new Map<string, SessionEntry>();

  #transport: DeskTransport | null = null;
  #link: LinkState = "offline";
  #attempts = 0;
  #sessionsDirty = true;
  #lastError: string | undefined;
  #stopped = false;
  #active = false;
  #generation = 0;
  #cancelReconnect: (() => void) | void = undefined;
  #currentSessionId = "";

  constructor(options: DeskReporterOptions) {
    this.#config = options.config;
    this.#createTransport = options.createTransport;
    this.#now = options.now ?? (() => Date.now());
    this.#onChange = options.onChange;
    this.#schedule = options.schedule ?? ((run, delayMs) => {
      const timer = setTimeout(run, delayMs);
      timer.unref?.();
      return () => clearTimeout(timer);
    });
  }

  start(): void {
    if (this.#stopped || this.#active) return;
    this.#active = true;
    this.#connect();
  }

  /** Close the link politely and stay stopped. */
  stop(): void {
    if (this.#stopped) return;
    this.#stopped = true;
    this.#disconnect();
  }

  /**
   * Close the link but stay usable. Pi emits session_shutdown for a session
   * switch, fork, or resume inside the same process, and that must not end
   * reporting for the session that follows.
   */
  disconnect(): void {
    if (this.#stopped) return;
    this.#disconnect();
  }

  #disconnect(): void {
    this.#active = false;
    this.#generation += 1;
    this.#cancelReconnect?.();
    this.#cancelReconnect = undefined;
    if (this.#link === "connected") this.#send({ v: DESK_LINK_PROTOCOL, type: "bye", machine: this.#config.machine });
    const transport = this.#transport;
    this.#transport = null;
    transport?.close();
    this.#link = "offline";
    this.#notify();
  }

  /** Upsert a session's identity and state. */
  recordSession(update: SessionUpdate): void {
    this.#currentSessionId = update.sessionId;
    const existing = this.#sessions.get(update.sessionId);
    const at = this.#now();
    const previous = existing?.session;
    const session: ReportedSession = {
      sessionId: update.sessionId,
      ...((update.name ?? previous?.name) === undefined ? {} : { name: (update.name ?? previous?.name) as string }),
      cwd: update.cwd ?? previous?.cwd ?? "",
      workspaceName: update.workspaceName ?? previous?.workspaceName ?? "",
      status: update.status ?? previous?.status ?? "running",
      startedAt: update.startedAt ?? previous?.startedAt ?? at,
      updatedAt: at,
      ...((update.latestGoal ?? previous?.latestGoal) === undefined ? {} : { latestGoal: (update.latestGoal ?? previous?.latestGoal) as string }),
      ...((update.activity ?? previous?.activity) === undefined ? {} : { activity: (update.activity ?? previous?.activity) as string }),
    };
    this.#sessions.set(update.sessionId, existing === undefined
      ? { discovered: false, session, events: [], pending: [] }
      : { ...existing, discovered: false, session });
    this.#evictOldestSessions();
    this.#sessionsDirty = true;
    this.#flush();
  }

  /** Replace inventory entries; refresh old observed state, never current state or events. */
  replaceDiscoveredSessions(sessions: readonly ReportedSession[]): void {
    for (const [id, entry] of this.#sessions) {
      if (entry.discovered) this.#sessions.delete(id);
      else if (id !== this.#currentSessionId) entry.session = { ...entry.session, status: "exited" };
    }
    for (const candidate of sessions) {
      const sessionId = normalizeSessionId(candidate.sessionId);
      if (!sessionId) continue;
      const existing = this.#sessions.get(sessionId);
      if (sessionId === this.#currentSessionId || (existing && existing.session.updatedAt > candidate.updatedAt)) continue;
      this.#sessions.set(sessionId, {
        discovered: existing?.discovered ?? true,
        session: { ...candidate, sessionId, discovered: true },
        events: existing?.events ?? [],
        pending: existing?.pending ?? [],
      });
      this.#evictOldestSessions();
    }
    this.#sessionsDirty = true;
    this.#flush();
  }

  /** Only the current session is pinned; history must not crowd out live work. */
  #evictOldestSessions(): void {
    const priority = { exited: 0, settled: 1, running: 2 };
    while (this.#sessions.size > MAX_SESSIONS_PER_MACHINE) {
      let victimId: string | null = null;
      let victimPriority = Number.POSITIVE_INFINITY;
      let victimAt = Number.POSITIVE_INFINITY;
      for (const [id, entry] of this.#sessions) {
        if (id === this.#currentSessionId) continue;
        const rank = priority[entry.session.status];
        const at = entry.session.updatedAt || entry.session.startedAt || 0;
        if (rank < victimPriority || (rank === victimPriority && at < victimAt)) {
          victimPriority = rank;
          victimAt = at;
          victimId = id;
        }
      }
      if (victimId === null) return;
      this.#sessions.delete(victimId);
    }
  }

  /** Rename a session without touching its identity or start time. */
  renameSession(sessionId: string, name: string | undefined): void {
    const entry = this.#sessions.get(sessionId);
    if (entry === undefined) return;
    const renamed: ReportedSession = { ...entry.session, updatedAt: this.#now() };
    if (name === undefined) delete renamed.name;
    else renamed.name = name;
    this.#sessions.set(sessionId, { ...entry, session: renamed });
    this.#sessionsDirty = true;
    this.#flush();
  }

  /**
   * Append Session Events to a session, keeping only the newest bounded set.
   * Text is bounded here as well as at extraction. Only results retain their
   * multiline Markdown; activity and other event kinds remain short summaries.
   */
  recordEvents(sessionId: string, events: readonly SessionEvent[]): void {
    const entry = this.#sessions.get(sessionId);
    if (entry === undefined || events.length === 0) return;
    const bounded = events.map(boundSessionEvent).filter((event): event is SessionEvent => event !== null);
    if (bounded.length === 0) return;
    entry.events = retainEvents([...entry.events, ...bounded]);
    entry.pending = retainEvents([...entry.pending, ...bounded]);
    entry.session = { ...entry.session, activity: boundEventText(bounded[bounded.length - 1]?.text) || entry.session.activity, updatedAt: this.#now() };
    this.#flush();
  }

  markStatus(sessionId: string, status: SessionStatus): void {
    const entry = this.#sessions.get(sessionId);
    if (entry === undefined) return;
    entry.session = { ...entry.session, status, updatedAt: this.#now() };
    this.#sessionsDirty = true;
    this.#flush();
  }

  eventsFor(sessionId: string): readonly SessionEvent[] {
    return this.#sessions.get(sessionId)?.events ?? [];
  }

  snapshot(): DeskLinkSnapshot {
    const record = this.#sessionRecord();
    let events = 0;
    for (const entry of this.#sessions.values()) events += entry.events.length;
    return {
      link: this.#link,
      machine: this.#config.machine,
      sessions: this.#sessions.size,
      events,
      attempts: this.#attempts,
      omittedSessions: this.#sessions.size - record.sessions.length,
      ...(this.#lastError === undefined ? {} : { lastError: this.#lastError }),
    };
  }

  #notify(): void {
    this.#onChange?.(this.snapshot());
  }

  #connect(): void {
    if (!this.#active || this.#stopped || this.#transport !== null) return;
    this.#link = "connecting";
    this.#notify();
    const transport = this.#createTransport(this.#config);
    this.#transport = transport;
    transport.onOpen(() => {
      if (!this.#active || this.#transport !== transport) return;
      this.#lastError = undefined;
      this.#link = "connected";
      this.#notify();
      this.#send({ v: DESK_LINK_PROTOCOL, type: "hello", machine: this.#config.machine, token: this.#config.token });
      // The service discards machine state after its last link closes. Replay
      // the bounded tail, not pending plus history. v1 has no event IDs, so a
      // surviving sibling link can cause duplicate retained events on replay.
      for (const entry of this.#sessions.values()) entry.pending = [...entry.events];
      this.#sessionsDirty = true;
      this.#flush();
    });
    transport.onClose((reason) => {
      if (!this.#active || this.#transport !== transport) return;
      this.#link = "offline";
      this.#lastError = reason;
      this.#notify();
      if (this.#transport === transport) this.#transport = null;
      this.#scheduleReconnect();
    });
    transport.onRecord((record) => {
      if (!this.#active || this.#transport !== transport) return;
      // The service's ack is the only proof the link was accepted. Resetting the
      // backoff on a bare TCP connect would make a refused token retry forever.
      if (typeof record === "object" && record !== null && (record as { type?: unknown }).type === "ack") {
        this.#attempts = 0;
      }
      // v1 is report-only. A future `prompt` record is the reserved control hook
      // and is deliberately not handled here.
    });
  }

  #scheduleReconnect(): void {
    if (this.#stopped || !this.#active) return;
    const generation = this.#generation;
    const delayMs = Math.min(RECONNECT_BASE_MS * 2 ** this.#attempts, RECONNECT_MAX_MS);
    this.#attempts += 1;
    this.#cancelReconnect = this.#schedule(() => {
      if (generation !== this.#generation) return;
      this.#cancelReconnect = undefined;
      this.#connect();
    }, delayMs);
  }

  #sessionRecord(): Extract<DeskLinkRecord, { type: "sessions" }> {
    const record: Extract<DeskLinkRecord, { type: "sessions" }> = {
      v: DESK_LINK_PROTOCOL,
      type: "sessions",
      machine: this.#config.machine,
      sessions: [...this.#sessions.values()].map((entry) => entry.session),
    };
    // One sessions frame replaces a connection's inventory, so it cannot be
    // split into batches. Shorten only discovered descriptions when necessary;
    // identity, metadata timestamps, and observed live data stay untouched.
    for (const max of [100, 50, 25, 12, 6, 0]) {
      if (Buffer.byteLength(JSON.stringify(record)) + 1 <= MAX_RECORD_BYTES) break;
      record.sessions = record.sessions.map((session) => {
        if (!session.discovered) return session;
        const short = (text: string): string => max === 0 ? "" : boundEventText(text, max);
        return {
          ...session,
          ...(session.name === undefined ? {} : { name: short(session.name) }),
          ...(session.latestGoal === undefined ? {} : { latestGoal: short(session.latestGoal) }),
          ...(session.activity === undefined ? {} : { activity: short(session.activity) }),
        };
      });
    }
    // Exact identity may still exceed an older service's frame budget. Omit
    // whole lowest-priority records, not pieces of paths or session IDs.
    if (Buffer.byteLength(JSON.stringify(record)) + 1 > MAX_RECORD_BYTES) {
      const priority = { exited: 0, settled: 1, running: 2 };
      const candidates = record.sessions.filter((session) => session.sessionId !== this.#currentSessionId)
        .sort((a, b) => priority[a.status] - priority[b.status]
          || (a.updatedAt || a.startedAt) - (b.updatedAt || b.startedAt));
      for (const candidate of candidates) {
        record.sessions = record.sessions.filter((session) => session !== candidate);
        if (Buffer.byteLength(JSON.stringify(record)) + 1 <= MAX_RECORD_BYTES) break;
      }
    }
    return record;
  }

  #flush(): void {
    if (this.#link !== "connected") return;
    if (this.#sessionsDirty) {
      this.#sessionsDirty = false;
      this.#send(this.#sessionRecord());
    }
    for (const entry of this.#sessions.values()) {
      if (entry.pending.length === 0) continue;
      const events = entry.pending;
      entry.pending = [];
      this.#sendEventBatches(entry.session.sessionId, events);
    }
  }

  /** Unlike replacing sessions frames, append-only events may split between events. */
  #sendEventBatches(sessionId: string, events: readonly SessionEvent[]): void {
    const record: Extract<DeskLinkRecord, { type: "events" }> = {
      v: DESK_LINK_PROTOCOL,
      type: "events",
      machine: this.#config.machine,
      sessionId,
      events: [],
    };
    // JSON escapes can expand one byte to six. Count encoded bytes plus LF,
    // not the retained-body budget, and include the exact identity envelope.
    const overhead = Buffer.byteLength(JSON.stringify(record)) + 1;
    let size = overhead;
    for (const event of events) {
      if (this.#link !== "connected") return;
      const eventBytes = Buffer.byteLength(JSON.stringify(event));
      if (overhead + eventBytes > MAX_EVENTS_RECORD_BYTES) {
        this.#lastError = "event frame exceeds 1 MiB with exact session identity";
        this.#notify();
        continue;
      }
      if (size + eventBytes + (record.events.length ? 1 : 0) > MAX_EVENTS_RECORD_BYTES) {
        this.#send({ ...record, events: record.events });
        record.events = [];
        size = overhead;
      }
      size += eventBytes + (record.events.length ? 1 : 0);
      record.events.push(event);
    }
    if (record.events.length > 0 && this.#link === "connected") this.#send(record);
  }

  #send(record: DeskLinkRecord): void {
    this.#transport?.send(record);
  }
}
