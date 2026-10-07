import type { Clause, ClauseKind, FeatureFile, Scenario } from "./types.ts";

/** A .feature file this MVP does not accept, with the line that stopped it. */
export class GherkinError extends Error {
  // No parameter properties: `node src/cli.ts` runs the files through
  // strip-only type erasure, which rejects them.
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

/**
 * Parses the Gherkin subset this package needs: Feature, Background, Scenario,
 * tags, and Given/When/Then/And/But steps. Scenario Outline, Examples, Rule,
 * Doc strings, and tables are rejected with the line number instead of being
 * read as prose, because a wrong parse would silently judge the wrong clause.
 */
export function parseFeature(source: string): FeatureFile {
  const lines = source.split("\n");
  let feature = "";
  const description: string[] = [];
  const scenarios: Scenario[] = [];
  let background: Clause[] = [];
  let inBackground = false;
  // The scenario under construction keeps a mutable clause list; the exported
  // type stays readonly.
  let draft: Draft | undefined;
  let pendingTags: string[] = [];
  let lastKind: ClauseKind | undefined;
  let thenCount = 0;

  for (const [index, raw] of lines.entries()) {
    const line = raw.trim();
    const at = index + 1;
    if (line === "" || line.startsWith("#")) continue;
    if (line.startsWith("@")) {
      // Tags can accumulate across multiple lines before a Scenario or Feature
      pendingTags.push(...line.split(/\s+/).filter((tag) => tag.startsWith("@")));
      continue;
    }
    if (line.startsWith("Feature:")) {
      if (feature !== "") throw new GherkinError("Multiple Feature declarations in one file", at);
      feature = line.slice("Feature:".length).trim();
      if (feature === "") throw new GherkinError("Feature needs a name", at);
      continue;
    }
    if (line.startsWith("Scenario Outline:") || line.startsWith("Examples:")) {
      throw new GherkinError("Scenario Outline is not supported by this package", at);
    }
    if (line.startsWith("Rule:")) throw new GherkinError("Rule is not supported by this package", at);
    if (line.startsWith("|") || line.startsWith('"""') || line.startsWith("```")) {
      throw new GherkinError("Tables and doc strings are not supported by this package", at);
    }
    if (line.startsWith("Background:")) {
      if (draft !== undefined || scenarios.length > 0) {
        throw new GherkinError("Background must sit above all Scenarios", at);
      }
      inBackground = true;
      background = [];
      lastKind = undefined;
      continue;
    }
    if (line.startsWith("Scenario:")) {
      inBackground = false;
      const name = line.slice("Scenario:".length).trim();
      if (name === "") throw new GherkinError("Scenario needs a name", at);
      flush(draft, feature, background, scenarios);
      draft = { name, tags: [...pendingTags], clauses: [] };
      pendingTags = [];
      thenCount = 0;
      lastKind = undefined;
      continue;
    }

    const [keyword, ...rest] = line.split(/\s+/);
    const keywordKind = STEP_KINDS[keyword];
    if (keywordKind === undefined) {
      if (draft === undefined && !inBackground) {
        description.push(line);
        continue;
      }
      throw new GherkinError(`Unknown line "${keyword}" in a scenario`, at);
    }

    const kind: ClauseKind = keywordKind === "and" || keywordKind === "but" ? (lastKind ?? "given") : keywordKind;
    const text = rest.join(" ").trim();
    if (text === "") throw new GherkinError(`Step "${keyword}" has no text`, at);

    if (inBackground) {
      background.push({ index: 0, kind, text });
      lastKind = kind;
      continue;
    }

    if (draft !== undefined) {
      if (kind === "then") thenCount += 1;
      draft.clauses.push({ index: kind === "then" ? thenCount : 0, kind, text });
      lastKind = kind;
      continue;
    }

    description.push(line);
  }

  flush(draft, feature, background, scenarios);

  if (feature === "") throw new GherkinError("Feature file has no Feature line", 1);
  if (scenarios.length === 0) throw new GherkinError("Feature file has no Scenario", 1);
  return { feature, description: description.join("\n").trim(), scenarios };
}

type Draft = { name: string; tags: readonly string[]; clauses: Clause[] };

/** Appends the scenario under construction, in file order. */
function flush(
  draft: Draft | undefined,
  feature: string,
  background: readonly Clause[],
  scenarios: Scenario[],
): void {
  if (draft === undefined) return;
  scenarios.push({ feature, name: draft.name, tags: draft.tags, background, clauses: draft.clauses });
}

/** The Then clauses of a scenario, in file order. */
export function thenClauses(scenario: Scenario): Clause[] {
  return scenario.clauses.filter((clause) => clause.kind === "then");
}

/** The clauses that set up the scenario, which the model reads as context. */
export function setupClauses(scenario: Scenario): Clause[] {
  return [...scenario.background, ...scenario.clauses.filter((clause) => clause.kind !== "then")];
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
