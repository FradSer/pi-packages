"""The public task surface: derived ownership, the closed transition set, and
the recovery hold.

Contract: features/tool-surface.feature

Everything imports through the package barrel, so a symbol missing from
`index.ts` fails rather than passing through a deep relative path. The board is
seeded with a two-task board and a roster of two living participants, so a
scenario can exercise a real conflict rather than asserting against a stub.
"""

from __future__ import annotations

import json
from pathlib import Path

from task_helpers import PACKAGE, run_node, source

TASK = (PACKAGE / "index.ts").as_uri()

# A board with one blocked task and one freely claimable one, plus two living
# participants. `sync` is a no-op because these scenarios are about the board's
# own refusals, not about roster bookkeeping.
SETUP = f"""
const ROSTER = {{
  alpha: {{ name: "alpha", spawnId: "s1", status: "idle" }},
  beta: {{ name: "beta", spawnId: "s2", status: "idle" }},
}};
const HELD = new Map();
task.configureBoardStore({{
  get: (name) => ROSTER[name],
  conflicting: (resources, except) => {{
    for (const [name, held] of HELD) {{
      if (name === except) continue;
      if (task.resourcesConflict(resources, held)) return {{ ...ROSTER[name] }};
    }}
    return undefined;
  }},
  sync: (name, assignment, taskId) => {{
    if (assignment) HELD.set(name, assignment.resources); else HELD.delete(name);
  }},
  changed: () => {{}},
}});
task.createTask({{ id: "t1", subject: "blocked" }});
task.createTask({{ id: "t2", subject: "free" }});
"""


def run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(
        f"""\
        import * as task from "{TASK}";
        {SETUP}
        {script}
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )


# ── Ownership is derived from action ──


def test_taking_a_task_is_the_act_of_moving_it_into_progress(tmp_path: Path) -> None:
    result = run(
        """
        const taken = task.takeTask("t1", "alpha");
        console.log(JSON.stringify({
          ok: taken.ok,
          status: taken.task?.status ?? null,
          holder: taken.task?.claimedBy ?? null,
          noAssigneeField: taken.task ? !("assignee" in taken.task) : null,
        }));
        """,
        tmp_path,
    )
    assert result["ok"] is True
    assert result["status"] == "in_progress"
    assert result["holder"] == "alpha"
    assert result["noAssigneeField"] is True


def test_two_participants_racing_for_one_task_produce_exactly_one_holder(tmp_path: Path) -> None:
    result = run(
        """
        const first = task.takeTask("t1", "alpha");
        const second = task.takeTask("t1", "beta");
        console.log(JSON.stringify({
          firstOk: first.ok,
          secondOk: second.ok,
          refusal: second.ok ? null : second.refusal,
          namesHolder: second.ok ? null : second.reason.includes("alpha"),
        }));
        """,
        tmp_path,
    )
    assert result["firstOk"] is True
    assert result["secondOk"] is False
    assert result["refusal"] == "held-by-other"
    assert result["namesHolder"] is True


def test_no_action_accepts_a_participant_name_besides_the_holder() -> None:
    """The take signature is the only place a participant is named, and it names
    exactly one. This is asserted against the source because the property is
    about what is expressible, not about any one call."""
    store = source("store.ts")
    start = store.index("export function takeTask")
    signature = store[start:store.index("export function updateTask")]
    assert "assignee" not in signature.lower()
    # Every public task-surface function takes the caller as a plain argument;
    # none of them accepts a second participant.
    for name in ("takeTask", "updateTask", "completeTaskWithOutcome", "reopenTask"):
        at = store.index(f"export function {name}")
        opening = store.index("(", at)
        closing = store.index("\n", store.index("):", opening))
        params = store[opening:closing].lower()
        assert "assignee" not in params, name
        assert "owner" not in params, name


# ── Failure is explicit, and never prose ──


def test_failure_is_explicit_and_retains_its_evidence(tmp_path: Path) -> None:
    result = run(
        """
        task.takeTask("t1", "alpha");
        const failed = task.completeTaskWithOutcome("t1", "alpha", "failed", "cannot reach the private registry");
        const record = task.getTask("t1");
        console.log(JSON.stringify({
          ok: failed.ok,
          status: record?.status,
          recoveryRequired: record?.recoveryRequired ?? null,
          evidence: record?.result ?? null,
        }));
        """,
        tmp_path,
    )
    assert result["ok"] is True
    assert result["status"] == "pending"
    assert result["recoveryRequired"] is True
    assert result["evidence"] == "cannot reach the private registry"


def test_the_recovery_hold_requires_a_stated_reason(tmp_path: Path) -> None:
    result = run(
        """
        task.takeTask("t1", "alpha");
        task.completeTaskWithOutcome("t1", "alpha", "failed", "blocked");
        const silent = task.takeTask("t1", "beta");
        const spoken = task.takeTask("t1", "beta", { reason: "mirrored the registry locally" });
        console.log(JSON.stringify({
          silentOk: silent.ok,
          silentRefusal: silent.ok ? null : silent.refusal,
          spokenOk: spoken.ok,
          holdCleared: spoken.task ? spoken.task.recoveryRequired === undefined : null,
          note: spoken.task?.recoveryNote ?? null,
        }));
        """,
        tmp_path,
    )
    assert result["silentOk"] is False
    assert result["silentRefusal"] == "recovery-hold-needs-reason"
    assert result["spokenOk"] is True
    assert result["holdCleared"] is True
    assert result["note"] == "mirrored the registry locally"


# ── Completion authority ──


def test_a_task_with_a_live_holder_cannot_be_closed_by_someone_else(tmp_path: Path) -> None:
    result = run(
        """
        task.takeTask("t1", "alpha");
        const byOther = task.completeTaskWithOutcome("t1", "beta", "success", "pretending");
        const byHolder = task.completeTaskWithOutcome("t1", "alpha", "success", "real evidence");
        console.log(JSON.stringify({
          otherOk: byOther.ok,
          otherReason: byOther.ok ? null : byOther.reason,
          holderOk: byHolder.ok,
          status: byHolder.task?.status ?? null,
        }));
        """,
        tmp_path,
    )
    assert result["otherOk"] is False
    assert "alpha" in result["otherReason"]
    assert result["holderOk"] is True
    assert result["status"] == "completed"


def test_an_unheld_task_accepts_fallback_acceptance(tmp_path: Path) -> None:
    """The path that exists so a dead agent's task is not stranded forever."""
    result = run(
        """
        const closed = task.completeTaskWithOutcome("t2", "main", "success", "verified by reading the output");
        console.log(JSON.stringify({ ok: closed.ok, status: closed.task?.status ?? null }));
        """,
        tmp_path,
    )
    assert result["ok"] is True
    assert result["status"] == "completed"


def test_reopening_is_refused_while_a_dependent_is_in_progress(tmp_path: Path) -> None:
    result = run(
        """
        task.createTask({ subject: "dependent", dependsOn: ["t1"] });
        task.completeTaskWithOutcome("t1", "alpha", "success");
        task.takeTask("dependent", "beta");
        const blocked = task.reopenTask("t1");
        console.log(JSON.stringify({
          ok: blocked.ok,
          namesDependent: blocked.ok ? null : blocked.reason.includes("dependent"),
        }));
        """,
        tmp_path,
    )
    assert result["ok"] is False
    assert result["namesDependent"] is True


# ── The transition set is closed ──


def test_update_accepts_no_status() -> None:
    """A generic status field would let a caller bypass the preconditions that
    `takeTask` and `reopenTask` enforce, so neither the update payload nor its
    signature may mention one."""
    store = source("store.ts")
    # Slice the declaration itself, not the doc comment above it, which
    # deliberately contains the word while explaining why it is absent.
    start = store.index("export interface TaskUpdate")
    interface = store[start:store.index("}", start)]
    assert "status" not in interface.lower()
    at = store.index("export function updateTask")
    params = store[store.index("(", at):store.index("):", at)].lower()
    assert "status" not in params


def test_no_verb_releases_work_explicitly(tmp_path: Path) -> None:
    """Release is automatic on completion, process exit, and stop, and nothing in
    the surface can free a task on demand.

    The three runtime transitions that *do* give a lease back are named for what
    happened rather than for the act: a holder reporting failure goes through
    `completeTaskWithOutcome`, the runtime undoing its own half-finished start
    through `revertInFlightAttempt`, and a holder freeing a lease on superseded
    work through `acknowledgeSupersession`. None of them is a general release, and
    two of the three are unreachable from the tool surface at all.
    """
    result = run(
        """
        const names = Object.keys(task);
        const explicit = names.filter((name) => /^(release|abandon|reclaim|assign|claim|complete)Task$/i.test(name));
        const surface = [
          "createTask", "listTasks", "updateTask", "takeTask",
          "completeTaskWithOutcome", "reopenTask", "releaseTasksOf",
          "revertInFlightAttempt", "acknowledgeSupersession",
        ];
        console.log(JSON.stringify({
          legacyRemainder: explicit,
          automaticRelease: names.includes("releaseTasksOf"),
          surfaceComplete: surface.every((name) => names.includes(name)),
          // The two runtime-only transitions must exist, or the paths that need
          // them have nowhere to go.
          revert: typeof task.revertInFlightAttempt === "function",
          acknowledge: typeof task.acknowledgeSupersession === "function",
        }));
        """,
        tmp_path,
    )
    assert result["legacyRemainder"] == []
    assert result["automaticRelease"] is True
    assert result["surfaceComplete"] is True
    assert result["revert"] is True
    assert result["acknowledge"] is True


def test_the_store_has_no_assignee_field_on_its_data_model() -> None:
    types = source("types.ts")
    body = types[types.index("export interface BoardTask"):]
    assert "assignee" not in body.lower()
    # `claimedBy` stays, because it is written by the runtime from the caller's
    # identity; what must not exist is a field a caller could set to a name.
    assert "claimedBy?: string" in types
