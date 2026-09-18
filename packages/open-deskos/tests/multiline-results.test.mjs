import assert from "node:assert/strict";
import test from "node:test";
import { eventsFromMessage } from "../src/events.ts";
import { DeskReporter } from "../src/reporter.ts";

const RESULT_BYTES = 65536;
const SESSION_BYTES = 262144;
const FRAME_BYTES = 1024 * 1024;
const table = "\n| Name | Value |\n| --- | ---: |\n| first | 1 |\n| last | 2 |\n";
const code = "```ts\r\nfunction example() {\r\n  return 'complete';\r\n}\r\n```\n";
const markdown = `${table}\n\n${code}`;
const config = { machine: "result-fixture", host: "127.0.0.1", port: 1, token: "fixture-only" };
const bytes = (events) => events.reduce((sum, event) => sum + Buffer.byteLength(event.text) + Buffer.byteLength(event.toolName ?? ""), 0);
const results = (count, toolName) => Array.from({ length: count }, (_, index) => ({
  kind: "result", text: `${String(index).padStart(2, "0")}\n${"x".repeat(RESULT_BYTES - 3)}`,
  ...(toolName ? { toolName } : {}),
}));

function harness() {
  const transports = [], timers = [];
  const reporter = new DeskReporter({
    config,
    now: () => 9000,
    schedule(run) { timers.push(run); },
    createTransport() {
      let open, close;
      const sent = [];
      const transport = {
        sent,
        open() { open?.(); },
        drop() { close?.("fixture drop"); },
        send(record) { sent.push(JSON.parse(JSON.stringify(record))); },
        close() {},
        onOpen(handler) { open = handler; },
        onClose(handler) { close = handler; },
        onRecord() {},
      };
      transports.push(transport);
      return transport;
    },
  });
  reporter.recordSession({ sessionId: "s1", cwd: "/fixture/results", workspaceName: "results", status: "running", startedAt: 1 });
  return {
    reporter, transports, timers,
    open() { reporter.start(); transports.at(-1).open(); },
    wire(index = transports.length - 1) { return transports[index].sent.filter((record) => record.type === "events"); },
    reconnect() { timers.at(-1)(); transports.at(-1).open(); },
  };
}

// Given separate Markdown text parts, when finalized, then one result preserves all text.
test("tool results preserve complete tables and code with a separate bounded tool name", () => {
  const message = { role: "toolResult", toolName: "read", content: [
    { type: "text", text: table },
    { type: "image", data: "fixture-image-not-reported", mimeType: "image/png" },
    { type: "text", text: code },
  ], details: { privateField: "fixture-details-not-reported" } };
  assert.deepEqual(eventsFromMessage(message), [{ kind: "result", text: markdown, toolName: "read" }]);
  assert.equal(message.content[0].text, table, "extraction does not mutate Pi messages");
  assert.deepEqual(eventsFromMessage({ role: "toolResult", content: [{ type: "text", text: " \n\t " }] }), []);
  assert.deepEqual(eventsFromMessage({ role: "toolResult", content: [{ type: "image", data: "ignored" }] }), []);
  assert.deepEqual(eventsFromMessage({ role: "toolResult", content: [{ type: "text", text: code }] }), [{ kind: "result", text: code }]);
  const withEmptyParts = eventsFromMessage({ role: "toolResult", content: [{ type: "text", text: "" }, { type: "text", text: code }, { type: "text", text: "" }] });
  assert.equal(withEmptyParts[0].text, `\n\n${code}\n\n`, "join every text part without trimming Markdown");
});

test("UTF-8 results at the limit stay complete and larger bodies carry explicit truncation", () => {
  const extract = (text) => eventsFromMessage({ role: "toolResult", content: [{ type: "text", text }] })[0];
  for (const body of ["x".repeat(RESULT_BYTES), "界".repeat(21845) + "x", "\u{1d11e}".repeat(16384)]) {
    const event = extract(body);
    assert.equal(Buffer.byteLength(event.text), RESULT_BYTES, "exact byte limit is preserved");
    assert.ok(event.text === body);
    assert.equal(Object.hasOwn(event, "truncated"), false, "complete body must not appear truncated");
  }
  for (const [body, expectedBytes] of [
    ["x".repeat(RESULT_BYTES + 1), RESULT_BYTES],
    ["界".repeat(21846), RESULT_BYTES - 1],
    ["x".repeat(RESULT_BYTES - 1) + "\u{1d11e}", RESULT_BYTES - 1],
    ["\u{1d11e}".repeat(16385), RESULT_BYTES],
  ]) {
    const event = extract(body);
    assert.equal(Buffer.byteLength(event.text), expectedBytes);
    assert.ok(body.startsWith(event.text), "keep the actual body prefix");
    assert.equal(event.text.includes("\ufffd"), false, "never split a UTF-8 code point");
    assert.equal(event.truncated, true);
  }
  const joined = eventsFromMessage({ role: "toolResult", content: [{ type: "text", text: "a".repeat(RESULT_BYTES - 1) }, { type: "text", text: "last" }] });
  assert.equal(joined.length, 1, "the joined body has one shared result limit");
  assert.equal(Buffer.byteLength(joined[0].text), RESULT_BYTES);
  assert.equal(joined[0].truncated, true);
});

test("recordEvents keeps Markdown and optional result fields while activity stays a short summary", () => {
  const h = harness();
  h.open();
  const input = Object.freeze({ kind: "result", text: markdown, toolName: "read", truncated: true });
  h.reporter.recordEvents("s1", [input, { kind: "result", text: " \n\t " }]);
  assert.deepEqual(h.reporter.eventsFor("s1"), [input]);
  assert.deepEqual(h.wire()[0].events, [input]);
  h.reporter.markStatus("s1", "settled");
  const snapshot = h.transports[0].sent.filter((record) => record.type === "sessions").at(-1);
  assert.equal(snapshot.sessions[0].activity, "| Name | Value |");
  assert.ok(Buffer.byteLength(`${JSON.stringify(snapshot)}\n`) <= 65536);
  h.reporter.recordEvents("s1", [{ kind: "result", text: "界".repeat(30000), toolName: "t".repeat(300) + "\nignored" }]);
  const bounded = h.wire().at(-1).events[0];
  assert.equal(Buffer.byteLength(bounded.text), 65535);
  assert.equal(bounded.truncated, true);
  assert.equal(bounded.toolName.length, 200);
  assert.equal(bounded.toolName.includes("\n"), false);
  h.reporter.markStatus("s1", "running");
  assert.equal(h.transports[0].sent.filter((record) => record.type === "sessions").at(-1).sessions[0].activity.length, 200);
  h.reporter.stop();
});

test("non-result summaries keep first-line and 200-character rules without result metadata", () => {
  const h = harness();
  h.open();
  h.reporter.recordEvents("s1", ["user", "thinking", "tool", "assistant"].map((kind) => ({
    kind, text: `\n  ${"x".repeat(250)}  \nignored`, toolName: "ignored", truncated: true,
  })));
  for (const event of h.wire()[0].events) {
    assert.equal(event.text.length, 200);
    assert.equal(event.text.includes("\n"), false);
    assert.deepEqual(Object.keys(event).sort(), ["kind", "text"]);
  }
  h.reporter.stop();
});

test("retained history and pending batches share a 256-KiB text-plus-tool-name tail", () => {
  for (const online of [false, true]) {
    for (const [toolName, count] of [[undefined, 4], ["界".repeat(200), 3]]) {
      const h = harness();
      if (online) h.open();
      const input = results(12, toolName);
      h.reporter.recordEvents("s1", input);
      const retained = h.reporter.eventsFor("s1");
      assert.equal(retained.length, count, "drop only the oldest whole events to fit bytes");
      assert.ok(bytes(retained) <= SESSION_BYTES);
      assert.deepEqual(retained.map((event) => event.text.slice(0, 2)), input.slice(-count).map((event) => event.text.slice(0, 2)));
      if (!online) h.open();
      const sent = h.wire().flatMap((record) => record.events);
      assert.equal(sent.length, count, "pending, not just retained history, must obey byte limits");
      assert.ok(bytes(sent) <= SESSION_BYTES);
      assert.ok(sent.every((event, index) => event.text === retained[index].text && event.toolName === retained[index].toolName));
      h.reporter.stop();
    }
  }
});

test("small events retain only the newest 60 in both history and pending wire batches", () => {
  for (const online of [false, true]) {
    const h = harness();
    if (online) h.open();
    h.reporter.recordEvents("s1", Array.from({ length: 70 }, (_, index) => ({ kind: "result", text: `${index}\nsecond line` })));
    assert.equal(h.reporter.eventsFor("s1").length, 60);
    assert.equal(h.reporter.eventsFor("s1")[0].text, "10\nsecond line");
    if (!online) h.open();
    const sent = h.wire().flatMap((record) => record.events);
    assert.equal(sent.length, 60);
    assert.equal(sent[59].text, "69\nsecond line");
    h.reporter.stop();
  }
});

test("JSON escape expansion splits whole ordered events into at-most-1-MiB LF frames", () => {
  const h = harness();
  h.open();
  const input = Array.from({ length: 4 }, (_, index) => ({ kind: "result", text: `${index}${"\u0000".repeat(RESULT_BYTES - 1)}` }));
  h.reporter.recordEvents("s1", input);
  assert.equal(bytes(h.reporter.eventsFor("s1")), SESSION_BYTES);
  const wire = h.wire();
  assert.ok(wire.length > 1, "escaped JSON cannot be sent as one oversized frame");
  for (const record of wire) assert.ok(Buffer.byteLength(`${JSON.stringify(record)}\n`) <= FRAME_BYTES);
  const sent = wire.flatMap((record) => record.events);
  assert.equal(sent.length, input.length);
  assert.ok(sent.every((event, index) => event.text === input[index].text), "no splitting a body, dropping, reordering or duplicating events");
  h.reporter.markStatus("s1", "settled");
  assert.equal(h.wire().length, wire.length, "ordinary flushes do not resend delivered events");
  h.reporter.stop();
});

test("reconnection replays all retained Markdown even without any new offline events", () => {
  const h = harness();
  h.open();
  h.reporter.recordEvents("s1", [{ kind: "result", text: markdown, toolName: "read", truncated: true }]);
  h.transports[0].drop();
  h.reconnect();
  assert.deepEqual(h.transports[1].sent.map((record) => record.type), ["hello", "sessions", "events"]);
  assert.deepEqual(h.wire(1)[0].events, h.wire(0)[0].events, "receiver may have forgotten all events when its last link closed");
  h.reporter.markStatus("s1", "settled");
  assert.equal(h.wire(1).length, 1, "replay is once per connection, not every state update");
  h.reporter.recordEvents("s1", [{ kind: "result", text: code }]);
  assert.deepEqual(h.wire(1).at(-1).events, [{ kind: "result", text: code }]);
  h.reporter.stop();
});

test("outages replay one bounded retained tail rather than pending plus duplicate history", () => {
  const h = harness();
  h.open();
  const all = results(12);
  h.reporter.recordEvents("s1", all.slice(0, 10));
  h.transports[0].drop();
  h.reporter.recordEvents("s1", all.slice(10));
  h.reconnect();
  const replayed = h.wire(1).flatMap((record) => record.events);
  assert.equal(replayed.length, 4);
  assert.ok(bytes(replayed) <= SESSION_BYTES);
  assert.deepEqual(replayed.map((event) => event.text.slice(0, 2)), ["08", "09", "10", "11"]);
  assert.ok(replayed.every((event, index) => event.text === all[index + 8].text));
  h.reporter.stop();
});
