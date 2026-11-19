"""Lifecycle evidence contract: features/lifecycle-evidence.feature."""
from __future__ import annotations

import json

from task_helpers import PACKAGE, run_node

ENTRY = json.dumps((PACKAGE / "index.ts").as_uri())


def run(script: str) -> dict[str, object]:
    return run_node(f'import * as task from {ENTRY};\n' + script)


def test_recovery_take_budget_and_blocked_delivery_through_public_tools() -> None:
    result = run("""
      const tools = new Map();
      task.default({registerTool(t) {tools.set(t.name,t)}, on() {}, events:{emit(){}}});
      const call = async params => (await tools.get("update_task").execute("case",params,undefined,undefined,{})).details;
      task.createTask({id:"recover",subject:"Recover",createdBy:"main"});
      task.completeTaskWithOutcome("recover","main","failed","first failure");
      const before = JSON.stringify(task.getTask("recover"));
      const oversized = await call({id:"recover",status:"in_progress",reason:"é".repeat(40000)});
      const unchanged = before === JSON.stringify(task.getTask("recover"));
      const bypass = await call({id:"recover",status:"completed",outcome:"success",result:"done"});
      const safe = await call({id:"recover",status:"in_progress",reason:"Repaired the blocker"});
      const done = await call({id:"recover",status:"completed",outcome:"success",result:"done"});
      task.createTask({id:"operational",subject:"Operational"});
      task.blockTask("operational","main","Service unavailable");
      const operational = await call({id:"operational",status:"completed",outcome:"success",result:"done"});
      task.createTask({id:"tight",subject:"Tight"});
      task.setTaskContext("tight",{budgetBytes:100});
      task.blockTask("tight","main","b".repeat(40));
      const tightBefore = JSON.stringify(task.getTask("tight"));
      const tight = task.takeTask("tight","main",{reason:"r".repeat(40)});
      const tightUnchanged = tightBefore === JSON.stringify(task.getTask("tight"));
      console.log(JSON.stringify({oversized,unchanged,bypass,safe,done,operational,tight,tightUnchanged,
        final:task.getTask("recover"),completable:task.completableTasks().map(t=>t.id)}));
    """)
    assert result["oversized"]["ok"] is False
    assert result["unchanged"] is True
    assert result["bypass"]["ok"] is False
    assert result["safe"]["ok"] is True
    assert result["done"]["ok"] is True
    assert result["operational"]["ok"] is False
    assert "operational" in result["completable"], "The library retains explicit fallback acceptance."
    assert result["tight"]["refusal"] == "budget-exceeded"
    assert result["tightUnchanged"] is True
    assert result["final"]["failureEvidence"] == "first failure"


def test_successive_failures_blockers_stop_and_budget_preserve_evidence() -> None:
    result = run("""
      task.createTask({id:"history",subject:"History"});
      task.takeTask("history","main");
      task.completeTaskWithOutcome("history","main","failed","failure one\n");
      task.takeTask("history","main",{reason:"Repair one"});
      task.completeTaskWithOutcome("history","main","failed","failure two");
      task.takeTask("history","main",{reason:"Repair two"});
      task.blockTask("history","main","operational blocker");
      task.takeTask("history","main",{reason:"Service repaired"});
      task.failTasksHeldBy("main","runtime stopped");
      const retained = structuredClone(task.getTask("history"));
      task.takeTask("history","main",{reason:"Runtime recovered"});
      task.blockTask("history","main","failure two");
      const deduplicated = task.getTask("history").evidenceHistory;
      task.takeTask("history","main",{reason:"Duplicate reviewed"});
      task.blockTask("history","main","runtime stopped");
      const before = JSON.stringify(task.getTask("history"));
      const oversized = task.blockTask("history","main","x".repeat(70000));
      const unchanged = before === JSON.stringify(task.getTask("history"));
      task.loadTasks({legacy:{id:"legacy",subject:"Legacy",status:"in_progress",claimedBy:"old",
        dependsOn:[],resources:[],createdAt:1,updatedAt:1,result:"old result",failureEvidence:"old failure",
        blockedReason:"old blocker",description:"x".repeat(70000)}});
      // A coordinated runtime can hold legacy content that predates budget checks.
      task.getTask("legacy").status="in_progress";
      task.getTask("legacy").claimedBy="old";
      task.failTasksHeldBy("old","cleanup");
      console.log(JSON.stringify({retained,deduplicated,oversized,unchanged,legacy:task.getTask("legacy")}));
    """.replace('"failure one\n"', '"failure one\\n"'))
    assert result["retained"]["evidenceHistory"] == ["failure one\n", "failure two", "operational blocker"]
    assert result["retained"]["failureEvidence"] == "runtime stopped"
    assert result["deduplicated"] == ["failure one\n", "failure two", "operational blocker", "runtime stopped"]
    assert result["oversized"]["refusal"] == "budget-exceeded"
    assert result["unchanged"] is True
    assert result["legacy"]["status"] == "blocked"
    assert "claimedBy" not in result["legacy"]
    assert "old failure" in result["legacy"]["evidenceHistory"]
    assert "old blocker" in result["legacy"]["evidenceHistory"]
    assert "old result" in result["legacy"]["evidenceHistory"]


def test_reopened_verified_result_survives_failure_through_public_tools() -> None:
    result = run(r"""
      const tools = new Map();
      task.default({registerTool(t){tools.set(t.name,t)},on(){},events:{emit(){}}});
      const call = async (name,params) => (await tools.get(name).execute("case",params,undefined,undefined,{})).details;
      const created = await call("create_task",{subject:"Repeat verification"});
      const id = created.id;
      const outcomes=[];
      for (const patch of [
        {status:"in_progress"},
        {status:"completed",outcome:"success",result:" verified local result\n"},
        {status:"pending"},
        {status:"in_progress"},
        {status:"completed",outcome:"failed",result:"remote failed"},
      ]) outcomes.push((await call("update_task",{id,...patch})).ok);
      const read = await call("get_task",{id});
      console.log(JSON.stringify({outcomes,task:read.task}));
    """)
    assert result["outcomes"] == [True] * 5
    assert result["task"]["result"] == "remote failed"
    assert result["task"]["evidenceHistory"] == [" verified local result\n"]


def test_outstanding_replaces_and_clears_while_findings_accumulate() -> None:
    result = run("""
      task.createTask({id:"brief",subject:"Brief"});
      task.setTaskContext("brief",{handoff:{priorFindings:["finding one"],outstanding:["old"]}});
      task.updateTask("brief",{context:{handoff:{priorFindings:["finding two"],outstanding:["new"]}}});
      const replaced = structuredClone(task.getTask("brief").context.handoff);
      const cleared = task.setTaskContext("brief",{handoff:{outstanding:[]}});
      console.log(JSON.stringify({replaced,cleared:cleared.ok,final:task.getTask("brief").context.handoff}));
    """)
    assert result["replaced"]["outstanding"] == ["new"]
    assert result["cleared"] is True
    assert result["final"]["outstanding"] == []
    assert result["final"]["priorFindings"] == ["finding one", "finding two"]


def test_malformed_present_files_do_not_attach_writer_and_valid_files_survive() -> None:
    result = run("""
      const fs = await import("node:fs");
      const path = await import("node:path");
      const hooks = new Map();
      task.default({registerTool(){},on(name,fn){if (!hooks.has(name)) hooks.set(name,fn)},events:{emit(){}}});
      const ctx={cwd:process.cwd(),sessionManager:{getSessionFile:()=>"fixture-session"}};
      const file=task.tasksFilePath("fixture-session",ctx.cwd);
      fs.mkdirSync(path.dirname(file),{recursive:true});
      const observations=[];
      for (const value of [{runtimeVersion:2},null,[],{runtimeVersion:2,tasks:[]},{runtimeVersion:2,tasks:{bad:null}}]) {
        const raw=JSON.stringify(value);fs.writeFileSync(file,raw);
        let error;try {task.readTasksFile(file)} catch(e) {error=e.message}
        await hooks.get("session_start")({},ctx);
        task.createTask({subject:"Must not overwrite"});
        observations.push({error:error??null,notice:task.storeNotice(),unchanged:fs.readFileSync(file,"utf8")===raw});
      }
      task.writeTasksFile(file,{done:{id:"done",subject:"Done",status:"completed",dependsOn:[],resources:[],
        result:"valid result",completionVerdict:"pass",createdAt:1,updatedAt:1,completedAt:2},
        legacy:{id:"legacy",subject:"Legacy",status:"recovery_hold",result:"legacy failure",dependsOn:[],resources:[],createdAt:1,updatedAt:1}});
      await hooks.get("session_start")({},ctx);
      const histories=[];
      for (const history of ["invalid", [" exact body\\n", " exact body\\n", null, ""], ["valid body"]]) {
        task.loadTasks({history:{id:"history",subject:"History",status:"blocked",dependsOn:[],resources:[],
          createdAt:1,updatedAt:1,evidenceHistory:history}});
        const restored=structuredClone(task.getTask("history"));
        const taken=task.takeTask("history","main",{reason:"Inspected restored evidence"});
        histories.push({restored,taken:taken.ok});
      }
      console.log(JSON.stringify({observations,histories,done:task.getTask("done"),legacy:task.getTask("legacy")}));
    """)
    for observation in result["observations"]:
        assert observation["error"]
        assert observation["notice"]
        assert observation["unchanged"] is True
    assert result["done"]["status"] == "completed"
    assert result["done"]["result"] == "valid result"
    assert result["done"]["completedAt"] == 2
    assert result["legacy"]["failureEvidence"] == "legacy failure"
    assert "evidenceHistory" not in result["histories"][0]["restored"]
    assert result["histories"][1]["restored"]["evidenceHistory"] == [" exact body\n"]
    assert result["histories"][2]["restored"]["evidenceHistory"] == ["valid body"]
    assert all(item["taken"] for item in result["histories"])
