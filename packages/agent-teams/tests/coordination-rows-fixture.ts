/**
 * Contract for the human-facing coordination rows: names, subjects, and the
 * text the Leader typed — never a session, Work, or assignment identifier.
 */

import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { stripVTControlCharacters } from "node:util";
import { initTheme, keyHint, type ExtensionAPI, type ToolDefinition } from "@earendil-works/pi-coding-agent";
import { KeybindingsManager, setKeybindings, truncateToWidth, visibleWidth, wrapTextWithAnsi, type Component } from "@earendil-works/pi-tui";
import agentTeams from "../src/index.ts";
import { runAgentAction } from "../src/agent-actions.ts";
import { resolveWorkerTools } from "../src/spawner.ts";
import { clearSessionAgents, registerSessionAgent } from "../src/agents.ts";
import { registerLeaderTools } from "../src/tools.ts";
import { registerWorkerCapabilities } from "../src/worker.ts";
import {
  createTask,
  getTeammate,
  registerTeammate,
  resetState,
  updateTeammate,
} from "../src/state.ts";

initTheme("dark", false);
// In-memory keybindings and a disposable agent directory keep this fixture
// independent of the developer's installed settings and terminal preferences.
setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }));
resetState();
clearSessionAgents();

const theme = {
  fg: (_name: string, text: string) => text,
  bg: (_name: string, text: string) => text,
  bold: (text: string) => text,
};

const tools = new Map<string, ToolDefinition>();
const capture = (prefix: string) => ({
  registerTool: (definition: ToolDefinition) => { tools.set(`${prefix}:${definition.name}`, definition); },
  on: () => {},
});
const runtime = {
  spawnTeammate(input: any) {
    const teammate = {
      name: input.name,
      agent: input.agent,
      spawnId: randomUUID(),
      workId: input.workId,
      status: "starting" as const,
      pid: 4242,
      isolation: "none" as const,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    registerTeammate({ ...teammate, assignment: input.prompt ? { id: `direct:${randomUUID()}`, kind: "direct", resources: input.resources ?? [] } : undefined });
    updateTeammate(input.name, {
      model: input.model ?? "anthropic/claude-sonnet-4-5",
      // Honor the requested grant so a coordination-only spawn renders the same
      // narrow Tools and Warning lines the real receipt produces.
      tools: resolveWorkerTools(input.definition?.tools ?? ["read", "bash"]),
      ...(input.prompt ? {} : { assignment: undefined }),
    });
    return { ok: true as const, teammate: getTeammate(input.name)! };
  },
  async shutdownTeammateExact(_name: string, _spawnId: string) {
    return { ok: true as const, body: `Agent @${_name} stopped. Work returned to pending.` };
  },
  sendLeaderMessage: () => ({ ok: true as const, outcome: "sent" }),
};
registerLeaderTools(capture("leader") as unknown as ExtensionAPI, runtime as never);
registerWorkerCapabilities(capture("worker") as unknown as ExtensionAPI);

interface RenderPayload {
  details?: unknown;
  text?: string;
  isError?: boolean;
  expanded?: boolean;
  isPartial?: boolean;
}

function renderComponent(
  key: string,
  args: Record<string, unknown>,
  payload: RenderPayload,
  rowTheme = theme,
): Component {
  const tool = tools.get(key);
  assert.ok(tool?.renderResult, `${key} has no result renderer`);
  return tool.renderResult(
    { content: [{ type: "text", text: payload.text ?? JSON.stringify(payload.details) }], details: payload.details },
    { expanded: payload.expanded ?? false, isPartial: payload.isPartial ?? false },
    rowTheme as never,
    { args, toolCallId: `call-${key}`, isError: payload.isError } as never,
  );
}

function render(key: string, args: Record<string, unknown>, payload: RenderPayload): string {
  return stripVTControlCharacters(renderComponent(key, args, payload).render(200).join("\n"));
}

function contentRows(component: Component, width: number): string[] {
  const lines = component.render(width);
  assert.ok(lines.every((line) => visibleWidth(line) <= width), `row exceeds ${width} display columns:\n${lines.join("\n")}`);
  return lines.slice(1, -1).map((line) => stripVTControlCharacters(line).slice(1).trimEnd());
}

const NO_IDENTIFIER = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|session:|work:|direct:/i;

function expectReadable(row: string, label: string): void {
  assert.ok(!NO_IDENTIFIER.test(row), `${label} leaked an identifier:\n${row}`);
}

// ── agent: delegate, inspect, stop, failure ───────────────────────

registerSessionAgent({ name: "ui-auditor", description: "Audits visible TUI rows", prompt: "Audit TUI rows.", tools: ["read", "bash"] });
const started = runAgentAction({
  action: "delegate",
  name: "ui-auditor",
  prompt: "Fix the spacing under the started row.\nCheck the widget too.",
  resources: ["packages/context"],
  model: "anthropic/claude-sonnet-4-5",
}, undefined, runtime);
assert.equal(started.action, "delegate");
const task = createTask({ id: started.work.id, subject: "Fix the spacing under the started row", resources: ["packages/context"] });
assert.ok(task.ok);

const collapsed = render("leader:agent", { action: "delegate", name: "ui-auditor", prompt: "Fix the spacing under the started row.\nCheck the widget too." }, { details: started });
expectReadable(collapsed, "delegate row");
assert.match(collapsed, /@ui-auditor · started · Fix the spacing under the started row/);
assert.ok(!collapsed.includes("role ·"), `collapsed delegate row must stay one line:\n${collapsed}`);

const expanded = render("leader:agent", { action: "delegate", name: "ui-auditor", prompt: "Fix the spacing under the started row.\nCheck the widget too.", resources: ["packages/context"] }, { details: started, expanded: true });
expectReadable(expanded, "expanded delegate row");
for (const line of ["role · Audits visible TUI rows · session role", "task · Fix the spacing under the started row.", "Check the widget too.", "model · anthropic/claude-sonnet-4-5", "tools · read, bash, agent_event, work", "resources · packages/context"]) {
  assert.ok(expanded.includes(line), `expanded delegate row missing "${line}":\n${expanded}`);
}
assert.ok(!expanded.includes("work · Fix the spacing"), "expanded delegate row must not duplicate the prompt as a work field");

const handle = started.session.id;
const working = runAgentAction({ action: "inspect", name: "ui-auditor", session: handle }, undefined, runtime);
updateTeammate("ui-auditor", { status: "working", activeTool: "file: overlay.ts" });
const inspected = render("leader:agent", { action: "inspect", name: "ui-auditor", session: handle }, { details: working, expanded: true });
expectReadable(inspected, "inspect row");
assert.match(inspected, /@ui-auditor · working/);
assert.ok(inspected.includes("now · file: overlay.ts"), `inspect row missing live activity:\n${inspected}`);

updateTeammate("ui-auditor", { status: "idle", activeTool: undefined });
const idleInspected = render("leader:agent", { action: "inspect", name: "ui-auditor", session: handle }, { details: { ...working, sessions: [{ ...working.sessions[0], status: "idle" }] }, expanded: true });
assert.ok(!idleInspected.includes("now ·"), `idle inspect row must not display a now activity:\n${idleInspected}`);
assert.ok(!idleInspected.includes("work ·"), `idle inspect row without active work must not dump old work:\n${idleInspected}`);
assert.ok(!idleInspected.includes("status ·"), `inspect row must not repeat its own header state word:\n${idleInspected}`);

// A coordination-only spawn states its narrow grant on the row that created it.
const narrowStarted = runAgentAction({
  action: "delegate",
  name: "row-check-narrow",
  prompt: "Answer with one word.",
  definition: { description: "Minimal probe", prompt: "Answer with one word.", tools: [] },
}, undefined, runtime);
const narrowRow = render("leader:agent", { action: "delegate", name: "row-check-narrow", prompt: "Answer with one word.", definition: { description: "Minimal probe", prompt: "Answer with one word.", tools: [] } }, { details: narrowStarted, expanded: true });
expectReadable(narrowRow, "coordination-only delegate row");
assert.ok(narrowRow.includes("tools · agent_event, work"), `narrow delegate row missing its grant:\n${narrowRow}`);
assert.ok(narrowRow.includes("warning · coordination-only"), `narrow delegate row missing the coordination-only warning:\n${narrowRow}`);

const stopped = await runAgentAction({ action: "stop", session: handle }, undefined, runtime);
const stoppedRow = render("leader:agent", { action: "stop", session: handle }, { details: stopped, expanded: true });
expectReadable(stoppedRow, "stop row");
assert.ok(stoppedRow.includes("@ui-auditor · stopped"), `stop row missing plain state:\n${stoppedRow}`);
assert.ok(stoppedRow.includes("Agent @ui-auditor stopped."), `stop row missing the shutdown summary:\n${stoppedRow}`);
assert.ok(!stoppedRow.includes("work ·"), `stop row must not duplicate previous work:\n${stoppedRow}`);

const failure = `Agent "ghost" not found. Direct assignment resources conflict with @ui-auditor's direct assignment "${started.assignment.id}" over ${started.work.id}.`;
const failureRow = render("leader:agent", { action: "delegate", name: "ghost" }, { text: failure, details: undefined, isError: true, expanded: true });
assert.ok(failureRow.includes("failed"), `failed row missing the plain state:\n${failureRow}`);
assert.ok(failureRow.includes('Agent "ghost" not found'), `failed row dropped the reason:\n${failureRow}`);
assert.ok(failureRow.includes("Fix the spacing under the started row"), `failed row kept a Work identifier:\n${failureRow}`);
expectReadable(failureRow, "failed row");

// ── work: subjects lead, identifiers stay model-facing ─────────────
const createdRow = render("leader:work", { action: "create", subject: "Fix the spacing under the started row" }, {
  details: {
    action: "create", outcome: "created", state: "pending",
    work: { id: task.ok ? task.task.id : "", subject: "Fix the spacing under the started row", resources: ["packages/context"], state: "pending" },
    notifiedTeammates: ["ui-auditor"], claimable: true, supersededWorkIds: [],
  },
  text: `WORK · current session\nCREATED · ${task.ok ? task.task.id : ""} · pending/claimable · Fix the spacing\nROUTING · eligible residents notified: @ui-auditor`,
  expanded: true,
});
assert.ok(createdRow.includes("Fix the spacing under the started row · created"), `work create row missing the subject:\n${createdRow}`);
expectReadable(createdRow, "work create row");
assert.ok(createdRow.includes("routing · @ui-auditor"), `work create row missing routing:\n${createdRow}`);

const listedRow = render("leader:work", { action: "list" }, {
  details: { action: "list", outcome: "listed", count: 1, works: [{ id: task.ok ? task.task.id : "", subject: "Fix the spacing under the started row", dependsOn: [], resources: [], state: "claimed", claimedBy: "ui-auditor" }] },
  text: "WORK · current session",
  expanded: true,
});
expectReadable(listedRow, "work list row");
assert.ok(listedRow.includes("1 work item"), `work list row missing the count:\n${listedRow}`);
assert.ok(listedRow.includes("· claimed · @ui-auditor"), `work list row missing state and owner:\n${listedRow}`);

// ── agent_event: the message itself, not the routing record ─────────

const messageRow = render("leader:agent_event", { to: "@ui-auditor", message: "Also check the widget spacing, then report.", intent: "request" }, {
  details: { to: "ui-auditor", outcome: "sent", intent: "request" },
  text: `EVENT ROUTING · sent · to=@ui-auditor\nINTENT · request`,
  expanded: true,
});
expectReadable(messageRow, "message row");
assert.ok(messageRow.includes("to @ui-auditor"), `message row missing the recipient:\n${messageRow}`);
assert.ok(messageRow.includes("Also check the widget spacing, then report."), `message row missing the message text:\n${messageRow}`);
assert.ok(!messageRow.includes("EVENT ROUTING"), `message row still shows the routing record:\n${messageRow}`);

const workerMessageRow = render("worker:agent_event", { message: "Done: spacing fixed and tests pass." }, {
  details: { to: "leader", outcome: "queued", intent: "inform" },
  text: "MESSAGING\nREPORT · to=leader · intent=inform",
  expanded: true,
});
expectReadable(workerMessageRow, "worker message row");
assert.ok(workerMessageRow.includes("Done: spacing fixed and tests pass."), `worker message row missing the report text:\n${workerMessageRow}`);

// ── worker work rows name the task, not the id ─────────────────────

const claimRow = render("worker:work", { action: "claim", id: task.ok ? task.task.id : "" }, {
  details: { action: "claim", outcome: "queued", id: task.ok ? task.task.id : "", subject: "Fix the spacing under the started row", worker: "ui-auditor" },
  text: `WORK · current session\nCLAIM INTENT QUEUED · ${task.ok ? task.task.id : ""} · Fix the spacing under the started row\nREQUESTER · @ui-auditor\nNEXT · wait for harness claim acceptance`,
  expanded: true,
});
expectReadable(claimRow, "worker claim row");
assert.ok(claimRow.includes("Fix the spacing under the started row · claim queued"), `worker claim row missing the subject:\n${claimRow}`);

const submitRow = render("worker:work", { action: "submit", outcome: "success" }, {
  details: { action: "submit", outcome: "queued", id: task.ok ? task.task.id : "", subject: "Fix the spacing under the started row", status: "success", verify: false },
  text: `WORK · current session\nSUBMISSION INTENT QUEUED · ${task.ok ? task.task.id : ""} · success\nVERIFY · none configured\nNEXT · wait for the harness result`,
  expanded: true,
});
expectReadable(submitRow, "worker submit row");
assert.ok(submitRow.includes("Fix the spacing under the started row"), `worker submit row missing the owned task subject:\n${submitRow}`);

// Model-supplied arguments arrive untyped: rendering must degrade, not throw.
for (const hostile of [{ action: "delegate", name: "ui-auditor", prompt: 42 }, { action: "delegate", name: 7 }, { action: "inspect" }, {}]) {
  expectReadable(render("leader:agent", hostile, { details: started, expanded: true }), `row for ${JSON.stringify(hostile)}`);
}
for (const hostile of [{ to: 5, message: { text: "hi" } }, {}, { action: "create", subject: { a: 1 }, dependsOn: "work:x" }, { action: "list" }]) {
  expectReadable(render("leader:agent_event", hostile, { details: { to: "ui-auditor", outcome: "sent" }, expanded: true }), `row for ${JSON.stringify(hostile)}`);
}

// A person's own identifier text is content, not a runtime handle: it survives.
const literal = render("leader:agent_event", { to: "@ui-auditor", message: "Compare with 6d102f1b-cc16-4059-8d86-d5c1192f3776 in the log." }, {
  details: { to: "ui-auditor", outcome: "sent", intent: "inform" },
  text: "EVENT ROUTING · sent",
  expanded: true,
});
assert.ok(literal.includes("6d102f1b-cc16-4059-8d86-d5c1192f3776"), `message text lost written identifier:
${literal}`);

// ── registered message surfaces: terminal-width preview and inline expansion ──

for (const surface of ["leader:agent_event", "worker:agent_event"]) {
  const prefix = "[message] to @continual-audit-close · steered · ";
  const message = `Start marker: ${Array.from({ length: 32 }, (_, i) => `evidence-${i}`).join(" ")} END-MARKER`;
  const args = { to: "continual-audit-close", message };
  const payload = { details: { to: "continual-audit-close", outcome: "steered" }, text: "EVENT ROUTING · steered" };
  const hint = stripVTControlCharacters(` · ${keyHint("app.tools.expand", "to expand")}`);
  const collapsed = renderComponent(surface, args, payload);
  const expanded = renderComponent(surface, args, { ...payload, expanded: true });
  for (const width of [48, 90, 240]) {
    assert.deepEqual(contentRows(collapsed, width), [
      stripVTControlCharacters(truncateToWidth(prefix + message, width - 2 - visibleWidth(hint))) + hint,
    ], `${surface}: collapsed preview must use ${width} columns, not a fixed character cap`);
    assert.deepEqual(contentRows(expanded, width), wrapTextWithAnsi(prefix + message, width - 2).map((line) => line.trimEnd()),
      `${surface}: expanded message must be one complete inline paragraph at width ${width}`);
  }
  // Render the same component through multiple sizes, without reconstructing it.
  const fullWidth = visibleWidth(prefix + message) + 2;
  assert.deepEqual(contentRows(collapsed, fullWidth), [prefix + message], `${surface}: fully visible text must not advertise expansion`);
  assert.ok(contentRows(collapsed, 90)[0].endsWith(hint), `${surface}: shrinking must restore the full hint`);
  assert.deepEqual(contentRows(collapsed, fullWidth), [prefix + message], `${surface}: growing must remove the hint again`);
  const hintWidth = visibleWidth(hint);
  assert.equal(contentRows(collapsed, hintWidth + 2)[0], hint.trimEnd(), `${surface}: the full hint must fit at its exact padded width`);
  for (const width of [3, 8, hintWidth + 1]) {
    const nativeHint = ` · ${keyHint("app.tools.expand", "to expand")}`;
    assert.deepEqual(contentRows(collapsed, width), wrapTextWithAnsi(nativeHint, width - 2).map((line) => stripVTControlCharacters(line).trimEnd()),
      `${surface}: physically narrow hints must wrap instead of losing text`);
  }
  assert.deepEqual(collapsed.render(0), []);
  for (const width of [1, 2]) {
    const lines = collapsed.render(width);
    assert.ok(lines.every((line) => visibleWidth(line) <= width), `${surface}: tiny terminals remain bounded`);
    assert.deepEqual(lines.slice(1, -1).map((line) => stripVTControlCharacters(line).trimEnd()),
      wrapTextWithAnsi(` · ${keyHint("app.tools.expand", "to expand")}`, width).map((line) => stripVTControlCharacters(line).trimEnd()),
      `${surface}: drop padding only when needed to retain hint text on tiny terminals`);
  }

  const exactRecipient = renderComponent(surface, { to: "session:reader:spawn-1", message: "Brief update." }, {});
  assert.deepEqual(contentRows(exactRecipient, 200), ["[message] to @reader · Brief update."], `${surface}: exact recipient route must remain model-only`);
  const prefixedRecipient = renderComponent(surface, { to: "@reader", message: "Brief update." }, {});
  assert.deepEqual(contentRows(prefixedRecipient, 200), ["[message] to @reader · Brief update."]);

  const shortMessage = "Brief update.";
  const short = renderComponent(surface, { ...args, message: shortMessage }, payload);
  assert.deepEqual(contentRows(short, 200), [prefix + shortMessage]);
  const notedPayload = { ...payload, details: { ...payload.details, terminalReport: "recorded result" } };
  const noted = renderComponent(surface, { ...args, message: shortMessage }, notedPayload);
  assert.deepEqual(contentRows(noted, 200), [prefix + shortMessage + hint]);
  const notedExpanded = renderComponent(surface, { ...args, message: shortMessage }, { ...notedPayload, expanded: true });
  assert.deepEqual(contentRows(notedExpanded, 200), [prefix + shortMessage, "note · terminal report recorded for this Work"]);

  // Full readback bypasses both the generic fifty-detail-line and field-size caps.
  const longMessage = Array.from({ length: 61 }, (_, index) => `line-${index}: ${"complete-message ".repeat(8)}`).join("\n") + "\n\nLAST-PARAGRAPH";
  const longExpanded = renderComponent(surface, { ...args, message: longMessage }, { ...payload, expanded: true });
  assert.deepEqual(contentRows(longExpanded, 90), wrapTextWithAnsi(prefix + longMessage, 88).map((line) => line.trimEnd()));
  const semanticMessage = "First line\n\nSecond line\n  indented third line";
  assert.deepEqual(contentRows(renderComponent(surface, { ...args, message: semanticMessage }, { ...payload, expanded: true }), 200),
    [prefix + "First line", "", "Second line", "  indented third line"]);

  const literalMessage = 'Preserve this JSON: {"value":""}\nLiteral spacing: alpha ; beta !\nTwo quoted lines: "\n"';
  for (const width of [48, 90, 240]) {
    const literalRows = contentRows(renderComponent(surface, { ...args, message: literalMessage }, { ...payload, expanded: true }), width);
    assert.deepEqual(literalRows, wrapTextWithAnsi(prefix + literalMessage, width - 2).map((line) => line.trimEnd()),
      `${surface}: expanded literal syntax must survive without prose cleanup at ${width}`);
  }

  const decorated = "\u001b]0;bad-title\u0007\u001b[31m检查终端宽度\u001b[0m cafe\u0301 界界界 ".repeat(18) + `session:reader:spawn-1 ${started.work.id} direct:6d102f1b-cc16-4059-8d86-d5c1192f3776`;
  const readable = "检查终端宽度 cafe\u0301 界界界 ".repeat(18) + "@reader Fix the spacing under the started row its assignment";
  for (const width of [48, 90, 240]) {
    const unicodeRows = contentRows(renderComponent(surface, { ...args, message: decorated }, { ...payload, expanded: true }), width);
    assert.deepEqual(unicodeRows, wrapTextWithAnsi(prefix + readable, width - 2).map((line) => line.trimEnd()));
    expectReadable(unicodeRows.join("\n"), `${surface}: Unicode message`);
    assert.ok(!unicodeRows.join("\n").includes("bad-title"));
    assert.deepEqual(contentRows(renderComponent(surface, { ...args, message: decorated }, payload), width), [
      stripVTControlCharacters(truncateToWidth(prefix + readable, width - 2 - visibleWidth(hint))) + hint,
    ]);
  }

  const hyperlink = "Open \u001b]8;;https://example.test\u001b\\LINK-LABEL\u001b]8;;\u001b\\ after.";
  for (const width of [48, 90, 240]) {
    const linkedRows = contentRows(renderComponent(surface, { ...args, message: hyperlink }, { ...payload, expanded: true }), width);
    assert.deepEqual(linkedRows, wrapTextWithAnsi(prefix + "Open LINK-LABEL after.", width - 2).map((line) => line.trimEnd()));
  }

  const styledTheme = {
    fg: (name: string, text: string) => `\u001b[${name === "error" ? "31" : name === "warning" ? "33" : name === "success" ? "32" : "36"}m${text}\u001b[39m`,
    bg: (name: string, text: string) => `\u001b[${name === "toolErrorBg" ? "41" : name === "toolPendingBg" ? "43" : "42"}m${text}\u001b[49m`,
    bold: (text: string) => `\u001b[1m${text}\u001b[22m`,
  };
  for (const state of [{ bg: "42", fg: "32" }, { isPartial: true, bg: "43", fg: "33" }, { isError: true, bg: "41", fg: "31" }]) {
    const component = renderComponent(surface, args, { ...payload, ...state, text: "Delivery failed", expanded: true }, styledTheme);
    const lines = component.render(90);
    assert.ok(lines.every((line) => line.startsWith(`\u001b[${state.bg}m`) && visibleWidth(line) <= 90));
    assert.ok(lines[1].includes(`\u001b[${state.fg}m`), `${surface}: status accent preserved`);
    if (!state.isError) assert.deepEqual(contentRows(component, 90), wrapTextWithAnsi(prefix + message, 88).map((line) => line.trimEnd()));
  }
}

// A real configured host keybinding, not a renderer-hardcoded ctrl+o string.
setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }, { "app.tools.expand": "ctrl+shift+e" }));
const remapped = renderComponent("leader:agent_event", { to: "reader", message: "Hidden message ".repeat(30) }, { details: { to: "reader", outcome: "steered" } });
assert.ok(contentRows(remapped, 90)[0].endsWith(" · ctrl+shift+e to expand"));
assert.ok(!contentRows(remapped, 90)[0].includes("ctrl+o"));

// Exercise the production incoming-report caller, without starting its session
// lifecycle or any worker. The native host wrapper owns mouse expansion.
const incoming = new Map<string, Parameters<ExtensionAPI["registerMessageRenderer"]>[1]>();
agentTeams({
  ...capture("incoming"),
  registerEntryRenderer: () => {},
  registerCommand: () => {},
  registerMessageRenderer: (name, renderer) => incoming.set(name, renderer),
} as ExtensionAPI);
const incomingRenderer = incoming.get("agent-teams-report");
assert.ok(incomingRenderer);
const report = incomingRenderer({
  customType: "agent-teams-report", content: "Full report body", display: true,
  details: { teammate: "continual-audit-close", body: "Full report body", timestamp: 1 },
}, { expanded: false, outputPad: 1 }, theme as never);
assert.ok(report);
for (const width of [48, 90, 240]) {
  assert.ok(contentRows(report, width)[0].endsWith(" · ctrl+shift+e to expand"), `incoming report hint missing at ${width}`);
}
assert.deepEqual(contentRows(report, 8), wrapTextWithAnsi(` · ${keyHint("app.tools.expand", "to expand")}`, 6).map((line) => stripVTControlCharacters(line).trimEnd()));
assert.equal(report.handleMouse?.({ type: "click", button: "left", x: 5, y: 1, width: 90, height: 3 })?.handled, true);
assert.ok(stripVTControlCharacters(report.render(90).join("\n")).includes("Full report body"));
assert.equal(report.handleMouse?.({ type: "click", button: "left", x: 5, y: 1, width: 90, height: 3 })?.handled, true);
assert.ok(contentRows(report, 90)[0].endsWith(" · ctrl+shift+e to expand"));

console.log("COORDINATION_ROWS_OK");
