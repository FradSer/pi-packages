/**
 * Prefix-stability contracts for the injected goal state.
 *
 * The property under test is a statement about two consecutive requests: the
 * first must be a true prefix of the second. That is the only thing a provider's
 * implicit prefix cache can use, and it is exactly what naive tail injection
 * breaks. Each scenario therefore builds two requests and compares them, rather
 * than inspecting the injection in isolation.
 */

import assert from "node:assert/strict";
import { LIVE_CONTEXT_MARKER, LiveContext } from "../src/live-context.ts";
import type { UserMessage } from "@earendil-works/pi-ai";

const results: string[] = [];

/** Async-capable: an assertion failure inside an un-awaited async body becomes an
 *  unhandled rejection and the scenario is silently recorded as passing. */
async function scenario(name: string, body: () => Promise<void> | void): Promise<void> {
  try {
    await body();
    results.push(`ok ${name}`);
  } catch (error) {
    results.push(`FAIL ${name}: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}

let seq = 0;
function user(text: string): UserMessage {
  seq += 1;
  return { role: "user", content: text, timestamp: seq };
}
function assistant(text: string): UserMessage {
  seq += 1;
  return { role: "assistant", content: [{ type: "text", text }], timestamp: seq } as unknown as UserMessage;
}

/** Whether `prefix` is literally the first messages of `full`. */
function isPrefixOf(prefix: unknown[], full: unknown[]): boolean {
  if (prefix.length > full.length) return false;
  return prefix.every((message, index) => JSON.stringify(message) === JSON.stringify(full[index]));
}

await scenario("the second request begins with the first one exactly", () => {
  const live = new LiveContext();
  const history = [user("start the goal")];
  const first = live.apply("s1", history, "GOAL STATE v1", 1);

  // The turn that ran in between is now part of the transcript.
  const grown = [...history, assistant("working"), user("keep going")];
  const second = live.apply("s1", grown, "GOAL STATE v2", 2);

  assert.ok(
    isPrefixOf(first.messages, second.messages),
    "the previous request must be a true prefix of this one",
  );
  assert.equal(second.reason, "preserved");
  assert.equal(second.preserved, true);
});

await scenario("re-inserted state is the state that was actually sent, not the current one", () => {
  const live = new LiveContext();
  const history = [user("go")];
  const first = live.apply("s1", history, "STATE v1", 1);
  const second = live.apply("s1", [...history, assistant("ok")], "STATE v2", 2);
  // Two notes appear: the one this session already read, and the current one.
  const contents = second.messages.map((message) => String(message.content));
  assert.equal(contents.filter((content) => content.includes("STATE v1")).length, 1);
  assert.equal(contents.filter((content) => content.includes("STATE v2")).length, 1);
  assert.ok(contents.indexOf(contents.find((c) => c.includes("STATE v1"))!) < contents.findIndex((c) => c.includes("STATE v2")));
  assert.ok(first.messages.length < second.messages.length);
});

await scenario("consecutive turns stay prefix-stable until the retained window fills", () => {
  const live = new LiveContext();
  let history: UserMessage[] = [user("go")];
  let previous = live.apply("s1", history, "STATE 0", 0);
  // The window holds 32 notes. Every turn inside it must be prefix-stable: no
  // silent per-turn cache break is acceptable, because that is the failure this
  // module exists to prevent.
  for (let turn = 1; turn <= 32; turn++) {
    history = [...history, assistant(`turn ${turn}`), user(`more ${turn}`)];
    const next = live.apply("s1", history, `STATE ${turn}`, turn);
    assert.ok(isPrefixOf(previous.messages, next.messages), `turn ${turn} broke the prefix: ${next.reason}`);
    previous = next;
  }
});

await scenario("overflowing the window costs one break and then stability resumes", () => {
  const live = new LiveContext();
  let history: UserMessage[] = [user("go")];
  let previous = live.apply("s1", history, "STATE 0", 0);
  const breaks: number[] = [];
  for (let turn = 1; turn <= 80; turn++) {
    history = [...history, assistant(`turn ${turn}`), user(`more ${turn}`)];
    const next = live.apply("s1", history, `STATE ${turn}`, turn);
    if (!isPrefixOf(previous.messages, next.messages)) breaks.push(turn);
    previous = next;
  }
  // Bounded retention means the window eventually fills and has to be dropped.
  // That is a documented cost, not a defect. It must happen once per window
  // rather than every turn: 80 turns with a 32-note window is two windows.
  assert.ok(breaks.length <= 2, `expected at most two deliberate breaks, got ${breaks.length} at turns ${breaks.join(",")}`);
  for (const turn of breaks) {
    assert.ok(turn > 32, `break at turn ${turn} came before the window could fill`);
  }
  // And the break must be recovered from immediately, not left to compound.
  const dense = breaks.filter((turn, index) => index > 0 && turn - breaks[index - 1]! <= 1);
  assert.equal(dense.length, 0, `breaks must not be consecutive: ${breaks.join(",")}`);
});

await scenario("replayed notes are bounded rather than accumulating without limit", () => {
  const live = new LiveContext();
  let history: UserMessage[] = [user("go")];
  for (let turn = 0; turn < 200; turn++) {
    history = [...history, assistant(`turn ${turn}`), user(`more ${turn}`)];
    live.apply("s1", history, `STATE ${turn}`, turn);
    assert.ok(live.retained <= 32, `retained ${live.retained} notes at turn ${turn}`);
    const last = live.apply("s1", history, `STATE ${turn}`, turn);
    // Wire overhead is the history plus the retained window plus this one.
    assert.ok(last.messages.length <= history.length + 33, `request ${turn} carried ${last.messages.length} messages`);
  }
});

await scenario("every note already sent is replayed, not just the newest", () => {
  const live = new LiveContext();
  let history: UserMessage[] = [user("go")];
  let previous = live.apply("s1", history, "STATE 0", 0);
  for (let turn = 1; turn <= 5; turn++) {
    history = [...history, assistant(`a${turn}`), user(`u${turn}`)];
    const next = live.apply("s1", history, `STATE ${turn}`, turn);
    for (let earlier = 0; earlier <= turn; earlier++) {
      const found = next.messages.some((message) => String(message.content).includes(`STATE ${earlier}`));
      assert.ok(found, `STATE ${earlier} vanished at turn ${turn}`);
    }
    assert.ok(isPrefixOf(previous.messages, next.messages), `turn ${turn} broke the prefix`);
    previous = next;
  }
});

await scenario("identical state across requests appends nothing extra", () => {
  const live = new LiveContext();
  const history = [user("go")];
  live.apply("s1", history, "STATE", 1);
  const second = live.apply("s1", [...history, assistant("ok")], "STATE", 2);
  const notes = second.messages.filter((message) => String(message.content).includes(LIVE_CONTEXT_MARKER));
  // The retained note plus the current one, both identical: no information is
  // added, which is the steady state an idle goal sits in.
  assert.equal(notes.length, 2);
  assert.equal(String(notes[0]?.content), String(notes[1]?.content));
});

await scenario("a rewritten history resets instead of re-inserting into the wrong place", () => {
  const live = new LiveContext();
  const history = [user("go"), assistant("thinking about it")];
  live.apply("s1", history, "STATE v1", 1);

  // Compaction: the middle of the transcript is replaced.
  const compacted = [user("summary of earlier work"), assistant("ok")];
  const applied = live.apply("s1", compacted, "STATE v2", 2);
  assert.equal(applied.reason, "history-rewritten");
  assert.equal(applied.preserved, false);
  const notes = applied.messages.filter((message) => String(message.content).includes(LIVE_CONTEXT_MARKER));
  assert.equal(notes.length, 1, "the stale note was dropped rather than re-inserted");
  assert.match(String(notes[0]?.content), /STATE v2/);
});

await scenario("a truncated history cannot re-insert at a vanished anchor", () => {
  const live = new LiveContext();
  const long = Array.from({ length: 5 }, (_, index) => user(`m${index}`));
  live.apply("s1", long, "STATE v1", 1);
  const applied = live.apply("s1", [user("m0")], "STATE v2", 2);
  assert.ok(applied.reason === "anchor-lost" || applied.reason === "history-rewritten", applied.reason);
  assert.equal(applied.preserved, false);
  const notes = applied.messages.filter((message) => String(message.content).includes(LIVE_CONTEXT_MARKER));
  assert.equal(notes.length, 1);
});

await scenario("notes never cross sessions, in either direction", () => {
  // One property, both leak directions: a note retained for one session must
  // not appear in another's request, whether moving away or coming back.
  const live = new LiveContext();
  const history = [user("go")];
  const first = live.apply("s1", history, "STATE s1", 1);
  const other = live.apply("s2", [user("other")], "STATE s2", 2);
  assert.equal(other.reason, "session-changed");
  assert.ok(!other.messages.some((m) => String(m.content).includes("STATE s1")), "s1 leaked into s2");
  const back = live.apply("s1", [...history, assistant("ok")], "STATE s1 again", 3);
  assert.ok(!back.messages.some((m) => String(m.content).includes("STATE s2")), "s2 leaked back into s1");
  // Correctness first: no leak. Prefix stability is re-established from the
  // second request in this session onwards, which is one break, not a loop.
  assert.equal(back.reason, "session-changed");
  assert.ok(!isPrefixOf(first.messages, back.messages));
});

await scenario("the note says it is not a message from the user", async () => {
  // It is delivered with a `user` role, and a `user` role is what the model reads
  // as a request. A custom role cannot fix this: pi downgrades `role: "custom"`
  // to `role: "user"` before the provider sees it. So the framing is the only
  // thing that can carry the distinction, and it has to be explicit.
  const live = new LiveContext();
  const applied = live.apply("s1", [user("go")], "GOAL STATE", 1);
  const content = String(applied.messages[1]?.content);
  assert.match(content, /not a message from the user/i);
  assert.match(content, /not a\s+request from the user/i);
  assert.match(content, /GOAL STATE/);
  assert.match(content, /\[pi-goal runtime state/, "and is labelled as runtime state");
});

process.stdout.write(`${JSON.stringify(results)}\n`);