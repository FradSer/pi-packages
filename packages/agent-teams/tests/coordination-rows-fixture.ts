/**
 * Contract for the human-facing coordination rows: names, subjects, and the
 * text the Leader typed — never a session, Work, or assignment identifier.
 */

import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { stripVTControlCharacters } from "node:util";
import { initTheme, keyHint, type ExtensionAPI, type ToolDefinition } from "@earendil-works/pi-coding-agent";
import { createStaticToolLifecycleResultRenderer } from "@fradser/pi-kit";
import { KeybindingsManager, setKeybindings, truncateToWidth, visibleWidth, wrapTextWithAnsi, type Component } from "@earendil-works/pi-tui";
import teamRuntime from "../src/index.ts";
import { runAgentAction } from "../src/agent-actions.ts";
import { resolveAgentTools } from "@fradser/pi-subagents";
import { WORKER_CAPABILITY_TOOLS } from "../src/capability-tools.ts";
import { clearSessionAgents, exactSessionRoute, executeChildIntent, registerIntentTools, setAgentHost } from "@fradser/pi-subagents";

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
import { registerTaskTools } from "@fradser/pi-tasks";
import { registerChildCapabilities } from "../src/worker.ts";
import {
  createTask,
  getAgent,
  registerAgent,
  resetState,
  updateAgent,
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
  spawnAgent(input: any) {
    const agent = {
      name: input.name,
      agent: input.agent,
      spawnId: randomUUID(),
      workId: input.workId,
      status: "starting" as const,
      pid: 4242,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    registerAgent({ ...agent, assignment: input.prompt ? { id: `direct:${randomUUID()}`, kind: "direct", resources: input.resources ?? [] } : undefined });
    updateAgent(input.name, {
      model: input.model ?? "anthropic/claude-sonnet-4-5",
      // Honor the requested grant so a coordination-only spawn renders the same
      // narrow Tools and Warning lines the real receipt produces.
      tools: resolveAgentTools(input.definition?.tools ?? ["read", "bash"], WORKER_CAPABILITY_TOOLS),
      ...(input.prompt ? {} : { assignment: undefined }),
    });
    return { ok: true as const, agent: getAgent(input.name)! };
  },
  async shutdownAgentExact(_name: string, _spawnId: string) {
    return { ok: true as const, body: `Agent @${_name} stopped. Work returned to pending.` };
  },
  sendLeaderMessage: () => ({ ok: true as const, outcome: "sent" }),
};
registerLeaderTools(capture("leader") as unknown as ExtensionAPI, runtime as never);
// The intent family is @fradser/pi-subagents'. It reaches the team spawn path by
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
  // Row-only host still declares the public control seam; no process is driven.
  send: async () => ({ ok: false, error: "Row fixture has no native child" }),
  interrupt: async () => ({ ok: false, error: "Row fixture has no native child" }),
  stop: (name, spawnId) => runtime.shutdownAgentExact(name, spawnId),
});
registerIntentTools(capture("leader") as unknown as ExtensionAPI, { renderResult: rowRenderer } as never);
registerTaskTools(capture("leader") as unknown as ExtensionAPI, { renderResult: rowRenderer } as never);
registerChildCapabilities(capture("worker") as unknown as ExtensionAPI);

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

/** The intent tool each child operation belongs to, so a row renders through the
 *  same registration a caller would use. */
const childTool = (operation: string): ToolDefinition => {
  const name = operation === "input" || operation === "steer" ? "agent_input"
    : operation === "stop" ? "agent_stop"
    : operation === "list" ? "agent_list" : "agent_start";
  const tool = tools.get(`leader:${name}`);
  assert.ok(tool, `the leader registers ${name}`);
  return tool;
};
const callChild = (request: { operation?: string; name?: string; identity?: string; session?: string; prompt?: string; tools?: string[] }, ctx: unknown) => {
  const { operation, name, identity, session, prompt, tools: grant } = request;
  const name2 = operation === "input" || operation === "steer" ? "agent_input"
    : operation === "stop" ? "agent_stop"
    : operation === "list" ? "agent_list" : "agent_start";
  // A roster read is a page of the whole roster, so it takes no session handle.
  const params = name2 === "agent_start"
    ? { prompt: prompt ?? "Start the assigned work.", ...(identity === undefined ? {} : { identity }), ...(name === undefined ? {} : { label: name }), ...(grant === undefined ? {} : { tools: grant }) }
    : name2 === "agent_input" ? { session: session!, prompt: prompt!, delivery: operation === "steer" ? "steer" : "next" }
    : name2 === "agent_list" ? {} : { session };
  return childTool(operation ?? "start").execute("row", params, undefined, undefined, ctx);
};

function render(key: string, args: Record<string, unknown>, payload: RenderPayload): string {
  return stripVTControlCharacters(renderComponent(key, args, payload).render(200).join("\n"));
}

function contentRows(component: Component, width: number): string[] {
  const lines = component.render(width);
  assert.ok(lines.every((line) => visibleWidth(line) <= width), `row exceeds ${width} display columns:\n${lines.join("\n")}`);
  return lines.slice(1, -1).map((line) => stripVTControlCharacters(line).slice(1).trimEnd());
}

const HANDLE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|session:/i;
const COORDINATION_ID = /work:|direct:/i;
const SESSION_ROUTE = /session:/i;

/** A collapsed row addresses nobody, and never shows an exact handle. Expansion is
 *  where `session ·` and `input ·` live, so there the rule is that no coordination
 *  identifier from another package leaks in. */
function expectReadable(row: string, label: string, expanded = false): void {
  assert.ok(!(expanded ? COORDINATION_ID : HANDLE).test(row), `${label} leaked an identifier:\n${row}`);
}

// ── child control: start, roster, stop, failure ───────────────

// The intent family mints the roster name and shows a label. The two are
// different facts, so every roster lookup below resolves the generated name and
// every row reads the label.
const projectRoot = fs.mkdtempSync(path.join(os.tmpdir(), "coordination-rows-"));
const toolCtx = { cwd: projectRoot, ui: {}, mode: "print" } as never;

// A real receipt from the real tool, so the row is rendered from what the tool
// actually returns rather than from a hand-built object.
const kickoff = "Fix the spacing under the started row.\nCheck the widget too.";
const started = await callChild({ operation: "start", name: "ui-auditor", prompt: kickoff, tools: ["read", "bash"] }, toolCtx);
assert.equal(started.details.operation, "agent_start");
assert.equal(started.details.disposition, "started", started.content[0].text);
assert.equal(started.details.label, "ui-auditor", "the label is the display claim");
const rosterName = started.details.name as string;
assert.match(rosterName, /^subagent-[0-9a-f]+$/, `a start must mint its roster name, got ${rosterName}`);
assert.equal(started.details.session, exactSessionRoute(rosterName, getAgent(rosterName)!.spawnId));

const collapsed = render("leader:agent_start", { prompt: kickoff, label: "ui-auditor" }, { details: started.details, text: started.content[0].text });
expectReadable(collapsed, "start row");
assert.match(collapsed, /\[agent\] started · @ui-auditor · starting/);
assert.match(collapsed, /Fix the spacing under the started row/);
assert.ok(!collapsed.includes("role ·"), `collapsed start row must stay one line:\n${collapsed}`);

const expanded = render("leader:agent_start", { prompt: kickoff, label: "ui-auditor" }, { details: started.details, text: started.content[0].text, expanded: true });
expectReadable(expanded, "expanded start row", true);
// A temporary role's description is its label, so the role line names what the
// child is for. What it must never carry is the minted roster name: the subject
// already shows the child, and a name repeated there spends the one place a row
// has for meaning on what the line above it already said.
for (const line of ["role · ui-auditor", "Check the widget too.", "model · anthropic/claude-sonnet-4-5", "tools · read, bash, message, task"]) {
  assert.ok(expanded.includes(line), `expanded start row missing "${line}":\n${expanded}`);
}
assert.ok(!/role · subagent-/.test(expanded), `role line repeated the minted roster name:\n${expanded}`);
// A spawned child records no task and no resources: there is no task to hold a
// resource lease for. The row must not imply otherwise.
assert.ok(!expanded.includes("resources ·"), "a spawned child has no resource lease");
assert.ok(!expanded.includes("work ·"), "a spawn is not a work item");

// A kickoff prompt is the deliverable: expansion reveals every line, so no
// character cap may drop the tail of a long prompt. Driven through a real call,
// because the row projects from the result and cannot see the arguments.
const longPrompt = `Kickoff headline\n${"evidence ".repeat(400)}TAIL-EVIDENCE`;
resetState();
const longStart = await callChild({ operation: "start", name: "ui-auditor", prompt: longPrompt, tools: ["read", "bash"] }, toolCtx);
assert.equal(longStart.details.operation, "agent_start");
assert.equal(longStart.details.disposition, "started", longStart.content[0].text);
const longPromptRow = render("leader:agent_start", { prompt: longPrompt, label: "ui-auditor" }, { details: longStart.details, text: longStart.content[0].text, expanded: true });
expectReadable(longPromptRow, "long-prompt start row", true);
assert.ok(longPromptRow.includes("TAIL-EVIDENCE"), `expanded start row clipped a long prompt:\n${longPromptRow.slice(-400)}`);
assert.ok(longPromptRow.includes("Kickoff headline"), `expanded start row dropped the prompt headline:\n${longPromptRow.slice(0, 400)}`);

const longRosterName = longStart.details.name as string;
const handle = exactSessionRoute(longRosterName, getAgent(longRosterName)!.spawnId);
// The status change comes first: a row renders the snapshot it was handed, so
// updating the roster afterwards would leave the row describing the previous
// state.
updateAgent(longRosterName, { status: "working", activeTool: "file: overlay.ts" });
// ADR-0008 left no inspect row. The roster row names no child and, because this
// page omitted nothing, no count: a page has no state of its own, and one child's
// state never becomes the subject's. Per-child facts appear only after expansion.
const working = await callChild({ operation: "list" }, toolCtx);
assert.equal(working.details.operation, "agent_list");
assert.equal(working.details.disposition, "listed", working.content[0].text);
const rosterCollapsed = render("leader:agent_list", {}, { details: working.details, text: working.content[0].text });
expectReadable(rosterCollapsed, "roster row");
assert.match(rosterCollapsed, /\[agent\] listed/, rosterCollapsed);
assert.ok(!/\d+ of \d+/.test(rosterCollapsed), `a complete page carries no count:\n${rosterCollapsed}`);
assert.ok(!/@ui-auditor · working/.test(rosterCollapsed),
  `a roster subject carries no child's state:\n${rosterCollapsed}`);
const rosterRow = render("leader:agent_list", {}, { details: working.details, text: working.content[0].text, expanded: true });
expectReadable(rosterRow, "roster row", true);
assert.ok(rosterRow.includes("active tool · file: overlay.ts"), `roster row missing live activity:\n${rosterRow}`);
assert.ok(rosterRow.includes("@ui-auditor · working"), `roster row missing the per-child header:\n${rosterRow}`);

updateAgent(longRosterName, { status: "idle", activeTool: undefined });
const idleListing = await callChild({ operation: "list" }, toolCtx);
const idleRow = render("leader:agent_list", {}, { details: idleListing.details, text: idleListing.content[0].text, expanded: true });
assert.ok(!idleRow.includes("active tool ·"), `idle roster row must not display a live activity:\n${idleRow}`);
assert.ok(!idleRow.includes("work ·"), `idle roster row must not dump old work:\n${idleRow}`);
// The per-child header carries the state word, so the block below it must not
// add a second one for the same row.
const idleLines = idleRow.split("\n").map((line) => line.trim());
assert.equal(idleLines.filter((line) => line === "@ui-auditor · idle").length, 1,
  `roster row must carry the child's state in its per-child header exactly once:\n${idleRow}`);
assert.ok(!idleRow.includes("status · idle"), `roster row repeated the state word under its header:\n${idleRow}`);
assert.equal(idleRow.match(/@ui-auditor · idle/g)?.length, 1,
  `the collapsed subject is the page, so the state is named only in the header:\n${idleRow}`);

// A coordination-only spawn states its narrow grant on the row that created it.
const narrowStarted = await callChild({ operation: "start", name: "row-check-narrow", prompt: "Answer with one word.", tools: [] }, toolCtx);
assert.equal(narrowStarted.details.operation, "agent_start");
assert.equal(narrowStarted.details.disposition, "started", narrowStarted.content[0].text);
const narrowRow = render("leader:agent_start", { prompt: "Answer with one word.", label: "row-check-narrow" }, { details: narrowStarted.details, text: narrowStarted.content[0].text, expanded: true });
expectReadable(narrowRow, "coordination-only delegate row", true);
// An empty request is coordination-only. The row names exactly what the roster
// recorded, and promises no file or shell tool the caller did not ask for.
assert.ok(narrowRow.includes("tools · message, task"), `coordination-only delegate row missing its grant:\n${narrowRow}`);
for (const capability of ["read", "bash", "grep", "find", "ls"]) {
  assert.ok(!new RegExp(`\\b${capability}\\b`).test(narrowRow), `coordination-only delegate row promised ${capability}:\n${narrowRow}`);
}

const stopped = await callChild({ operation: "stop", session: handle }, toolCtx);
assert.equal(stopped.details.operation, "agent_stop");
assert.equal(stopped.details.disposition, "stopped", stopped.content[0].text);
const stoppedRow = render("leader:agent_stop", { session: handle }, { details: stopped.details, text: stopped.content[0].text, expanded: true });
expectReadable(stoppedRow, "stop row", true);
assert.ok(stoppedRow.includes("[agent] stopped · @ui-auditor"), `stop row missing plain state:\n${stoppedRow}`);
assert.ok(stoppedRow.includes("note · Completion belongs to the child result or task record."), `stop row missing the completion note:\n${stoppedRow}`);
assert.ok(!stoppedRow.includes("work ·"), `stop row must not duplicate previous work:\n${stoppedRow}`);

// A real refusal, not a fabricated one. A spawned child no longer creates an
// assignment or its work id, so a row citing them would test a failure the tool
// cannot produce. The name guard is what remains, and an authoring caller
// reaches it through `identity`; the executor keeps the same check for the
// coordinator that does choose roster names.
const refusedStart = await callChild({ operation: "start", identity: "../escape", prompt: "Escape the roster." }, toolCtx);
assert.equal(refusedStart.details.ok, false);
assert.equal(refusedStart.details.disposition, "rejected");
const failureRow = render("leader:agent_start", { identity: "../escape", prompt: "Escape the roster." }, { text: refusedStart.content[0].text, details: refusedStart.details, isError: true, expanded: true });
assert.ok(failureRow.includes("rejected"), `failed row missing the plain state:\n${failureRow}`);
// The strict validator reports the name's actual requirement, not an echo.
assert.ok(failureRow.includes('Parameter "name" must start with a letter'), `failed row dropped the reason:\n${failureRow}`);
expectReadable(failureRow, "failed row", true);
const escapeName = await executeChildIntent({ operation: "start", name: "../escape", prompt: "Escape the roster." }, { cwd: projectRoot });
assert.equal(escapeName.structuredContent.ok, false);
assert.equal(escapeName.structuredContent.operation, "start");
assert.match(escapeName.content[0].text, /Parameter "name" must start with a letter/,
  `the executor's own name guard must still reject an escape:\n${escapeName.content[0].text}`);

// ── work: subjects lead, identifiers stay model-facing ─────────────
const taskCreated = await tools.get("leader:create_task").execute(
  "row",
  { subject: "Fix the spacing under the started row", resources: ["packages/context"] },
  undefined,
  undefined,
  { cwd: process.cwd(), ui: {}, mode: "print" } as never,
);
assert.equal(taskCreated.details.ok, true, taskCreated.content[0].text);
const createdRow = render("leader:create_task", { subject: "Fix the spacing under the started row" }, {
  details: taskCreated.details,
  text: taskCreated.content[0].text,
  expanded: true,
});
assert.ok(createdRow.includes("Fix the spacing under the started row"), `task create row missing the subject:\n${createdRow}`);
// The old row carried a ROUTING line naming the residents that were notified.
// The task tools cannot know a participant exists, and the row carries no
// notification list. It also used to end with a "NEXT · take it with update
// status=in_progress" line, which was model-facing call syntax painted into a
// transcript a person reads; that went with the single-tool surface, and how to
// spell the next call lives in each tool's declared description. So a creation
// row is its headline and nothing else: the work, and the state it is in.
assert.ok(!/take it with|status=in_progress/.test(createdRow),
  `a creation row must not carry model-facing call syntax:\n${createdRow}`);
assert.ok(!/ROUTING|notified/.test(createdRow),
  `a creation row must not carry a notification list:\n${createdRow}`);

assert.ok(!/eligible residents notified/.test(createdRow),
  "the tasks tool must not claim to know which residents exist");
expectReadable(createdRow, "task create row");

// A held task, so the row has state to show. Taken by this session, which is the
// same thing any participant does. Ownership stays in the structured result and
// the persisted data; the row itself names no holder.
await tools.get("leader:update_task").execute(
  "row",
  { id: taskCreated.details.id, status: "in_progress" },
  undefined,
  undefined,
  { cwd: process.cwd(), ui: {}, mode: "print" } as never,
);
const taskListed = await tools.get("leader:list_tasks").execute(
  "row",
  {},
  undefined,
  undefined,
  { cwd: process.cwd(), ui: {}, mode: "print" } as never,
);
const listedRow = render("leader:list_tasks", {}, { details: taskListed.details, text: taskListed.content[0].text, expanded: true });
expectReadable(listedRow, "task list row");
assert.ok(listedRow.includes("Fix the spacing under the started row"), `task list row missing the subject:\n${listedRow}`);
assert.ok(listedRow.includes("(in progress)"), `task list row missing state:\n${listedRow}`);
assert.ok(!listedRow.includes("@main"), `task list row must not name a holder:\n${listedRow}`);

// A long Work subject stays whole: the row fits it to the terminal and
// expansion reveals it, so no fixed character cap may cut it short.
const longSubject = `${"keep the widget aligned ".repeat(5)}TAIL-SUBJECT`.trim();
assert.ok(longSubject.length > 110, "the long-subject regression must exceed the removed 90-character cap");
const longCreated = await tools.get("leader:create_task").execute(
  "row",
  { subject: longSubject },
  undefined,
  undefined,
  { cwd: process.cwd(), ui: {}, mode: "print" } as never,
);
assert.equal(longCreated.details.ok, true, longCreated.content[0].text);
const longCreatedRow = render("leader:create_task", { subject: longSubject }, { details: longCreated.details, text: longCreated.content[0].text });
expectReadable(longCreatedRow, "long-subject task create row");
assert.ok(longCreatedRow.includes("TAIL-SUBJECT"), `collapsed work row clipped the subject at a fixed width:\n${longCreatedRow}`);
const longCreatedExpanded = render("leader:create_task", { subject: longSubject }, {
  details: longCreated.details,
  text: longCreated.content[0].text,
  expanded: true,
});
assert.ok(longCreatedExpanded.includes(longSubject), `expanded work row lost the complete subject:\n${longCreatedExpanded}`);
const narrowLongRow = stripVTControlCharacters(renderComponent("leader:create_task", { subject: longSubject }, {
  details: longCreated.details,
  text: longCreated.content[0].text,
}).render(80).join("\n"));
assert.ok(!narrowLongRow.includes("to expand"), `Task titles are complete by default:\n${narrowLongRow}`);
assert.ok(narrowLongRow.includes("TAIL-SUBJECT"), `default Task title lost its tail:\n${narrowLongRow}`);

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

const teammateMessageRow = render("worker:message", { body: "Done: spacing fixed and tests pass." }, {
  details: { to: "leader", outcome: "queued", kind: "inform" },
  text: "MESSAGING\nREPORT · to=leader · intent=inform",
  expanded: true,
});
expectReadable(teammateMessageRow, "agent message row");
assert.ok(teammateMessageRow.includes("Done: spacing fixed and tests pass."), `agent message row missing the report text:\n${teammateMessageRow}`);

// ── agent work rows name the task, not the id ─────────────────────

const claimRow = render("worker:task", { action: "claim", id: taskCreated.details.id }, {
  details: { action: "claim", outcome: "queued", id: taskCreated.details.id, subject: "Fix the spacing under the started row", agent: "ui-auditor" },
  text: `WORK · current session\nCLAIM INTENT QUEUED · ${taskCreated.details.id} · Fix the spacing under the started row\nREQUESTER · @ui-auditor\nNEXT · wait for harness claim acceptance`,
  expanded: true,
});
expectReadable(claimRow, "agent claim row");
assert.ok(claimRow.includes("Fix the spacing under the started row · claim queued"), `agent claim row missing the subject:\n${claimRow}`);

const submitRow = render("worker:task", { action: "submit", outcome: "success" }, {
  details: { action: "submit", outcome: "queued", id: taskCreated.details.id, subject: "Fix the spacing under the started row", status: "success", verify: false },
  text: `WORK · current session\nSUBMISSION INTENT QUEUED · ${taskCreated.details.id} · success\nVERIFY · none configured\nNEXT · wait for the harness result`,
  expanded: true,
});
expectReadable(submitRow, "agent submit row");
assert.ok(submitRow.includes("Fix the spacing under the started row"), `agent submit row missing the owned task subject:\n${submitRow}`);

// Model-supplied arguments arrive untyped: rendering must degrade, not throw.
for (const hostile of [{ prompt: 42 }, { unknown: 7 }, { label: { a: 1 } }, { prompt: "x", tools: "read" }, { prompt: "x", delivery: "nope" }, {}]) {
  expectReadable(render("leader:agent_start", hostile, { details: started.details, text: started.content[0].text }), `row for ${JSON.stringify(hostile)}`);
}
for (const hostile of [{ to: 5, message: { text: "hi" } }, {}, { action: "create", subject: { a: 1 }, dependsOn: "work:x" }, { operation: "list" }]) {
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
  // tasks's id shape does.
  const decorated = "\u001b]0;bad-title\u0007\u001b[31m检查终端宽度\u001b[0m cafe\u0301 界界界 ".repeat(18)
    + "session:reader:spawn-1 work:9f1b7c22-0a4d-4f1e-9c33-2f0a5d7b1e64 direct:6d102f1b-cc16-4059-8d86-d5c1192f3776 its assignment";
  for (const width of [48, 90, 240]) {
    const unicodeRows = contentRows(renderComponent(surface, { ...args, body: decorated }, { ...payload, expanded: true }), width);
    const joined = unicodeRows.join("\n");
    expectReadable(joined, `${surface}: Unicode message`);
    assert.ok(!joined.includes("bad-title"), "an OSC title must not survive into the row");
    // A message body is authored text, and pi-kit scrubs the handles it can resolve:
    // `session:<name>:<id>` becomes `@name`. A bare `work:` or `direct:` id is what the
    // author wrote, and the row preserves it; forbidding it here would test a
    // sanitiser that does not exist. Coordination identifiers are still checked where
    // the package itself authors the row, through `expectReadable`.
    assert.ok(!SESSION_ROUTE.test(joined), `a session handle must not survive: ${joined}`);
    assert.ok(!joined.includes("session:"), `a session route must not survive: ${joined}`);
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
// lifecycle or any agent. The native host wrapper owns mouse expansion.
const incoming = new Map<string, Parameters<ExtensionAPI["registerMessageRenderer"]>[1]>();
teamRuntime({
  ...capture("incoming"),
  registerEntryRenderer: () => {},
  registerCommand: () => {},
  registerMessageRenderer: (name, renderer) => incoming.set(name, renderer),
} as ExtensionAPI);
const incomingRenderer = incoming.get("agent-teams-report");
assert.ok(incomingRenderer);
const report = incomingRenderer({
  customType: "agent-teams-report", content: "Full report body", display: true,
  details: { agent: "continual-audit-close", body: "Full report body", timestamp: 1 },
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


// Every renderer a registered tool exposes must hand back a component, not
// undefined. Pi builds a container and a mouse region over the call and result
// components, so an undefined one surfaces as MouseRegion reading render of
// undefined on the first real repaint. `--print` never paints, so an offline run
// cannot see it: asserting on the returned value is the only place this is
// catchable, which is why it is asserted here rather than left to a TUI session.
{
  const fakeResult = { content: [{ type: "text" as const, text: "x" }], details: {} };
  const options = { expanded: false, isPartial: false };
  for (const [key, tool] of tools) {
    for (const [name, render] of [["renderCall", tool.renderCall], ["renderResult", tool.renderResult]] as const) {
      if (typeof render !== "function") continue;
      const component = (render as (...args: unknown[]) => unknown)(fakeResult, options, theme, { args: {}, isError: false });
      assert.ok(component && typeof component === "object", `${key}:${name} returned ${component}`);
      const shape = component as { render?: unknown; invalidate?: unknown };
      assert.equal(typeof shape.render, "function", `${key}:${name} has no render()`);
      assert.equal(typeof shape.invalidate, "function", `${key}:${name} has no invalidate()`);
      const lines = shape.render(80);
      assert.ok(Array.isArray(lines), `${key}:${name}.render() must return an array`);
    }
  }
}

console.log("COORDINATION_ROWS_OK");
