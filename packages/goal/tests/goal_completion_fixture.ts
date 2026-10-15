/** Scripted native Pi acceptance. The Goal implementation is real; no remote model runs. */
import { appendFileSync, existsSync } from "node:fs";
import { createAssistantMessageEventStream, type JsonObject, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import goal from "../src/index.ts";

export default function (pi: ExtensionAPI): void {
  const mode=process.env.PI_GOAL_COMPLETION_CASE ?? "complete";
  // Opt-in start delay. A probe that must read the screen before the run advances, such as a
  // live resize of the request row, holds the first response instead of racing the transcript.
  const delay=Number(process.env.PI_GOAL_FIXTURE_DELAY_MS ?? "0");
  const trace=process.env.PI_GOAL_COMPLETION_TRACE;
  const log=(data: unknown) => {if(trace) appendFileSync(trace,JSON.stringify(data)+"\n");};
  let step=0;
  pi.on("session_start",()=>log({kind:"ready"}));
  if (process.env.PI_GOAL_AUTOLOAD !== "1") goal(pi, {runCheck: async options => {
    log({kind:"check",objective:options.objective,observations:options.evidence?.observations});
    if(mode === "error") return {met:false,report:"",error:"Offline provider unavailable."};
    if(mode === "cancel") {
      log({kind:"checking"});
      const release=process.env.PI_GOAL_CHECK_RELEASE;
      while(!options.signal?.aborted && release && !existsSync(release)) await new Promise(resolve=>setTimeout(resolve,10));
      return {met:true,report:"Old completion result."};
    }
    if(mode === "refuse") return {met:false,report:"Required independent review evidence is missing."};
    const met=options.evidence?.observations.some(item=>item.label === "bash" && item.outcome === "success" && item.output.includes("NATIVE_COMPLETION_E2E_PASS"));
    return {met:!!met,report:met ? "The executed command satisfies the complete contract. COMPLETION_END" : "Actual executed output is missing.",
      usage:{input:10,output:5,cacheRead:0,cacheWrite:0,totalTokens:15,cost:0}};
  }});
  pi.on("agent_settled",(_event,ctx)=> {const core=(pi as unknown as {_goalCore?: {goal?: unknown}})._goalCore;log({kind:"settled",goal:core?.goal,branch:ctx.sessionManager.getBranch().filter(entry=>entry.type === "custom_message")});});
  pi.registerProvider("goal-completion-offline",{
    api:"goal-completion-offline",baseUrl:"http://127.0.0.1",apiKey:"offline-fixture",
    models:[{id:"scripted",name:"Offline Goal fixture",reasoning:false,input:["text"],contextWindow:200000,maxTokens:4096,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}],
    streamSimple(model){
      const index=step++;log({kind:"provider",step:index});
      const call=(name:string,args:JsonObject):AssistantMessage["content"]=>[{type:"toolCall",id:`native-${index}`,name,arguments:args}];
      let content:AssistantMessage["content"];
      // The revision case needs two runs: one creates the goal and stops, and the later
      // /goal request is the run that merges into it and records work.
      if(mode === "revision" && index === 0) content=call("create_goal",{objective:"Probe the live goal rows.",verification_contract:"The revision keeps this contract."});
      else if(mode === "revision" && index === 1) content=[{type:"text",text:"Native fixture turn finished."}];
      else if(mode === "revision" && index === 2) content=call("update_goal",{objective:"Probe the live goal rows. Audit the export path."});
      // From here the revision case keeps recording work, so the goal keeps pursuing and the
      // probe can read that state instead of racing a pause. Each receipt differs, because a
      // repeated identical receipt is not new work.
      else if(mode === "revision" && index >= 3 && index <= 60) content=call("bash",{command:"printf 'PROBE_REVISION_WORK "+String(index)+"\\n'"});
      else if(index === 0) content=call("create_goal",{objective:mode === "long" ? "Preserve every requirement, including 中文字符. ".repeat(100)+"GOAL_REQUIREMENT_END" : "Run a command printing NATIVE_COMPLETION_E2E_PASS.",verification_contract:mode === "long" ? "Keep all completion conditions. ".repeat(25)+"GOAL_CONTRACT_END" : "The recorded command succeeds and prints NATIVE_COMPLETION_E2E_PASS."});
      else if(mode === "long" && index === 1) content=call("get_goal",{});
      else if(mode === "blocked" && index <= 3) content=call("update_goal",{status:"blocked",reason:"Required fixture input is unavailable."});
      else if(["complete","error","cancel"].includes(mode) && index === 1) content=call("bash",{command:"printf 'NATIVE_COMPLETION_E2E_PASS\\n'"});
      else if(["complete","error","cancel"].includes(mode) && index === 2 || mode === "refuse" && index <= 3) content=call("update_goal",{status:"complete",completion_summary:"Judge the recorded command output."});
      else content=[{type:"text",text:"Native fixture turn finished."}];
      const message:AssistantMessage={role:"assistant",api:model.api,provider:model.provider,model:model.id,timestamp:Date.now(),content,stopReason:content[0]?.type === "toolCall" ? "toolUse" : "stop",
        usage:{input:10,output:5,cacheRead:0,cacheWrite:0,totalTokens:15,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}};
      const stream=createAssistantMessageEventStream();
      const publish=()=>{stream.push({type:"start",partial:message});stream.push({type:"done",reason:message.stopReason as "toolUse"|"stop",message});stream.end();};
      if(delay > 0 && index === 0) setTimeout(publish,delay); else publish();
      return stream;
    },
  });
}
