import { createHmac, randomUUID } from "node:crypto";
import { DESK_LINK_CONTROL_PROTOCOL, type ControlTransport } from "./control-transport.ts";
import type { DeskLinkConfig, HistoryPage, HostedPiSession, PositionedSessionEvent } from "./types.ts";

const CONTROL_TIMEOUT_MS = 5000;
const CONTROL_DOMAIN = "open-deskos-control-v2";
const MAX_ATTACH_BUFFER_EVENTS = 2048;
const MAX_ATTACH_BUFFER_BYTES = 1024 * 1024;

interface ConsoleClientOptions {
  config: DeskLinkConfig;
  consoleSessionId: string;
  createTransport: (config: DeskLinkConfig) => ControlTransport;
  timeoutMs?: number;
}

interface AttachOptions {
  sessionId: string;
  /** Last physical session-log position applied, or undefined for a fresh attach. */
  position?: number;
  onEvent?: (entry: PositionedSessionEvent) => void;
  onState?: (state: { state?: string; lifecycle?: string; activity?: string; turnOutcome?: string; response?: string }) => void;
  onTerminal?: (record: { outcome?: string; response?: string }) => void;
  onPosition?: (position: number) => void;
}

interface PendingRequest {
  resolve(record: Record<string, unknown>): void;
  reject(error: Error): void;
  timer: ReturnType<typeof setTimeout>;
  mutationId?: string;
  sessionId?: string;
  project?: string;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : null;
}

function asPosition(value: unknown): number | null {
  return Number.isSafeInteger(value) && Number(value) >= 0 ? Number(value) : null;
}

function reasonFrom(record: Record<string, unknown>, fallback = "control request failed"): string {
  return typeof record.reason === "string" && record.reason.length > 0 ? record.reason : fallback;
}

function versionError(record: Record<string, unknown>): Error {
  const received = String(record.received ?? record.v ?? "unknown");
  const accepted = Array.isArray(record.accepted) ? record.accepted.join(", ") : String(DESK_LINK_CONTROL_PROTOCOL);
  return new Error(`Desk Link control protocol version ${received} refused; accepted ${accepted}`);
}

function unwrapReply(record: Record<string, unknown>): Record<string, unknown> {
  const result = asRecord(record.result);
  return result ? { ...result, requestId: record.requestId } : record;
}

export function controlTranscript(machine: string, sessionId: string, nonce: string): string {
  return `${CONTROL_DOMAIN}\n${DESK_LINK_CONTROL_PROTOCOL}\n${nonce}\n${machine}\n${sessionId}`;
}

export function createControlProof(controlCredential: string, machine: string, sessionId: string, nonce: string): string {
  return createHmac("sha256", controlCredential).update(controlTranscript(machine, sessionId, nonce), "utf8").digest("hex");
}

export class ControlRequestError extends Error {
  readonly requestId?: string;
  readonly mutationId?: string;
  readonly sessionId?: string;
  readonly project?: string;

  constructor(message: string, ids: { requestId?: string; mutationId?: string; sessionId?: string; project?: string } = {}) {
    const reconciliation = [ids.mutationId && `mutationId ${ids.mutationId}`, ids.sessionId && `sessionId ${ids.sessionId}`, ids.project && `project ${ids.project}`].filter(Boolean).join(", ");
    super(reconciliation ? `${message} (${reconciliation})` : message);
    this.name = "ControlRequestError";
    this.requestId = ids.requestId;
    this.mutationId = ids.mutationId;
    this.sessionId = ids.sessionId;
    this.project = ids.project;
  }
}

class ControlConnection {
  readonly #options: ConsoleClientOptions;
  readonly #transport: ControlTransport;
  readonly #pending = new Map<string, PendingRequest>();
  readonly #onUnsolicited: (record: Record<string, unknown>) => void;
  #ready: Promise<void>;
  #readyResolve!: () => void;
  #readyReject!: (error: Error) => void;
  #closed = false;
  #transportClosed = false;

  constructor(options: ConsoleClientOptions, onUnsolicited: (record: Record<string, unknown>) => void = () => {}) {
    this.#options = options;
    this.#onUnsolicited = onUnsolicited;
    this.#ready = new Promise<void>((resolve, reject) => {
      this.#readyResolve = resolve;
      this.#readyReject = reject;
    });
    this.#transport = options.createTransport(options.config);
    const readyTimer = setTimeout(() => this.#fail(new Error("control handshake timed out"), true), options.timeoutMs ?? CONTROL_TIMEOUT_MS);
    readyTimer.unref?.();
    this.#ready.then(() => clearTimeout(readyTimer), () => clearTimeout(readyTimer));
    this.#transport.onOpen(() => this.#transport.send({
      v: DESK_LINK_CONTROL_PROTOCOL,
      type: "control-hello",
      token: options.config.token,
      machine: options.config.machine,
      sessionId: options.consoleSessionId,
    }));
    this.#transport.onRecord((value) => this.#receive(value));
    this.#transport.onClose((reason) => this.#fail(new Error(reason), false));
  }

  async request(type: string, fields: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    await this.#ready;
    if (this.#closed) throw new Error("control link closed");
    const requestId = randomUUID();
    const mutationId = typeof fields.mutationId === "string" ? fields.mutationId : undefined;
    const sessionId = typeof fields.sessionId === "string" ? fields.sessionId : undefined;
    const project = typeof fields.project === "string" ? fields.project : undefined;
    const response = new Promise<Record<string, unknown>>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.#pending.delete(requestId);
        reject(new ControlRequestError(`control request timed out: ${type}`, { requestId, mutationId, sessionId, project }));
      }, this.#options.timeoutMs ?? CONTROL_TIMEOUT_MS);
      timer.unref?.();
      this.#pending.set(requestId, { resolve, reject, timer, mutationId, sessionId, project });
    });
    this.#transport.send({ v: DESK_LINK_CONTROL_PROTOCOL, type, requestId, ...fields });
    return response;
  }

  close(): void {
    this.#fail(new Error("control link closed"), true);
  }

  #receive(value: unknown): void {
    const record = asRecord(value);
    if (!record) return;
    if (record.type === "version-mismatch" || (record.v !== undefined && record.v !== DESK_LINK_CONTROL_PROTOCOL)) {
      this.#fail(versionError(record), true);
      return;
    }
    if (record.type === "challenge") {
      const nonce = typeof record.nonce === "string" ? record.nonce : "";
      const algorithm = record.algorithm;
      const credential = this.#options.config.controlToken ?? "";
      if (!nonce || (algorithm !== undefined && algorithm !== "hmac-sha256")) {
        this.#fail(new Error("invalid Desk Link control challenge"), true);
        return;
      }
      if (!credential) {
        this.#fail(new Error("Control Credential is not configured"), true);
        return;
      }
      this.#transport.send({
        v: DESK_LINK_CONTROL_PROTOCOL,
        type: "control-proof",
        proof: createControlProof(credential, this.#options.config.machine, this.#options.consoleSessionId, nonce),
      });
      return;
    }
    if (record.type === "control-ack") {
      this.#readyResolve();
      return;
    }
    const requestId = typeof record.requestId === "string" ? record.requestId : "";
    if (requestId) {
      const pending = this.#pending.get(requestId);
      if (!pending) {
        this.#onUnsolicited(record);
        return;
      }
      this.#pending.delete(requestId);
      clearTimeout(pending.timer);
      if (record.type === "error") pending.reject(new ControlRequestError(reasonFrom(record), { requestId, mutationId: pending.mutationId, sessionId: pending.sessionId, project: pending.project }));
      else pending.resolve(unwrapReply(record));
      return;
    }
    if (record.type === "error") {
      this.#fail(new Error(reasonFrom(record, "control authentication failed")), true);
      return;
    }
    this.#onUnsolicited(record);
  }

  #fail(error: Error, closeTransport: boolean): void {
    if (!this.#closed) {
      this.#closed = true;
      this.#readyReject(error);
      for (const [requestId, pending] of this.#pending) {
        clearTimeout(pending.timer);
        pending.reject(new ControlRequestError(error.message, { requestId, mutationId: pending.mutationId, sessionId: pending.sessionId, project: pending.project }));
      }
      this.#pending.clear();
    }
    if (closeTransport && !this.#transportClosed) {
      this.#transportClosed = true;
      this.#transport.close();
    }
  }
}

export interface ConsoleAttachment {
  sessionId: string;
  attachmentId: string;
  prompt(prompt: string, options?: { mutationId?: string }): Promise<void>;
  cancel(options?: { mutationId?: string; turnId?: string; precondition?: string }): Promise<void>;
  end(options?: { mutationId?: string }): Promise<void>;
  history(position?: number): Promise<HistoryPage>;
  lastApplied(): number;
  error(): string | undefined;
  close(): void;
}

export class DeskConsoleClient {
  readonly #options: ConsoleClientOptions;
  #attachment: ConsoleAttachment | null = null;

  constructor(options: ConsoleClientOptions) {
    this.#options = options;
  }

  async list(): Promise<{ sessions: HostedPiSession[] }> {
    const reply = await this.#oneShot("list");
    return { sessions: Array.isArray(reply.sessions) ? reply.sessions as HostedPiSession[] : [] };
  }

  async launch(input: { project: string; prompt: string; sessionId?: string; mutationId?: string }): Promise<Record<string, unknown>> {
    const mutationId = input.mutationId ?? randomUUID();
    const sessionId = input.sessionId ?? randomUUID();
    return this.#oneShot("launch", { ...input, sessionId, mutationId });
  }

  async history(input: { sessionId: string; position?: number; limit?: number; through?: number }): Promise<HistoryPage> {
    const reply = await this.#oneShot("history", {
      sessionId: input.sessionId,
      after: input.position ?? null,
      ...(input.limit === undefined ? {} : { limit: input.limit }),
      ...(input.through === undefined ? {} : { through: input.through }),
    });
    return this.#historyPage(reply, input.sessionId);
  }

  async attach(options: AttachOptions): Promise<ConsoleAttachment> {
    this.#attachment?.close();
    const attachmentId = randomUUID();
    let lastApplied = options.position ?? 0;
    let streamError: string | undefined;
    let caughtUp = false;
    let acknowledged = false;
    let pendingBoundary: number | null = null;
    let queuedBytes = 0;
    const queued: PositionedSessionEvent[] = [];
    const apply = (entry: PositionedSessionEvent): void => {
      if (entry.position === lastApplied) return;
      if (entry.position < lastApplied) {
        streamError = `Hosted Pi position regression: applied ${lastApplied}, received ${entry.position}`;
        return;
      }
      lastApplied = entry.position;
      options.onPosition?.(lastApplied);
      options.onEvent?.(entry);
    };
    const drainQueued = (): void => {
      if (!acknowledged) return;
      for (const entry of queued.sort((a, b) => a.position - b.position)) apply(entry);
      queued.length = 0;
      queuedBytes = 0;
    };
    const connection = new ControlConnection(this.#options, (record) => {
      if (record.sessionId !== options.sessionId || record.attachmentId !== attachmentId) return;
      if (record.type === "event") {
        const position = asPosition(record.position);
        const values = Array.isArray(record.events) ? record.events : record.event === undefined ? [] : [record.event];
        const events = values.map(asRecord).filter((event): event is Record<string, unknown> => event !== null);
        if (position === null || events.length === 0) return;
        const entry: PositionedSessionEvent = { position, events: events as unknown as PositionedSessionEvent["events"] };
        if (caughtUp && acknowledged) apply(entry);
        else {
          const entryBytes = Buffer.byteLength(JSON.stringify(entry));
          if (queued.length >= MAX_ATTACH_BUFFER_EVENTS || queuedBytes + entryBytes > MAX_ATTACH_BUFFER_BYTES) {
            streamError = "Hosted Pi catch-up exceeded the 2,048-event / 1-MiB Console buffer";
            connection.close();
            return;
          }
          queued.push(entry);
          queuedBytes += entryBytes;
        }
      } else if (record.type === "caught_up") {
        drainQueued();
        const boundary = asPosition(record.boundary);
        if (boundary !== null && boundary > lastApplied) pendingBoundary = boundary;
        if (acknowledged && pendingBoundary !== null) {
          lastApplied = pendingBoundary;
          options.onPosition?.(lastApplied);
          pendingBoundary = null;
        }
        caughtUp = true;
      } else if (record.type === "state") {
        options.onState?.({
          ...(typeof record.state === "string" ? { state: record.state } : {}),
          ...(typeof record.lifecycle === "string" ? { lifecycle: record.lifecycle } : {}),
          ...(typeof record.activity === "string" ? { activity: record.activity } : {}),
          ...(typeof record.turnOutcome === "string" ? { turnOutcome: record.turnOutcome } : {}),
          ...(typeof record.response === "string" ? { response: record.response } : {}),
        });
      } else if (record.type === "terminal") {
        options.onTerminal?.({
          ...(typeof record.outcome === "string" ? { outcome: record.outcome } : {}),
          ...(typeof record.response === "string" ? { response: record.response } : {}),
        });
      }
    });
    const attached = await connection.request("attach", {
      sessionId: options.sessionId,
      attachmentId,
      after: options.position ?? null,
    });
    acknowledged = true;
    drainQueued();
    const boundary = asPosition(attached.boundary);
    if (boundary !== null && options.position === undefined && boundary > lastApplied) {
      lastApplied = boundary;
      options.onPosition?.(lastApplied);
    }
    if (attached.caughtUp === true || attached.type === "caught_up") {
      drainQueued();
      if (boundary !== null && boundary > lastApplied) pendingBoundary = boundary;
      caughtUp = true;
    }
    if (pendingBoundary !== null) {
      if (pendingBoundary > lastApplied) {
        lastApplied = pendingBoundary;
        options.onPosition?.(lastApplied);
      }
      pendingBoundary = null;
    }
    const mutate = async (type: "prompt" | "cancel" | "end", fields: Record<string, unknown> = {}): Promise<void> => {
      const mutationId = typeof fields.mutationId === "string" ? fields.mutationId : randomUUID();
      await connection.request(type, { sessionId: options.sessionId, attachmentId, ...fields, mutationId });
    };
    const attachment: ConsoleAttachment = {
      sessionId: options.sessionId,
      attachmentId,
      prompt: async (prompt, promptOptions = {}) => mutate("prompt", { prompt, ...promptOptions }),
      cancel: async (cancelOptions = {}) => mutate("cancel", cancelOptions),
      end: async (endOptions = {}) => mutate("end", endOptions),
      history: async (position = 0) => this.#historyPage(await connection.request("history", { sessionId: options.sessionId, after: position }), options.sessionId),
      lastApplied: () => lastApplied,
      error: () => streamError,
      close: () => {
        connection.close();
        if (this.#attachment === attachment) this.#attachment = null;
      },
    };
    this.#attachment = attachment;
    return attachment;
  }

  closeAttachment(): void {
    this.#attachment?.close();
  }

  async #oneShot(type: string, fields: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    const connection = new ControlConnection(this.#options);
    try {
      return await connection.request(type, fields);
    } finally {
      connection.close();
    }
  }

  #historyPage(reply: Record<string, unknown>, sessionId: string): HistoryPage {
    const entries = Array.isArray(reply.entries)
      ? reply.entries.map((value) => {
        const record = asRecord(value);
        const position = asPosition(record?.position);
        const values = Array.isArray(record?.events) ? record.events : record?.event === undefined ? [] : [record.event];
        const events = values.map(asRecord).filter((event): event is Record<string, unknown> => event !== null);
        return position === null || events.length === 0 ? null : { position, events: events as unknown as PositionedSessionEvent["events"] };
      }).filter((entry): entry is PositionedSessionEvent => entry !== null)
      : [];
    return {
      sessionId: typeof reply.sessionId === "string" ? reply.sessionId : sessionId,
      entries,
      nextPosition: asPosition(reply.nextPosition ?? reply.next),
      ...(asPosition(reply.boundary) === null ? {} : { boundary: asPosition(reply.boundary)! }),
      ...(reply.oversized === true ? { oversized: true } : {}),
    };
  }
}
