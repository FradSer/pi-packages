import assert from "node:assert/strict";
import { stripVTControlCharacters } from "node:util";
import { initTheme, type ExtensionAPI, type ToolDefinition } from "@earendil-works/pi-coding-agent";
import { visibleWidth } from "@earendil-works/pi-tui";
import { registerContextGuidance } from "../extensions/context-command.ts";
import {
  buildContextResearchPrompt,
  renderContextPromptTemplate,
  validateContextPromptTemplate,
} from "../extensions/context-prompt.ts";
import registerContextTools, {
  buildResearchPrompt,
  runResearchWithFinalAnswerRetry,
} from "../extensions/context-tools.ts";

const mode = process.argv[2] ?? "all";

async function runRetryChecks(): Promise<void> {
  type Result = { text: string; stderr: string; exitCode: number; cancelled: boolean };

  const empty: Result = { text: "", stderr: "", exitCode: 0, cancelled: false };
  const answer: Result = { text: "Retry answer", stderr: "", exitCode: 0, cancelled: false };
  const calls: Array<{ query: string; finalAnswerRetry: boolean }> = [];
  const retried = await runResearchWithFinalAnswerRetry(
    "research React",
    undefined,
    undefined,
    async (query, _signal, _onUpdate, finalAnswerRetry) => {
      calls.push({ query, finalAnswerRetry });
      return calls.length === 1 ? empty : answer;
    },
  );
  assert.equal(retried.text, "Retry answer");
  assert.equal(retried.retried, true);
  assert.deepEqual(calls, [
    { query: "research React", finalAnswerRetry: false },
    { query: "research React", finalAnswerRetry: true },
  ]);
  const retryPrompt = buildResearchPrompt("research React", true);
  assert.ok(retryPrompt.includes("research React"));
  assert.ok(retryPrompt.includes("without relying on hidden reasoning"));
  assert.ok(retryPrompt.includes("repeat any inspection needed"));

  for (const terminal of [
    { text: "", stderr: "failed", exitCode: 2, cancelled: false },
    { text: "", stderr: "cancelled", exitCode: 1, cancelled: true },
  ] satisfies Result[]) {
    let count = 0;
    const result = await runResearchWithFinalAnswerRetry(
      "research React",
      undefined,
      undefined,
      async () => {
        count++;
        return terminal;
      },
    );
    assert.equal(count, 1);
    assert.equal(result.retried, false);
  }

  let emptyCount = 0;
  const twiceEmpty = await runResearchWithFinalAnswerRetry(
    "research React",
    undefined,
    undefined,
    async () => {
      emptyCount++;
      return empty;
    },
  );
  assert.equal(emptyCount, 2);
  assert.equal(twiceEmpty.text, "");
  assert.equal(twiceEmpty.retried, true);
}

function runPromptChecks(): void {
  const request = "Inspect {{UNKNOWN}} literally without expanding it.";
  const prompt = buildContextResearchPrompt({ userResearchRequest: request, workingDirectory: "/workspace/project" });
  assert.ok(prompt.includes("# Context Review"));
  assert.ok(prompt.includes("## Reference Protocol"));
  assert.ok(prompt.includes("## Completion Contract"));
  assert.ok(prompt.includes("## Current Research Task"));
  assert.ok(prompt.includes("Working directory: /workspace/project"));
  assert.ok(prompt.includes(request));
  assert.ok(prompt.includes("textual final answer"));
  assert.equal(prompt.includes("{{USER_RESEARCH_REQUEST}}"), false);

  const recursive = renderContextPromptTemplate(
    "Value: {{USER_RESEARCH_REQUEST}}",
    { userResearchRequest: "{{USER_RESEARCH_REQUEST}} stays literal", workingDirectory: "/workspace/project" },
  );
  assert.equal(recursive, "Value: {{USER_RESEARCH_REQUEST}} stays literal");

  assert.throws(() => validateContextPromptTemplate("{{UNKNOWN}}"), /unknown placeholder/i);
  assert.throws(() => validateContextPromptTemplate("No placeholder"), /missing placeholder/i);
  assert.throws(
    () => renderContextPromptTemplate("{{USER_RESEARCH_REQUEST}} {{UNKNOWN}}", { userResearchRequest: "request", workingDirectory: "/workspace/project" }),
    /unknown placeholder/i,
  );
  assert.throws(
    () => renderContextPromptTemplate("{{USER_RESEARCH_REQUEST}} {{lowercase}}", { userResearchRequest: "request", workingDirectory: "/workspace/project" }),
    /unknown placeholder/i,
  );
}

function runRenderingChecks(): void {
  initTheme("dark", false);

  let tool: ToolDefinition | undefined;
  registerContextTools({ registerTool: (definition: ToolDefinition) => { tool = definition; } } as ExtensionAPI);
  assert.ok(tool?.renderCall);
  let color = 35;
  const bgCalls: string[] = [];
  const theme = {
    fg: (_name: string, text: string) => `\x1b[${color}m${text}\x1b[39m`,
    bg: (name: string, text: string) => { bgCalls.push(name); return text; },
    bold: (text: string) => `\x1b[1m${text}\x1b[22m`,
  };
  const toolCallId = "call-context-rendering";
  for (const args of [{}, { query: undefined }, { query: null }, { query: 42 }, { query: {} }, { query: " \n " }]) {
    const pending = tool.renderCall(args, theme as never, { toolCallId } as never);
    assert.equal(
      stripVTControlCharacters(pending.render(200).join("\n")).trimEnd(),
      "[context] research started · context request",
    );
  }
  const started = tool.renderCall({ query: "  Verify   runtime behavior  " }, theme as never, { toolCallId } as never);
  const otherStarted = tool.renderCall({ query: "Inspect cancellation behavior" }, theme as never, { toolCallId: "call-context-rendering-2" } as never);
  const wideStarted = stripVTControlCharacters(started.render(200).join("\n")).trimEnd();
  assert.equal(wideStarted, "[context] research started · Verify runtime behavior");
  assert.ok(!wideStarted.includes(".md"));
  assert.equal(started.render(200).length, 2);
  assert.equal(started.render(200)[1], "");
  assert.equal(
    stripVTControlCharacters(otherStarted.render(200).join("\n")).trimEnd(),
    "[context] research started · Inspect cancellation behavior",
  );
  assert.ok(started.render(200)[0].startsWith("\x1b[35m\x1b[1m[context]"));
  for (const width of [40, 80, 160, 200, 40, 200, 0, 1, 10]) {
    assert.ok(started.render(width).every((line) => visibleWidth(line) <= width), `started row exceeds ${width}`);
  }
  color = 36;
  started.invalidate();
  assert.ok(started.render(200)[0].includes("\x1b[36m"));
  color = 35;

  assert.ok(tool.renderResult);

  for (const args of [{}, { query: "Verify runtime behavior" }, { query: " \n " }]) {
    const partial = tool.renderResult(
      { content: [{ type: "text", text: "Working..." }], details: {} },
      { expanded: false, isPartial: true },
      theme as never,
      { args, toolCallId } as never,
    );
    assert.deepEqual(partial.render(200), []);
    assert.deepEqual(partial.render(80), []);
    partial.invalidate();
  }

  const completed = tool.renderResult(
    { content: [{ type: "text", text: "Complete research answer that remains model-facing." }], details: {} },
    { expanded: false, isPartial: false },
    theme as never,
    { args: { query: "Verify runtime behavior" }, toolCallId } as never,
  );
  const collapsedText = stripVTControlCharacters(completed.render(200).join("\n"));
  assert.ok(collapsedText.includes("[context] researched · Verify runtime behavior"), `collapsed row missing researched title: ${collapsedText}`);
  for (const width of [40, 80, 160, 200]) {
    assert.ok(completed.render(width).every((line) => visibleWidth(line) <= width), `completed row exceeds ${width}`);
  }
  completed.invalidate();

  const expandedCompleted = tool.renderResult(
    { content: [{ type: "text", text: "Complete research answer that remains model-facing." }], details: {} },
    { expanded: true, isPartial: false },
    theme as never,
    { args: { query: "Verify runtime behavior" }, toolCallId } as never,
  );
  const expandedText = stripVTControlCharacters(expandedCompleted.render(200).join("\n"));
  assert.ok(expandedText.includes("Complete research answer that remains model-facing."), `expanded row missing detail text: ${expandedText}`);
  assert.ok(collapsedText.includes("to expand"), `collapsed row missing expand hint: ${collapsedText}`);

  const longAnswer = "A".repeat(400);
  const longExpanded = tool.renderResult(
    { content: [{ type: "text", text: longAnswer }], details: {} },
    { expanded: true, isPartial: false },
    theme as never,
    { args: { query: "Verify runtime behavior" }, toolCallId } as never,
  );
  const longLines = longExpanded.render(80);
  for (const line of longLines) {
    assert.ok(visibleWidth(line) <= 80, `expanded long line exceeds width: ${line}`);
  }
  const longJoined = stripVTControlCharacters(longLines.join("\n")).replace(/\s/g, "");
  assert.ok(longJoined.includes(longAnswer), "expanded details truncated instead of wrapped");

  const failed = tool.renderResult(
    { content: [{ type: "text", text: "Isolated Pi research failed\ninternal detail" }], details: {} },
    { expanded: false, isPartial: false },
    theme as never,
    { args: { query: "Verify runtime behavior" }, toolCallId, isError: true } as never,
  );
  const failedLines = failed.render(200).map((line) => stripVTControlCharacters(line).trimEnd());
  assert.ok(failedLines.some((line) => line.includes("Isolated Pi research failed")), `failed row missing error: ${failedLines.join("\n")}`);

  bgCalls.length = 0;
  completed.render(200);
  assert.ok(bgCalls.includes("toolSuccessBg"), `settled row must paint toolSuccessBg, saw: ${bgCalls.join(",")}`);
  bgCalls.length = 0;
  failed.render(200);
  assert.ok(bgCalls.includes("toolErrorBg"), `failed row must paint toolErrorBg, saw: ${bgCalls.join(",")}`);
}

async function runPromptCompositionChecks(): Promise<void> {
  const { buildSystemPrompt } = await import(
    process.env.PI_PROMPT_BUILDER ?? "../../../node_modules/@earendil-works/pi-coding-agent/dist/core/system-prompt.js"
  );
  let hook: ((event: Record<string, unknown>) => Promise<unknown> | unknown) | undefined;
  registerContextGuidance({
    on(_name: string, handler: (event: Record<string, unknown>) => Promise<unknown> | unknown) {
      hook = handler;
    },
  } as unknown as ExtensionAPI);
  assert.ok(hook);
  for (const start of [{ prompt: "research", messageType: "user" }, { messageType: "custom" }]) {
    const options = {
      cwd: process.cwd(),
      sections: { other: "retained" } as Record<string, string>,
      promptGuidelines: ["existing"],
      customPrompt: "owner",
    };
    const result = await hook({ ...start, systemPrompt: "forced owner", systemPromptOptions: options });
    const rendered = buildSystemPrompt(options);
    assert.ok(rendered.startsWith("owner"));
    assert.match(rendered, /context_get/);
    assert.match(buildSystemPrompt({ ...options, customPrompt: undefined }), /context_get/);
    assert.equal(options.sections.other, "retained");
    assert.equal(result, undefined);
    assert.equal(options.promptGuidelines[0], "existing");
    assert.deepEqual(options.promptGuidelines, ["existing"]);
    assert.match(options.sections.context_research, /context_get/);
    assert.equal(options.customPrompt, "owner");
  }
  await assert.rejects(async () => hook!({ messageType: "custom", systemPromptOptions: {} }), /structured prompt sections/);
}

if (mode === "retry" || mode === "all") await runRetryChecks();
if (mode === "prompt" || mode === "all") runPromptChecks();
if (mode === "rendering" || mode === "all") runRenderingChecks();
if (mode === "composition" || mode === "all") await runPromptCompositionChecks();
