import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { createAssistantMessageEventStream, getCurrentTools, type AssistantMessage } from "@earendil-works/pi-ai";
import verifierReference from "./continuous-verifier-reference.ts";
import { installStudyToolBudget } from "./continuous-tool-budget.ts";

export default function fixture(pi: ExtensionAPI): void {
  verifierReference(pi); installStudyToolBudget(pi, 1);
  let calls = 0;
  pi.registerProvider("study-verifier-fixture", {
    api: "study-verifier-fixture", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{id:"deterministic",name:"Verifier fixture",reasoning:false,input:["text"],contextWindow:200000,maxTokens:4096,
      cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}],
    streamSimple(model, context) {
      calls++;
      pi.appendEntry("study-verifier-provider", {call:calls,tools:getCurrentTools(context.messages).map(tool=>tool.name)});
      const message: AssistantMessage = {role:"assistant",api:model.api,provider:model.provider,model:model.id,timestamp:Date.now(),
        content:calls===1?[{type:"toolCall",id:process.env.PI_STUDY_VERIFIER_FILE?"verification":"source",name:"read",
          arguments:{path:process.env.PI_STUDY_VERIFIER_FILE??"index.js"}}]:[{type:"text",text:"Observed actual source and checks."}],
        stopReason:calls===1?"toolUse":"stop",usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}};
      const stream=createAssistantMessageEventStream();stream.push({type:"start",partial:message});stream.push({type:"done",reason:message.stopReason,message});stream.end();return stream;
    },
  });
}
