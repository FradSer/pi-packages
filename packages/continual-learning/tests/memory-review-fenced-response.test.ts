/** Worker responses may arrive wrapped in a single Markdown JSON fence.
 * The parent must parse them without accepting trailing prose or extra objects.
 *
 * The worker stand-in is a module mock, and Bun keeps a mocked module bound for
 * the rest of the process even after a restore, so every scenario runs in one
 * child process. pi-kit's real exports then stay intact for every other test
 * file in the same `bun test` run, whatever order Bun loads them in. */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

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
  const run = async (name: string, text: string, kind: "coverage" | "bodies") => {
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

  await run("fenced-coverage", fenced(coverageResponse), "coverage");
  await run("fenced-bodies", fenced(bodyResponse), "bodies");
  await run("plain-json", JSON.stringify(coverageResponse), "coverage");
  await run("fence-then-prose", fenced(coverageResponse) + "\nHere is my explanation.", "coverage");
  await run("inner-fence", "```json\n" + JSON.stringify(coverageResponse) + "\n```markdown\nextra\n```", "coverage");
  await run("unfenced-garbage", "not JSON at all", "coverage");
  await run("two-fenced-objects", fenced(coverageResponse) + "\n" + fenced(coverageResponse), "coverage");
  process.stdout.write(JSON.stringify(rows));
}

if (process.argv.includes("--fixture")) await fixture();
else {
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
}
