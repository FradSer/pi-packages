import type { BeforeAgentStartEvent, ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { routerRoot, skillToolName } from "./src/paths";
import { loadCollections } from "./src/registry";
import { isExplicitSkillInvocation, routePrompt, routingGuidance } from "./src/router";
import { codemodeReachesSkillTool, refreshSkillTools } from "./src/skills";
import { exposedSkillPaths } from "./src/sync";
import { showSkillRouterMenu } from "./src/menu";

/**
 * Two channels reach a leaf skill.
 *
 * The tools channel registers one codemode tool per routed leaf skill, so the
 * model searches codemode's tools and calls the matched one. The fallback
 * channel keeps the routing suggestion whenever that skill's own tool cannot be
 * called: a session that does not declare codemode, an allowlist that removed
 * the tool, or a collection added after this extension loaded. The gateway stays
 * exposed either way, as the human `/skill:<gateway>` entry point.
 */
export default function skillRouter(pi: ExtensionAPI): void {
  refreshSkillTools(pi, routerRoot());

  pi.on("resources_discover", () => ({
    skillPaths: exposedSkillPaths(routerRoot()),
  }));

  pi.on("before_agent_start", (event: BeforeAgentStartEvent) => {
    const options = event.systemPromptOptions;
    if (!("sections" in options) || !options.sections || typeof options.sections !== "object" || Array.isArray(options.sections)) {
      throw new Error("This extension requires Pi structured prompt sections.");
    }
    const sections = options.sections;
    Reflect.deleteProperty(sections, "skill_router");
    if (!("prompt" in event) || typeof event.prompt !== "string" || isExplicitSkillInvocation(event.prompt)) return;

    const skills = event.systemPromptOptions.skills ?? [];
    const match = routePrompt(event.prompt, loadCollections(routerRoot()), new Map(skills.map((skill) => [skill.name, skill])));
    if (!match) return;
    // The tools channel wins only for this skill's own tool. A surviving sibling
    // tool, or a collection that registered nothing before the next reload, must
    // not suppress the suggestion that is the only working path to this skill.
    if (codemodeReachesSkillTool(pi, skillToolName(match.collectionId, match.skillName))) return;

    Object.assign(sections, { skill_router: routingGuidance(match) });
  });

  pi.registerCommand("skill-router", {
    description: "Manage externally hosted skill collections (add, update, remove, toggle, list)",
    handler: async (_args, ctx) => {
      await showSkillRouterMenu(ctx, { refreshTools: () => refreshSkillTools(pi, routerRoot()) });
    },
  });
}

export { routePrompt };
