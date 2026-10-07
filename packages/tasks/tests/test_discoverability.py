"""How a session learns the task tools exist.

Contract: packages/tasks/features/discoverability.feature

Two surfaces carry the trigger conditions. The four tool descriptions say what
each tool is for and are sent on every turn already. The bounded note says when
the situation calls for a tool at all, which a description cannot say. Both are
asserted here, and so is the property that makes the note affordable: it is
identical on every turn and lands at a fixed index.
"""

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
          snippetStatesTrigger: /several steps|several files/.test(create.snippet),
          statesSeveralSteps: /several steps or several files/.test(text),
          statesOutlivesTurn: /outlives this turn/.test(text),
          statesSingleEditIsNotATask: /single edit is not a task/.test(text),
          statesNotAGoal: /not a goal/.test(text),
          statesGoalKeepsRunning: /keeps running until it is met/.test(text),
          statesUnitOfWork: /one unit of work/.test(text),
        }));
        """,
        tmp_path,
    )
    assert result["snippetStatesTrigger"] is True
    assert result["statesSeveralSteps"] is True
    assert result["statesOutlivesTurn"] is True
    assert result["statesSingleEditIsNotATask"] is True
    assert result["statesNotAGoal"] is True
    assert result["statesGoalKeepsRunning"] is True
    assert result["statesUnitOfWork"] is True


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


def test_a_session_with_no_open_task_receives_the_note(tmp_path: Path) -> None:
    """The note is what a session with nothing recorded has to go on.

    A tool description cannot say when to reach for the tool: a session that never
    considers recording work never reads the description of the tool that would
    record it. Measured over 1152 recorded sessions, `create_task` ran 17 times in
    7 sessions while `bash` ran 78178 times, with the descriptions present.
    """
    result = run(
        """
        const request = await handlers.get("context")({ messages: [{ role: "system", content: "s" }, { role: "user", content: "hi" }] }, {});
        const text = request.messages[1].content;
        console.log(JSON.stringify({
          hasNote: text.includes("[pi-tasks capability]"),
          namesTools: ["create_task", "get_task", "list_tasks", "update_task"].filter((name) => text.includes(name)),
          statesSeveralSteps: /several steps or several files/.test(text),
          statesOutlivesTurn: /outlives this turn/.test(text),
          statesSingleEditIsNotATask: /single edit is not a task/.test(text),
          statesNotAGoal: /not a goal/.test(text),
          statesGoalKeepsRunning: /keeps running until it is met/.test(text),
        }));
        """,
        tmp_path,
    )
    assert result["hasNote"] is True
    assert result["namesTools"] == TOOL_NAMES
    assert result["statesSeveralSteps"] is True
    assert result["statesOutlivesTurn"] is True
    assert result["statesSingleEditIsNotATask"] is True
    # The one thing a model reading two similar notes has to get right.
    assert result["statesNotAGoal"] is True
    assert result["statesGoalKeepsRunning"] is True


def test_the_note_is_bounded_and_never_grows_with_the_task_set(tmp_path: Path) -> None:
    result = run(
        """
        const ask = async () => (await handlers.get("context")({ messages: [{ role: "system", content: "s" }] }, {})).messages[1].content;
        const empty = await ask();
        for (let index = 0; index < 25; index += 1) {
          task.createTask({ id: `many-${index}`, subject: `Task number ${index}` });
        }
        task.takeTask("many-0", "main");
        const loaded = await ask();
        console.log(JSON.stringify({
          identical: empty === loaded,
          bytes: Buffer.byteLength(empty, "utf8"),
          namesNoTask: !loaded.includes("many-0") && !loaded.includes("Task number"),
        }));
        """,
        tmp_path,
    )
    assert result["identical"] is True
    assert result["namesNoTask"] is True
    # Bounded is what makes it safe to send every turn. A note that grew with the
    # store would be a second copy of the list.
    assert isinstance(result["bytes"], int) and result["bytes"] < 1024


def test_the_note_lands_at_a_stable_position_so_each_request_prefixes_the_last(tmp_path: Path) -> None:
    """The property that makes a per-turn note affordable.

    The note is identical on every turn, so the same text at the same index keeps
    each request a prefix of the previous one and the provider's implicit prefix
    cache keeps matching. Appending at the tail would differ from the last request
    at the index the newest turn occupies.
    """
    result = run(
        """
        const ask = async (messages) => handlers.get("context")({ messages }, {});
        const first = await ask([{ role: "system", content: "s" }, { role: "user", content: "one" }]);
        const second = await ask([
          { role: "system", content: "s" }, { role: "user", content: "one" }, { role: "assistant", content: "two" },
        ]);
        const position = (messages) => messages.findIndex((message) => String(message.content).includes("[pi-tasks capability]"));
        const prefix = (shorter, longer) => shorter.every((message, index) => JSON.stringify(message) === JSON.stringify(longer[index]));
        const copies = (messages) => messages.filter((message) => String(message.content).includes("[pi-tasks capability]")).length;
        console.log(JSON.stringify({
          firstPosition: position(first.messages), secondPosition: position(second.messages),
          noteUnchanged: first.messages[1].content === second.messages[1].content,
          prefixHolds: prefix(first.messages, second.messages), copies: copies(second.messages),
        }));
        """,
        tmp_path,
    )
    assert result["firstPosition"] == 1
    assert result["secondPosition"] == 1
    assert result["noteUnchanged"] is True
    assert result["prefixHolds"] is True
    assert result["copies"] == 1

    # One definition of the note. A second copy of the text in another module is
    # how the two drift, so the marker lives in exactly one source file.
    holders = [
        name
        for name in ("presence.ts", "extension.ts", "stop-check.ts", "tool.ts", "store.ts", "context.ts")
        if (PACKAGE / "src" / name).exists() and "[pi-tasks capability]" in source(name)
    ]
    assert holders == ["presence.ts"], f"the note has one home: {holders}"


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