/** Entry-scoped routing for the single learn tool (Phase 1, option B). */
import { expect, test } from "bun:test";
import { classifyLearnRoute, lastUserText } from "../extensions/learn-intent.ts";
import { screenLearningEntries } from "../extensions/learning-efficiency.ts";

const user = (text: string) => ({ type: "message", id: "u", message: { role: "user", content: [{ type: "text", text }] } });

test("an explicit Harness request routes to Harness, not Memory", () => {
  for (const prompt of ["以后禁止 npm", "纠正旧规则", "永久约束这条命令", "require a regression test before publishing"]) {
    expect(classifyLearnRoute(prompt), prompt).toBe("harness");
  }
});

test("an explicit Memory request routes to Memory", () => {
  for (const prompt of ["整理记忆", "记住这个", "remember this", "consolidate memory"]) {
    expect(classifyLearnRoute(prompt), prompt).toBe("memory");
  }
});

test("ordinary tasks and negated remember text do not route", () => {
  for (const prompt of ["Thanks, run the tests now", "do not remember this token", "不要整理记忆", "", "   "]) {
    expect(classifyLearnRoute(prompt), prompt).toBe("none");
  }
});

test("an unrelated privacy caveat does not cancel an explicit request", () => {
  const cases: Array<[string, "harness" | "memory"]> = [
    ["以后禁止 npm，别记住 token", "harness"],
    ["Please remember this but do not store my API key", "memory"],
    ["整理记忆, and never persist my token", "memory"],
    ["以后禁止 npm。这条是永久规则，不是临时要求", "harness"],
  ];
  for (const [prompt, expected] of cases) expect(classifyLearnRoute(prompt), prompt).toBe(expected);
});

test("generic lasting-rule wording routes to Harness", () => {
  for (const prompt of [
    "Never allow direct database writes in future tasks",
    "From now on, always run the linter before committing",
    "Add a lasting rule for release checks",
    "要求发布前增加回归测试",
  ]) expect(classifyLearnRoute(prompt), prompt).toBe("harness");
});

test("a quoted command name in an explanation does not trigger a route", () => {
  for (const prompt of [
    '"以后禁止 npm" is written in the README, please explain it',
    'The documentation says "remember this" is a command',
    "请解释文档里引用的「整理记忆」是什么意思",
  ]) expect(classifyLearnRoute(prompt), prompt).toBe("none");
});

test("only the last real user entry supplies the request", () => {
  const entries = [user("整理记忆"), { role: "assistant", content: "以后禁止 npm" }, user("记住这个")];
  expect(lastUserText(entries)).toBe("记住这个");
  expect(classifyLearnRoute(lastUserText(entries))).toBe("memory");
});

test("tool and assistant text never supplies the request", () => {
  const entries = [{ role: "toolResult", content: "以后禁止 npm" }, { role: "assistant", content: "整理记忆" }];
  expect(lastUserText(entries)).toBe("");
  expect(classifyLearnRoute(lastUserText(entries))).toBe("none");
});

test("the frozen evidence screen keeps its own both-surface truth table", () => {
  // This classifier does not narrow or reclassify screenLearningEntries.
  for (const prompt of ["以后禁止 npm", "纠正旧规则", "require a regression test before publishing"]) {
    const screen = screenLearningEntries([user(prompt)], "automatic");
    expect(screen.memory, prompt).toBe(true);
    expect(screen.harness, prompt).toBe(true);
    expect(classifyLearnRoute(prompt), prompt).toBe("harness");
  }
});
