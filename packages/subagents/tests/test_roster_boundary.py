"""The roster's package boundary.

`@fradser/pi-subagents` owns the child-process roster, so it must be usable by a
consumer that has no team runtime installed. Two things are asserted here that a
type-checker cannot: that the module imports no consumer package, and that the
roster works with no coordinator configured at all.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from subagents_helpers import PACKAGE, SRC, run_node


def test_the_roster_imports_no_consumer_package() -> None:
    """A consumer import would make the execution layer un-installable alone, and
    would close the cycle the three-package split exists to keep open."""
    forbidden = ("@fradser/pi-agent-teams", "pi-agent-teams")
    for module in sorted(SRC.glob("*.ts")):
        text = module.read_text(encoding="utf-8")
        for spec in re.findall(r'from\s+"([^"]+)"', text):
            for name in forbidden:
                assert name not in spec, f"{module.name} imports {spec}"


def test_the_roster_takes_its_assignment_shape_from_the_task_domain() -> None:
    """The allowed direction: the process layer knows the task domain, never the
    reverse. Asserted against the import so a future refactor cannot quietly
    redefine the assignment locally and drift from the board."""
    text = (SRC / "roster.ts").read_text(encoding="utf-8")
    assert 'from "@fradser/pi-tasks"' in text
    assert "WorkAssignment" in text
    assert "BoardTask" not in text


def test_the_roster_works_with_no_coordinator_configured() -> None:
    """The standalone case: no roster hooks published, so nothing to conflict
    against. A registry this survives is what makes a single-session install
    usable rather than a package that only works inside a team."""
    result = run_node(
        f"""
        import {{ registerTeammate, getTeammate, listTeammates, livingTeammates,
                   idleTeammates, updateTeammate, assignTeammate, resetRoster,
                   isValidTeammateName, rosterRevision }} from {json.dumps((PACKAGE / "index.ts").as_uri())};
        resetRoster();
        const before = rosterRevision();
        const member = {{ name: "scout", agent: "reviewer", spawnId: "s1", pid: 1,
          status: "starting", isolation: "none", createdAt: 1, updatedAt: 1 }};
        const added = registerTeammate(member);
        const seen = getTeammate("scout");
        const moved = updateTeammate("scout", {{ status: "working" }});
        const assigned = assignTeammate("scout",
          {{ id: "board:1", kind: "board", resources: [] }}, "t1");
        const duplicate = registerTeammate({{ ...member, spawnId: "s2" }});
        console.log(JSON.stringify({{
          added: added.ok,
          bump: rosterRevision() > before,
          sameObject: seen === member,
          status: moved?.status,
          assignment: assigned?.assignment?.id,
          task: assigned?.currentTaskId,
          counts: [listTeammates().length, livingTeammates().length, idleTeammates().length],
          duplicateRefused: duplicate.ok === false,
          duplicateGuides: duplicate.ok ? null : duplicate.error,
          valid: isValidTeammateName("scout") && !isValidTeammateName("../evil"),
        }}));
        """,
    )
    assert result["added"] is True
    assert result["bump"] is True
    assert result["sameObject"] is True
    assert result["status"] == "working"
    assert result["assignment"] == "board:1"
    assert result["task"] == "t1"
    assert result["counts"] == [1, 1, 0]
    assert result["duplicateRefused"] is True
    assert result["valid"] is True
    # The refusal has to name the way out, or the caller retries the same spawn
    # forever.
    assert "inspect" in result["duplicateGuides"]
    assert "stop" in result["duplicateGuides"]


def test_a_prototype_named_child_cannot_alias_an_inherited_property() -> None:
    result = run_node(
        f"""
        import {{ registerTeammate, getTeammate, listTeammates, resetRoster }} from {json.dumps((PACKAGE / "index.ts").as_uri())};
        resetRoster();
        const base = {{ agent: "reviewer", spawnId: "s", pid: 1, status: "idle", isolation: "none", createdAt: 1, updatedAt: 1 }};
        registerTeammate({{ ...base, name: "constructor" }});
        registerTeammate({{ ...base, name: "hasOwnProperty" }});
        console.log(JSON.stringify({{
          constructorIsOwn: getTeammate("constructor")?.name === "constructor",
          hasOwnPropertyIsOwn: getTeammate("hasOwnProperty")?.name === "hasOwnProperty",
          // The map is created without a prototype, so there is no inherited
          // property to alias at all — stronger than an own entry merely
          // shadowing the prototype, which is all a plain object literal gives.
          noInheritedAtAll: getTeammate("toString") === undefined,
          listHasNoGarbage: listTeammates().length === 2,
        }}));
        """,
    )
    assert result["constructorIsOwn"] is True
    assert result["hasOwnPropertyIsOwn"] is True
    assert result["noInheritedAtAll"] is True
    assert result["listHasNoGarbage"] is True
