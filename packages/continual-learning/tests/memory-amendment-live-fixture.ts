import assert from "node:assert/strict";
import fs from "node:fs";
import {createAssistantMessageEventStream, getCurrentTools, type AssistantMessage} from "@earendil-works/pi-ai";
import type {ExtensionAPI} from "@earendil-works/pi-coding-agent";

export default function fixture(pi: ExtensionAPI): void {
  let generationAttempts = 0;
  pi.registerFlag("generation-native-retry", {type:"string", description:"Offline native retry lifecycle fixture"});
  pi.registerFlag("generation-json-whitespace", {type:"string", description:"Offline frozen generation serialization fixture"});
  pi.registerFlag("raw-string-whitespace", {type:"string", description:"Offline malformed JSON whitespace fixture"});
  pi.registerFlag("missing-memory-body", {type:"string", description:"Offline metadata-only structural repair fixture"});
  pi.registerFlag("source-excerpt-selection", {type:"string", description:"Offline explicit parent-audited source selection"});
  pi.registerFlag("bound-candidate-response", {type:"string", description:"Offline explicit parent-bound candidate references"});
  pi.registerProvider("amendment-fixture", {
    api: "amendment-fixture", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{id: "fixed", name: "Read-only Memory amendment", reasoning: false, input: ["text"], contextWindow: 200000, maxTokens: 2048, cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0}}],
    streamSimple(model, context) {
      assert.equal(getCurrentTools(context.messages).length, 0);
      const user = context.messages.filter(message => message.role === "user").at(-1);
      const text = typeof user?.content === "string" ? user.content : user?.content.filter(block => block.type === "text").map(block => block.text).join("\n");
      assert.ok(text);
      const generationWhitespace = pi.getFlag("generation-json-whitespace") === "enabled";
      let reply: string;
      if (generationWhitespace) {
        assert.equal(text, "frozen generation serialization");
        reply = JSON.parse(fs.readFileSync(new URL("./fixtures/real-memory-generation-raw-whitespace.json", import.meta.url), "utf8")).content;
      } else {
      const data = JSON.parse(text.split("\n").at(-1)!);
      const bound = pi.getFlag("bound-candidate-response");
      if (typeof bound === "string") {
        const response = JSON.parse(bound);
        if (response.replacements) assert.ok(text.includes("Prefer the exact short candidateRef"));
        else assert.ok(data.retainedOperationContract);
        for (const operation of response.operations ?? []) {
          const record = data.retainedOperationContract.records.find((record: {name: string}) => record.name === operation.name);
          assert.ok(record);
          assert.equal(operation.classification, record.classification);
          if (operation.kind === "rewrite" && !Object.hasOwn(operation, "content")) assert.equal(record.reuseFrozenContent, true);
        }
        for (const patch of response.replacements ?? []) {
          assert.ok(data.repairCandidates.some((candidate: {candidateRef: string}) => candidate.candidateRef === patch.candidateRef));
          assert.equal(Object.hasOwn(patch, "candidateId"), false);
        }
        for (const withdrawal of response.withdrawals ?? []) {
          assert.ok(data.repairCandidates.some((candidate: {candidateRef: string; withdrawalAllowed?: boolean}) => candidate.candidateRef === withdrawal.candidateRef && candidate.withdrawalAllowed === true));
          assert.equal(Object.hasOwn(withdrawal, "candidateId"), false);
        }
        reply = bound;
      } else {
      const missingBody = pi.getFlag("missing-memory-body") === "enabled";
      if (missingBody) assert.equal(data.rejectedPlan.newMemories.length, 1);
      else assert.equal(data.repairCandidates.length, 1);
      const candidate = missingBody ? {field: "newMemories", index: 0} : data.repairCandidates[0];
      const prior = data.rejectedPlan[candidate.field][candidate.index];
      if (candidate.requiredKnowledgeSections?.length) {
        assert.ok(text.includes("Keep each section non-empty in the complete corrected content."));
        assert.ok(candidate.requiredKnowledgeSections.every((section: string) => ["Why", "How to apply"].includes(section)));
      }
      if (missingBody) {
        assert.ok(text.includes("non-empty Memory body"));
        assert.ok(JSON.stringify(data).includes("Correct claim"));
      }
      const replacement = missingBody ? prior.content + "Correct claim\n" : prior.content.replace("Old claim", "Correct claim");
      const output = {kind: "incremental-memory-amendment", version: 1, ...data.identity,
        replacements: [{candidateId: candidate.candidateId, content: replacement, evidence: prior.evidence}]};
      const excerpt = pi.getFlag("source-excerpt-selection");
      if (typeof excerpt === "string") {
        assert.equal(candidate.sourceExcerptAllowed, true);
        assert.ok(text.includes("sourceExcerptAllowed:true"));
        const sourceExcerpt = JSON.parse(excerpt);
        (output as {replacements: unknown[]}).replacements = [{candidateId: candidate.candidateId, sourceExcerpt, evidence: [sourceExcerpt]}];
      }
      const encoded = JSON.stringify(missingBody ? {
        ...data.rejectedPlan,
        newMemories: data.rejectedPlan.newMemories.map((entry: unknown, index: number) => index === candidate.index
          ? {...prior, content: replacement} : entry),
      } : output);
      reply = pi.getFlag("raw-string-whitespace") === "enabled" ? encoded.replace("\\n", "\n").replace("\\t", "\t") : encoded;
      }
      }
      const message: AssistantMessage = {role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: [...(generationWhitespace ? [{type: "thinking" as const, thinking: "Offline untrusted analysis", thinkingSignature: "reasoning_content"}] : []), {type: "text", text: reply}], stopReason: "stop",
        usage: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0}}};
      const stream = createAssistantMessageEventStream();
      if (generationWhitespace && pi.getFlag("generation-native-retry") === "enabled" && generationAttempts++ === 0) {
        message.stopReason = "error";
        message.errorMessage = "503 offline fixture service unavailable";
        message.content = [];
        stream.push({type: "start", partial: message});
        stream.push({type: "error", reason: "error", error: message});
        stream.end();
        return stream;
      }
      stream.push({type: "start", partial: message});
      stream.push({type: "done", reason: "stop", message});
      stream.end();
      return stream;
    },
  });
}
