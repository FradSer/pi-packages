"""Shared standalone child setup; execution and callbacks use the real runtime."""
from __future__ import annotations

import json
from pathlib import Path

from subagents_helpers import PACKAGE, SRC, run_node

PREAMBLE = f"""
import assert from "node:assert/strict";
import * as roster from {json.dumps((SRC / "roster.ts").as_uri())};
import {{ executeChildIntent }} from {json.dumps((SRC / "child-execution.ts").as_uri())};
import {{ registerSessionAgent }} from {json.dumps((SRC / "agents.ts").as_uri())};
roster.resetRoster();
const spawns = [], prompts = [], steers = [], notices = [], workspaces = [];
let ready = true;
let accepted = true;
let steerAccepted = true;
const cwd = process.env.PI_TEST_CWD;
const call = (params, extra = {{}}) => executeChildIntent(params, {{
  cwd,
  parentSessionId: "resident-parent",
  leaderModel: () => "test/parent",
  thinking: () => "low",
  spawn: (options) => {{ spawns.push(options); return {{ pid: 42, readiness: Promise.resolve(ready) }}; }},
  prompt: async (name, message) => {{ prompts.push({{ name, message }}); return accepted; }},
  steer: (name, message) => {{ steers.push({{ name, message }}); return steerAccepted; }},
  terminate: async () => ({{ outcome: "closed" }}),
  workspace: (input) => {{ workspaces.push(input); return {{ cwd:input.cwd,
    workspacePath:process.env.PI_CODING_AGENT_DIR+"/agents/"+input.agentName+"/workspace",
    sessionDir:process.env.PI_CODING_AGENT_DIR+"/agents/"+input.agentName+"/projects/test/session",reused:false }}; }},
  deliverSessionResult: (notice) => notices.push(notice),
  ...extra,
}});
const final = (index, text) => spawns[index].onUpdate({{ text, turns: 1, finalResponse: true }});
"""


def run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(PREAMBLE + script, env_overrides={
        "PI_TEST_CWD": str(tmp_path),
        "PI_CODING_AGENT_DIR": str(tmp_path / "agent"),
        "HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
    })


def role(tmp_path: Path, name: str, fields: str) -> None:
    directory = tmp_path / ".pi" / "agents" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent.md").write_text(
        f"---\nname: {name}\ndescription: inspect\n{fields}---\nPINNED ROLE BODY\n", encoding="utf-8",
    )


