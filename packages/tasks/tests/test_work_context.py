"""Per-Work-Item context: workspace path, structured handoff, budget, refs.

Contract: packages/tasks/features/work-context.feature
"""

from __future__ import annotations

import json
from pathlib import Path

from task_helpers import PACKAGE, run_node

TASK = (PACKAGE / "index.ts").as_uri()


def run(script: str, tmp_path: Path) -> dict[str, object]:
    return run_node(
        f'''\
        import * as task from "{TASK}";
        {script}
        ''',
        env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)},
    )


def test_handoff_carries_every_supplied_field_and_formats_one_section_each(tmp_path: Path) -> None:
    result = run(
        '''
        const built = task.buildWorkHandoff({
          candidate: "rev abc123, excluding dirty recap files",
          delta: "rewrote the retry loop",
          verification: "pnpm typecheck clean; 42 tests pass",
          priorFindings: ["F1: unbounded list", "F2: vacuous assertion"],
          outstanding: ["sandbox profile not implemented"],
        });
        const text = task.formatWorkHandoff(built.handoff);
        const partial = task.formatWorkHandoff(task.buildWorkHandoff({ delta: "only a delta" }).handoff);
        console.log(JSON.stringify({
          handoff: built.handoff,
          clipped: built.clipped,
          sections: ["CANDIDATE CHECKED", "CHANGE DELTA", "VERIFICATION RUN", "PRIOR FINDINGS", "OUTSTANDING"]
            .filter((heading) => text.includes(heading)),
          findingsMarked: text.includes("do not lose these"),
          partialSections: ["CANDIDATE CHECKED", "CHANGE DELTA", "VERIFICATION RUN", "PRIOR FINDINGS", "OUTSTANDING"]
            .filter((heading) => partial.includes(heading)),
          empty: task.formatWorkHandoff(undefined),
        }));
        ''',
        tmp_path,
    )
    handoff = result["handoff"]
    assert isinstance(handoff, dict)
    assert handoff["candidate"] == "rev abc123, excluding dirty recap files"
    assert handoff["priorFindings"] == ["F1: unbounded list", "F2: vacuous assertion"]
    assert result["clipped"] is False
    assert result["sections"] == ["CANDIDATE CHECKED", "CHANGE DELTA", "VERIFICATION RUN", "PRIOR FINDINGS", "OUTSTANDING"]
    assert result["findingsMarked"] is True, "prior findings must be flagged so a successor cannot drop them"
    assert result["partialSections"] == ["CHANGE DELTA"], "an absent field produces no empty section"
    assert result["empty"] == ""


def test_an_oversized_brief_is_clipped_and_says_so_without_splitting_utf8(tmp_path: Path) -> None:
    result = run(
        '''
        const long = "é".repeat(4000);
        const built = task.buildWorkHandoff({ delta: long, budgetBytes: 1200 });
        const clipped = task.clipToBytes("héllo wörld", 8);
        console.log(JSON.stringify({
          clipped: built.clipped,
          marked: (built.handoff.delta ?? "").includes("clipped to budget"),
          withinBudget: Buffer.byteLength(built.handoff.delta ?? "", "utf-8") <= 1200,
          noReplacementChar: !(built.handoff.delta ?? "").includes("\\uFFFD"),
          shortUnclipped: task.clipToBytes("abc", 100),
          clippedNoReplacement: !clipped.text.includes("\\uFFFD"),
        }));
        ''',
        tmp_path,
    )
    assert result["clipped"] is True
    assert result["marked"] is True, "a silently truncated brief is worse than one that announces itself"
    assert result["withinBudget"] is True
    assert result["noReplacementChar"] is True, "clipping must not split a UTF-8 sequence"
    assert result["shortUnclipped"] == {"text": "abc", "clipped": False}
    assert result["clippedNoReplacement"] is True


def test_context_budget_is_measured_not_declared(tmp_path: Path) -> None:
    result = run(
        '''
        const small = { description: "fix it", result: "done", context: { budgetBytes: 4096 } };
        const big = { description: "x".repeat(3000), result: "y".repeat(3000),
          errorMessage: "z".repeat(3000), context: { budgetBytes: 4096,
            handoff: { delta: "w".repeat(3000) }, refs: [{ kind: "work", id: "a" }] } };
        const defaulted = { description: "x".repeat(200) };
        console.log(JSON.stringify({
          smallWithin: task.withinContextBudget(small),
          bigWithin: task.withinContextBudget(big),
          bigBytes: task.workContextBytes(big),
          defaultBudget: task.DEFAULT_CONTEXT_BUDGET_BYTES,
          defaultWithin: task.withinContextBudget(defaulted),
          countsEveryPart: task.workContextBytes(big) > 12000,
        }));
        ''',
        tmp_path,
    )
    assert result["smallWithin"] is True
    assert result["bigWithin"] is False, "an over-budget Work Item is reported, not silently grown"
    assert result["defaultWithin"] is True
    assert int(str(result["defaultBudget"])) == 64 * 1024
    assert result["countsEveryPart"] is True, "description, result, error, handoff, and refs all count"


def test_context_refs_are_deduplicated_and_capped(tmp_path: Path) -> None:
    refs = json.dumps(
        [{"kind": "work", "id": "a"}, {"kind": "work", "id": "a"}, {"kind": "file", "id": "  "}]
        + [{"kind": "report", "id": f"r{i}"} for i in range(80)]
    )
    result = run(
        f'''
        const normalized = task.normalizeContextRefs({refs});
        console.log(JSON.stringify({{
          count: normalized.length,
          cap: task.MAX_CONTEXT_REFS,
          first: normalized[0],
          hasDuplicate: normalized.filter((ref) => ref.id === "a").length,
          hasEmpty: normalized.some((ref) => ref.id.trim() === ""),
          emptyInput: task.normalizeContextRefs(undefined),
        }}));
        ''',
        tmp_path,
    )
    assert result["count"] == int(str(result["cap"]))
    assert result["hasDuplicate"] == 1
    assert result["hasEmpty"] is False
    assert result["first"] == {"kind": "work", "id": "a"}
    assert result["emptyInput"] == []


def test_a_work_item_records_a_workspace_path_and_never_a_session_id(tmp_path: Path) -> None:
    """The boundary that keeps @fradser/pi-tasks free of the process layer."""
    result = run(
        '''
        // Not named `task`: that shadows the imported namespace binding.
        const item = { id: "w1", subject: "s", dependsOn: [], resources: [], status: "pending",
          createdAt: 1, updatedAt: 1,
          context: { workspacePath: "/home/dev/.pi/agent/workspaces/reviewer/proj-abc" } };
        console.log(JSON.stringify({ serialized: JSON.stringify(item) }));
        ''',
        tmp_path,
    )
    serialized = str(result["serialized"])
    assert "workspacePath" in serialized
    for forbidden in ("sessionId", "sessionFile", "sessionRef", "session-id"):
        assert forbidden not in serialized, forbidden
    source = (PACKAGE / "src" / "context.ts").read_text(encoding="utf-8")
    assert "sessionId" not in source and "SessionManager" not in source, (
        "@fradser/pi-tasks must not resolve or store session handles; Pi owns session storage"
    )
