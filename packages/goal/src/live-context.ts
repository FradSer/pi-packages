/**
 * Prefix-stable injection of live goal state.
 *
 * Pi rebuilds the request from the transcript on every LLM call, so a runtime
 * note appended to it is *not* persisted. That sounds harmless and is not: the
 * note occupies the last position of request N, and in request N+1 the turn
 * that ran in between occupies that same position. The two requests diverge at
 * that index, so the provider's implicit prefix cache stops matching and every
 * request re-reads the whole session.
 *
 * The fix is to make each request a true prefix of the next: re-insert the note
 * that was already sent, verbatim, at the index it was sent from, then append
 * the current one. Request N+1 then begins with exactly request N.
 *
 * When the retained note cannot be re-inserted safely — the history was
 * compacted, the branch moved, the session changed, the anchor no longer
 * exists — this does one full reset instead. A single prefix break is
 * recoverable; a silently shifted or corrupted message list is not.
 */

import type { UserMessage } from "@earendil-works/pi-ai";

/**
 * The label on an injected note.
 *
 * It is not decoration. The note is delivered as a `user` message, and a `user`
 * role is what the model reads as "someone asked for this" — so the framing has
 * to say otherwise in the model's terms rather than rely on the transcript,
 * which never sees the note at all.
 *
 * A custom role would be the tidier answer and is deliberately not used:
 * measured against a live session, pi downgrades a message carrying
 * `role: "custom"` to `role: "user"` before the provider sees it, content
 * intact and role discarded. The role therefore buys nothing at the wire, and
 * the framing is the only thing that can carry the distinction. See
 * packages/goal/AGENTS.md.
 */
export const LIVE_CONTEXT_MARKER = "[pi-goal runtime state — not a message from the user]";

/** States what the block is and what it is not, so the distinction is legible
 * to the model rather than implied by punctuation. */
const LIVE_CONTEXT_PREAMBLE = [
  "The block below is live state reported by the pi-goal extension. It is not a",
  "request from the user and contains no instruction to act on its own. Treat it",
  "as context about a goal that is already running: use it to decide what to do",
  "next, and let the user's own messages decide what the work is.",
].join(" ");

export function liveNote(content: string, timestamp: number): UserMessage {
  return { role: "user", content: `${LIVE_CONTEXT_MARKER}\n${LIVE_CONTEXT_PREAMBLE}\n\n${content}`, timestamp };
}

/** Bounds the work per request and the memory retained per session. Beyond
 * either bound the module resets rather than degrading. */
const MAX_ANCHOR = 4096;
const DIGEST_CHARS = 96;
/**
 * How many already-sent notes stay replayable.
 *
 * Every request emits one note, and every note already sent has to be re-inserted
 * or this request stops being a prefix of the last. So the retained list grows
 * with the session and has to be bounded. Exceeding the bound costs one prefix
 * break, which is the same price the history-rewrite path already pays, and it is
 * paid once rather than every turn.
 */
const MAX_RETAINED = 32;

export interface LiveTail {
  /** Index in the *base* transcript at which the note must be re-inserted. */
  anchor: number;
  content: string;
  /** Digest of the base transcript when the note was emitted, used to prove the
   * prefix the note is anchored to is still the same prefix. */
  digests: string[];
  timestamp: number;
}

export interface ApplyResult {
  messages: UserMessage[];
  /** Whether request N was a true prefix of the one just produced. */
  preserved: boolean;
  reason: "first" | "preserved" | "session-changed" | "history-rewritten" | "anchor-lost" | "too-long";
}

function digest(message: unknown): string {
  const role = (message as { role?: unknown }).role;
  const rest = safeJson(message);
  return `${String(role)}:${rest.slice(0, DIGEST_CHARS)}`;
}

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value) ?? "";
  } catch {
    return String(value);
  }
}

export class LiveContext {
  /** Already-sent notes, oldest first, each with its base-transcript anchor. */
  private tails: LiveTail[] = [];
  private sessionKey: string | undefined;

  /**
   * Produce the messages for one request.
   *
   * `fresh` is the current state to send. The returned array is the request;
   * nothing here is persisted.
   *
   * The anchor is expressed in *base* coordinates — the transcript pi handed us
   * — because that is the only coordinate system the next request shares. A
   * note appended to a base of length N sits at base index N, and that is where
   * it has to be re-inserted next time, however many notes were replayed before
   * it in between.
   */
  apply(sessionKey: string, base: readonly unknown[], fresh: string, timestamp: number): ApplyResult {
    const messages = base as UserMessage[];
    const digests = messages.map(digest);
    const knownSession = this.sessionKey !== undefined;
    const sameSession = this.sessionKey === sessionKey;

    let reason: ApplyResult["reason"] = !knownSession ? "first" : sameSession ? "first" : "session-changed";
    let tails = sameSession ? this.tails : [];
    if (sameSession && tails.length > 0) {
      // Every retained note must land inside the base, and the base prefix each
      // one was anchored to must still be the same prefix.
      if (tails.some((tail) => tail.anchor > MAX_ANCHOR)) {
        reason = "too-long";
        tails = [];
      } else if (tails.some((tail) => digests.length < tail.anchor)) {
        reason = "anchor-lost";
        tails = [];
      } else if (!tails.every((tail) => matches(digests, tail.digests, tail.anchor))) {
        reason = "history-rewritten";
        tails = [];
      } else {
        reason = "preserved";
      }
    }

    // Oldest first, adding the number already inserted. Each note is anchored in
    // base coordinates, and every earlier insertion shifts everything after it
    // by one, so an unshifted anchor would place later notes inside earlier
    // turns instead of at the position they were sent from.
    const out = messages.slice();
    let inserted = 0;
    for (const tail of tails) {
      out.splice(tail.anchor + inserted, 0, liveNote(tail.content, tail.timestamp));
      inserted += 1;
    }
    out.push(liveNote(fresh, timestamp));

    const retained = [...tails, { anchor: messages.length, content: fresh, digests, timestamp }];
    // Overflow clears the whole window rather than dropping the oldest note.
    // A partial drop does not restore stability: the dropped note sits at a fixed
    // position that every later request would then be missing, so the break would
    // repeat every turn forever. An empty window costs one break and the turn
    // after it is stable again.
    this.tails = retained.length > MAX_RETAINED ? [] : retained;
    this.sessionKey = sessionKey;
    return { messages: out, preserved: reason === "preserved" || reason === "first", reason };
  }

  /** Forget every retained note. Called when a session boundary makes any
   * re-insertion meaningless, so the next request starts clean. */
  reset(sessionKey?: string): void {
    this.tails = [];
    this.sessionKey = sessionKey;
  }

  /** How many notes are currently replayable, for tests and diagnostics. */
  get retained(): number {
    return this.tails.length;
  }
}

function matches(current: string[], stored: string[], anchor: number): boolean {
  for (let index = 0; index < anchor; index++) {
    if (current[index] !== stored[index]) return false;
  }
  return true;
}