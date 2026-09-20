import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import net from "node:net";
import test from "node:test";
import { DeskConsoleClient } from "../src/console-client.ts";
import { createControlTcpTransport } from "../src/control-transport.ts";

const config = {
  machine: "desk-mac",
  host: "127.0.0.1",
  port: 8765,
  token: "report-token",
  controlToken: "control-secret",
};

function proof(nonce, sessionId = "console-a") {
  const transcript = `open-deskos-control-v2\n2\n${nonce}\ndesk-mac\n${sessionId}`;
  return createHmac("sha256", "control-secret").update(transcript, "utf8").digest("hex");
}

function fakeDesk(handler) {
  const transports = [];
  return {
    transports,
    createTransport() {
      let openHandler = () => {};
      let closeHandler = () => {};
      let recordHandler = () => {};
      let closed = false;
      const sent = [];
      const transport = {
        sent,
        get closed() { return closed; },
        send(record) {
          sent.push(structuredClone(record));
          handler(record, {
            deliver(value) { queueMicrotask(() => recordHandler(structuredClone(value))); },
            close(reason = "desk closed") { queueMicrotask(() => closeHandler(reason)); },
          });
        },
        close() { closed = true; closeHandler("closed by console"); },
        onOpen(callback) { openHandler = callback; },
        onClose(callback) { closeHandler = callback; },
        onRecord(callback) { recordHandler = callback; },
      };
      transports.push(transport);
      queueMicrotask(() => openHandler());
      return transport;
    },
  };
}

function authenticatedDesk(onRequest) {
  let nonceIndex = 0;
  return fakeDesk((record, peer) => {
    if (record.type === "control-hello") {
      peer.deliver({ v: 2, type: "challenge", nonce: `nonce-${++nonceIndex}`, algorithm: "hmac-sha256" });
      return;
    }
    if (record.type === "control-proof") {
      peer.deliver({ v: 2, type: "control-ack", machine: "desk-mac" });
      return;
    }
    onRequest(record, peer);
  });
}

// Given a one-shot list, when challenged, then the approved transcript is bound
// and only the reporting token—not the independent credential—is on the wire.
test("one-shot requests authenticate with the canonical transcript, correlate, and unwrap result", async () => {
  const desk = authenticatedDesk((record, peer) => {
    if (record.type === "list") peer.deliver({ v: 2, type: "ack", requestId: record.requestId, result: { sessions: [{ sessionId: "hosted-1", status: "settled" }] } });
  });
  const client = new DeskConsoleClient({ config, consoleSessionId: "console-a", createTransport: desk.createTransport });
  const result = await client.list();
  assert.equal(result.sessions[0].sessionId, "hosted-1");
  const sent = desk.transports[0].sent;
  assert.deepEqual(sent.map((record) => record.type), ["control-hello", "control-proof", "list"]);
  assert.deepEqual(sent[0], { v: 2, type: "control-hello", token: "report-token", machine: "desk-mac", sessionId: "console-a" });
  assert.equal(sent[1].proof, proof("nonce-1"));
  assert.equal(JSON.stringify(sent).includes(config.controlToken), false);
  assert.equal(typeof sent[2].requestId, "string");
  assert.equal(desk.transports[0].closed, true, "one-shot connections close after the correlated answer");
});

test("explicit version mismatches close the connection before credential errors", async () => {
  const mismatch = fakeDesk((record, peer) => {
    if (record.type === "control-hello") peer.deliver({ v: 2, type: "version-mismatch", received: 2, accepted: [3] });
  });
  const client = new DeskConsoleClient({ config, consoleSessionId: "console-a", createTransport: mismatch.createTransport });
  await assert.rejects(() => client.list(), /protocol version 2.*accepted 3/i);
  assert.equal(mismatch.transports[0].closed, true);
});

test("mutations carry stable operation identities and expose them on correlated errors", async () => {
  const requests = [];
  const desk = authenticatedDesk((record, peer) => {
    requests.push(record);
    peer.deliver({ v: 2, type: "error", requestId: record.requestId, reason: "host uncertain" });
  });
  const client = new DeskConsoleClient({ config, consoleSessionId: "console-a", createTransport: desk.createTransport });
  await assert.rejects(
    () => client.launch({ project: "/workspace/desk", prompt: "Run tests", mutationId: "launch-mutation" }),
    (error) => error.mutationId === "launch-mutation" && typeof error.sessionId === "string" && error.project === "/workspace/desk" && /sessionId/.test(error.message),
  );
  assert.equal(requests[0].mutationId, "launch-mutation");
  assert.equal(typeof requests[0].sessionId, "string", "the client fixes the Hosted Pi identity before a launch can have an unknown outcome");
});

// Given no saved position, attach starts at the desk's current boundary. Old
// content is fetched only by an explicit history request.
test("fresh attach sends after null, holds the connection, and does not fetch history", async () => {
  const requests = [];
  let heldPeer;
  const desk = authenticatedDesk((record, peer) => {
    requests.push(record);
    if (record.type === "attach") {
      heldPeer = peer;
      peer.deliver({ v: 2, type: "ack", requestId: record.requestId, result: { boundary: 20, caughtUp: true } });
    } else if (record.type === "history") {
      peer.deliver({ v: 2, type: "ack", requestId: record.requestId, result: { sessionId: "hosted-1", entries: [], nextPosition: null } });
    } else {
      peer.deliver({ v: 2, type: "ack", requestId: record.requestId, result: {} });
    }
  });
  const applied = [];
  const client = new DeskConsoleClient({ config, consoleSessionId: "console-a", createTransport: desk.createTransport });
  const attachment = await client.attach({ sessionId: "hosted-1", onEvent: (entry) => applied.push(entry) });
  const attach = requests.find((record) => record.type === "attach");
  assert.equal(attach.after, null);
  assert.equal(typeof attach.attachmentId, "string");
  assert.equal(requests.some((record) => record.type === "history"), false);
  assert.equal(attachment.lastApplied(), 20);
  heldPeer.deliver({ v: 2, type: "event", attachmentId: attachment.attachmentId, sessionId: "hosted-1", position: 24, events: [{ kind: "assistant", text: "Live after non-message entries" }] });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(applied.map((entry) => entry.position), [24]);
  assert.equal(attachment.error(), undefined, "physical log positions need not be consecutive");
  attachment.close();
});

// Given a saved place, held attach buffers the atomic catch-up until caught_up,
// orders it, de-duplicates positions, then accepts strictly increasing live places.
test("resume attach orders and deduplicates catch-up, accepts physical gaps, and detects regression", async () => {
  const applied = [];
  const requests = [];
  let heldPeer;
  const desk = authenticatedDesk((record, peer) => {
    requests.push(record);
    if (record.type === "attach") {
      heldPeer = peer;
      peer.deliver({ v: 2, type: "event", attachmentId: record.attachmentId, sessionId: record.sessionId, position: 9, events: [{ kind: "assistant", text: "later" }] });
      peer.deliver({ v: 2, type: "event", attachmentId: record.attachmentId, sessionId: record.sessionId, position: 7, events: [{ kind: "thinking", text: "earlier thought" }, { kind: "tool", text: "earlier" }] });
      peer.deliver({ v: 2, type: "event", attachmentId: record.attachmentId, sessionId: record.sessionId, position: 7, events: [{ kind: "tool", text: "duplicate" }] });
      peer.deliver({ v: 2, type: "caught_up", attachmentId: record.attachmentId, sessionId: record.sessionId, boundary: 9 });
      peer.deliver({ v: 2, type: "ack", requestId: record.requestId, result: { boundary: 9 } });
    } else {
      peer.deliver({ v: 2, type: "ack", requestId: record.requestId, result: {} });
    }
  });
  const client = new DeskConsoleClient({ config, consoleSessionId: "console-a", createTransport: desk.createTransport });
  const attachment = await client.attach({ sessionId: "hosted-1", position: 4, onEvent: (entry) => applied.push(entry) });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(requests.find((record) => record.type === "attach").after, 4);
  assert.equal(requests.some((record) => record.type === "history"), false, "attach catch-up is atomic on the held connection");
  assert.deepEqual(applied.map((entry) => entry.position), [7, 9]);
  assert.deepEqual(applied[0].events.map((event) => event.kind), ["thinking", "tool"], "one physical position applies its whole event batch");
  heldPeer.deliver({ v: 2, type: "event", attachmentId: attachment.attachmentId, sessionId: "hosted-1", position: 14, events: [{ kind: "assistant", text: "live" }] });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(attachment.error(), undefined);
  heldPeer.deliver({ v: 2, type: "event", attachmentId: attachment.attachmentId, sessionId: "hosted-1", position: 12, events: [{ kind: "assistant", text: "regressed" }] });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.match(attachment.error() ?? "", /regression.*14.*12/i);
  await attachment.prompt("Continue carefully");
  await attachment.cancel({ turnId: "turn-1", precondition: "running" });
  const mutations = requests.filter((record) => ["prompt", "cancel"].includes(record.type));
  assert.ok(mutations.every((record) => typeof record.mutationId === "string"));
  assert.ok(mutations.every((record) => record.attachmentId === attachment.attachmentId));
  assert.equal(mutations[1].turnId, "turn-1");
  attachment.close();
});

test("terminal records from an attached Hosted Pi are delivered to the Console", async () => {
  let heldPeer;
  const terminals = [];
  const desk = authenticatedDesk((record, peer) => {
    if (record.type === "attach") {
      heldPeer = peer;
      peer.deliver({ v: 2, type: "ack", requestId: record.requestId, result: { boundary: 0, caughtUp: true } });
    }
  });
  const client = new DeskConsoleClient({ config, consoleSessionId: "console-a", createTransport: desk.createTransport });
  const attachment = await client.attach({ sessionId: "hosted-1", onTerminal: (record) => terminals.push(record) });
  heldPeer.deliver({ v: 2, type: "terminal", attachmentId: attachment.attachmentId, sessionId: "hosted-1", outcome: "finished", response: "Done" });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(terminals[0].response, "Done");
  attachment.close();
});

test("pre-ACK caught-up boundary never regresses a later queued event after success", async () => {
  const positions = [];
  const desk = authenticatedDesk((record, peer) => {
    if (record.type === "attach") {
      peer.deliver({ v: 2, type: "caught_up", attachmentId: record.attachmentId, sessionId: record.sessionId, boundary: 7 });
      peer.deliver({ v: 2, type: "event", attachmentId: record.attachmentId, sessionId: record.sessionId, position: 8, events: [{ kind: "assistant", text: "newer" }] });
      peer.deliver({ v: 2, type: "ack", requestId: record.requestId, result: { boundary: 7, caughtUp: true } });
    }
  });
  const client = new DeskConsoleClient({ config, consoleSessionId: "console-a", createTransport: desk.createTransport });
  const attachment = await client.attach({ sessionId: "hosted-1", onPosition: (position) => positions.push(position) });
  assert.equal(attachment.lastApplied(), 8);
  assert.deepEqual(positions, [8]);
  attachment.close();
});

test("caught-up events do not persist a position when Attach ACK fails", async () => {
  const positions = [];
  const events = [];
  const desk = authenticatedDesk((record, peer) => {
    if (record.type === "attach") {
      peer.deliver({ v: 2, type: "caught_up", attachmentId: record.attachmentId, sessionId: record.sessionId, boundary: 7 });
      peer.deliver({ v: 2, type: "event", attachmentId: record.attachmentId, sessionId: record.sessionId, position: 8, events: [{ kind: "assistant", text: "not committed" }] });
      peer.deliver({ v: 2, type: "error", requestId: record.requestId, reason: "attach failed" });
    }
  });
  const client = new DeskConsoleClient({ config, consoleSessionId: "console-a", createTransport: desk.createTransport });
  await assert.rejects(() => client.attach({ sessionId: "hosted-1", onPosition: (position) => positions.push(position), onEvent: (entry) => events.push(entry) }), /attach failed/);
  assert.deepEqual(positions, []);
  assert.deepEqual(events, []);
});

test("real loopback transport reads fragmented NDJSON and discards an oversized record", async (t) => {
  const server = net.createServer((socket) => {
    let pending = "";
    socket.on("data", (chunk) => {
      pending += chunk.toString("utf8");
      const lines = pending.split("\n");
      pending = lines.pop() ?? "";
      for (const line of lines) {
        if (!line) continue;
        const record = JSON.parse(line);
        if (record.type === "control-hello") {
          socket.write(`${JSON.stringify({ v: 2, type: "challenge", nonce: "loopback-nonce", algorithm: "hmac-sha256" })}\n`);
        } else if (record.type === "control-proof") {
          socket.write(`${JSON.stringify({ v: 2, type: "control-ack" })}\n`);
        } else if (record.type === "list") {
          socket.write("x".repeat(1024 * 1024 + 1));
          socket.write("\n");
          const response = Buffer.from(`${JSON.stringify({ v: 2, type: "ack", requestId: record.requestId, result: { sessions: [{ sessionId: "界-session", status: "settled" }] } })}\n`);
          const split = response.indexOf(Buffer.from("界")) + 1;
          socket.write(response.subarray(0, split));
          socket.write(response.subarray(split));
        }
      }
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const port = server.address().port;
  const client = new DeskConsoleClient({ config: { ...config, port }, consoleSessionId: "console-loopback", createTransport: createControlTcpTransport });
  assert.equal((await client.list()).sessions[0].sessionId, "界-session");
});
