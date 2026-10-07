/** A bounded proposal template, never a permission decision or rule migration.
 * Only simple absolute roots have identical unquoted/single/double shell values.
 * Unsupported spelling stays on the planner's general validation path. */
export function projectPushTemplate(repoRoot: string): string | undefined {
  if (!/^\/[A-Za-z0-9_./-]+$/.test(repoRoot) || repoRoot.includes("//")
    || repoRoot.split("/").some(part => part === "." || part === "..")) return undefined;
  const root = repoRoot.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return String.raw`^(?:cd[ \t]+(?:${root}|'${root}'|"${root}"|\.)[ \t]+&&[ \t]+)?git(?:[ \t]+(?:-C[ \t]+\.|-c[ \t]+core\.quotePath=false|--no-pager))*[ \t]+push(?:[ \t]|$(?![\s\S]))`;
}

/** Literal tabs and escaped tabs are equivalent only in these exact template
 * slots. This recognizes spelling, never arbitrary regex equivalence or authority. */
export function matchesProjectPushTemplate(pattern: unknown, repoRoot: string): boolean {
  const template = projectPushTemplate(repoRoot);
  return template !== undefined && typeof pattern === "string"
    && pattern.replaceAll("\t", String.raw`\t`) === template;
}

export function projectPushCoverage(repoRoot: string): string {
  const template = projectPushTemplate(repoRoot);
  if (!template) return "Current-project cd wrapper spelling has no bounded template. Validate its exact shell spelling and coverage; report unsupported coverage rather than claiming whole-family interception.";
  return [
    "Current-project wrapper coverage (parent-bound root; not authorization):",
    `For a quoted durable prohibition covering the entire current-project push family, retain positive cases cd ${repoRoot} && git push --dry-run, cd '${repoRoot}' && git push --dry-run, cd \"${repoRoot}\" && git push --dry-run, and cd . && git push --dry-run.`,
    `A bounded proposal template is: ${template}`,
    "Keep echo/printf of those command strings, other-project cd prefixes and non-&& operators negative. This template covers only this exact root or dot, three safe Git option forms, and ASCII horizontal separators. It does not parse arbitrary shell scripts. Do not apply it to exact-only, branch-specific, temporary or approval-excepted restrictions without preserving their limits. Never change existing rules merely to adopt this template. Parent cases, original citations, permission and semantic checks remain mandatory.",
  ].join("\n");
}
