/** Zero-write Memory review holds are policy holds, not pipeline failures. */
import { expect, test } from "bun:test";
import {
  buildLearningReceipt, learningSummarySubject, learningSummaryTone,
  isZeroWriteReviewHold, MEMORY_REVIEW_HOLD,
} from "../extensions/learning-efficiency.ts";
import { learningReceiptComplete } from "../extensions/learning-replay.ts";

const screen = () => ({ memory: true, harness: false, agents: false, reasons: ["agent-requested-learning"] });
const usage = { input: 3, output: 2, cacheRead: 0, cacheWrite: 0, totalTokens: 5, cost: 0.1 };
const hold = (diagnostic: string, outcome = "failed") => ({
  phase: "memory" as const, attempt: 0, outcome: outcome as "failed",
  operations: 0, durationMs: 4, usage, diagnostic,
});

const HOLD_DIAGNOSTICS = [
  "Jev propose: uncertain",
  "Independent Memory coverage account: invalid-response; diagnostic only.",
  "Retained Memory review remains unresolved; no corrective operation was proposed. No files changed.",
  "Semantic Memory repair changed protected intent.",
];

test("only zero-write review decisions are classified as holds", () => {
  for (const d of HOLD_DIAGNOSTICS) expect(isZeroWriteReviewHold(hold(d))).toBe(true);
  expect(isZeroWriteReviewHold({ ...hold(HOLD_DIAGNOSTICS[0]!), operations: 1 })).toBe(false);
  expect(isZeroWriteReviewHold(hold("memory planner model error"))).toBe(false);
  expect(isZeroWriteReviewHold(hold("Memory worker could not prepare its frozen prompt; no planner started."))).toBe(false);
});

test("a zero-write review hold is skipped, held, and replayable", () => {
  const receipt = buildLearningReceipt("automatic", screen(), [hold(HOLD_DIAGNOSTICS[0]!)]);
  expect(receipt.screen.reasons).toContain(MEMORY_REVIEW_HOLD);
  const finalMemory = receipt.attempts.filter(a => a.phase === "memory").at(-1)!;
  expect(finalMemory.outcome).toBe("skipped");
  expect(finalMemory.operations).toBe(0);
  expect(finalMemory.diagnostic).toBe(HOLD_DIAGNOSTICS[0]);
  expect(finalMemory.outcome).not.toMatch(/failed|rejected|cancelled/);
  expect(learningSummarySubject(receipt)).toBe("held by Memory review");
  expect(learningSummaryTone(receipt)).toBe("warning");
  expect(learningReceiptComplete(receipt)).toBe(false);
});

test("a real planner failure stays a failure", () => {
  const receipt = buildLearningReceipt("automatic", screen(), [hold("memory planner model error")]);
  expect(receipt.screen.reasons).not.toContain(MEMORY_REVIEW_HOLD);
  expect(receipt.attempts[0]!.outcome).toBe("failed");
  expect(learningSummarySubject(receipt)).toBe("finished with issues: memory failed");
  expect(learningSummaryTone(receipt)).toBe("error");
  expect(learningReceiptComplete(receipt)).toBe(false);
});

test("an explicit verification refusal is never masked by an undecidable hold", () => {
  const receipt = buildLearningReceipt("automatic", screen(), [
    hold("Independent Memory coverage account: invalid-response; diagnostic only."),
    hold("Jev propose: unsupported"),
  ]);
  expect(receipt.screen.reasons).not.toContain(MEMORY_REVIEW_HOLD);
  expect(receipt.attempts.every(a => a.outcome === "failed")).toBe(true);
  expect(learningSummarySubject(receipt)).toBe("finished with issues: memory failed");
  expect(learningReceiptComplete(receipt)).toBe(false);
});

test("an applied change is never reclassified as a hold", () => {
  const applied = { phase: "memory" as const, attempt: 0, outcome: "applied" as const, operations: 1, durationMs: 4, usage };
  const receipt = buildLearningReceipt("automatic", screen(), [hold(HOLD_DIAGNOSTICS[1]!), applied]);
  expect(receipt.screen.reasons).not.toContain(MEMORY_REVIEW_HOLD);
  expect(learningSummarySubject(receipt)).toBe("1 memory applied");
  expect(learningReceiptComplete(receipt)).toBe(true);
});
