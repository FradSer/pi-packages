/** Offline native authoring fixture; real mode registers only product hooks. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {createAssistantMessageEventStream, type AssistantMessage} from "@earendil-works/pi-ai";
import type {ExtensionAPI} from "@earendil-works/pi-coding-agent";
import registerGuardrails from "../extensions/guardrails.ts";
import registerGuidance from "../extensions/harness-guidance.ts";

export default function(pi: ExtensionAPI): void {
  registerGuardrails(pi);
  registerGuidance(pi);
  pi.on("session_start", () => fs.writeFileSync(process.env.PI_HARNESS_READY!, "ready"));
  pi.on("agent_end", () => fs.appendFileSync(process.env.PI_HARNESS_ENDED!, "ended\n"));
  const target = path.join(process.cwd(), ".pi/harness.json");
  const schemaDocs = new Set<string>(JSON.parse(process.env.PI_HARNESS_SCHEMA_DOCS ?? "[]"));
  let writes = 0;
  pi.on("tool_call", event => {
    if (event.toolName === "harness_preview" && process.env.PI_HARNESS_FOLLOWUP !== "1") return;
    const input = event.input as Record<string, unknown>;
    const requested = typeof input.path === "string" ? path.resolve(process.cwd(), input.path) : undefined;
    const permittedRead = event.toolName === "read" && requested !== undefined && (requested === target || schemaDocs.has(requested));
    const permittedWrite = event.toolName === "write" && requested === target;
    if ((!permittedRead && !permittedWrite) || input.offset !== undefined || input.limit !== undefined) {
      pi.appendEntry("harness-first-boundary", {outcome: "rejected", reason: "outside-exact-target-or-partial-read"});
      return {block: true, reason: "Acceptance permits complete target reads, bundled public SDK schema documentation reads, and one disposable target write."};
    }
    if (event.toolName === "write" && (process.env.PI_HARNESS_FOLLOWUP === "1" || ++writes > 1)) {
      pi.appendEntry("harness-first-boundary", {outcome: "rejected", reason: "additional-write"});
      return {block: true, reason: "Only one complete target write is admitted."};
    }
  });
  if (process.env.PI_HARNESS_REAL === "1") return;
  let calls = process.env.PI_HARNESS_FOLLOWUP === "1" ? 6 : 0;
  const candidate = {rules: [{id: "d0-traffic-safeguard", text: String.raw`\bD0\b`,
    instructions: "涉及 D0 流量的工作应先确认服务预算与现有保护，优先本地验证，避免无界并发、重复请求和未经确认的压测；遇到限流先停止并查明原因。未确认预算时先询问，不假定数值。"}]};
  pi.registerProvider("harness-first-fixture", {
    api: "harness-first-fixture", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{id: "deterministic", name: "First Harness authoring fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 256, cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0}}],
    streamSimple(model, context) {
      assert.ok(++calls <= 7, "Unexpected native authoring loop");
      const results = context.messages.filter(message => message.role === "toolResult");
      const last = results.at(-1);
      let content: AssistantMessage["content"], stopReason: AssistantMessage["stopReason"] = "toolUse";
      if (calls === 1) {
        const prompt = JSON.stringify(context.messages);
        assert.ok(prompt.includes("Target state checked by the parent: absent"));
        assert.ok(prompt.includes("避免后续 D0 的流量被打爆"));
        assert.ok(!fs.existsSync(target));
        content = [{type: "toolCall", id: "missing-target", name: "read", arguments: {path: target}}];
      } else if (calls === 2) {
        assert.equal(last?.role, "toolResult");
        assert.ok(last && last.role === "toolResult" && last.isError);
        assert.ok(JSON.stringify(last).includes("ENOENT"));
        content = [{type: "toolCall", id: "inert-candidate-preview", name: "harness_preview", arguments: {content: JSON.stringify({rules:[{...candidate.rules[0],text:"unrelated-never-match"}]}), cases:[{ruleId:candidate.rules[0].id,input:"维护 D0",matches:true},{ruleId:candidate.rules[0].id,input:"本地配色",matches:false}]}}];
      } else if (calls === 3) {
        assert.ok(last && last.role === "toolResult" && last.isError);
        assert.ok(!fs.existsSync(target));
        content = [{type:"toolCall",id:"candidate-preview",name:"harness_preview",arguments:{content:JSON.stringify(candidate),cases:[{ruleId:candidate.rules[0].id,input:"维护 D0",matches:true},{ruleId:candidate.rules[0].id,input:"D1 流量被打爆",matches:false},{ruleId:candidate.rules[0].id,input:"D0x 流量被打爆",matches:false}]}}];
      } else if (calls === 4) {
        assert.ok(last && last.role === "toolResult" && !last.isError);
        assert.ok(JSON.stringify(last).includes('"passed":true'));
        assert.ok(!fs.existsSync(target));
        content = [{type: "toolCall", id: "complete-first-write", name: "write", arguments: {path: target, content: JSON.stringify(candidate)}}];
      } else if (calls === 5) {
        assert.ok(last && last.role === "toolResult" && !last.isError);
        assert.deepEqual(JSON.parse(fs.readFileSync(target, "utf8")), candidate);
        content = [{type: "toolCall", id: "read-back", name: "read", arguments: {path: target}}];
      } else {
        if (calls === 6) assert.ok(last && last.role === "toolResult" && !last.isError);
        if (calls === 7) assert.ok(JSON.stringify(context.messages).includes(candidate.rules[0].instructions));
        content = [{type: "text", text: calls === 6 ? "已创建 D0 流量保护指引；这是上下文指引，不是强制限流器。" : "D0 后续任务已收到保存的保护指引。"}];
        stopReason = "stop";
      }
      const message: AssistantMessage = {role: "assistant", api: model.api, provider: model.provider, model: model.id,
        timestamp: Date.now(), content, stopReason, usage: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0,
          totalTokens: 0, cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0}}};
      const stream = createAssistantMessageEventStream();
      stream.push({type: "start", partial: message});
      stream.push({type: "done", reason: stopReason, message});
      stream.end();
      return stream;
    },
  });
}
