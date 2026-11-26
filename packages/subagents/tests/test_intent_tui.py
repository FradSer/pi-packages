from __future__ import annotations

# --- Merged from test_intent_tui.py ---
"""Intent tool lifecycle rows: readable names, compact previews, and honest state."""


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
          assert.ok(!rows[operation].expanded.includes(handle), rows[operation].expanded);
          assert.equal(value.details.session, handle, "exact handle stays in model-facing details");
        }
        // A roster names no child, so its collapsed row carries no child's name and,
        // when the page omitted nothing, no count either: each name waits for
        // expansion, and a count that says "all of them" says nothing.
        rows.agent_list = { collapsed: render("agent_list", listed, false), expanded: render("agent_list", listed, true) };
        assert.ok(rows.agent_list.collapsed.includes("[agent] listed"), rows.agent_list.collapsed);
        assert.ok(!/\\d+ of \\d+/.test(rows.agent_list.collapsed), rows.agent_list.collapsed);
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
        assert.ok(!expanded.includes("session · " + handle), expanded);
        assert.ok(!expanded.includes("state · working") && !expanded.includes("next · runtime"), expanded);
        assert.equal(value.details.session, handle);
        assert.equal(value.details.state, "working");
        assert.equal(value.details.nextActor, "runtime");
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
          assert.ok(collapsed.includes("@friendly-reviewer"), `${operation}: ${collapsed}`);
          // The row carries one identifier-shaped name, never the authored phrase.
          assert.ok(!collapsed.includes("friendly reviewer"), `${operation}: ${collapsed}`);
          assert.ok(!collapsed.includes(session), `${operation} leaked exact handle: ${collapsed}`);
          assert.ok(!render(operation, value, true).includes(session), `${operation} leaked exact handle on expansion`);
          assert.equal(value.structuredContent.session, session);
        }
        const listCollapsed = render("agent_list", listed, false);
        assert.ok(listCollapsed.includes("[agent] listed") && !listCollapsed.includes(session), listCollapsed);
        assert.ok(render("agent_list", listed, true).includes("@friendly-reviewer"), render("agent_list", listed, true));
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
        assert.ok(!render("agent_input", failure, true, 100, true).includes(handle));
        assert.equal(failure.details.session, handle);
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
      assert.ok(!render('agent_input', value, true, 200, true).includes(handle));
      assert.equal(value.details.session, handle);
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
      assert.ok(row.includes('@original-reader'), row);
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
      assert.ok(row.includes('[agent] ' + value.details.disposition + ' · @original-reader'), row);
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
assert.equal(ended[0].details.name, 'storage-reviewer', 'the failure row must keep the start display name, projected to one token');
const theme = {{ fg: (_color, text) => text, bg: (_color, text) => text, bold: text => text }};
const row = renderers.get(ended[0].customType)(ended[0], {{ expanded: false }}, theme)
  .render(80).map(stripVTControlCharacters).join('\\n');
assert.match(row, /\\[agent\\] ended · @storage-reviewer/);
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


def test_control_rows_do_not_dump_runtime_bookkeeping_on_expansion() -> None:
    # Given a steered child with exact handles, state, pending intent and a
    # next actor, When a person expands the row, Then they see the authored
    # guidance only -- not session/input/state/next/pending identifiers. The
    # model-facing structured details keep every exact handle unchanged.
    result = run(
        """
        const steer = "Integrated ./test.sh currently fails Tests/TextDeliveryTests.swift:32 original??.count optional chaining; please correct in your ongoing test pass. Parent not touching your files. Parent only broad build owner.";
        const value = base("agent_input", {
          disposition: "steered", prompt: steer, inputId: "bbbd780f-f418-4091-bd54-9ec3ed2210c3",
          pendingIntent: "steer", state: "working", nextActor: "runtime", pendingInputs: 1,
        });
        const before = JSON.stringify(value);
        const collapsed = render("agent_input", value, false, 100);
        const expanded = render("agent_input", value, true, 100);
        assert.ok(collapsed.includes("steered") && collapsed.includes("@reviewer"), collapsed);
        for (const marker of ["session ·", "input · bbbd", "state ·", "next ·", "pending ·", "queued ·"]) {
          assert.ok(!expanded.includes(marker), `${marker} leaked into the expanded row:\\n${expanded}`);
        }
        const flat = expanded.replace(/\\s+/g, " ");
        assert.ok(flat.includes("Integrated ./test.sh currently fails"), expanded);
        assert.ok(flat.includes("Parent only broad build owner."), expanded);
        assert.equal(JSON.stringify(value), before);
        console.log(JSON.stringify({ collapsed, expanded }));
        """
    )
    assert "Integrated ./test.sh currently fails" in result["expanded"]


# --- Merged from test_agent_activity_widget.py ---
"""The real standalone entry mounts pi-kit's widget from roster callbacks."""

import json
from pathlib import Path

import pytest

from subagents_helpers import PACKAGE, SRC, run_node

SPAWNER = (SRC / 'spawner.ts').as_uri()
_m1_PREAMBLE = f"""
import assert from 'node:assert/strict';
import {{ mock }} from 'node:test';
import {{ visibleWidth }} from '@earendil-works/pi-tui';
import * as spawner from {json.dumps(SPAWNER)};
const spawns=[];
let acknowledge;
mock.module({json.dumps(SPAWNER)}, {{namedExports:{{...spawner,
  spawnResident:o=>(spawns.push(o),{{pid:7,accepted:new Promise(resolve=>acknowledge=resolve)}}),
  terminateAgent:async()=>({{outcome:'closed'}}),
}}}});
const {{default:extension,setAgentHost}}=await import({json.dumps((PACKAGE / 'index.ts').as_uri())});
const {{getAgent,resetRoster,registerAgent,updateAgent}}=await import({json.dumps((SRC / 'roster.ts').as_uri())});
resetRoster();setAgentHost(undefined);
const handlers=new Map(),tools=[],mounts=[],sent=[],widgets=new Map(),painted=[];
let renders=0;
const theme={{fg:(color,text)=>{{painted.push([color,text]);return text}},bold:text=>text}};
const ui={{setWidget(key,factory,options){{
  widgets.get(key)?.dispose?.();widgets.delete(key);mounts.push({{key,mounted:!!factory,options}});
  if(factory)widgets.set(key,factory({{requestRender:()=>renders++}},theme));
}}}};
const pi={{registerTool:t=>tools.push(t),registerMessageRenderer(){{}},events:{{emit(){{}}}},getSettings:()=>({{}}),
  sendMessage:(message,options)=>sent.push({{message,options}}),
  on:(name,handler)=>{{const list=handlers.get(name)??[];list.push(handler);handlers.set(name,list);}}
}};
extension(pi);
const ctx={{cwd:process.env.PI_TEST_CWD,mode:process.env.PI_TEST_MODE??'tui',ui}};
const event=async name=>{{for(const handler of handlers.get(name)??[])await handler({{}},ctx);}};
// The reload case: an extension loaded into a running session never sees a
// session start, so a test can ask for the surface without one.
if(!process.env.PI_TEST_SKIP_SESSION_START) await event('session_start');
const intentTools=new Map(tools.filter(t=>t.name.startsWith("agent_")).map(t=>[t.name,t]));
const call=(request)=>{{
  const {{operation,name,session,prompt,tools:grant,...rest}}=request;
  const tool=operation==="input"||operation==="steer"?"agent_input":operation==="inspect"?"agent_list"
    :operation==="stop"?"agent_stop":operation==="list"?"agent_list":"agent_start";
  const params=tool==="agent_start"
    ?{{prompt:prompt??"Start the assigned work.",...(name===undefined?{{}}:{{label:name}}),...(grant===undefined?{{}}:{{tools:grant}}),...rest}}
    :tool==="agent_input"?{{session,prompt,delivery:operation==="steer"?"steer":"next"}}:session===undefined?{{...rest}}:{{session,...rest}};
  return intentTools.get(tool).execute('probe',params,undefined,undefined,ctx);
}};
const lines=(width=90)=>[...widgets.values()].flatMap(widget=>widget.render(width));
const entry=(name,spawnId)=>({{name,role:name,spawnId,pid:8,status:'working',scope:'session',createdAt:1,updatedAt:1}});
"""


def _m1_run(script: str, tmp_path: Path, mode: str = 'tui', *, skip_session_start: bool = False) -> dict[str, object]:
    env = {
        'PI_TEST_CWD': str(tmp_path), 'PI_TEST_MODE': mode,
        'HOME': str(tmp_path), 'PI_CODING_AGENT_DIR': str(tmp_path / 'agent'),
        'XDG_CONFIG_HOME': str(tmp_path / 'config'), 'XDG_CACHE_HOME': str(tmp_path / 'cache'),
    }
    if skip_session_start:
        env['PI_TEST_SKIP_SESSION_START'] = '1'
    return run_node(_m1_PREAMBLE + script, module_mocks=True, env_overrides=env)


def test_a_child_started_without_a_session_start_still_mounts_activity(tmp_path: Path) -> None:
    """The reload case: no session start, so nothing may depend on having seen one.

    `session_start` used to be the only place the extension adopted its activity
    context. An extension reloaded into a running session never sees one, so the
    roster callback still ran, the widget update received no context, and the child
    working above the editor was invisible for the rest of the session. The live
    context is available on every tool call, which is exactly when a child starts.
    """
    result = _m1_run("""
      // The host fires `tool_call` before it executes the tool, which is where the
      // live context reaches the extension when no session start has.
      await event('tool_call');
      const pending=call({name:'reloaded',prompt:'1+1'});
      const mountedWhileStarting=mounts.length;
      acknowledge(true);
      await pending;
      console.log(JSON.stringify({
        mountedWhileStarting,
        rows:lines().filter(line=>line.includes('reloaded')).length,
      }));
    """, tmp_path, skip_session_start=True)
    assert result['mountedWhileStarting'] > 0, 'a child starting without a session start still paints the widget'
    assert result['rows'] > 0


def test_widget_mounts_while_start_acknowledgement_is_pending(tmp_path: Path) -> None:
    result = _m1_run("""
      const pending=call({name:'calculator',prompt:'1+1',tools:[]});
      await Promise.resolve();
      const before=lines();
      const placements=mounts.filter(m=>m.mounted).map(m=>m.options?.placement);
      acknowledge(true);const started=await pending;
      console.log(JSON.stringify({before,placements,started:started.details.ok,renders}));
    """, tmp_path)
    assert any('calculator · Starting' in line for line in result['before'])
    assert result['placements'] == ['aboveEditor']
    assert result['started'] is True
    assert result['renders'] > 0


def test_widget_streams_sanitized_activity_and_drops_settled_children(tmp_path: Path) -> None:
    result = _m1_run("""
      const first=call({name:'first',prompt:'1+1'});acknowledge(true);await first;
      const second=call({name:'second',prompt:'2+3'});acknowledge(true);await second;
      spawns[0].onUpdate({text:'',liveThinking:'**Checking** arithmetic',turns:1,finalResponse:false});
      const thinking=lines();
      spawns[0].onUpdate({text:'',activeTool:'read: 文件\u001b[31m\\n'+ 'x'.repeat(200),turns:1,finalResponse:false});
      const tool=lines(40);
      const bounded=[12,40,90,240].every(width=>lines(width).every(line=>visibleWidth(line)<=width&&!line.includes('\\n')));
      spawns[0].onUpdate({text:'2',turns:1,finalResponse:true,answerComplete:true});
      const remaining=lines();
      spawns[1].onError(new Error('fixture startup failure'));await new Promise(resolve=>setImmediate(resolve));
      console.log(JSON.stringify({thinking,tool,bounded,remaining,widgets:widgets.size,results:sent.length}));
    """, tmp_path)
    assert any('first · Checking arithmetic' in line for line in result['thinking'])
    assert any('read: 文件' in line for line in result['tool'])
    # pi-tui may add its own Markdown styling; the foreign red escape is stripped.
    assert all('\x1b[31m' not in line for line in result['tool'])
    assert result['bounded'] is True
    # The settled child left the area; the one still working keeps its row, and the
    # failed startup never gets one.
    assert len(result['remaining']) == 1
    assert any('second' in line for line in result['remaining'])
    assert not any('first' in line for line in result['remaining'])
    # Once the working child fails too, the area is empty and the widget unmounts.
    assert result['widgets'] == 0
    assert result['results'] == 2


def test_hidden_thinking_shows_pis_label_instead_of_the_reasoning(tmp_path: Path) -> None:
    """The status row is the same reader's surface as the transcript.

    Pi hides thinking blocks when `hideThinkingBlock` is set, and this area used
    to stream the reasoning anyway. A reader who asked not to read thinking must
    not read it above the editor either, so the row shows Pi's own label, gray.
    """
    result = _m1_run("""
      const pending=call({name:'quiet',prompt:'1+1'});acknowledge(true);await pending;
      pi.getSettings=()=>({hideThinkingBlock:true});
      spawns[0].onUpdate({text:'',liveThinking:'**private reasoning**',turns:1,finalResponse:false});
      const thinking=lines();
      // The label is plain activity text, which the shared row paints muted.
      const gray=painted.some(([color,text])=>color==='muted'&&text.includes('Thinking'));
      spawns[0].onUpdate({text:'',liveThinking:'**private reasoning**',activeTool:'read: notes.md',turns:1,finalResponse:false});
      const tool=lines();
      // The label describes thinking, so answer text replaces it once it exists.
      spawns[0].onUpdate({text:'the answer',liveThinking:'**private reasoning**',turns:1,finalResponse:false});
      const answered=lines();
      pi.getSettings=()=>({hideThinkingBlock:false});
      spawns[0].onUpdate({text:'the answer',liveThinking:'**private reasoning** ',turns:1,finalResponse:false});
      const shown=lines();
      console.log(JSON.stringify({thinking,tool,answered,shown,gray}));
    """, tmp_path)
    assert len(result['thinking']) == 1
    assert 'quiet · Thinking...' in result['thinking'][0]
    assert 'private reasoning' not in result['thinking'][0]
    assert result['gray'] is True, 'the hidden-thinking label keeps the shared muted activity color'
    assert 'read: notes.md' in result['tool'][0]
    assert 'the answer' in result['answered'][0]
    assert 'Thinking' not in result['answered'][0]
    assert 'private reasoning' not in result['answered'][0]
    assert 'quiet · private reasoning' in result['shown'][0]


def test_settled_standalone_child_leaves_the_activity_area(tmp_path: Path) -> None:
    result = _m1_run("""
      const pending=call({name:'resident',prompt:'1+1'});acknowledge(true);const started=await pending;
      spawns[0].onUpdate({text:'2',liveThinking:'old thinking',activeTool:'old tool',turns:1,finalResponse:true,answerComplete:true});
      const settled=lines();
      // Settling leaves the activity area; the child is still addressable, so it is
      // found through the roster rather than by a stale row.
      const page=await call({ operation:'list' });
      const child=page.details.sessions.find((row)=>row.session===started.details.session);
      console.log(JSON.stringify({settled,ok:page.details.ok,status:child?.status,
        label:child?.label,results:sent.length}));
    """, tmp_path)
    assert result['settled'] == []
    assert result['ok'] is True
    assert result['status'] == 'idle'
    assert result['label'] == 'resident'
    assert result['results'] == 1


def test_unanswered_settlement_also_leaves_the_activity_area(tmp_path: Path) -> None:
    result = _m1_run("""
      const pending=call({name:'resident',prompt:'finish safely'});acknowledge(true);await pending;
      spawns[0].onUpdate({text:'',liveThinking:'stale thinking',activeTool:'stale tool',turns:1,finalResponse:true,answerComplete:false,missingFinal:true});
      const settled=lines();
      console.log(JSON.stringify({settled,results:sent.length}));
    """, tmp_path)
    # An unanswered turn settles the child like any other, so the row goes with it
    # and its stale stream text never reaches the activity area.
    assert result['settled'] == []
    assert result['results'] == 1


def test_settled_residents_leave_the_area_while_confirmed_closure_clears_the_rest(tmp_path: Path) -> None:
    result = _m1_run("""
      const pendingFirst=call({name:'stopped',prompt:'one'});acknowledge(true);const first=await pendingFirst;
      const pendingSecond=call({name:'idle',prompt:'two'});acknowledge(true);const second=await pendingSecond;
      spawns[0].onUpdate({text:'done',turns:1,finalResponse:true,answerComplete:true});
      spawns[1].onUpdate({text:'done',turns:1,finalResponse:true,answerComplete:true});
      // Roster updates address the generated name behind the handle, not the label.
      updateAgent(first.details.name,{status:'stopped'});
      const rows=lines();
      console.log(JSON.stringify({rows,widgets:widgets.size,labels:[first.details.label,second.details.label]}));
    """, tmp_path)
    assert result['labels'] == ['stopped', 'idle']
    # Both children settled, so neither occupies the area; both stay addressable.
    assert result['rows'] == []
    assert result['widgets'] == 0, "an empty activity area mounts no widget at all"


def test_unconfirmed_stop_stays_visible_as_stopping_until_close(tmp_path: Path) -> None:
    result = _m1_run("""
      const pending=call({name:'resident',prompt:'one'});acknowledge(true);const started=await pending;
      // The child is still working when the leader asks it to stop, which is the
      // only state in which a stopping row exists: a settled child has left the area.
      spawns[0].onUpdate({text:'done',liveThinking:'stale',turns:1,finalResponse:false});
      const name=started.details.name;
      assert.notEqual(name,'resident','the roster address is the generated name');
      updateAgent(name,{leaderRequestedEnd:true});
      const stopping=lines();
      updateAgent(name,{status:'stopped'});
      const closed=lines();
      console.log(JSON.stringify({stopping,closed}));
    """, tmp_path)
    assert len(result['stopping']) == 1
    assert 'resident' in result['stopping'][0]
    assert 'Stopping...' in result['stopping'][0]
    assert 'Idle' not in result['stopping'][0]
    assert 'stale' not in result['stopping'][0]
    assert '⠋' in result['stopping'][0]
    assert result['closed'] == []


@pytest.mark.parametrize('mode', ['print', 'json', 'rpc'])
def test_non_terminal_sessions_never_mount_activity(tmp_path: Path, mode: str) -> None:
    result = _m1_run("""
      const pending=call({name:'headless',prompt:'1+1'});acknowledge(true);await pending;
      spawns[0].onUpdate({text:'2',turns:1,finalResponse:true,answerComplete:true});
      console.log(JSON.stringify({mounts:mounts.length,widgets:widgets.size,results:sent.length}));
    """, tmp_path, mode)
    assert result == {'mounts': 0, 'widgets': 0, 'results': 1}


def test_coordinator_widget_is_not_duplicated_but_standalone_work_still_renders(tmp_path: Path) -> None:
    directory = tmp_path / '.pi' / 'agents' / 'standalone'
    directory.mkdir(parents=True)
    (directory / 'agent.md').write_text('---\nname: standalone\ndescription: Independent durable role\ntools: read\n---\nStandalone role\n', encoding='utf-8')
    result = _m1_run("""
      setAgentHost({start:()=>({ok:true,session:'session:hosted:s1'}),stop:async()=>({ok:true})});
      registerAgent(entry('hosted','s1'));
      const hosted=lines();
      // Release the host so the next start really spawns: while a host owns the
      // session, the widget belongs to that host and this entry paints nothing.
      setAgentHost(undefined);
      const pending=call({name:'standalone',prompt:'1+1'});acknowledge(true);await pending;
      const standalone=lines();
      console.log(JSON.stringify({hosted,standalone}));
    """, tmp_path)
    assert result['hosted'] == []
    assert len(result['standalone']) == 1
    assert 'standalone' in result['standalone'][0]


def test_session_switch_remounts_and_shutdown_unsubscribes(tmp_path: Path) -> None:
    result = _m1_run("""
      const pending=call({name:'lifecycle',prompt:'1+1'});acknowledge(true);const started=await pending;
      const first=lines();await event('session_start');const restored=lines();
      await event('session_shutdown');const mountCount=mounts.length;
      // Address the real roster entry, so the no-remount claim is proven against
      // a live update rather than against a name nothing is filed under.
      updateAgent(started.details.name,{activeTool:'late progress'});
      console.log(JSON.stringify({first,restored,widgets:widgets.size,lateMounts:mounts.length-mountCount}));
    """, tmp_path)
    assert len(result['first']) == 1
    assert len(result['restored']) == 1
    assert result['widgets'] == 0
    assert result['lateMounts'] == 0


def test_the_activity_area_names_a_child_by_one_identifier_token(tmp_path: Path) -> None:
    """The working row above the editor is a display surface too: it reads the
    roster label, so it carries the same one-token name as every other row."""
    result = _m1_run("""
      const pending=call({name:'Task SQL measured optimization',prompt:'1+1'});acknowledge(true);await pending;
      console.log(JSON.stringify({rows:lines()}));
    """, tmp_path)
    assert len(result['rows']) == 1
    assert 'task-sql-measured-optimization' in result['rows'][0]
    assert 'Task SQL measured optimization' not in result['rows'][0]


# --- Merged from test_agent_row_tui.py ---
"""The intent family's transcript rows.

Contract: features/agent-row-tui.feature

The package entry is what Pi loads, so the entry is what binds the shared
lifecycle renderer. Driving the intent family with an injected spawn and
painting through the *entry-registered* renderer keeps the two halves of the
contract separate: this asserts the row a person sees, not the receipt text the
model reads.
"""


import json
from pathlib import Path

from subagents_helpers import PACKAGE, SRC, run_isolated_node as run_node



_m2_ENTRY = (PACKAGE / "index.ts").as_uri()
INTENT_TOOLS = (SRC / "intent-tools.ts").as_uri()
ROSTER = (SRC / "roster.ts").as_uri()

_m2_PREAMBLE = f"""
import assert from "node:assert/strict";
import {{ stripVTControlCharacters }} from "node:util";
import {{ KeybindingsManager, setKeybindings, visibleWidth }} from "@earendil-works/pi-tui";
import {{ initTheme }} from "@earendil-works/pi-coding-agent";
import piSubagentsExtension from {json.dumps(_m2_ENTRY)};
import {{ executeIntentTool }} from {json.dumps(INTENT_TOOLS)};

const theme = {{ fg: (_name, text) => text, bg: (_name, text) => text, bold: (text) => text }};
const calls = [];
const messageRenderers = new Map();
const pi = {{ registerTool: (tool) => calls.push(tool), registerMessageRenderer: (name, renderer) => messageRenderers.set(name, renderer), on() {{}}, events: {{ emit() {{}} }} }};
piSubagentsExtension(pi);
const intentNames = ["agent_start", "agent_input", "agent_stop", "agent_list"];
const intentTools = new Map(calls.filter((tool) => intentNames.includes(tool.name)).map((tool) => [tool.name, tool]));
assert.equal(intentTools.size, intentNames.length, "the extension entry registers the intent family");
assert.equal(calls.some((tool) => tool.name === "agent"), false, "the retired tool is not registered");
for (const tool of intentTools.values()) {{
  assert.equal(typeof tool.renderResult, "function", "the entry must bind the lifecycle result renderer");
  assert.deepEqual(tool.renderCall().render(), [], "the started call line stays empty");
}}

const width = 120;
const paint = (operation, result, expanded, renderWidth = width) => {{
  const component = intentTools.get(operation).renderResult(
    {{ content: result.content, details: result.details }},
    {{ expanded, isPartial: false }},
    theme,
    {{ args: {{}}, toolCallId: "row", isError: result.isError === true }},
  );
  assert.ok(component && typeof component.render === "function", "the renderer returns a component");
  const rows = component.render(renderWidth).map(stripVTControlCharacters);
  assert.ok(rows.every((row) => visibleWidth(row) <= renderWidth), `row exceeds ${{renderWidth}} columns:\\n${{rows.join("\\n")}}`);
  return rows;
}};
const band = (rows) => rows.filter((row) => row.trim());
// The rows a person reads come from the intent family, so every scenario drives
// one intent tool and paints the result of the tool it called. Only the spawn is
// injected; the row geometry, the receipt, and the selection all stay real.
const options = {{
  cwd: process.env.PI_TEST_CWD,
  spawn: () => ({{ pid: 7 }}),
  steer: async () => true,
  terminate: async () => ({{ outcome: "closed" }}),
}};
const run = async (request) => {{
  const {{ operation, label, session, prompt, delivery, tools, ...rest }} = request;
  const toolName = operation === "input" || operation === "steer" ? "agent_input"
    : operation === "stop" ? "agent_stop"
    : operation === "list" ? "agent_list" : "agent_start";
  const params = toolName === "agent_start"
    ? {{ ...(prompt === undefined ? {{}} : {{ prompt }}), ...(label === undefined ? {{}} : {{ label }}), ...(tools === undefined ? {{}} : {{ tools }}), ...rest }}
    : toolName === "agent_input" ? {{ session, prompt, delivery: operation === "steer" ? "steer" : delivery ?? "next" }}
    : toolName === "agent_list" ? {{ ...rest }} : {{ session, ...rest }};
  const result = await executeIntentTool(toolName, params, options);
  return {{ ...result, operation: toolName }};
}};
"""


def _m2_run(script: str) -> None:
    run_node(f"{_m2_PREAMBLE}\n{script}")


def run_isolated(script: str, tmp_path: Path) -> None:
    """A run with its own agent directory and working tree, for the rows that need
    a saved definition. Isolated because a project identity creates its folder
    under the agent directory, and a row test must not write into the developer's
    own."""
    run_node(
        f"{_m2_PREAMBLE}\n{script}",
        env_overrides={
            "PI_TEST_CWD": str(tmp_path),
            "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
            "HOME": str(tmp_path),
            "XDG_CONFIG_HOME": str(tmp_path),
        },
    )


def test_disk_identity_facts_stay_off_the_collapsed_row_and_expand_once(tmp_path: Path) -> None:
    """Scope and canonical source are configuration, not the collapsed deliverable.
    The receipt keeps both facts for the model, and the roster row prints each of
    them once as expansion detail."""
    directory = tmp_path / ".pi" / "agents" / "saved-row"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent.md").write_text(
        "---\nname: saved-row\ndescription: inspect one file\ntools: read\n---\nSAVED BODY\n",
        encoding="utf-8",
    )
    run_isolated(
        """
        const cwd = process.env.PI_TEST_CWD;
        const started = await run({ operation: "start", identity: "saved-row", prompt: "Check the ledger." });
        assert.equal(started.details.ok, true, started.content[0].text);
        assert.equal(started.details.scope, "project");
        assert.equal(started.details.source, `${cwd}/.pi/agents/saved-row/agent.md`);
        assert.ok(!("persistent" in started.details) && !("sessionNote" in started.details));
        const collapsed = band(paint("agent_start", started, false));
        assert.match(collapsed[0], /^\\s*\\[agent\\] started · @saved-row · starting/, collapsed[0]);
        assert.equal(collapsed[1].trim(), "Check the ledger.");
        assert.equal(collapsed.length, 2, `the collapsed row is one band:\\n${collapsed.join("\\n")}`);
        assert.equal(collapsed[0].split("@saved-row").length - 1, 1, "the name appears once");
        assert.ok(!collapsed.join("\\n").includes(started.details.source), collapsed.join("\\n"));
        assert.ok(!collapsed.join("\\n").includes("scope ·"), collapsed.join("\\n"));
        assert.ok(!collapsed.join("\\n").includes("cwd ·") && !collapsed.join("\\n").includes("workspace ·"), collapsed.join("\\n"));
        // The roster is where a person looks a retained child up, so it carries
        // the configuration facts the collapsed row keeps to itself.
        const listed = await run({ operation: "list" });
        const roster = band(paint("agent_list", listed, false));
        assert.match(roster[0], /^\\s*\\[agent\\] listed · /, roster[0]);
        assert.ok(!/\\d+ of \\d+/.test(roster[0]), `a page that omitted nothing carries no count:\n${roster[0]}`);
        assert.equal(roster.length, 1, "a roster subject names no child on its own row");
        assert.ok(!roster[0].includes(started.details.source), roster[0]);
        const expanded = paint("agent_list", listed, true).join("\\n");
        assert.ok(expanded.includes("scope · project"), expanded);
        // Width fitting can wrap a canonical path, so compare the visible
        // characters across rows without requiring one unbroken line.
        const fitted = expanded.replace(/\\s+/g, "");
        const source = `source·${started.details.source}`;
        assert.ok(fitted.includes(source), expanded);
        assert.equal(fitted.split(source).length - 1, 1, expanded);
        console.log(JSON.stringify({ ok: true }));
        """,
        tmp_path,
    )


def test_a_started_child_renders_one_band_naming_it_and_its_work() -> None:
    _m2_run(
        """
        const started = await run({
          operation: "start",
          label: "row-tui",
          prompt: "Add the ledger row.\\nThen check the widget.",
          tools: ["read"],
        });
        assert.equal(started.details.disposition, "started", started.content[0].text);
        const collapsed = band(paint("agent_start", started, false));
        assert.equal(collapsed.length, 2, `the collapsed row is one band plus its headline:\\n${collapsed.join("\\n")}`);
        assert.match(collapsed[0], /\\[agent\\] started · @row-tui · starting/, collapsed[0]);
        assert.equal(collapsed[0].split("@row-tui").length - 1, 1, `the name appears once:\\n${collapsed[0]}`);
        assert.equal(collapsed[1].trim(), "Add the ledger row. Then check the widget.");
        // The handle is the model's addressing mechanism and a person's noise.
        assert.ok(!/session:|\\b[0-9a-f]{8}-[0-9a-f]{4}-/.test(collapsed[0]), `row leaked a handle:\\n${collapsed[0]}`);

        const expanded = paint("agent_start", started, true);
        assert.ok(expanded.some((row) => row.trim() === "Add the ledger row."), `expanded row dropped a line:\\n${expanded.join("\\n")}`);
        assert.ok(expanded.some((row) => row.trim() === "Then check the widget."), `expanded row clipped the prompt:\\n${expanded.join("\\n")}`);
        const text = expanded.join("\\n");
        // Startup configuration stays; runtime handles and state words do not.
        assert.ok(text.includes("tools · read"), text);
        assert.equal(text.split("tools · read").length - 1, 1, text);
        for (const noise of [`session · ${started.details.session}`, "state · starting", "next · runtime"]) {
          assert.ok(!text.includes(noise), `expanded row printed ${noise}:\\n${text}`);
        }
        assert.equal(started.details.session, started.structuredContent.session);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_startup_model_metadata_is_rendered_once_without_changing_the_receipt() -> None:
    _m2_run(
        """
        const model = "cli-proxy/gpt-6.1-sol";
        const started = await run({
          operation: "start", label: "row-model",
          prompt: "Review the TUI state.", model, tools: ["read"],
        });
        assert.equal(started.details.ok, true, started.content[0].text);
        assert.equal(started.details.model, model);
        assert.ok(started.content[0].text.includes(`Model: ${model}`), "model-facing receipt is preserved");
        const collapsed = band(paint("agent_start", started, false));
        assert.ok(!collapsed.join("\\n").includes(model), `collapsed row leaked configuration:\\n${collapsed.join("\\n")}`);
        const expanded = paint("agent_start", started, true).join("\\n");
        assert.ok(expanded.includes(`model · ${model}`), expanded);
        assert.equal(expanded.split(model).length - 1, 1, `expanded model is repeated:\\n${expanded}`);
        assert.ok(!expanded.includes("MODEL ·"), expanded);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_prompt_less_start_is_refused_because_the_family_has_no_idle_startup() -> None:
    """The family starts a child with work or it does not start one. There is no
    idle child to prompt later, so a prompt-less start is a refusal and the row
    has to say so instead of waiting."""
    _m2_run(
        """
        initTheme("dark", false);
        setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }));
        assert.ok(intentTools.get("agent_start").parameters.required.includes("prompt"),
          "the schema requires the work the child would run");
        const refused = await run({ operation: "start", label: "row-idle" });
        assert.equal(refused.details.ok, false);
        assert.equal(refused.details.code, "invalid-parameters");
        assert.equal(refused.details.disposition, "rejected");
        const collapsed = band(paint("agent_start", refused, false));
        assert.match(collapsed[0], /^\\s*\\[agent\\] rejected · @child · ctrl\\+o to expand/, collapsed[0]);
        assert.equal(collapsed[1].trim(), "prompt must be a nonempty string for agent_start.");
        assert.ok(paint("agent_start", refused, true).join("\\n").includes("prompt must be a nonempty string for agent_start."));
        // A refused start leaves nothing to address, so no row ever offers a
        // handle for a child that does not exist.
        const listed = await run({ operation: "list" });
        assert.deepEqual(listed.details.sessions, []);
        const emptyRoster = band(paint("agent_list", listed, false))[0];
        assert.match(emptyRoster, /^\\s*\\[agent\\] listed · /, emptyRoster);
        assert.ok(!/\\d+ of \\d+/.test(emptyRoster), `an empty roster carries no count:\n${emptyRoster}`);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_coordination_only_grant_is_disclosed_however_it_was_asked_for() -> None:
    """`tools: []` leaves the child exactly as unable to read as an unnamed grant,
    so the row says the same thing either way. Warning only about the unnamed one
    would hide the cost of the deliberate choice from the person who made it."""
    _m2_run(
        """
        const deliberate = await run({ operation: "start", label: "row-plain", prompt: "Compute 1+1.", tools: [] });
        const unasked = await run({ operation: "start", label: "row-unasked", prompt: "Compute 1+1." });
        for (const result of [deliberate, unasked]) {
          const collapsed = band(paint("agent_start", result, false)).join("\\n");
          assert.ok(!collapsed.includes("tools"), `the grant is expansion detail:\\n${collapsed}`);
          assert.match(paint("agent_start", result, true).join("\\n"), /tools · none/);
        }
        // A child that was granted read has nothing to warn about.
        const reader = await run({ operation: "start", label: "row-reader", prompt: "Read it.", tools: ["read"] });
        const granted = paint("agent_start", reader, true).join("\\n");
        assert.ok(granted.includes("tools · read"), granted);
        assert.ok(!granted.includes("tools · none"), "a granted child is not reported as having none");
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_parent_message_row_keeps_body_and_rejects_malformed_details() -> None:
    _m2_run(
        """
        const renderer = messageRenderers.get("subagents-parent-message");
        assert.equal(typeof renderer, "function", "the entry binds an independent parent-message renderer");
        const details = { kind: "intermediate", name: "worker", session: "session:worker:incarnation", inputId: "input-1", sequence: 1, text: "**Keep** this body", deliveredAt: 0 };
        const collapsed = renderer({ content: details.text, details }, { expanded: false }, theme).render(100).join("\\n");
        const expanded = renderer({ content: details.text, details }, { expanded: true }, theme).render(100).join("\\n");
        assert.match(collapsed, /\\[agent\\] message · @worker/);
        assert.ok(expanded.includes("Keep"), expanded);
        assert.ok(!expanded.includes("session · session:worker:incarnation") && !expanded.includes("input · input-1") && !expanded.includes("sequence ·"), expanded);
        const malformed = renderer({ content: "ignored", details: { kind: "intermediate", name: "worker", session: "session:worker:incarnation", sequence: 1e20, text: "body", deliveredAt: 1e20 } }, { expanded: true }, theme).render(100).join("\\n");
        assert.ok(malformed.includes("intermediate message details were invalid"), malformed);
        const missingTimestamp = renderer({ content: "ignored", details: { kind: "intermediate", name: "worker", session: "session:worker:incarnation", sequence: 1, text: "body" } }, { expanded: true }, theme).render(100).join("\\n");
        assert.ok(missingTimestamp.includes("intermediate message details were invalid"), missingTimestamp);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_long_single_line_steer_is_expandable_without_losing_its_first_line_tail() -> None:
    _m2_run(
        """
        initTheme("dark", false);
        setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }));
        const started = await run({ operation: "start", label: "review-agent-boundary", prompt: "Review", tools: [] });
        const prompt = "steering ".repeat(45) + "REQUIRED_STEER_TAIL";
        const result = await run({ operation: "input", delivery: "steer", session: started.details.session, prompt });
        assert.equal(result.details.ok, true, result.content[0].text);
        assert.equal(result.details.disposition, "steered");
        assert.equal(result.details.prompt, prompt);
        const before = JSON.stringify(result);
        const collapsed = band(paint("agent_input", result, false, 80));
        assert.match(collapsed[0], /\\[agent\\] steered · @review-agent-boundary · starting · ctrl\\+o to expand/, collapsed[0]);
        assert.ok(collapsed[1].trim().startsWith("steering steering steering"), `the steer headline stays on the row:\\n${collapsed[1]}`);
        assert.ok(!collapsed.join("\\n").includes(result.details.session));
        const expanded = paint("agent_input", result, true, 80).join("\\n");
        assert.equal(expanded.split("REQUIRED_STEER_TAIL").length - 1, 1, "expanded steer must include the first-line tail exactly once");
        assert.equal(expanded.split("steering").length - 1, 45, "the authored input must be rendered once, not headline plus body");
        assert.ok(!expanded.includes(`session · ${result.details.session}`), expanded);
        assert.ok(!expanded.includes("state · starting") && !expanded.includes("next · runtime"), expanded);
        assert.equal(result.details.session, result.structuredContent.session);
        assert.equal(band(paint("agent_input", result, false, 80)).join("\\n"), collapsed.join("\\n"));
        assert.equal(JSON.stringify(result), before);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_short_input_stays_readable_without_runtime_metadata() -> None:
    _m2_run(
        """
        initTheme("dark", false);
        setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }));
        for (const delivery of ["next", "steer"]) {
          const started = await run({ operation: "start", label: `row-${delivery}`, prompt: "Work.", tools: [] });
          const prompt = "Only the number";
          const result = await run({ operation: delivery, session: started.details.session, prompt });
          assert.equal(result.details.ok, true, result.content[0].text);
          const collapsed = band(paint("agent_input", result, false));
          // A short input shows its whole authored body on the row. Whether a
          // delivery still has substantive startup facts to expand is its own
          // business; runtime handles are never part of either state.
          assert.ok(collapsed.join("\\n").includes(prompt), collapsed.join("\\n"));
          assert.equal(collapsed[1].trim(), prompt);
          assert.ok(!collapsed.join("\\n").includes(result.details.session), collapsed.join("\\n"));
          const expanded = paint("agent_input", result, true).join("\\n");
          assert.equal(expanded.split(prompt).length - 1, 1, expanded);
          assert.ok(!expanded.includes(`session · ${result.details.session}`), expanded);
          assert.ok(!expanded.includes("state · starting") && !expanded.includes("next · runtime"), expanded);
          assert.equal(result.details.session, result.structuredContent.session);
        }
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_multiline_input_keeps_first_and_later_paragraphs_once() -> None:
    _m2_run(
        """
        const prompt = "FIRST_AUTHORED_LINE\\n\\nSECOND_AUTHORED_LINE";
        const started = await run({ operation: "start", label: "row-multiline", prompt });
        const queued = await run({ operation: "input", delivery: "next", session: started.details.session, prompt });
        for (const result of [started, queued]) {
          const text = paint(result.operation, result, true).join("\\n");
          assert.equal(text.split("FIRST_AUTHORED_LINE").length - 1, 1, text);
          assert.equal(text.split("SECOND_AUTHORED_LINE").length - 1, 1, text);
          assert.ok(/FIRST_AUTHORED_LINE\\s*\\n\\s*\\n\\s*SECOND_AUTHORED_LINE/.test(text), text);
        }
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_rendered_row_advertises_expansion_through_the_configured_key() -> None:
    _m2_run(
        """
        initTheme("dark", false);
        setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }));
        const started = await run({
          operation: "start",
          label: "row-hint",
          prompt: `${"evidence ".repeat(60)}TAIL`,
        });
        const collapsed = band(paint("agent_start", started, false));
        assert.match(collapsed[0], /to expand/, `a clipped row must advertise expansion:\\n${collapsed[0]}`);
        // The affordance belongs to the collapsed row alone: the expanded row has
        // nothing left to open.
        assert.ok(!paint("agent_start", started, true).join("\\n").includes("to expand"));
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_roster_page_that_hides_entries_carries_the_count(tmp_path: Path) -> None:
    """The count is the one fact a collapsed page cannot state any other way.

    A page that returned the whole roster says nothing about size, because there is
    nothing it is hiding. A page that omitted an entry is the case that has to say
    so without being opened, and the count is how it says it.
    """
    run_isolated(f"""
        import {{ registerAgent, resetRoster }} from {json.dumps(ROSTER)};
        resetRoster();
        for (let index = 0; index < 21; index += 1) {{
          registerAgent({{ name: `child-${{index}}`, role: "worker", spawnId: `s${{index}}`, pid: index,
            status: "stopped", scope: "session", createdAt: 1, updatedAt: 1 }});
        }}
        const listed = await run({{ operation: "list" }});
        const collapsed = band(paint("agent_list", listed, false))[0];
        assert.equal(listed.details.page.returned, 20, collapsed);
        assert.equal(listed.details.page.omitted, 1, collapsed);
        assert.match(collapsed, /^\\s*\\[agent\\] listed · 20 of 21/, collapsed);
        console.log(JSON.stringify({{ ok: true }}));
        """, tmp_path)
