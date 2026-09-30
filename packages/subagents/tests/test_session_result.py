"""Session Result delivery from a standalone child.

Contract: features/session-result.feature

One seam: the package extension entry with a fake `ExtensionAPI`. The entry is
the highest boundary that owns both halves of the feature — the tool, the message
renderers, and the sender — so these tests drive the real `agent` tool with an
injected spawn, feed it the progress frames the real spawner emits, and assert
on the messages that were sent. Nothing here reaches into the delivery module.
"""

from __future__ import annotations

import json
import os
import subprocess

from subagents_helpers import PACKAGE, run_node

ENTRY = (PACKAGE / "index.ts").as_uri()
BARREL = (PACKAGE / "index.ts").as_uri()
SPAWNER = (PACKAGE / "src" / "spawner.ts").as_uri()

# The real entry, the real tool, the real delivery — with only the child process
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
    terminateTeammate: async (name) => {{ terminations.push(name); return {{ outcome: "closed" }}; }},
  }},
}});

const {{ default: piSubagentsExtension, setAgentHost }} = await import({json.dumps(ENTRY)});

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
const agent = registered.find((tool) => tool.name === "agent");
assert.ok(agent, "the entry registers the agent tool");

const ctx = {{ cwd: process.cwd() }};
const start = (params) => agent.execute("row", params, undefined, undefined, ctx);
const settle = (text) => frames({{ text, turns: 1, finalResponse: true, modelOutputSeen: true }});
const beginTurn = () => frames({{ text: "", turns: 0, finalResponse: false, modelOutputSeen: true }});
const results = () => sent.filter((message) => message.customType === "subagents-session-result");
const ended = () => sent.filter((message) => message.customType === "subagents-session-ended");
const theme = {{ fg: (_name, text) => text, bg: (_name, text) => text, bold: (text) => text }};
const paint = (message, expanded) => stripVTControlCharacters(
  renderers.get(message.customType)(message, {{ expanded }}, theme).render(90).map((row) => row.replace(/\\s+$/, "")).join("\\n"),
);
"""


def run(script: str) -> None:
    run_node(f"{PREAMBLE}\n{script}", module_mocks=True)


def test_a_prompted_childs_answer_is_delivered_verbatim_with_its_provenance() -> None:
    run(
        """
        const started = await start({ action: "start", name: "solo", prompt: "Reply with the number 1+1.", tools: [] });
        assert.equal(started.details.outcome, "started", started.content[0].text);
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
        assert.equal(message.details.name, "solo");
        assert.match(message.details.session, /^session:solo:/);
        assert.equal(message.details.turn, 1);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_one_delivery_per_settled_turn_not_per_frame() -> None:
    run(
        """
        await start({ action: "start", name: "solo", prompt: "Work.", tools: [] });
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
        await start({ action: "start", name: "solo", prompt: "First question.", tools: [] });
        beginTurn();
        settle("first answer");
        beginTurn();
        settle("second answer");
        const delivered = results();
        assert.equal(delivered.length, 2, `each settled turn is its own result:\\n${JSON.stringify(sent)}`);
        assert.ok(delivered[1].content.includes("second answer"));
        assert.equal(delivered[0].details.turn, 1);
        assert.equal(delivered[1].details.turn, 2);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_an_empty_settled_answer_is_not_delivered() -> None:
    run(
        """
        await start({ action: "start", name: "solo", prompt: "Say nothing.", tools: [] });
        beginTurn();
        settle("   ");
        assert.deepEqual(results(), [], "a child with nothing to say costs no turn");
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
        await start({ action: "start", name: "solo", prompt: "Reply with the number 1+1.", tools: [] });
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


def test_the_delivered_message_renders_as_one_row_without_handles() -> None:
    run(
        """
        initTheme("dark", false);
        setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }));
        const started = await start({ action: "start", name: "solo", prompt: "Do the work.\\nAnd check the widget.", tools: [] });
        beginTurn();
        settle("Fixed the spacing under the started row.\\nThe widget lines up at 90 columns.");
        const [message] = results();
        const collapsed = paint(message, false);
        assert.match(collapsed, /\\[agent\\] reported · @solo|\\[agent\\] result · @solo/, collapsed);
        assert.ok(collapsed.includes("Fixed the spacing"), `row dropped the result headline:\\n${collapsed}`);
        assert.ok(!collapsed.includes("solo:"), `row leaked a session handle:\\n${collapsed}`);
        assert.ok(!/session:/.test(collapsed), `row leaked a session handle:\\n${collapsed}`);
        const expanded = paint(message, true);
        assert.ok(expanded.includes("The widget lines up at 90 columns."), `expansion clipped the result:\\n${expanded}`);
        // The prompt is the start row's business; repeating it here would put the
        // same line in the transcript twice.
        assert.ok(!expanded.includes("Do the work."), `the result row repeated the prompt:\\n${expanded}`);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_child_that_ends_without_a_result_shows_one_visible_line_and_no_turn() -> None:
    run(
        """
        const started = await start({ action: "start", name: "solo", prompt: "Work.", tools: [] });
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
        // The detail stays where detail belongs: the roster, read through `list`.
        // An exact handle addresses a living incarnation by design, so a stopped
        // child is listed rather than inspected.
        const listed = await start({ action: "list" });
        assert.ok(listed.details.agents[0].error, "the roster keeps the exit detail");
        const refused = await start({ action: "inspect", session: started.details.session });
        assert.equal(refused.details.ok, false, "a retired handle does not resolve");
        assert.match(refused.content[0].text, /No living session/);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_death_that_leaves_a_later_turn_unanswered_is_announced() -> None:
    run(
        """
        await start({ action: "start", name: "solo", prompt: "First question.", tools: [] });
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
        const started = await start({ action: "start", name: "solo", tools: [] });
        const stopped = await start({ action: "stop", session: started.details.session });
        assert.equal(stopped.details.outcome, "stopped", stopped.content[0].text);
        assert.deepEqual(terminations, ["solo"], "the stop reached the terminator");
        exits({ pid: 4242, exitCode: null, signal: "SIGTERM", stdout: "", stderr: "" });
        // The stop receipt is the report. Painting SIGTERM on the failure band
        // would tell a person their own shutdown was a death.
        assert.deepEqual(ended(), [], `a planned stop is not news:\\n${JSON.stringify(sent)}`);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_an_answered_child_is_listed_as_idle_with_its_answer() -> None:
    run(
        """
        await start({ action: "start", name: "solo", prompt: "Reply with the number 1+1.", tools: [] });
        beginTurn();
        settle("2");
        const listed = await start({ action: "list" });
        const [entry] = listed.details.agents;
        assert.equal(entry.status, "idle", "a child that answered is not working");
        assert.equal(entry.liveText, "2", "the roster is the second read of a result");
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_child_that_already_reported_is_not_announced_as_ended() -> None:
    run(
        """
        const started = await start({ action: "start", name: "solo", prompt: "Work.", tools: [] });
        beginTurn();
        settle("done");
        exits({ pid: 4242, exitCode: 0, signal: null, stdout: "", stderr: "" });
        assert.equal(ended().length, 0, `a reported child ending is not news:\\n${JSON.stringify(sent)}`);
        assert.equal(results().length, 1);
        assert.equal(started.details.outcome, "started");
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_coordinator_host_keeps_ownership_of_delivery() -> None:
    run(
        """
        setAgentHost({
          start: async () => ({ ok: true, session: "session:hosted:s1" }),
          stop: async () => ({ ok: true }),
        });
        const hosted = await start({ action: "start", name: "hosted", prompt: "Work.", tools: [] });
        assert.equal(hosted.details.outcome, "started");
        setAgentHost(undefined);
        // The host owns the spawn and the report; the execution layer delivering
        // its own copy is the double-delivery this guards.
        assert.deepEqual(sent, [], `a hosted spawn delivers nothing itself:\\n${JSON.stringify(sent)}`);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_the_entry_registers_a_renderer_for_each_message_type() -> None:
    run(
        """
        assert.equal(typeof renderers.get("subagents-session-result"), "function");
        assert.equal(typeof renderers.get("subagents-session-ended"), "function");
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
        const agent = tools.find((t) => t.name === "agent");
        assert.ok(agent, "the tool registers without the optional surfaces");
        const started = await agent.execute("t", {{ action: "start", name: "bare", prompt: "Work.", tools: [] }},
          undefined, undefined, {{ cwd: process.cwd() }});
        assert.equal(started.details.ok, true, started.content[0].text);
        // A settled frame with nowhere to go is not an error: the roster keeps it.
        frames({{ text: "the answer", turns: 1, finalResponse: true, modelOutputSeen: true }});
        const listed = await agent.execute("t", {{ action: "list" }}, undefined, undefined, {{ cwd: process.cwd() }});
        assert.equal(listed.details.agents[0].liveText, "the answer");
        exits({{ pid: 11, exitCode: 0, signal: null, stdout: "", stderr: "" }});
        console.log(JSON.stringify({{ ok: true }}));
        """,
        module_mocks=True,
    )
    assert result["ok"] is True


def test_the_library_barrel_loads_no_tui_module() -> None:
    """The scenario "the library stays free of the TUI" is only true if the
    barrel Pi loads as an extension is the same file another package imports as
    a library, and that file pulls in no pi-tui."""
    result = run_node(
        f"""
        import assert from "node:assert/strict";
        const before = new Set(Object.keys(process.getBuiltinModule?.("node:module")._cache ?? {{}}));
        const loaded = (specifier) => Object.keys(process.getBuiltinModule("node:module")._cache)
          .some((key) => key.includes(specifier));
        await import({json.dumps(BARREL)});
        assert.ok(!loaded("pi-tui"), "importing the library barrel must not load pi-tui");
        assert.ok(!loaded("pi-coding-agent"), "importing the library barrel must not load the host API");
        console.log(JSON.stringify({{ ok: true }}));
        """
    )
    assert result["ok"] is True


def test_a_settle_reaching_the_spawner_with_the_next_turn_is_still_reported() -> None:
    """The parser, not a hand-written frame.

    A real child can settle and start its next turn inside one stdout read. If
    the spawner reports one frame per read, the settle is invisible — which is
    exactly the failure this feature exists to remove, and exactly what a
    hand-written frame list cannot catch. Driven by
    `coalesced-settle-fixture.ts`, because node only exposes module mocking
    reliably for a real entry point.
    """
    result = subprocess.run(
        ["node", "--experimental-test-module-mocks", str(PACKAGE / "tests" / "coalesced-settle-fixture.ts")],
        cwd=PACKAGE,
        check=False,
        capture_output=True,
        text=True,
        env={key: value for key, value in os.environ.items() if not key.startswith("PI_TEAMMATE_")},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True
