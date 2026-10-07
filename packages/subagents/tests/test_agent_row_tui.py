"""The intent family's transcript rows.

Contract: features/agent-row-tui.feature

The package entry is what Pi loads, so the entry is what binds the shared
lifecycle renderer. Driving the intent family with an injected spawn and
painting through the *entry-registered* renderer keeps the two halves of the
contract separate: this asserts the row a person sees, not the receipt text the
model reads.
"""

from __future__ import annotations

import json
from pathlib import Path

from subagents_helpers import PACKAGE, SRC, run_isolated_node as run_node



ENTRY = (PACKAGE / "index.ts").as_uri()
INTENT_TOOLS = (SRC / "intent-tools.ts").as_uri()
ROSTER = (SRC / "roster.ts").as_uri()

PREAMBLE = f"""
import assert from "node:assert/strict";
import {{ stripVTControlCharacters }} from "node:util";
import {{ KeybindingsManager, setKeybindings, visibleWidth }} from "@earendil-works/pi-tui";
import {{ initTheme }} from "@earendil-works/pi-coding-agent";
import piSubagentsExtension from {json.dumps(ENTRY)};
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


def run(script: str) -> None:
    run_node(f"{PREAMBLE}\n{script}")


def run_isolated(script: str, tmp_path: Path) -> None:
    """A run with its own agent directory and working tree, for the rows that need
    a saved definition. Isolated because a project identity creates its folder
    under the agent directory, and a row test must not write into the developer's
    own."""
    run_node(
        f"{PREAMBLE}\n{script}",
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
    run(
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
        for (const fact of [`session · ${started.details.session}`, "tools · read", "state · starting", "next · runtime"]) {
          assert.ok(text.includes(fact), `expanded row dropped ${fact}:\\n${text}`);
          assert.equal(text.split(fact).length - 1, 1, `expanded row repeated ${fact}:\\n${text}`);
        }
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_startup_model_metadata_is_rendered_once_without_changing_the_receipt() -> None:
    run(
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
    run(
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
    run(
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
    run(
        """
        const renderer = messageRenderers.get("subagents-parent-message");
        assert.equal(typeof renderer, "function", "the entry binds an independent parent-message renderer");
        const details = { kind: "intermediate", name: "worker", session: "session:worker:incarnation", inputId: "input-1", sequence: 1, text: "**Keep** this body", deliveredAt: 0 };
        const collapsed = renderer({ content: details.text, details }, { expanded: false }, theme).render(100).join("\\n");
        const expanded = renderer({ content: details.text, details }, { expanded: true }, theme).render(100).join("\\n");
        assert.match(collapsed, /\\[agent\\] message · @worker/);
        assert.ok(expanded.includes("Keep") && expanded.includes("session · session:worker:incarnation") && expanded.includes("input · input-1"), expanded);
        const malformed = renderer({ content: "ignored", details: { kind: "intermediate", name: "worker", session: "session:worker:incarnation", sequence: 1e20, text: "body", deliveredAt: 1e20 } }, { expanded: true }, theme).render(100).join("\\n");
        assert.ok(malformed.includes("intermediate message details were invalid"), malformed);
        const missingTimestamp = renderer({ content: "ignored", details: { kind: "intermediate", name: "worker", session: "session:worker:incarnation", sequence: 1, text: "body" } }, { expanded: true }, theme).render(100).join("\\n");
        assert.ok(missingTimestamp.includes("intermediate message details were invalid"), missingTimestamp);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_long_single_line_steer_is_expandable_without_losing_its_first_line_tail() -> None:
    run(
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
        assert.ok(expanded.includes(`session · ${result.details.session}`), expanded);
        assert.ok(expanded.includes("state · starting") && expanded.includes("next · runtime"), expanded);
        assert.equal(band(paint("agent_input", result, false, 80)).join("\\n"), collapsed.join("\\n"));
        assert.equal(JSON.stringify(result), before);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_short_input_expands_metadata_without_duplicate_input() -> None:
    run(
        """
        initTheme("dark", false);
        setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }));
        for (const delivery of ["next", "steer"]) {
          const started = await run({ operation: "start", label: `row-${delivery}`, prompt: "Work.", tools: [] });
          const prompt = "Only the number";
          const result = await run({ operation: delivery, session: started.details.session, prompt });
          assert.equal(result.details.ok, true, result.content[0].text);
          const collapsed = band(paint("agent_input", result, false));
          assert.ok(collapsed[0].includes("to expand"), `${delivery} hides its expansion affordance:\\n${collapsed.join("\\n")}`);
          assert.equal(collapsed[1].trim(), prompt);
          assert.ok(!collapsed.join("\\n").includes(result.details.session), collapsed.join("\\n"));
          const expanded = paint("agent_input", result, true).join("\\n");
          assert.equal(expanded.split(prompt).length - 1, 1, expanded);
          assert.ok(expanded.includes(`session · ${result.details.session}`), expanded);
          assert.ok(expanded.includes("state · starting") && expanded.includes("next · runtime"), expanded);
        }
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_multiline_input_keeps_first_and_later_paragraphs_once() -> None:
    run(
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
    run(
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