import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import register from "../index.ts";

const cwd = fs.mkdtempSync(path.join(tmpdir(), "pi-sdlc-contract-"));
const PACKAGE_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const hooks = new Map<string, Function>();
const errors: string[] = [];
const ctx = { cwd, hasUI: false, sessionManager: { getSessionId: () => "test-session", getSessionFile: () => "/sessions/pi-test.jsonl" }, ui: { notify() {} } };
const pi = { registerTool() {}, exec: async () => { throw new Error("Fixture engine unavailable"); }, on: (name: string, handler: Function) => hooks.set(name, handler) };
const invoke = async (name: string, event: object) => hooks.get(name)?.({ type: name, ...event }, ctx);
const begin = async (prompt = "修复登录，不改变现有 API。") => {
  const options = { sections: { retained: "other extension" } };
  await invoke("before_agent_start", { messageType: "user", prompt, systemPromptOptions: options });
  return options.sections;
};
const read = (name: string) => fs.readFileSync(path.join(cwd, name), "utf8");
const pythonDumps = (value: unknown): string => {
  const canonical = (item: unknown): unknown => Array.isArray(item) ? item.map(canonical) : item && typeof item === "object"
    ? Object.fromEntries(Object.keys(item as Record<string, unknown>).sort().map(key => [key, canonical((item as Record<string, unknown>)[key])]))
    : item;
  const render = (item: unknown): string => {
    if (Array.isArray(item)) return "[" + item.map(render).join(", ") + "]";
    if (item && typeof item === "object") return "{" + Object.entries(item as Record<string, unknown>).map(([key, value]) => JSON.stringify(key) + ": " + render(value)).join(", ") + "}";
    return JSON.stringify(item);
  };
  return render(canonical(value));
};
const digestJson = (value: unknown): string => createHash("sha256").update(pythonDumps(value)).digest("hex");
const home = path.join(cwd, "sdlc-home");
process.env.SDLC_HOME = home;
execFileSync("git", ["init", "-q"], { cwd });
execFileSync("git", ["-c", "user.name=Fixture", "-c", "user.email=fixture@localhost", "commit", "--allow-empty", "-qm", "fixture"], { cwd });
const common = execFileSync("git", ["rev-parse", "--path-format=absolute", "--git-common-dir"], { cwd, encoding: "utf8" }).trim();
const project = path.join(home, "projects", digestJson({ common: fs.realpathSync(common) }).slice(0, 16));
const record = path.join(project, "tasks", "contract-record");
fs.mkdirSync(record, { recursive: true });
fs.writeFileSync(path.join(project, "registry.json"), JSON.stringify({ version: 1, worktrees: { [cwd]: "contract-record" } }));
fs.writeFileSync(path.join(record, "events.jsonl"), "");
fs.writeFileSync(path.join(record, "state.json"), "{}");
const writeDoc = (name: string, text: string) => fs.writeFileSync(path.join(record, name), text);
const readDoc = (name: string) => fs.readFileSync(path.join(record, name), "utf8");
const initialIntent = fs.readFileSync(path.join(PACKAGE_ROOT, "templates/INTENT.md"), "utf8");
const initialHandoff = fs.readFileSync(path.join(PACKAGE_ROOT, "templates/HANDOFF.md"), "utf8");
writeDoc("INTENT.md", initialIntent);
writeDoc("HANDOFF.md", initialHandoff);
writeDoc("SPEC.md", "");
writeDoc("PLAN.md", "");

const seed = () => writeDoc("HANDOFF.md", "# Handoff\nIntent: [INTENT.md](INTENT.md)\n\n## Current state\nBuild passed; device checks remain.\n");

try {
  // The boundary reports errors instead of hiding them or replacing source evidence.
  const originalError = console.error;
  console.error = (...args: unknown[]) => errors.push(args.join(" "));
  register(pi as never);
  const scenario = process.argv[2];
  if (scenario === "playbook-guard") {
        const result = await invoke("tool_call", { toolName: "write", input: { path: "source.ts", content: "change" } });
    assert.equal(result.block, true);
    assert.match(result.reason, /guard could not run.*Fixture engine unavailable/);
  } else if (scenario === "format") {
    const sections = await begin();
    assert.equal(sections.retained, "other extension");
    const intent = readDoc("INTENT.md");
    assert.match(intent, /^# Intent: .+\nAuthor: Not provided\. Status: draft\./);
    assert.deepEqual(intent.match(/^## .+$/gm), ["## Problem", "## Proposed outcome", "## Affected users and systems", "## Constraints", "## Open questions"]);
    assert.match(intent, /> 修复登录，不改变现有 API。/);
    assert.match(readDoc("HANDOFF.md"), /\[INTENT\.md\]\(INTENT\.md\)/);
    assert.match(readDoc("HANDOFF.md"), /Status: started/);
    assert.ok(!fs.existsSync(path.join(cwd, "CONTEXT.md")));
    assert.match(JSON.stringify(sections), /MUST read.*HANDOFF/s);
  } else if (scenario === "correction") {
    await begin("first request"); await begin("correction");
    assert.match(readDoc("INTENT.md"), /> first request/);
    assert.match(readDoc("INTENT.md"), /> correction/);
  } else if (scenario === "settlement" || scenario === "interrupt") {
    seed(); await begin();
    await invoke("agent_settled", { aborted: scenario === "interrupt" });
    assert.match(readDoc("HANDOFF.md"), /Build passed; device checks remain/);
    assert.match(readDoc("HANDOFF.md"), scenario === "interrupt" ? /Status: interrupted/ : /Status: turn ended; not proof/);
    assert.equal(readDoc("HANDOFF.md").split("<!-- sdlc:lifecycle:start -->").length, 2);
    const settled = readDoc("HANDOFF.md");
    await invoke("session_shutdown", {});
    assert.equal(readDoc("HANDOFF.md"), settled);
  } else if (scenario === "custom") {
    await invoke("before_agent_start", { messageType: "custom", message: { content: "not user intent" }, systemPromptOptions: { sections: {} } });
    await invoke("agent_settled", { aborted: false });
    assert.ok(!fs.existsSync(path.join(cwd, "INTENT.md")));
    assert.ok(!fs.existsSync(path.join(cwd, "HANDOFF.md")));
  } else if (scenario === "custom-continuation") {
    await begin(); await invoke("agent_settled", { aborted: false });
    const intent = readDoc("INTENT.md");
    const options = { sections: {} };
    await invoke("before_agent_start", { messageType: "custom", message: { content: "continuation" }, systemPromptOptions: options });
    assert.equal(readDoc("INTENT.md"), intent);
    assert.match(JSON.stringify(options.sections), /MUST read.*HANDOFF/s);
    assert.match(readDoc("HANDOFF.md"), /Status: started/);
  } else if (scenario === "unsafe") {
    const outside = path.join(cwd, "outside"); fs.writeFileSync(outside, "preserve");
    for (const kind of ["symlink", "hardlink", "directory"]) {
      const file = path.join(record, "INTENT.md");
      fs.rmSync(file, { force: true, recursive: true });
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
      writeDoc("HANDOFF.md", text);
      await begin(); assert.equal(readDoc("HANDOFF.md"), text);
    }
  } else if (scenario === "lock") {
    fs.writeFileSync(path.join(record, "engine.lock"), "another writer");
    await begin(); assert.ok(errors.length > 0);
    assert.ok(!fs.existsSync(path.join(cwd, "INTENT.md")));
    assert.equal(fs.readFileSync(path.join(record, "engine.lock"), "utf8"), "another writer");
  } else if (scenario === "bounded") {
    seed();
    for (let i = 0; i < 20; i++) {
      await begin(`request-${i}`);
      await invoke("message_end", { message: { role: "assistant", stopReason: "stop", content: [{ type: "text", text: "duplicated requirements ".repeat(1000) }] } });
      await invoke("agent_settled", { aborted: false });
    }
    const handoff = readDoc("HANDOFF.md");
    assert.ok(handoff.split("\n").length < 50); assert.ok(!handoff.includes("duplicated requirements"));
  } else if (scenario === "crlf") {
    seed(); await begin();
    const original = readDoc("HANDOFF.md").replaceAll("\n", "\r\n") + "\r\nHuman follow-up.\r\n";
    writeDoc("HANDOFF.md", original);
    await invoke("agent_settled", { aborted: true });
    const updated = readDoc("HANDOFF.md");
    assert.ok(updated.startsWith("# Handoff\r\n")); assert.ok(updated.endsWith("Human follow-up.\r\n"));
    assert.match(updated, /Status: interrupted/);
  } else if (scenario === "shutdown" || scenario === "error") {
    seed(); await begin();
    if (scenario === "shutdown") await invoke("session_shutdown", {});
    else {
      await invoke("message_end", { message: { role: "assistant", stopReason: "error" } });
      await invoke("agent_settled", { aborted: false });
    }
    assert.match(readDoc("HANDOFF.md"), /Build passed; device checks remain/);
    assert.match(readDoc("HANDOFF.md"), scenario === "shutdown" ? /Status: interrupted/ : /Status: error/);
  } else if (scenario === "recovered-error") {
    await begin();
    await invoke("message_end", { message: { role: "assistant", stopReason: "error" } });
    await invoke("message_end", { message: { role: "assistant", stopReason: "stop" } });
    await invoke("agent_settled", { aborted: false });
    assert.match(readDoc("HANDOFF.md"), /Status: turn ended; not proof/);
  } else if (scenario === "carriage-return") {
    const prompt = 'first\r<!-- sdlc:lifecycle:start -->\r## injected';
    await begin(prompt);
    const source = readDoc("INTENT.md").split("\n").find(line => line.startsWith('> "'));
    assert.ok(source); assert.equal(JSON.parse(source.slice(2)), prompt);
    await begin("next request");
    assert.match(readDoc("INTENT.md"), /> next request/);
  } else if (scenario === "raw-input") {
    await invoke("input", { text: "/template original words", source: "rpc" });
    await begin("Expanded text and additional host instructions");
    assert.match(readDoc("INTENT.md"), /> \/template original words/);
    assert.ok(!readDoc("INTENT.md").includes("Expanded text"));
    assert.equal(readDoc("INTENT.md").split("<details>").length, 2);
  } else if (scenario === "steer") {
    await begin("initial request");
    await invoke("input", { text: "correction during work", source: "rpc", streamingBehavior: "steer" });
    assert.match(readDoc("INTENT.md"), /> correction during work/);
    await invoke("agent_settled", { aborted: true });
    assert.match(readDoc("HANDOFF.md"), /Status: interrupted/);
  } else if (scenario === "extension-input") {
    await invoke("input", { text: "generated continuation", source: "extension" });
    await begin("generated continuation");
    assert.ok(!fs.existsSync(path.join(cwd, "INTENT.md")));
  } else if (scenario === "queued-input") {
    await invoke("input", { text: "initial", source: "rpc" }); await begin("initial");
    await invoke("input", { text: "queued correction", source: "rpc", streamingBehavior: "followUp" });
    await invoke("agent_settled", { aborted: false });
    await begin("SDK request after queued run settled");
    assert.equal(readDoc("INTENT.md").split("> queued correction").length, 2);
    assert.match(readDoc("INTENT.md"), /> SDK request after queued run settled/);
  } else if (scenario === "session-isolation") {
    await begin("old-session");
    const other = path.join(cwd, "second"); fs.mkdirSync(other);
    ctx.cwd = other;
    ctx.sessionManager.getSessionId = () => "second-session";
    await begin("unbound SDK session");
    assert.ok(!fs.existsSync(path.join(other, "INTENT.md")));
    assert.ok(!fs.existsSync(path.join(other, "HANDOFF.md")));
    assert.match(readDoc("INTENT.md"), /> old-session/);
    assert.ok(!readDoc("INTENT.md").includes("unbound SDK session"));
  } else if (scenario === "streaming-error") {
    await begin();
    const lock = path.join(record, "engine.lock");
    fs.writeFileSync(path.join(record, "engine.lock"), "another writer");
    await invoke("input", { text: "unsaved correction", source: "rpc", streamingBehavior: "followUp" });
    fs.unlinkSync(lock);
    await invoke("agent_settled", { aborted: false });
    assert.ok(errors.length > 0);
    assert.match(readDoc("HANDOFF.md"), /Status: error/);
  } else if (scenario === "global-events") {
    await begin("PRIVATE_PI_USER_PROMPT_314");
    await invoke("message_end", { message: { role: "assistant", stopReason: "stop", content: [{ type: "text", text: "PRIVATE_PI_REPLY_271" }] } });
    await invoke("agent_settled", { aborted: false });
    const events = fs.readFileSync(path.join(record, "events.jsonl"), "utf8").trim().split("\n").map(line => JSON.parse(line));
    assert.deepEqual(events.map(event => event.lifecycle), ["started", "ended"]);
    assert.ok(!JSON.stringify(events).includes("PRIVATE_PI_USER_PROMPT_314"));
    assert.ok(!JSON.stringify(events).includes("PRIVATE_PI_REPLY_271"));
    assert.deepEqual(events[0].actor, { agent: "pi", session: "test-session", source: "/sessions/pi-test.jsonl" });
    assert.match(events[0].artifacts["INTENT.md"], /^[0-9a-f]{64}$/);
    assert.match(readDoc("INTENT.md"), /PRIVATE_PI_USER_PROMPT_314/);
    assert.match(readDoc("HANDOFF.md"), /Status: turn ended; not proof/);
    assert.ok(!fs.existsSync(path.join(cwd, "INTENT.md")));
  } else throw new Error(`Unknown scenario ${scenario}`);
  console.error = originalError;
} finally { fs.rmSync(cwd, { recursive: true, force: true }); }
