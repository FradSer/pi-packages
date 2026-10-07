/**
 * Live TUI rows: the blocking research row and the /goal procedure row.
 *
 * Drives only pre-existing entry points (GoalCore, registerGoalTools,
 * goalExtension, goalRequest), so the same file RED-fails on a pristine tree
 * and passes with the feature. No static import of the new modules: the
 * procedure row is observed through sendMessage plus the registered message
 * renderer, and the absence of a research widget through the host's setWidget
 * calls.
 */
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { GoalCore } from "../src/core.ts";
import { registerGoalTools } from "../src/tools.ts";
import goalExtension from "../src/index.ts";
import { goalRequest } from "../src/prompt.ts";

const PROCEDURE_TYPE = "goal-procedure";
/** The row research used to mount. Research blocks, so it must never appear. */
const RESEARCH_KEY = "goal-research";

const results: string[] = [];
async function scenario(name: string, body: () => Promise<void> | void): Promise<void> {
  try {
    await body();
    results.push(`ok ${name}`);
  } catch (error) {
    results.push(`FAIL ${name}: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}

const roots: string[] = [];
function tempRoot(prefix: string): string {
  const root = mkdtempSync(join(tmpdir(), prefix));
  roots.push(root);
  return root;
}

/** Minimal host double. Records every surface the runtime can reach. */
function makeHost() {
  const commands = new Map<string, { handler: (args: string, ctx: unknown) => Promise<void> }>();
  const tools = new Map<string, { execute: (...args: unknown[]) => Promise<unknown> }>();
  const handlers = new Map<string, ((event: unknown, ctx: unknown) => Promise<unknown>)[]>();
  const sent: { message: unknown; options: unknown }[] = [];
  const userSent: unknown[] = [];
  const renderers = new Map<string, (message: unknown, options: unknown, theme: unknown) => { render(width: number): string[] }>();
  const pi = {
    registerCommand: (name: string, spec: { handler: (args: string, ctx: unknown) => Promise<void> }) => { commands.set(name, spec); },
    registerTool: (tool: { name: string; execute: (...args: unknown[]) => Promise<unknown> }) => { tools.set(tool.name, tool); },
    on: (event: string, handler: (event: unknown, ctx: unknown) => Promise<unknown>) => {
      const list = handlers.get(event) ?? [];
      list.push(handler);
      handlers.set(event, list);
    },
    sendMessage: (message: unknown, options: unknown) => { sent.push({ message, options }); },
    sendUserMessage: (content: unknown) => { userSent.push(content); },
    appendEntry: () => {},
    registerMessageRenderer: (
      type: string,
      fn: (message: unknown, options: unknown, theme: unknown) => { render(width: number): string[] },
    ) => { renderers.set(type, fn); },
    setActiveTools: () => {},
    getActiveTools: () => [] as string[],
  };
  return { commands, tools, handlers, sent, userSent, renderers, pi };
}

interface WidgetMount { key: string; factory: unknown; options: unknown }

/** TUI-mode context capturing every widget call with its placement. */
function makeTuiCtx(root: string, session = "live-session") {
  const mounts: WidgetMount[] = [];
  const live = new Map<string, { factory: unknown; options: unknown }>();
  const notifications: string[] = [];
  const ui = {
    setWidget: (key: string, factory: unknown, options?: unknown) => {
      mounts.push({ key, factory, options });
      if (factory === undefined) live.delete(key);
      else live.set(key, { factory, options });
    },
    notify: (line: string) => { notifications.push(line); },
  };
  const ctx = {
    mode: "tui",
    cwd: root,
    hasUI: true,
    isIdle: () => true,
    hasPendingMessages: () => false,
    sessionManager: { getSessionId: () => session, getBranch: () => [] as unknown[] },
    ui,
  };
  return { ctx, mounts, live, notifications };
}

const PLAIN_THEME = {
  fg: (_color: string, text: string) => text,
  bg: (_color: string, text: string) => text,
  bold: (text: string) => text,
};

interface ResearchCall {
  focus: unknown;
  cwd: unknown;
  model: unknown;
  signal: unknown;
  onUpdate: unknown;
}

type ResearchResult = { findings: string; usage?: unknown; error?: string };

/** Deferred stand-in child: the test, not the runtime, decides when it settles. */
function deferredChild() {
  const calls: ResearchCall[] = [];
  const releases: ((value: ResearchResult) => void)[] = [];
  const runResearch = (opts: ResearchCall) => {
    calls.push(opts);
    return new Promise<ResearchResult>((resolve) => { releases.push(resolve); });
  };
  return { calls, releases, runResearch };
}

function researchTool(root: string, runResearch: unknown) {
  const host = makeHost();
  const core = new GoalCore(host.pi as never, root, { runResearch: runResearch as never });
  registerGoalTools(core);
  const tool = host.tools.get("research_goal");
  assert.ok(tool, "research_goal is registered");
  return { host, core, tool };
}

function procedureRows(host: ReturnType<typeof makeHost>, requirement: string): string[] {
  const renderer = host.renderers.get(PROCEDURE_TYPE);
  assert.ok(renderer, "procedure channel absent: no goal-procedure message renderer is registered");
  const message = {
    customType: PROCEDURE_TYPE,
    content: goalRequest(requirement),
    display: true,
    details: { request: requirement },
  };
  return renderer(message, { expanded: false, outputPad: 0 }, PLAIN_THEME).render(80);
}

// ── research row ──

/** Widget calls made above the input box, which research must never make. */
function aboveEditor(tui: ReturnType<typeof makeTuiCtx>) {
  return tui.mounts.filter((call) => (call.options as { placement?: string } | undefined)?.placement === "aboveEditor");
}

await scenario("Research blocks and mounts no widget above the editor", async () => {
  const root = tempRoot("goal-live-");
  const child = deferredChild();
  const { tool } = researchTool(root, child.runResearch);
  const tui = makeTuiCtx(root);
  const pending = tool.execute("call-1", { focus: "Where is the CSV export written?" }, undefined, undefined, tui.ctx);
  try {
    assert.equal(child.calls.length, 1, "a read-only child started");
    assert.deepEqual(aboveEditor(tui), [], "no widget is mounted above the editor while the child works");
    assert.ok(!tui.live.has(RESEARCH_KEY), "no research row exists to show progress");
    (child.calls[0]!.onUpdate as (update: unknown) => void)({ activeTool: "grep", activity: "cd /repo && ls -la" });
    assert.deepEqual(aboveEditor(tui), [], "a progress update mounts nothing either");
    child.releases[0]!({ findings: "export.ts builds the CSV.", usage: { totalTokens: 10 } });
    const result = (await pending) as { details: { subject?: string } };
    assert.match(String(result.details.subject ?? ""), /Research ready/, "the result row still reports the findings");
    assert.deepEqual(aboveEditor(tui), [], "settling the child leaves nothing above the editor");
  } finally {
    child.releases.forEach((release) => release({ findings: "", error: "settled by harness cleanup" }));
    await pending.catch(() => {});
  }
});

await scenario("the research row carries the latest progress and renders markdown", async () => {
  const root = tempRoot("goal-live-");
  const child = deferredChild();
  const { tool } = researchTool(root, child.runResearch);
  const tui = makeTuiCtx(root);
  const partials: { subject?: unknown; summary?: unknown; markdown?: unknown }[] = [];
  const pending = tool.execute(
    "call-1",
    { focus: "Where is the CSV export written?" },
    undefined,
    (partial: { details?: { subject?: unknown; summary?: unknown; markdown?: unknown } }) => {
      partials.push({ subject: partial.details?.subject, summary: partial.details?.summary, markdown: partial.details?.markdown });
    },
    tui.ctx,
  );
  try {
    const onUpdate = child.calls[0]!.onUpdate as (update: unknown) => void;
    // The child's own latest activity is the progress the row exists to show.
    onUpdate({ activeTool: "grep", activity: "**searching** `tests`", text: "**searching** `tests`" });
    onUpdate({ activeTool: "read", activity: "reading export.ts", text: "reading export.ts" });
    assert.equal(partials.length, 2, "each update updates the one row in place");
    for (const partial of partials) {
      assert.equal(partial.subject, "Researching...", "the row reads as in progress");
      assert.equal(partial.markdown, true, "pi-kit renders the progress through markdown");
    }
    assert.equal(partials[0]!.summary, "**searching** `tests`", "the newest activity is what the row shows");
    assert.equal(partials[1]!.summary, "reading export.ts", "and it replaces the older one rather than stacking");
    child.releases[0]!({ findings: "# Findings\n\n- export.ts writes the CSV." });
    const result = (await pending) as { details: { subject?: string; summary?: string; markdown?: unknown } };
    assert.equal(result.details.subject, "Research ready", "the subject carries no character count");
    assert.equal(result.details.markdown, true, "the findings render through markdown");
    assert.match(String(result.details.summary), /# Findings/, "the findings are the body");
    const final = partials.at(-1);
    assert.equal(final?.subject, "Research ready", "the final update replaces the in-progress row before tool completion");
    assert.equal(final?.markdown, true, "the final update uses markdown");
    assert.match(String(final?.summary), /# Findings/, "the final update carries the findings");
  } finally {
    child.releases.forEach((release) => release({ findings: "", error: "settled by harness cleanup" }));
    await pending.catch(() => {});
  }
});

await scenario("Every research outcome returns a row and mounts nothing", async () => {
  const outcomes: { name: string; settle: (release: (value: ResearchResult) => void) => void }[] = [
    { name: "findings", settle: (release) => release({ findings: "export.ts builds the CSV." }) },
    { name: "non-zero exit", settle: (release) => release({ findings: "", error: "The research child exited with code 2." }) },
    { name: "empty answer", settle: (release) => release({ findings: "", error: "The research child returned nothing." }) },
  ];
  for (const outcome of outcomes) {
    const root = tempRoot("goal-live-");
    const child = deferredChild();
    const { tool } = researchTool(root, child.runResearch);
    const tui = makeTuiCtx(root);
    const pending = tool.execute("call-1", { focus: "probe" }, undefined, undefined, tui.ctx);
    try {
      (child.calls[0]!.onUpdate as (update: unknown) => void)({ activeTool: "read" });
      outcome.settle(child.releases[0]!);
      const result = (await pending) as { details: { subject?: string } };
      assert.ok(typeof result.details.subject === "string" && result.details.subject.length > 0, `a row reports ${outcome.name}`);
      assert.deepEqual(aboveEditor(tui), [], `no widget remains after ${outcome.name}`);
      assert.ok(!tui.live.has(RESEARCH_KEY), `no research row remains after ${outcome.name}`);
    } finally {
      child.releases.forEach((release) => release({ findings: "", error: "settled by harness cleanup" }));
      await pending.catch(() => {});
    }
  }
  {
    const root = tempRoot("goal-live-");
    const controller = new AbortController();
    controller.abort();
    const child = deferredChild();
    const { tool } = researchTool(root, child.runResearch);
    const tui = makeTuiCtx(root);
    const pending = tool.execute("call-1", { focus: "probe" }, controller.signal, undefined, tui.ctx);
    try {
      child.releases[0]?.({ findings: "", error: "Research was cancelled before it started." });
      await pending;
      assert.deepEqual(aboveEditor(tui), [], "no widget remains after abort");
    } finally {
      child.releases.forEach((release) => release({ findings: "", error: "settled by harness cleanup" }));
      await pending.catch(() => {});
    }
  }
});

// ── /goal procedure row ──

function commandCore() {
  const root = tempRoot("goal-live-");
  const host = makeHost();
  // Full extension setup, as production wires it: the procedure channel is
  // registered alongside the command, tools, and events.
  goalExtension(host.pi as never, { projectRoot: root });
  const core = (host.pi as unknown as { _goalCore?: GoalCore })._goalCore;
  assert.ok(core, "the extension exposes its core");
  const handler = host.commands.get("goal")?.handler;
  assert.ok(handler, "the /goal command is registered");
  return { root, host, core, handler };
}

function idleCtx() {
  const notifications: string[] = [];
  return {
    ctx: {
      mode: "print",
      isIdle: () => true,
      hasPendingMessages: () => false,
      ui: { notify: (line: string) => notifications.push(line) },
    },
    notifications,
  };
}

await scenario("/goal delivers one lifecycle row with the requirement", async () => {
  const { host, handler } = commandCore();
  const { ctx } = idleCtx();
  await handler("Export the reports page as CSV", ctx);
  assert.equal(host.sent.length, 1, `exactly one transcript row, got ${host.sent.length}`);
  assert.equal(host.userSent.length, 0, "the requirement is not also sent as a plain user message");
  const msg = host.sent[0]!.message as { customType?: unknown; content?: unknown; display?: unknown; details?: unknown };
  assert.equal(msg.customType, PROCEDURE_TYPE, "the row uses the goal procedure channel");
  assert.equal(msg.display, true, "the row is displayed");
  assert.equal((host.sent[0]!.options as { triggerTurn?: unknown }).triggerTurn, true, "the turn is triggered");
  assert.equal((host.sent[0]!.options as { deliverAs?: unknown }).deliverAs, "followUp", "delivery is a follow-up");
  assert.equal((msg.details as { request?: unknown }).request, "Export the reports page as CSV", "the requirement is verbatim");
  assert.equal(String(msg.content), goalRequest("Export the reports page as CSV"), "the model receives the full goalRequest body");
  const rows = procedureRows(host, "Export the reports page as CSV");
  const head = rows.map((line) => line.trim()).find((line) => line.startsWith("[goal]")) ?? "";
  assert.ok(head.includes("[goal] started") && !head.includes("started ·"), `the row head reads "[goal] started" without repeating the subject, got ${JSON.stringify(head)}`);
  assert.ok(rows.join("\n").includes("Export the reports page as CSV"), "the requirement appears verbatim in a block under the head");
});

await scenario("Different requirements produce different rows", async () => {
  const { host, handler } = commandCore();
  const { ctx } = idleCtx();
  await handler("first requirement", ctx);
  await handler("second requirement", ctx);
  assert.equal(host.sent.length, 2, `one row per request, got ${host.sent.length}`);
  const first = (host.sent[0]!.message as { details: { request: string } }).details.request;
  const second = (host.sent[1]!.message as { details: { request: string } }).details.request;
  assert.equal(first, "first requirement");
  assert.equal(second, "second requirement", "the second row shows the second text");
});

await scenario("Management arguments emit no lifecycle row", async () => {
  const { host } = commandCore();
  assert.ok(host.renderers.has(PROCEDURE_TYPE), "the procedure channel exists, so silence is a guarantee rather than an absence");
  for (const arg of ["", "pause", "resume", "clear"]) {
    const { host: session, handler } = commandCore();
    const notifications: string[] = [];
    await handler(arg, {
      mode: "print",
      isIdle: () => true,
      hasPendingMessages: () => false,
      hasUI: true,
      ui: { notify: (line: string) => notifications.push(line), select: async () => "Keep goal" },
    });
    const rows = session.sent.filter((entry) => (entry.message as { customType?: unknown }).customType === PROCEDURE_TYPE);
    assert.equal(rows.length, 0, `/${arg || "(bare)"} sends no "[goal] started" row`);
    assert.ok(notifications.length > 0 || arg === "", "the existing notification behaviour is unchanged");
  }
  assert.ok(!host.sent.some((entry) => (entry.message as { customType?: unknown }).customType === PROCEDURE_TYPE));
});

await scenario("A revision under way emits exactly one row", async () => {
  const { host, core, handler } = commandCore();
  const created = core.store.create({ objective: "Export the reports page as CSV.", owner: "unknown-session", id: core.newId() });
  assert.ok(created.ok, created.ok ? "" : created.message);
  if (created.ok) {
    const armed = core.store.apply({
      expectedGoalId: created.goal.id,
      mutate: (draft) => ({ ...draft, status: "active" as const, autoContinue: true }),
    });
    assert.ok(armed.ok, armed.ok ? "" : JSON.stringify(armed));
    (core as unknown as { focusedGoalId: string }).focusedGoalId = created.goal.id;
  }
  const notifications: string[] = [];
  await handler("Export as PDF instead, with one test per format.", {
    mode: "print",
    isIdle: () => false,
    hasPendingMessages: () => true,
    ui: { notify: (line: string) => notifications.push(line) },
  });
  assert.equal(host.sent.length, 1, `a revision under way emits exactly one row, got ${host.sent.length}`);
  const msg = host.sent[0]!.message as { customType?: unknown; details?: { request?: unknown } };
  assert.equal(msg.customType, PROCEDURE_TYPE, "the row uses the goal procedure channel");
  assert.equal(msg.details?.request, "Export as PDF instead, with one test per format.");
  assert.match(core.store.readGoal(created.ok ? created.goal.id : "")?.objective ?? "", /PDF/, "the text goes through applyRevision as a revision");
});

for (const root of roots) rmSync(root, { recursive: true, force: true });
process.stdout.write(`${JSON.stringify(results)}\n`);
