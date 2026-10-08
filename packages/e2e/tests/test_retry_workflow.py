from test_run_provenance import RUN_PREAMBLE
from test_e2e_package import PREAMBLE, SRC, run_typescript

RUN_PREAMBLE += r'''
const passed = gate => gate.isAccepted();
'''


def test_failed_run_can_be_repaired_and_retried_in_the_same_turn() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        const gate = new E2EGate();
        await writeFile(path.join(cwd, ".e2e/runner.json"), JSON.stringify({executable: process.execPath, args: [fixture, "unmet"], adapterFiles: [fixture]}));
        await gate.beginTurn("verify test.feature", cwd);
        gate.recordToolResult("write", {path: "test.feature"}, false, cwd);
        const attempt = async mode => {
          const observer = gate.verificationObserver();
          return executeE2EVerify({feature: "test.feature", offline: true, runner: {executable: process.execPath, args: [fixture, mode]}}, observer.onVerdict, {cwd, validateRunner: observer.validateRunner});
        };
        const failed = await attempt("unmet");
        pending(gate);
        pending(gate);
        await writeFile(path.join(cwd, ".e2e/runner.json"), JSON.stringify({executable: process.execPath, args: [fixture, "pass"], adapterFiles: [fixture]}));
        const retries = [];
        for (let i=0;i<4;i++) retries.push((await attempt("pass")).details?.status);
        await gate.refreshFeatureChanges(cwd);
        out({first: failed.details?.status, retries, pending: pending(gate), passed:passed(gate)});
      } finally {await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result == {"first": "not_fulfilled", "retries": ["fulfilled"] * 4, "pending": False, "passed":True}


def test_authorized_adapter_setup_in_current_turn_can_be_verified() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        await rm(path.join(cwd, ".e2e/runner.json"));
        const gate = new E2EGate(); await gate.beginTurn("verify test.feature", cwd);
        await writeFile(path.join(cwd, ".e2e/runner.json"), JSON.stringify({executable: process.execPath, args: [fixture,"pass"], adapterFiles:[fixture]}));
        const observer=gate.verificationObserver();
        const result=await executeE2EVerify({feature:"test.feature",offline:true,runner:{executable:process.execPath,args:[fixture,"pass"]}},observer.onVerdict,{cwd,validateRunner:observer.validateRunner});
        out({status:result.details?.status,verified:result.details?.verifiedRun,pending:pending(gate),passed:passed(gate)});
      } finally {await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result == {"status": "fulfilled", "verified": True, "pending": False,"passed":True}


def test_aborted_settlement_does_not_emit_generic_acceptance_warning() -> None:
    result = run_typescript(PREAMBLE + r'''
      import {registerE2EHarness} from "''' + (SRC / "harness.ts").as_uri() + r'''";
      const hooks = new Map(); const gate = new E2EGate();
      registerE2EHarness({on(name,fn){hooks.set(name,fn);},registerMessageRenderer(){}} as never,gate);
      gate.recordToolResult("write",{path:"changed.feature"});
      const messages=[];
      await hooks.get("agent_before_settle")({outcome:"aborted",context:{pendingMessages:[]}},{});
      await hooks.get("agent_settled")({type:"agent_settled"},{ui:{notify(text){messages.push(text);}}});
      out({messages});
    ''')
    assert result == {"messages": []}


def test_default_error_and_report_keep_their_full_tails() -> None:
    result = run_typescript(PREAMBLE + r'''
      import {registerE2ETools} from "''' + (SRC / "tool.ts").as_uri() + r'''";
      let tool;registerE2ETools({registerTool(value){tool=value;}} as never);
      const theme={fg:(_c,t)=>t,bg:(_c,t)=>t,bold:t=>t};
      const report=Array.from({length:130},(_,i)=>`Clause ${i}`).join("\n")+"\nREPORT_TAIL";
      const error="Diagnostic detail ".repeat(100)+"ERROR_TAIL";
      const output=[{content:[{type:"text",text:report}],details:{status:"fulfilled",scenario:"Scenario ".repeat(50)+"SCENARIO_TAIL"}},{content:[{type:"text",text:error}],details:{status:"error",error},isError:true}];
      const text=output.map(r=>tool.renderResult(r,{},theme,{isError:!!r.isError}).render(40).join("\n"));
      out({report:text[0].includes("REPORT_TAIL"),scenario:text[0].includes("SCENARIO_TAIL"),error:text[1].includes("ERROR_TAIL"),noExpand:text.every(t=>!t.includes("to expand"))});
    ''')
    assert result == {"report": True, "scenario": True, "error": True, "noExpand": True}


def test_requested_feature_waits_for_all_scenarios_and_stale_pass_can_be_rerun() -> None:
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        await writeFile(path.join(cwd,"test.feature"),source+"Scenario: Also works\nThen value is true\n");
        const gate=new E2EGate();await gate.beginTurn("Run e2e ./test.feature",cwd);
        const verify=async scenario=>{
          const observer=gate.verificationObserver();
          return executeE2EVerify({feature:"test.feature",scenario,offline:true,runner:{executable:process.execPath,args:[fixture,"pass"]}},observer.onVerdict,{cwd,validateRunner:observer.validateRunner});
        };
        await verify("Works");const partial=pending(gate)&&!passed(gate);
        await verify("Also works");const complete=!pending(gate)&&passed(gate);
        const adapter=path.join(cwd,"adapter.mjs");await writeFile(adapter,`await import(${JSON.stringify("file://"+fixture)});`);
        await writeFile(path.join(cwd,".e2e/runner.json"),JSON.stringify({executable:process.execPath,args:[adapter],adapterFiles:[adapter,fixture]}));
        await gate.refreshFeatureChanges(cwd);const stale=pending(gate);
        await writeFile(path.join(cwd,".e2e/runner.json"),JSON.stringify({executable:process.execPath,args:[fixture,"pass"],adapterFiles:[fixture]}));
        await verify("Works");await verify("Also works");await gate.refreshFeatureChanges(cwd);
        out({partial,complete,stale,repaired:!pending(gate)&&passed(gate)});
      } finally {await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result == {"partial": True, "complete": True, "stale": True, "repaired": True}


def test_read_only_request_is_not_overwritten_by_turn_preparation() -> None:
    result=run_typescript(RUN_PREAMBLE+r'''
      try {
        const gate=new E2EGate();
        const prompt="Do not run e2e ./test.feature; only review it";
        gate.recordUserPrompt(prompt,cwd);await gate.beginTurn(prompt,cwd);
        out({pending:pending(gate)});
      } finally {await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result == {"pending":False}


def test_generic_acceptance_request_keeps_partial_feature_pending() -> None:
    result=run_typescript(RUN_PREAMBLE+r'''
      try {
        await writeFile(path.join(cwd,"test.feature"),source+"Scenario: Also works\nThen value is true\n");
        const gate=new E2EGate();await gate.beginTurn("Run e2e tests",cwd);
        const observer=gate.verificationObserver();
        await executeE2EVerify({feature:"test.feature",scenario:"Works",offline:true,runner:{executable:process.execPath,args:[fixture,"pass"]}},observer.onVerdict,{cwd,validateRunner:observer.validateRunner});
        const checkpoint=gate.checkBeforeSettle(event as never,{cwd} as never);
        out({pending:checkpoint?.continue??false,namesFeature:JSON.stringify(checkpoint?.entries??[]).includes("test.feature"),passed:passed(gate)});
      } finally {await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result=={"pending":True,"namesFeature":True,"passed":False}


def test_later_runner_error_with_same_adapter_withdraws_prior_pass() -> None:
    result=run_typescript(RUN_PREAMBLE+r'''
      try {
        const adapter=path.join(cwd,"adapter.mjs");
        await writeFile(adapter,`import {existsSync} from 'node:fs'; if(existsSync('crash')) process.exit(1); await import(${JSON.stringify("file://"+fixture)});`);
        const runner={executable:process.execPath,args:[adapter]};
        await writeFile(path.join(cwd,".e2e/runner.json"),JSON.stringify({...runner,adapterFiles:[adapter,fixture]}));
        const gate=new E2EGate();await gate.beginTurn("Run e2e test.feature",cwd);
        const verify=async()=>{
          const observer=gate.verificationObserver();
          return executeE2EVerify({feature:"test.feature",offline:true,runner},observer.onVerdict,{cwd,...observer});
        };
        await verify();const initial=passed(gate);
        await writeFile(path.join(cwd,"crash"),"yes");const failed=await verify();
        await gate.refreshFeatureChanges(cwd);const errorPending=pending(gate);const falselyPassed=passed(gate);
        await rm(path.join(cwd,"crash"));await verify();await gate.refreshFeatureChanges(cwd);
        out({initial,error:failed.details?.status,errorPending,falselyPassed,recovered:passed(gate)});
      } finally {await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result=={"initial":True,"error":"error","errorPending":True,"falselyPassed":False,"recovered":True}


def test_stale_error_callback_and_corrected_scenario_name_do_not_poison_retries() -> None:
    result=run_typescript(RUN_PREAMBLE+r'''
      try {
        const gate=new E2EGate();await gate.beginTurn("Run e2e test.feature",cwd);
        const stale=gate.verificationObserver();await gate.beginTurn("Only review the source",cwd);
        await stale.onError("old failure","test.feature","Works",cwd);const clean=!pending(gate);
        await gate.beginTurn("Run e2e test.feature",cwd);
        const verify=async scenario=>{const observer=gate.verificationObserver();return executeE2EVerify({feature:"test.feature",scenario,offline:true,runner:{executable:process.execPath,args:[fixture,"pass"]}},observer.onVerdict,{cwd,...observer});};
        await verify("Typo");const rejected=pending(gate);
        const result=await verify("Works");await gate.refreshFeatureChanges(cwd);
        out({clean,rejected,recovered:passed(gate),status:result.details?.status});
      } finally {await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result=={"clean":True,"rejected":True,"recovered":True,"status":"fulfilled"}


def test_cancellation_signal_during_snapshot_skips_checkpoint_and_notification() -> None:
    result=run_typescript(PREAMBLE+r'''
      import {registerE2EHarness} from "''' + (SRC / "harness.ts").as_uri() + r'''";
      const hooks=new Map();const gate=new E2EGate();const controller=new AbortController();const messages=[];
      gate.recordToolResult("write",{path:"test.feature"});
      gate.refreshFeatureChanges=async()=>{controller.abort();};
      registerE2EHarness({on(name,fn){hooks.set(name,fn);},registerMessageRenderer(){}} as never,gate);
      const ctx={signal:controller.signal,ui:{notify(text){messages.push(text);}}};
      const checkpoint=await hooks.get("agent_before_settle")({outcome:"completed",context:{pendingMessages:[]}},ctx);
      await hooks.get("agent_settled")({},ctx);
      out({continues:checkpoint?.continue??false,messages});
    ''')
    assert result=={"continues":False,"messages":[]}


def test_checkpoint_uses_shared_full_renderer_and_actual_allowance() -> None:
    result=run_typescript(PREAMBLE+r'''
      import {registerE2EHarness} from "''' + (SRC / "harness.ts").as_uri() + r'''";
      const gate=new E2EGate();const renderers=new Map();
      registerE2EHarness({on(){},registerMessageRenderer(name,fn){renderers.set(name,fn);}} as never,gate);
      gate.recordUserPrompt("Run e2e tests");
      const checkpoint=gate.checkBeforeSettle({outcome:"completed",entries:[],context:{pendingMessages:[]}} as never,{} as never);
      const message=checkpoint.entries[0];
      const theme={fg:(_c,t)=>t,bg:(_c,t)=>t,bold:t=>t};
      const text=renderers.get(message.customType)({...message,details:{...message.details,failures:[{scenario:"Long scenario ".repeat(30)+"SCENARIO_TAIL",status:"needs_review",reason:"Diagnostic ".repeat(30)+"REASON_TAIL"}]}},{},theme).render(40).join("\n");
      out({prefix:text.includes("[e2e] continue"),actualLimit:text.includes("1/1"),tails:text.includes("SCENARIO_TAIL")&&text.includes("REASON_TAIL"),noInstruction:text.includes("Never invent")===false,noExpand:text.includes("to expand")===false});
    ''')
    assert result=={"prefix":True,"actualLimit":True,"tails":True,"noInstruction":True,"noExpand":True}


def test_relevant_implementation_edit_withdraws_acceptance_but_unrelated_edit_does_not() -> None:
    result=run_typescript(RUN_PREAMBLE+r'''
      try {
        await mkdir(path.join(cwd,"packages/shop/features"),{recursive:true});
        const feature="packages/shop/features/test.feature";await writeFile(path.join(cwd,feature),source);
        const gate=new E2EGate();await gate.beginTurn(`Run e2e ${feature}`,cwd);
        const observer=gate.verificationObserver();
        await executeE2EVerify({feature,offline:true,runner:{executable:process.execPath,args:[fixture,"pass"]}},observer.onVerdict,{cwd,...observer});
        gate.recordToolResult("write",{path:"packages/other/src/app.ts"},false,cwd);
        const unrelated=!pending(gate);
        gate.recordToolResult("write",{path:"packages/shop/src/app.ts"},false,cwd);
        out({unrelated,relevantPending:pending(gate)});
      } finally {await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result=={"unrelated":True,"relevantPending":True}


def test_root_project_implementation_edits_withdraw_root_feature_acceptance() -> None:
    result=run_typescript(RUN_PREAMBLE+r'''
      try {
        await mkdir(path.join(cwd,"features"));const cases=[];
        for(const feature of ["features/test.feature","test.feature"]){
          await writeFile(path.join(cwd,feature),source);
          const gate=new E2EGate();await gate.beginTurn(`Run e2e ${feature}`,cwd);
          const observer=gate.verificationObserver();
          await executeE2EVerify({feature,offline:true,runner:{executable:process.execPath,args:[fixture,"pass"]}},observer.onVerdict,{cwd,...observer});
          gate.recordToolResult("write",{path:path.join(cwd,"../external/app.ts")},false,cwd);
          const outsideIsolated=!pending(gate);
          gate.recordToolResult("write",{path:"src/app.ts"},false,cwd);
          cases.push({feature,outsideIsolated,pending:pending(gate),passed:passed(gate)});
        }
        out({cases});
      }finally{await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result=={"cases":[{"feature":"features/test.feature","outsideIsolated":True,"pending":True,"passed":False},{"feature":"test.feature","outsideIsolated":True,"pending":True,"passed":False}]}


def test_partial_checkpoint_names_only_remaining_scenarios() -> None:
    result=run_typescript(RUN_PREAMBLE+r'''
      try {
        await writeFile(path.join(cwd,"test.feature"),source+"Scenario: Remaining scenario\nThen value is true\n");
        const gate=new E2EGate();await gate.beginTurn("Run e2e test.feature",cwd);
        await run("pass",{},gate);
        const checkpoint=gate.checkBeforeSettle(event as never,{cwd} as never);
        out({remaining:checkpoint?.entries[0]?.details?.remainingScenarios,content:String(checkpoint?.entries[0]?.content)});
      } finally {await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result["remaining"] == [{"feature": "test.feature", "scenarios": ["Remaining scenario"]}]
    assert "Remaining scenario" in result["content"]


def test_verified_completion_has_no_duplicate_success_notice_and_plain_status_keeps_pass() -> None:
    result=run_typescript(RUN_PREAMBLE+r'''
      try {
        const gate=new E2EGate();await gate.beginTurn("Run e2e test.feature",cwd);await run("pass",{},gate);
        const notices=[];gate.notifyOnSettled({ui:{notify(text){notices.push(text);}}} as never);
        gate.recordToolResult("bash",{command:"git status --short"},false,cwd);
        await gate.refreshFeatureChanges(cwd);
        out({notices,pending:pending(gate),accepted:gate.isAccepted()});
      } finally {await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result == {"notices": [], "pending": False, "accepted": True}


def test_needs_review_checkpoint_requests_evidence_before_implementation_repairs() -> None:
    result=run_typescript(PREAMBLE+r'''
      const gate=new E2EGate();gate.recordUserPrompt("Run e2e tests");
      await gate.recordVerdict({feature:"Test",scenario:"Missing",status:"needs_review",exitCode:2,
        reason:"no settled evidence for clause 1",clauses:[],unjudged:1,triage:[],policy:{clauseGate:.8,verdictGate:.6}});
      const checkpoint=gate.checkBeforeSettle({outcome:"completed",entries:[],context:{pendingMessages:[]}} as never,{} as never);
      out({content:String(checkpoint?.entries[0]?.content)});
    ''')
    assert "missing observations or clause checks" in result["content"]
    assert "Fix unmet criteria" not in result["content"]


def test_repeated_real_settlement_refresh_preserves_checkpoint_budget_without_progress() -> None:
    result=run_typescript(RUN_PREAMBLE+r'''
      import {registerE2EHarness} from "''' + (SRC / "harness.ts").as_uri() + r'''";
      try {
        const gate=new E2EGate();await gate.beginTurn("Run e2e test.feature",cwd);
        gate.recordToolResult("write",{path:"test.feature"},false,cwd);
        const hooks=new Map();registerE2EHarness({on(name,fn){hooks.set(name,fn);},registerMessageRenderer(){}} as never,gate);
        const ctx={cwd,hasPendingMessages:()=>false};
        const first=await hooks.get("agent_before_settle")(event,ctx);
        const repeated=await hooks.get("agent_before_settle")(event,ctx);
        gate.recordToolResult("edit",{path:"test.feature"},false,cwd);
        const progressed=await hooks.get("agent_before_settle")(event,ctx);
        out({first:!!first?.continue,repeated:!!repeated?.continue,progressed:!!progressed?.continue});
      } finally {await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result == {"first": True, "repeated": False, "progressed": True}
