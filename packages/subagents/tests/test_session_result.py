from __future__ import annotations

# --- Merged from test_session_result.py ---
# --- Merged from test_session_result.py ---
"""Session Result delivery from a standalone child.

Contract: features/session-result.feature

One seam: the package extension entry with a fake `ExtensionAPI`. The entry is
the highest boundary that owns both halves of the feature — the intent tools,
the message renderers, and the sender — so these tests drive the real registered
tools with an injected spawn, feed them the progress frames the real spawner
emits, and assert on the messages that were sent. Nothing here reaches into the
delivery module. The tools are addressed through the `start` adapter in the
PREAMBLE, so a scenario reads as one intent rather than five tool calls.
"""


import json
import os
import subprocess
import tempfile
from pathlib import Path

from subagents_helpers import PACKAGE, run_isolated_node as run_node



ENTRY = (PACKAGE / "index.ts").as_uri()
BARREL = (PACKAGE / "index.ts").as_uri()
SPAWNER = (PACKAGE / "src" / "spawner.ts").as_uri()

# The real entry, the real tools, the real delivery — with only the child process
# faked. Mocking the spawner module rather than injecting a spawn function is what
# makes this the package's public surface: the entry wires its own delivery in,
# and a test that injected the spawn itself would be testing a tool the entry
# never registered.
PREAMBLE = f"""
import assert from "node:assert/strict";
import {{ mock }} from "node:test";
import {{ stripVTControlCharacters }} from "node:util";
import {{ initTheme }} from "@earendil-works/pi-coding-agent";
import {{ KeybindingsManager, setKeybindings }} from "@earendil-works/pi-tui";
import * as spawner from {json.dumps(SPAWNER)};
import {{ sessionNoticeSpec }} from {json.dumps((PACKAGE / 'src' / 'session-result.ts').as_uri())};

// One spawn, one captured callback set: the frames below are the real shapes
// `spawnResident` hands `onUpdate`, so delivery is driven by the spawner's own
// contract rather than by a test-only path. The resident-wake and termination
// helpers are counted rather than faked blind, so a test can prove the prompt
// reached the child exactly once and that a stop reached the terminator.
let frames;
let exits;
const wakes = [];
const terminations = [];
mock.module({json.dumps(SPAWNER)}, {{
  namedExports: {{
    ...spawner,
    spawnResident: (options) => {{ frames = options.onUpdate; exits = options.onExit; return {{ pid: 4242 }}; }},
    deliverPrompt: (name, message) => {{ wakes.push({{ name, message }}); return true; }},
    deliverResidentPrompt: async (name, message) => {{ wakes.push({{ name, message }}); return true; }},
    terminateAgent: async (name) => {{ terminations.push(name); return {{ outcome: "closed" }}; }},
  }},
}});

const {{ default: piSubagentsExtension, setAgentHost, registerAgent }} = await import({json.dumps(ENTRY)});

const sent = [];
const renderers = new Map();
const registered = [];
const pi = {{
  registerTool: (tool) => registered.push(tool),
  registerMessageRenderer: (type, renderer) => renderers.set(type, renderer),
  on() {{}},
  events: {{ emit() {{}} }},
  sendMessage: (message, options) => {{ sent.push({{ ...message, options: options ?? {{}} }}); }},
}};
piSubagentsExtension(pi);
assert.ok(registered.some((tool) => tool.name === "agent_start"), "the entry registers the intent tools");

const ctx = {{ cwd: process.env.PI_TEST_CWD }};
const intentTools=new Map(registered.filter(t=>t.name.startsWith("agent_")).map(t=>[t.name,t]));
const start=(request)=>{{
  const {{operation,name,session,prompt,tools:grant,...rest}}=request;
  const tool=operation==="input"||operation==="steer"?"agent_input"
    :operation==="stop"?"agent_stop":operation==="list"?"agent_list":"agent_start";
  const params=tool==="agent_start"
    ?{{prompt:prompt??"Start the assigned work.",...(name===undefined?{{}}:{{label:name}}),...(grant===undefined?{{}}:{{tools:grant}}),...rest}}
    :tool==="agent_input"?{{session,prompt,delivery:operation==="steer"?"steer":"next"}}:session===undefined?{{...rest}}:{{session,...rest}};
  return intentTools.get(tool).execute("row",params,undefined,undefined,ctx);
}};
const settle = (text) => frames({{ text, turns: 1, finalResponse: true, modelOutputSeen: true }});
const beginTurn = () => frames({{ text: "", turns: 0, finalResponse: false, modelOutputSeen: true }});
const results = () => sent.filter((message) => message.customType === "subagents-session-result");
const ended = () => sent.filter((message) => message.customType === "subagents-session-ended");
const theme = {{ fg: (_name, text) => text, bg: (_name, text) => text, bold: (text) => text }};
const paint = (message, expanded, width = 90) => stripVTControlCharacters(
  renderers.get(message.customType)(message, {{ expanded }}, theme).render(width).map((row) => row.replace(/\\s+$/, "")).join("\\n"),
);
"""


def _s0_run(script: str) -> None:
    with tempfile.TemporaryDirectory(prefix="subagents-session-result-") as root:
        run_node(f"{PREAMBLE}\n{script}", module_mocks=True, env_overrides={"PI_CODING_AGENT_DIR": root, "HOME": root})


def test_a_prompted_childs_answer_is_delivered_verbatim_with_its_provenance() -> None:
    _s0_run(
        """
        const started = await start({ operation: "start", name: "solo", prompt: "Reply with the number 1+1.", tools: [] });
        assert.equal(started.details.ok, true, started.content[0].text);
        assert.equal(started.details.disposition, "started", "the intent receipt names the disposition, not a legacy outcome");
        assert.deepEqual(results(), [], "the receipt is not a delivery");
        beginTurn();
        settle("2");
        const delivered = results();
        assert.equal(delivered.length, 1, `one settled turn, one delivery:\\n${JSON.stringify(sent)}`);
        const [message] = delivered;
        assert.ok(message.content.includes("2"), `the child's text was not carried: ${message.content}`);
        // The child's words are the body; a provenance line names the source and
        // never rewrites what the child said.
        // The envelope names the Agent by its bare name, matching the harness
        // report family; the leading `@` is the row's human-facing convention.
        assert.match(message.content, /from="solo"/);
        assert.equal(message.options.deliverAs, "followUp");
        assert.equal(message.options.triggerTurn, true);
        assert.equal(message.details.label ?? message.details.name, "solo");
        assert.match(message.details.session, /^session:/);
        assert.equal(message.details.label ?? message.details.name, "solo", "the intent family names the child by its label, not by its generated name");
        assert.equal(message.details.turn, 1);
        // A settled child stays resident and addressable, and this delivery is the
        // only place that says so. A Leader that reads no such line spends a whole
        // new process on a follow-up the child it already holds could have taken.
        const continuation = message.content.split("\\n").find((line) => line.includes("agent_input"));
        assert.ok(continuation, `the delivery never says the child can be continued: ${message.content}`);
        assert.match(continuation, /IDLE/);
        assert.match(continuation, /not acceptance/);
        // The child's words stay the body: the guidance is envelope text above it.
        assert.ok(message.content.endsWith("2\\n</agent-result>"), message.content);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_one_delivery_per_settled_turn_not_per_frame() -> None:
    _s0_run(
        """
        await start({ operation: "start", name: "solo", prompt: "Work.", tools: [] });
        beginTurn();
        frames({ text: "par", turns: 1, finalResponse: false, modelOutputSeen: true });
        frames({ text: "partial", turns: 1, finalResponse: false, modelOutputSeen: true });
        assert.deepEqual(results(), [], "streaming frames are not deliveries");
        settle("the final answer");
        settle("the final answer");
        frames({ text: "the final answer", turns: 1, finalResponse: true, modelOutputSeen: true });
        assert.equal(results().length, 1, `settle must be an edge, not a level:\\n${JSON.stringify(sent)}`);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_every_wake_of_a_resident_child_is_delivered() -> None:
    _s0_run(
        """
        const first=await start({ operation: "start", name: "solo", prompt: "First question.", tools: [] });
        beginTurn();
        settle("first answer");
        assert.deepEqual(terminations, [], "settlement leaves a temporary resident alive");
        const second=await start({operation:"input",delivery:"next",session:first.details.session,prompt:"Second question."});
        assert.equal(second.details.ok,true,second.content[0].text);
        settle("second answer");
        assert.equal(wakes.length,1);
        assert.equal(wakes[0].message,"Second question.");
        const delivered = results();
        assert.equal(delivered.length, 2, `each settled turn is its own result:\\n${JSON.stringify(sent)}`);
        assert.ok(delivered[1].content.includes("second answer"));
        assert.equal(delivered[0].details.turn, 1);
        assert.equal(delivered[1].details.turn, 2);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_an_empty_settle_does_not_consume_the_turns_one_delivery() -> None:
    """The regression a live session found.

    A real child settles empty before it settles with its answer — the first
    settle closes a sequence that produced nothing. Treating that as the turn's
    result armed the dedupe, and the answer that followed was suppressed for the
    life of the Work Session: the Leader was told its work was in flight and
    nothing ever came back.
    """
    _s0_run(
        """
        await start({ operation: "start", name: "solo", prompt: "Reply with the number 1+1.", tools: [] });
        beginTurn();
        settle("");
        assert.deepEqual(results(), [], "the empty settle is not this turn's result");
        settle("2");
        const delivered = results();
        assert.equal(delivered.length, 1, `the answer after an empty settle must still arrive:\\n${JSON.stringify(sent)}`);
        assert.equal(delivered[0].details.text, "2", "the delivered result is the answer, not the empty text");
        assert.equal(delivered[0].details.turn, 1);
        // And the turn's one delivery is still one delivery.
        settle("2");
        assert.equal(results().length, 1, `a repeated settle is not a second result:\\n${JSON.stringify(sent)}`);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_short_result_is_rendered_once_without_bookkeeping_or_expansion_hint() -> None:
    _s0_run(
        """
        initTheme("dark", false);
        setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }));
        await start({ name: "calculator", prompt: "Calculate 1+1.", tools: [] });
        beginTurn();settle("2");
        const [message] = results();
        const content = message.content;
        const details = structuredClone(message.details);
        for (const expanded of [false, true]) {
          const row = paint(message, expanded);
          const visible = row.split("\\n").map(line => line.trim()).filter(Boolean);
          // Collapsed, the row is the headline and the answer waits; expanded, the
          // answer appears once, below it.
          assert.deepEqual(visible, expanded
            ? ["[agent] reported · @calculator", "2"]
            : ["[agent] reported · @calculator · ctrl+o to expand"]);
          assert.ok(!row.includes("Session Result") && !/turn [0-9]/.test(row), row);
        }
        assert.equal(message.content, content, "rendering cannot change the model-facing answer");
        assert.deepEqual(message.details, details, "turn/session remain machine metadata");
        assert.equal(message.details.text, "2");assert.equal(message.details.turn, 1);
        assert.match(message.details.session, /^session:/);
        assert.equal(message.details.label ?? message.details.name, "calculator", "the notice keeps the child name the handle was copied from");
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_multiline_result_preserves_authored_text_once_on_expansion() -> None:
    _s0_run(
        """
        initTheme("dark", false);
        setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }));
        await start({ name: "multiline", prompt: "Return evidence.", tools: [] });
        beginTurn();
        const text = "FIRST_RESULT_LINE\\n\\nSECOND_RESULT_LINE\\nFIRST_RESULT_LINE";
        settle(text);const [message] = results();
        const collapsed = paint(message, false, 70);
        assert.ok(collapsed.includes("to expand"), collapsed);
        const expanded = paint(message, true, 70);
        assert.equal(expanded.split("FIRST_RESULT_LINE").length - 1, 2, "only authored repeats survive");
        assert.equal(expanded.split("SECOND_RESULT_LINE").length - 1, 1, expanded);
        assert.ok(!expanded.includes("Session Result"), expanded);
        assert.equal(message.details.text, text);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_long_single_line_uses_terminal_width_and_retains_expanded_tail() -> None:
    _s0_run(
        """
        initTheme("dark", false);
        setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }));
        await start({ name: "long-result", prompt: "Return a long line.", tools: [] });beginTurn();
        const text = "word ".repeat(55) + "REQUIRED_RESULT_TAIL";settle(text);
        const [message] = results();
        const narrow = paint(message, false, 60);
        // The answer is expansion detail now: the collapsed row is the headline
        // plus the affordance, and the tail survives expansion whole.
        assert.ok(!narrow.includes("REQUIRED_RESULT_TAIL"), narrow);
        assert.ok(narrow.includes("to expand"), narrow);
        const expanded = paint(message, true, 60);
        assert.equal(expanded.split("REQUIRED_RESULT_TAIL").length - 1, 1, expanded);
        assert.ok(expanded.split("\\n").every(line => line.length <= 120), expanded);
        const wide = paint(message, false, 400);
        assert.ok(!wide.includes(text), wide);
        assert.ok(wide.includes("to expand"), wide);
        assert.equal(message.details.text, text);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_reported_body_renders_markdown_without_mutating_final_text() -> None:
    _s0_run(
        r'''
        const { visibleWidth } = await import("@earendil-works/pi-tui");
        await start({name:"markdown",prompt:"Return formatted evidence.",tools:[]});beginTurn();
        const text = "## Findings\n\n- **Important**: use `agent_input`.\n\n```ts\nconst result = 2;\n```";
        settle(text);const [message]=results();const before=JSON.stringify(message);
        const rendered=paint(message,true,48);
        assert.ok(rendered.includes("Findings") && rendered.includes("Important"),rendered);
        assert.ok(!rendered.includes("## Findings") && !rendered.includes("**Important**"),rendered);
        // Native Markdown retains fence-shaped borders, but indents and styles code separately.
        assert.ok(rendered.includes("  const result = 2;"),rendered);
        assert.equal(rendered.split("const result = 2;").length-1,1,rendered);
        assert.ok(rendered.split("\n").every(line=>visibleWidth(line)<=48),rendered);
        const styledTheme={...theme,fg:(token,value)=>`\x1b[36m${value}\x1b[39m`,bold:value=>`\x1b[1m${value}\x1b[22m`};
        const styled=renderers.get(message.customType)(message,{expanded:true},styledTheme).render(48).join("\n");
        assert.match(styled,/\x1b\[1m(?:\x1b\[[0-9;]*m)*Important(?:\x1b\[[0-9;]*m)*\x1b\[22m/,styled);
        assert.equal(JSON.stringify(message),before);
        settle("ignored duplicate");
        console.log(JSON.stringify({ok:true}));
        ''',
    )


def test_short_markdown_answer_has_no_markup_or_false_expansion_hint() -> None:
    _s0_run(
        r'''
        await start({name:"markdown-short",prompt:"Return one bold word.",tools:[]});beginTurn();
        settle("**Done**");const [message]=results();
        // Collapsed, the row is only the headline and the reader is told to expand.
        const collapsed=paint(message,false,70);
        assert.ok(collapsed.includes("reported"),collapsed);
        assert.ok(!collapsed.includes("Done"),collapsed);
        assert.ok(/to expand|ctrl\+o to expand/.test(collapsed),collapsed);
        // Expanded, the authored answer is complete and rendered as Markdown.
        const rendered=paint(message,true,70);
        assert.ok(rendered.includes("Done"),rendered);
        assert.ok(!rendered.includes("**"),rendered);
        assert.equal(message.details.text,"**Done**");
        console.log(JSON.stringify({ok:true}));
        ''',
    )


def test_a_child_that_ends_without_a_result_shows_one_visible_line_and_no_turn() -> None:
    _s0_run(
        """
        const started = await start({ operation: "start", name: "solo", prompt: "Work.", tools: [] });
        exits({ pid: 4242, exitCode: null, signal: "SIGKILL", stdout: "", stderr: "" });
        const notices = ended();
        assert.equal(notices.length, 1, `one death, one notice:\\n${JSON.stringify(sent)}`);
        const [notice] = notices;
        // A death is a terminal outcome a person must see, not a decision the
        // leader has to make. `triggerTurn: false` is spelled out because
        // *absent* means "not false", which pi reads as permission to steer the
        // turn in flight — the thing ADR-0002 exists to prevent.
        assert.equal(notice.options.triggerTurn, false, "an ended notice must never request a turn");
        assert.equal(notice.options.deliverAs, "nextTurn", "and must not interrupt the turn in flight");
        assert.equal(notice.display, true);
        assert.ok(!notice.content.includes("Work."), "the notice carries no result text");
        const painted = paint(notice, true);
        assert.match(painted, /@solo/, painted);
        // The roster is where a person reads a retained child's exit detail, and
        // it keeps the stopped state of the exact incarnation named earlier.
        const listed = await start({ operation: "list" });
        const retained = listed.details.sessions.find((entry) => entry.session === started.details.session);
        assert.ok(retained, `the roster keeps the stopped incarnation:\n${JSON.stringify(listed.details.sessions)}`);
        assert.ok(retained.error, "the roster keeps the exit detail");
        assert.equal(retained.status, "stopped");
        assert.ok(!listed.isError, listed.content[0].text);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_death_that_leaves_a_later_turn_unanswered_is_announced() -> None:
    _s0_run(
        """
        await start({ operation: "start", name: "solo", prompt: "First question.", tools: [] });
        beginTurn();
        settle("first answer");
        beginTurn();
        exits({ pid: 4242, exitCode: null, signal: "SIGKILL", stdout: "", stderr: "" });
        // Answering turn 1 does not silence a death during turn 2: the Leader
        // still has a question with no answer.
        assert.equal(ended().length, 1, `an unanswered turn must still be announced:\\n${JSON.stringify(sent)}`);
        assert.equal(results().length, 1);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_shutdown_the_leader_asked_for_is_not_reported_as_a_death() -> None:
    _s0_run(
        """
        const started = await start({ operation: "start", name: "solo", tools: [] });
        const stopped = await start({ operation: "stop", session: started.details.session });
        assert.equal(stopped.details.ok, true, stopped.content[0].text);
        assert.equal(stopped.details.disposition, "stopped");
        // The terminator is addressed by the roster name behind the handle, never
        // by the display label the caller wrote.
        assert.deepEqual(terminations, [started.details.name], "the stop reached the terminator");
        assert.match(started.details.session, /^session:subagent-[0-9a-f]+:/);
        assert.equal(stopped.details.label, "solo", "the receipt keeps the caller's display label");
        exits({ pid: 4242, exitCode: null, signal: "SIGTERM", stdout: "", stderr: "" });
        // The stop receipt is the report. Painting SIGTERM on the failure band
        // would tell a person their own shutdown was a death.
        assert.deepEqual(ended(), [], `a planned stop is not news:\\n${JSON.stringify(sent)}`);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_an_answered_child_is_listed_as_idle_without_its_output() -> None:
    _s0_run(
        """
        await start({ operation: "start", name: "solo", prompt: "Reply with the number 1+1.", tools: [] });
        beginTurn();
        settle("2");
        const listed = await start({ operation: "list" });
        const [entry] = listed.details.sessions;
        assert.equal(entry.status, "idle", "a child that answered is not working");
        // ADR-0008 left no inspection operation. A roster entry is a status
        // summary, so the settled answer is not part of it: it arrives with the
        // Session Result, not with a second read of the roster.
        assert.equal(entry.liveText, undefined);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_child_that_already_reported_is_not_announced_as_ended() -> None:
    _s0_run(
        """
        const started = await start({ operation: "start", name: "solo", prompt: "Work.", tools: [] });
        beginTurn();
        settle("done");
        exits({ pid: 4242, exitCode: 0, signal: null, stdout: "", stderr: "" });
        assert.equal(ended().length, 0, `a reported child ending is not news:\\n${JSON.stringify(sent)}`);
        assert.equal(results().length, 1);
        assert.equal(started.details.disposition, "started");
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_coordinator_host_keeps_ownership_of_delivery() -> None:
    _s0_run(
        """
        setAgentHost({
          // The host reserves the roster name it was asked for, so the handle it
          // returns is the exact incarnation this start owns.
          start: async (request) => {
            registerAgent({name:request.name,role:"hosted",spawnId:"s1",pid:8,status:"working",scope:"session",createdAt:1,updatedAt:1});
            return { ok: true, session: `session:${request.name}:s1` };
          },
          send:async()=>({ok:true}),interrupt:async()=>({ok:true}),
          stop: async () => ({ ok: true }),
        });
        const hosted = await start({ operation: "start", name: "hosted", prompt: "Work.", tools: [] });
        assert.equal(hosted.details.ok, true, hosted.content[0].text);
        assert.equal(hosted.details.disposition, "started");
        assert.equal(hosted.details.label, "hosted", "the receipt names the child by its label");
        assert.match(hosted.details.session, /^session:subagent-[0-9a-f]+:s1$/);
        setAgentHost(undefined);
        // The host owns the spawn and the report; the execution layer delivering
        // its own copy is the double-delivery this guards.
        assert.deepEqual(sent, [], `a hosted spawn delivers nothing itself:\\n${JSON.stringify(sent)}`);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_unreadable_details_are_reported_as_unreadable_and_not_as_a_death() -> None:
    _s0_run(
        """
        const row = paint({ customType: "subagents-session-result", details: { nonsense: true } }, true);
        assert.match(row, /unreadable/i, row);
        assert.ok(!/ended/.test(row), `a fallback must not claim a child ended:\\n${row}`);
        const empty = paint({ customType: "subagents-session-ended" }, true);
        assert.match(empty, /unreadable/i, empty);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_host_without_the_optional_surfaces_still_works() -> None:
    """Degradation is a contract, not an accident: a host that offers neither
    the renderer nor the session API must still load, register, and spawn."""
    result = run_node(
        f"""
        import assert from "node:assert/strict";
        import * as spawner from {json.dumps(SPAWNER)};
import {{ sessionNoticeSpec }} from {json.dumps((PACKAGE / 'src' / 'session-result.ts').as_uri())};
        let frames;
        let exits;
        const {{ mock }} = await import("node:test");
        mock.module({json.dumps(SPAWNER)}, {{
          namedExports: {{
            ...spawner,
            spawnResident: (options) => {{ frames = options.onUpdate; exits = options.onExit; return {{ pid: 11 }}; }},
          }},
        }});
        const {{ default: piSubagentsExtension }} = await import({json.dumps(ENTRY)});
        const tools = [];
        // No registerMessageRenderer, no sendMessage, no events bus.
        piSubagentsExtension({{ registerTool: (t) => tools.push(t), on() {{}} }});
        const tool = (name) => {{
          const found = tools.find((candidate) => candidate.name === name);
          assert.ok(found, `the intent family registers ${{name}}`);
          return found;
        }};
        const ctx = {{ cwd: process.cwd() }};
        const started = await tool("agent_start").execute("t", {{ label: "bare", prompt: "Work.", tools: [] }},
          undefined, undefined, ctx);
        assert.equal(started.details.ok, true, started.content[0].text);
        // A settled frame with nowhere to go is not an error: the roster keeps it.
        frames({{ text: "the answer", turns: 1, finalResponse: true, modelOutputSeen: true }});
        const listed = await tool("agent_list").execute("t", {{}}, undefined, undefined, ctx);
        assert.equal(listed.details.ok, true, listed.content[0].text);
        assert.equal(listed.details.sessions.length, 1, listed.content[0].text);
        assert.equal(listed.details.sessions[0].liveText, undefined);
        exits({{ pid: 11, exitCode: 0, signal: null, stdout: "", stderr: "" }});
        console.log(JSON.stringify({{ ok: true }}));
        """,
        module_mocks=True,
    )
    assert result["ok"] is True


def test_only_the_extension_module_reaches_the_row_renderer() -> None:
    """One file is both the library barrel and the extension Pi loads, so
    `src/rows.ts` is reachable from the barrel. The previous probe for this read
    `Module._cache`, which ESM never populates: it reported "clean" for any input,
    which is worse than no test at all.

    This one watches real module resolution. It cannot assert that importing the
    barrel loads no pi-tui, because `@fradser/pi-kit` imports pi-tui for its
    Markdown helper and every package's barrel reaches it — a boundary that
    belongs to pi-kit, not here, and one this package cannot fix alone. What
    subagents does own is the reach of its own TUI-bearing module, so that is what
    is asserted: the row renderer is imported by the entry body and by nothing
    else.
    """
    result = run_node(
        f"""
        import {{ registerHooks }} from "node:module";
        const parents = [];
        registerHooks({{
          resolve(specifier, context, nextResolve) {{
            // The specifier is relative, so what matters is which module asked.
            if (specifier.includes("rows.ts")) parents.push(context.parentURL);
            return nextResolve(specifier, context);
          }},
        }});
        await import({json.dumps(BARREL)});
        const importers = [...new Set(parents.map((url) => url.split("/").pop()))];
        console.log(JSON.stringify({{ rowsReached: parents.length, importers }}));
        """
    )
    assert int(result["rowsReached"]) > 0, "the probe cannot see the row renderer, so this assertion is vacuous"
    # `extension.ts` is the only module allowed to reach it: a row needs real
    # terminal geometry, and a library consumer has none.
    assert list(result["importers"]) == ["extension.ts"], result["importers"]


def test_a_settle_reaching_the_spawner_with_the_next_turn_is_still_reported() -> None:
    """The parser, not a hand-written frame.

    A real child can settle and start its next turn inside one stdout read. If
    the spawner reports one frame per read, the settle is invisible — which is
    exactly the failure this feature exists to remove, and exactly what a
    hand-written frame list cannot catch. Driven by
    `coalesced-settle-fixture.ts`, because node only exposes module mocking
    reliably for a real entry point.
    """
    with tempfile.TemporaryDirectory(prefix="coalesced-settle-") as directory:
        root = Path(directory)
        env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
        env.update(HOME=directory, PI_CODING_AGENT_DIR=str(root / "agent"),
                   XDG_CONFIG_HOME=str(root / "config"), XDG_CACHE_HOME=str(root / "cache"))
        result = subprocess.run(
            ["node", "--experimental-test-module-mocks", str(PACKAGE / "tests" / "coalesced-settle-fixture.ts")],
            cwd=PACKAGE, check=False, capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["ok"] is True


# --- Merged from test_agent_cancellation.py ---
"""Cancellation stops caller waiting, not acknowledged resident lifetime."""

from pathlib import Path

import pytest

from resident_support import run


# ADR-0008 retired `inspect`, so the surviving executor operations are the four
# below and nothing addresses a single child any more.
@pytest.mark.parametrize("operation", ["start", "input", "list", "stop"])
def test_aborted_signal_refuses_before_any_effect(tmp_path: Path, operation: str) -> None:
    run("""
      const controller=new AbortController();controller.abort();
      const result=await call(ACTION==="start"?{operation:"start",name:"cancelled",prompt:"Run"}
        :ACTION==="list"?{operation:"list"}
        :ACTION==="stop"?{operation:"stop",session:"session:missing:exact"}
        :{operation:"input",delivery:"next",session:"session:missing:exact",prompt:"Run"},
        {signal:controller.signal});
      assert.equal(result.details.ok,false);assert.equal(result.details.outcome,"cancelled");
      assert.equal(result.details.dispatched,false);assert.equal(result.details.controlOutcome,"not-dispatched");
      assert.deepEqual([spawns.length,prompts.length,steers.length,notices.length,workspaces.length],[0,0,0,0,0]);
      assert.deepEqual(roster.listAgents(),[]);console.log(JSON.stringify({ok:true}));
    """.replace("ACTION", f'"{operation}"'),tmp_path)


def test_cancelled_start_wait_retains_late_ack_and_result_on_original_incarnation(tmp_path: Path) -> None:
    run("""
      const controller=new AbortController();let acknowledge;
      const startupAck=new Promise(resolve=>acknowledge=resolve);
      let stops=0;
      const pending=call({name:"cancelled-start",prompt:"  authored kickoff\\n",tools:[]},{signal:controller.signal,
        spawn:options=>(spawns.push(options),{pid:42,accepted:startupAck}),
        terminate:async()=>{stops++;return {outcome:"closed"}}});
      controller.abort();
      // The race only proves the caller was not left waiting: the runtime work on this
      // path is longer than a hundred milliseconds under load, so the budget is a
      // hang detector rather than a timing assumption.
      const cancelled=await Promise.race([pending,new Promise(resolve=>setTimeout(()=>resolve({timedOut:true}),2000))]);
      assert.ok(!cancelled.timedOut,"tool cancellation must release the caller before acknowledgement");
      assert.equal(cancelled.details.outcome,"cancelled");assert.equal(cancelled.details.controlOutcome,"uncertain");
      assert.equal(cancelled.details.pendingIntent,"start");assert.equal(cancelled.details.dispatched,true);
      assert.equal(cancelled.details.session,"session:cancelled-start:"+roster.getAgent("cancelled-start").spawnId);
      assert.equal(roster.getAgent("cancelled-start").status,"starting");assert.equal(stops,0);
      acknowledge(true);await new Promise(resolve=>setImmediate(resolve));
      final(0,"2");assert.equal(roster.getAgent("cancelled-start").status,"idle");assert.equal(notices.length,1);
      const next=await call({operation:"input",delivery:"next",session:cancelled.details.session,prompt:"Next"});
      assert.equal(next.details.ok,true);assert.equal(prompts.length,1);assert.equal(spawns.length,1);
      final(0,"3");assert.equal(notices.length,2);assert.equal(stops,0);
      assert.deepEqual(notices.map(notice=>notice.session),[cancelled.details.session,cancelled.details.session]);
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


@pytest.mark.parametrize("operation", ["input", "steer", "stop"])
def test_cancelled_control_wait_preserves_late_outcome(tmp_path: Path, operation: str) -> None:
    run("""
      const controller=new AbortController();let acknowledge;let controls=0;
      const acknowledgement=new Promise(resolve=>acknowledge=resolve);
      const seam=ACTION==="input"?{prompt:async()=>{controls++;return acknowledgement}}:
        ACTION==="steer"?{steer:async()=>{controls++;return acknowledgement}}:
        {terminate:async()=>{controls++;return acknowledgement}};
      const started=await call({name:"cancelled-control",prompt:"Run",tools:[]},seam);
      // A steer addresses a working child, which the runtime reaches on the child's
      // first frame; the other deliveries address the child a settled turn leaves idle.
      if(ACTION==="steer")roster.updateAgent(started.details.name,{status:"working"});else final(0,"first");
      // One `input` operation carries both deliveries, so the pending intent a
      // cancelled wait reports is the operation, never the delivery.
      const pending=call({operation:ACTION==="stop"?"stop":"input",session:started.details.session,
        ...(ACTION==="stop"?{}:{delivery:ACTION==="steer"?"steer":"next",prompt:"  exact input\\n"})},{...seam,signal:controller.signal});
      controller.abort();
      // The race only proves the caller was not left waiting: the runtime work on this
      // path is longer than a hundred milliseconds under load, so the budget is a
      // hang detector rather than a timing assumption.
      const cancelled=await Promise.race([pending,new Promise(resolve=>setTimeout(()=>resolve({timedOut:true}),2000))]);
      assert.ok(!cancelled.timedOut);assert.equal(cancelled.details.outcome,"cancelled");
      assert.equal(cancelled.details.pendingIntent,ACTION==="stop"?"stop":"input");
      assert.equal(cancelled.details.session,started.details.session);
      assert.equal(controls,1);assert.equal(spawns.length,1);
      if(ACTION==="stop")assert.equal(roster.getAgent(started.details.name).leaderRequestedEnd,true);
      else assert.notEqual(roster.getAgent(started.details.name).status,"idle");
      acknowledge(ACTION==="stop"?{outcome:"closed"}:true);
      await new Promise(resolve=>setImmediate(resolve));
      if(ACTION==="stop")assert.equal(roster.getAgent(started.details.name).status,"stopped");
      else {final(0,"later");assert.equal(roster.getAgent(started.details.name).status,"idle");}
      assert.equal(controls,1);console.log(JSON.stringify({ok:true}));
    """.replace("ACTION", f'"{operation}"'),tmp_path)


def test_aborting_parent_turn_after_acceptance_does_not_close_child(tmp_path: Path) -> None:
    run("""
      const controller=new AbortController();let stops=0;
      const started=await call({name:"accepted",prompt:"Run",tools:[]},{signal:controller.signal,
        terminate:async()=>{stops++;return {outcome:"closed"}}});
      assert.equal(started.details.ok,true);controller.abort();
      final(0,"still valid");assert.equal(notices.length,1);assert.equal(stops,0);
      assert.equal(roster.getAgent("accepted").status,"idle");
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_reservation_callback_abort_keeps_exact_committed_start(tmp_path: Path) -> None:
    run("""
      const controller=new AbortController();let acknowledge;
      const startupAck=new Promise(resolve=>acknowledge=resolve);
      const stopObserve=roster.observeAgentRoster(()=>controller.abort());
      const pending=call({name:"reservation-cancelled",prompt:"Run",tools:[]},{signal:controller.signal,
        spawn:options=>(spawns.push(options),{pid:42,accepted:startupAck})});
      stopObserve();const cancelled=await pending;
      assert.equal(cancelled.details.outcome,"cancelled");assert.equal(cancelled.details.dispatched,true);
      assert.equal(cancelled.details.session,"session:reservation-cancelled:"+roster.getAgent("reservation-cancelled").spawnId);
      acknowledge(true);await new Promise(resolve=>setImmediate(resolve));final(0,"2");
      assert.equal(notices.length,1);assert.equal(spawns.length,1);
      assert.equal(roster.getAgent("reservation-cancelled").status,"idle");
      console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_cancelled_host_start_retains_its_original_exact_reservation(tmp_path: Path) -> None:
    run("""
      const {setAgentHost}=await import("file://"+process.cwd()+"/src/child-execution.ts");
      let confirm;setAgentHost({start:request=>{
        roster.registerAgent({name:request.name,role:request.name,spawnId:"host-original",pid:7,
          status:"starting",createdAt:1,updatedAt:1});
        return new Promise(resolve=>confirm=resolve);
      },send:async()=>({ok:true}),interrupt:async()=>({ok:true}),stop:async()=>({ok:true})});
      const controller=new AbortController();
      const pending=call({name:"host-cancelled",prompt:"Run"},{signal:controller.signal});controller.abort();
      const cancelled=await pending;
      assert.equal(cancelled.details.outcome,"cancelled");assert.equal(cancelled.details.session,"session:host-cancelled:host-original");
      assert.equal(cancelled.details.state,"starting");
      roster.updateAgent("host-cancelled",{status:"idle"});confirm({ok:true,session:cancelled.details.session});
      await new Promise(resolve=>setImmediate(resolve));
      const sent=await call({operation:"input",delivery:"next",session:cancelled.details.session,prompt:"Continue"});
      assert.equal(sent.details.ok,true);setAgentHost(undefined);console.log(JSON.stringify({ok:true}));
    """,tmp_path)


def test_cancelled_late_host_failure_cannot_write_to_successor(tmp_path: Path) -> None:
    run("""
      const {setAgentHost}=await import("file://"+process.cwd()+"/src/child-execution.ts");
      let reject;
      setAgentHost({start:()=>new Promise((_resolve,rejectPromise)=>reject=rejectPromise),
        send:async()=>({ok:true}),interrupt:async()=>({ok:true}),stop:async()=>({ok:true})});
      const controller=new AbortController();
      const pending=call({name:"host-pending",prompt:"Run"},{signal:controller.signal});controller.abort();
      // The race only proves the caller was not left waiting: the runtime work on this
      // path is longer than a hundred milliseconds under load, so the budget is a
      // hang detector rather than a timing assumption.
      const cancelled=await Promise.race([pending,new Promise(resolve=>setTimeout(()=>resolve({timedOut:true}),2000))]);
      assert.ok(!cancelled.timedOut);assert.equal(cancelled.details.outcome,"cancelled");
      setAgentHost(undefined);const successor=await call({name:"host-pending",tools:[]});
      reject(new Error("LATE_HOST_FAILURE"));await new Promise(resolve=>setImmediate(resolve));
      assert.equal(roster.getAgent("host-pending").error,undefined);
      assert.equal(roster.getAgent("host-pending").status,"idle");
      assert.ok(successor.details.session);console.log(JSON.stringify({ok:true}));
    """,tmp_path)


# --- Merged from test_hosted_cancellation_authority.py ---
"""Scoped review regressions: exact hosted owner and late cancelled failures."""

from pathlib import Path

import pytest

from resident_support import run

HOST_PREAMBLE = """
const {setAgentHost}=await import('file://'+process.cwd()+'/src/child-execution.ts');
const bindings=globalThis[Symbol.for('fradser.pi-subagents.host-bindings')];
const record=(name,id,status='starting')=>({name,role:name,spawnId:id,pid:7,status,scope:'session',standalone:false,createdAt:1,updatedAt:1});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
"""


@pytest.mark.parametrize('returned_handle', ['original', 'successor'])
@pytest.mark.parametrize('cancel', [False, True])
def test_late_start_cannot_retarget_successor_owner(
    tmp_path: Path, returned_handle: str, cancel: bool,
) -> None:
    run(HOST_PREAMBLE + """
      let confirm;const callsA=[],callsB=[];
      const hostA={start:request=>{
        roster.registerAgent(record(request.name,'old'));
        return new Promise(resolve=>confirm=resolve);
      },send:async()=>{callsA.push('send');return {ok:true}},interrupt:async()=>{callsA.push('interrupt');return {ok:true}},
      stop:async()=>{callsA.push('stop');return {ok:true}}};
      const hostB={start:request=>{roster.registerAgent(record(request.name,'new','idle'));return {ok:true,session:`session:${request.name}:new`}},
        send:async(name)=>{callsB.push('send');roster.updateAgent(name,{status:'working'});return {ok:true}},
        interrupt:async()=>{callsB.push('interrupt');return {ok:true}},stop:async()=>{callsB.push('stop');return {ok:true}}};
      setAgentHost(hostA);const controller=new AbortController();
      const pending=call({name:'ownership',prompt:'First'},{signal:controller.signal});
      if(CANCEL){controller.abort();const cancelled=await pending;assert.equal(cancelled.details.outcome,'cancelled');}
      roster.updateAgent('ownership',{status:'stopped'});
      setAgentHost(hostB);const second=await call({name:'ownership',tools:[]});assert.equal(second.details.ok,true);
      const before=JSON.stringify(roster.getAgent('ownership'));
      confirm({ok:true,session:RETURNED==='original'?'session:ownership:old':second.details.session});await flush();
      if(!CANCEL){const refused=await pending;assert.equal(refused.details.ok,false,'late start cannot report successor acceptance');}
      assert.equal(JSON.stringify(roster.getAgent('ownership')),before,'old confirmation cannot modify successor facts');
      const sent=await call({operation:'input',delivery:'next',session:second.details.session,prompt:'Next'});assert.equal(sent.details.ok,true);
      const steered=await call({operation:'input',delivery:'steer',session:second.details.session,prompt:'Steer'});assert.equal(steered.details.ok,true);
      const stopped=await call({operation:'stop',session:second.details.session});assert.equal(stopped.details.ok,true);
      assert.deepEqual(callsB,['send','interrupt','stop']);assert.deepEqual(callsA,[]);
      assert.equal(spawns.length,0);setAgentHost(undefined);console.log(JSON.stringify({ok:true}));
    """.replace('CANCEL','true' if cancel else 'false').replace('RETURNED',f'"{returned_handle}"'),tmp_path)


@pytest.mark.parametrize('owner', ['same-host', 'other-host'])
@pytest.mark.parametrize('cancel', [False, True])
def test_synchronous_reentrant_start_never_pins_owned_successor(
    tmp_path: Path, owner: str, cancel: bool,
) -> None:
    run(HOST_PREAMBLE + """
      const callsA=[],callsB=[];let confirm;let successorStart;let successorSnapshot;
      let calls=0;const successor='session:reentrant:new';
      const hostB={start:request=>{roster.registerAgent(record(request.name,'new','idle'));return {ok:true,session:successor}},
        send:async(name)=>{callsB.push('send');roster.updateAgent(name,{status:'working'});return {ok:true}},
        interrupt:async()=>{callsB.push('interrupt');return {ok:true}},stop:async()=>{callsB.push('stop');return {ok:true}}};
      const hostA={start:request=>{
        calls++;
        if(calls>1){roster.registerAgent(record(request.name,'new','idle'));return {ok:true,session:successor}}
        roster.registerAgent(record(request.name,'old'));roster.updateAgent(request.name,{status:'stopped'});
        setAgentHost(OWNER==='same-host'?hostA:hostB);
        successorStart=call({name:request.name,tools:[]});
        successorSnapshot=JSON.stringify(roster.getAgent(request.name));
        return new Promise(resolve=>confirm=resolve);
      },send:async(name)=>{callsA.push('send');roster.updateAgent(name,{status:'working'});return {ok:true}},
        interrupt:async()=>{callsA.push('interrupt');return {ok:true}},stop:async()=>{callsA.push('stop');return {ok:true}}};
      setAgentHost(hostA);const controller=new AbortController();
      const old=call({name:'reentrant',prompt:'Old input'},{signal:controller.signal});
      if(CANCEL){controller.abort();const cancelled=await old;assert.equal(cancelled.details.outcome,'cancelled');
        assert.notEqual(cancelled.details.session,successor,"cancellation must not advertise another start's handle");}
      const newStart=await successorStart;
      assert.equal(newStart.details.ok,true,newStart.content[0].text);assert.equal(newStart.details.session,successor);
      const expectedOwner=OWNER==='same-host'?hostA:hostB;
      assert.equal(bindings.get(successor),expectedOwner,'existing owner must survive before any confirmation');
      const before=JSON.stringify(roster.getAgent('reentrant'));
      confirm({ok:true,session:successor});await flush();
      if(!CANCEL){const failed=await old;assert.equal(failed.details.ok,false);assert.notEqual(failed.details.session,successor);}
      assert.equal(JSON.stringify(roster.getAgent('reentrant')),before);
      assert.equal(bindings.get(successor),expectedOwner);
      assert.equal((await call({operation:'input',delivery:'next',session:successor,prompt:'Next'})).details.ok,true);
      assert.equal((await call({operation:'input',delivery:'steer',session:successor,prompt:'Steer'})).details.ok,true);
      assert.equal((await call({operation:'stop',session:successor})).details.ok,true);
      assert.deepEqual(OWNER==='same-host'?callsA:callsB,['send','interrupt','stop']);
      assert.deepEqual(OWNER==='same-host'?callsB:callsA,[]);
      assert.ok(successorSnapshot);setAgentHost(undefined);console.log(JSON.stringify({ok:true}));
    """.replace('OWNER',f'"{owner}"').replace('CANCEL','true' if cancel else 'false'),tmp_path)


@pytest.mark.parametrize('owner', ['same-host', 'other-host'])
def test_start_without_an_original_reservation_cannot_claim_an_existing_session(
    tmp_path: Path, owner: str,
) -> None:
    run(HOST_PREAMBLE + """
      const stopped=[];const host={start:()=>({ok:true,session:'session:incumbent:original'}),
        send:async()=>({ok:true}),interrupt:async()=>({ok:true}),stop:async()=>{stopped.push('wrong');return {ok:true}}};
      roster.registerAgent(record('incumbent','original','idle'));
      const existingOwner=OWNER==='same-host'?host:{...host,stop:async()=>{stopped.push('original');return {ok:true}}};
      bindings.set('session:incumbent:original',existingOwner);setAgentHost(host);
      const before=JSON.stringify(roster.getAgent('incumbent'));
      const result=await call({name:'incumbent',prompt:'Must not reuse a living start'});
      assert.equal(result.details.ok,false,'a returned live handle without a new reservation is not a start');
      assert.equal(bindings.get('session:incumbent:original'),existingOwner);
      assert.equal(JSON.stringify(roster.getAgent('incumbent')),before);assert.deepEqual(stopped,[]);
      setAgentHost(undefined);console.log(JSON.stringify({ok:true}));
    """.replace('OWNER',f'"{owner}"'),tmp_path)


@pytest.mark.parametrize('cancel', [False, True])
def test_pending_hosted_start_is_explicitly_stoppable_before_ack(tmp_path: Path, cancel: bool) -> None:
    run(HOST_PREAMBLE + """
      let confirm;const stopped=[];const host={start:request=>{
        roster.registerAgent(record(request.name,'pending'));
        return new Promise(resolve=>confirm=resolve);
      },send:async()=>({ok:true}),interrupt:async()=>({ok:true}),stop:async(name,id)=>{stopped.push({name,id});return {ok:true}}};
      setAgentHost(host);const controller=new AbortController();
      const pending=call({name:'closable',prompt:'Run'},{signal:controller.signal});
      let session='session:closable:pending';
      if(CANCEL){controller.abort();const cancelled=await pending;assert.equal(cancelled.details.session,session);}
      assert.equal(bindings.get(session),host,'closure owner must be bound before confirmation');
      assert.deepEqual(stopped,[],'wait cancellation alone never closes a process');
      const closed=await call({operation:'stop',session});assert.equal(closed.details.ok,true,closed.content[0].text);
      assert.deepEqual(stopped,[{name:'closable',id:'pending'}]);assert.equal(roster.getAgent('closable').status,'stopped');
      assert.equal(bindings.has(session),false);
      confirm({ok:true,session});await flush();
      if(!CANCEL)assert.equal((await pending).details.ok,false,'stopped startup cannot report success');
      assert.equal(roster.getAgent('closable').status,'stopped');assert.equal(bindings.has(session),false,'late ACK cannot restore retired controls');
      assert.deepEqual(stopped,[{name:'closable',id:'pending'}]);setAgentHost(undefined);console.log(JSON.stringify({ok:true}));
    """.replace('CANCEL','true' if cancel else 'false'),tmp_path)


@pytest.mark.parametrize('ownership', ['standalone', 'hosted'])
@pytest.mark.parametrize('operation', ['input', 'steer', 'stop'])
@pytest.mark.parametrize('kind', ['throw', 'negative'])
def test_cancelled_returned_or_thrown_control_failure_is_readable(
    tmp_path: Path, ownership: str, operation: str, kind: str,
) -> None:
    run(HOST_PREAMBLE + """
      let settle;let count=0;const ack=new Promise(resolve=>settle=resolve);
      const control=async()=>{count++;const result=await ack;if(KIND==='throw')throw new Error(result);return result;};
      let start;
      if(OWNERSHIP==='hosted'){
        setAgentHost({start:request=>{roster.registerAgent(record(request.name,'late-error','idle'));
          return {ok:true,session:`session:${request.name}:late-error`}},
          send:async(name)=>{roster.updateAgent(name,{status:'starting'});return control()},interrupt:control,stop:control});
        start=await call({name:'diagnostic'});
        if(ACTION==='steer')roster.updateAgent('diagnostic',{status:'working'});
        roster.updateAgent('diagnostic',{liveText:'PREVIOUS_ANSWER'});
      }else{
        const seams=ACTION==='input'?{prompt:control}:ACTION==='steer'?{steer:control}:{terminate:control};
        start=await call({name:'diagnostic',prompt:'First',tools:[]},seams);final(0,'PREVIOUS_ANSWER');
        if(ACTION==='steer')roster.updateAgent('diagnostic',{status:'working'});
      }
      const controller=new AbortController();
      const pending=call(ACTION==="stop"?{operation:"stop",session:start.details.session}:{operation:"input",delivery:ACTION==="steer"?"steer":"next",session:start.details.session,prompt:'New input'},
        {signal:controller.signal,...(OWNERSHIP==='standalone'&&ACTION==='stop'?{terminate:control}:{})});
      controller.abort();const cancelled=await pending;assert.equal(cancelled.details.outcome,'cancelled');
      const status=roster.getAgent('diagnostic').status;const beforeNotices=notices.length;
      const diagnostic='LATE_ACK_ERROR';
      settle(KIND==='throw'?diagnostic:OWNERSHIP==='hosted'?{ok:false,error:diagnostic}:ACTION==='stop'?{outcome:'unconfirmed'}:false);
      await flush();const listed=await call({operation:'list'});
      // ADR-0008 left no inspection operation: the roster is the one read that
      // survives, and it keeps the exact incarnation a cancelled wait owned.
      const retained=listed.details.sessions.find(row=>row.session===start.details.session);
      assert.ok(retained,'the roster keeps the exact incarnation the cancelled wait dispatched');
      assert.ok(retained.error,'a cancelled operation failure must remain readable on the roster');
      if(KIND==='throw'||OWNERSHIP==='hosted')assert.ok(retained.error.includes(diagnostic));
      // A definitive native false reply may restore idle by the existing
      // send contract. Only uncertain/rejected promise errors retain busy state;
      // the diagnostic recorder itself never guesses a status transition.
      const expected=OWNERSHIP==='standalone'&&ACTION==='input'&&KIND==='negative'?'idle':status;
      assert.equal(roster.getAgent('diagnostic').status,expected,'diagnostic recording cannot invent a process outcome');
      if(ACTION==='stop')assert.equal(roster.getAgent('diagnostic').leaderRequestedEnd,true);
      assert.equal(count,1);assert.equal(notices.length,beforeNotices);setAgentHost(undefined);console.log(JSON.stringify({ok:true}));
    """.replace('OWNERSHIP',f'"{ownership}"').replace('ACTION',f'"{operation}"').replace('KIND',f'"{kind}"'),tmp_path)


@pytest.mark.parametrize('operation', ['input', 'steer', 'stop'])
def test_cancelled_late_failure_never_writes_to_replacement(tmp_path: Path, operation: str) -> None:
    run(HOST_PREAMBLE + """
      let reject;const ack=new Promise((_resolve,rejectPromise)=>reject=rejectPromise);
      const host={start:request=>{roster.registerAgent(record(request.name,'old','idle'));return {ok:true,session:`session:${request.name}:old`}},
        send:async(name)=>{roster.updateAgent(name,{status:'starting'});return ack},interrupt:async()=>ack,stop:async()=>ack};
      setAgentHost(host);const start=await call({name:'replacement'});
      if(ACTION==='steer')roster.updateAgent('replacement',{status:'working'});
      const controller=new AbortController();const pending=call(ACTION==="stop"?{operation:"stop",session:start.details.session}:{operation:"input",delivery:ACTION==="steer"?"steer":"next",session:start.details.session,prompt:'Run'},{signal:controller.signal});controller.abort();await pending;
      roster.updateAgent('replacement',{status:'stopped'});roster.registerAgent({...record('replacement','new','idle'),error:'SUCCESSOR_ONLY'});
      const before=JSON.stringify(roster.getAgent('replacement'));reject(new Error('PREDECESSOR_ONLY'));await flush();
      assert.equal(JSON.stringify(roster.getAgent('replacement')),before);assert.equal(roster.getAgent('replacement').error,'SUCCESSOR_ONLY');
      setAgentHost(undefined);console.log(JSON.stringify({ok:true}));
    """.replace('ACTION',f'"{operation}"'),tmp_path)


# --- Merged from test_parent_message.py ---
"""Parent-message transport and result-shape regression tests."""

import os
import subprocess
from pathlib import Path

import pytest
from subagents_helpers import PACKAGE


@pytest.mark.parametrize("probe", ["parse", "extension", "route", "ownership"])
def test_parent_message_contract(probe: str, tmp_path: Path) -> None:
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "PI_OFFLINE": "1",
    }
    result = subprocess.run(
        ["node", "--experimental-test-module-mocks", str(PACKAGE / "tests" / "parent-message-fixture.ts"), probe],
        cwd=PACKAGE,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"ok":true' in result.stdout


# --- Merged from test_stream_recovery.py ---
"""Native retry regression for the exact premature-close provider diagnostic."""

import json
import os
from pathlib import Path
import subprocess

import pytest

from subagents_helpers import PACKAGE, SRC, run_node

ERROR = "stream error: stream disconnected before completion: stream closed before response.completed"


@pytest.mark.parametrize("enabled,always_fail,attempts,stop", [
    (True, False, 2, "stop"), (False, False, 1, "error"), (True, True, 2, "error"),
])
def test_native_retry_policy_recovers_or_exhausts_without_new_input(
    tmp_path: Path, enabled: bool, always_fail: bool, attempts: int, stop: str,
) -> None:
    # The native probe must be independent of the developer's provider,
    # credentials, NODE_OPTIONS, and extension/config environment.  Node only
    # needs PATH to resolve its executable; the fixture supplies every Pi
    # setting it intentionally uses below.
    env = {"PATH": os.environ.get("PATH", os.defpath)}
    env.update(HOME=str(tmp_path), PI_CODING_AGENT_DIR=str(tmp_path / "agent"), PI_OFFLINE="1",
               PI_STREAM_CASE=json.dumps({"enabled": enabled, "alwaysFail": always_fail}))
    result = subprocess.run(["node", str(PACKAGE / "tests" / "native-stream-recovery-fixture.ts")],
                            cwd=PACKAGE, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["attempts"] == attempts
    assert report["stopReason"] == stop
    assert report["settled"] == report["userInputs"] == 1
    assert report["nativeRetries"] == (1 if enabled else 0)
    if stop == "stop":
        assert report["finalText"] == "RECOVERED_FINAL"
    else:
        assert ERROR in report["diagnostic"]


def test_recovery_only_matches_known_transport_failure_without_tool_calls() -> None:
    report = run_node(f'''
      const {{default:extension}}=await import({json.dumps((SRC / 'stream-recovery.ts').as_uri())});
      const handlers=new Map();extension({{on:(name,handler)=>handlers.set(name,handler)}});
      const error={json.dumps(ERROR)};
      const message={{role:'assistant',stopReason:'error',errorMessage:error,content:[{{type:'text',text:'original partial'}}]}};
      const handler=handlers.get('message_end');
      const matched=handler({{message}});
      const misses=[{{...message,stopReason:'aborted'}},{{...message,errorMessage:'401 unauthorized'}},
        {{...message,errorMessage:'insufficient_quota '+error}},
        {{...message,content:[{{type:'toolCall',id:'pending',name:'write',arguments:{{}}}}]}},
        {{...message,errorMessage:'connection closed for an unrelated reason'}}].map(value=>handler({{message:value}})??null);
      console.log(JSON.stringify({{matched,misses,original:message}}));
    ''')
    assert report["matched"]["message"]["errorMessage"].endswith(ERROR)
    assert report["matched"]["message"]["content"] == report["original"]["content"]
    assert report["matched"]["message"]["stopReason"] == "error"
    assert report["misses"] == [None] * 5


# --- Merged from test_unanswered_results.py ---
"""Regressions for blank review envelopes through the real standalone entry."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from subagents_helpers import SRC, PACKAGE, run_node

_m5_SPAWNER = (SRC / "spawner.ts").as_uri()
_m5_ENTRY = (PACKAGE / "index.ts").as_uri()
_m5_PREAMBLE = f"""
import assert from "node:assert/strict";
import {{mock}} from "node:test";
import * as transport from {json.dumps(_m5_SPAWNER)};
let callbacks;const sent=[],spawns=[],prompts=[];
mock.module({json.dumps(_m5_SPAWNER)},{{namedExports:{{...transport,
  spawnResident:options=>(callbacks=options,spawns.push(options),{{pid:7,accepted:Promise.resolve(true),readiness:Promise.resolve(true)}}),
  deliverResidentPrompt:async(name,input)=>(prompts.push({{name,input}}),true),
  terminateAgent:async()=>({{outcome:"closed"}}),
}}}});
const {{default:extension,getAgent,resetRoster}}=await import({json.dumps(_m5_ENTRY)});
resetRoster();const registered=[],renderers=new Map();
extension({{registerTool:tool=>registered.push(tool),registerMessageRenderer:(type,render)=>renderers.set(type,render),
  on(){{}},events:{{emit(){{}}}},sendMessage:(message,options)=>sent.push({{...message,options}})}});
const intentTools=new Map(registered.filter(t=>t.name.startsWith("agent_")).map(t=>[t.name,t]));
const call=(request)=>{{
  const {{operation,name,session,prompt,tools,...rest}}=request;
  const tool=operation==="input"||operation==="steer"?"agent_input":operation==="inspect"?"agent_list"
    :operation==="stop"?"agent_stop":operation==="list"?"agent_list":"agent_start";
  const params=tool==="agent_start"
    ?{{prompt:prompt??"Start the assigned work.",...(name===undefined?{{}}:{{label:name}}),...(tools===undefined?{{}}:{{tools}}),...rest}}
    :tool==="agent_input"?{{session,prompt,delivery:operation==="steer"?"steer":"next"}}:session===undefined?{{...rest}}:{{session,...rest}};
  return intentTools.get(tool).execute("repro",params,undefined,undefined,{{cwd:process.env.PI_TEST_CWD}});
}};
const begin=()=>callbacks.onUpdate({{text:"",turns:0,finalResponse:false}});
const theme={{fg:(_key,text)=>text,bg:(_key,text)=>text,bold:text=>text}};
const paint=message=>renderers.get(message.customType)(message,{{expanded:true}},theme).render(100).join("\\n");
"""


def _m5_run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(_m5_PREAMBLE + script, module_mocks=True, env_overrides={
        "HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "PI_TEST_CWD": str(tmp_path), "PI_OFFLINE": "1",
    })


CASES = [
    ({"text": "", "stopReason": "stop"}, "empty"),
    ({"text": "  \n\t", "stopReason": "stop"}, "empty"),
    ({"text": "", "stopReason": "stop", "liveThinking": "Review reasoning"}, "empty"),
    ({"text": "", "stopReason": "error", "errorMessage": "provider temporarily unavailable"}, "error"),
    ({"text": "partial", "stopReason": "error", "errorMessage": "provider temporarily unavailable"}, "error"),
    ({"text": "partial", "stopReason": "aborted", "errorMessage": "user cancelled"}, "aborted"),
    ({"text": "partial", "stopReason": "length"}, "length"),
    ({"text": "", "stopReason": "toolUse", "hasToolCalls": True}, "incomplete"),
    ({"text": "partial", "stopReason": "stop", "hasToolCalls": True}, "incomplete"),
]


@pytest.mark.parametrize("terminal,reason", CASES)
def test_authoritative_unusable_answer_is_explicit_and_deduplicated(
    tmp_path: Path, terminal: dict[str, object], reason: str,
) -> None:
    result = _m5_run(f"""
      const start=await call({{name:"reviewer",prompt:"Review the fork",tools:[]}});begin();
      const terminal={{...{json.dumps(terminal)},turns:1,finalResponse:true,answerComplete:true}};
      callbacks.onUpdate(terminal);callbacks.onUpdate(terminal);
      const list=await call({{operation:"list"}});
      const outcome=sent[0];
      console.log(JSON.stringify({{count:sent.length,kind:outcome?.details?.kind,reason:outcome?.details?.reason,
        text:outcome?.details?.text,stopReason:outcome?.details?.stopReason,content:outcome?.content,
        options:outcome?.options,status:getAgent(start.details.name).status,list:list.content[0].text,
        row:outcome?paint(outcome):""}}));
    """, tmp_path)
    assert result["count"] == 1
    assert result["kind"] == "unanswered", result
    assert result["reason"] == reason
    assert result["text"] == terminal["text"]
    assert result["stopReason"] == terminal["stopReason"]
    assert "<agent-result-unanswered" in result["content"]
    assert "No usable final answer" in result["content"]
    assert result["options"] == {"deliverAs": "followUp", "triggerTurn": True}
    assert result["status"] == "idle"
    assert "unanswered ·" in result["list"] and "result ·" not in result["list"]
    assert "unanswered" in result["row"]


def test_empty_answer_can_receive_a_later_valid_input_in_the_same_resident(tmp_path: Path) -> None:
    result = _m5_run("""
      const first=await call({name:"reviewer",prompt:"Review",tools:[]});begin();
      callbacks.onUpdate({text:"",turns:1,finalResponse:true,answerComplete:true,stopReason:"stop"});
      const next=await call({operation:"input",delivery:"next",session:first.details.session,prompt:"Return a short final verdict"});
      begin();callbacks.onUpdate({text:"No blocking findings. Static review only.",turns:1,finalResponse:true,answerComplete:true,stopReason:"stop"});
      const same=sent.every(message=>message.details.session===first.details.session);
      const stopped=await call({operation:"stop",session:first.details.session});
      callbacks.onExit({pid:7,exitCode:0,signal:null,stdout:"",stderr:""});
      console.log(JSON.stringify({kinds:sent.map(message=>message.details.kind),turns:sent.map(message=>message.details.turn),same,
        spawns:spawns.length,accepted:next.details.ok,stopped:stopped.details.ok,count:sent.length}));
    """, tmp_path)
    assert result == {"kinds": ["unanswered", "result"], "turns": [1, 2], "same": True,
                      "spawns": 1, "accepted": True, "stopped": True, "count": 2}


def test_readiness_and_unconfirmed_empty_frame_do_not_consume_the_answer(tmp_path: Path) -> None:
    result = _m5_run("""
      const start=await call({name:"reviewer",tools:[]});
      callbacks.onUpdate({text:"",turns:0,finalResponse:true,ready:true});
      const accepted=await call({operation:"input",delivery:"next",session:start.details.session,prompt:"Review"});begin();
      callbacks.onUpdate({text:"",turns:1,finalResponse:true});
      const before=sent.length;
      callbacks.onUpdate({text:"  Complete final text\\n",turns:1,finalResponse:true,answerComplete:true,stopReason:"stop"});
      console.log(JSON.stringify({before,count:sent.length,kind:sent[0].details.kind,text:sent[0].details.text}));
    """, tmp_path)
    assert result == {"before": 0, "count": 1, "kind": "result", "text": "  Complete final text\n"}


def test_unanswered_delivery_retry_does_not_duplicate_or_reanswer_a_later_sequence(tmp_path: Path) -> None:
    result = _m5_run("""
      const {executeChildIntent}=await import("file://"+process.cwd()+"/src/child-execution.ts");
      const notices=[];let attempts=0;
      const start=await executeChildIntent({name:"retry-review",prompt:"Review",tools:[]},{cwd:process.env.PI_TEST_CWD,
        spawn:options=>(callbacks=options,{pid:7,accepted:Promise.resolve(true)}),
        deliverSessionResult:notice=>{
          if(notice.kind==="unanswered"&&++attempts===1)throw new Error("temporary sender failure");
          notices.push(notice);
        }});
      begin();callbacks.onUpdate({text:"",turns:1,finalResponse:true,answerComplete:true,stopReason:"stop"});
      callbacks.onUpdate({text:"",turns:1,finalResponse:true,answerComplete:true,stopReason:"stop"});
      await new Promise(resolve=>setImmediate(resolve));
      console.log(JSON.stringify({attempts,count:notices.length,kind:notices[0].kind,turn:notices[0].turn,
        status:getAgent(start.details.name).status}));
    """, tmp_path)
    assert result == {"attempts":2, "count":1, "kind":"unanswered", "turn":1, "status":"idle"}


def test_unanswered_details_round_trip_and_remain_distinct_from_ended(tmp_path: Path) -> None:
    result = _m5_run("""
      const {readSessionNotice,formatSessionNotice,sessionNoticeSpec}=await import("file://"+process.cwd()+"/src/session-result.ts");
      const old={kind:"result",name:"old",session:"session:old:handle",turn:1,text:"legacy answer",deliveredAt:0};
      const invalid={kind:"unanswered",name:"bad",session:"session:bad:handle",reason:"unknown",text:"",turn:1};
      const notice={kind:"unanswered",name:"review",session:"session:review:handle",reason:"length",
        text:"  partial\\n",turn:3,stopReason:"length",errorMessage:"  local diagnosis ",deliveredAt:0};
      const parsed=readSessionNotice(notice);const spec=sessionNoticeSpec(parsed);
      console.log(JSON.stringify({oldKind:readSessionNotice(old).kind,invalid:readSessionNotice(invalid)??null,
        kind:parsed.kind,text:parsed.text,turn:parsed.turn,bg:spec.bgToken,label:spec.label,content:formatSessionNotice(parsed)}));
    """, tmp_path)
    assert result["oldKind"] == "result" and result["invalid"] is None
    assert result["kind"] == "unanswered" and result["text"] == "  partial\n"
    assert result["turn"] == 3 and result["bg"] == "toolErrorBg" and result["label"] == "unanswered"
    assert "No usable final answer" in result["content"]


def test_malformed_notice_metadata_is_rejected_instead_of_fabricated(tmp_path: Path) -> None:
    result = _m5_run("""
      const {readSessionNotice,boundedFinalDiagnostic}=await import("file://"+process.cwd()+"/src/session-result.ts");
      const base={kind:"result",name:"review",session:"session:review:incarnation",text:"answer"};
      const malformed=[
        {...base,turn:0}, {...base,turn:NaN}, {...base,turn:"1"},
        {...base,deliveredAt:Infinity}, {...base,deliveredAt:1e20}, {...base,deliveredAt:"now"},
      ];
      const diagnostic="x".repeat(999)+"𐐀"+"tail";
      const bounded=boundedFinalDiagnostic(diagnostic);
      console.log(JSON.stringify({rejected:malformed.map(value=>readSessionNotice(value)===undefined),bounded,wellFormed:bounded?.includes("𐐀")===false && !/\\ud800|\\udc00/.test(JSON.stringify(bounded))}));
    """, tmp_path)
    assert result == {
        "rejected": [True, True, True, True, True, True],
        "bounded": "x" * 999 + "… [diagnostic truncated]",
        "wellFormed": True,
    }


def test_started_settle_without_completed_message_is_an_explicit_outcome(tmp_path: Path) -> None:
    result = _m5_run("""
      await call({name:"reviewer",prompt:"Review",tools:[]});begin();
      callbacks.onUpdate({text:"draft",turns:0,finalResponse:true,missingFinal:true});
      console.log(JSON.stringify({kind:sent[0].details.kind,reason:sent[0].details.reason,text:sent[0].details.text}));
    """, tmp_path)
    assert result == {"kind":"unanswered", "reason":"missing-final", "text":"draft"}


def test_unknown_stop_reason_is_bounded_for_delivery_restore_and_render(tmp_path: Path) -> None:
    result = _m5_run("""
      await call({name:"reviewer",prompt:"Review",tools:[]});begin();
      const raw="\\u001b[31m"+"z".repeat(20000);
      callbacks.onUpdate({text:"partial original",turns:1,finalResponse:true,answerComplete:true,stopReason:raw});
      const {readSessionNotice,formatSessionNotice,sessionNoticeSpec}=await import("file://"+process.cwd()+"/src/session-result.ts");
      const restored=readSessionNotice({...sent[0].details,stopReason:raw});
      const content=formatSessionNotice({...sent[0].details,stopReason:raw});
      const spec=sessionNoticeSpec({...sent[0].details,stopReason:raw});
      const listed=await call({operation:"list"});
      console.log(JSON.stringify({reason:sent[0].details.reason,stop:sent[0].details.stopReason,
        restored:restored.stopReason,text:sent[0].details.text,summary:spec.summary.join(" "),
        length:content.length,content,listLength:listed.content[0].text.length}));
    """, tmp_path)
    assert result["reason"] == "incomplete"
    assert result["stop"] == result["restored"] == "unknown", result
    assert result["length"] < 2000 and result["listLength"] < 2000
    assert len(result["summary"]) < 400
    assert "zzzz" not in result["content"] and "stop-reason=\"unknown\"" in result["content"]
    assert result["text"] == "partial original"


@pytest.mark.parametrize("probe", ["message-start", "text-start", "delta-only", "thinking-start", "tool-start", "unknown-stop"])
def test_native_parser_delivery_resets_evidence_per_message(tmp_path: Path, probe: str) -> None:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update(HOME=str(tmp_path), PI_CODING_AGENT_DIR=str(tmp_path / "agent"), PI_TEST_CWD=str(tmp_path), PI_OFFLINE="1")
    result = subprocess.run(["node", "--experimental-test-module-mocks",
        str(PACKAGE / "tests" / "parsed-final-evidence-fixture.ts"), probe],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout) == {"ok": True, "probe": probe}


def test_error_diagnostic_is_bounded_and_original_partial_answer_remains(tmp_path: Path) -> None:
    result = _m5_run("""
      await call({name:"reviewer",prompt:"Review",tools:[]});begin();
      callbacks.onUpdate({text:"Original partial bytes",turns:1,finalResponse:true,answerComplete:true,stopReason:"error",
        errorMessage:"\\u001b[31m"+"x".repeat(5000)});
      console.log(JSON.stringify({kind:sent[0].details.kind,text:sent[0].details.text,error:sent[0].details.errorMessage,content:sent[0].content}));
    """, tmp_path)
    assert result["kind"] == "unanswered"
    assert result["text"] == "Original partial bytes"
    assert len(result["error"]) < 1200
    assert "truncated" in result["error"] and "\x1b" not in result["error"]


# --- Merged from test_parent_history.py ---
"""Parent-scoped durable history through native tool registrants and the library."""

import json
from pathlib import Path

from subagents_helpers import SRC, run_node


def test_tool_uses_native_parent_session_id_for_durable_history(tmp_path: Path) -> None:
    definition = tmp_path / "project" / ".pi" / "agents" / "reviewer" / "agent.md"
    definition.parent.mkdir(parents=True)
    definition.write_text("---\nname: reviewer\ndescription: Parent history regression\ntools: read\n---\nReview.\n")
    result = run_node(f"""
      import fs from "node:fs";import path from "node:path";
      import {{registerIntentTools}} from {json.dumps((SRC / 'intent-tools.ts').as_uri())};
      import {{ensureAgentWorkspace}} from {json.dumps((SRC / 'workspace.ts').as_uri())};
      const tools=new Map(),spawns=[],workspaces=[];
      const pi={{registerTool:tool=>tools.set(tool.name,tool)}};
      const options={{spawn:input=>{{spawns.push(input);return {{pid:42,readiness:Promise.resolve(true)}};}},
        terminate:async()=>({{outcome:"closed"}}),workspace:input=>{{workspaces.push(input);return ensureAgentWorkspace(input);}}}};
      registerIntentTools(pi,options);
      const ctx=id=>({{cwd:process.env.PI_TEST_CWD,sessionManager:{{getSessionId:()=>id}}}});
      const start=async id=>tools.get("agent_start").execute("start-"+id,
        {{identity:"reviewer",prompt:"Check"}},undefined,undefined,ctx(id));
      const stop=async (id,result)=>tools.get("agent_stop").execute("stop-"+id,
        {{session:result.details.session}},undefined,undefined,ctx(id));
      const a=await start("parent-A");await stop("parent-A",a);
      fs.writeFileSync(path.join(spawns[0].sessionDir,"history.jsonl"),JSON.stringify({{type:"session",version:3,id:"A",cwd:process.env.PI_TEST_CWD}})+"\\n");
      const b=await start("parent-B");await stop("parent-B",b);
      const resumed=await start("parent-A");await stop("parent-A",resumed);
      console.log(JSON.stringify({{ok:[a,b,resumed].map(value=>value.details.ok),parents:workspaces.map(input=>input.parentSessionId),
        paths:spawns.map(input=>input.sessionDir),modes:spawns.map(input=>input.session),cwd:spawns.map(input=>input.cwd),
        scratch:workspaces.map(input=>ensureAgentWorkspace(input).workspacePath)}}));
    """, env_overrides={"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
                       "PI_TEST_CWD": str(tmp_path / "project")})
    assert result["ok"] == [True, True, True]
    parents = result["parents"]
    assert parents == ["parent-A", "parent-B", "parent-A"]
    paths = result["paths"]
    assert paths[0] == paths[2] and paths[0] != paths[1]
    assert result["modes"] == ["persist", "persist", "resume"]
    assert result["cwd"] == [str(tmp_path / "project")] * 3
    assert len(set(result["scratch"])) == 1


def test_headless_parent_id_is_explicit_or_process_local(tmp_path: Path) -> None:
    definition = tmp_path / "project" / ".pi" / "agents" / "reviewer" / "agent.md"
    definition.parent.mkdir(parents=True)
    definition.write_text("---\nname: reviewer\ndescription: Parent history regression\ntools: read\n---\nReview.\n")
    result = run_node(f"""
      import {{executeChildIntent}} from {json.dumps((SRC / 'child-execution.ts').as_uri())};
      import {{ensureAgentWorkspace}} from {json.dumps((SRC / 'workspace.ts').as_uri())};
      const inputs=[];
      const options={{cwd:process.env.PI_TEST_CWD,spawn:()=>({{pid:42,readiness:Promise.resolve(true)}}),
        terminate:async()=>({{outcome:"closed"}}),workspace:input=>{{inputs.push(input);return ensureAgentWorkspace(input);}}}};
      for(const parentSessionId of ["embedded-parent",undefined,undefined]){{
        const started=await executeChildIntent({{name:"reviewer",prompt:"Check"}},{{...options,...(parentSessionId?{{parentSessionId}}:{{}})}});
        if(!started.details.ok)throw new Error(started.details.error);
        await executeChildIntent({{operation:"stop",session:started.details.session}},options);
      }}
      console.log(JSON.stringify({{parents:inputs.map(input=>input.parentSessionId)}}));
    """, env_overrides={"HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
                       "PI_TEST_CWD": str(tmp_path / "project")})
    parents = result["parents"]
    assert parents[0] == "embedded-parent"
    assert isinstance(parents[1], str) and parents[1] and parents[1] == parents[2]
    assert parents[1] != "embedded-parent"
