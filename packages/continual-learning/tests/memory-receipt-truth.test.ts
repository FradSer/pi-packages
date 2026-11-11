/** Truthful learning receipts: screened scope, evidence vs routing, no dangling proposals. */
import { expect, test } from "bun:test";
import {
  buildLearningReceipt, isLearningPipelineReceipt, learningSummaryDetails, learningSummarySubject,
} from "../extensions/learning-efficiency.ts";

const screen = (reasons: string[]) => ({ memory: true, harness: false, agents: false, reasons });
const zeros = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: 0 };

test("receipt records how many frozen entries the evidence screen actually examined", () => {
  const receipt = buildLearningReceipt("automatic", screen(["no-durable-memory-evidence"]), [],
    { source: "current-session", entryCount: 839, screenedEntryCount: 2 });
  expect(isLearningPipelineReceipt(receipt)).toBe(true);
  expect(receipt.input?.screenedEntryCount).toBe(2);
  const details = learningSummaryDetails(receipt).join("\n");
  expect(details).toContain("839 entries");
  expect(details).toContain("2 screened");
});

test("evidence reasons and routing decisions are separate fields on the screen", () => {
  const receipt = buildLearningReceipt("automatic", {
    memory: true, harness: false, agents: false,
    reasons: ["no-durable-memory-evidence"],
    routing: ["harness-disabled-by-policy", "agents-disabled-by-policy", "memory-enabled-by-agent-request"],
  }, [], { source: "current-session", entryCount: 226, screenedEntryCount: 2 });
  expect(isLearningPipelineReceipt(receipt)).toBe(true);
  expect(receipt.screen.reasons).toEqual(["no-durable-memory-evidence"]);
  expect(receipt.screen.routing).toEqual([
    "harness-disabled-by-policy", "agents-disabled-by-policy", "memory-enabled-by-agent-request"]);
  const details = learningSummaryDetails(receipt).join("\n");
  expect(details).toContain("harness-disabled-by-policy");
});

test("a zero-operation proposed attempt is not reported as a proposal for external action", () => {
  const receipt = buildLearningReceipt("automatic", screen(["agent-requested-learning"]), [
    { phase: "selector", attempt: 0, outcome: "applied", operations: 0, durationMs: 1 },
    { phase: "memory", attempt: 0, outcome: "proposed", operations: 0, durationMs: 1, usage: zeros },
  ], { source: "current-session", entryCount: 226, screenedEntryCount: 2 });
  expect(learningSummarySubject(receipt)).not.toContain("proposals saved for review");
  expect(learningSummarySubject(receipt)).toContain("no changes written");
});

test("a genuine proposal with operations still reports that a proposal was saved", () => {
  const receipt = buildLearningReceipt("automatic", screen(["agent-requested-learning"]), [
    { phase: "memory", attempt: 0, outcome: "proposed", operations: 1, pendingOperations: 1, durationMs: 1, usage: zeros },
  ]);
  expect(learningSummarySubject(receipt)).toContain("proposals saved for review");
});
