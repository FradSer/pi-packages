import assert from "node:assert/strict";
import {
  buildResearchPrompt,
  runResearchWithFinalAnswerRetry,
} from "../extensions/context-tools.ts";

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
