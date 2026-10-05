/** Offline native Pi boundary probe. Usage fields are deliberately zero; never billing evidence. */
import assert from "node:assert/strict";
import { appendFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import { convertResponsesMessages, convertResponsesTools } from "@earendil-works/pi-ai/api/openai-responses-shared";
import { getCurrentTools } from "@earendil-works/pi-ai/utils/transcript";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { detailField } from "@fradser/pi-kit";
import monitor from "../src/index.ts";
import type { MonitorTerminalResult } from "../src/monitor.ts";
import { formatTerminalContent } from "../src/report.ts";

export default function (pi: ExtensionAPI): void {
  const spec = JSON.parse(process.env.PI_MONITOR_TOKEN_SPEC!);
  if (spec.loaded) monitor(pi);
  if (spec.monitor_inactive) pi.on("session_start", () => {
    pi.setActiveTools(pi.getActiveTools().filter((name) => name !== "monitor_start" && name !== "monitor_stop"));
  });
  if (spec.report_variant) pi.on("tool_result", (event) => {
    if (event.toolName !== "monitor_start") return;
    const result = detailField<MonitorTerminalResult>(event.details, "result");
    if (!result) return;
    return { content: [{type:"text",text:formatTerminalContent(
      detailField<string>(event.details,"description") ?? spec.name,result,
      detailField<string>(event.details,"monitorId"),true,spec.report_variant === "native-envelope")}],
      structuredContent: event.structuredContent, details: event.details };
  });
  let step = 0;
  pi.registerProvider("monitor-token-offline", {
    api: "monitor-token-offline", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{ id: "scripted", name: "Offline context measurement", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model, context) {
      const current = step++;
      const tools = getCurrentTools(context.messages);
      const input = convertResponsesMessages(model, context, new Set([model.provider]));
      const requestTools = convertResponsesTools(tools);
      if (spec.monitor_inactive) assert.ok(!tools.some((tool) => tool.name === "monitor_start" || tool.name === "monitor_stop"));
      // Explicitly prove hidden UI/codemode fields cannot inflate this provider payload.
      const marked = structuredClone(context);
      for (const message of marked.messages) if (message.role === "toolResult") {
        Object.assign(message, { details: { marker: "HIDDEN_BOUNDARY_MARKER" },
          structuredContent: { marker: "HIDDEN_BOUNDARY_MARKER" } });
      }
      assert.deepEqual(convertResponsesMessages(model, marked, new Set([model.provider])), input);
      assert.ok(!JSON.stringify(requestTools).includes('"outputSchema"'));

      if (spec.tool === "monitor_start" && spec.expected_status) {
        for (const message of context.messages) if (message.role === "toolResult") {
          const result = detailField<MonitorTerminalResult>(message.details, "result");
          assert.ok(result);
          assert.equal(result.status, spec.expected_status);
          if (spec.expected_parse_error) {
            if (spec.expected_capture_truncation) assert.equal(result.capturesTruncated, true);
            assert.ok(result.resultParseError);
            assert.equal(result.result, undefined);
          } else if (spec.expected_length !== undefined && spec.expected_length !== null) {
            const payload = result.result;
            assert.ok(payload && typeof payload === "object" && "value" in payload);
            assert.equal(typeof payload.value, "string");
            assert.equal((payload.value as string).length, spec.expected_length);
            assert.equal(result.resultParseError, undefined);
          }
          if (Object.hasOwn(spec, "expected_result")) assert.deepEqual(result.result, spec.expected_result);
          if (spec.expected_captures) assert.deepEqual(result.captures, spec.expected_captures);
          if (spec.expected_capture_truncation) assert.equal(result.capturesTruncated, true);
          if (spec.compact) {
            const text = message.content.filter(block => block.type === "text").map(block => block.text).join("\n");
            if (text.startsWith("status=success\n") || text === "status=success") {
              assert.ok(message.toolCallId, "minimal replies require native correlation");
              assert.ok(input.some(item => item.type === "function_call_output" && item.call_id === message.toolCallId),
                "provider payload must preserve native tool-call correlation");
              assert.ok(detailField<string>(message.details, "monitorId"));
              assert.ok(detailField<string>(message.details, "description"));
            }
            let reconstructed = text;
            const match = /^payload_rle=(.*)$/m.exec(text);
            if (match) {
              const parts: Array<string | [string, number]> = JSON.parse(match[1]);
              const decoded = parts.map(part => typeof part === "string" ? part : part[0].repeat(part[1])).join("");
              const original = text.replace(/^payload_encoding=.*\npayload_rle=.*$/m, () => decoded);
              reconstructed = original;
              let baseline = formatTerminalContent(detailField<string>(message.details, "description") ?? spec.name,
                result, detailField<string>(message.details, "monitorId"));
              if (text.startsWith("status=success")) baseline = baseline.split("\n").filter(line => !/^(Monitor:|monitor_id=|elapsed=)/.test(line)).join("\n");
              assert.equal(original, baseline);
            }
            if (Object.hasOwn(spec, "expected_result")) {
              const resultLine = reconstructed.split("\n").find(line => line.startsWith("result="));
              assert.ok(resultLine, "required JSON must be present in model-facing text");
              assert.deepEqual(JSON.parse(resultLine.slice(7)), spec.expected_result);
            }
          }
        }
      }
      if (spec.batch_bash) for (const message of context.messages) if (message.role === "toolResult") {
        const lines = message.content.filter(block=>block.type === "text").map(block=>block.text).join("\n").split("\n").filter(line=>line.startsWith("DONE"));
        assert.equal(lines.length,8);
        if (Object.hasOwn(spec,"expected_result")) for (const line of lines) assert.deepEqual(JSON.parse(line.slice(5)),spec.expected_result);
      }
      if (spec.batch_jobs) for (const message of context.messages) if (message.role === "toolResult") {
        const output = message.content.filter(block=>block.type === "text").map(block=>block.text).join("\n");
        const line = output.split("\n").find(line=>line.startsWith("["));
        assert.ok(line, "batch must return every full job result");
        const jobs = JSON.parse(line);
        assert.equal(jobs.length, spec.batch_jobs);
        for (const job of jobs) {
          assert.equal(job.status, spec.expected_status);
          if (spec.expected_batch_failure) {
            assert.equal(job.result.exitCode,7);
            assert.equal(job.result.reason,"process_exit");
            assert.ok(job.monitorId);
          }
          if (Object.hasOwn(spec,"expected_result")) assert.deepEqual(job.result, spec.expected_result);
        }
      }
      const hasCall = current < spec.repeats;
      const monitorArgs = { command: spec.command, ...(!spec.minimal_arguments ? { description: spec.name } : {}), result_pattern: spec.result_pattern,
        ...(spec.failure_pattern ? { failure_pattern: spec.failure_pattern } : {}),
        ...(spec.completion ? { completion: spec.completion } : {}),
        ...(spec.compact ? { compact: true } : {}),
        ...(spec.timeout_ms !== undefined ? { timeout_ms: spec.timeout_ms } : !spec.minimal_arguments ? { timeout_ms: 5000 } : {}) };
      let code = `
        const terminal = await tools.monitor_start(${JSON.stringify(monitorArgs)});
        const expectedStatus = ${JSON.stringify(spec.expected_status)};
        if (terminal.status !== expectedStatus) throw new Error('Unexpected terminal status: ' + terminal.status);
        const result = terminal.result;
        const summary = {status:terminal.status};
        if (result.resultParseError) summary.resultParseError=result.resultParseError;
        if (result.capturesTruncated) summary.capturesTruncated=true;
        if (${JSON.stringify(spec.expected_parse_error ?? false)}) {
          if (!result.resultParseError || !result.capturesTruncated || result.result !== undefined)
            throw new Error('Missing explicit JSON truncation failure');
        }
        if (${JSON.stringify(spec.expected_capture_truncation ?? false)} && !result.capturesTruncated)
          throw new Error('Missing capture truncation disclosure');
        if (!${JSON.stringify(spec.expected_parse_error ?? false)} && ${JSON.stringify(spec.expected_length ?? null)} !== null) {
          if (typeof result.result?.value !== 'string' || result.result.value.length !== ${JSON.stringify(spec.expected_length ?? null)})
            throw new Error('JSON payload integrity failed');
          summary.valueLength=result.result.value.length;
        }
        if (terminal.status !== 'success') {
          summary.reason=result.reason;
          summary.exitCode=result.exitCode;
          summary.tail=result.output?.slice(-3);
          summary.outputTruncated=result.outputTruncated;
        }
        text(summary);
      `;
      if (spec.batch_jobs) code = `
        const jobs = await Promise.all(Array.from({length:${JSON.stringify(spec.batch_jobs)}},()=>tools.monitor_start(${JSON.stringify(monitorArgs)})));
        for (const job of jobs) {
          if (job.status !== ${JSON.stringify(spec.expected_status)} || job.result.resultParseError || job.result.capturesTruncated || job.result.outputTruncated)
            throw new Error('Invalid batch terminal result');
        }
        text(jobs.map(job=>({status:job.status,...(Object.hasOwn(job.result,'result')?{result:job.result.result}:{})})));
      `;
      if (spec.batch_code) code = spec.batch_code;
      const content: AssistantMessage["content"] = hasCall ? [{ type: "toolCall", id: `measure-${current}`,
        name: spec.tool, arguments: spec.tool === "bash" ? { command: spec.command, timeout: (spec.timeout_ms ?? 5000) / 1000 }
          : spec.tool === "codemode" ? { code } : monitorArgs,
      }] : [{ type: "text", text: "TOKEN_MEASUREMENT_COMPLETE" }];
      appendFileSync(process.env.PI_MONITOR_TOKEN_TRACE!, JSON.stringify({ step: current, input,
        tools: requestTools, hiddenFieldsExcluded: true, messages: context.messages, generated_content: content }) + "\n");
      const message: AssistantMessage = { role: "assistant", api: model.api, provider: model.provider,
        model: model.id, timestamp: Date.now(), content, stopReason: hasCall ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: message.stopReason as "stop" | "toolUse", message });
      stream.end();
      return stream;
    },
  });
}
