import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const CONTEXT_GUIDANCE = `
## Isolated research

When the user asks to research, investigate, compare, or understand an external repository, library, codebase, or current technical topic, call \`context_get\`. It starts a separate read-only Pi process and keeps research work out of the main session. The child may inspect public repositories with a depth-1 temporary clone under /tmp.
`;

export function registerContextGuidance(pi: ExtensionAPI): void {
  pi.on("before_agent_start", async (event) => ({
    systemPrompt: event.systemPrompt + CONTEXT_GUIDANCE,
  }));
}

export default registerContextGuidance;
