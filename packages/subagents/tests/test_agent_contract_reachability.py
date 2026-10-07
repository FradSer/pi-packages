"""Observable contract for the startup reachability rules in features/intent-tools.feature."""
from __future__ import annotations

import json
from pathlib import Path

from subagents_helpers import PACKAGE, SRC, run_node

ENTRY = (PACKAGE / "index.ts").as_uri()
INTENT_TOOLS = (SRC / "intent-tools.ts").as_uri()

PREAMBLE = f"""
import assert from 'node:assert/strict';
import {{ stripVTControlCharacters }} from 'node:util';
import piSubagentsExtension from {json.dumps(ENTRY)};
import {{ executeIntentTool, INTENT_TOOL_SCHEMAS }} from {json.dumps(INTENT_TOOLS)};

const registered = [];
const pi = {{ registerTool: (tool) => registered.push(tool), registerMessageRenderer() {{}}, on() {{}}, events: {{ emit() {{}} }} }};
piSubagentsExtension(pi);
const intentTools = new Map(registered.map((tool) => [tool.name, tool]));

const spawns = [];
const options = {{
  cwd: process.env.PI_TEST_CWD,
  spawn: (value) => {{ spawns.push(value); return {{ pid: 42, accepted: Promise.resolve(true), readiness: Promise.resolve(true) }}; }},
  prompt: async () => true,
  steer: async () => true,
  terminate: async () => ({{ outcome: 'closed' }}),
  deliverSessionResult: () => {{}},
}};
const call = async (name, args) => (await executeIntentTool(name, args, options)).structuredContent;
const {{ Check }} = await import('typebox/value');
"""


def run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(PREAMBLE + script, env_overrides={
        "PI_TEST_CWD": str(tmp_path), "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "HOME": str(tmp_path),
    })


def test_an_empty_identity_is_a_temporary_role(tmp_path: Path) -> None:
    """A caller that names an identity with no value gets a temporary child.

    The extension already reads an empty identity as absent, so the declared
    schema accepts what the extension accepts instead of refusing a call the
    product itself would have served.
    """
    result = run("""
      const empty = await call('agent_start', { identity: '', prompt: 'FIRST', instructions: 'TEMP ROLE' });
      const absent = await call('agent_start', { prompt: 'SECOND' });
      console.log(JSON.stringify({
        declared: Check(INTENT_TOOL_SCHEMAS.agent_start, { prompt: 'THIRD', identity: '' }),
        empty: { ok: empty.ok, name: empty.name, scope: empty.scope, identity: empty.identity ?? null },
        absent: { ok: absent.ok, scope: absent.scope },
        spawns: spawns.map((value) => ({ description: value.description ?? null, role: value.env?.PI_SUBAGENT_ROLE ?? null })),
      }));
    """, tmp_path)
    assert result["declared"] is True, "the schema accepts an identity field with no value"
    assert result["empty"]["ok"] is True
    assert result["empty"]["scope"] == "session"
    assert result["empty"]["identity"] is None, "an empty identity is not an identity"
    assert result["empty"]["name"] != "", "a temporary child never carries an empty name"
    assert len(result["spawns"]) == 2
    assert result["spawns"][0]["description"], "a temporary child still carries the role half it was given"
    assert result["spawns"][0]["role"] is None, "a temporary child carries no saved identity"


def test_the_tools_parameter_names_every_grantable_id(tmp_path: Path) -> None:
    """The description is the only contract a caller reads before spending a call.

    The ids a child accepts are a fixed set, and a project-extension tool is not
    in it. Both facts belong in the parameter description, because a refused call
    is the only other place they appear.
    """
    result = run("""
      const description = INTENT_TOOL_SCHEMAS.agent_start.properties.tools.description;
      console.log(JSON.stringify({
        missing: ['read','bash','edit','write','grep','find','ls','powershell','agent_memory'].filter((id) => !new RegExp(`\\\\b${id}\\\\b`).test(description)),
        child: /bare pi process|child process/i.test(description),
        extension: /extension|MCP/i.test(description),
      }));
    """, tmp_path)
    assert result["missing"] == [], "every grantable id is named"
    assert result["child"] is True
    assert result["extension"] is True


def test_an_empty_definition_list_says_where_an_identity_lives(tmp_path: Path) -> None:
    """Zero saved identities is a state the caller has to act on.

    The row names the project-local path a repository identity uses and states
    that a temporary role needs no file, so the first reachable answer is not the
    user-scope path under the agent home.
    """
    result = run("""
      const listed = await executeIntentTool('agent_list', {}, options);
      const component = intentTools.get('agent_list').renderResult(
        { content: listed.content, details: listed.details },
        { expanded: true, isPartial: false },
        { fg: (_n, text) => text, bg: (_n, text) => text, bold: (text) => text },
        { args: {}, toolCallId: 'empty-page', isError: false },
      );
      console.log(JSON.stringify({ rows: component.render(120).map(stripVTControlCharacters) }));
    """, tmp_path)
    text = "\n".join(str(row) for row in result["rows"])
    assert ".pi/agents/" in text, f"the project-local identity path is named:\n{text}"
    assert "temporary" in text.lower()