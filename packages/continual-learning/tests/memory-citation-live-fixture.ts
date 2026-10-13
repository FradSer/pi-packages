/** Native scoped-reader acceptance with no model service or mutation. */
import assert from "node:assert/strict";
import {readFileSync, writeFileSync} from "node:fs";
import {createAssistantMessageEventStream, type AssistantMessage} from "@earendil-works/pi-ai";
import type {ExtensionAPI} from "@earendil-works/pi-coding-agent";
import {registerPlannerRead} from "../extensions/planner-read-scope.ts";
import {normalizeSnapshotEvidence} from "../extensions/consolidation-run.ts";
import {resolveMemoryPlanCitations} from "../extensions/memory-citation-locations.ts";

export default function (pi: ExtensionAPI): void {
  const file = process.env.PI_CITATION_FIXTURE_FILE!;
  registerPlannerRead(pi, {cwd: process.cwd(), files: [file], roots: [], indexedEvidence: true});
  let calls = 0;
  pi.registerProvider("memory-citation-fixture", {
    api: "memory-citation-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_CITATION_FIXTURE_AUTH,
    models: [{id: "deterministic", name: "Scoped citation fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 256, cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0}}],
    streamSimple(model, context) {
      assert.ok(++calls <= 2, "Unexpected native tool loop");
      let content: AssistantMessage["content"];
      let stopReason: AssistantMessage["stopReason"];
      if (calls === 1) {
        content = [{type: "toolCall", id: "scoped-evidence-read", name: "learning_read", arguments: {path: file, limit: 2000}}];
        stopReason = "toolUse";
      } else {
        const results = context.messages.filter(message => message.role === "toolResult" && message.toolCallId === "scoped-evidence-read");
        assert.equal(results.length, 1);
        const result = results[0];
        assert.equal(result.role, "toolResult");
        assert.ok(!result.isError);
        const text = result.content.filter(part => part.type === "text").map(part => part.text).join("\n");
        const shown = JSON.parse(text.slice(0, text.lastIndexOf("\n[lines")));
        const original = readFileSync(file, "utf8");
        const snapshot = JSON.parse(original);
        const message = snapshot.entries[0].message ?? snapshot.entries[0];
        const expected = message.content[0].text.split("\n")[22];
        const entry = shown.entries[0].entry;
        const line = (entry.message ?? entry).content[0].citationLines.lines[22];
        assert.equal(line.chunks.map((chunk: {text: string}) => chunk.text).join(""), expected);
        for (const chunk of line.chunks) {
          const plan = resolveMemoryPlanCitations({operations: [{evidence: [{index: 0,
            lines: {block: 0, start: 23, end: 23, characters: {start: chunk.start, end: chunk.end}}}]}]}, snapshot) as {operations: {evidence: {quote: string}[]}[]};
          assert.equal(plan.operations[0].evidence[0].quote, chunk.text);
          const referenced = resolveMemoryPlanCitations({operations: [{evidence: [{ref: chunk.ref}]}]}, snapshot) as {operations: {evidence: {quote: string}[]}[]};
          assert.equal(referenced.operations[0].evidence[0].quote, chunk.text);
        }
        assert.equal(shown.entries[2].citationEligible, false);
        assert.deepEqual(shown.entries[2].entry, snapshot.entries[2]);
        assert.throws(() => resolveMemoryPlanCitations({operations: [{evidence: [{ref: "e2.b0.l1"}]}]}, snapshot));
        assert.throws(() => normalizeSnapshotEvidence([{index: 2, quote: snapshot.entries[2].content}], snapshot));
        assert.equal(readFileSync(file, "utf8"), original);
        writeFileSync(process.env.PI_CITATION_FIXTURE_RESULT!, JSON.stringify({status: "passed", remoteRequests: 0,
          actualToolResults: 1, originalLineCharacters: expected.length, chunks: line.chunks.length,
          allOriginalCharactersPreserved: true, exactParentExtraction: true, parentLabelledReferences: true, sourceUnchanged: true, memoryReadbackPreservedButNotIndependent: true, efficacyEstablished: false}));
        content = [{type: "text", text: "Scoped citation fixture passed"}];
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
