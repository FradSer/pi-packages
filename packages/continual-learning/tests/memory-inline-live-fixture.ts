import assert from "node:assert/strict";
import fs from "node:fs";
import {createAssistantMessageEventStream, getCurrentTools, type AssistantMessage} from "@earendil-works/pi-ai";
import type {ExtensionAPI} from "@earendil-works/pi-coding-agent";

export default function fixture(pi: ExtensionAPI): void {
  pi.registerProvider("inline-memory-fixture", {
    api: "inline-memory-fixture", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{id:"fixed",name:"Complete frozen Memory input",reasoning:false,input:["text"],contextWindow:200000,maxTokens:128,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}],
    streamSimple(model, context) {
      assert.equal(getCurrentTools(context.messages).length, 0);
      const user = context.messages.filter(message => message.role === "user").at(-1);
      const text = typeof user?.content === "string" ? user.content : user?.content.filter(block => block.type === "text").map(block => block.text).join("\n");
      assert.ok(text);
      assert.ok(text.includes(fs.readFileSync(process.env.CL_INLINE_EXPECTED!, "utf8")));
      assert.ok(text.includes("No tools are available"));
      const message: AssistantMessage = {role:"assistant",api:model.api,provider:model.provider,model:model.id,timestamp:Date.now(),content:[{type:"text",text:"Complete frozen input received; no learned change claimed."}],stopReason:"stop",usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}};
      const stream = createAssistantMessageEventStream();
      stream.push({type:"start",partial:message});stream.push({type:"done",reason:"stop",message});stream.end();return stream;
    },
  });
}
