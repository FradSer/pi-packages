import assert from "node:assert/strict";
import test from "node:test";

import { DEFAULT_DESKS_FILE, readDeskLinkConfigs } from "../src/config.ts";
import { aggregateDeskSnapshots, selectConsoleDesk } from "../src/desk-set.ts";

function deeper() {
  const files = new Map();
  return {
    files,
    readFile: (file) => {
      const content = files.get(file);
      if (content === undefined) throw missing();
      return content;
    },
  };
}

function missing(code = "ENOENT") {
  const error = new Error(`${code}: not available`);
  error.code = code;
  return error;
}

const DESKS_FILE = "/home/desk/.config/open-deskos/desks.json";

test("a desks file configures one link per desk, each with its own token", () => {
  const { readFile } = deeper();
  const env = { ODK_DESK_LINK_DESKS_FILE: DESKS_FILE, ODK_DESK_LINK_MACHINE: "desk-mac" };
  const result = readDeskLinkConfigs(env, {
    readFile: () => JSON.stringify({
      desks: [
        { address: "cm5.example.ts.net:8765", token: "token-for-cm5", controlToken: "control-for-cm5" },
        { address: "handheld.example.ts.net:8765", token: "token-for-handheld" },
      ],
    }),
  });

  assert.equal(result.source, "desks-file");
  assert.deepEqual(result.refusals, []);
  assert.equal(result.configs.length, 2);
  assert.deepEqual(
    result.configs.map((config) => [config.host, config.port, config.token, config.controlToken]),
    [
      ["cm5.example.ts.net", 8765, "token-for-cm5", "control-for-cm5"],
      ["handheld.example.ts.net", 8765, "token-for-handheld", undefined],
    ],
  );
  // One reporting machine identity, stated once, applies to every desk.
  assert.deepEqual(result.configs.map((config) => config.machine), ["desk-mac", "desk-mac"]);
});

test("an entry without a token is refused by name while the usable desks still report", () => {
  const result = readDeskLinkConfigs(
    { ODK_DESK_LINK_DESKS_FILE: DESKS_FILE },
    {
      readFile: () => JSON.stringify([
        { address: "usable.example:8765", token: "usable-token" },
        { address: "broken.example:8765", token: "" },
        { address: "no-port.example", token: "some-token" },
      ]),
    },
  );

  assert.equal(result.configs.length, 1);
  assert.equal(result.configs[0]?.host, "usable.example");
  assert.equal(result.refusals.length, 2);
  assert.ok(result.refusals.every((reason) => reason.includes("broken.example") || reason.includes("no-port.example")), result.refusals.join("; "));
});

test("an explicit desks file that cannot be read is refused rather than silently ignored", () => {
  const result = readDeskLinkConfigs(
    { ODK_DESK_LINK_DESKS_FILE: DESKS_FILE, ODK_DESK_LINK_ADDRESS: "fallback.example:8765", ODK_DESK_LINK_TOKEN: "fallback-token" },
    { readFile: () => { throw missing("EACCES"); } },
  );

  assert.deepEqual(result.configs, [], "an operator who named a file must learn it was not used");
  assert.equal(result.refusals.length, 1);
  assert.ok(result.refusals[0]?.includes(DESKS_FILE));
});

test("the single-desk environment form keeps working when no desks file exists", () => {
  const result = readDeskLinkConfigs(
    {
      ODK_DESK_LINK_ADDRESS: "cm5.example:8765",
      ODK_DESK_LINK_TOKEN: "env-token",
      ODK_DESK_LINK_CONTROL_TOKEN: "env-control",
      ODK_DESK_LINK_MACHINE: "desk-mac",
    },
    { readFile: () => { throw missing(); } },
  );

  assert.equal(result.source, "environment");
  assert.equal(result.configs.length, 1);
  assert.deepEqual(result.configs[0], {
    machine: "desk-mac",
    host: "cm5.example",
    port: 8765,
    token: "env-token",
    controlToken: "env-control",
  });
});

test("a desks file is the one source of truth when the environment also names a desk", () => {
  const result = readDeskLinkConfigs(
    {
      ODK_DESK_LINK_DESKS_FILE: DESKS_FILE,
      ODK_DESK_LINK_ADDRESS: "env.example:8765",
      ODK_DESK_LINK_TOKEN: "env-token",
    },
    { readFile: () => JSON.stringify({ desks: [{ address: "file.example:8765", token: "file-token" }] }) },
  );

  assert.equal(result.configs.length, 1);
  assert.equal(result.configs[0]?.host, "file.example");
  assert.ok(!result.configs.some((config) => config.host === "env.example"), "the environment form must not add a second link beside the file");
});

test("the default desks file is found without an explicit variable", () => {
  const result = readDeskLinkConfigs(
    {},
    { readFile: (file) => (file === DEFAULT_DESKS_FILE ? JSON.stringify({ desks: [{ address: "default.example:8765", token: "tok" }] }) : "") },
  );

  assert.equal(result.source, "desks-file");
  assert.equal(result.configs[0]?.host, "default.example");
});

test("an unconfigured machine reports to nothing", () => {
  const result = readDeskLinkConfigs({}, { readFile: () => { throw missing(); } });

  assert.deepEqual(result.configs, []);
  assert.equal(result.source, "none");
});

test("two entries for the same desk are one link", () => {
  const result = readDeskLinkConfigs(
    { ODK_DESK_LINK_DESKS_FILE: DESKS_FILE },
    { readFile: () => JSON.stringify({ desks: [{ address: "same.example:8765", token: "a" }, { address: "same.example:8765", token: "b" }] }) },
  );

  assert.equal(result.configs.length, 1);
  assert.equal(result.refusals.length, 1, "the duplicate is stated, not silently dropped");
});

test("a set of desks reports connected only when every desk is connected", () => {
  const snapshot = (endpoint, link) => ({ endpoint, link, lastError: undefined });

  const all = aggregateDeskSnapshots([
    { ...snapshot("a:8765", "connected"), machine: "desk-mac", sessions: 2, events: 7, attempts: 1, omittedSessions: 0 },
    { ...snapshot("b:8765", "connected"), machine: "desk-mac", sessions: 2, events: 7, attempts: 1, omittedSessions: 0 },
  ]);
  assert.equal(all?.link, "connected");
  assert.deepEqual(all?.desks?.map((desk) => desk.endpoint), ["a:8765", "b:8765"], "each desk keeps its own state in the aggregate");

  const half = aggregateDeskSnapshots([
    { ...snapshot("a:8765", "connected"), machine: "desk-mac", sessions: 2, events: 7, attempts: 1, omittedSessions: 0 },
    { ...snapshot("b:8765", "offline"), machine: "desk-mac", sessions: 0, events: 0, attempts: 4, omittedSessions: 0, lastError: "ECONNREFUSED" },
  ]);
  assert.equal(half?.link, "connecting", "a set that is neither fully up nor fully down is not called connected");
  assert.equal(half?.desks?.[1]?.lastError, "ECONNREFUSED");
  // The counts come from the healthy desk so a dead one cannot zero them.
  assert.equal(half?.sessions, 2);

  const none = aggregateDeskSnapshots([
    { ...snapshot("a:8765", "offline"), machine: "desk-mac", sessions: 0, events: 0, attempts: 2, omittedSessions: 0 },
  ]);
  assert.equal(none?.link, "offline");
  assert.equal(aggregateDeskSnapshots([]), null);
});

test("the console drives the desk that has a control credential, and says which", () => {
  const report = { machine: "desk-mac", host: "a", port: 8765, token: "t" };
  const control = { machine: "desk-mac", host: "b", port: 8765, token: "t", controlToken: "c" };

  assert.equal(selectConsoleDesk([report, control])?.host, "b");
  assert.equal(selectConsoleDesk([report])?.host, undefined, "no control credential means no console desk");
  // An explicit choice wins even when another desk has a control credential.
  assert.equal(selectConsoleDesk([report, control], "a:8765")?.host, "a");
  assert.equal(selectConsoleDesk([report, control], "a:8765")?.controlToken, undefined);
});
test('a keyboard-pasted multi-line prompt survives as lines, not as its first line', async () => {
  const { boundEventLines } = await import('../src/events.ts')

  // The desk shows the prompt a person typed. Taking only its first non-empty
  // line threw away everything they pasted after it, which is the report the
  // owner made: a card showed 提交。 for a message that carried much more.
  assert.equal(boundEventLines('提交。\n\n然后看截图\n再优化字号'), '提交。\n然后看截图\n再优化字号')

  // Blank lines are separators, not content: they do not consume a line of budget.
  assert.equal(boundEventLines('one\n\n\ntwo'), 'one\ntwo')

  // Beyond the line budget the text stops with an ellipsis instead of growing
  // without bound, which is what keeps a card from outgrowing its lane.
  assert.equal(boundEventLines('a\nb\nc\nd\ne', 4), 'a\nb\nc\nd\n…')
  assert.equal(boundEventLines('a\nb\nc\nd\ne', 2), 'a\nb\n…')

  // A single long line is still bounded, and a line is still whitespace-collapsed.
  const long = boundEventLines('x'.repeat(50), 4, 20)
  assert.equal(long.endsWith('…'), true)
  assert.equal(long.length <= 20, true)
  assert.equal(boundEventLines('  spaced   out  '), 'spaced out')
  assert.equal(boundEventLines(''), '')
  assert.equal(boundEventLines(undefined), '')
})
