import assert from "node:assert/strict";
import {
  buildContextResearchPrompt,
  renderContextPromptTemplate,
  validateContextPromptTemplate,
} from "../extensions/context-prompt.ts";

const request = "Inspect {{UNKNOWN}} literally without expanding it.";
const prompt = buildContextResearchPrompt({ userResearchRequest: request, workingDirectory: "/workspace/project" });
assert.ok(prompt.includes("# Context Review"));
assert.ok(prompt.includes("## Reference Protocol"));
assert.ok(prompt.includes("## Completion Contract"));
assert.ok(prompt.includes("## Current Research Task"));
assert.ok(prompt.includes("Working directory: /workspace/project"));
assert.ok(prompt.includes(request));
assert.ok(prompt.includes("textual final answer"));
assert.equal(prompt.includes("{{USER_RESEARCH_REQUEST}}"), false);

const recursive = renderContextPromptTemplate(
  "Value: {{USER_RESEARCH_REQUEST}}",
  { userResearchRequest: "{{USER_RESEARCH_REQUEST}} stays literal", workingDirectory: "/workspace/project" },
);
assert.equal(recursive, "Value: {{USER_RESEARCH_REQUEST}} stays literal");

assert.throws(
  () => validateContextPromptTemplate("{{UNKNOWN}}"),
  /unknown placeholder/i,
);
assert.throws(
  () => validateContextPromptTemplate("No placeholder"),
  /missing placeholder/i,
);
assert.throws(
  () => renderContextPromptTemplate("{{USER_RESEARCH_REQUEST}} {{UNKNOWN}}", { userResearchRequest: "request", workingDirectory: "/workspace/project" }),
  /unknown placeholder/i,
);
assert.throws(
  () => renderContextPromptTemplate("{{USER_RESEARCH_REQUEST}} {{lowercase}}", { userResearchRequest: "request", workingDirectory: "/workspace/project" }),
  /unknown placeholder/i,
);

console.log("Context prompt builder passed: typed binding, literal nonrecursive replacement, and placeholder validation.");
