"""The public task surface: derived ownership, the closed transition set, and
the recovery hold.

Contracts: features/task-tool.feature and features/completion-checks.feature

Everything imports through the package barrel, so a symbol missing from
`index.ts` fails rather than passing through a deep relative path. The task store is
seeded with a two-task storage and a roster of two living participants, so a
scenario can exercise a real conflict rather than asserting against a stub.
"""

from __future__ import annotations

import json
from pathlib import Path

from task_helpers import PACKAGE, run_node, source

TASK = (PACKAGE / "index.ts").as_uri()

# Two independent pending tasks and two current participants. The assignment
# map supplies real resource conflicts without loading an execution package.
SETUP = f"""
const ROSTER = {{
  alpha: {{ name: "alpha", spawnId: "s1", status: "idle" }},
  beta: {{ name: "beta", spawnId: "s2", status: "idle" }},
}};
const HELD = new Map();
task.configureTaskStore({{
  get: (name) => ROSTER[name],
  current: (name, incarnation) => {{
    const entry = ROSTER[name];
    if (!entry) return false;
    return incarnation === undefined || entry.spawnId === incarnation;
  }},
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
    assert result["status"] == "recovery_hold"
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
          holdCleared: spoken.task ? spoken.task.status !== "recovery_hold" : null,
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


def test_an_unheld_task_accepts_fallback_acceptance_when_a_holder_died(tmp_path: Path) -> None:
    """The path that exists so a dead holder's task is not stranded forever.

    The setup matters, and the old one did not build it: it completed a task that
    had *never been taken*, which is not a dead holder. A dead holder is on the
    record — the failure it reported is what put the task back in pending with a
    recovery hold and nobody holding it. That state is what makes fallback
    acceptance sound, and it is what this now sets up.
    """
    result = run(
        """
        task.takeTask("t1", "alpha");
        task.completeTaskWithOutcome("t1", "alpha", "failed", "alpha stopped before delivering");
        // Values, not the record: `getTask` hands back the live object, so a
        // snapshot read after the next call reports the *later* state.
        const after = task.getTask("t1");
        const afterFailure = { status: after.status, held: after.claimedBy ?? null, hold: after.status === "recovery_hold" };
        const closed = task.completeTaskWithOutcome("t1", "main", "success", "verified by reading the output");
        console.log(JSON.stringify({
          afterFailure,
          ok: closed.ok,
          status: closed.ok ? closed.task.status : null,
          evidence: task.getTask("t1").result,
        }));
        """,
        tmp_path,
    )
    assert result["afterFailure"] == {"status": "recovery_hold", "held": None, "hold": True}, (
        "a reported failure is what makes an unheld task accept-able again"
    )
    assert result["ok"] is True
    assert result["status"] == "completed"


def test_reopening_proceeds_while_a_dependent_is_being_worked_on(tmp_path: Path) -> None:
    """This used to assert the opposite, and the reversal is the point.

    Reopen was refused while a dependent was held and accepted a moment later, so
    the same reopen had two answers depending on who was working. It is the only
    way back from a completed task, so it cannot be conditional: the dependent's
    attempt is invalidated instead, which is the treatment a completed conclusion
    has always got.
    """
    result = run(
        """
        task.createTask({ subject: "dependent", dependsOn: ["t1"] });
        task.takeTask("t1", "alpha");
        task.completeTaskWithOutcome("t1", "alpha", "success", "done", { checks: task.ALL_COMPLETION_CHECKS });
        task.takeTask("dependent", "beta");
        const reopened = task.reopenTask("t1");
        const dependent = task.getTask("dependent");
        console.log(JSON.stringify({
          ok: reopened.ok,
          withdrawn: reopened.ok ? reopened.invalidated.map((entry) => entry.id) : null,
          dependentStatus: dependent.status,
          namesTheTask: dependent.invalidatedBy ?? null,
        }));
        """,
        tmp_path,
    )
    assert result["ok"] is True
    assert result["withdrawn"] == ["dependent"]
    assert result["dependentStatus"] == "recovery_hold"
    assert result["namesTheTask"] == "t1"


# ── The transition set is closed ──


def test_update_accepts_no_status() -> None:
    """A generic status field would let a caller bypass the preconditions that
    `takeTask` and `reopenTask` enforce, so neither the update payload nor its
    signature may mention one."""
    store = source("store.ts")
    # Slice the declaration itself, not the doc comment above it, which
    # deliberately contains the word while explaining why it is absent.
    start = store.index("export interface update_task")
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
          "completeTaskWithOutcome", "reopenTask", "failTasksHeldBy",
          "revertUndeliveredTake", "acknowledgeSupersession",
        ];
        console.log(JSON.stringify({
          legacyRemainder: explicit,
          automaticRelease: names.includes("failTasksHeldBy"),
          surfaceComplete: surface.every((name) => names.includes(name)),
          // The two runtime-only transitions must exist, or the paths that need
          // them have nowhere to go.
          revert: typeof task.revertUndeliveredTake === "function",
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
    body = types[types.index("export interface Task"):]
    assert "assignee" not in body.lower()
    # `claimedBy` stays, because it is written by the runtime from the caller's
    # identity; what must not exist is a field a caller could set to a name.
    assert "claimedBy?: string" in types


# ── A completion is checked before it is recorded ──
#
# The scenario this exists for: a model splits a large task into n tasks that may
# depend on each other, takes them in parallel or in series, then marks them
# complete. The task store is the only thing that sees the whole sequence.


def test_a_completion_whose_dependency_is_unfinished_is_refused(tmp_path: Path) -> None:
    """The dependency graph was enforced on the take path and not at all on the
    completion path, so a model could mark a dependent done while its dependency
    was still pending. The tasks then held a completed task depending on an
    unfinished one, which is the state the graph exists to make impossible."""
    result = run(
        """
        task.createTask({ id: "t2", subject: "blocker" });
        task.createTask({ id: "dependent", subject: "depends on the blocker", dependsOn: ["t2"] });
        const all = task.ALL_COMPLETION_CHECKS;
        // Isolate the dependency condition from the unrelated never-taken
        // condition. An earlier build could hold this task prematurely.
        task.getTask("dependent").status = "in_progress";
        task.getTask("dependent").claimedBy = "main";
        const closed = task.completeTaskWithOutcome("dependent", "main", "success", "done", { checks: all });
        const record = task.getTask("dependent");
        console.log(JSON.stringify({
          refused: closed.ok === false,
          reason: closed.ok ? null : closed.reason,
          status: record.status,
          dependency: task.getTask("t2").status,
        }));
        """,
        tmp_path,
    )
    assert result["refused"] is True
    assert "t2" in str(result["reason"]), "the refusal names the unfinished dependency"
    assert result["status"] == "in_progress", "a refused completion leaves the attempt unchanged"
    assert result["dependency"] == "pending"


def test_a_success_without_evidence_is_refused_when_the_check_is_asked_for(tmp_path: Path) -> None:
    result = run(
        """
        // One task per call: the first completion ends the task, so a second
        // call on it would be refused as already completed rather than for the
        // rule under test.
        for (const id of ["bare", "checked", "evidenced"]) {
          task.createTask({ id, subject: id });
          task.takeTask(id, "alpha");
        }
        const bare = task.completeTaskWithOutcome("bare", "alpha", "success");
        const checked = task.completeTaskWithOutcome("checked", "alpha", "success", undefined, {
          checks: task.ALL_COMPLETION_CHECKS,
        });
        const withEvidence = task.completeTaskWithOutcome("evidenced", "alpha", "success", "ran the suite, 43 pass", {
          checks: task.ALL_COMPLETION_CHECKS,
        });
        console.log(JSON.stringify({
          bareAccepted: bare.ok,
          bareStatus: task.getTask("t1").status,
          checkedRefused: checked.ok === false,
          reason: checked.ok ? null : checked.reason,
          withEvidenceAccepted: withEvidence.ok,
        }));
        """,
        tmp_path,
    )
    assert result["bareAccepted"] is True, "the checks are opt-in, so an unchecked caller is unaffected"
    assert result["checkedRefused"] is True
    assert "result" in str(result["reason"]), "the refusal names what would satisfy it"
    assert result["withEvidenceAccepted"] is True


def test_a_task_nobody_worked_on_cannot_be_accepted(tmp_path: Path) -> None:
    """Fallback acceptance exists for a holder that *died*, which leaves the
    attempt on the record as a recovery hold. A task that was never taken has no
    attempt at all, so accepting it is a bare assertion."""
    result = run(
        """
        const never = task.completeTaskWithOutcome("t2", "main", "success", "looks fine to me", {
          checks: task.ALL_COMPLETION_CHECKS,
        });
        task.takeTask("t1", "alpha");
        task.completeTaskWithOutcome("t1", "alpha", "failed", "alpha stopped");
        const dead = task.completeTaskWithOutcome("t1", "main", "success", "checked the output myself", {
          checks: task.ALL_COMPLETION_CHECKS,
        });
        console.log(JSON.stringify({
          neverRefused: never.ok === false,
          neverReason: never.ok ? null : never.reason,
          neverStatus: task.getTask("t2").status,
          deadAccepted: dead.ok,
          deadStatus: dead.ok ? dead.task.status : null,
        }));
        """,
        tmp_path,
    )
    assert result["neverRefused"] is True
    assert "never" in str(result["neverReason"]).lower() or "taken" in str(result["neverReason"]).lower()
    assert result["neverStatus"] == "pending"
    assert result["deadAccepted"] is True, "a dead holder's work is still accept-able"
    assert result["deadStatus"] == "completed"


def test_a_declared_gate_must_be_answered_with_a_verdict(tmp_path: Path) -> None:
    """The task store cannot run a gate — a gate is a prompt, and a task set that
    evaluates prompts runs agents. It can demand the answer and record it, so the
    omission is impossible even though the answer is taken on trust."""
    result = run(
        """
        task.createTask({ id: "gated", subject: "ship it", verify: "a fresh reviewer confirms the tasks survives a restart" });
        task.takeTask("gated", "alpha");
        const silent = task.completeTaskWithOutcome("gated", "alpha", "success", "done", {
          checks: task.ALL_COMPLETION_CHECKS, verdict: undefined,
        });
        const answered = task.completeTaskWithOutcome("gated", "alpha", "success", "done", {
          checks: task.ALL_COMPLETION_CHECKS, verdict: "pass",
        });
        const record = task.getTask("gated");
        console.log(JSON.stringify({
          silentRefused: silent.ok === false,
          silentReason: silent.ok ? null : silent.reason,
          answeredAccepted: answered.ok,
          recordedVerdict: record.completionVerdict ?? null,
          recordedBy: record.completionGate ?? null,
        }));
        """,
        tmp_path,
    )
    assert result["silentRefused"] is True
    assert "gate" in str(result["silentReason"]).lower() or "verdict" in str(result["silentReason"]).lower()
    assert result["answeredAccepted"] is True
    assert result["recordedVerdict"] == "pass", "the answer is on the record, so a later reader can see what kind of done this is"


def test_every_check_is_asked_for_on_its_own(tmp_path: Path) -> None:
    """One check at a time, so a caller that wants one rule is not held to the
    other three and cannot tell which one refused it."""
    result = run(
        """
        task.createTask({ id: "solo", subject: "one rule only" });
        task.createTask({ id: "blocked", subject: "blocked" });
        task.createTask({ id: "t2", subject: "blocker" });
        task.createTask({ id: "waits", subject: "depends on it", dependsOn: ["t2"] });
        const evidenceOnly = task.completeTaskWithOutcome("solo", "main", "success", undefined, {
          checks: { requireEvidence: true },
        });
        const depsOnly = task.completeTaskWithOutcome("waits", "main", "success", "has evidence", {
          checks: { requireDependenciesCompleted: true },
        });
        const holdOnly = task.completeTaskWithOutcome("blocked", "main", "success", "has evidence", {
          checks: { requirePriorHold: true },
        });
        console.log(JSON.stringify({
          evidenceRefused: evidenceOnly.ok === false,
          evidenceReason: evidenceOnly.ok ? null : evidenceOnly.reason,
          depsRefused: depsOnly.ok === false,
          depsReason: depsOnly.ok ? null : depsOnly.reason,
          holdRefused: holdOnly.ok === false,
          holdReason: holdOnly.ok ? null : holdOnly.reason,
        }));
        """,
        tmp_path,
    )
    assert result["evidenceRefused"] is True
    assert "result" in str(result["evidenceReason"])
    assert result["depsRefused"] is True
    assert "t2" in str(result["depsReason"])
    assert result["holdRefused"] is True, "t1 was never taken either, so this rule refuses on its own account"
    assert "taken" in str(result["holdReason"]).lower() or "never" in str(result["holdReason"]).lower()


# ── A withdrawn premise takes its conclusions with it ──


def test_reopening_pulls_back_what_was_concluded_on_it(tmp_path: Path) -> None:
    """The other door into the same invariant. Completion is checked, so a task
    cannot be completed on an unfinished premise — but reopening the premise left
    the conclusion standing, so the tasks could still hold a completed task
    depending on a pending one."""
    result = run(
        """
        task.createTask({ id: "base", subject: "the premise" });
        task.createTask({ id: "built", subject: "concluded on it", dependsOn: ["base"] });
        task.takeTask("base", "alpha");
        task.completeTaskWithOutcome("base", "alpha", "success", "wrote the spec", { checks: task.ALL_COMPLETION_CHECKS });
        task.takeTask("built", "beta");
        task.completeTaskWithOutcome("built", "beta", "success", "wrote the code", { checks: task.ALL_COMPLETION_CHECKS });
        const completedBefore = task.getTask("built").status;
        const reopened = task.reopenTask("base");
        const after = task.getTask("built");
        console.log(JSON.stringify({
          completedBefore,
          premiseAfter: task.getTask("base").status,
          withdrawnIds: reopened.ok ? reopened.invalidated.map((entry) => entry.id) : null,
          dependentAfter: after.status,
          held: after.status === "recovery_hold",
          namesTheTask: after.invalidatedBy ?? null,
          evidenceKept: after.result ?? null,
          invariant: !(after.status === "completed" && task.getTask("base").status !== "completed"),
        }));
        """,
        tmp_path,
    )
    assert result["completedBefore"] == "completed"
    assert result["premiseAfter"] == "pending"
    assert result["withdrawnIds"] == ["built"], "the conclusion is pulled back, and named"
    assert result["dependentAfter"] == "recovery_hold", (
        "a completed task must never depend on an unfinished one, whichever door is used"
    )
    assert result["held"] is True, "it is held rather than offered straight back out"
    assert result["namesTheTask"] == "base"
    assert result["evidenceKept"] == "wrote the code", "the evidence is what the next attempt has to answer"
    assert result["invariant"] is True


def test_a_reopened_premise_withdraws_its_recorded_gate_verdict(tmp_path: Path) -> None:
    """A withdrawn conclusion must not keep a `pass` standing.

    The previous version of this test took the premise and the dependent in one
    loop, so the dependent's take was refused for an unmet dependency, its
    completion was refused with it, and it never held a verdict — the assertion
    that the verdict was gone passed because there had never been one.
    """
    result = run(
        """
        task.createTask({ id: "gated-base", subject: "gated premise", verify: "a fresh reviewer confirms X" });
        const gate = "Confirm the implementation still satisfies X";
        task.createTask({
          id: "built-on-gated", subject: "concluded on it", dependsOn: ["gated-base"], verify: gate,
        });
        const premiseTake = task.takeTask("gated-base", "alpha");
        const premiseCompletion = task.completeTaskWithOutcome("gated-base", "alpha", "success", "did X", {
          checks: task.ALL_COMPLETION_CHECKS, verdict: "pass",
        });
        // Only now is the dependent takeable, so only now can it hold a verdict.
        const took = task.takeTask("built-on-gated", "alpha");
        const completed = task.completeTaskWithOutcome("built-on-gated", "alpha", "success", "used X", {
          checks: task.ALL_COMPLETION_CHECKS, verdict: "pass",
        });
        const verdictBefore = task.getTask("built-on-gated").completionVerdict ?? null;
        const gateBefore = task.getTask("built-on-gated").completionGate ?? null;

        const reopened = task.reopenTask("gated-base");
        const after = task.getTask("built-on-gated");
        console.log(JSON.stringify({
          premiseTakeOk: premiseTake.ok,
          premiseCompletionOk: premiseCompletion.ok,
          tookOk: took.ok,
          completedOk: completed.ok,
          verdictBefore,
          gateBefore,
          withdrawn: reopened.ok ? reopened.invalidated.map((entry) => entry.id) : null,
          dependentVerdict: after.completionVerdict ?? null,
          dependentGate: after.completionGate ?? null,
          dependentStatus: after.status,
          ownVerdictKept: task.getTask("gated-base").completionVerdict ?? null,
        }));
        """,
        tmp_path,
    )
    assert result["premiseTakeOk"] is True
    assert result["premiseCompletionOk"] is True
    assert result["tookOk"] is True, "the setup must reach the state under test"
    assert result["completedOk"] is True
    assert result["verdictBefore"] == "pass", "the verdict exists before reopening"
    assert result["gateBefore"] == "Confirm the implementation still satisfies X"
    assert result["withdrawn"] == ["built-on-gated"], "and the reopening really reached it"
    assert result["dependentVerdict"] is None, (
        "a pass on work whose premise is gone is the one reading this task set cannot afford"
    )
    assert result["dependentGate"] is None
    assert result["dependentStatus"] == "recovery_hold"
    assert result["ownVerdictKept"] == "pass", (
        "a task keeps its own verdict when it is the one reopened; it is pending again, "
        "and the answer described an attempt that may yet stand"
    )


def test_a_reopen_cascade_reaches_every_conclusion(tmp_path: Path) -> None:
    result = run(
        """
        task.createTask({ id: "c1", subject: "one" });
        task.createTask({ id: "c2", subject: "two", dependsOn: ["c1"] });
        task.createTask({ id: "c3", subject: "three", dependsOn: ["c2"] });
        for (const id of ["c1", "c2", "c3"]) {
          task.takeTask(id, "alpha");
          task.completeTaskWithOutcome(id, "alpha", "success", `did ${id}`, { checks: task.ALL_COMPLETION_CHECKS });
        }
        const reopened = task.reopenTask("c1");
        console.log(JSON.stringify({
          withdrawn: reopened.ok ? reopened.invalidated.map((entry) => entry.id) : null,
          statuses: ["c1", "c2", "c3"].map((id) => task.getTask(id).status),
        }));
        """,
        tmp_path,
    )
    assert result["withdrawn"] == ["c2", "c3"], "the cascade reaches the far end, not just the nearest"
    assert result["statuses"] == ["pending", "recovery_hold", "recovery_hold"]


def test_a_dependent_being_worked_on_is_invalidated_rather_than_blocking(tmp_path: Path) -> None:
    """Reopen is the only way back, so it cannot depend on who happens to be
    working: the same reopen was refused while a dependent was held and accepted a
    second later. It now always goes ahead, and the held dependent's attempt is
    invalidated with its lease released — the same treatment a completed
    conclusion gets, because both stood on a premise that just moved."""
    result = run(
        """
        const released = [];
        task.configureTaskStore({
          get: (name) => ({ name, spawnId: name === "alpha" ? "s1" : "s2", status: "idle" }),
          current: () => true,
          conflicting: () => undefined,
          sync: (name, assignment) => { if (!assignment) released.push(name); },
          changed: () => {},
        });
        task.createTask({ id: "h1", subject: "premise" });
        task.createTask({ id: "h2", subject: "being built on it", dependsOn: ["h1"], resources: ["firmware"] });
        task.takeTask("h1", "alpha");
        task.completeTaskWithOutcome("h1", "alpha", "success", "done", { checks: task.ALL_COMPLETION_CHECKS });
        task.takeTask("h2", "beta");
        // Counted from here: a completion releases its own holder, and this is
        // about the lease the reopen gives back.
        released.length = 0;
        const reopened = task.reopenTask("h1");
        const dependent = task.getTask("h2");
        console.log(JSON.stringify({
          reopened: reopened.ok,
          withdrawn: reopened.ok ? reopened.invalidated.map((entry) => entry.id) : null,
          dependentStatus: dependent.status,
          heldBy: dependent.claimedBy ?? null,
          held: dependent.status === "recovery_hold",
          namesTheTask: dependent.invalidatedBy ?? null,
          note: dependent.recoveryNote ?? null,
          leaseReleased: released,
          invariant: !(dependent.status === "completed" && task.getTask("h1").status !== "completed"),
        }));
        """,
        tmp_path,
    )
    assert result["reopened"] is True, (
        "reopen must be available: it is the only way back from a completed task"
    )
    assert result["withdrawn"] == ["h2"]
    assert result["dependentStatus"] == "recovery_hold"
    assert result["heldBy"] is None, "the holder is released with the premise"
    assert result["held"] is True, "and the attempt is held rather than offered straight back out"
    assert result["namesTheTask"] == "h1"
    assert "premise" in str(result["note"]), "the note says what withdrew it"
    assert result["leaseReleased"] == ["beta"], (
        "an open lease left behind would keep the resources locked by a participant "
        "who is no longer working on anything"
    )
    assert result["invariant"] is True


def test_reopen_does_not_depend_on_who_is_working(tmp_path: Path) -> None:
    """The reason the refusal went, stated as the property that replaced it.

    Reopen used to be refused while a dependent was held and accepted a moment
    later, so one operation had two answers depending on timing. Two independent
    fixtures differ in exactly one thing — whether the dependent is completed or
    being worked on — and the reopen's answer must not differ with it.

    Separate ids on purpose: rebuilding one chain in place does not work, because
    a withdrawn task comes back under a recovery hold and re-taking it needs a
    reason, which is the other rule doing its job.
    """
    result = run(
        """
        const build = (premise, dependent) => {
          task.createTask({ id: premise, subject: premise });
          task.createTask({ id: dependent, subject: dependent, dependsOn: [premise] });
          task.takeTask(premise, "alpha");
          task.completeTaskWithOutcome(premise, "alpha", "success", "done", { checks: task.ALL_COMPLETION_CHECKS });
        };
        // One fixture with the dependent completed, one with it being worked on.
        build("done-premise", "done-dependent");
        task.takeTask("done-dependent", "beta");
        task.completeTaskWithOutcome("done-dependent", "beta", "success", "built on it", { checks: task.ALL_COMPLETION_CHECKS });
        const quiet = task.reopenTask("done-premise");

        build("busy-premise", "busy-dependent");
        task.takeTask("busy-dependent", "beta");
        const heldBefore = task.getTask("busy-dependent").status;
        const busy = task.reopenTask("busy-premise");

        console.log(JSON.stringify({
          completedRefused: quiet.ok === false,
          completedWithdrawn: quiet.ok ? quiet.invalidated.map((entry) => entry.id) : null,
          heldBefore,
          heldRefused: busy.ok === false,
          heldWithdrawn: busy.ok ? busy.invalidated.map((entry) => entry.id) : null,
          heldAfter: task.getTask("busy-dependent").status,
          heldAfterNamesPremise: task.getTask("busy-dependent").invalidatedBy ?? null,
        }));
        """,
        tmp_path,
    )
    assert result["heldBefore"] == "in_progress", "the setup really is a held dependent"
    assert result["completedRefused"] is False, "reopen after a completed dependent"
    assert result["heldRefused"] is False, (
        "the same reopen must not be refused because somebody happens to be working"
    )
    assert result["completedWithdrawn"] == ["done-dependent"]
    assert result["heldWithdrawn"] == ["busy-dependent"], "the held dependent is withdrawn, not spared"
    assert result["heldAfter"] == "recovery_hold"
    assert result["heldAfterNamesPremise"] == "busy-premise"


def test_a_marker_submission_cannot_skip_the_checks(tmp_path: Path) -> None:
    """A participant writes a marker file instead of calling a tool. That is a
    second route to the same completion, so it carries the same rules — otherwise
    every check would be advisory."""
    result = run(
        """
        task.createTask({ id: "m1", subject: "via marker" });
        task.takeTask("m1", "alpha");
        const silent = task.applySubmissionIntent({
          taskId: "m1", participant: "alpha", spawnId: "s1", status: "completed", timestamp: Date.now(),
        }, { checks: task.ALL_COMPLETION_CHECKS });
        const answered = task.applySubmissionIntent({
          taskId: "m1", participant: "alpha", spawnId: "s1", status: "completed",
          result: "the checks passed", timestamp: Date.now(),
        }, { checks: task.ALL_COMPLETION_CHECKS });
        console.log(JSON.stringify({
          silentRefused: silent.ok === false,
          silentRefusal: silent.ok ? null : silent.reason,
          answeredAccepted: answered.ok,
          status: task.getTask("m1").status,
        }));
        """,
        tmp_path,
    )
    assert result["silentRefused"] is True, "a marker is not a way around the checks"
    assert "result" in str(result["silentRefusal"])
    assert result["answeredAccepted"] is True
    assert result["status"] == "completed"


# ── The read side of the completion checks ──


def test_marker_submissions_retain_gate_verdicts_and_refuse_retired_callers(tmp_path: Path) -> None:
    """Exercise persisted marker data, validation, and application together."""
    result = run(
        """
        import fs from "node:fs";
        import path from "node:path";
        const directory = path.join(process.env.PI_CODING_AGENT_DIR, "submissions");
        const created = task.createTask({ id: "marker-gate", subject: "gated marker", verify: "Confirm the output" });
        const taken = task.takeTask("marker-gate", "alpha");
        if (!created.ok || !taken.ok) throw new Error("The gated attempt was not started");
        const publish = (overrides) => {
          const intent = {
            taskId: "marker-gate", participant: "alpha", spawnId: "s1", status: "completed",
            result: "Checked the output", timestamp: Date.now(), ...overrides,
          };
          if (!task.createTaskIntent(directory, "marker-gate", intent)) throw new Error("The marker was not published");
          return task.takeTaskIntent(directory);
        };
        const invalid = publish({ verdict: "unknown" });
        const stale = publish({ spawnId: "retired", verdict: "pass" });
        const staleResult = task.applySubmissionIntent(stale.intent, { checks: task.ALL_COMPLETION_CHECKS });
        const failed = publish({ verdict: "fail" });
        const failedResult = task.applySubmissionIntent(failed.intent, { checks: task.ALL_COMPLETION_CHECKS });
        const beforeSuccess = task.getTask("marker-gate").status;
        const passed = publish({ verdict: "pass" });
        const passedResult = task.applySubmissionIntent(passed.intent, { checks: task.ALL_COMPLETION_CHECKS });
        console.log(JSON.stringify({
          invalidAccepted: invalid.intent !== undefined,
          invalidNotice: invalid.diagnostic,
          staleAccepted: staleResult.ok,
          staleNotice: staleResult.reason,
          failedAccepted: failedResult.ok,
          failedNotice: failedResult.reason,
          beforeSuccess,
          passedAccepted: passedResult.ok,
          status: task.getTask("marker-gate").status,
          verdict: task.getTask("marker-gate").completionVerdict,
          gate: task.getTask("marker-gate").completionGate,
          markersRemaining: fs.readdirSync(directory),
        }));
        """,
        tmp_path,
    )
    assert result["invalidAccepted"] is False
    assert "invalid submission verdict" in result["invalidNotice"]
    assert result["staleAccepted"] is False
    assert "current participant" in result["staleNotice"]
    assert result["failedAccepted"] is False
    assert "fail" in result["failedNotice"]
    assert result["beforeSuccess"] == "in_progress"
    assert result["passedAccepted"] is True
    assert result["status"] == "completed"
    assert result["verdict"] == "pass"
    assert result["gate"] == "Confirm the output"
    assert result["markersRemaining"] == []


def test_the_graph_is_enforced_on_the_take_path_itself(tmp_path: Path) -> None:
    """Two refusals are decided in `takeTask` and nothing pinned either.

    The dependency graph is the reason a task set is safe to share — a task cannot be
    taken before what it depends on exists, and two participants cannot take work
    over the same files. Both refusals lived in the take path, and both were
    reachable only from a throwaway driver script, which is not a test: removing
    either check left the suite green.
    """
    result = run(
        """
        task.createTask({ id: "premise", subject: "the premise" });
        task.createTask({ id: "needs-it", subject: "depends on the premise", dependsOn: ["premise"] });
        task.createTask({ id: "firmware-a", subject: "touches the firmware", resources: ["firmware"] });
        task.createTask({ id: "firmware-b", subject: "touches it too", resources: ["firmware/sub-node"] });

        const early = task.takeTask("needs-it", "alpha");
        task.takeTask("premise", "alpha");
        task.completeTaskWithOutcome("premise", "alpha", "success", "done", { checks: task.ALL_COMPLETION_CHECKS });
        const nowOk = task.takeTask("needs-it", "alpha");

        const first = task.takeTask("firmware-a", "alpha");
        const second = task.takeTask("firmware-b", "beta");

        console.log(JSON.stringify({
          earlyRefusal: early.ok === false,
          earlyReason: early.refusal ?? null,
          namedDependencies: early.ok ? null : early.detail,
          reasonNamesIt: early.ok ? null : early.reason.includes("premise"),
          okAfterPremise: nowOk.ok,
          firstOk: first.ok,
          secondRefusal: second.ok === false,
          secondReason: second.refusal ?? null,
          namesTheHolder: second.ok ? null : second.detail,
        }));
        """,
        tmp_path,
    )
    assert result["earlyRefusal"] is True, (
        "a task cannot be taken before what it depends on exists"
    )
    assert result["earlyReason"] == "unmet-dependencies"
    assert result["namedDependencies"] == "premise", (
        "a task with several dependencies and one refusal saying only that some are unmet gives the "
        "caller nothing to act on"
    )
    assert result["reasonNamesIt"] is True
    assert result["okAfterPremise"] is True, "and it becomes takeable once the premise completes"
    assert result["firstOk"] is True
    assert result["secondRefusal"] is True, (
        "two participants cannot hold work whose resources overlap; a prefix overlaps its descendants"
    )
    assert result["secondReason"] == "resource-conflict"
    assert result["namesTheHolder"] == "alpha", "the refusal names who holds it"


def test_a_task_names_which_of_its_dependencies_are_unfinished(tmp_path: Path) -> None:
    """`dependsOn` says what the edges are. Which of them are unfinished is the
    comparison a caller would otherwise make by hand against a list — and in a
    split of n tasks, the one it wants answered for every task at once."""
    result = run(
        """
        task.createTask({ id: "base", subject: "the premise" });
        task.createTask({ id: "mid", subject: "middle", dependsOn: ["base"] });
        task.createTask({ id: "leaf", subject: "leaf", dependsOn: ["mid"] });
        task.createTask({ id: "solo", subject: "no dependencies" });
        const before = {
          base: task.blockedDependencies(task.getTask("base")),
          mid: task.blockedDependencies(task.getTask("mid")),
          leaf: task.blockedDependencies(task.getTask("leaf")),
          solo: task.blockedDependencies(task.getTask("solo")),
        };
        task.takeTask("base", "alpha");
        task.completeTaskWithOutcome("base", "alpha", "success", "done", { checks: task.ALL_COMPLETION_CHECKS });
        const after = {
          mid: task.blockedDependencies(task.getTask("mid")),
          leaf: task.blockedDependencies(task.getTask("leaf")),
        };
        console.log(JSON.stringify({ before, after }));
        """,
        tmp_path,
    )
    assert result["before"] == {"base": [], "mid": ["base"], "leaf": ["mid"], "solo": []}, (
        "each task names only what is unfinished, in declaration order"
    )
    assert result["after"] == {"mid": [], "leaf": ["mid"]}, (
        "finishing the premise unblocks exactly one edge, and the rest still name theirs"
    )


def test_a_list_can_be_narrowed_to_what_is_completable_now(tmp_path: Path) -> None:
    """`claimable` answers what can be started. After finishing one of n, the
    question is which of the rest can be *finished* — and a batch of n should not
    have to be discovered one refused completion at a time."""
    result = run(
        """
        task.createTask({ id: "c-base", subject: "base" });
        task.createTask({ id: "c-first", subject: "first", dependsOn: ["c-base"] });
        task.createTask({ id: "c-second", subject: "second", dependsOn: ["c-first"] });
        task.createTask({ id: "c-side", subject: "unrelated side quest" });
        const nothingReady = task.completableTasks().map((task) => task.id);
        task.takeTask("c-base", "alpha");
        task.completeTaskWithOutcome("c-base", "alpha", "success", "done", { checks: task.ALL_COMPLETION_CHECKS });
        task.takeTask("c-first", "beta");
        const ready = task.completableTasks().map((task) => task.id);
        // A task nobody has touched has no attempt on the record, so it is not
        // completable however finished its dependencies are.
        task.takeTask("c-side", "alpha");
        const readyWithSide = task.completableTasks().map((task) => task.id);
        task.takeTask("c-second", "beta");
        console.log(JSON.stringify({ nothingReady, ready, readyWithSide }));
        """,
        tmp_path,
    )
    assert result["nothingReady"] == [], (
        "nothing is completable before an attempt exists, whatever the dependencies say"
    )
    assert result["ready"] == ["c-first"], (
        "finishing the premise unblocks exactly the dependent that is being worked on"
    )
    assert result["readyWithSide"] == ["c-first", "c-side"], (
        "an unrelated task with an attempt is completable too; the filter is about state, not about the split"
    )
