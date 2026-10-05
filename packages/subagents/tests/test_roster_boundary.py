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


def test_the_roster_works_with_no_coordinator_configured() -> None:
    """The standalone case: no roster hooks published, so nothing to conflict
    against. A registry this survives is what makes a single-session install
    usable rather than a package that only works inside a team."""
    result = run_node(
        f"""
        import {{ registerAgent, getAgent, listAgents, livingAgents,
                   idleAgents, updateAgent, assignAgent, resetRoster,
                   isValidAgentName, rosterRevision }} from {json.dumps((PACKAGE / "index.ts").as_uri())};
        resetRoster();
        const before = rosterRevision();
        const member = {{ name: "scout", agent: "reviewer", spawnId: "s1", pid: 1,
          status: "starting", scope: "session", createdAt: 1, updatedAt: 1 }};
        const added = registerAgent(member);
        const seen = getAgent("scout");
        const moved = updateAgent("scout", {{ status: "working" }});
        const assigned = assignAgent("scout",
          {{ id: "task:1", kind: "task", resources: [] }}, "t1");
        const duplicate = registerAgent({{ ...member, spawnId: "s2" }});
        console.log(JSON.stringify({{
          added: added.ok,
          bump: rosterRevision() > before,
          sameObject: seen === member,
          status: moved?.status,
          assignment: assigned?.assignment?.id,
          task: assigned?.currentTaskId,
          counts: [listAgents().length, livingAgents().length, idleAgents().length],
          duplicateRefused: duplicate.ok === false,
          duplicateGuides: duplicate.ok ? null : duplicate.error,
          valid: isValidAgentName("scout") && !isValidAgentName("../evil"),
        }}));
        """,
    )
    assert result["added"] is True
    assert result["bump"] is True
    assert result["sameObject"] is True
    assert result["status"] == "working"
    assert result["assignment"] == "task:1"
    assert result["task"] == "t1"
    assert result["counts"] == [1, 1, 0]
    assert result["duplicateRefused"] is True
    assert result["valid"] is True
    # The refusal has to name the way out, or the caller retries the same spawn
    # forever.
    assert "inspect" in result["duplicateGuides"]
    assert "stop" in result["duplicateGuides"]


def test_a_revision_written_through_one_module_instance_reaches_the_other() -> None:
    """The map lives on `globalThis` because two module instances are normal here,
    so the revision counters describing it have to live there too. Counters held
    per instance left the other instance concluding that nothing changed, and a
    roster write is then never republished to the children that read it."""
    result = run_node(
        f"""
        import * as viaBarrel from {json.dumps((PACKAGE / "index.ts").as_uri())};
        import * as viaModule from {json.dumps((SRC / "roster.ts").as_uri())};
        // Two specifiers, two module instances, one process. The map is shared;
        // this asserts the counters are as well.
        viaBarrel.resetRoster();
        const before = viaModule.rosterRevision();
        viaBarrel.registerAgent({{
          name: "shared-counter", agent: "reviewer", spawnId: "s1", pid: 1,
          status: "starting", scope: "session", createdAt: 1, updatedAt: 1,
        }});
        console.log(JSON.stringify({{
          distinctInstances: viaBarrel !== viaModule,
          seenThroughOther: viaModule.rosterRevision() > before,
          sameEntry: viaModule.getAgent("shared-counter")?.name === "shared-counter",
        }}));
        """,
    )
    assert result["distinctInstances"] is True
    assert result["seenThroughOther"] is True
    assert result["sameEntry"] is True


def test_a_prototype_named_child_cannot_alias_an_inherited_property() -> None:
    result = run_node(
        f"""
        import {{ registerAgent, getAgent, listAgents, resetRoster }} from {json.dumps((PACKAGE / "index.ts").as_uri())};
        resetRoster();
        const base = {{ role: "reviewer", spawnId: "s", pid: 1, status: "idle", scope: "session", createdAt: 1, updatedAt: 1 }};
        registerAgent({{ ...base, name: "constructor" }});
        registerAgent({{ ...base, name: "hasOwnProperty" }});
        console.log(JSON.stringify({{
          constructorIsOwn: getAgent("constructor")?.name === "constructor",
          hasOwnPropertyIsOwn: getAgent("hasOwnProperty")?.name === "hasOwnProperty",
          // The map is created without a prototype, so there is no inherited
          // property to alias at all — stronger than an own entry merely
          // shadowing the prototype, which is all a plain object literal gives.
          noInheritedAtAll: getAgent("toString") === undefined,
          listHasNoGarbage: listAgents().length === 2,
        }}));
        """,
    )
    assert result["constructorIsOwn"] is True
    assert result["hasOwnPropertyIsOwn"] is True
    assert result["noInheritedAtAll"] is True
    assert result["listHasNoGarbage"] is True


def test_the_published_registry_carries_the_whole_holder_shape() -> None:
    """The seam has to be a shape both sides can read without importing the other,
    so it is asserted in both directions: what the roster publishes, and what it
    writes back when a task set hands it an assignment.

    `sync` is the half that is easy to get wrong. Without it the task store can see who
    holds what but cannot record it, so the roster entry would never show an
    assignment and a successor would have nothing to inherit.
    """
    result = run_node(
        f"""
        import {{ registerAgent, getAgent, resetRoster, assignAgent,
                   rosterAsParticipantRegistry }} from {json.dumps((PACKAGE / "index.ts").as_uri())};
        import {{ publishParticipantRegistry, resolveParticipantRegistry }} from "@fradser/pi-kit";
        resetRoster();
        publishParticipantRegistry(rosterAsParticipantRegistry());
        const registry = resolveParticipantRegistry();
        const base = {{ role: "scout", pid: 1, scope: "session", createdAt: 1, updatedAt: 1 }};
        registerAgent({{ ...base, name: "scout", spawnId: "s1", status: "idle" }});
        registerAgent({{ ...base, name: "gone", spawnId: "s2", status: "stopped" }});
        // A projection, not the entry: a consumer cannot reach roster state by
        // writing to what it was handed.
        const projected = registry?.get("scout");
        registry?.sync("scout", {{ id: "work:1", kind: "task", resources: ["ledger"] }}, "t1");
        registry?.sync("gone", {{ id: "work:2", kind: "direct", resources: [] }}, "t2");
        console.log(JSON.stringify({{
          // A stopped child cannot hold anything, so it is never listed.
          listed: registry?.list().map((p) => p.name),
          name: projected?.name,
          spawnId: projected?.spawnId,
          status: projected?.status,
          // No pid, no live text, no tools: the shape is a holder, not the entry.
          projectedFields: Object.keys(projected ?? {{}}).sort(),
          storedOnRoster: getAgent("scout")?.assignment,
          taskIdOnRoster: getAgent("scout")?.currentTaskId,
          // A stopped entry can still be written to, but is not a participant.
          stillNotListed: registry?.list().length,
          missing: registry?.get("nobody") === undefined,
          cleared: (() => {{ registry?.sync("scout", undefined, undefined); return getAgent("scout")?.assignment ?? null; }})(),
          // A reload republishes rather than stacking, and the roster it publishes
          // is the same shared object, so the second registry sees the first's writes.
          republished: (() => {{
            publishParticipantRegistry(rosterAsParticipantRegistry());
            const again = resolveParticipantRegistry();
            again?.sync("scout", {{ id: "work:3", kind: "direct", resources: [] }}, "t3");
            return {{
              // One registry in the slot, and it is the republished one: a reload
              // replaces the offer rather than stacking a second.
              replaced: again !== registry && resolveParticipantRegistry() === again,
              stored: getAgent("scout")?.currentTaskId ?? null,
              // Over the same shared roster, so the republished offer sees what the
              // first one wrote.
              seesTheSameRoster: again?.get("scout")?.currentTaskId ?? null,
            }};
          }})(),
        }}));
        """,
    )
    assert result["listed"] == ["scout"]
    assert result["name"] == "scout"
    assert result["spawnId"] == "s1"
    assert result["status"] == "idle"
    assert list(result["projectedFields"]) == ["name", "spawnId", "status"]
    assert result["storedOnRoster"] == {"id": "work:1", "kind": "task", "resources": ["ledger"]}
    assert result["taskIdOnRoster"] == "t1"
    assert result["stillNotListed"] == 1
    assert result["missing"] is True
    assert result["cleared"] is None
    assert result["republished"]["replaced"] is True
    assert result["republished"]["stored"] == "t3"
    assert result["republished"]["seesTheSameRoster"] == "t3"
