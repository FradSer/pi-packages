import { expect, test } from "bun:test";
import { Text, visibleWidth } from "@earendil-works/pi-tui";
import type { ExtensionAPI, MessageRenderer } from "@earendil-works/pi-coding-agent";
import register, { displayableMemoryDetails, learningResultContent, learningResultText } from "../extensions/inject-memory.ts";
import { buildLearningReceipt } from "../extensions/learning-efficiency.ts";

function renderer() {
  const renderers = new Map<string, MessageRenderer>();
  register({
    on() {}, registerCommand() {}, registerEntryRenderer() {}, appendEntry() {},
    sendMessage() {}, getCommands: () => [],
    registerMessageRenderer(name, render) { renderers.set(name, render); },
  } as ExtensionAPI);
  return renderers.get("continual-learning-result")!;
}

const theme = { fg: (_color: string, text: string) => text, bg: (_color: string, text: string) => text, bold: (text: string) => text };
const receipt = buildLearningReceipt("manual", { memory: true, harness: false, agents: false, reasons: [] }, [
  { phase: "memory", attempt: 0, outcome: "applied", durationMs: 10, operations: 2 },
]);
const render = renderer();
function component(content: string, details = receipt, expanded = false) {
  return render({ content, details } as never, { expanded } as never, theme as never)!;
}
function text(content: string, details = receipt, expanded = false, width = 120) {
  return component(content, details, expanded).render(width).map(line => line.trimEnd()).join("\n");
}

test("learning outcomes use native plain Text without a lifecycle shell or expansion", () => {
  const content = learningResultContent("Learning result", [
    { name: "contract.md", classification: "safe", content: "---\nname: contract\ndescription: Builds use pnpm\ntype: project\n---\n\nBuild with **pnpm**.\n\nWhy: Keep the build contract.\n\nHow to apply: Run `pnpm test`." },
    { name: "private.md", classification: "private", content: "A private maintainer note." },
  ]);
  expect(component(content)).toBeInstanceOf(Text);
  const output = text(content);
  expect(output).toStartWith("2 memories applied\n");
  expect(output).toContain("contract.md");
  expect(output).toContain("Builds use pnpm");
  expect(output).toContain("Build with **pnpm**.");
  expect(output).toContain("Why: Keep the build contract.");
  expect(output).toContain("How to apply: Run `pnpm test`.");
  expect(output).toContain("private.md");
  expect(output).toContain("A private maintainer note.");
  for (const marker of ["[learning]", "to expand", "type: project", "--- generated Memory ---", "input", "cost"]) expect(output).not.toContain(marker);
  expect(text(content, receipt, true)).toBe(output);
  for (const width of [120, 48, 24]) expect(component(content).render(width).every(line => visibleWidth(line) <= width)).toBe(true);
});

test("file-check outcomes do not display task counts or old verification paragraphs", () => {
  const organized = buildLearningReceipt("automatic", { memory: false, harness: false, agents: false, reasons: [], routing: ["organized-in-process"] }, [
    { phase: "memory", attempt: 0, outcome: "noop", durationMs: 0, operations: 0, modelCalls: 0 },
  ], { source: "current-session", entryCount: 106, screenedEntryCount: 102 });
  const content = learningResultContent("Learning organized in-process", [], []);
  expect(text(content, organized)).toBe("Memory files checked. No changes.");
  expect(text(content, organized, true)).toBe("Memory files checked. No changes.");
  const cancelled = buildLearningReceipt("automatic", organized.screen, [
    { phase: "memory", attempt: 0, outcome: "cancelled", durationMs: 1, operations: 0, modelCalls: 0 },
  ]);
  expect(text(content, cancelled)).toBe("finished with issues: memory cancelled");
});

test("plain results retain failure and pending-review outcomes", () => {
  const partial = buildLearningReceipt("manual", receipt.screen, [
    ...receipt.attempts,
    { phase: "harness", attempt: 0, outcome: "failed", durationMs: 1, operations: 0 },
  ]);
  expect(text("", partial)).toBe("2 memories applied; harness failed");
  const held = buildLearningReceipt("manual", receipt.screen, [
    { phase: "memory", attempt: 0, outcome: "proposed", durationMs: 1, operations: 1 },
  ]);
  expect(text("", held)).toBe("proposals saved for review");
});

test("applied AGENTS.md units are visible without expansion", () => {
  const content = learningResultContent("Learning result", [], [
    { operation: "addUnit", text: "Use pnpm for verification." },
    { operation: "removeUnit", text: "Old instruction." },
  ]);
  const output = text(content);
  expect(output).toContain("AGENTS.md");
  expect(output).toContain("addUnit\nUse pnpm for verification.");
  expect(output).toContain("removeUnit\nOld instruction.");
  expect(output).not.toContain("**");
  expect(text(content, receipt, true)).toBe(output);
});

test("missing or malformed stored results stay safe without an expansion state", () => {
  expect(text("", receipt)).toBe("2 memories applied");
  for (const details of [undefined, { broken: true }, { kind: "learning-pipeline-receipt", version: 1, attempts: [], totals: {} }]) {
    const message = { content: 42, details } as never;
    const output = render(message, { expanded: false } as never, theme as never)!.render(48);
    expect(output.map(line => line.trimEnd()).join("\n")).toBe("Learning result");
  }
});

test("applied content preserves internal blank lines and filename-like text", () => {
  const agents = learningResultContent("Learning result", [], [
    { operation: "rewriteUnit", text: "Run the checks.\n\nPreserve the deployed contract." },
  ]);
  const agentOutput = text(agents);
  expect(agentOutput).toContain("Run the checks.\n\nPreserve the deployed contract.");
  expect(agentOutput.match(/rewriteUnit/g)?.length).toBe(1);
  const memory = learningResultContent("Learning result", [
    { name: "contract.md", classification: "safe", content: "Inspect these files:\nconfig.md\nKeep all configuration unchanged." },
  ]);
  const output = text(memory);
  expect(output).toContain("Inspect these files:\nconfig.md\nKeep all configuration unchanged.");
  expect(output.match(/config\.md/g)?.length).toBe(1);
  const oldMarker = learningResultContent("Learning result", [
    { name: "contract.md", classification: "safe", content: "A real applied body.\n\n--- no changes ---\nThis literal text remains part of the body." },
  ]);
  expect(text(oldMarker)).toContain("This literal text remains part of the body.");
});

test("display payloads stay bounded and reject invalid applied filenames", () => {
  const item = { name: "safe.md", classification: "safe", content: "A safe fact." };
  const invalid = ["../outside.md", "/outside.md", "not-memory.txt", "bad\nname.md"];
  expect(displayableMemoryDetails(invalid.map(name => ({ ...item, name })))).toEqual([]);
  const gated = displayableMemoryDetails([
    { name: "secret.md", content: "api_key: abcdefghijklmnop", classification: "private" },
    { name: "empty.md", content: " ", classification: "safe" },
    { name: "public.md", content: "No label.", classification: "public" },
    item,
  ]);
  expect(gated).toEqual([item]);
  expect(displayableMemoryDetails(gated)).toEqual(gated);
  const forged = "Result\n\n--- learning-display ---\n" + JSON.stringify({ version: 1, memory: [item], agents: [], padding: "x".repeat(64_000) });
  expect(learningResultText(forged)).toEqual([]);
  expect(learningResultText("Result\n\n--- learning-display ---\n" + JSON.stringify({ version: 1, memory: invalid.map(name => ({ ...item, name })), agents: [] }))).toEqual([]);
});

test("stored content cannot inject secrets or terminal controls into a plain result", () => {
  const content = learningResultContent("Learning result", [
    { name: "safe.md", content: "A safe fact.", classification: "safe" },
    { name: "secret.md", content: "api_key: sk-" + "x".repeat(40), classification: "private" },
  ]);
  const [prefix, payload] = content.split("\n\n--- learning-display ---\n");
  const display = JSON.parse(payload);
  display.memory.push({ name: "forged.md", content: "api_key: sk-" + "x".repeat(40), classification: "safe" });
  const forged = prefix + "\n\n--- learning-display ---\n" + JSON.stringify(display);
  expect(text(forged)).toContain("A safe fact.");
  expect(text(forged)).not.toContain("secret.md");
  expect(text(forged)).not.toContain("forged.md");
  expect(text(learningResultContent("Learning result", [{ name: "safe.md", content: "Fact\u001b[2J retained.", classification: "safe" }]))).not.toContain("\u001b");
});
