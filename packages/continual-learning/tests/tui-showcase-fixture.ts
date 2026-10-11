/** Deterministic showcase data; all UI components and renderers are production code. */
import { appendFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { searchModelFromPicker } from "@fradser/pi-kit";
import baseFixture from "./meaningful-details-live-fixture.ts";
import { openMemoryMenu } from "../extensions/memory-menu.ts";
import { runHarnessMenu } from "../extensions/harness-menu.ts";
import { managementUI, showDetailPages } from "../extensions/detail-pages.ts";
import { buildLearningReceipt } from "../extensions/learning-efficiency.ts";
import type { LearningHistory } from "../extensions/learning-history.ts";
import type { ResolvedHarnessConfig } from "../extensions/guardrail-types.ts";

export default function showcase(pi: ExtensionAPI): void {
  baseFixture(pi);
  const mark = (name: string) => appendFileSync(process.env.PI_DETAILS_LIVE_SNAPSHOTS!, JSON.stringify({kind:"showcase-done", name})+"\n");
  pi.registerCommand("case-memory", {description:"Isolated Memory showcase", handler:async (_args,ctx)=>{
    const entries = Array.from({length:129},(_,i)=>{
      const filename=`memory-${String(i+1).padStart(3,"0")}.md`;
      const content=Array.from({length:100},(_,n)=>`line-${String(n+1).padStart(3,"0")} Preserve evidence and verify the actual result.`).join("\n");
      const readPath=path.join(ctx.cwd,filename);writeFileSync(readPath,content);
      return {filename,source:"public" as const,readPath,content,description:`Reference ${i+1}: `+"Preserve original evidence. ".repeat(8)};
    });
    const history:LearningHistory[]=Array.from({length:50},(_,i)=>({version:1,id:`change_fixture_${String(i).padStart(16,"0")}`,cwd:ctx.cwd,agentDir:ctx.cwd,phase:i%2?"harness":"memory",createdAt:`2026-10-09T${String(i%24).padStart(2,"0")}:30:00Z`,status:"applied",changes:[{target:{root:"project",name:i%2?".pi/harness.json":"build-command.md"},before:null,after:{bytes:Buffer.from("Verified change for record "+(i+1)).toString("base64"),mode:420,digest:"fixture"}}]}));
    await openMemoryMenu(ctx,{
      status:async()=>({autoMemory:false,model:"fixture/jkev",entries:129}),
      loadMemories:async()=>({entries,totalEntries:129,omittedEntries:0,limitedEntries:0,unavailableEntries:0,indexes:[],maxTotalChars:6000}),
      listHistory:async()=>history,manage:async()=>{throw Error("Showcase must not change policies or undo")},
      selectModel:async()=>{},toggleAutoMemory:async()=>{},isBusy:()=>false,
      policies:async()=>({policies:{memory:"apply",harness:"propose",agents:"off"},agentsDisabled:true}),
    });mark("memory");
  }});
  pi.registerCommand("case-harness", {description:"Isolated Harness showcase",handler:async (_args,ctx)=>{
    const config:ResolvedHarnessConfig={rules:Array.from({length:35},(_,i)=>({id:`evidence-rule-${String(i+1).padStart(2,"0")}`,text:"release",instructions:"Preserve the approved evidence and verify the result.",source:"project" as const})),errors:Array.from({length:12},(_,i)=>`diagnostic-${String(i+1).padStart(2,"0")}: configuration layer needs repair`),notices:["All twelve errors remain available"],invalidRules:[],legacy:{policies:[],invalidPolicies:[],skillPrompts:{},disabled:[],unavailable:false},bashEvaluationComplete:false,configReadIncomplete:true};
    await runHarnessMenu(ctx.ui,config,{project:path.join(ctx.cwd,".pi/harness.json"),projectLocal:path.join(ctx.cwd,".pi/harness.local.json"),user:path.join(ctx.cwd,"agent/harness.json"),userScoped:path.join(ctx.cwd,"agent/scoped.json")},()=>{throw Error("No authoring in read-only showcase")},ctx.mode);mark("harness");
  }});
  pi.registerCommand("case-model", {description:"Production model picker",handler:async(_args,ctx)=>{
    await searchModelFromPicker(ctx.ui,Array.from({length:20},(_,i)=>({provider:"fixture",id:`jkev-${i}-`+"long-model-".repeat(12)+"UNIQUE_TAIL"})),undefined);mark("model");
  }});
  pi.registerCommand("case-rpc", {description:"RPC reader fallback",handler:async(_args,ctx)=>{
    await showDetailPages(managementUI(ctx.ui,ctx.mode),"RPC reader", "RPC_BODY_START\n"+"preserved body ".repeat(350)+"\nRPC_BODY_TAIL");mark("rpc");
  }});
  pi.registerCommand("case-recovery", {description:"Recovered retry and later terminal failure",handler:async()=>{
    const screen={memory:true,harness:false,agents:true,reasons:[]};
    const attempts=[{phase:"memory" as const,attempt:0,outcome:"rejected" as const,durationMs:1,operations:0},{phase:"memory" as const,attempt:1,outcome:"applied" as const,durationMs:1,operations:1}];
    pi.sendMessage({customType:"continual-learning-result",content:"Recovered retry",display:true,details:buildLearningReceipt("manual",screen,attempts)});
    pi.sendMessage({customType:"continual-learning-result",content:"Later failure",display:true,details:buildLearningReceipt("manual",screen,[...attempts,{phase:"agents",attempt:0,outcome:"noop",durationMs:1,operations:0},{phase:"agents",attempt:1,outcome:"failed",durationMs:0,operations:0}])});mark("recovery");
  }});
  pi.registerCommand("case-status", {description:"Production lifecycle renderers",handler:async()=>{
    const receipt=buildLearningReceipt("manual",{memory:true,harness:true,agents:false,reasons:[]},[{phase:"memory",attempt:0,outcome:"applied",durationMs:10,operations:1},{phase:"harness",attempt:0,outcome:"failed",durationMs:5,operations:0}]);
    pi.sendMessage({customType:"continual-learning-result",content:"Partial result fixture",display:true,details:receipt});
    pi.appendEntry("harness-event",{kind:"policy-matched",policy:"protected-report",action:"block",outcome:"blocked",tool:"write",reason:"Protected report requires approval",source:"project",file:".pi/harness.json"});
    pi.appendEntry("harness-check",{kind:"harness-check",phase:"artifact",status:"violated",detail:"Required report is missing",policy:"report-required",path:"reports/final.txt"});
    pi.appendEntry("harness-guidance-event",{kind:"text-incomplete",ruleId:"review-evidence",source:"project",file:".pi/harness.json",prompt:"Configuration is incomplete; guidance is indeterminate."});
    pi.sendMessage({customType:"harness-procedure",content:"Required protocol: this full text stays in model context.",display:true,details:{subject:"Preserve approved release evidence"}});mark("status");
  }});
}
