import type { BeforeAgentStartEvent, ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { routerRoot } from "./src/paths";
import { loadCollections } from "./src/registry";
import { isExplicitSkillInvocation, routePrompt, routingGuidance } from "./src/router";
import { exposedSkillPaths } from "./src/sync";
import { showSkillRouterMenu } from "./src/menu";

export default function skillRouter(pi: ExtensionAPI): void {
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
    if (typeof event.prompt !== "string" || isExplicitSkillInvocation(event.prompt)) return;

    const skills = event.systemPromptOptions.skills ?? [];
    const match = routePrompt(event.prompt, loadCollections(routerRoot()), new Map(skills.map((skill) => [skill.name, skill])));
    if (!match) return;

    Object.assign(sections, { skill_router: routingGuidance(match) });
  });

  pi.registerCommand("skill-router", {
    description: "Manage externally hosted skill collections (add, update, remove, toggle, list)",
    handler: async (_args, ctx) => {
      await showSkillRouterMenu(ctx);
    },
  });
}

export { routePrompt };
