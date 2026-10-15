/**
 * The repeating injection engine.
 *
 * Time and delivery are injected, so every rule here is testable without real
 * time and without a session. One rule matters most: a tick whose previous
 * injection has not settled is skipped, so a slow turn can never turn a loop
 * into a queue of pending prompts.
 */

import { formatDuration } from "./duration.ts";
import { expandTemplate, templateClock, unknownPlaceholder } from "./template.ts";
import type { LoopPlan, TimerApi, TimerHandle } from "./types.ts";

export type LoopStopReason = "user" | "limit" | "condition" | "shutdown" | "delivery";

export type LoopEvent =
  | { type: "injected"; index: number; text: string }
  | { type: "skipped"; index: number; reason: "busy" }
  /** An attempt the host refused outright, named by the stop it causes. */
  | { type: "undelivered"; index: number; reason: string }
  | { type: "stopped"; reason: LoopStopReason; injections: number; skipped: number };

export interface LoopRunnerOptions {
  plan: LoopPlan;
  timers: TimerApi;
  /**
   * Deliver the text into the session as a user turn. Pi's `sendUserMessage`
   * returns void and reports a turn that fails after acceptance on its own error
   * channel, so the refusal this catches is the synchronous throw the host raises
   * for a captured extension API that has gone stale.
   */
  send: (text: string) => void;
  now?: () => Date;
  onEvent?: (event: LoopEvent) => void;
}

/** One active repeating injection. Create it, start it, then stop it once. */
export class LoopRunner {
  readonly plan: LoopPlan;
  private readonly timers: TimerApi;
  private readonly send: (text: string) => void;
  private readonly now: () => Date;
  private readonly onEvent: ((event: LoopEvent) => void) | undefined;
  private handle: TimerHandle | undefined;
  private running = false;
  private busy = false;
  private finished = false;
  private count = 0;
  private skipCount = 0;

  constructor(options: LoopRunnerOptions) {
    const unknown = unknownPlaceholder(options.plan.message);
    if (unknown !== undefined) throw new Error("Unknown placeholder: " + unknown);
    this.plan = options.plan;
    this.timers = options.timers;
    this.send = options.send;
    this.now = options.now ?? (() => new Date());
    this.onEvent = options.onEvent;
  }

  /** Injections delivered so far. */
  get injections(): number {
    return this.count;
  }

  /** Ticks skipped because the previous injection had not settled. */
  get skipped(): number {
    return this.skipCount;
  }

  /** True while a timer is pending. */
  get active(): boolean {
    return this.running;
  }

  /** True while the last injection has not settled. */
  get awaitingSettle(): boolean {
    return this.busy;
  }

  get intervalLabel(): string {
    return formatDuration(this.plan.intervalMs);
  }

  /** Schedule the first injection one interval from now. */
  start(): void {
    if (this.finished) throw new Error("A stopped loop cannot restart; start a new loop.");
    if (this.running) throw new Error("The loop is already running.");
    this.running = true;
    this.schedule();
  }

  /** Release the timer. Later calls do nothing. */
  stop(reason: LoopStopReason): void {
    if (!this.running) return;
    this.running = false;
    this.finished = true;
    this.clear();
    this.emit({ type: "stopped", reason, injections: this.count, skipped: this.skipCount });
  }

  /** Mark the last injection as settled, which allows the next tick to deliver. */
  markSettled(): void {
    this.busy = false;
  }

  private emit(event: LoopEvent): void {
    this.onEvent?.(event);
  }

  private clear(): void {
    if (this.handle === undefined) return;
    this.timers.clear(this.handle);
    this.handle = undefined;
  }

  private schedule(): void {
    this.handle = this.timers.set(() => this.tick(), this.plan.intervalMs);
  }

  private tick(): void {
    this.handle = undefined;
    if (!this.running) return;
    if (this.busy) {
      this.skipCount += 1;
      this.emit({ type: "skipped", index: this.count + 1, reason: "busy" });
      this.schedule();
      return;
    }
    const index = this.count + 1;
    const clock = templateClock(this.now());
    const text = expandTemplate(this.plan.message, {
      index,
      ...(this.plan.maxRuns !== undefined ? { total: this.plan.maxRuns } : {}),
      time: clock.time,
      date: clock.date,
    });
    this.busy = true;
    this.count = index;
    try {
      this.send(text);
    } catch (error) {
      this.failDelivery(index, error);
      return;
    }
    this.emit({ type: "injected", index, text });
    if (this.plan.maxRuns !== undefined && this.count >= this.plan.maxRuns) {
      this.stop("limit");
      return;
    }
    this.schedule();
  }

  /**
   * Report a delivery the host refused, and end the loop: every later repetition
   * would be refused the same way, and the status row would keep claiming a loop
   * that is doing nothing.
   */
  private failDelivery(index: number, error: unknown): void {
    this.emit({ type: "undelivered", index, reason: messageOf(error) });
    this.stop("delivery");
  }
}

/** A delivery failure's own text, for a report a reader can act on. */
function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** The real timer surface. A pending tick never keeps the process alive. */
export function nodeTimers(): TimerApi {
  let nextId = 1;
  const handles = new Map<number, ReturnType<typeof setTimeout>>();
  return {
    set(callback: () => void, ms: number): TimerHandle {
      const id = nextId;
      nextId += 1;
      const timer = setTimeout(() => {
        handles.delete(id);
        callback();
      }, ms);
      timer.unref?.();
      handles.set(id, timer);
      return { id };
    },
    clear(handle: TimerHandle): void {
      const timer = handles.get(handle.id);
      if (timer === undefined) return;
      clearTimeout(timer);
      handles.delete(handle.id);
    },
  };
}
