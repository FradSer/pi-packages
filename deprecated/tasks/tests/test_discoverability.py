"""Tool descriptions expose Tasks without request injection."""

from __future__ import annotations

import json
from pathlib import Path

from task_helpers import PACKAGE, run_node, source

ENTRY = (PACKAGE / "index.ts").as_uri()

TOOL_NAMES = ["create_task", "get_task", "list_tasks", "update_task"]


def run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(
        f"""
        import * as task from {json.dumps(ENTRY)};
        const handlers = new Map();
        const registered = [];
        task.default({{
          registerTool(tool) {{ registered.push({{ name: tool.name, snippet: tool.promptSnippet, description: tool.description }}); }},
          on(name, handler) {{ handlers.set(name, handler); }},
          events: {{ emit() {{}} }},
        }});
        {script}
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )


def test_create_task_states_when_recording_a_task_is_warranted(tmp_path: Path) -> None:
    result = run(
        """
        const create = registered.find((tool) => tool.name === "create_task");
        const text = `${create.snippet} ${create.description}`;
        console.log(JSON.stringify({
          snippetNamesTask: /task/.test(create.snippet) && create.snippet.length <= 80,
          snippetStatesTrigger: /several steps|several files/.test(create.snippet),
          statesSeveralSteps: /several steps or several files/.test(text),
          statesOutlivesTurn: /outlives this turn/.test(text),
          statesSingleEditIsNotATask: /single edit is not a task/.test(text),
          statesNotAGoal: /not a goal/.test(text),
          statesGoalKeepsRunning: /keeps running until it is met/.test(text),
          statesUnitOfWork: /one unit of work/.test(text),
          statesSubjectIsShortName: /short name for the row/.test(text),
          statesSubjectLimit: /at most 60 characters/.test(text),
          statesSubjectAloneIsComplete: /subject alone is a complete task/.test(text),
          statesDescriptionIsOptional: /add description only for detail that does not fit/.test(text),
          statesDependsOnTrigger: /cannot start before another/.test(text),
          statesSupersedesTrigger: /obsolete or wrong/.test(text),
        }));
        """,
        tmp_path,
    )
    assert result["snippetNamesTask"] is True
    assert result["snippetStatesTrigger"] is True
    assert result["statesSeveralSteps"] is True
    assert result["statesOutlivesTurn"] is True
    assert result["statesSingleEditIsNotATask"] is True
    assert result["statesNotAGoal"] is True
    assert result["statesGoalKeepsRunning"] is True
    assert result["statesUnitOfWork"] is True
    assert result["statesSubjectIsShortName"] is True
    assert result["statesSubjectLimit"] is True
    assert result["statesSubjectAloneIsComplete"] is True
    assert result["statesDescriptionIsOptional"] is True
    assert result["statesDependsOnTrigger"] is True
    assert result["statesSupersedesTrigger"] is True


def test_all_four_tools_reach_the_model_with_a_snippet(tmp_path: Path) -> None:
    result = run(
        """
        console.log(JSON.stringify({
          names: registered.map((tool) => tool.name),
          snippetless: registered.filter((tool) => !tool.snippet?.trim()).map((tool) => tool.name),
        }));
        """,
        tmp_path,
    )
    assert sorted(result["names"]) == sorted(TOOL_NAMES)
    assert result["snippetless"] == []


def test_the_repository_instructions_name_when_to_use_the_tools() -> None:
    """A session that has not loaded this package reads the repository instead."""
    instructions = (PACKAGE.parents[1] / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Task Records" in instructions
    # Whitespace is collapsed first: the file wraps at 80 columns, so a phrase the
    # reader sees as one line arrives with a newline inside it.
    section = " ".join(instructions.split("## Task Records", 1)[1].split("\n## ", 1)[0].split())
    for name in TOOL_NAMES:
        assert name in section, name
    assert "several steps or several files" in section
    assert "single edit is not a task" in section
    # The limit a delegating session has to know before it plans around it.
    assert "do not reach a child process" in section
    assert "cannot take or complete" in section