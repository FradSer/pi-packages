import type { Skill } from "@earendil-works/pi-coding-agent";
import { leafSkillFile, routerRoot } from "./paths";
import type { RegistryCollection } from "./registry";

export interface RouteMatch {
  collectionId: string;
  skillName: string;
  skillPath: string;
}

function termMatches(prompt: string, term: string): boolean {
  const escaped = term.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^a-z0-9])${escaped}(?=$|[^a-z0-9])`).test(prompt);
}

export function routePrompt(
  prompt: string,
  collections: RegistryCollection[],
  availableSkills: ReadonlyMap<string, Skill>,
  root = routerRoot(),
): RouteMatch | undefined {
  const normalizedPrompt = prompt.toLowerCase();
  let bestMatch: RouteMatch | undefined;
  let bestScore = 0;

  for (const collection of collections) {
    if (!collection.enabled || collection.mode !== "suggest") continue;
    if (!availableSkills.has(collection.gateway)) continue;

    for (const route of collection.routes) {
      const matchingTerms = route.terms.filter((term) => termMatches(normalizedPrompt, term));
      if (matchingTerms.length === 0) continue;

      const maxTermLength = Math.max(...matchingTerms.map((term) => term.length));
      const totalLength = matchingTerms.reduce((sum, term) => sum + term.length, 0);
      const score = maxTermLength * 10 + totalLength + matchingTerms.length * 5;

      if (score > bestScore) {
        bestScore = score;
        bestMatch = {
          collectionId: collection.id,
          skillName: route.skill,
          skillPath: leafSkillFile(root, collection.id, route.skill),
        };
      }
    }
  }

  return bestMatch;
}

export function isExplicitSkillInvocation(prompt: string): boolean {
  return /(?:^|[^a-z0-9_])\/skill:[a-z0-9]+(?:-[a-z0-9]+)*(?=$|[^a-z0-9-])/i.test(prompt)
    || /<skill\s+name\s*=\s*["'][^"']+["']/i.test(prompt);
}

export function routingGuidance(match: RouteMatch): string {
  return [
    "## Skill collection suggestion",
    "",
    `The user's request strongly matches the \`${match.collectionId}\` skill collection (\`${match.skillName}\`).`,
    `Read \`${match.skillPath}\` before applying its workflow.`,
    "This is a suggestion, not a replacement for your judgment. Do not load unrelated collection skills.",
  ].join("\n");
}
