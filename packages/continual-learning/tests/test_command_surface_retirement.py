"""Phase 4: one documented command entry and a retired worker tool surface."""
from __future__ import annotations

import json

from support import PKG_DIR, run_bun


def test_runtime_diagnostics_do_not_tell_users_to_type_an_old_command() -> None:
    # A user who hits a Memory write guard, a headless menu, or a status view
    # must be pointed at /learning, never at a retired /memory, /consolidate or
    # /harness command. Frozen fixtures under tests/fixtures/** keep their
    # historical strings byte-identical and are intentionally excluded here.
    retired = ("Use /memory", "Use /consolidate", "Use /harness",
               "type /memory", "type /consolidate", "type /harness")
    offenders: list[str] = []
    for path in (PKG_DIR / "extensions").glob("*.ts"):
        text = path.read_text(encoding="utf-8")
        for phrase in retired:
            if phrase in text:
                offenders.append(f"{path.name}: {phrase}")
    assert offenders == [], offenders


def _inject_source() -> str:
    return (PKG_DIR / "extensions" / "inject-memory.ts").read_text(encoding="utf-8")


def test_learning_menu_harness_branch_uses_the_direct_procedure_bridge() -> None:
    # Given /harness is no longer a registered command, When a user chooses
    # Manage Harness rules in /learning, Then the menu opens the guarded
    # procedure through the same bridge the learn tool uses, instead of
    # looking up a command or telling the user to type /harness.
    source = _inject_source()
    menu = source.split("const openLearningMenu", 1)[1].split("pi.registerCommand(\"learning\"", 1)[0]
    assert "getCommands().find" not in menu
    assert 'name === "harness"' not in menu
    assert "Use /harness" not in menu
    assert " ".join(menu.split()).count("startHarnessProcedureForLearn(") == 1
    assert "Harness rules are unavailable" not in menu


def test_only_learning_is_exposed_to_users() -> None:
    # Phase 4 retires the old *user* command surface: the model guidance and
    # the single documented entry name only /learning. Three legacy command
    # registrations (/memory, /consolidate in inject-memory.ts; /harness in
    # guardrails.ts) deliberately survive as internal frozen-provenance and
    # offline-E2E bindings -- they are never offered in a menu, never named by
    # guidance, and never documented as user input. See HANDOFF.md for the
    # exact completion-gate and frozen-proof consumers that require them.
    source = _inject_source()
    assert 'pi.registerCommand("learning"' in source
    for guidance in (
        "AGENT_LEARNING_TOOL_GUIDANCE",
        "SETTLED_LEARNING_GUIDANCE",
    ):
        block = source.split(guidance, 1)[1].split("`;", 1)[0]
        assert "/memory" not in block and "/consolidate" not in block, guidance
        assert "/harness" not in block, guidance
    # The model guidance must steer to learn without naming retired commands.
    tool_description = source.split("name: AGENT_MEMORY_TOOL", 1)[1].split("async execute", 1)[0]
    assert "/memory" not in tool_description and "/consolidate" not in tool_description
    assert "/harness" not in tool_description
    assert "learn" in tool_description


def test_internal_frozen_and_e2e_command_bindings_survive() -> None:
    # The old command registrations are internal bindings, not user entry
    # points. Frozen provenance proofs drive /memory and /consolidate through a
    # real `pi --print` argv; offline E2E drives /harness through its command
    # handler. Removing any of them breaks those gates. Lock the boundary: the
    # registrations stay, but no documentation table offers them to a user.
    inject = _inject_source()
    assert 'pi.registerCommand("memory"' in inject
    assert 'pi.registerCommand("consolidate"' in inject
    guardrails = (PKG_DIR / "extensions" / "guardrails.ts").read_text(encoding="utf-8")
    assert 'pi.registerCommand("harness"' in guardrails
    readme = (PKG_DIR / "README.md").read_text(encoding="utf-8")
    # Only the command rows themselves; the prose after the table documents
    # the internal frozen bindings on purpose and is not part of the table.
    rows = [
        line
        for line in readme.split("| Command | Purpose |", 1)[1].split("## ", 1)[0].splitlines()
        if line.strip().startswith("|")
    ]
    table = "\n".join(rows)
    assert "/learning" in table
    assert "/memory" not in table and "/consolidate" not in table
    assert "/harness" not in table


def test_worker_loadout_symbols_are_retired() -> None:
    value = run_bun(r'''
      import * as surface from './packages/continual-learning/extensions/tool-surface.ts';
      console.log(JSON.stringify({exports:Object.keys(surface).sort(),toolNames:Object.keys(surface.TOOL_NAMES).sort()}));
    ''')
    for retired in ("workerCliArgs", "WORKER_LOADOUTS", "workerToolNames", "createWorkerToolSurface"):
        assert retired not in value["exports"], (retired, value["exports"])
    assert "harnessCheckCases" not in value["toolNames"], value["toolNames"]
    assert value["toolNames"] == ["harnessPreview", "harnessWrite", "learn", "learningRead"], value["toolNames"]


def test_collector_and_parent_activation_survive_the_retirement() -> None:
    # The dynamic current-source collector still needs its scoped read tool,
    # and the parent still needs to activate learn/harness_write.
    value = run_bun(r'''
      import {TOOL_NAMES,createParentToolSurface} from './packages/continual-learning/extensions/tool-surface.ts';
      const active=['read','write'];
      const surface=createParentToolSurface({getActiveTools:()=>[...active],setActiveTools:names=>{active.length=0;active.push(...names);}});
      surface.refreshAgentMemory(true);const withLearn=[...active];
      surface.beginHarnessAuthoring();const withHarness=[...active];
      surface.resetSession();
      console.log(JSON.stringify({marker:TOOL_NAMES.learningRead,withLearn,withHarness,afterReset:[...active]}));
    ''')
    assert value["marker"] == "learning_read"
    assert "learn" in value["withLearn"]
    assert "harness_write" in value["withHarness"]
    assert "harness_preview" in value["withHarness"]
    assert "harness_write" not in value["afterReset"]
