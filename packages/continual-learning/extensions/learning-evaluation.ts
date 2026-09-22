import { DEFAULT_RULES, evaluateBash, evaluateSkill, evaluateText, mergeLayers } from "./guardrail-engine";
import { evaluateLegacyTools } from "./legacy-harness";
import { sha256Digest } from "./consolidation-run";
import type { RuleLayer } from "./guardrail-types";

interface EvaluationCase { id: string; bash?: string; skill?: string; userMessage?: string; text?: string[]; expected: string | boolean }

function configuration(raw: unknown, source: string, skills: Set<string>) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error(`${source} must be a configuration object`);
  const config = mergeLayers([{ source: "built-in defaults", rules: DEFAULT_RULES.map(rule => ({ ...rule })) }, { ...raw, source } as RuleLayer], skills);
  if (config.errors.length) throw new Error(`${source}: ${config.errors.join("; ")}`);
  return config;
}

/** Curated held-out cases are supplied independently of a planner's plan.cases. */
export function evaluateLearningRules(rawSuite: unknown, baseline: unknown, candidate: unknown) {
  if (!rawSuite || typeof rawSuite !== "object") throw new Error("Evaluation suite must be an object");
  const suite = rawSuite as { version?: unknown; cases?: unknown; skills?: unknown };
  if (suite.version !== 1 || !Array.isArray(suite.cases) || suite.cases.length < 1 || suite.cases.length > 256) throw new Error("Evaluation requires version 1 and 1..256 held-out cases");
  const cases: EvaluationCase[] = [];
  const ids = new Set<string>();
  for (const raw of suite.cases) {
    if (!raw || typeof raw !== "object" || Buffer.byteLength(JSON.stringify(raw)) > 16_384) throw new Error("Invalid evaluation case");
    const item = raw as EvaluationCase;
    if (typeof item.id !== "string" || !item.id.trim() || ids.has(item.id)) throw new Error("Evaluation case ids must be unique");
    ids.add(item.id);
    if ([item.bash, item.skill, item.text].filter(value => value !== undefined).length !== 1) throw new Error("Each evaluation case needs one selector");
    if (item.userMessage !== undefined && (item.skill === undefined || typeof item.userMessage !== "string")) throw new Error("userMessage applies only to a skill evaluation case");
    if (item.bash !== undefined) {
      if (typeof item.bash !== "string" || !["execute", "confirm", "block"].includes(String(item.expected))) throw new Error("Invalid Bash evaluation case");
    } else if (typeof item.expected !== "boolean" || (item.skill !== undefined ? typeof item.skill !== "string" : !Array.isArray(item.text) || item.text.length > 64 || !item.text.every(text => typeof text === "string"))) throw new Error("Invalid guidance evaluation case");
    cases.push(item);
  }
  if (suite.skills !== undefined && (!Array.isArray(suite.skills) || !suite.skills.every(skill => typeof skill === "string"))) throw new Error("Evaluation skills must be strings");
  const skills = new Set([...(suite.skills as string[] | undefined ?? []), ...cases.flatMap(item => item.skill ? [item.skill] : [])]);
  const evaluate = (raw: unknown, source: string) => {
    const config = configuration(raw, source, skills);
    const results = cases.map(item => {
      let actual: string | boolean;
      if (item.bash !== undefined) {
        const flat = evaluateBash(config, item.bash);
        const legacy = evaluateLegacyTools(config.legacy, "bash", { command: item.bash });
        const actions = legacy.matches.map(match => match.action);
        actual = legacy.incomplete.length || flat.decision === "incomplete" ? "incomplete"
          : flat.decision === "block" || actions.includes("block") ? "block"
          : flat.decision === "confirm" || actions.includes("confirm") ? "confirm" : "execute";
      } else if (item.skill !== undefined) {
        const legacy = config.legacy.skillPrompts[item.skill];
        const legacyMatches = legacy && (!legacy.userMessagePattern || new RegExp(legacy.userMessagePattern).test(item.userMessage ?? ""));
        actual = Boolean(legacyMatches) || evaluateSkill(config, item.skill).length > 0;
      }
      else {
        const result = evaluateText(config, item.text ?? []);
        if (result.incomplete) throw new Error("Evaluation text scan is incomplete");
        actual = result.matches.length > 0;
      }
      return { id: item.id, expected: item.expected, actual, passed: actual === item.expected };
    });
    return {
      cases: results.length,
      accuracy: results.filter(result => result.passed).length / results.length,
      falseBlocks: results.filter(result => (result.expected === "execute" || result.expected === "confirm") && (result.actual === "block" || result.actual === "incomplete")).length,
      unnecessaryConfirmations: results.filter(result => result.expected === "execute" && result.actual === "confirm").length,
      missedProtections: results.filter(result => (result.expected === "block" && (result.actual === "execute" || result.actual === "confirm")) || (result.expected === "confirm" && result.actual === "execute")).length,
      results,
    };
  };
  const before = evaluate(baseline, "baseline");
  const after = evaluate(candidate, "candidate");
  return {
    kind: "independent-learning-rule-evaluation", version: 1,
    suiteDigest: sha256Digest(JSON.stringify(rawSuite)), baselineDigest: sha256Digest(JSON.stringify(baseline)), candidateDigest: sha256Digest(JSON.stringify(candidate)),
    baseline: before, candidate: after,
    regressions: after.results.filter((result, index) => !result.passed && before.results[index].passed).map(result => result.id),
    improvements: after.results.filter((result, index) => result.passed && !before.results[index].passed).map(result => result.id),
    scope: "Held-out selector and execution-policy behavior; model task quality and provider savings are not measured.",
  };
}
