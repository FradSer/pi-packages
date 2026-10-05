/** Real parent and temporary RPC child: no model credentials beyond loopback fixture. */
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { INTENT_TOOL_NAMES, type IntentToolName } from "../packages/subagents/src/intent-tools.ts";
import extension from "../packages/subagents/src/extension.ts";
import { getAgent, livingAgents } from "../packages/subagents/src/roster.ts";
import { parseExactSessionRoute } from "../packages/subagents/src/session-route.ts";

export default function(pi: ExtensionAPI): void {
  // This fixture verifies the supported legacy model interface.
  const nativeGetFlag = pi.getFlag.bind(pi);
  const evidence=process.env.PI_TEMPORARY_EVIDENCE;assert.ok(evidence);
  const texts:string[]=[],turns:number[]=[],sessions:string[]=[];
  let handle:string|undefined,request=0,idleAfterFirst=false,stopped=false;
  const resolvers:Array<()=>void>=[];
  const answers=[0,1].map(()=>new Promise<void>(resolve=>resolvers.push(resolve)));
  extension({...pi,sendMessage(message,options){
    if(message.customType==="subagents-session-result"){
      const notice=message.details as {text:string;turn:number;session:string};
      texts.push(notice.text);turns.push(notice.turn);sessions.push(notice.session);
      assert.ok(texts.length<=2);
      resolvers[texts.length-1]();
    }
    pi.sendMessage(message,options);
  }});
  pi.on("tool_result",event=>{
    if(!INTENT_TOOL_NAMES.includes(event.toolName as IntentToolName))return;
    const details=event.details as {session?:string;operation?:string;ok?:boolean};
    assert.equal(details.ok,true,JSON.stringify(event.content));
    if(details.operation==="agent_start")handle=details.session;
    if(details.operation==="agent_stop")stopped=true;
  });
  pi.on("session_shutdown",()=>writeFileSync(evidence,JSON.stringify({texts,turns,
    sameSession:sessions.length===2&&sessions.every(session=>session===handle),idleAfterFirst,stopped,living:livingAgents().length})));
  pi.registerProvider("temporary-parent",{api:"temporary-parent",baseUrl:"http://127.0.0.1",apiKey:process.env.PI_TEMPORARY_AUTH,
    models:[{id:"scripted",name:"Temporary resident fixture",reasoning:false,input:["text"],contextWindow:200000,maxTokens:4096,
      cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}],
    streamSimple(model){
      const index=request++;
      const session=()=>{assert.ok(handle,"Start must return an exact session");return handle;};
      // The label is display only; the roster name is minted per start.
      const childName=()=>{const route=parseExactSessionRoute(session());assert.ok(route);return route.name;};
      if(index===2){idleAfterFirst=getAgent(childName())?.status==="idle";assert.ok(idleAfterFirst);}
      const tool: Extract<AssistantMessage["content"][number], { type: "toolCall" }> | undefined=index===0?{type:"toolCall" as const,id:"start",name:"agent_start",arguments:{label:"temporary-math",prompt:"Calculate 1+1",tools:[],model:"temporary-loopback/arithmetic"}}
        :index===2?{type:"toolCall" as const,id:"send",name:"agent_input",arguments:{session:session(),prompt:"Calculate 2+3",delivery:"next"}}
        :index===4?{type:"toolCall" as const,id:"stop",name:"agent_stop",arguments:{session:session()}}:undefined;
      const message:AssistantMessage={role:"assistant",api:model.api,provider:model.provider,model:model.id,timestamp:Date.now(),
        content:tool?[tool]:[{type:"text",text:index===5?"TEMPORARY_TWO_RESULTS_OK":"Input accepted"}],stopReason:tool?"toolUse":"stop",
        usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}};
      const stream=createAssistantMessageEventStream();
      const emit=()=>{stream.push({type:"start",partial:message});stream.push({type:"done",reason:tool?"toolUse":"stop",message});stream.end();};
      // Keep print alive for the asynchronous callback without polling child state.
      if(index===1||index===3)void answers[index===1?0:1].then(emit);else emit();
      return stream;
    }
  });
}
