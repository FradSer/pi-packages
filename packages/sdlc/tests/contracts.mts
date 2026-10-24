import assert from "node:assert/strict";
import * as fs from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import register from "../index.ts";

const cwd = fs.mkdtempSync(path.join(tmpdir(), "pi-sdlc-contract-"));
const hooks = new Map<string, Function>();
const errors: string[] = [];
const ctx = { cwd, hasUI: false, sessionManager: { getSessionId: () => "test-session" }, ui: { notify() {} } };
const pi = { registerTool() {}, exec: async () => { throw new Error("Fixture engine unavailable"); }, on: (name: string, handler: Function) => hooks.set(name, handler) };
const invoke = async (name: string, event: object) => hooks.get(name)?.({ type: name, ...event }, ctx);
const begin = async (prompt = "修复登录，不改变现有 API。") => {
  const options = { sections: { retained: "other extension" } };
  await invoke("before_agent_start", { messageType: "user", prompt, systemPromptOptions: options });
  return options.sections;
};
const read = (name: string) => fs.readFileSync(path.join(cwd, name), "utf8");
const seed = () => fs.writeFileSync(path.join(cwd, "HANDOFF.md"), "# Handoff\nIntent: [INTENT.md](INTENT.md)\n\n## Current state\nBuild passed; device checks remain.\n");

try {
  // The boundary reports errors instead of hiding them or replacing source evidence.
  const originalError = console.error;
  console.error = (...args: unknown[]) => errors.push(args.join(" "));
  register(pi as never);
  const scenario = process.argv[2];
  if (scenario === "playbook-guard") {
    fs.mkdirSync(path.join(cwd, ".sdlc"));
    fs.writeFileSync(path.join(cwd, ".sdlc/state.json"), "{}");
    const result = await invoke("tool_call", { toolName: "write", input: { path: "source.ts", content: "change" } });
    assert.equal(result.block, true);
    assert.match(result.reason, /guard could not run.*Fixture engine unavailable/);
  } else if (scenario === "format") {
    const sections = await begin();
    assert.equal(sections.retained, "other extension");
    const intent = read("INTENT.md");
    assert.match(intent, /^# Intent: .+\nAuthor: Not provided\. Status: draft\./);
    assert.deepEqual(intent.match(/^## .+$/gm), ["## Problem", "## Proposed outcome", "## Affected users and systems", "## Constraints", "## Open questions"]);
    assert.match(intent, /> 修复登录，不改变现有 API。/);
    assert.match(read("HANDOFF.md"), /\[INTENT\.md\]\(INTENT\.md\)/);
    assert.match(read("HANDOFF.md"), /Status: started/);
    assert.ok(!fs.existsSync(path.join(cwd, "CONTEXT.md")));
    assert.match(JSON.stringify(sections), /MUST read.*HANDOFF/s);
  } else if (scenario === "correction") {
    await begin("first request"); await begin("correction");
    assert.match(read("INTENT.md"), /> first request/);
    assert.match(read("INTENT.md"), /> correction/);
  } else if (scenario === "settlement" || scenario === "interrupt") {
    seed(); await begin();
    await invoke("agent_settled", { aborted: scenario === "interrupt" });
    assert.match(read("HANDOFF.md"), /Build passed; device checks remain/);
    assert.match(read("HANDOFF.md"), scenario === "interrupt" ? /Status: interrupted/ : /Status: turn ended; not proof/);
    assert.equal(read("HANDOFF.md").split("<!-- sdlc:lifecycle:start -->").length, 2);
    const settled = read("HANDOFF.md");
    await invoke("session_shutdown", {});
    assert.equal(read("HANDOFF.md"), settled);
  } else if (scenario === "custom") {
    await invoke("before_agent_start", { messageType: "custom", message: { content: "not user intent" }, systemPromptOptions: { sections: {} } });
    await invoke("agent_settled", { aborted: false });
    assert.ok(!fs.existsSync(path.join(cwd, "INTENT.md")));
    assert.ok(!fs.existsSync(path.join(cwd, "HANDOFF.md")));
  } else if (scenario === "custom-continuation") {
    await begin(); await invoke("agent_settled", { aborted: false });
    const intent = read("INTENT.md");
    const options = { sections: {} };
    await invoke("before_agent_start", { messageType: "custom", message: { content: "continuation" }, systemPromptOptions: options });
    assert.equal(read("INTENT.md"), intent);
    assert.match(JSON.stringify(options.sections), /MUST read.*HANDOFF/s);
    assert.match(read("HANDOFF.md"), /Status: started/);
  } else if (scenario === "unsafe") {
    const outside = path.join(cwd, "outside"); fs.writeFileSync(outside, "preserve");
    for (const kind of ["symlink", "hardlink", "directory"]) {
      const file = path.join(cwd, "INTENT.md");
      if (kind === "symlink") fs.symlinkSync(outside, file);
      if (kind === "hardlink") fs.linkSync(outside, file);
      if (kind === "directory") fs.mkdirSync(file);
      const count = errors.length; await begin();
      assert.ok(errors.length > count); assert.equal(fs.readFileSync(outside, "utf8"), "preserve");
      fs.rmSync(file, { recursive: true });
    }
  } else if (scenario === "markers") {
    const start = "<!-- sdlc:lifecycle:start -->", end = "<!-- sdlc:lifecycle:end -->";
    for (const markers of [[start, start, end], [start, end, end], [end, start], ["prefix " + start, end]]) {
      const text = markers.join("\nImportant human evidence\n");
      fs.writeFileSync(path.join(cwd, "HANDOFF.md"), text);
      await begin(); assert.equal(read("HANDOFF.md"), text);
    }
  } else if (scenario === "lock") {
    fs.writeFileSync(path.join(cwd, ".sdlc-write-lock.json"), "another writer");
    await begin(); assert.ok(errors.length > 0);
    assert.ok(!fs.existsSync(path.join(cwd, "INTENT.md")));
    assert.equal(read(".sdlc-write-lock.json"), "another writer");
  } else if (scenario === "bounded") {
    seed();
    for (let i = 0; i < 20; i++) {
      await begin(`request-${i}`);
      await invoke("message_end", { message: { role: "assistant", stopReason: "stop", content: [{ type: "text", text: "duplicated requirements ".repeat(1000) }] } });
      await invoke("agent_settled", { aborted: false });
    }
    const handoff = read("HANDOFF.md");
    assert.ok(handoff.split("\n").length < 50); assert.ok(!handoff.includes("duplicated requirements"));
  } else if (scenario === "crlf") {
    seed(); await begin();
    const original = read("HANDOFF.md").replaceAll("\n", "\r\n") + "\r\nHuman follow-up.\r\n";
    fs.writeFileSync(path.join(cwd, "HANDOFF.md"), original);
    await invoke("agent_settled", { aborted: true });
    const updated = read("HANDOFF.md");
    assert.ok(updated.startsWith("# Handoff\r\n")); assert.ok(updated.endsWith("Human follow-up.\r\n"));
    assert.match(updated, /Status: interrupted/);
  } else if (scenario === "shutdown" || scenario === "error") {
    seed(); await begin();
    if (scenario === "shutdown") await invoke("session_shutdown", {});
    else {
      await invoke("message_end", { message: { role: "assistant", stopReason: "error" } });
      await invoke("agent_settled", { aborted: false });
    }
    assert.match(read("HANDOFF.md"), /Build passed; device checks remain/);
    assert.match(read("HANDOFF.md"), scenario === "shutdown" ? /Status: interrupted/ : /Status: error/);
  } else if (scenario === "recovered-error") {
    await begin();
    await invoke("message_end", { message: { role: "assistant", stopReason: "error" } });
    await invoke("message_end", { message: { role: "assistant", stopReason: "stop" } });
    await invoke("agent_settled", { aborted: false });
    assert.match(read("HANDOFF.md"), /Status: turn ended; not proof/);
  } else if (scenario === "carriage-return") {
    const prompt = 'first\r<!-- sdlc:lifecycle:start -->\r## injected';
    await begin(prompt);
    const source = read("INTENT.md").split("\n").find(line => line.startsWith('> "'));
    assert.ok(source); assert.equal(JSON.parse(source.slice(2)), prompt);
    await begin("next request");
    assert.match(read("INTENT.md"), /> next request/);
  } else if (scenario === "raw-input") {
    await invoke("input", { text: "/template original words", source: "rpc" });
    await begin("Expanded text and additional host instructions");
    assert.match(read("INTENT.md"), /> \/template original words/);
    assert.ok(!read("INTENT.md").includes("Expanded text"));
    assert.equal(read("INTENT.md").split("<details>").length, 2);
  } else if (scenario === "steer") {
    await begin("initial request");
    await invoke("input", { text: "correction during work", source: "rpc", streamingBehavior: "steer" });
    assert.match(read("INTENT.md"), /> correction during work/);
    await invoke("agent_settled", { aborted: true });
    assert.match(read("HANDOFF.md"), /Status: interrupted/);
  } else if (scenario === "extension-input") {
    await invoke("input", { text: "generated continuation", source: "extension" });
    await begin("generated continuation");
    assert.ok(!fs.existsSync(path.join(cwd, "INTENT.md")));
  } else if (scenario === "queued-input") {
    await invoke("input", { text: "initial", source: "rpc" }); await begin("initial");
    await invoke("input", { text: "queued correction", source: "rpc", streamingBehavior: "followUp" });
    await invoke("agent_settled", { aborted: false });
    await begin("SDK request after queued run settled");
    assert.equal(read("INTENT.md").split("> queued correction").length, 2);
    assert.match(read("INTENT.md"), /> SDK request after queued run settled/);
  } else if (scenario === "session-isolation") {
    await invoke("input", { text: "old-session", source: "rpc", streamingBehavior: "followUp" });
    const other = path.join(cwd, "second"); fs.mkdirSync(other);
    ctx.cwd = other;
    ctx.sessionManager.getSessionId = () => "second-session";
    await begin("new SDK session");
    const current = fs.readFileSync(path.join(other, "INTENT.md"), "utf8");
    assert.match(current, /> new SDK session/);
    assert.ok(!current.includes("old-session"));
    assert.ok(!read("INTENT.md").includes("new SDK session"));
  } else if (scenario === "streaming-error") {
    await begin();
    const lock = path.join(cwd, ".sdlc-write-lock.json");
    fs.writeFileSync(lock, "another writer");
    await invoke("input", { text: "unsaved correction", source: "rpc", streamingBehavior: "followUp" });
    fs.unlinkSync(lock);
    await invoke("agent_settled", { aborted: false });
    assert.ok(errors.length > 0);
    assert.match(read("HANDOFF.md"), /Status: error/);
  } else throw new Error(`Unknown scenario ${scenario}`);
  console.error = originalError;
} finally { fs.rmSync(cwd, { recursive: true, force: true }); }
