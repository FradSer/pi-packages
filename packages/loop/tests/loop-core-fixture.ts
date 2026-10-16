/**
 * Core harness for the deterministic /loop surfaces.
 *
 * One scenario per line of JSON. Pytest asserts the values, so a rule that
 * changes without a changed expectation fails here.
 */
import { isRunCountSegment, messageCandidates, stripSchedulePhrase } from "../src/candidates.ts";
import { formatDuration, MAX_INTERVAL_MS, MIN_INTERVAL_MS, parseDuration } from "../src/duration.ts";
import { parseParameterized } from "../src/params.ts";
import { LoopRunner } from "../src/scheduler.ts";
import { segmentRequest } from "../src/segments.ts";
import { expandTemplate, templateClock, TemplateError, unknownPlaceholder } from "../src/template.ts";
import type { TimerApi, TimerHandle } from "../src/types.ts";

/** A virtual clock: no scenario depends on real time. */
function manualClock() {
  let nextId = 1;
  let now = 0;
  const scheduled = new Map<number, { at: number; callback: () => void }>();
  const timers: TimerApi = {
    set(callback: () => void, ms: number): TimerHandle {
      const id = nextId;
      nextId += 1;
      scheduled.set(id, { at: now + ms, callback });
      return { id };
    },
    clear(handle: TimerHandle): void {
      scheduled.delete(handle.id);
    },
  };
  return {
    timers,
    advance(ms: number): void {
      const target = now + ms;
      for (;;) {
        const due = [...scheduled.entries()]
          .filter((entry) => entry[1].at <= target)
          .sort((a, b) => a[1].at - b[1].at || a[0] - b[0])[0];
        if (due === undefined) break;
        scheduled.delete(due[0]);
        now = due[1].at;
        due[1].callback();
      }
      now = target;
    },
    pending(): number {
      return scheduled.size;
    },
  };
}

function captureThrown(call: () => unknown): unknown {
  try {
    return { threw: false, value: call() };
  } catch (error) {
    return {
      threw: true,
      name: error instanceof Error ? error.name : typeof error,
      message: error instanceof Error ? error.message : String(error),
    };
  }
}

function tuplePair(pair: unknown): { input: unknown; expected: unknown; actual: unknown } {
  const values = pair as [unknown, unknown];
  return { input: values[0], expected: values[1], actual: parseDuration(String(values[0])) };
}

const scenarios: Record<string, () => unknown> = {
  duration() {
    const parsed = [["30s", 30000], ["5m", 300000], ["1h", 3600000], ["2d", null], ["90", 90000], ["1h30m", 5400000], ["1m 30s", 90000], ["5", 5000], ["500ms", null], ["0s", null], ["24h", 86400000], ["25h", null], ["banana", null], ["", null], ["1x", null], [" 5m ", 300000]].map(tuplePair);
    const formatted = [[90000, "1m30s"], [300000, "5m"], [5400000, "1h30m"], [86400000, "1d"], [1000, "1s"], [500, "500ms"], [30000, "30s"]].map((pair) => {
      const values = pair as [number, string];
      return { input: values[0], expected: values[1], actual: formatDuration(values[0]) };
    });
    return { parsed, formatted, min: MIN_INTERVAL_MS, max: MAX_INTERVAL_MS };
  },

  template() {
    const clock = templateClock(new Date(2026, 0, 2, 3, 4, 5));
    return {
      clock,
      bounded: expandTemplate("status {{index}} of {{total}}", { index: 2, total: 2, time: clock.time, date: clock.date }),
      unbounded: expandTemplate("{{index}}/{{total}} {{remaining}}", { index: 3, time: clock.time, date: clock.date }),
      remaining: expandTemplate("{{remaining}}", { index: 1, total: 4, time: clock.time, date: clock.date }),
      spaced: expandTemplate("{{ index }}", { index: 7, time: clock.time, date: clock.date }),
      unknown: unknownPlaceholder("a {{bogus}} b"),
      none: unknownPlaceholder("a {{index}} b"),
      // A brace token that is not a known lowercase name is refused too, so a
      // typo is reported instead of reaching the model as literal text.
      unknownCased: unknownPlaceholder("status {{Index}} of {{total}}"),
      unknownNumeric: unknownPlaceholder("{{1}}"),
      unknownSpacedName: unknownPlaceholder("{{ index_2 }}"),
      unknownEmpty: unknownPlaceholder("{{}}"),
      // A brace group that never closes is not a placeholder token.
      unclosed: expandTemplate("compare {{ before", { index: 1, time: clock.time, date: clock.date }),
      threwCased: captureThrown(() => expandTemplate("{{Index}}", { index: 1, time: clock.time, date: clock.date })),
      threw: captureThrown(() => expandTemplate("{{bogus}}", { index: 1, time: clock.time, date: clock.date })),
      thrownClass: TemplateError.name,
    };
  },

  params() {
    const inputs = [
      "--every 5m --times 3 check the build",
      "--every 30s --until \"tests pass\" run the suite",
      "--every=1m --message \"hi there\"",
      "-e 2h -t 2 -m report",
      "--every 5m \"quoted message\"",
      "--every 5m -- everything --weird",
      "--every 5m",
      "--every banana x",
      "--every 5m --times 0 x",
      "--every 5m --times two x",
      "--every 5m --bogus x",
      "--every 5m {{bogus}}",
      "--every 5m {{Index}}",
      "--every 5m {{}}",
      "--every 5m compare {{ before",
      "--every 5m --message a b",
      "--every \"5m",
      "check the build every 5 minutes",
      "keep an eye on the deploy",
    ];
    return { cases: inputs.map((input) => ({ input, result: parseParameterized(input) })) };
  },

  candidates() {
    const stripped = [
      "keep an eye on the deploy every ten minutes",
      "check the deploy every 10 minutes",
      "每5分钟检查部署",
      "每小时汇报一次",
      "check the build",
      "report once a minute",
    ].map((input) => ({ input, stripped: stripSchedulePhrase(input) ?? null }));
    const request = "check the deploy every 10 minutes. stop when it is green";
    const segments = segmentRequest(request);
    // A real-model run chose "3 times" as the stopping condition for count-only
    // requests, so the count's own segment class is pinned here.
    const counts = ["3 times", "five times", "20 x", "10 次", "3 times a day", "3", "times",
                    "check the build", "每5分钟", "twice"].map((input) => ({ input, isCount: isRunCountSegment(input) }));
    const counted = segmentRequest("check the build every 5 minutes, 3 times");
    const countedFirst = segmentRequest("3 times, check the deploy every 5 minutes, stop when green");
    return {
      stripped,
      segments,
      counts,
      counted,
      countedFirst,
      withoutStop: messageCandidates(request, segments[1]),
      withoutAny: messageCandidates("check the build", undefined),
      singleCandidate: messageCandidates("deploy is green", "deploy is green"),
      withoutCount: messageCandidates("check the build every 5 minutes, 3 times", undefined,
                                      counted.filter(isRunCountSegment)),
      withoutCountFirst: messageCandidates("3 times, check the deploy every 5 minutes, stop when green",
                                            "stop when green", countedFirst.filter(isRunCountSegment)),
    };
  },

  scheduler() {
    const limit = manualClock();
    const sent: string[] = [];
    const events: string[] = [];
    const runner = new LoopRunner({
      plan: { message: "tick {{index}}/{{total}}", intervalMs: 1000, maxRuns: 2 },
      timers: limit.timers,
      send: (text) => {
        sent.push(text);
      },
      now: () => new Date(2026, 0, 2, 3, 4, 5),
      onEvent: (event) => events.push(event.type + ":" + (event.type === "stopped" ? event.reason : String(event.index))),
    });
    runner.start();
    const beforeFirst = { sent: [...sent], pending: limit.pending() };
    limit.advance(1000);
    runner.markSettled();
    limit.advance(1000);
    const afterLimit = { sent: [...sent], active: runner.active, injections: runner.injections, pending: limit.pending(), events: [...events] };

    const skip = manualClock();
    const skippedSent: string[] = [];
    const skipRunner = new LoopRunner({
      plan: { message: "go", intervalMs: 1000, maxRuns: 3 },
      timers: skip.timers,
      send: (text) => {
        skippedSent.push(text);
      },
    });
    skipRunner.start();
    skip.advance(1000);
    skip.advance(3000);
    const whileBusy = { sent: [...skippedSent], skipped: skipRunner.skipped, awaitingSettle: skipRunner.awaitingSettle };
    skipRunner.markSettled();
    skip.advance(1000);
    const afterSettle = { sent: [...skippedSent], injections: skipRunner.injections, skipped: skipRunner.skipped };

    const stop = manualClock();
    const stoppedSent: string[] = [];
    const stopRunner = new LoopRunner({
      plan: { message: "go", intervalMs: 1000 },
      timers: stop.timers,
      send: (text) => {
        stoppedSent.push(text);
      },
    });
    stopRunner.start();
    stop.advance(1000);
    stopRunner.stop("user");
    stop.advance(60000);
    const afterStop = { sent: [...stoppedSent], active: stopRunner.active, pending: stop.pending() };

    const restart = captureThrown(() => stopRunner.start());
    const firstStart = captureThrown(() => new LoopRunner({ plan: { message: "{{bogus}}", intervalMs: 1000 }, timers: stop.timers, send: () => {} }));
    return { beforeFirst, afterLimit, whileBusy, afterSettle, afterStop, restart, firstStart };
  },

  delivery() {
    // Pi refuses a delivery by throwing: a captured extension API goes stale
    // after session replacement or reload. The loop must report it and release
    // its timer rather than stay active with nothing pending.
    const clock = manualClock();
    const sent: string[] = [];
    const events: string[] = [];
    let undelivered: string | undefined;
    const runner = new LoopRunner({
      plan: { message: "go", intervalMs: 1000, maxRuns: 3 },
      timers: clock.timers,
      send: (text) => {
        sent.push(text);
        throw new Error("This extension ctx is stale after session replacement or reload.");
      },
      onEvent: (event) => {
        events.push(event.type + ":" + (event.type === "stopped" ? event.reason : String(event.index)));
        if (event.type === "undelivered") undelivered = event.reason;
      },
    });
    runner.start();
    clock.advance(1000);
    clock.advance(5000);
    return {
      events,
      sent,
      undelivered,
      active: runner.active,
      injections: runner.injections,
      pending: clock.pending(),
    };
  },
};

const requested = process.argv.slice(2);
for (const name of requested.length > 0 ? requested : Object.keys(scenarios)) {
  const scenario = scenarios[name];
  if (scenario === undefined) {
    console.log(JSON.stringify({ scenario: name, ok: false, error: "unknown scenario" }));
    continue;
  }
  try {
    console.log(JSON.stringify({ scenario: name, ok: true, value: scenario() }));
  } catch (error) {
    console.log(JSON.stringify({ scenario: name, ok: false, error: error instanceof Error ? error.message : String(error) }));
  }
}
