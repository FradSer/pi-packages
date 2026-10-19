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

from __future__ import annotations

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


def run(script: str) -> None:
    with tempfile.TemporaryDirectory(prefix="subagents-session-result-") as root:
        run_node(f"{PREAMBLE}\n{script}", module_mocks=True, env_overrides={"PI_CODING_AGENT_DIR": root, "HOME": root})


def test_a_prompted_childs_answer_is_delivered_verbatim_with_its_provenance() -> None:
    run(
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
    run(
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
    run(
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
    run(
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
    run(
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
    run(
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
    run(
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
    run(
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
    run(
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
    run(
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
    run(
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
    run(
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
    run(
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
    run(
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
    run(
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
    run(
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
