"""Execution classification and evidence remain available through explicit reads."""
from pathlib import Path
from task_helpers import run_node

def run(script: str, tmp_path: Path):
    return run_node("import * as task from './index.ts';" + script, env_overrides={"PI_CODING_AGENT_DIR": str(tmp_path)})

def test_execution_history_is_retained_without_continuation(tmp_path: Path):
    result = run('''
      task.createTask({id:"run",subject:"Review",recordKind:"execution"});
      task.takeTask("run","main");
      task.completeTaskWithOutcome("run","main","failed","Provider disconnected");
      task.createTask({id:"explicit",subject:"Implement"});
      const full=await task.executeTaskGet({id:"run"});
      console.log(JSON.stringify({evidence:full.details.task.result,status:full.details.task.status}));
    ''',tmp_path)
    assert result["evidence"] == "Provider disconnected"
    assert result["status"] == "blocked"

def test_restored_execution_and_explicit_recovery_remain_readable(tmp_path: Path):
    result = run('''
      const generated="work:83bf154f-e05b-4919-b26d-51f150c5a58c";
      const base={dependsOn:[],resources:[],createdAt:1,updatedAt:1,status:"pending",recoveryRequired:true};
      task.loadTasks({[generated]:{...base,id:generated,subject:"Earlier review",result:"Interrupted"},
        explicit:{...base,id:"explicit",subject:"User task"}});
      console.log(JSON.stringify({kind:task.getTask(generated).recordKind,
        evidence:task.getTask(generated).result,status:task.getTask("explicit").status}));
    ''',tmp_path)
    assert result == {"kind":"execution","evidence":"Interrupted","status":"blocked"}

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
          observations.push({kind:full.details.task.recordKind,hold:task.getTask(id).status === "blocked",
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
