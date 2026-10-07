"""Intent tool lifecycle rows: readable names, compact previews, and honest state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from subagents_helpers import PACKAGE, SRC, run_isolated_node as run_node




ENTRY = (PACKAGE / "index.ts").as_uri()

PREAMBLE = f"""
import assert from "node:assert/strict";
import {{ stripVTControlCharacters }} from "node:util";
import {{ visibleWidth }} from "@earendil-works/pi-tui";
import piSubagentsExtension from {json.dumps(ENTRY)};
import {{ executeIntentTool }} from {json.dumps((PACKAGE / "src" / "intent-tools.ts").as_uri())};
import * as roster from {json.dumps((PACKAGE / "src" / "roster.ts").as_uri())};

const theme = {{ fg: (_name, text) => text, bg: (_name, text) => text, bold: (text) => text }};
const calls = [];
const pi = {{ registerTool: (tool) => calls.push(tool), registerMessageRenderer() {{}}, on() {{}}, events: {{ emit() {{}} }} }};
piSubagentsExtension(pi);
const tools = Object.fromEntries(calls.filter((tool) => tool.name.startsWith("agent_")).map((tool) => [tool.name, tool]));
assert.deepEqual(Object.keys(tools).sort(), ["agent_input", "agent_list", "agent_start", "agent_stop"]);

const render = (operation, result, expanded, width = 100, isError = false) => {{
  const component = tools[operation].renderResult(
    {{ content: result.content ?? [{{ type: "text", text: "" }}], details: result.details }},
    {{ expanded, isPartial: false }}, theme, {{ args: {{}}, toolCallId: operation, isError }},
  );
  const rows = component.render(width).map(stripVTControlCharacters);
  assert.ok(rows.every((row) => visibleWidth(row) <= width), `${{operation}} row exceeds ${{width}} columns:\\n${{rows.join("\\n")}}`);
  return rows.join("\\n");
}};
const handle = "session:review-child:spawn-123";
const base = (operation, extra = {{}}) => ({{
  content: [{{ type: "text", text: "receipt" }}],
  details: {{ version: 1, operation, ok: true, disposition: "queued", state: "working", nextActor: "runtime", session: handle, name: "review-child", label: "reviewer", ...extra }},
}});
"""


def run(script: str) -> dict[str, object]:
    return run_node(f"{PREAMBLE}\n{script}")


def test_intent_rows_use_readable_subjects_and_hide_handles_until_expanded() -> None:
    result = run(
        """
        const input = base("agent_input", { disposition: "queued", prompt: "Check the ledger." });
        const stop = base("agent_stop", { disposition: "stopped", state: "stopped", evidence: "Process terminated. Its work is complete where its own result or a completed task says so." });
        const listed = base("agent_list", { disposition: "listed", sessions: [
          { name: "review-child", label: "reviewer", session: handle, status: "working", activeTool: "read", pendingInputs: 2 },
        ], agents: [], definitions: [] });
        const rows = {};
        for (const [operation, value] of Object.entries({ agent_input: input, agent_stop: stop })) {
          rows[operation] = { collapsed: render(operation, value, false), expanded: render(operation, value, true) };
          assert.ok(rows[operation].collapsed.includes("reviewer"), rows[operation].collapsed);
          assert.ok(!rows[operation].collapsed.includes(handle), rows[operation].collapsed);
          assert.ok(rows[operation].expanded.includes(handle), rows[operation].expanded);
        }
        // A roster names no child, so its collapsed row carries no child's name and,
        // when the page omitted nothing, no count either: each name waits for
        // expansion, and a count that says "all of them" says nothing.
        rows.agent_list = { collapsed: render("agent_list", listed, false), expanded: render("agent_list", listed, true) };
        assert.ok(rows.agent_list.collapsed.includes("[agent] listed"), rows.agent_list.collapsed);
        assert.ok(!/\d+ of \d+/.test(rows.agent_list.collapsed), rows.agent_list.collapsed);
        assert.ok(!rows.agent_list.collapsed.includes("reviewer"), rows.agent_list.collapsed);
        assert.ok(rows.agent_list.expanded.includes("reviewer") && rows.agent_list.expanded.includes(handle), rows.agent_list.expanded);
        // The roster carries each child's live facts, printed once, after expansion.
        assert.ok(rows.agent_list.expanded.includes("active tool · read") && rows.agent_list.expanded.includes("queued · 2"), rows.agent_list.expanded);
        for (const key of ["session ·", "active tool ·", "queued ·"]) {
          const times = rows.agent_list.expanded.split(key).length - 1;
          assert.equal(times, 1, `${key} appeared ${times} times:\\n${rows.agent_list.expanded}`);
        }
        console.log(JSON.stringify(rows));
        """
    )
    assert "reviewer" in result["agent_input"]["collapsed"]


def test_control_input_is_previewed_once_and_receipt_is_unchanged() -> None:
    result = run(
        """
        const prompt = "FIRST_AUTHORED_LINE\\n\\nSECOND_AUTHORED_LINE";
        const value = base("agent_input", { disposition: "steered", prompt, inputId: "input-1" });
        const before = JSON.stringify(value);
        const collapsed = render("agent_input", value, false, 70);
        const expanded = render("agent_input", value, true, 70);
        assert.ok(collapsed.includes("FIRST_AUTHORED_LINE"), collapsed);
        assert.ok(!collapsed.includes(handle), collapsed);
        assert.ok(expanded.includes("FIRST_AUTHORED_LINE") && expanded.includes("SECOND_AUTHORED_LINE"), expanded);
        assert.equal(expanded.split("FIRST_AUTHORED_LINE").length - 1, 1, expanded);
        assert.equal(expanded.split("SECOND_AUTHORED_LINE").length - 1, 1, expanded);
        assert.ok(expanded.includes("session · " + handle), expanded);
        assert.ok(expanded.includes("state · working") && expanded.includes("next · runtime"), expanded);
        assert.equal(JSON.stringify(value), before);
        console.log(JSON.stringify({ collapsed, expanded }));
        """
    )
    assert "FIRST_AUTHORED_LINE" in result["collapsed"]


def test_actual_intent_results_retain_friendly_label_for_controls() -> None:
    result = run(
        """
        const options = {
          cwd: process.env.PI_TEST_CWD,
          spawn: () => ({ pid: 7 }),
          steer: async () => true,
          terminate: async () => ({ outcome: "closed" }),
        };
        const started = await executeIntentTool("agent_start", { label: "friendly reviewer", prompt: "FIRST" }, options);
        const session = started.structuredContent.session;
        const name = started.structuredContent.name;
        roster.updateAgent(name, { activeTool: "read", liveText: "bounded live output", error: "diagnostic", model: "provider/model", tools: ["read"], resultKind: "unanswered" });
        const steered = await executeIntentTool("agent_input", { session, prompt: "ADJUST", delivery: "steer" }, options);
        const stopped = await executeIntentTool("agent_stop", { session }, options);
        const listed = await executeIntentTool("agent_list", {}, options);
        for (const [operation, value] of Object.entries({ agent_input: steered, agent_stop: stopped })) {
          const collapsed = render(operation, value, false);
          assert.ok(collapsed.includes("@friendly reviewer"), `${operation}: ${collapsed}`);
          assert.ok(!collapsed.includes(session), `${operation} leaked exact handle: ${collapsed}`);
          assert.ok(render(operation, value, true).includes(session), `${operation} hid exact handle on expansion`);
        }
        const listCollapsed = render("agent_list", listed, false);
        assert.ok(listCollapsed.includes("[agent] listed") && !listCollapsed.includes(session), listCollapsed);
        assert.ok(render("agent_list", listed, true).includes("@friendly reviewer"), render("agent_list", listed, true));
        const expandedRoster = render("agent_list", listed, true);
        for (const fact of ["active tool · read", "error · diagnostic", "model · provider/model", "tools · read", "result · unanswered"]) {
          assert.ok(expandedRoster.includes(fact), `roster expansion dropped ${fact}: ${expandedRoster}`);
        }
        // A handle that no longer exists is refused by the controls that need one.
        const missing = await executeIntentTool("agent_stop", { session: "session:missing:incarnation" }, options);
        const missingCollapsed = render("agent_stop", missing, false, 100, true);
        const missingExpanded = render("agent_stop", missing, true, 100, true);
        assert.ok(!missingCollapsed.includes("session:missing:incarnation"), missingCollapsed);
        assert.ok(missingExpanded.includes("session:missing:incarnation"), missingExpanded);
        console.log(JSON.stringify({ session, list: listed.structuredContent, stop: stopped.structuredContent }));
        """
    )
    assert result["session"].startswith("session:")


def test_queued_prompt_preview_is_bounded_and_marks_truncation() -> None:
    result = run(
        """
        const options = {
          cwd: process.env.PI_TEST_CWD,
          spawn: () => ({ pid: 7 }),
          terminate: async () => ({ outcome: "closed" }),
        };
        const started = await executeIntentTool("agent_start", { label: "budgeted", prompt: "FIRST" }, options);
        const prompt = "界".repeat(5000);
        const queued = await executeIntentTool("agent_input", { session: started.structuredContent.session, prompt, delivery: "next" }, options);
        const receipt = queued.structuredContent;
        assert.ok(receipt.prompt);
        assert.ok(Buffer.byteLength(receipt.prompt, "utf8") <= 4096, `prompt preview exceeded budget: ${Buffer.byteLength(receipt.prompt, "utf8")}`);
        assert.equal(receipt.truncation.fields[0].field, "prompt");
        assert.equal(receipt.truncation.fields[0].truncated, true);
        assert.ok(prompt.startsWith("界界"), "the dispatched authored value was constructed independently");
        console.log(JSON.stringify({ bytes: Buffer.byteLength(receipt.prompt, "utf8"), truncation: receipt.truncation }));
        """
    )
    assert result["bytes"] <= 4096


def test_stop_and_error_rows_are_honest_and_keep_exact_handle_expanded() -> None:
    result = run(
        """
        const stop = base("agent_stop", { disposition: "stopped", state: "stopped", evidence: "Process terminated. Its work is complete where its own result or a completed task says so." });
        const failure = { content: [
          { type: "text", text: "The exact child could not be confirmed.\\nsession · " + handle },
        ], details: { version: 1, operation: "agent_input", ok: false, disposition: "uncertain", state: "working", nextActor: "runtime", session: handle, name: "review-child", label: "reviewer", error: "The exact child could not be confirmed.", code: "delivery-failed" } };
        const stopRow = render("agent_stop", stop, false);
        const stopExpanded = render("agent_stop", stop, true);
        const failureRow = render("agent_input", failure, false, 100, true);
        assert.match(stopRow, /\\[agent\\] stopped · @reviewer/, stopRow);
        assert.ok(!stopRow.includes(handle), stopRow);
        assert.match(stopExpanded, /note · Completion belongs to the child result or task record/, stopExpanded);
        assert.ok(failureRow.includes("reviewer") || failureRow.includes("child"), failureRow);
        assert.ok(!failureRow.includes(handle), failureRow);
        assert.ok(render("agent_input", failure, true, 100, true).includes(handle));
        console.log(JSON.stringify({ stopRow, stopExpanded, failureRow }));
        """
    )
    assert "reviewer" in result["stopRow"]
    assert "completion" in result["stopExpanded"].lower()


def test_unanswered_diagnostic_and_preview_notice_survive_expansion() -> None:
    result = run("""
      const options = { cwd: process.env.PI_TEST_CWD, spawn: () => ({ pid: 7 }) };
      const started = await executeIntentTool('agent_start', { label: 'reader', prompt: 'Read.' }, options);
      roster.updateAgent(started.details.name, { status: 'idle', resultKind: 'unanswered',
        unansweredReason: 'error', stopReason: 'error', finalDiagnostic: 'PROVIDER_DIAGNOSTIC', liveText: 'Partial evidence.' });
      const value = await executeIntentTool('agent_list', {}, options);
      const before = JSON.stringify(value);
      const expanded = render('agent_list', value, true, 200);
      assert.ok(expanded.includes('provider failed before producing a complete final answer'), expanded);
      assert.ok(expanded.includes('PROVIDER_DIAGNOSTIC'), expanded);
      assert.ok(expanded.includes('Status summary only'), expanded);
      assert.equal(JSON.stringify(value), before);
      console.log(JSON.stringify({ ok: true }));
    """)
    assert result['ok'] is True


def test_authored_handle_is_hidden_in_preview_and_preserved_on_expansion() -> None:
    result = run("""
      const prompt = 'Continue ' + handle + ' and check the ledger.';
      const value = base('agent_input', { prompt });
      const before = JSON.stringify(value);
      const collapsed = render('agent_input', value, false, 200);
      const expanded = render('agent_input', value, true, 200);
      assert.ok(!collapsed.includes(handle), collapsed);
      assert.ok(expanded.includes(prompt), expanded);
      assert.equal(expanded.split(prompt).length - 1, 1);
      assert.equal(JSON.stringify(value), before);
      console.log(JSON.stringify({ ok: true }));
    """)
    assert result['ok'] is True


def test_offline_role_facts_survive_expansion() -> None:
    result = run("""
      const value = base('agent_list', { sessions: [], definitions: [{
        name: 'saved-reader', status: 'offline', scope: 'project', source: '/project/.pi/agents/saved-reader/agent.md',
        description: 'Inspect storage boundaries.', tools: ['read'], model: 'provider/model',
      }] });
      const expanded = render('agent_list', value, true, 200);
      for (const fact of ['scope · project', 'source · /project/.pi/agents/saved-reader/agent.md',
        'description · Inspect storage boundaries.', 'tools · read', 'model · provider/model']) {
        assert.ok(expanded.includes(fact), expanded);
      }
      console.log(JSON.stringify({ ok: true }));
    """)
    assert result['ok'] is True


def test_native_error_context_keeps_child_name_and_uncertain_disposition() -> None:
    result = run("""
      const value = base('agent_input', { ok: false, disposition: 'uncertain', error: 'Wait cancelled; do not repeat input.' });
      value.content = [{ type: 'text', text: 'Wait cancelled; do not repeat input.\\nsession · ' + handle }];
      const before = JSON.stringify(value);
      const collapsed = render('agent_input', value, false, 200, true);
      assert.ok(collapsed.includes('[agent] uncertain · @reviewer'), collapsed);
      assert.ok(collapsed.includes('do not repeat input'), collapsed);
      assert.ok(!collapsed.includes(handle), collapsed);
      assert.ok(render('agent_input', value, true, 200, true).includes(handle));
      assert.equal(JSON.stringify(value), before);
      console.log(JSON.stringify({ ok: true }));
    """)
    assert result['ok'] is True


def test_list_page_discloses_remaining_entries_and_empty_page() -> None:
    result = run("""
      const options = { cwd: process.env.PI_TEST_CWD, spawn: () => ({ pid: 7 }) };
      await executeIntentTool('agent_start', { label: 'first', prompt: 'Read.' }, options);
      await executeIntentTool('agent_start', { label: 'second', prompt: 'Read.' }, options);
      const first = await executeIntentTool('agent_list', { limit: 1 }, options);
      assert.ok(render('agent_list', first, false, 200).includes('1 of 2'));
      const expanded = render('agent_list', first, true, 200);
      assert.ok(expanded.includes('1 remaining') && expanded.includes('next offset 1'), expanded);
      const empty = await executeIntentTool('agent_list', { offset: 2, limit: 1 }, options);
      const emptyRow = render('agent_list', empty, false, 200);
      assert.ok(emptyRow.includes('2 total') && !emptyRow.includes('No child sessions'), emptyRow);
      console.log(JSON.stringify({ ok: true }));
    """)
    assert result['ok'] is True


@pytest.mark.parametrize('operation', ['agent_input', 'agent_stop'])
def test_historical_operation_label_survives_roster_replacement(operation: str) -> None:
    result = run(f"""
      const options = {{ cwd: process.env.PI_TEST_CWD, spawn: () => ({{ pid: 7 }}),
        steer: async () => true, terminate: async () => ({{ outcome: 'closed' }}) }};
      const started = await executeIntentTool('agent_start', {{ label: 'original reader', prompt: 'Read.' }}, options);
      const operation = {operation!r};
      const value = await executeIntentTool(operation, {{ session: started.details.session,
        ...(operation === 'agent_input' ? {{ prompt: 'Adjust.', delivery: 'steer' }} : {{}}) }}, options);
      assert.equal(value.details.ok, true);
      roster.resetRoster();
      roster.registerAgent({{ name: started.details.name, role: started.details.name, label: 'successor label',
        spawnId: 'replacement', status: 'idle', scope: 'session', createdAt: 1, updatedAt: 1 }});
      const row = render(operation, value, false, 200);
      assert.ok(row.includes('@original reader'), row);
      assert.ok(!row.includes('successor label'), row);
      console.log(JSON.stringify({{ ok: true }}));
    """)
    assert result['ok'] is True


@pytest.mark.parametrize('failure', ['idle-steer', 'stopping', 'cancelled', 'async-rejection'])
def test_historical_failure_label_survives_roster_replacement(failure: str) -> None:
    result = run(f"""
      let rejectPrompt = async () => true;
      const options = {{ cwd: process.env.PI_TEST_CWD, spawn: () => ({{ pid: 7 }}), prompt: () => rejectPrompt() }};
      const started = await executeIntentTool('agent_start', {{ label: 'original reader', prompt: 'Read.' }}, options);
      const failure = {failure!r};
      const replace = () => {{
        roster.resetRoster();
        roster.registerAgent({{ name: started.details.name, role: started.details.name, label: 'successor label',
          spawnId: 'replacement', status: 'idle', scope: 'session', createdAt: 1, updatedAt: 1 }});
      }};
      if (failure === 'idle-steer') roster.updateAgent(started.details.name, {{ status: 'idle' }});
      if (failure === 'stopping') roster.updateAgent(started.details.name, {{ leaderRequestedEnd: true }});
      const controller = new AbortController();
      let promptCalls = 0;
      if (failure === 'cancelled') controller.abort();
      if (failure === 'async-rejection') {{
        roster.updateAgent(started.details.name, {{ status: 'idle' }});
        const {{ settleInputSequence }} = await import('./src/input-sequences.ts');
        settleInputSequence(started.details.session);
        rejectPrompt = async () => {{ promptCalls++; replace(); return false; }};
      }}
      const value = await executeIntentTool('agent_input', {{ session: started.details.session,
        prompt: 'Adjust.', delivery: failure === 'idle-steer' ? 'steer' : 'next' }}, {{ ...options, signal: controller.signal }});
      assert.equal(value.details.ok, false);
      if (failure === 'async-rejection') assert.equal(promptCalls, 1);
      if (failure !== 'async-rejection') replace();
      const row = render('agent_input', value, false, 200, true);
      assert.ok(row.includes('[agent] ' + value.details.disposition + ' · @original reader'), row);
      assert.ok(!row.includes('successor label'), row);
      console.log(JSON.stringify({{ ok: true }}));
    """)
    assert result['ok'] is True


@pytest.mark.parametrize("failure", ["exit", "transport", "delivery"])
def test_ended_notice_keeps_the_original_display_label(tmp_path: Path, failure: str) -> None:
    script = f"""
import assert from 'node:assert/strict';
import {{ mock }} from 'node:test';
import {{ stripVTControlCharacters }} from 'node:util';
import * as spawner from {json.dumps((SRC / 'spawner.ts').as_uri())};
let child;
mock.module({json.dumps((SRC / 'spawner.ts').as_uri())}, {{ namedExports: {{
  ...spawner,
  spawnResident: options => {{ child = options; return {{ pid: 7, accepted: Promise.resolve(true) }}; }},
  terminateAgent: async () => ({{ outcome: 'closed' }}),
}} }});
const {{ default: extension }} = await import({json.dumps((PACKAGE / 'index.ts').as_uri())});
const tools = [], notices = [], renderers = new Map();
let failedDeliveries = 0;
const pi = {{ registerTool: tool => tools.push(tool), on() {{}}, events: {{ emit() {{}} }},
  registerMessageRenderer: (name, renderer) => renderers.set(name, renderer),
  sendMessage: message => {{
    if (process.env.PI_NOTICE_FAILURE === 'delivery' && message.customType === 'subagents-session-result') {{
      failedDeliveries++; throw new Error('fixture delivery failure');
    }}
    notices.push(message);
  }},
}};
extension(pi);
const started = await tools.find(tool => tool.name === 'agent_start').execute('start', {{
  label: 'storage reviewer', prompt: 'Review the storage contract.', tools: [],
}}, undefined, undefined, {{ cwd: process.env.PI_TEST_CWD }});
assert.equal(started.details.ok, true);
const failure = process.env.PI_NOTICE_FAILURE;
if (failure === 'exit') child.onExit({{ exitCode: 1 }});
else if (failure === 'transport') child.onError(new Error('fixture transport failure'));
else child.onUpdate({{ text: 'Preserved answer.', turns: 1, finalResponse: true, answerComplete: true, stopReason: 'stop' }});
await new Promise(resolve => setImmediate(resolve));
const ended = notices.filter(message => message.customType === 'subagents-session-ended');
assert.equal(ended.length, 1, JSON.stringify(notices));
assert.equal(ended[0].details.session, started.details.session);
assert.equal(ended[0].details.name, 'storage reviewer', 'the failure row must keep the start display name');
const theme = {{ fg: (_color, text) => text, bg: (_color, text) => text, bold: text => text }};
const row = renderers.get(ended[0].customType)(ended[0], {{ expanded: false }}, theme)
  .render(80).map(stripVTControlCharacters).join('\\n');
assert.match(row, /\\[agent\\] ended · @storage reviewer/);
assert.ok(!row.includes('subagent-'), row);
assert.ok(!row.includes('reported'), row);
if (failure === 'delivery') assert.equal(failedDeliveries, 2);
console.log(JSON.stringify({{ ok: true }}));
"""
    result = run_node(script, module_mocks=True, env_overrides={
        "HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "PI_TEST_CWD": str(tmp_path), "PI_NOTICE_FAILURE": failure,
    })
    assert result["ok"] is True
