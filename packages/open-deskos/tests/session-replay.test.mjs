import assert from "node:assert/strict";
import test from "node:test";
import { CurrentSessionReplay } from "../src/session-replay.ts";

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

const old = { kind: "user", text: "old" };
const live = { kind: "assistant", text: "live" };

const flatten = (batches) => batches.flatMap((batch) => batch.events);

test("an awaited replay delivers history before later live messages without content deduplication", async () => {
  const read = deferred();
  const replay = new CurrentSessionReplay(() => read.promise);
  const delivered = [];
  const start = replay.start("A", "/sessions/A.jsonl", (id, events) => delivered.push({ id, events }));

  // Pi awaits async session_start handlers, so message_end begins only after
  // this durable snapshot has settled.
  read.resolve([old]);
  await start;
  replay.append("A", [old, live], (id, events) => delivered.push({ id, events }));

  assert.deepEqual(flatten(delivered), [old, old, live]);
});

test("a stale replay cannot cross an A to B to A session switch", async () => {
  const reads = [];
  const replay = new CurrentSessionReplay((file) => {
    const next = deferred();
    reads.push({ file, ...next });
    return next.promise;
  });
  const delivered = [];

  const oldStart = replay.start("A", "/sessions/A-old.jsonl", (id, events) => delivered.push({ id, events }));
  replay.invalidate(); // B starts without a durable replay.
  const currentStart = replay.start("A", "/sessions/A-current.jsonl", (id, events) => delivered.push({ id, events }));
  await new Promise((resolve) => setImmediate(resolve));

  reads[0].resolve([old]);
  await oldStart;
  assert.deepEqual(delivered, [], "the old A tail must not revive after B ran");

  reads[1].resolve([live]);
  await currentStart;
  assert.deepEqual(delivered, [{ id: "A", events: [live] }]);
});
