import {isDeepStrictEqual} from "node:util";
import {evaluateBash, evaluateSkill, evaluateText, mergeLayers} from "./guardrail-engine.ts";
import type {RuleLayer} from "./guardrail-types.ts";

export interface HarnessPreviewCase {ruleId: string; input: string; matches: boolean}
export function previewHarnessCandidate(content: string, cases: readonly HarnessPreviewCase[], skills: ReadonlySet<string>, previous?: unknown, commandExamples: ReadonlySet<string> = new Set()): {passed: boolean; errors: string[]; cases: Array<{ruleId: string; expected: boolean; actual: boolean}>} {
  const errors: string[] = [];
  const results: Array<{ruleId: string; expected: boolean; actual: boolean}> = [];
  const fail = (message: string) => ({passed: false, errors: [message], cases: results});
  if (typeof content !== "string" || content.length > 128000 || !Array.isArray(cases) || cases.length > 64) return fail("Preview input exceeds bounds");
  let candidate: RuleLayer;
  try { candidate = JSON.parse(content); } catch { return fail("Candidate must be valid JSON"); }
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return fail("Candidate must be a configuration object");
  const config = mergeLayers([{...candidate, source: "preview"}], skills);
  if (previous === undefined && !config.rules.length) return fail("First creation requires a supported rule declaration, not an empty placeholder");
  if (config.errors.length) return {passed: false, errors: config.errors, cases: results};
  const prior = previous && typeof previous === "object" && "rules" in previous && Array.isArray(previous.rules) ? previous.rules : [];
  const changed = config.rules.filter(rule => rule.enabled !== false && !prior.some(old => old && typeof old === "object" && old.id === rule.id && isDeepStrictEqual(old, candidate.rules?.find(item => item.id === rule.id))));
  for (const fixture of cases) {
    if (!fixture || typeof fixture.ruleId !== "string" || typeof fixture.input !== "string" || fixture.input.length > 8000 || typeof fixture.matches !== "boolean") return fail("Invalid preview fixture");
    const rule = config.rules.find(rule => rule.id === fixture.ruleId && rule.enabled !== false);
    if (!rule) { errors.push("Fixture refers to an absent or disabled rule"); continue; }
    const actual = "text" in rule ? evaluateText(config, [fixture.input]).matches.some(match => match.id === rule.id)
      : "bash" in rule ? evaluateBash(config, fixture.input).matchedRules.some(match => match.id === rule.id)
      : evaluateSkill(config, fixture.input).some(match => match.id === rule.id);
    results.push({ruleId: rule.id, expected: fixture.matches, actual});
    if (actual !== fixture.matches) errors.push(`Rule ${rule.id}: fixture did not match its expected result`);
  }
  for (const rule of changed) {
    if ("bash" in rule && !cases.some(fixture => fixture.ruleId === rule.id && fixture.matches && commandExamples.has(fixture.input) && results.some(result => result.ruleId === rule.id && result.expected && result.actual))) errors.push(`Rule ${rule.id}: Bash requires an exact quoted user command or successful observed Bash command as a positive fixture; use scoped text guidance or ask for a command example`);
    if (![true, false].every(expected => results.some(result => result.ruleId === rule.id && result.expected === expected && result.actual === expected))) errors.push(`Rule ${rule.id}: requires a passing positive and negative fixture`);
  }
  return {passed: errors.length === 0, errors, cases: results};
}
