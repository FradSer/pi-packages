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
        const built = task.buildTaskHandoff({
          candidate: "rev abc123, excluding dirty recap files",
          delta: "rewrote the retry loop",
          verification: "pnpm typecheck clean; 42 tests pass",
          priorFindings: ["F1: unbounded list", "F2: vacuous assertion"],
          outstanding: ["sandbox profile not implemented"],
        });
        const text = task.formatTaskHandoff(built.handoff);
        const partial = task.formatTaskHandoff(task.buildTaskHandoff({ delta: "only a delta" }).handoff);
        console.log(JSON.stringify({
          handoff: built.handoff,
          clipped: built.clipped,
          sections: ["CANDIDATE CHECKED", "CHANGE DELTA", "VERIFICATION RUN", "PRIOR FINDINGS", "OUTSTANDING"]
            .filter((heading) => text.includes(heading)),
          findingsMarked: text.includes("do not lose these"),
          partialSections: ["CANDIDATE CHECKED", "CHANGE DELTA", "VERIFICATION RUN", "PRIOR FINDINGS", "OUTSTANDING"]
            .filter((heading) => partial.includes(heading)),
          empty: task.formatTaskHandoff(undefined),
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
        const built = task.buildTaskHandoff({ delta: long, budgetBytes: 1200 });
        console.log(JSON.stringify({
          clipped: built.clipped,
          marked: (built.handoff.delta ?? "").includes("clipped to budget"),
          withinBudget: Buffer.byteLength(built.handoff.delta ?? "", "utf-8") <= 1200,
          noReplacementChar: !(built.handoff.delta ?? "").includes("\\uFFFD"),
          shortUnclipped: task.clipToBytes("abc", 100),
        }));
        ''',
        tmp_path,
    )
    assert result["clipped"] is True
    assert result["marked"] is True, "a silently truncated brief is worse than one that announces itself"
    assert result["withinBudget"] is True
    assert result["noReplacementChar"] is True, "clipping must not split a UTF-8 sequence"
    assert result["shortUnclipped"] == {"text": "abc", "clipped": False}


def test_clipping_preserves_complete_utf8_prefixes_within_the_byte_limit(tmp_path: Path) -> None:
    """Test aligned and split cuts for two-, three-, and four-byte characters."""
    result = run(
        '''
        const marker = "\\n[context clipped to budget]";
        const markerBytes = Buffer.byteLength(marker, "utf8");
        const cases = [];
        for (const character of ["é", "中", "𐍈"]) {
          const width = Buffer.byteLength(character, "utf8");
          const text = character.repeat(80);
          for (const room of [1, width - 1, width, width + 1]) {
            const budget = markerBytes + room;
            const clipped = task.clipToBytes(text, budget);
            cases.push({
              character, room, budget, clipped: clipped.clipped,
              text: clipped.text,
              expected: character.repeat(Math.floor(room / width)) + marker,
              bytes: Buffer.byteLength(clipped.text, "utf8"),
            });
          }
        }
        // A budget smaller than the notice still bounds the output. The
        // structured clipped flag reports truncation when the notice cannot fit.
        const tiny = [0, 8, markerBytes].map((budget) => {
          const clipped = task.clipToBytes("é".repeat(80), budget);
          return { budget, bytes: Buffer.byteLength(clipped.text, "utf8"), clipped: clipped.clipped };
        });
        console.log(JSON.stringify({ cases, tiny }));
        ''',
        tmp_path,
    )
    for case in result["cases"]:
        assert case["clipped"] is True
        assert case["text"] == case["expected"], case
        assert case["bytes"] <= case["budget"], case
    for case in result["tiny"]:
        assert case["clipped"] is True
        assert case["bytes"] <= case["budget"], case


def test_context_budget_is_measured_not_declared(tmp_path: Path) -> None:
    result = run(
        '''
        const small = { description: "fix it", result: "done", context: { budgetBytes: 4096 } };
        const big = { description: "x".repeat(3000), result: "y".repeat(3000),
          context: { budgetBytes: 4096,
            handoff: { delta: "w".repeat(3000), verification: "v".repeat(3000) },
            refs: [{ kind: "work", id: "a" }] } };
        const defaulted = { description: "x".repeat(200) };
        console.log(JSON.stringify({
          smallWithin: task.withinContextBudget(small),
          bigWithin: task.withinContextBudget(big),
          bigBytes: task.taskContextBytes(big),
          defaultBudget: task.DEFAULT_CONTEXT_BUDGET_BYTES,
          defaultWithin: task.withinContextBudget(defaulted),
          countsEveryPart: task.taskContextBytes(big) > 12000,
        }));
        ''',
        tmp_path,
    )
    assert result["smallWithin"] is True
    assert result["bigWithin"] is False, "an over-budget Work Item is reported, not silently grown"
    assert result["defaultWithin"] is True
    assert int(str(result["defaultBudget"])) == 64 * 1024
    assert result["countsEveryPart"] is True, "description, result, handoff, and refs all count"


def test_a_completion_gate_is_measured_and_a_creation_over_budget_is_refused(tmp_path: Path) -> None:
    """`verify` is free text a model writes in its own words, and the tasks file
    is re-serialized on every change. Measuring only `description`, `result` and
    `context` left it unbounded — the identical hole the context measurement was
    closed for, one field up."""
    result = run(
        """
        const gate = "x".repeat(300000);
        const created = task.createTask({ subject: "gate bomb", verify: gate });
        task.createTask({ id: "g1", subject: "update gate" });
        const updated = task.updateTask("g1", { verify: gate });
        console.log(JSON.stringify({
          createRefused: created.ok === false,
          createReason: created.ok ? null : created.reason,
          updateRefused: updated.ok === false,
          measuredWithGate: task.taskContextBytes({ subject: "s", verify: gate }),
          measuredWithout: task.taskContextBytes({ subject: "s" }),
        }));
        """,
        tmp_path,
    )
    assert result["createRefused"] is True, "a creation is a write like any other"
    assert int(str(result["measuredWithGate"])) > 290000
    assert int(str(result["measuredWithGate"])) - int(str(result["measuredWithout"])) > 290000, (
        "the completion gate counts against the budget"
    )
    assert result["updateRefused"] is True


def test_a_budget_below_one_byte_is_refused_rather_than_floored_to_nothing(tmp_path: Path) -> None:
    """`0.5` passed a `> 0` guard and was floored afterwards, leaving a Task whose
    budget was 0: every later write refused for exceeding a budget of nothing."""
    result = run(
        """
        const refused = task.normalizeTaskContext({ budgetBytes: 0.5 });
        task.createTask({ id: "b1", subject: "budget" });
        const stored = task.setTaskContext("b1", { budgetBytes: 0.5 });
        const one = task.normalizeTaskContext({ budgetBytes: 1 });
        console.log(JSON.stringify({
          refused: refused.ok === false,
          reason: refused.ok ? null : refused.error,
          storeRefused: stored.ok === false,
          smallestAccepted: one.ok ? one.value.budgetBytes : null,
        }));
        """,
        tmp_path,
    )
    assert result["refused"] is True
    assert "budgetBytes" in str(result["reason"])
    assert result["storeRefused"] is True, "the store must also refuse a sub-byte budget"
    assert int(str(result["smallestAccepted"])) == 1, "one byte is a budget; anything under it is not"


def test_resource_tags_are_capped_and_measured_like_every_other_retained_field(tmp_path: Path) -> None:
    """`resources` is the one model-supplied list on a Task with no ceiling. It is
    re-serialized into the tasks file on every change, so an uncapped list is a
    tasks file that grows for free — and it measured as one byte."""
    result = run(
        """
        const tags = (n) => Array.from({ length: n }, (_, i) => `resource/number/${i}`);
        task.createTask({ id: "r1", subject: "tags" });
        const atCap = task.updateTask("r1", { resources: tags(task.MAX_TASK_RESOURCES) });
        const overCap = task.updateTask("r1", { resources: tags(task.MAX_TASK_RESOURCES + 1) });
        const createOver = task.createTask({ subject: "too many", resources: tags(task.MAX_TASK_RESOURCES + 1) });
        const measured = task.taskContextBytes({ subject: "s", resources: tags(100) });
        const unmeasured = task.taskContextBytes({ subject: "s" });
        console.log(JSON.stringify({
          cap: task.MAX_TASK_RESOURCES,
          atCapOk: atCap.ok,
          storedAtCap: task.getTask("r1").resources.length,
          overCapRefused: overCap.ok === false,
          overCapReason: overCap.ok ? null : overCap.reason,
          createOverRefused: createOver.ok === false,
          measuredDelta: measured - unmeasured,
        }));
        """,
        tmp_path,
    )
    assert result["atCapOk"] is True
    assert result["storedAtCap"] == int(str(result["cap"]))
    assert result["overCapRefused"] is True, "an uncapped tag list makes the tasks file grow for free"
    assert "resources" in str(result["overCapReason"])
    assert result["createOverRefused"] is True, "a creation is bounded like every other write"
    assert int(str(result["measuredDelta"])) > 1000, "tags count against the budget like any other free text"


def test_a_budget_can_be_tightened_but_never_loosened(tmp_path: Path) -> None:
    """The byte budget is the only thing bounding a brief, so a caller able to
    raise it removes the bound. One `update` setting a gigabyte made 2.7 MB of
    findings on a single task, re-serialized on every change after that."""
    result = run(
        """
        task.createTask({ id: "b1", subject: "budget" });
        const raised = task.setTaskContext("b1", { budgetBytes: 1e9 });
        const afterRaise = task.getTask("b1").context.budgetBytes;
        const tightened = task.setTaskContext("b1", { budgetBytes: 4096 });
        const afterTighten = task.getTask("b1").context.budgetBytes;
        // A later raise is clamped to the ceiling again, so it lands on the
        // default rather than on whatever the Task had been held to.
        const raisedAgain = task.updateTask("b1", { context: { budgetBytes: 2e9 } });
        console.log(JSON.stringify({
          ceiling: task.DEFAULT_CONTEXT_BUDGET_BYTES,
          effectiveAfterRaise: afterRaise,
          raiseAccepted: raised.ok,
          tightenAccepted: tightened.ok,
          afterTighten,
          afterSecondRaise: task.getTask("b1").context.budgetBytes,
          raiseAgainAccepted: raisedAgain.ok,
          schemaMaximum: task.TASK_UPDATE_PARAMS.properties.context.properties.budgetBytes.maximum,
        }));
        """,
        tmp_path,
    )
    assert result["raiseAccepted"] is True
    assert int(str(result["effectiveAfterRaise"])) == int(str(result["ceiling"])), (
        "a budget above the task set's own default is clamped to it"
    )
    assert result["tightenAccepted"] is True
    assert int(str(result["afterTighten"])) == 4096, "a tighter budget is honoured"
    assert int(str(result["afterSecondRaise"])) == int(str(result["ceiling"])), (
        "a later raise is clamped to the ceiling rather than accepted"
    )
    assert int(str(result["schemaMaximum"])) == int(str(result["ceiling"])), (
        "the declared schema says the same thing the reader enforces"
    )


def test_the_store_refuses_an_unknown_context_field_on_its_own_account(tmp_path: Path) -> None:
    """`setTaskContext` is a public export a coordinator calls directly. Folding
    its argument through the merge dropped a misspelled field and reported
    success, so the caller believed a brief was recorded when nothing was — and a
    top-level-only check left a misspelled field *inside* a handoff doing the
    same thing."""
    result = run(
        """
        task.createTask({ id: "s1", subject: "direct write" });
        const viaSet = task.setTaskContext("s1", { notes: ["y".repeat(70000)] });
        const viaUpdate = task.updateTask("s1", { context: { handOff: { delta: "x" } } });
        const nestedViaSet = task.setTaskContext("s1", { handoff: { handOff: { delta: "x" } } });
        const nestedViaUpdate = task.updateTask("s1", { context: { handoff: { notes: ["x"] } } });
        console.log(JSON.stringify({
          setOk: viaSet.ok,
          setReason: viaSet.ok ? null : viaSet.reason,
          updateOk: viaUpdate.ok,
          updateReason: viaUpdate.ok ? null : viaUpdate.reason,
          nestedSetOk: nestedViaSet.ok,
          nestedSetReason: nestedViaSet.ok ? null : nestedViaSet.reason,
          nestedUpdateOk: nestedViaUpdate.ok,
          nestedUpdateReason: nestedViaUpdate.ok ? null : nestedViaUpdate.reason,
          stored: task.getTask("s1").context ?? null,
        }));
        """,
        tmp_path,
    )
    assert result["setOk"] is False, "the store refuses rather than repairing a field it cannot read"
    assert "notes" in str(result["setReason"])
    assert result["updateOk"] is False
    assert "handOff" in str(result["updateReason"])
    assert result["nestedSetOk"] is False, "a field inside a handoff is refused, not dropped"
    assert "handOff" in str(result["nestedSetReason"])
    assert result["nestedUpdateOk"] is False
    assert "notes" in str(result["nestedUpdateReason"])
    assert result["stored"] is None, "nothing was recorded in place of what was refused"


def test_a_refusal_does_not_echo_an_unbounded_input_back_to_the_model(tmp_path: Path) -> None:
    """A refusal is model-facing text. Naming the offending subject in it turned a
    70 KB input into a 70 KB error, which is the opposite of a bounded surface."""
    result = run(
        """
        const huge = "x".repeat(70000);
        const refused = task.createTask({ subject: huge });
        const viaTool = await task.executeTaskCreate({ subject: huge });
        console.log(JSON.stringify({
          refused: refused.ok === false,
          reasonLength: refused.ok ? null : refused.reason.length,
          reasonHasId: refused.ok ? null : /^[a-z0-9-]{1,48}$/.test(refused.reason.split('"')[1] ?? ""),
          toolTextLength: viaTool.content[0].text.length,
        }));
        """,
        tmp_path,
    )
    assert result["refused"] is True
    assert int(str(result["reasonLength"])) < 200, "the refusal names the task, not its subject"
    assert result["reasonHasId"] is True, "the derived id is the bounded thing to name"
    assert int(str(result["toolTextLength"])) < 200


def test_the_restored_tasks_is_read_back_through_the_same_checks_as_a_write(tmp_path: Path) -> None:
    """`loadTasks` is the other route into the store. Validating only on write left
    a restored `budgetBytes` unclamped, a context spread straight off disk, and a
    `dependsOn` holding something other than task ids — all reachable by editing
    one line of JSON, and all of them things the write path refuses."""
    result = run(
        """
        task.loadTasks({
          loose: {
            id: "loose", subject: "hand-edited", resources: [], status: "pending", createdAt: 1, updatedAt: 1,
            context: { budgetBytes: 1000000000, handoff: { priorFindings: ["abc"] } },
          },
          weird: {
            id: "weird", subject: "bad status", resources: [], dependsOn: [null, 7], status: "invented",
            createdAt: 1, updatedAt: 1,
          },
          badRefs: {
            id: "badRefs", subject: "bad refs", resources: [], dependsOn: [], status: "pending",
            createdAt: 1, updatedAt: 1, context: { refs: "not-an-array" },
          },
        });
        const listed = await task.executeTaskList({});
        const update = task.updateTask("loose", { context: { handoff: { delta: "x" } } });
        const takeable = task.listTasks().filter((t) => t.status === "pending" && !(t.status === "recovery_hold")).map((t) => t.id);
        console.log(JSON.stringify({
          clampedBudget: task.getTask("loose").context?.budgetBytes,
          ceiling: task.DEFAULT_CONTEXT_BUDGET_BYTES,
          findingsKept: task.getTask("loose").context?.handoff?.priorFindings,
          weirdStatus: task.getTask("weird").status,
          weirdHeld: task.getTask("weird").status === "recovery_hold",
          weirdDeps: task.getTask("weird").dependsOn,
          badRefsContext: task.getTask("badRefs").context ?? null,
          listed: listed.details.count,
          updateOk: update.ok,
          noticeMentionsAll: ["loose", "weird", "badRefs"].every((id) => (task.storeNotice() ?? "").includes(id)),
          takeable,
        }));
        """,
        tmp_path,
    )
    assert int(str(result["clampedBudget"])) == int(str(result["ceiling"])), (
        "a restored budget is clamped by the same rule a written one is"
    )
    assert result["findingsKept"] == ["abc"], "a readable brief survives the restore"
    assert result["weirdStatus"] == "recovery_hold", "a status the task store cannot define is held for inspection, not adopted"
    assert result["weirdHeld"] is True, "and the task is held rather than offered out"
    assert result["weirdDeps"] == [], "a dependency that is not a task id is dropped"
    assert result["badRefsContext"] is None, "a context the task store cannot read is dropped, not spread"
    assert result["listed"] == 3, "every task survives; only the unreadable fields go"
    assert result["updateOk"] is True
    assert result["noticeMentionsAll"] is True, "the repair is reported, naming what was repaired"
    assert "loose" in result["takeable"] and "weird" not in result["takeable"]


def test_a_context_that_would_record_nothing_is_refused_rather_than_accepted(tmp_path: Path) -> None:
    """A context whose every value is blank normalizes to nothing. Reporting
    success there is the outcome the reader exists to prevent — relocated from a
    misspelled field to a blank one."""
    result = run(
        """
        task.createTask({ id: "c1", subject: "blank" });
        const viaSet = task.setTaskContext("c1", { workspacePath: "   " });
        const viaUpdate = task.updateTask("c1", { context: { handoff: { delta: "" } } });
        const viaTool = await task.executeTaskUpdate({ id: "c1", context: {} });
        // A blank field beside a real one is still fine: the point is refusing a
        // context that would record nothing at all.
        const mixed = task.updateTask("c1", { context: { handoff: { delta: "", verification: "ran the suite" } } });
        console.log(JSON.stringify({
          setOk: viaSet.ok,
          setReason: viaSet.ok ? null : viaSet.reason,
          updateOk: viaUpdate.ok,
          toolOk: viaTool.details.ok,
          toolText: viaTool.content[0].text,
          mixedOk: mixed.ok,
          stored: task.getTask("c1").context ?? null,
        }));
        """,
        tmp_path,
    )
    assert result["setOk"] is False
    assert "no value to record" in str(result["setReason"])
    assert result["updateOk"] is False
    assert result["toolOk"] is False
    assert "no value to record" in result["toolText"]
    assert result["mixedOk"] is True, "a blank field beside a real one is not an empty context"
    assert result["stored"] == {"handoff": {"verification": "ran the suite"}}


def test_the_declared_status_enum_is_the_one_the_tasks_produces(tmp_path: Path) -> None:
    """`STATUS_ENUM` duplicated the `TaskStatus` union by hand. A status added to
    the union and not to the list would make every projection of it fail the
    declared schema at the codemode boundary, with a clean typecheck."""
    result = run(
        """
        task.createTask({ id: "e1", subject: "statuses" });
        const declared = task.TASK_TOOL_OUTPUT_SCHEMA.properties.task.properties.status.enum;
        const filterEnum = task.TASK_LIST_PARAMS.properties.statusFilter.items.enum;
        // Every status the store can put on a task, read from the type's own doc.
        const union = ["pending", "in_progress", "recovery_hold", "completed", "superseded"];
        console.log(JSON.stringify({
          declared,
          filterEnum,
          union,
          // The list is the task set's, so a status added to the tasks reaches the
          // declaration without a second edit anywhere.
          derivedFromTheTasks: JSON.stringify(declared) === JSON.stringify(task.TASK_STATUSES),
          agrees: JSON.stringify([...declared].sort()) === JSON.stringify([...union].sort()),
          filterAgrees: JSON.stringify([...filterEnum].sort()) === JSON.stringify([...union].sort()),
        }));
        """,
        tmp_path,
    )
    assert result["derivedFromTheTasks"] is True, (
        "the declared enum is the task set's own list, not a copy of it"
    )
    assert result["agrees"] is True, (
        f"the declared status enum has drifted from the task set's statuses: {result['declared']}"
    )
    assert result["filterAgrees"] is True, "the list filter and the declared result name the same statuses"


def test_a_note_on_a_reference_can_be_corrected(tmp_path: Path) -> None:
    """The note is the one field a later write exists to correct, so the most
    recent non-empty one is kept. Keeping the first made a corrected note
    unrecordable for the life of the Task."""
    result = run(
        """
        task.createTask({ id: "r1", subject: "refs" });
        task.updateTask("r1", { context: { refs: [{ kind: "report", id: "r0", note: "original" }] } });
        task.updateTask("r1", { context: { refs: [{ kind: "report", id: "r0", note: "corrected" }] } });
        task.updateTask("r1", { context: { refs: [{ kind: "report", id: "r0" }] } });
        console.log(JSON.stringify({
          refs: task.getTask("r1").context.refs,
          order: task.normalizeContextRefs([
            { kind: "work", id: "a", note: "first" },
            { kind: "work", id: "b" },
            { kind: "work", id: "a", note: "second" },
          ]),
        }));
        """,
        tmp_path,
    )
    assert result["refs"] == [{"kind": "report", "id": "r0", "note": "corrected"}], (
        f"the corrected note is the one kept: {result['refs']}"
    )
    order = result["order"]
    assert isinstance(order, list) and len(order) == 2
    assert [ref["id"] for ref in order] == ["a", "b"], "the first position is kept, so ordering is stable"
    assert order[0].get("note") == "second", "the most recent note wins"


def test_a_successor_brief_adds_to_the_findings_already_recorded(tmp_path: Path) -> None:
    """A successor supplies its own field; the outgoing attempt's findings are the
    one thing a brief must not drop, so a later write adds to them rather than
    replacing the list."""
    result = run(
        '''
        task.createTask({ id: "w1", subject: "hand this on" });
        task.setTaskContext("w1", { handoff: { candidate: "rev-1", priorFindings: ["F1: unbounded list", "F2: vacuous assertion"] } });
        const added = task.updateTask("w1", { context: { handoff: { delta: "rewrote the retry loop" } } });
        const twice = task.updateTask("w1", { context: { handoff: { priorFindings: ["F3: stale snapshot"] } } });
        const record = task.getTask("w1");
        console.log(JSON.stringify({
          ok: added.ok && twice.ok,
          candidate: record.context?.handoff?.candidate ?? null,
          delta: record.context?.handoff?.delta ?? null,
          findings: record.context?.handoff?.priorFindings ?? null,
        }));
        ''',
        tmp_path,
    )
    assert result["ok"] is True
    assert result["candidate"] == "rev-1", "an absent field leaves the recorded one alone"
    assert result["delta"] == "rewrote the retry loop"
    assert result["findings"] == ["F1: unbounded list", "F2: vacuous assertion", "F3: stale snapshot"], (
        "prior findings are added to; a successor must not be able to erase them by naming one more"
    )


def test_a_context_the_tasks_does_not_recognize_is_refused(tmp_path: Path) -> None:
    """The tool hands a model's context to the store, so the store is what has to
    know the shape. An unrecognized field is refused rather than retained: a brief
    nobody can read is not a brief."""
    result = run(
        '''
        task.createTask({ id: "w1", subject: "hand this on" });
        const wrong = task.normalizeTaskContext({ handOff: { canddate: "rev-1" } });
        const wrongRef = task.normalizeTaskContext({ refs: [{ kind: "note", id: "a" }] });
        const right = task.normalizeTaskContext({
          workspacePath: "/home/dev/proj",
          handoff: { delta: "two files", priorFindings: ["F1"] },
          refs: [{ kind: "work", id: "  " }, { kind: "file", id: "src/a.ts", note: " read " }],
        });
        console.log(JSON.stringify({
          unknownField: wrong.ok ? null : wrong.error,
          unknownRefKind: wrongRef.ok ? null : wrongRef.error,
          accepted: right.ok ? right.value : null,
          stored: (task.setTaskContext("w1", { handoff: { delta: "x" } }), task.getTask("w1").context?.handoff?.delta ?? null),
        }));
        ''',
        tmp_path,
    )
    assert "handOff" in str(result["unknownField"]), "the refusal names the field it did not recognize"
    assert "kind" in str(result["unknownRefKind"]), "a ref kind outside the closed set is refused"
    accepted = result["accepted"]
    assert isinstance(accepted, dict)
    assert accepted["workspacePath"] == "/home/dev/proj"
    assert accepted["handoff"] == {"delta": "two files", "priorFindings": ["F1"]}
    assert accepted["refs"] == [{"kind": "file", "id": "src/a.ts", "note": "read"}], (
        "refs are normalized on the way in, so the cap cannot be side-stepped by writing them"
    )
    assert result["stored"] == "x"


def test_the_budget_measures_what_a_task_retains_not_known_fields(tmp_path: Path) -> None:
    """Measuring named fields only is how an unmeasured field gets stored: a
    context the task store cannot read measured zero bytes and blew through a 64 KiB
    ceiling. The measurement has to cover the retained value itself."""
    result = run(
        '''
        const spelled = { description: "short", context: { notes: ["x".repeat(200000)] } };
        const known = { description: "short", context: { handoff: { delta: "x".repeat(200000) } } };
        console.log(JSON.stringify({
          spelledBytes: task.taskContextBytes(spelled),
          knownBytes: task.taskContextBytes(known),
          spelledWithin: task.withinContextBudget(spelled),
          knownWithin: task.withinContextBudget(known),
          emptyContext: task.taskContextBytes({ description: "only a description" }),
        }));
        ''',
        tmp_path,
    )
    assert int(str(result["spelledBytes"])) > 190000, (
        "a field the task store does not read still occupies the Task's budget"
    )
    assert int(str(result["knownBytes"])) > 190000
    assert result["spelledWithin"] is False, "an unmeasured field must not pass as within budget"
    assert result["knownWithin"] is False
    assert int(str(result["emptyContext"])) == len("only a description")


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


def test_refs_written_through_the_store_are_capped_too(tmp_path: Path) -> None:
    """`normalizeContextRefs` is not opt-in. A caller writing through the tool
    must not be able to accumulate references past the cap the feature names."""
    refs = [{"kind": "report", "id": f"r{i}"} for i in range(90)]
    result = run(
        f'''
        task.createTask({{ id: "w1", subject: "bounded refs" }});
        const written = task.updateTask("w1", {{
          context: {{ refs: [{{ kind: "work", id: "a" }}, {{ kind: "work", id: "a" }}, ...{json.dumps(refs)}] }},
        }});
        const stored = task.getTask("w1").context?.refs ?? [];
        console.log(JSON.stringify({{
          ok: written.ok,
          count: stored.length,
          cap: task.MAX_CONTEXT_REFS,
          duplicates: stored.filter((ref) => ref.id === "a").length,
        }}));
        ''',
        tmp_path,
    )
    assert result["ok"] is True
    assert int(str(result["count"])) == int(str(result["cap"])), "the cap applies to what a caller stores"
    assert result["duplicates"] == 1


def test_a_work_item_records_a_workspace_path_and_never_a_session_id(tmp_path: Path) -> None:
    """The boundary that keeps @fradser/pi-tasks free of the process layer."""
    result = run(
        '''
        // Not named `task`: that shadows the imported namespace binding.
        const created = task.createTask({ id: "w1", subject: "workspace context" });
        const written = task.setTaskContext("w1", {
          workspacePath: "/home/dev/.pi/agent/workspaces/reviewer/proj-abc",
        });
        const item = task.getTask("w1");
        console.log(JSON.stringify({ created: created.ok, written: written.ok, serialized: JSON.stringify(item) }));
        ''',
        tmp_path,
    )
    assert result["created"] is True
    assert result["written"] is True
    serialized = str(result["serialized"])
    assert json.loads(serialized)["context"]["workspacePath"] == "/home/dev/.pi/agent/workspaces/reviewer/proj-abc"
    for forbidden in ("sessionId", "sessionFile", "sessionRef", "session-id"):
        assert forbidden not in serialized, forbidden
    source = (PACKAGE / "src" / "context.ts").read_text(encoding="utf-8")
    assert "sessionId" not in source and "SessionManager" not in source, (
        "@fradser/pi-tasks must not resolve or store session handles; Pi owns session storage"
    )
