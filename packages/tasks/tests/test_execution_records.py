"""Execution history and actionable task separation through the shipped hook."""
from pathlib import Path

from test_task_stop_check import run


def test_execution_history_is_retained_without_continuation(tmp_path: Path) -> None:
    result = run(
        """
        task.createTask({ id: "run", subject: "Review a candidate", recordKind: "execution" });
        task.takeTask("run", "main");
        task.completeTaskWithOutcome("run", "main", "failed", "Provider disconnected");
        const alone = await settle();
        task.createTask({ id: "explicit", subject: "Implement the change" });
        const mixed = await settle();
        const full = await task.executeTaskGet({id:"run"});
        console.log(JSON.stringify({alone:alone??null,content:mixed.entries[0].content,
          count:mixed.entries[0].details.remaining, evidence:full.details.task.result,
          status:full.details.task.status}));
        """,
        tmp_path,
    )
    assert result["alone"] is None
    assert result["count"] == 1
    assert "id=explicit" in result["content"]
    assert "id=run" not in result["content"]
    assert result["evidence"] == "Provider disconnected"
    assert result["status"] == "recovery_hold"


def test_restored_generated_execution_does_not_hide_explicit_recovery(tmp_path: Path) -> None:
    result = run(
        """
        const generated="work:83bf154f-e05b-4919-b26d-51f150c5a58c";
        const base={dependsOn:[],resources:[],createdAt:1,updatedAt:1,status:"pending",recoveryRequired:true};
        task.loadTasks({[generated]:{...base,id:generated,subject:"Earlier review",result:"Interrupted"},
          explicit:{...base,id:"explicit",subject:"User task"}});
        const receipt=await settle();
        console.log(JSON.stringify({count:receipt.entries[0].details.remaining,
          content:receipt.entries[0].content,kind:task.getTask(generated).recordKind,
          evidence:task.getTask(generated).result,hold:task.getTask(generated).status === "recovery_hold",
          status:receipt.entries[0].details.status}));
        """,
        tmp_path,
    )
    assert result["count"] == 1
    assert result["kind"] == "execution"
    assert result["evidence"] == "Interrupted"
    assert result["hold"] is True
    assert result["status"] == "continue", "the blocked snapshot continues once; the blocker is named in its reason"
    assert "id=work:" not in result["content"]


def test_invalid_present_classification_is_repaired_not_inferred(tmp_path: Path) -> None:
    result = run(
        """
        const observations=[];
        for (const value of ["executon", {kind:"execution"}, null]) {
          task.clearTasks();
          task.setStoreNotice(undefined);
          const id="work:83bf154f-e05b-4919-b26d-51f150c5a58c";
          task.loadTasks({[id]:{id,subject:"Saved work",recordKind:value,dependsOn:[],resources:[],
            status:"pending",createdAt:1,updatedAt:1,result:"Preserved evidence"}});
          const full=await task.executeTaskGet({id});
          observations.push({kind:full.details.task.recordKind,hold:task.getTask(id).status === "recovery_hold",
            evidence:full.details.task.result,notice:task.storeNotice(),claimable:task.claimableTasks().length});
        }
        console.log(JSON.stringify({observations}));
        """,
        tmp_path,
    )
    for observed in result["observations"]:
        assert observed["kind"] == "task"
        assert observed["hold"] is True
        assert observed["evidence"] == "Preserved evidence"
        assert "recordKind" in observed["notice"]
        assert observed["claimable"] == 0
