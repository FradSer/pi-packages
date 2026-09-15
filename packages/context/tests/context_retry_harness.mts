import assert from "node:assert/strict";
import {
  buildResearchPrompt,
  runResearchWithFinalAnswerRetry,
} from "../extensions/context-tools.ts";

type Result = { text: string; stderr: string; exitCode: number; cancelled: boolean };

const empty: Result = { text: "", stderr: "", exitCode: 0, cancelled: false };
const answer: Result = { text: "Retry answer", stderr: "", exitCode: 0, cancelled: false };
const calls: Array<{ query: string; toolCallId: string; finalAnswerRetry: boolean }> = [];
const retried = await runResearchWithFinalAnswerRetry(
  "research React",
  "call-1",
  undefined,
  undefined,
  async (query, toolCallId, _signal, _onUpdate, finalAnswerRetry) => {
    calls.push({ query, toolCallId, finalAnswerRetry });
    return calls.length === 1 ? empty : answer;
  },
);
assert.equal(retried.text, "Retry answer");
assert.equal(retried.retried, true);
assert.deepEqual(calls, [
  { query: "research React", toolCallId: "call-1", finalAnswerRetry: false },
  { query: "research React", toolCallId: "call-1", finalAnswerRetry: true },
]);
const retryPrompt = buildResearchPrompt("research React", "call-1");
assert.ok(retryPrompt.includes("research React"));

for (const terminal of [
  { text: "", stderr: "failed", exitCode: 2, cancelled: false },
  { text: "", stderr: "cancelled", exitCode: 1, cancelled: true },
] satisfies Result[]) {
  let count = 0;
  const result = await runResearchWithFinalAnswerRetry(
    "research React",
    "call-terminal",
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
  "call-empty",
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
