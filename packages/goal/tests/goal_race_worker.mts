/**
 * One writer in the cross-process race.
 *
 * Run as a real process by goal_store.mts. The revision guard is only worth
 * anything if the write lock actually excludes across processes, so the race
 * has to involve real processes rather than several stores in one event loop —
 * in-process calls cannot interleave inside the synchronous critical section.
 *
 * Usage: node --import tsx goal_race_worker.mts <projectRoot> <goalId> <startAt>
 * Prints one line: `won` or `lost`.
 */

import { GoalStore } from "../src/store.ts";

const [projectRoot, goalId, startAt] = process.argv.slice(2);
// Epoch milliseconds, not a date string. `Date.parse("1759584000000")` is `NaN`,
// and `Date.now() < NaN` is false, so the barrier below never waited and the
// writers overlapped only by accident. An unusable value now stops the worker
// instead of quietly turning the barrier off.
const barrier = Number(startAt);
if (!Number.isFinite(barrier)) throw new Error(`The start barrier must be epoch milliseconds, received ${String(startAt)}.`);

const store = new GoalStore({ projectRoot });
// Read first, so every writer is competing for the same revision. Without the
// lock this is a lost update: all eight would see revision 0 and all eight
// would write revision 1.
store.readGoalFromDisk(goalId);

while (Date.now() < barrier) {
  // Spin to the shared start instant rather than sleeping a fixed amount, so the
  // writers genuinely overlap.
}

/** Widen the critical section.
 *
 * The read and the write inside `apply` are a few microseconds apart, so eight
 * processes started together would rarely overlap by accident and a
 * non-exclusive lock could still appear to work. Busy-waiting inside the
 * mutation makes the window wide enough that exclusion is what decides the
 * outcome. */
function widen(milliseconds: number): void {
  const until = Date.now() + milliseconds;
  while (Date.now() < until) {
    // Intentionally empty: the point is wall-clock time inside the critical section.
  }
}

let outcome: "won" | "lost" = "lost";
try {
  const result = store.apply({
    expectedGoalId: goalId,
    expectedRevision: 0,
    mutate: (goal) => {
      widen(60);
      return { ...goal, pauseReason: `writer ${process.pid}` };
    },
  });
  outcome = result.ok ? "won" : "lost";
} catch {
  outcome = "lost";
}

process.stdout.write(`${outcome}\n`);