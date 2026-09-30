"""The `agent` tool's transcript row.

Contract: features/agent-row-tui.feature

The package entry is what Pi loads, so the entry is what must bind the shared
lifecycle renderer. Driving `executeAgentAction` with an injected spawn and
painting through the *entry-registered* renderer keeps the two halves of the
contract separate: this asserts the row a person sees, not the receipt text the
model reads.
"""

from __future__ import annotations

import json

from subagents_helpers import PACKAGE, run_node

ENTRY = (PACKAGE / "index.ts").as_uri()

PREAMBLE = f"""
import assert from "node:assert/strict";
import {{ stripVTControlCharacters }} from "node:util";
import {{ KeybindingsManager, setKeybindings, visibleWidth }} from "@earendil-works/pi-tui";
import {{ initTheme }} from "@earendil-works/pi-coding-agent";
import piSubagentsExtension, {{ executeAgentAction }} from {json.dumps(ENTRY)};

const theme = {{ fg: (_name, text) => text, bg: (_name, text) => text, bold: (text) => text }};
const calls = [];
const pi = {{ registerTool: (tool) => calls.push(tool), on() {{}}, events: {{ emit() {{}} }} }};
piSubagentsExtension(pi);
const agent = calls.find((tool) => tool.name === "agent");
assert.ok(agent, "the extension entry registers the agent tool");
assert.equal(typeof agent.renderResult, "function", "the entry must bind the lifecycle result renderer");
assert.deepEqual(agent.renderCall().render(), [], "the started call line stays empty");

const width = 120;
const paint = (result, expanded) => {{
  const component = agent.renderResult(
    {{ content: result.content, details: result.details }},
    {{ expanded, isPartial: false }},
    theme,
    {{ args: {{}}, toolCallId: "row", isError: false }},
  );
  assert.ok(component && typeof component.render === "function", "the renderer returns a component");
  const rows = component.render(width);
  assert.ok(rows.every((row) => visibleWidth(row) <= width), `row exceeds {{width}} columns:\\n${{rows.join("\\n")}}`);
  return rows.map(stripVTControlCharacters);
}};
const run = (params) => executeAgentAction(params, {{
  cwd: process.cwd(),
  spawn: () => ({{ pid: 7 }}),
  deliver: () => true,
}});
"""


def run(script: str) -> None:
    run_node(f"{PREAMBLE}\n{script}")


def test_the_entry_binds_a_row_renderer_and_survives_a_headless_load() -> None:
    """Registration and a first render happen before any theme exists.

    The renderer resolves its expand hint per render precisely so this path
    cannot throw: a row built here and painted in a real session is the same
    component, and a module that needed `initTheme` at import time would take
    every headless test down with it.
    """
    run(
        """
        const early = await run({ action: "start", name: "row-headless", prompt: "One short question." });
        assert.ok(paint(early, false).length > 0, "a render before initTheme must still produce rows");
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_started_child_renders_one_band_naming_it_and_its_work() -> None:
    run(
        """
        const started = await run({
          action: "start",
          name: "row-tui",
          prompt: "Add the ledger row.\\nThen check the widget.",
          tools: ["read"],
        });
        assert.equal(started.details.outcome, "started", started.content[0].text);
        const collapsed = paint(started, false).join("\\n");
        assert.match(collapsed, /\\[agent\\] started · @row-tui/, collapsed);
        assert.ok(collapsed.includes("Add the ledger row."), `row dropped the prompt headline:\\n${collapsed}`);
        assert.ok(!collapsed.includes("role ·"), `collapsed row must stay one line:\\n${collapsed}`);
        // The handle is the model's addressing mechanism and a person's noise.
        assert.ok(!/session:|\\b[0-9a-f]{8}-[0-9a-f]{4}-/.test(collapsed), `row leaked a handle:\\n${collapsed}`);

        const expanded = paint(started, true).join("\\n");
        assert.ok(expanded.includes("tools · read"), `expanded row missing the grant:\\n${expanded}`);
        assert.ok(expanded.includes("Then check the widget."), `expanded row clipped the prompt:\\n${expanded}`);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_child_with_no_prompt_says_it_is_waiting() -> None:
    run(
        """
        const idle = await run({ action: "start", name: "row-idle" });
        assert.equal(idle.details.prompted, false);
        const collapsed = paint(idle, false).join("\\n");
        assert.match(collapsed, /\\[agent\\] started · @row-idle/, collapsed);
        assert.match(collapsed, /take work assigned to it/, collapsed);
        // The receipt keeps saying it for the model, which is who acts on it.
        assert.match(idle.content[0].text, /take work assigned to it/);
        console.log(JSON.stringify({ ok: true }));
        """
    )


def test_a_rendered_row_advertises_expansion_through_the_configured_key() -> None:
    run(
        """
        initTheme("dark", false);
        setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }));
        const started = await run({
          action: "start",
          name: "row-hint",
          prompt: `${"evidence ".repeat(60)}TAIL`,
        });
        const collapsed = paint(started, false).join("\\n");
        assert.match(collapsed, /to expand/, `a clipped row must advertise expansion:\\n${collapsed}`);
        console.log(JSON.stringify({ ok: true }));
        """
    )
