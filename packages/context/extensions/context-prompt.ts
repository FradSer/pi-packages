import { readFileSync } from "node:fs";

export interface ContextResearchPromptBindings {
  userResearchRequest: string;
  workingDirectory: string;
}

const CONTEXT_REVIEW_COMPLETION = [
  "Return one self-contained review of the requested context.",
  "State the conclusion, cite concrete evidence, and distinguish observed facts from uncertainty.",
  "Finish with a textual final answer rather than ending after a tool call.",
].join(" ");

const CONTEXT_RESEARCH_TEMPLATE_URL = new URL("../prompts/context-research.md", import.meta.url);
const PLACEHOLDER_PATTERN = /\{\{([A-Z][A-Z0-9_]*)\}\}/g;
const PLACEHOLDER_TOKEN_PATTERN = /\{\{[^{}]+\}\}/g;
const REQUIRED_PLACEHOLDERS = ["USER_RESEARCH_REQUEST"] as const;

function templatePlaceholders(template: string): string[] {
  return [...template.matchAll(PLACEHOLDER_PATTERN)].map((match) => match[1]);
}

function placeholderTokens(template: string): string[] {
  return template.match(PLACEHOLDER_TOKEN_PATTERN) ?? [];
}

export function validateContextPromptTemplate(template: string): void {
  const placeholders = templatePlaceholders(template);
  const allowedTokens = new Set(REQUIRED_PLACEHOLDERS.map((placeholder) => `{{${placeholder}}}`));
  const unknown = [...new Set(placeholderTokens(template).filter((token) => !allowedTokens.has(token)))];
  if (unknown.length > 0) {
    throw new Error(`Context prompt has unknown placeholder(s): ${unknown.join(", ")}`);
  }
  const missing = REQUIRED_PLACEHOLDERS.filter((placeholder) => !placeholders.includes(placeholder));
  if (missing.length > 0) {
    throw new Error(`Context prompt has missing placeholder(s): ${missing.join(", ")}`);
  }
}

export function renderContextPromptTemplate(
  template: string,
  bindings: ContextResearchPromptBindings,
): string {
  validateContextPromptTemplate(template);
  const rendered = template.replace(
    "{{USER_RESEARCH_REQUEST}}",
    () => bindings.userResearchRequest,
  );
  const bindingTokens = new Set(placeholderTokens(bindings.userResearchRequest));
  const unexpected = placeholderTokens(rendered).filter((token) => !bindingTokens.has(token));
  if (unexpected.length > 0) {
    throw new Error(`Context prompt has unresolved placeholder(s): ${[...new Set(unexpected)].join(", ")}`);
  }
  return rendered;
}

const CONTEXT_RESEARCH_TEMPLATE = readFileSync(CONTEXT_RESEARCH_TEMPLATE_URL, "utf8").trim();

export function buildContextResearchPrompt(bindings: ContextResearchPromptBindings): string {
  const protocol = renderContextPromptTemplate(CONTEXT_RESEARCH_TEMPLATE, bindings);
  return [
    "# Context Review",
    "",
    "## Current Research Task",
    `Working directory: ${bindings.workingDirectory}`,
    "",
    bindings.userResearchRequest,
    "",
    "## Reference Protocol",
    protocol,
    "",
    "## Completion Contract",
    CONTEXT_REVIEW_COMPLETION,
  ].join("\n");
}
