/** Frozen routing truth table and the two Harness write-path gate split.
 * These hold regardless of which single-tool route is chosen; a refactor that
 * narrows the truth table or drops a write gate must fail here first. */
import { expect, test } from "bun:test";
import { screenLearningEntries } from "../extensions/learning-efficiency.ts";

const entry = (text: string) => ({ role: "user", content: text });
const screen = (text: string) => screenLearningEntries([entry(text)], "automatic");

test("a lasting constraint keeps its frozen both-surface screen", () => {
  for (const prompt of ["以后禁止 npm", "纠正旧规则", "require a regression test before publishing"]) {
    const value = screen(prompt);
    expect(value.memory, prompt).toBe(true);
    expect(value.harness, prompt).toBe(true);
  }
});

test("an explicit remember request is Memory-only", () => {
  const value = screen("记住这个");
  expect(value.memory).toBe(true);
  expect(value.harness).toBe(false);
  expect(value.agents).toBe(false);
});

test("a pure organize request has no durable or Harness signal", () => {
  const value = screen("整理记忆");
  expect(value.memory).toBe(false);
  expect(value.harness).toBe(false);
  expect(value.agents).toBe(false);
});

test("an ordinary task screens to no learning surface", () => {
  const value = screen("Thanks, run the tests now");
  expect(value.memory).toBe(false);
  expect(value.harness).toBe(false);
  expect(value.agents).toBe(false);
});

const source = async (name: string) => Bun.file(new URL(`../extensions/${name}`, import.meta.url)).text();

test("the interactive Harness path keeps consent and exact-byte gates", async () => {
  const text = await source("guardrails.ts");
  for (const marker of ["ctx.hasUI", "ui.select", "isDeepStrictEqual", "recheckHarnessWriteApproval"]) {
    expect(text.includes(marker), marker).toBe(true);
  }
});

test("the automatic Harness path keeps validation, receipt and undo gates", async () => {
  const text = await source("harness-consolidation.ts");
  for (const marker of ["validateHarnessPlan", "recordLearningMutation", "buildHarnessReceipt", "readback", "rollback"]) {
    expect(text.includes(marker), marker).toBe(true);
  }
});

test("planner-child structured-output contracts are not removed with the tools", async () => {
  const text = await source("planner-json-output.ts");
  expect(text.includes("registerFlag")).toBe(true);
});

test("the learning_read evidence marker stays a frozen token", async () => {
  const text = await source("tool-surface.ts");
  expect(text.includes('learningRead: "learning_read"')).toBe(true);
});
