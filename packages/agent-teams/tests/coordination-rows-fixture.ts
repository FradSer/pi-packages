/**
 * Contract for the human-facing coordination rows: names, subjects, and the
 * text the Leader typed — never a session, Work, or assignment identifier.
 */

import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { stripVTControlCharacters } from "node:util";
import { initTheme, keyHint, type ExtensionAPI, type ToolDefinition } from "@earendil-works/pi-coding-agent";
import { createStaticToolLifecycleResultRenderer } from "@fradser/pi-kit";
import { KeybindingsManager, setKeybindings, truncateToWidth, visibleWidth, wrapTextWithAnsi, type Component } from "@earendil-works/pi-tui";
import agentTeams from "../src/index.ts";
import { runAgentAction } from "../src/agent-actions.ts";
import { resolveWorkerTools } from "@fradser/pi-subagents";
import { WORKER_CAPABILITY_TOOLS } from "../src/capability-tools.ts";
import { clearSessionAgents, exactSessionRoute, registerAgentTool, registerSessionAgent, setAgentHost } from "@fradser/pi-subagents";

// Real geometry, supplied here because this fixture is the one that paints rows.
// The extension entries cannot: they are loaded by headless tests too, and
// importing pi-tui there executes theme code that throws outside a rendered
// session. Identity functions would render here and take the terminal down on a
// real repaint.
const rowRenderer = (spec: { createSpec: Parameters<typeof createStaticToolLifecycleResultRenderer>[0]["createSpec"] }) =>
  createStaticToolLifecycleResultRenderer({
    ...spec, fit: truncateToWidth, visibleWidth,
    wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
    expandHint: keyHint("app.tools.expand", "to expand"),
  });
import { registerLeaderTools } from "../src/tools.ts";
import { registerTaskTool } from "@fradser/pi-tasks";
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
      tools: resolveWorkerTools(input.definition?.tools ?? ["read", "bash"], WORKER_CAPABILITY_TOOLS),
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
// The `agent` tool is @fradser/pi-subagents'. It reaches the team spawn path by
// the coordinator publishing itself, so the row under test is the real tool's.
setAgentHost({
  // `runAgentAction` throws on refusal and returns a receipt carrying the exact
  // handle, so the host translates rather than reshaping.
  async start(request) {
    try {
      const receipt = await runAgentAction({
        action: "start",
        name: request.name,
        ...(request.prompt ? { prompt: request.prompt } : {}),
        ...(request.definition ? { definition: { ...request.definition, tools: request.definition.tools ?? ["read", "bash"] } } : {}),
        model: "anthropic/claude-sonnet-4-5",
      }, undefined, runtime as never) as unknown as { session: { id?: string } & Record<string, unknown> };
      const session = receipt.session?.id ?? receipt.session;
      if (!session) return { ok: false, error: "the team spawn returned no handle" };
      return { ok: true, session: String(session) };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
  },
  stop: (name, spawnId) => runtime.shutdownTeammateExact(name, spawnId),
});
registerAgentTool(capture("leader") as unknown as ExtensionAPI, { renderResult: rowRenderer } as never);
registerTaskTool(capture("leader") as unknown as ExtensionAPI, { renderResult: rowRenderer } as never);
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
// A real receipt from the real tool, so the row is rendered from what the tool
// actually returns rather than from a hand-built object.
const started = await tools.get("leader:agent").execute(
  "row",
  { action: "start", name: "ui-auditor", prompt: "Fix the spacing under the started row.\nCheck the widget too." },
  undefined,
  undefined,
  { cwd: process.cwd(), ui: {}, mode: "print" } as never,
);
assert.equal(started.details.outcome, "started", started.content[0].text);

const collapsed = render("leader:agent", { action: "start", name: "ui-auditor", prompt: "Fix the spacing under the started row.\nCheck the widget too." }, { details: started.details, text: started.content[0].text });
expectReadable(collapsed, "start row");
assert.match(collapsed, /Fix the spacing under the started row/);
assert.ok(!collapsed.includes("role ·"), `collapsed start row must stay one line:\n${collapsed}`);

const expanded = render("leader:agent", { action: "start", name: "ui-auditor", prompt: "Fix the spacing under the started row.\nCheck the widget too." }, { details: started.details, text: started.content[0].text, expanded: true });
expectReadable(expanded, "expanded start row");
for (const line of ["role · ui-auditor", "Check the widget too.", "model · anthropic/claude-sonnet-4-5", "tools · read, bash, message, task"]) {
  assert.ok(expanded.includes(line), `expanded start row missing "${line}":\n${expanded}`);
}
// A spawned child records no task and no resources: there is no task to hold a
// resource lease for. The row must not imply otherwise.
assert.ok(!expanded.includes("resources ·"), "a spawned child has no resource lease");
assert.ok(!expanded.includes("work ·"), "a spawn is not a work item");

// A kickoff prompt is the deliverable: expansion reveals every line, so no
// character cap may drop the tail of a long prompt. Driven through a real call,
// because the row projects from the result and cannot see the arguments.
const longPrompt = `Kickoff headline\n${"evidence ".repeat(400)}TAIL-EVIDENCE`;
resetState();
const longStart = await tools.get("leader:agent").execute(
  "row",
  { action: "start", name: "ui-auditor", prompt: longPrompt },
  undefined,
  undefined,
  { cwd: process.cwd(), ui: {}, mode: "print" } as never,
);
assert.equal(longStart.details.outcome, "started", longStart.content[0].text);
const longPromptRow = render("leader:agent", { action: "start", name: "ui-auditor", prompt: longPrompt }, { details: longStart.details, text: longStart.content[0].text, expanded: true });
expectReadable(longPromptRow, "long-prompt start row");
assert.ok(longPromptRow.includes("TAIL-EVIDENCE"), `expanded start row clipped a long prompt:\n${longPromptRow.slice(-400)}`);
assert.ok(longPromptRow.includes("Kickoff headline"), `expanded start row dropped the prompt headline:\n${longPromptRow.slice(0, 400)}`);

const handle = exactSessionRoute("ui-auditor", getTeammate("ui-auditor")!.spawnId);
// The status change comes first: a row renders the snapshot it was handed, so
// updating the roster afterwards would leave the row describing the previous
// state.
updateTeammate("ui-auditor", { status: "working", activeTool: "file: overlay.ts" });
const inspected = await tools.get("leader:agent").execute(
  "row",
  { action: "inspect", session: handle },
  undefined,
  undefined,
  { cwd: process.cwd(), ui: {}, mode: "print" } as never,
);
const inspectedRow = render("leader:agent", { action: "inspect", session: handle }, { details: inspected.details, text: inspected.content[0].text, expanded: true });
expectReadable(inspectedRow, "inspect row");
assert.match(inspectedRow, /@ui-auditor · working/);
assert.ok(inspectedRow.includes("now · file: overlay.ts"), `inspect row missing live activity:\n${inspectedRow}`);

updateTeammate("ui-auditor", { status: "idle", activeTool: undefined });
const idleInspected = await tools.get("leader:agent").execute(
  "row",
  { action: "inspect", session: handle },
  undefined,
  undefined,
  { cwd: process.cwd(), ui: {}, mode: "print" } as never,
);
const idleRow = render("leader:agent", { action: "inspect", session: handle }, { details: idleInspected.details, text: idleInspected.content[0].text, expanded: true });
assert.ok(!idleRow.includes("now ·"), `idle inspect row must not display a now activity:\n${idleRow}`);
assert.ok(!idleRow.includes("work ·"), `idle inspect row must not dump old work:\n${idleRow}`);
assert.ok(!idleRow.includes("status ·"), `inspect row must not repeat its own header state word:\n${idleRow}`);

// A coordination-only spawn states its narrow grant on the row that created it.
const narrowStarted = await tools.get("leader:agent").execute(
  "row",
  { action: "start", name: "row-check-narrow", prompt: "Answer with one word.",
    description: "Minimal probe", role_prompt: "Answer with one word.", tools: [] },
  undefined,
  undefined,
  { cwd: process.cwd(), ui: {}, mode: "print" } as never,
);
assert.equal(narrowStarted.details.outcome, "started", narrowStarted.content[0].text);
const narrowRow = render("leader:agent", { action: "start", name: "row-check-narrow", prompt: "Answer with one word." }, { details: narrowStarted.details, text: narrowStarted.content[0].text, expanded: true });
expectReadable(narrowRow, "coordination-only delegate row");
assert.ok(narrowRow.includes("tools · message, task"), `narrow delegate row missing its grant:\n${narrowRow}`);
assert.ok(narrowRow.includes("warning · coordination-only"), `narrow delegate row missing the coordination-only warning:\n${narrowRow}`);

const stopped = await runAgentAction({ action: "stop", session: handle }, undefined, runtime);
const stoppedRow = render("leader:agent", { action: "stop", session: handle }, { details: stopped, expanded: true });
expectReadable(stoppedRow, "stop row");
assert.ok(stoppedRow.includes("@ui-auditor · stopped"), `stop row missing plain state:\n${stoppedRow}`);
assert.ok(stoppedRow.includes("Agent @ui-auditor stopped."), `stop row missing the shutdown summary:\n${stoppedRow}`);
assert.ok(!stoppedRow.includes("work ·"), `stop row must not duplicate previous work:\n${stoppedRow}`);

// A real refusal, not a fabricated one. The old version cited a direct
// assignment and its work id, which is the capability that moved to the board
// with the work item; a spawn no longer creates either, so a row citing them
// would be testing a failure the tool cannot produce.
const refusedStart = await tools.get("leader:agent").execute(
  "row",
  { action: "start", name: "../escape" },
  undefined,
  undefined,
  { cwd: process.cwd(), ui: {}, mode: "print" } as never,
);
assert.equal(refusedStart.details.ok, false);
const failureRow = render("leader:agent", { action: "start", name: "../escape" }, { text: refusedStart.content[0].text, details: refusedStart.details, isError: true, expanded: true });
assert.ok(failureRow.includes("failed"), `failed row missing the plain state:\n${failureRow}`);
assert.ok(failureRow.includes("Invalid agent name"), `failed row dropped the reason:\n${failureRow}`);
expectReadable(failureRow, "failed row");

// ── work: subjects lead, identifiers stay model-facing ─────────────
const taskCreated = await tools.get("leader:task").execute(
  "row",
  { action: "create", subject: "Fix the spacing under the started row", resources: ["packages/context"] },
  undefined,
  undefined,
  { cwd: process.cwd(), ui: {}, mode: "print" } as never,
);
assert.equal(taskCreated.details.ok, true, taskCreated.content[0].text);
const createdRow = render("leader:task", { action: "create", subject: "Fix the spacing under the started row" }, {
  details: taskCreated.details,
  text: taskCreated.content[0].text,
  expanded: true,
});
assert.ok(createdRow.includes("Fix the spacing under the started row"), `task create row missing the subject:\n${createdRow}`);
// The old row carried a ROUTING line naming the residents that were notified.
// The board tool cannot know a resident exists, so it reports the next step
// instead; who was woken is the coordinator's business and is visible in the
// console. Asserting the guidance rather than a notification list keeps the
// boundary honest.
assert.ok(createdRow.includes("take it with update status=in_progress"),
  `task create row must state the next step rather than a routing list:\n${createdRow}`);
assert.ok(!/eligible residents notified/.test(createdRow),
  "the board tool must not claim to know which residents exist");
expectReadable(createdRow, "task create row");

// A held task, so the row has a holder to show. Taken by this session, which is
// the same thing any participant does.
await tools.get("leader:task").execute(
  "row",
  { action: "update", id: taskCreated.details.id, status: "in_progress" },
  undefined,
  undefined,
  { cwd: process.cwd(), ui: {}, mode: "print" } as never,
);
const taskListed = await tools.get("leader:task").execute(
  "row",
  { action: "list" },
  undefined,
  undefined,
  { cwd: process.cwd(), ui: {}, mode: "print" } as never,
);
const listedRow = render("leader:task", { action: "list" }, { details: taskListed.details, text: taskListed.content[0].text, expanded: true });
expectReadable(listedRow, "task list row");
assert.ok(listedRow.includes("Fix the spacing under the started row"), `task list row missing the subject:\n${listedRow}`);
assert.ok(listedRow.includes("· in_progress · @main"), `task list row missing state and holder:\n${listedRow}`);

// A long Work subject stays whole: the row fits it to the terminal and
// expansion reveals it, so no fixed character cap may cut it short.
const longSubject = `${"keep the widget aligned ".repeat(5)}TAIL-SUBJECT`.trim();
assert.ok(longSubject.length > 110, "the long-subject regression must exceed the removed 90-character cap");
const longCreated = await tools.get("leader:task").execute(
  "row",
  { action: "create", subject: longSubject },
  undefined,
  undefined,
  { cwd: process.cwd(), ui: {}, mode: "print" } as never,
);
assert.equal(longCreated.details.ok, true, longCreated.content[0].text);
const longCreatedRow = render("leader:task", { action: "create", subject: longSubject }, { details: longCreated.details, text: longCreated.content[0].text });
expectReadable(longCreatedRow, "long-subject task create row");
assert.ok(longCreatedRow.includes("TAIL-SUBJECT"), `collapsed work row clipped the subject at a fixed width:\n${longCreatedRow}`);
const longCreatedExpanded = render("leader:task", { action: "create", subject: longSubject }, {
  details: longCreated.details,
  text: longCreated.content[0].text,
  expanded: true,
});
assert.ok(longCreatedExpanded.includes(longSubject), `expanded work row lost the complete subject:\n${longCreatedExpanded}`);
const narrowLongRow = stripVTControlCharacters(renderComponent("leader:task", { action: "create", subject: longSubject }, {
  details: longCreated.details,
  text: longCreated.content[0].text,
}).render(80).join("\n"));
assert.ok(narrowLongRow.includes("to expand"), `a width-clipped subject must advertise expansion:\n${narrowLongRow}`);

// ── agent_event: the message itself, not the routing record ─────────

const messageRow = render("leader:message", { to: "@ui-auditor", body: "Also check the widget spacing, then report.", kind: "request" }, {
  details: { to: "ui-auditor", outcome: "sent", kind: "request" },
  text: `EVENT ROUTING · sent · to=@ui-auditor\nINTENT · request`,
  expanded: true,
});
expectReadable(messageRow, "message row");
assert.ok(messageRow.includes("to @ui-auditor"), `message row missing the recipient:\n${messageRow}`);
assert.ok(messageRow.includes("Also check the widget spacing, then report."), `message row missing the message text:\n${messageRow}`);
assert.ok(!messageRow.includes("EVENT ROUTING"), `message row still shows the routing record:\n${messageRow}`);

const workerMessageRow = render("worker:message", { body: "Done: spacing fixed and tests pass." }, {
  details: { to: "leader", outcome: "queued", kind: "inform" },
  text: "MESSAGING\nREPORT · to=leader · intent=inform",
  expanded: true,
});
expectReadable(workerMessageRow, "worker message row");
assert.ok(workerMessageRow.includes("Done: spacing fixed and tests pass."), `worker message row missing the report text:\n${workerMessageRow}`);

// ── worker work rows name the task, not the id ─────────────────────

const claimRow = render("worker:task", { action: "claim", id: taskCreated.details.id }, {
  details: { action: "claim", outcome: "queued", id: taskCreated.details.id, subject: "Fix the spacing under the started row", worker: "ui-auditor" },
  text: `WORK · current session\nCLAIM INTENT QUEUED · ${taskCreated.details.id} · Fix the spacing under the started row\nREQUESTER · @ui-auditor\nNEXT · wait for harness claim acceptance`,
  expanded: true,
});
expectReadable(claimRow, "worker claim row");
assert.ok(claimRow.includes("Fix the spacing under the started row · claim queued"), `worker claim row missing the subject:\n${claimRow}`);

const submitRow = render("worker:task", { action: "submit", outcome: "success" }, {
  details: { action: "submit", outcome: "queued", id: taskCreated.details.id, subject: "Fix the spacing under the started row", status: "success", verify: false },
  text: `WORK · current session\nSUBMISSION INTENT QUEUED · ${taskCreated.details.id} · success\nVERIFY · none configured\nNEXT · wait for the harness result`,
  expanded: true,
});
expectReadable(submitRow, "worker submit row");
assert.ok(submitRow.includes("Fix the spacing under the started row"), `worker submit row missing the owned task subject:\n${submitRow}`);

// Model-supplied arguments arrive untyped: rendering must degrade, not throw.
for (const hostile of [{ action: "delegate", name: "ui-auditor", prompt: 42 }, { action: "delegate", name: 7 }, { action: "inspect" }, {}]) {
  expectReadable(render("leader:agent", hostile, { details: started, expanded: true }), `row for ${JSON.stringify(hostile)}`);
}
for (const hostile of [{ to: 5, message: { text: "hi" } }, {}, { action: "create", subject: { a: 1 }, dependsOn: "work:x" }, { action: "list" }]) {
  expectReadable(render("leader:message", hostile, { details: { to: "ui-auditor", outcome: "sent" }, expanded: true }), `row for ${JSON.stringify(hostile)}`);
}

// A person's own identifier text is content, not a runtime handle: it survives.
const literal = render("leader:message", { to: "@ui-auditor", body: "Compare with 6d102f1b-cc16-4059-8d86-d5c1192f3776 in the log." }, {
  details: { to: "ui-auditor", outcome: "sent", kind: "inform" },
  text: "EVENT ROUTING · sent",
  expanded: true,
});
assert.ok(literal.includes("6d102f1b-cc16-4059-8d86-d5c1192f3776"), `message text lost written identifier:
${literal}`);

// ── registered message surfaces: terminal-width preview and inline expansion ──

for (const surface of ["leader:message", "worker:message"]) {
  const prefix = "[message] to @continual-audit-close · steered · ";
  const message = `Start marker: ${Array.from({ length: 32 }, (_, i) => `evidence-${i}`).join(" ")} END-MARKER`;
  const args = { to: "continual-audit-close", body: message };
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

  const exactRecipient = renderComponent(surface, { to: "session:reader:spawn-1", body: "Brief update." }, {});
  assert.deepEqual(contentRows(exactRecipient, 200), ["[message] to @reader · Brief update."], `${surface}: exact recipient route must remain model-only`);
  const prefixedRecipient = renderComponent(surface, { to: "@reader", body: "Brief update." }, {});
  assert.deepEqual(contentRows(prefixedRecipient, 200), ["[message] to @reader · Brief update."]);

  const shortMessage = "Brief update.";
  const short = renderComponent(surface, { ...args, body: shortMessage }, payload);
  assert.deepEqual(contentRows(short, 200), [prefix + shortMessage]);
  const notedPayload = { ...payload, details: { ...payload.details, terminalReport: "recorded result" } };
  const noted = renderComponent(surface, { ...args, body: shortMessage }, notedPayload);
  assert.deepEqual(contentRows(noted, 200), [prefix + shortMessage + hint]);
  const notedExpanded = renderComponent(surface, { ...args, body: shortMessage }, { ...notedPayload, expanded: true });
  assert.deepEqual(contentRows(notedExpanded, 200), [prefix + shortMessage, "note · terminal report recorded for this Work"]);

  // Full readback bypasses both the generic fifty-detail-line and field-size caps.
  const longMessage = Array.from({ length: 61 }, (_, index) => `line-${index}: ${"complete-message ".repeat(8)}`).join("\n") + "\n\nLAST-PARAGRAPH";
  const longExpanded = renderComponent(surface, { ...args, body: longMessage }, { ...payload, expanded: true });
  assert.deepEqual(contentRows(longExpanded, 90), wrapTextWithAnsi(prefix + longMessage, 88).map((line) => line.trimEnd()));
  const semanticMessage = "First line\n\nSecond line\n  indented third line";
  assert.deepEqual(contentRows(renderComponent(surface, { ...args, body: semanticMessage }, { ...payload, expanded: true }), 200),
    [prefix + "First line", "", "Second line", "  indented third line"]);

  const literalMessage = 'Preserve this JSON: {"value":""}\nLiteral spacing: alpha ; beta !\nTwo quoted lines: "\n"';
  for (const width of [48, 90, 240]) {
    const literalRows = contentRows(renderComponent(surface, { ...args, body: literalMessage }, { ...payload, expanded: true }), width);
    assert.deepEqual(literalRows, wrapTextWithAnsi(prefix + literalMessage, width - 2).map((line) => line.trimEnd()),
      `${surface}: expanded literal syntax must survive without prose cleanup at ${width}`);
  }

  // A hostile message: an OSC title, colour, a combining accent, and identifier
  // shapes. The property is that none of it survives into the row as an
  // identifier, and that the text still wraps. Pinning the exact replacement
  // wording would test the sanitiser's phrasing rather than its guarantee, and
  // an unknown identifier resolving to a subject is a detail that moves when the
  // board's id shape does.
  const decorated = "\u001b]0;bad-title\u0007\u001b[31m检查终端宽度\u001b[0m cafe\u0301 界界界 ".repeat(18)
    + "session:reader:spawn-1 work:9f1b7c22-0a4d-4f1e-9c33-2f0a5d7b1e64 direct:6d102f1b-cc16-4059-8d86-d5c1192f3776 its assignment";
  for (const width of [48, 90, 240]) {
    const unicodeRows = contentRows(renderComponent(surface, { ...args, body: decorated }, { ...payload, expanded: true }), width);
    const joined = unicodeRows.join("\n");
    expectReadable(joined, `${surface}: Unicode message`);
    assert.ok(!joined.includes("bad-title"), "an OSC title must not survive into the row");
    assert.ok(!NO_IDENTIFIER.test(joined), `identifiers must not survive: ${joined}`);
    // The prose itself is preserved, so the row is still readable as a message.
    assert.ok(joined.includes("its assignment"), `the message text was dropped: ${joined}`);
    // A clipped row advertises expansion rather than silently truncating.
    const collapsedRows = contentRows(renderComponent(surface, { ...args, body: decorated }, payload), width);
    assert.equal(collapsedRows.length, 1, `collapsed row must be one line: ${collapsedRows.join("\n")}`);
    assert.ok(collapsedRows[0].includes("to expand"), `a clipped message must advertise expansion: ${collapsedRows[0]}`);
  }

  const hyperlink = "Open \u001b]8;;https://example.test\u001b\\LINK-LABEL\u001b]8;;\u001b\\ after.";
  for (const width of [48, 90, 240]) {
    const linkedRows = contentRows(renderComponent(surface, { ...args, body: hyperlink }, { ...payload, expanded: true }), width);
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
const remapped = renderComponent("leader:message", { to: "reader", body: "Hidden message ".repeat(30) }, { details: { to: "reader", outcome: "steered" } });
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
