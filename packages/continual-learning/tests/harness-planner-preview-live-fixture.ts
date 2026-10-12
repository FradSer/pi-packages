import assert from "node:assert/strict";
import {createAssistantMessageEventStream, getCurrentTools, type AssistantMessage} from "@earendil-works/pi-ai";
import type {ExtensionAPI} from "@earendil-works/pi-coding-agent";

export default function fixture(pi: ExtensionAPI): void {
  let calls = 0;
  pi.registerProvider("preview-fixture", {
    api:"preview-fixture", baseUrl:"http://127.0.0.1", apiKey:"offline-fixture",
    models:[{id:"fixed",name:"Read-only case check",reasoning:false,input:["text"],contextWindow:200000,maxTokens:256,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}],
    streamSimple(model, context) {
      assert.ok(++calls <= 3);
      const schema = getCurrentTools(context.messages).find(tool => tool.name === "harness_check_cases")?.parameters;
      assert.equal(schema?.properties.rule.type, "object", JSON.stringify(schema));
      assert.equal(schema?.properties.cases.type, "object", JSON.stringify(schema));
      assert.equal(schema?.properties.cases.properties.positive.items.type, "object", JSON.stringify(schema));
      const last = context.messages.filter(m => m.role === "toolResult").at(-1);
      if (calls === 2) assert.ok(last?.isError && JSON.stringify(last).includes("matched but must remain unmatched"));
      if (calls === 3) assert.ok(last && !last.isError && JSON.stringify(last).includes('"authorizesMutation":false'));
      const content: AssistantMessage["content"] = calls === 3 ? [{type:"text",text:"preview-correction-verified"}] : [{type:"toolCall",id:`preview-${calls}`,name:"harness_check_cases",arguments:{rule:{id:"r",bash:"^npm(?:[ \\t]|$)",action:"block",message:"use pnpm"},cases:{positive:[{bash:"npm test",expected:"block"}],negative:[{bash:calls === 1 ? "npm test\r" : "pnpm test"}]}}}];
      const message: AssistantMessage = {role:"assistant",api:model.api,provider:model.provider,model:model.id,timestamp:Date.now(),content,stopReason:calls === 3 ? "stop" : "toolUse",usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}};
      const stream = createAssistantMessageEventStream();
      stream.push({type:"start",partial:message});
      stream.push({type:"done",reason:message.stopReason as "stop" | "toolUse",message});
      stream.end();return stream;
    },
  });
}
