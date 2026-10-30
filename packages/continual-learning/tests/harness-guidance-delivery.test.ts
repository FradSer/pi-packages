import { afterAll, expect, test } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { SessionManager, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import registerGuidance from "../extensions/harness-guidance.ts";
import registerGuardrails from "../extensions/guardrails.ts";
import { applyHarnessOps, correctionDigest, type HarnessOp } from "../extensions/harness-consolidation.ts";
import { ruleRevision } from "../extensions/guardrail-engine.ts";

// These exercise parent persistence and real native branch reconstruction. The
// proposed rules and judgments are controlled; they establish delivery only.
const root = fs.mkdtempSync(path.join(os.tmpdir(), "harness-delivery-"));
const priorAgentDir = process.env.PI_CODING_AGENT_DIR;
process.env.PI_CODING_AGENT_DIR = path.join(root, "agent");
afterAll(() => {
  if (priorAgentDir === undefined) delete process.env.PI_CODING_AGENT_DIR;
  else process.env.PI_CODING_AGENT_DIR = priorAgentDir;
  fs.rmSync(root, { recursive: true, force: true });
});

function fixture(name: string) {
  const cwd = path.join(root, name);
  fs.mkdirSync(path.join(cwd, ".pi"), { recursive: true });
  const target = path.join(cwd, ".pi", "harness.json");
  const session = SessionManager.inMemory(cwd);
  const bind = () => {
    const hooks: Record<string, (...args: any[]) => any> = {};
    registerGuidance({
      on: (name: string, handler: (...args: any[]) => any) => { hooks[name] = handler; },
      registerEntryRenderer() {},
      appendEntry: (type: string, data: unknown) => session.appendCustomEntry(type, data),
    } as unknown as ExtensionAPI);
    return hooks;
  };
  let hooks = bind();
  const start = (prompt: string, skills: Array<{ name: string }> = []) => {
    const options = { skills, sections: { other: "OTHER_OWNER" } as Record<string, string>, customPrompt: "CUSTOM_OWNER" };
    expect(hooks.before_agent_start({ prompt, systemPromptOptions: options }, { cwd, sessionManager: session })).toBeUndefined();
    expect(options.sections.other).toBe("OTHER_OWNER");
    expect(options.customPrompt).toBe("CUSTOM_OWNER");
    return options.sections.harness_guidance ?? "";
  };
  const rows = (type: string) => session.getBranch().filter(entry => entry.type === "custom" && entry.customType === type);
  return { cwd, target, session, start, rows, reload: () => { hooks = bind(); } };
}

test("an automatically persisted text rule survives later turns and reload without duplicate rows", async () => {
  const f = fixture("learned-text");
  const quote = "Project A is retired.";
  expect(await applyHarnessOps(f.target, [{
    op: "addRule", rule: { id: "project-a", text: "Project A", instructions: quote },
    cases: { positive: [{ text: ["Project A status"] }], negative: [{ text: ["Project B status"] }] },
  }], {
    automatic: true,
    snapshot: { entries: [{ message: { role: "user", content: quote } }] },
    evidence: [{ index: 0, source: "user", quote, count: 1 }],
  })).toEqual({ ok: true, applied: ["addRule:project-a"] });
  const saved = JSON.parse(fs.readFileSync(f.target, "utf8"));
  expect(saved.learnedRules["project-a"].origin).toBe("consolidation");

  expect(f.start("Project B status")).toBe("");
  const first = f.start("Project A status");
  expect(first).toContain('Only for subjects matching "Project A"');
  expect(first).toContain(quote);
  f.session.appendMessage({ role: "user", content: "Project A status", timestamp: Date.now() });
  expect(f.start("Continue")).toBe(first);
  f.reload();
  expect(f.start("Continue after reload")).toBe(first);
  expect(f.rows("harness-guidance-event")).toHaveLength(1);
  expect(f.rows("harness-guidance-delivery")).toHaveLength(1);
});

test("reviewed owned corrections replace and retire persisted guidance without duplicate deliveries", async () => {
  const f = fixture("revision");
  const prior = { id: "project-a", text: "Project A", instructions: "Project A is retired." };
  const cases = { positive: [{ text: ["Project A status"] }], negative: [{ text: ["Project B status"] }] };
  const context = (quote: string) => ({
    automatic: true, snapshot: { entries: [{ message: { role: "user", content: quote } }] },
    evidence: [{ index: 0, eventIndex: 0, source: "user", quote, count: 1 }],
  });
  expect((await applyHarnessOps(f.target, [{ op: "addRule", rule: prior, cases }], context(prior.instructions))).ok).toBe(true);
  f.start("Project A");
  f.session.appendMessage({ role: "user", content: "Project A", timestamp: Date.now() });
  const changed = { ...prior, instructions: "Project A is active." };
  const quote = "Permanently correct project-a: Project A is active, replacing the obsolete retired status.";
  const correction: HarnessOp = {
    op: "updateRule", rule: changed, cases,
    correction: { eventIndex: 0, quote, priorRevision: ruleRevision(prior) },
  };
  const originalBytes = fs.readFileSync(f.target, "utf8");
  expect((await applyHarnessOps(f.target, [correction], context(quote))).ok).toBe(false);
  expect(fs.readFileSync(f.target, "utf8")).toBe(originalBytes);
  expect((await applyHarnessOps(f.target, [correction], {
    ...context(quote), reviewedCorrections: { [prior.id]: correctionDigest(correction) },
  })).ok).toBe(true);
  const revised = f.start("Continue");
  expect(revised).toContain(changed.instructions);
  expect(revised).not.toContain(prior.instructions);
  expect(f.start("Continue")).toBe(revised);
  expect(f.rows("harness-guidance-delivery")).toHaveLength(2);
  const retireQuote = "Permanently retire project-a; Project A status guidance is obsolete.";
  const retirement: HarnessOp = {
    op: "updateRule", rule: { ...changed, enabled: false }, cases,
    correction: { eventIndex: 0, quote: retireQuote, priorRevision: ruleRevision(changed) },
  };
  expect((await applyHarnessOps(f.target, [retirement], {
    ...context(retireQuote), reviewedCorrections: { [prior.id]: correctionDigest(retirement) },
  })).ok).toBe(true);
  expect(f.start("Continue")).toContain("[harness:project-a retired]");
  expect(f.start("Continue")).toBe("");
  expect(f.rows("harness-guidance-delivery")).toHaveLength(3);
});

test("skill guidance requires its available expanded invocation and obeys the nearest override", () => {
  const f = fixture("skill");
  fs.writeFileSync(f.target, JSON.stringify({ rules: [{ id: "review", skill: "review", instructions: "SHARED_SKILL" }] }));
  const expanded = '<skill name="review" location="/fixture/SKILL.md">\nbody\n</skill>\n\nReview this change';
  expect(f.start(expanded)).toBe("");
  expect(f.start("Read /fixture/SKILL.md", [{ name: "review" }])).toBe("");
  expect(f.start(expanded, [{ name: "review" }])).toContain("Only for this /skill:review task");
  f.session.appendMessage({ role: "user", content: expanded, timestamp: Date.now() });
  expect(f.start("Unrelated task", [{ name: "review" }])).toBe("");
  fs.writeFileSync(path.join(f.cwd, ".pi", "harness.local.json"), JSON.stringify({ rules: [{ id: "review", enabled: false }] }));
  expect(f.start(expanded, [{ name: "review" }])).toBe("");
  fs.writeFileSync(path.join(f.cwd, ".pi", "harness.local.json"), JSON.stringify({ rules: [{ id: "review", skill: "review", instructions: "PERSONAL_SKILL" }] }));
  const personal = f.start(expanded, [{ name: "review" }]);
  expect(personal).toContain("PERSONAL_SKILL");
  expect(personal).not.toContain("SHARED_SKILL");
});

test("branch-only text delivery does not re-inject when ordinary matching history is absent", () => {
  const f = fixture("branch-scope");
  fs.writeFileSync(f.target, JSON.stringify({ rules: [{ id: "project-a", text: "Project A", instructions: "PROJECT_A_ONLY" }] }));
  expect(f.start("Project A")).toContain("PROJECT_A_ONLY");
  // The real non-context ledger is retained, while no ordinary matching message
  // exists in this branch. Ledger text is never fresh selector evidence.
  expect(f.start("Project B")).toBe("");
  expect(f.rows("harness-guidance-delivery")).toHaveLength(1);
});

test("a persisted Bash guidance rule attaches once to its own success or failure result", async () => {
  const f = fixture("bash");
  const quote = "For fixture-command, report its actual result.";
  expect((await applyHarnessOps(f.target, [{
    op: "addRule", rule: { id: "fixture-note", bash: "^fixture-command$", message: quote },
    cases: { positive: [{ bash: "fixture-command" }], negative: [{ bash: "other-command" }] },
  }], {
    automatic: true, snapshot: { entries: [{ message: { role: "user", content: quote } }] },
    evidence: [{ index: 0, source: "user", quote, count: 1 }],
  })).ok).toBe(true);
  const hooks: Record<string, (...args: any[]) => any> = {};
  registerGuardrails({
    on: (name: string, handler: (...args: any[]) => any) => { hooks[name] = handler; },
    registerCommand() {}, registerTool() {}, registerEntryRenderer() {}, getCommands: () => [],
    appendEntry: (type: string, data: unknown) => f.session.appendCustomEntry(type, data),
  } as unknown as ExtensionAPI);
  const ctx = { cwd: f.cwd, hasUI: false };
  expect(f.start("fixture-command")).toBe("");
  for (const isError of [false, true]) {
    const event = {
      toolName: "bash", toolCallId: `call-${isError}`, input: { command: "fixture-command" },
      content: [{ type: "text", text: `NATIVE_RESULT_${isError}` }], isError, details: { native: true },
    };
    expect((await hooks.tool_call(event, ctx))?.block ?? false).toBe(false);
    const result = await hooks.tool_result(event, ctx);
    expect(result.content[0]).toEqual(event.content[0]);
    expect(result.content).toHaveLength(2);
    expect(result.content[1].text).toBe(`[harness-bash-note]\n[harness:fixture-note] ${quote}`);
    expect(result.isError).toBeUndefined(); // Native state is preserved by Pi's merge.
    expect(event.isError).toBe(isError);
    expect(event.details).toEqual({ native: true });
    expect(await hooks.tool_result(event, ctx)).toBeUndefined();
  }
  const unrelated = { toolName: "bash", toolCallId: "other", input: { command: "other-command" }, content: [], isError: false };
  expect((await hooks.tool_call(unrelated, ctx))?.block ?? false).toBe(false);
  expect(await hooks.tool_result(unrelated, ctx)).toBeUndefined();
});
