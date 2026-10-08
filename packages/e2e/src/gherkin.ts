import type {
  Clause,
  ClauseKind,
  FeatureFile,
  FeatureSection,
  RuleGroup,
  Scenario,
} from "./types.ts";

/** A .feature file structure this parser does not accept, with its line number. */
export class GherkinError extends Error {
  readonly line: number;

  constructor(message: string, line: number) {
    super(`${message} (line ${line})`);
    this.name = "GherkinError";
    this.line = line;
  }
}

const STEP_KINDS: Record<string, ClauseKind | "and" | "but"> = {
  Given: "given",
  When: "when",
  Then: "then",
  And: "and",
  But: "but",
};

type ScenarioDraft = { name: string; tags: readonly string[]; clauses: Clause[] };
type RuleDraft = { name: string; tags: readonly string[]; background: Clause[]; scenarios: Scenario[]; hasBackground: boolean };
type FeatureDraft = {
  name: string;
  tags: readonly string[];
  description: string[];
  background: Clause[];
  scenarios: Scenario[];
  rules: RuleGroup[];
  hasBackground: boolean;
  rule?: RuleDraft;
};

/** Parse multiple Feature sections with their Rule and Background scopes. */
export function parseFeature(source: string): FeatureFile {
  const lines = source.split("\n");
  const features: FeatureSection[] = [];
  const scenarios: Scenario[] = [];
  const scenarioNames = new Set<string>();
  let feature: FeatureDraft | undefined;
  let scenario: ScenarioDraft | undefined;
  let pendingTags: string[] = [];
  let backgroundTarget: Clause[] | undefined;
  let backgroundIndent = -1;
  let lastKind: ClauseKind | undefined;
  let lastStepIndent = -1;
  let thenCount = 0;

  const flushScenario = (): void => {
    if (!scenario) return;
    if (!feature) throw new GherkinError("Scenario must belong to a Feature", lines.length);
    if (!scenario.clauses.some((clause) => clause.kind === "then")) {
      throw new GherkinError(`Scenario "${scenario.name}" needs a Then clause`, lines.length);
    }
    const rule = feature.rule;
    const parsed: Scenario = {
      feature: feature.name,
      featureTags: feature.tags,
      name: scenario.name,
      ...(rule ? { rule: rule.name } : {}),
      ruleTags: rule?.tags ?? [],
      tags: [...feature.tags, ...(rule?.tags ?? []), ...scenario.tags],
      background: [...feature.background, ...(rule?.background ?? [])],
      featureBackground: [...feature.background],
      ruleBackground: [...(rule?.background ?? [])],
      clauses: scenario.clauses,
    };
    scenarios.push(parsed);
    if (rule) rule.scenarios.push(parsed);
    else feature.scenarios.push(parsed);
    scenario = undefined;
  };

  const flushRule = (): void => {
    flushScenario();
    if (!feature?.rule) return;
    feature.rules.push({
      name: feature.rule.name,
      tags: feature.rule.tags,
      background: [...feature.rule.background],
      scenarios: [...feature.rule.scenarios],
    });
    feature.rule = undefined;
    backgroundTarget = undefined;
  };

  const flushFeature = (): void => {
    flushRule();
    if (!feature) return;
    features.push({
      name: feature.name,
      tags: feature.tags,
      description: feature.description.join("\n").trim(),
      background: [...feature.background],
      rules: [...feature.rules],
      scenarios: [...feature.scenarios],
    });
    feature = undefined;
    backgroundTarget = undefined;
    backgroundIndent = -1;
    lastStepIndent = -1;
  };

  for (const [index, raw] of lines.entries()) {
    const line = raw.trim();
    const at = index + 1;
    if (line === "" || line.startsWith("#")) continue;
    if (line.startsWith("@")) {
      pendingTags.push(...line.split(/\s+/).filter((tag) => tag.startsWith("@")));
      continue;
    }

    if (line.startsWith("Feature:")) {
      flushFeature();
      const name = line.slice("Feature:".length).trim();
      if (!name) throw new GherkinError("Feature needs a name", at);
      feature = { name, tags: pendingTags, description: [], background: [], scenarios: [], rules: [], hasBackground: false };
      pendingTags = [];
      lastStepIndent = -1;
      continue;
    }
    if (line.startsWith("Scenario Outline:") || line.startsWith("Scenario Template:") || line.startsWith("Examples:")) {
      throw new GherkinError("Scenario Outline is not supported by this package", at);
    }
    if (line.startsWith("|") || line.startsWith('"""') || line.startsWith("```")) {
      throw new GherkinError("Tables and doc strings are not supported by this package", at);
    }
    if (line.startsWith("Rule:")) {
      if (!feature) throw new GherkinError("Rule must belong to a Feature", at);
      if (scenario) flushScenario();
      if (backgroundTarget) {
        backgroundTarget = undefined;
        backgroundIndent = -1;
      }
      flushRule();
      const name = line.slice("Rule:".length).trim();
      if (!name) throw new GherkinError("Rule needs a name", at);
      feature.rule = { name, tags: pendingTags, background: [], scenarios: [], hasBackground: false };
      pendingTags = [];
      lastStepIndent = -1;
      continue;
    }
    if (line.startsWith("Background:")) {
      const parent = feature?.rule ?? feature;
      const scopedScenarios = feature?.rule?.scenarios ?? feature?.scenarios ?? [];
      if (
        !parent || scenario || parent.hasBackground || scopedScenarios.length > 0 ||
        (!feature?.rule && (feature?.scenarios.length !== 0 || feature?.rules.length !== 0))
      ) {
        throw new GherkinError("Background must occur once before scenarios in its Feature or Rule", at);
      }
      parent.hasBackground = true;
      backgroundTarget = parent.background;
      backgroundIndent = raw.length - raw.trimStart().length;
      lastKind = undefined;
      lastStepIndent = -1;
      continue;
    }
    if (line.startsWith("Scenario:")) {
      if (!feature) throw new GherkinError("Scenario must belong to a Feature", at);
      flushScenario();
      const name = line.slice("Scenario:".length).trim();
      if (!name) throw new GherkinError("Scenario needs a name", at);
      if (scenarioNames.has(name)) throw new GherkinError("Scenario names must be unique", at);
      scenarioNames.add(name);
      scenario = { name, tags: pendingTags, clauses: [] };
      pendingTags = [];
      backgroundTarget = undefined;
      backgroundIndent = -1;
      lastStepIndent = -1;
      thenCount = 0;
      lastKind = undefined;
      continue;
    }

    const indent = raw.length - raw.trimStart().length;
    const [keyword, ...rest] = line.split(/\s+/);
    if (keyword === "Or") {
      const text = rest.join(" ").trim();
      const clauses = scenario?.clauses ?? backgroundTarget;
      const previous = clauses?.at(-1);
      if (!text || !lastKind || !clauses || !previous) {
        throw new GherkinError("Or must follow a step in the same block", at);
      }
      clauses[clauses.length - 1] = { ...previous, text: `${previous.text}\nOr ${text}` };
      lastStepIndent = indent;
      continue;
    }
    const keywordKind = STEP_KINDS[keyword];
    if (keywordKind === undefined) {
      if (!feature) throw new GherkinError(`Unexpected line "${keyword}" outside a Feature`, at);
      if (scenario) {
        const previous = scenario.clauses.at(-1);
        if (!previous || indent <= lastStepIndent) throw new GherkinError(`Unknown line "${keyword}" in a scenario`, at);
        scenario.clauses[scenario.clauses.length - 1] = { ...previous, text: `${previous.text} ${line}` };
      } else if (backgroundTarget && indent > backgroundIndent) {
        const previous = backgroundTarget.at(-1);
        if (!previous || indent <= lastStepIndent) throw new GherkinError(`Unknown line "${keyword}" in a background`, at);
        backgroundTarget[backgroundTarget.length - 1] = { ...previous, text: `${previous.text} ${line}` };
      } else if (backgroundTarget) {
        backgroundTarget = undefined;
        backgroundIndent = -1;
        feature.description.push(line);
      } else {
        feature.description.push(line);
      }
      continue;
    }
    const kind: ClauseKind = keywordKind === "and" || keywordKind === "but" ? (lastKind ?? "given") : keywordKind;
    const text = rest.join(" ").trim();
    if (!text) throw new GherkinError(`Step "${keyword}" has no text`, at);
    const clause: Clause = { index: kind === "then" && scenario ? ++thenCount : 0, kind, text };
    if (scenario) scenario.clauses.push(clause);
    else if (backgroundTarget) backgroundTarget.push(clause);
    else if (feature) feature.description.push(line);
    else throw new GherkinError("Step must belong to a Feature", at);
    lastKind = kind;
    lastStepIndent = indent;
  }

  flushFeature();
  if (features.length === 0) throw new GherkinError("Feature file has no Feature line", 1);
  if (scenarios.length === 0) throw new GherkinError("Feature file has no Scenario", 1);
  return {
    feature: features[0]!.name,
    description: features.map((item) => item.description).filter(Boolean).join("\n\n"),
    features,
    scenarios,
  };
}

/** The Then clauses of a scenario, in file order. */
export function thenClauses(scenario: Scenario): Clause[] {
  return scenario.clauses.filter((clause) => clause.kind === "then");
}

/** The clauses that set up the scenario, which the model reads as context. */
export function setupClauses(scenario: Scenario): Clause[] {
  return [
    ...scenario.background,
    ...scenario.clauses.filter((clause) => clause.kind !== "then"),
  ];
}

/** The first scenario, or an error that names the scenarios that exist. */
export function firstScenario(file: FeatureFile): Scenario {
  const first = file.scenarios[0];
  if (first !== undefined) return first;
  throw new GherkinError("Feature file has no Scenario", 1);
}

/** Finds one scenario by exact name. */
export function scenarioByName(file: FeatureFile, name: string): Scenario | undefined {
  return file.scenarios.find((scenario) => scenario.name === name);
}
