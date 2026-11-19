"""What the completion checks cost a caller that satisfies them.

Contract: packages/tasks/features/completion-checks.feature
Rule: An honest attempt is not made to pay for the checks twice.
"""

from __future__ import annotations

import json
from pathlib import Path

from task_helpers import PACKAGE, run_node

ENTRY = (PACKAGE / "index.ts").as_uri()

# The tool harness, because two of these scenarios are about what the model is
# told: a refusal it reads, and a take result that names the rules ahead of time.
# Plain string, so its braces stay single: only the surrounding f-string in
# `run` interprets braces, and the harness is substituted into it as a value.
TOOLS = """
import assert from "node:assert/strict";
import { Value } from "typebox/value";
const tools = new Map();
task.default({
  registerTool(tool) { tools.set(tool.name, tool); },
  on() {}, events: { emit() {} },
});
const call = async (name, params) => {
  const tool = tools.get(name);
  assert.equal(Value.Check(tool.parameters, params), true, `${name} parameters are not declared`);
  return tool.execute("case", params, undefined, undefined, {});
};
const checked = async (name, params) => {
  const result = await call(name, params);
  assert.equal(result.details.ok, true, result.content[0].text);
  return result;
};
"""


def run(script: str, tmp_path: Path, harness: str = "") -> dict[str, object]:
    # Substituted, not formatted: the harness is JavaScript full of braces, and a
    # Python format pass reads every one of them as a placeholder.
    return run_node(
        f"""
        import * as task from {json.dumps(ENTRY)};
        {harness.replace("{entry}", json.dumps(ENTRY))}
        {script}
        """,
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )


def test_a_refusal_names_every_unsatisfied_check_at_once(tmp_path: Path) -> None:
    """One round trip per rule was the old cost: fix one, be refused for the next."""
    result = run(
        '''
        task.createTask({ id: "prereq", subject: "Prerequisite" });
        task.createTask({ id: "one", subject: "Gated work", verify: "Reviewer confirms the fix", dependsOn: ["prereq"] });
        const refused = task.completeTaskWithOutcome("one", "main", "success", undefined, {
          checks: task.ALL_COMPLETION_CHECKS,
        });
        console.log(JSON.stringify({ ok: refused.ok, code: refused.refusal, reason: refused.reason }));
        ''',
        tmp_path,
    )
    assert result["ok"] is False
    # The machine code stays a closed set a caller switches on, so it names the
    # first check that failed. The reason is where the whole list lives.
    assert result["code"] == "unfinished-dependency"
    reason = str(result["reason"])
    for remedy in (
        "is not completed",              # the dependency
        "was never taken",               # no attempt on the record
        "no result recorded",            # no evidence
        "declares a completion gate",    # the gate was not answered
    ):
        assert remedy in reason, f"{remedy} missing from: {reason}"


def test_taking_a_task_names_what_its_completion_must_carry(tmp_path: Path) -> None:
    result = run(
        """
        const gated = await checked("create_task", { subject: "Gated", verify: "Reviewer confirms the fix" });
        const plain = await checked("create_task", { subject: "Plain" });
        const takenGated = await checked("update_task", { id: gated.details.id, status: "in_progress" });
        const takenPlain = await checked("update_task", { id: plain.details.id, status: "in_progress" });
        console.log(JSON.stringify({
          gated: takenGated.details.requirements ?? [],
          gatedText: takenGated.content[0].text,
          plain: takenPlain.details.requirements ?? [],
          plainHasGate: (takenPlain.details.requirements ?? []).some(entry => entry.includes("verdict")),
        }));
        """,
        tmp_path,
        harness=TOOLS,
    )
    assert any("evidence" in entry for entry in result["gated"])
    assert any("Reviewer confirms the fix" in entry for entry in result["gated"])
    assert "REQUIRED AT COMPLETION" in str(result["gatedText"])
    # A task with no gate is not asked for a verdict, so the promise matches the
    # checks that would actually refuse it.
    assert result["plainHasGate"] is False


def test_a_creator_completes_its_own_task_without_a_take(tmp_path: Path) -> None:
    """Contract: completion-checks.feature, "A creator is accountable for the work
    it records itself".

    `createdBy` is recorded from the caller's own context. A task a caller recorded
    and then finished itself has an accountable party on the record, so the take
    that would only restate it is not demanded.
    """
    result = run(
        """
        const created = await checked("create_task", { subject: "Recorded and finished", verify: "Reviewer confirms the fix" });
        const completed = await checked("update_task", {
          id: created.details.id, status: "completed", outcome: "success",
          result: "ran the suite; 141 passed", verdict: "pass",
        });
        const after = task.getTask(created.details.id);
        console.log(JSON.stringify({
          status: completed.details.status, createdBy: after.createdBy, held: after.claimedBy ?? null,
        }));
        """,
        tmp_path,
        harness=TOOLS,
    )
    assert result["status"] == "completed"
    assert result["createdBy"] == "main"
    # The take was skipped, and the record still says who delivered it.
    assert result["held"] is None


def test_a_task_recorded_by_another_participant_still_refuses_a_bare_completion(tmp_path: Path) -> None:
    """The creator route is accountability, not a hole in the rule."""
    result = run(
        '''
        task.createTask({ id: "theirs", subject: "Another participant's work", createdBy: "reviewer" });
        const refused = task.completeTaskWithOutcome("theirs", "main", "success", "my word for it", {
          checks: task.ALL_COMPLETION_CHECKS,
        });
        console.log(JSON.stringify({ ok: refused.ok, code: refused.refusal, reason: refused.reason }));
        ''',
        tmp_path,
    )
    assert result["ok"] is False
    assert result["code"] == "never-taken"
    assert "was not recorded by this caller" in str(result["reason"])


def test_the_call_after_a_refusal_succeeds_so_the_attempt_costs_at_most_one_extra_call(tmp_path: Path) -> None:
    result = run(
        """
        const created = await checked("create_task", { subject: "Cost", verify: "Reviewer confirms the fix" });
        await checked("update_task", { id: created.details.id, status: "in_progress" });
        const refused = await call("update_task", {
          id: created.details.id, status: "completed", outcome: "success",
        });
        const accepted = await checked("update_task", {
          id: created.details.id, status: "completed", outcome: "success",
          result: "ran the suite; 130 passed", verdict: "pass",
        });
        console.log(JSON.stringify({
          refusedAccepted: refused.details.ok, refusal: refused.content[0].text,
          accepted: accepted.details.status, verdict: accepted.details.verdict,
        }));
        """,
        tmp_path,
        harness=TOOLS,
    )
    assert result["refusedAccepted"] is False
    refusal = str(result["refusal"])
    assert "no result recorded" in refusal
    assert "declares a completion gate" in refusal
    assert result["accepted"] == "completed"
    assert result["verdict"] == "pass"
