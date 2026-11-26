/** Memory review holds, coverage-hold repair policy, fenced responses, and truthful learning receipts. */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "bun:test";
import {
  buildLearningReceipt,
  isLearningPipelineReceipt,
  isZeroWriteReviewHold,
  learningSummaryDetails,
  learningSummarySubject,
  learningSummaryTone,
  MEMORY_REVIEW_HOLD,
} from "../extensions/learning-efficiency.ts";
import { learningReceiptComplete } from "../extensions/learning-replay.ts";

interface ScenarioRow {
  name: string;
  status: string;
  accounts: number;
  judgments: number;
}

const evidence = {
  contextEnabled: true,
  entries: [{ role: "user", content: "A project fact with one necessary condition." }],
};
const candidates = [{ name: "fact.md", content: "A project fact." }];

const coverageResponse = {
  plan: { verdict: "covered", obligations: [] },
  reviews: {
    "0": {
      scope: { basis: "optional", statement: "A bounded project fact", evidence: [{ ref: "e0.b0.l1" }] },
      claims: [{ statement: "A project fact", evidence: [{ ref: "e0.b0.l1" }], bodyQuote: "A project fact.", conditions: [] }],
      uncovered: [],
      verdict: "uncertain",
    },
  },
};
const bodyResponse = {
  reviews: { "0": { verdict: "consistent", conflictingQuotes: [], reason: "Source blind body consistency" } },
};

function fenced(value: unknown): string {
  return "```json\n" + JSON.stringify(value, null, 2) + "\n```";
}

async function fixture(): Promise<void> {
  const { mock } = await import("bun:test");
  const kit = await import("../../kit/src/index.ts");
  let workerText = "";
  mock.module("../../kit/src/index.ts", () => ({
    ...kit,
    runPiWorker: async () => ({
      exitCode: 0,
      text: workerText,
      usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: 0 },
      usageLedger: { complete: true },
    }),
  }));

  const { reviewMemoryCoverage } = await import("../extensions/memory-knowledge-coverage.ts");
  const { reviewMemoryBodies } = await import("../extensions/memory-body-review.ts");
  const coverageInput = {
    candidates, retained: [], evidence, predecessors: [],
    plan: { operations: [], newMemories: candidates },
  };

  const rows: ScenarioRow[] = [];
  const runScenario = async (name: string, text: string, kind: "coverage" | "bodies") => {
    workerText = text;
    const result: any = kind === "coverage"
      ? await reviewMemoryCoverage(coverageInput)
      : await reviewMemoryBodies({ candidates, retained: [] });
    rows.push({
      name,
      status: result.status,
      accounts: result.accounts?.length ?? -1,
      judgments: result.judgments?.length ?? -1,
    });
  };

  await runScenario("fenced-coverage", fenced(coverageResponse), "coverage");
  await runScenario("fenced-bodies", fenced(bodyResponse), "bodies");
  await runScenario("plain-json", JSON.stringify(coverageResponse), "coverage");
  await runScenario("fence-then-prose", fenced(coverageResponse) + "\nHere is my explanation.", "coverage");
  await runScenario("inner-fence", "```json\n" + JSON.stringify(coverageResponse) + "\n```markdown\nextra\n```", "coverage");
  await runScenario("unfenced-garbage", "not JSON at all", "coverage");
  await runScenario("two-fenced-objects", fenced(coverageResponse) + "\n" + fenced(coverageResponse), "coverage");
  process.stdout.write(JSON.stringify(rows));
}

if (process.argv.includes("--fixture")) await fixture();
else {
  describe("memory coverage hold", () => {
    function run(fixtureName: string, coverage = "held") {
      const result = spawnSync("bun", [fileURLToPath(new URL("./learning-policy-harness.ts", import.meta.url)), "remember-shared"], {
        cwd: fileURLToPath(new URL("../../../..", import.meta.url)),
        env: { ...process.env, TYPESAFE_API_KEY: "", CL_JEV_FIXTURE: fixtureName, CL_COVERAGE_INITIAL_RESULT: coverage },
        encoding: "utf8", timeout: 120_000, maxBuffer: 16 * 1024 * 1024,
      });
      assert.equal(result.status, 0, result.stderr);
      return JSON.parse(result.stdout.trim().split("\n").at(-1)!);
    }

    for (const kind of ["citations", "body", "description", "retained-only", "mixed-retained"]) {
      test(`uncertain coverage alone does not launch a ${kind} correction`, () => {
        const result = run(`coverage-real-repair-${kind}`);
        assert.equal(result.semanticRepairs, 0);
        assert.equal(result.totalRepairs, 0);
        assert.equal(result.coverageRepairTransports.length, 1);
        assert.equal(result.bodyReviewCalls, 1);
        assert.equal(result.registryReceipt.operations, 0);
        assert.equal(result.memoryMirrored, false);
        assert.equal(result.coverageRepairContracts.length, 0);
        assert.equal(result.coverageRepairResponses.length, 1);
        const initial = result.coverageRepairReviews.find((review: any) => review.coverage);
        assert.ok(initial.coverage.checks.every((check: any) => check.choice === "complete" && check.confidence === 0.72));
        assert.ok(Object.values(initial.checks).every((check: any) => check.positiveProbabilityLowerBound >= 0.9 && check.confidence >= 0.8));
        assert.ok(result.registryReceipt.attempts.some((attempt: any) => attempt.jev?.status === "propose" && attempt.jev.reason === "uncertain"));
        assert.equal(result.registryReceipt.attempts.filter((attempt: any) => attempt.usage?.cost === 0.004).length, 1);
        if (["retained-only", "mixed-retained"].includes(kind)) {
          assert.ok(result.correctedKnownMemory.endsWith("Existing knowledge.\n"));
          assert.equal(result.history.filter((record: any) => record.status === "applied").length, 0);
          assert.ok(result.history.every((record: any) => record.changes.length === 0));
        }
      });
    }

    test("a confirmed missing condition keeps its existing semantic correction", () => {
      const result = run("coverage-real-correction");
      assert.equal(result.semanticRepairs, 1);
      assert.equal(result.registryReceipt.operations, 1);
      assert.equal(result.memoryMirrored, true);
      assert.ok(result.conciseMemory.includes("Apply this convention only during releases."));
    });

    test("a genuine source hold keeps evidence-only correction when coverage passed", () => {
      const result = run("coverage-real-repair-source", "passed");
      assert.equal(result.semanticRepairs, 1);
      assert.equal(result.registryReceipt.operations, 1);
      assert.equal(result.coverageRepairTransports.length, 2);
      assert.equal(result.memoryMirrored, true);
    });

    test("a confirmed body contradiction still enters correction beside uncertain coverage", () => {
      const result = run("coverage-real-repair-body-conflict");
      assert.equal(result.semanticRepairs, 1);
      assert.equal(result.bodyReviewCalls, 1);
      assert.equal(result.registryReceipt.operations, 0);
      assert.equal(result.coverageRepairTransports.length, 1);
    });

    test("an invalid account cannot suppress an independently held source correction", () => {
      const result = run("coverage-real-invalid-correction");
      assert.equal(result.semanticRepairs, 1);
      assert.equal(result.registryReceipt.operations, 1);
      assert.equal(result.memoryMirrored, true);
    });
  });

  describe("zero-write Memory review holds", () => {
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
  });

  describe("truthful learning receipts", () => {
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
  });

  describe("fenced worker responses", () => {
    let rows: ScenarioRow[] | undefined;
    const observed = (): ScenarioRow[] => {
      if (rows) return rows;
      const result = spawnSync("bun", [fileURLToPath(import.meta.url), "--fixture"], {
        cwd: fileURLToPath(new URL("../../..", import.meta.url)),
        encoding: "utf8",
        timeout: 30_000,
        env: { ...process.env, TYPESAFE_API_KEY: "" },
        maxBuffer: 4 * 1024 * 1024,
      });
      assert.equal(result.status, 0, result.stderr);
      rows = JSON.parse(result.stdout) as ScenarioRow[];
      return rows;
    };
    const row = (name: string): ScenarioRow => {
      const found = observed().find((value) => value.name === name);
      assert.ok(found, `fixture reported no scenario ${name}`);
      return found;
    };

    test("a fenced coverage decision is reviewed, not rejected", () => {
      assert.equal(row("fenced-coverage").status, "reviewed");
      assert.equal(row("fenced-coverage").accounts, 1);
    });

    test("a fenced body review decision is reviewed, not rejected", () => {
      assert.equal(row("fenced-bodies").status, "reviewed");
      assert.equal(row("fenced-bodies").judgments, 1);
    });

    test("plain JSON still works", () => {
      assert.equal(row("plain-json").status, "reviewed");
    });

    test("a fence followed by prose remains rejected", () => {
      assert.equal(row("fence-then-prose").status, "invalid-response");
    });

    test("an inner fence remains rejected", () => {
      assert.equal(row("inner-fence").status, "invalid-response");
    });

    test("unfenced garbage remains rejected", () => {
      assert.equal(row("unfenced-garbage").status, "invalid-response");
    });

    test("two fenced objects remain rejected", () => {
      assert.equal(row("two-fenced-objects").status, "invalid-response");
    });
  });
}
