import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const CONTEXT_GUIDANCE = `
## Isolated research

For questions about an external repository, library, codebase, or current technical topic, call \`context_get\` instead of researching inline. Research then stays out of the main session.
`;

export function registerContextGuidance(pi: ExtensionAPI): void {
  pi.on("before_agent_start", async (event) => ({
    systemPrompt: event.systemPrompt + CONTEXT_GUIDANCE,
  }));
}

export default registerContextGuidance;
