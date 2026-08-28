import type { Skill } from "@earendil-works/pi-coding-agent";
import type { RegistryCollection } from "./registry";

export interface RouteMatch {
  collectionId: string;
  skill: Skill;
}

function termMatches(prompt: string, term: string): boolean {
  const escaped = term.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^a-z0-9])${escaped}(?=$|[^a-z0-9])`).test(prompt);
}

export function routePrompt(
  prompt: string,
  collections: RegistryCollection[],
  availableSkills: ReadonlyMap<string, Skill>,
): RouteMatch | undefined {
  const normalizedPrompt = prompt.toLowerCase();
  for (const collection of collections) {
    if (!collection.enabled || collection.mode !== "suggest") continue;
    if (!availableSkills.has(collection.gateway)) continue;
    for (const route of collection.routes) {
      const skill = availableSkills.get(`${collection.prefix}-${route.skill}`);
      if (skill && route.terms.some((term) => termMatches(normalizedPrompt, term))) {
        return { collectionId: collection.id, skill };
      }
    }
  }
  return undefined;
}

export function isExplicitSkillInvocation(prompt: string): boolean {
  return /(?:^|[^a-z0-9_])\/skill:[a-z0-9]+(?:-[a-z0-9]+)*(?=$|[^a-z0-9-])/i.test(prompt)
    || /<skill\s+name\s*=\s*["'][^"']+["']/i.test(prompt);
}

export function routingGuidance(match: RouteMatch): string {
  return [
    "## Skill collection suggestion",
    "",
    `The user's request strongly matches the \`${match.collectionId}\` skill collection.`,
    `The user can explicitly invoke \`/skill:${match.skill.name}\` to load that workflow.`,
    `If the user has not invoked it, read \`${match.skill.filePath}\` before applying its workflow.`,
    "This is a suggestion, not a replacement for your judgment. Do not load unrelated collection skills.",
  ].join("\n");
}
