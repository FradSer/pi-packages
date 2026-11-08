/** Worker responses may arrive wrapped in a single Markdown JSON fence.
 * The parent must parse them without accepting trailing prose or extra objects. */
import { expect, mock, test } from "bun:test";

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

test("a fenced coverage decision is reviewed, not rejected", async () => {
  workerText = fenced(coverageResponse);
  const result = await reviewMemoryCoverage({
    candidates, retained: [], evidence, predecessors: [], plan: { operations: [], newMemories: candidates },
  });
  expect(result.status).toBe("reviewed");
  expect(result.accounts).toHaveLength(1);
});

test("a fenced body review decision is reviewed, not rejected", async () => {
  workerText = fenced(bodyResponse);
  const result = await reviewMemoryBodies({ candidates, retained: [] });
  expect(result.status).toBe("reviewed");
  expect(result.judgments).toHaveLength(1);
});

test("plain JSON still works", async () => {
  workerText = JSON.stringify(coverageResponse);
  const result = await reviewMemoryCoverage({
    candidates, retained: [], evidence, predecessors: [], plan: { operations: [], newMemories: candidates },
  });
  expect(result.status).toBe("reviewed");
});

test("a fence followed by prose remains rejected", async () => {
  workerText = fenced(coverageResponse) + "\nHere is my explanation.";
  const result = await reviewMemoryCoverage({
    candidates, retained: [], evidence, predecessors: [], plan: { operations: [], newMemories: candidates },
  });
  expect(result.status).toBe("invalid-response");
});

test("an inner fence remains rejected", async () => {
  workerText = "```json\n" + JSON.stringify(coverageResponse) + "\n```markdown\nextra\n```";
  const result = await reviewMemoryCoverage({
    candidates, retained: [], evidence, predecessors: [], plan: { operations: [], newMemories: candidates },
  });
  expect(result.status).toBe("invalid-response");
});

test("unfenced garbage remains rejected", async () => {
  workerText = "not JSON at all";
  const result = await reviewMemoryCoverage({
    candidates, retained: [], evidence, predecessors: [], plan: { operations: [], newMemories: candidates },
  });
  expect(result.status).toBe("invalid-response");
});

test("two fenced objects remain rejected", async () => {
  workerText = fenced(coverageResponse) + "\n" + fenced(coverageResponse);
  const result = await reviewMemoryCoverage({
    candidates, retained: [], evidence, predecessors: [], plan: { operations: [], newMemories: candidates },
  });
  expect(result.status).toBe("invalid-response");
});
