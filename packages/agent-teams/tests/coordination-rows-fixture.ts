/**
 * Contract for the human-facing coordination rows: names, subjects, and the
 * text the Leader typed — never a session, Work, or assignment identifier.
 */

import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { stripVTControlCharacters } from "node:util";
import { initTheme, type ExtensionAPI, type ToolDefinition } from "@earendil-works/pi-coding-agent";
import { runAgentAction } from "../src/agent-actions.ts";
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
      tools: ["read", "bash", "agent_event", "work"],
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

function render(
  key: string,
  args: Record<string, unknown>,
  payload: { details?: unknown; text?: string; isError?: boolean; expanded?: boolean; isPartial?: boolean },
): string {
  const tool = tools.get(key);
  assert.ok(tool?.renderResult, `${key} has no result renderer`);
  const component = tool.renderResult(
    { content: [{ type: "text", text: payload.text ?? JSON.stringify(payload.details) }], details: payload.details },
    { expanded: payload.expanded ?? false, isPartial: payload.isPartial ?? false },
    theme as never,
    { args, toolCallId: `call-${key}`, isError: payload.isError } as never,
  );
  return stripVTControlCharacters(component.render(200).join("\n"));
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

const handle = started.session.id;
const working = runAgentAction({ action: "inspect", name: "ui-auditor", session: handle }, undefined, runtime);
updateTeammate("ui-auditor", { status: "working", activeTool: "file: overlay.ts" });
const inspected = render("leader:agent", { action: "inspect", name: "ui-auditor", session: handle }, { details: working, expanded: true });
expectReadable(inspected, "inspect row");
assert.match(inspected, /@ui-auditor · working/);
assert.ok(inspected.includes("now · file: overlay.ts"), `inspect row missing live activity:\n${inspected}`);

const stopped = await runAgentAction({ action: "stop", session: handle }, undefined, runtime);
const stoppedRow = render("leader:agent", { action: "stop", session: handle }, { details: stopped, expanded: true });
expectReadable(stoppedRow, "stop row");
assert.ok(stoppedRow.includes("@ui-auditor · stopped"), `stop row missing plain state:\n${stoppedRow}`);
assert.ok(stoppedRow.includes("Agent @ui-auditor stopped."), `stop row missing the shutdown summary:\n${stoppedRow}`);

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

console.log("COORDINATION_ROWS_OK");
