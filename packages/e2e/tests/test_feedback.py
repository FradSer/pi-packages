from test_e2e_package import PREAMBLE, SRC, run_typescript
from test_run_provenance import RUN_PREAMBLE


def test_read_only_shell_activity_keeps_pass_but_actual_adapter_changes_reopen_it() -> None:
    # Given fresh acceptance, when shell inspection changes nothing, then it
    # stays accepted; when declared adapter inputs change, then it reopens.
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        const gate=new E2EGate();await gate.beginTurn("Run e2e test.feature",cwd);
        await run("pass",{},gate);
        const states=[];
        for(const command of ["ls","cat test.feature","rg value test.feature","git status --short"]){
          gate.recordToolResult("bash",{command},false,cwd);
          await gate.refreshFeatureChanges(cwd);states.push(gate.isAccepted());
        }
        await writeFile(path.join(cwd,".e2e/runner.json"),JSON.stringify({executable:process.execPath,args:[fixture,"unmet"],adapterFiles:[fixture]}));
        gate.recordToolResult("bash",{command:"node repair-adapter.mjs"},false,cwd);
        await gate.refreshFeatureChanges(cwd);
        out({states,changed:!gate.isAccepted()&&pending(gate)});
      }finally{await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result == {"states": [True] * 4, "changed": True}


def test_unknown_shell_edit_of_unlisted_application_input_revokes_acceptance() -> None:
    # Given a valid legacy adapter that imports an unlisted application file,
    # when unknown shell work edits it, then stale acceptance cannot survive.
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        await writeFile(path.join(cwd,"app.mjs"),"export const value=true;");
        await writeFile(path.join(cwd,"adapter.mjs"),'import {value} from "./app.mjs";import {writeFileSync} from "node:fs";writeFileSync(process.env.PI_E2E_EVIDENCE_PATH,JSON.stringify({run:{observations:{value}},checks:[{clause:1,path:"value",op:"equals",value:true}]}));');
        const runner={executable:process.execPath,args:["adapter.mjs"]};
        await writeFile(path.join(cwd,".e2e/runner.json"),JSON.stringify({...runner,adapterFiles:["adapter.mjs"]}));
        const gate=new E2EGate();await gate.beginTurn("Run e2e test.feature",cwd);
        const verify=async()=>{const observer=gate.verificationObserver();return executeE2EVerify({feature:"test.feature",runner,offline:true},observer.onVerdict,{cwd,...observer});};
        await verify();const before=gate.isAccepted();
        await writeFile(path.join(cwd,"app.mjs"),"export const value=false;");
        gate.recordToolResult("bash",{command:"python repair.py"},false,cwd);
        await gate.refreshFeatureChanges(cwd);
        const after=gate.isAccepted(),checkpoint=pending(gate);
        const failure=await verify();
        out({before,after,checkpoint,rerun:failure.details.status});
      }finally{await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result == {"before": True, "after": False, "checkpoint": True, "rerun": "not_fulfilled"}


def test_failed_rerun_withdraws_previous_feature_progress() -> None:
    # Given a passed scenario, when its fresh rerun fails, then the feedback
    # no longer counts that scenario as accepted or omits its remaining work.
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        const gate=new E2EGate();await gate.beginTurn("Run e2e test.feature",cwd);
        const verify=async mode=>{
          await writeFile(path.join(cwd,".e2e/runner.json"),JSON.stringify({executable:process.execPath,args:[fixture,mode],adapterFiles:[fixture]}));
          const observer=gate.verificationObserver();
          return executeE2EVerify({feature:"test.feature",runner:{executable:process.execPath,args:[fixture,mode]},offline:true},observer.onVerdict,{cwd,...observer});
        };
        await verify("pass");const result=await verify("unmet");
        out({lines:result.details.feedback.lines,accepted:gate.isAccepted()});
      }finally{await rm(cwd,{recursive:true,force:true});}
    ''')
    assert "Feature acceptance: 0/1 scenarios passed" in result["lines"]
    assert "Remaining: Works" in result["lines"]
    assert not result["accepted"]


def test_provider_blocker_is_visible_and_caller_pass_is_not_verified_success() -> None:
    # Given missing provider credentials or supplied evidence, when rendered,
    # then recovery and evidence origin precede the clause breakdown.
    result = run_typescript(RUN_PREAMBLE + r'''
      import {registerE2ETools} from "''' + (SRC / "tool.ts").as_uri() + r'''";
      try {
        delete process.env.TYPESAFE_API_KEY;
        let tool;registerE2ETools({registerTool(value){tool=value;}} as never);
        const theme={fg:(_c,t)=>t,bg:(_c,t)=>t,bold:t=>t};
        const gate=new E2EGate();await gate.beginTurn("Run e2e test.feature",cwd);
        const missing=await executeE2EVerify({feature:"test.feature",evidence:{run:{observations:{}}}},gate.verdictListener(),{cwd});
        const notices=[];gate.notifyOnSettled({cwd,ui:{notify(text){notices.push(text);}}} as never);
        const supplied=await executeE2EVerify({feature:"test.feature",offline:true,evidence:{run:{observations:{value:true}},checks:[{clause:1,path:"value",op:"equals",value:true}]}},undefined,{cwd});
        const text=r=>tool.renderResult(r,{},theme,{isError:r.isError}).render(80).map(line=>line.trim()).filter(Boolean);
        const m=text(missing),s=text(supplied);
        out({missingHeader:m[0],suppliedHeader:s[0],blocker:m.join("\n").includes("NO_API_KEY"),waitingBlocker:notices[0].includes("NO_API_KEY"),visibleContent:missing.content[0].text.includes("NO_API_KEY"),origin:s.findIndex(line=>line.includes("caller-supplied")),clause:s.findIndex(line=>line.includes("PASS")),status:supplied.details.status});
      }finally{await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result["missingHeader"] == "[e2e] needs review"
    assert result["suppliedHeader"] == "[e2e] needs review"
    assert result["blocker"] and result["visibleContent"] and result["waitingBlocker"]
    assert 0 < result["origin"] < result["clause"]
    assert result["status"] == "fulfilled"


def test_native_tool_updates_phases_and_reports_whole_feature_progress() -> None:
    # Given two scenarios, when each executes, then updates are running and
    # the result distinguishes the scenario pass from whole-feature acceptance.
    result = run_typescript(RUN_PREAMBLE + r'''
      import {registerE2ETools} from "''' + (SRC / "tool.ts").as_uri() + r'''";
      try {
        await writeFile(path.join(cwd,"test.feature"),source+"Scenario: Remaining\nThen value is true\n");
        const gate=new E2EGate();await gate.beginTurn("Run e2e test.feature",cwd);
        let tool;registerE2ETools({registerTool(value){tool=value;}} as never,undefined,()=>gate.verificationObserver());
        const theme={fg:(_c,t)=>t,bg:(_c,t)=>t,bold:t=>t};
        const updates=[];
        const first=await tool.execute("a",{feature:"test.feature",offline:true,runner:{executable:process.execPath,args:[fixture,"pass"]}},undefined,r=>updates.push(r),{cwd});
        const text=r=>tool.renderResult(r,{},theme,{isError:r.isError}).render(80).map(line=>line.trim()).filter(Boolean);
        const lines=text(first);
        const second=await tool.execute("b",{feature:"test.feature",scenario:"Remaining",offline:true,runner:{executable:process.execPath,args:[fixture,"pass"]}},undefined,()=>{},{cwd});
        out({header:lines[0],remaining:lines.join("\n").includes("Remaining: Remaining"),partial:lines.join("\n").includes("1/2"),complete:text(second).join("\n").includes("2/2"),updates:updates.map(r=>text(r)[0]),phases:updates.map(r=>r.content[0].text),accepted:gate.isAccepted(),markdown:lines.some(line=>line.includes("**")||line.startsWith("|"))});
      }finally{await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result["header"] == "[e2e] passed"
    assert result["remaining"] and result["partial"] and result["complete"]
    assert len(result["updates"]) >= 3
    assert set(result["updates"]) == {"[e2e] running"}
    assert any("Running project tests" in phase for phase in result["phases"])
    assert result["accepted"] and not result["markdown"]


def test_waiting_feedback_names_remaining_work_and_recovery() -> None:
    # Given incomplete acceptance, when settlement cannot continue, then the
    # bare waiting header is followed by concrete work and a next actor/action.
    result = run_typescript(RUN_PREAMBLE + r'''
      try {
        await writeFile(path.join(cwd,"test.feature"),source+"Scenario: Remaining\nThen value is true\n");
        const gate=new E2EGate();await gate.beginTurn("Run e2e test.feature",cwd);await run("pass",{},gate);
        const notices=[];gate.notifyOnSettled({cwd,ui:{notify(text){notices.push(text);}}} as never);
        out({text:notices[0]});
      }finally{await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result["text"].splitlines()[0] == "[e2e] waiting"
    assert "Remaining" in result["text"] and "test.feature" in result["text"]
    assert "Next:" in result["text"]


def test_slash_command_uses_the_same_feedback_renderer_without_starting_a_turn() -> None:
    # Given caller-supplied evidence, when /e2e is used, then its durable
    # feedback has the same bare header and never starts an agent turn.
    result = run_typescript(RUN_PREAMBLE + r'''
      import extension from "''' + (SRC.parent / "extensions/index.ts").as_uri() + r'''";
      try {
        const commands=new Map(),renderers=new Map(),messages=[];
        extension({on(){},registerTool(){},registerCommand(name,value){commands.set(name,value);},registerMessageRenderer(name,fn){renderers.set(name,fn);},sendMessage(message,options){messages.push({message,options});}} as never);
        await writeFile(path.join(cwd,"evidence.json"),JSON.stringify({run:{observations:{value:true}},checks:[{clause:1,path:"value",op:"equals",value:true}]}));
        await commands.get("e2e").handler("test.feature evidence.json",{cwd,ui:{notify(){throw new Error("unexpected notification");}}});
        const final=messages.at(-1),theme={fg:(_c,t)=>t,bg:(_c,t)=>t,bold:t=>t};
        const lines=renderers.get(final.message.customType)(final.message,{},theme).render(80).map(line=>line.trim()).filter(Boolean);
        out({header:lines[0],scenario:lines.includes("Scenario: Works"),origin:lines.some(line=>line.includes("caller-supplied")),trigger:final.options?.triggerTurn??false});
      }finally{await rm(cwd,{recursive:true,force:true});}
    ''')
    assert result == {"header": "[e2e] needs review", "scenario": True, "origin": True, "trigger": False}


def test_all_terminal_states_have_bare_headers_and_review_uses_warning_style() -> None:
    # Given business failure, uncertainty, success or lifecycle feedback, when
    # rendered, then headers stay bare and warning states are not error bands.
    result = run_typescript(PREAMBLE + r'''
      import {renderFeedback,verdictFeedback} from "''' + (SRC / "feedback.ts").as_uri() + r'''";
      const base={feature:"Test",scenario:"Works",status:"fulfilled",exitCode:0,reason:"confirmed",policy:{clauseGate:.8,verdictGate:.6},unjudged:0,triage:[],clauses:[{clause:1,text:"actual observation",kind:"then",status:"met",source:"deterministic"}]};
      const feedback=[verdictFeedback(base,{verifiedRun:true}),verdictFeedback({...base,status:"not_fulfilled"},{verifiedRun:true}),verdictFeedback({...base,status:"partially_fulfilled"},{verifiedRun:true}),verdictFeedback({...base,status:"needs_review"},{verifiedRun:true}),verdictFeedback(base,{verifiedRun:false}),...['running','error','continue','waiting'].map(label=>({label,tone:label==='error'?'error':'warning',lines:['detail']}))];
      const output=feedback.map(value=>{const backgrounds=[];const theme={fg:(_c,t)=>t,bold:t=>t,bg:(c,t)=>{backgrounds.push(c);return t;}};const lines=renderFeedback(value,theme).render(40);return {header:lines.map(line=>line.trim()).find(Boolean),background:backgrounds[0]};});
      out({output});
    ''')
    assert [item["header"] for item in result["output"]] == [
        "[e2e] passed", "[e2e] failed", "[e2e] failed", "[e2e] needs review",
        "[e2e] needs review", "[e2e] running", "[e2e] error", "[e2e] continue", "[e2e] waiting",
    ]
    assert result["output"][3]["background"] == "toolPendingBg"
    assert result["output"][4]["background"] == "toolPendingBg"
