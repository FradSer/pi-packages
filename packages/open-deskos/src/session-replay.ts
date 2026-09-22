import type { SessionEvent } from "./types.ts";

/**
 * Replays one current session's durable tail before its later live events. The
 * session_start handler awaits start(), so message_end cannot interleave with a
 * snapshot. A numeric generation still rejects A -> B -> A stale reads.
 */
export class CurrentSessionReplay {
  #generation = 0;
  #sessionId = "";
  readonly #read: (sessionFile: string) => Promise<SessionEvent[]>;

  constructor(read: (sessionFile: string) => Promise<SessionEvent[]>) {
    this.#read = read;
  }

  invalidate(): void {
    this.#generation += 1;
    this.#sessionId = "";
  }

  async start(sessionId: string, sessionFile: string | undefined, deliver: (sessionId: string, events: SessionEvent[]) => void): Promise<void> {
    const generation = ++this.#generation;
    this.#sessionId = sessionId;
    if (!sessionFile) return;
    try {
      const events = await this.#read(sessionFile);
      if (this.#generation === generation && this.#sessionId === sessionId && events.length > 0) deliver(sessionId, events);
    } catch {
      // The durable reader is best effort; a later live message can still
      // establish the stream after a transient file failure.
    }
  }

  append(sessionId: string, events: SessionEvent[], deliver: (sessionId: string, events: SessionEvent[]) => void): void {
    if (this.#sessionId === sessionId && events.length > 0) deliver(sessionId, events);
  }
}
