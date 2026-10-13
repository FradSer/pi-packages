import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const CONTEXT_GUIDANCE = `
## Isolated research

For questions about an external repository, library, codebase, or current technical topic, call \`context_get\` instead of researching inline. Research then stays out of the main session.
`;

export function registerContextGuidance(pi: ExtensionAPI): void {
  pi.on("before_agent_start", async (event) => {
    const options = event.systemPromptOptions;
    if (!("sections" in options) || !options.sections || typeof options.sections !== "object" || Array.isArray(options.sections)) {
      throw new Error("This extension requires Pi structured prompt sections.");
    }
    const sections = options.sections;
    Reflect.deleteProperty(sections, "context_research");
    Object.assign(sections, { context_research: CONTEXT_GUIDANCE });
  });
}

export default registerContextGuidance;
