// Restore probe: reuse the runtime matrix's deterministic provider and native
// Pi event instrumentation, adding only the final system-prompt observation.
import { appendFileSync } from "node:fs";
import type { Api, Provider } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ProviderConfig } from "@earendil-works/pi-coding-agent";
import runtimeFixture from "./runtime-live-fixture.ts";

export default function restoreFixture(pi: ExtensionAPI): void {
  const configuredEvidencePath = process.env.PI_RUNTIME_EVIDENCE;
  if (!configuredEvidencePath) throw new Error("The restore fixture requires runtime evidence.");
  const evidencePath = configuredEvidencePath;
  function registerProvider(provider: Provider<Api>): void;
  function registerProvider(name: string, config: ProviderConfig): void;
  function registerProvider(nameOrProvider: string | Provider<Api>, config?: ProviderConfig): void {
    if (typeof nameOrProvider !== "string") {
      pi.registerProvider(nameOrProvider);
      return;
    }
    if (!config) throw new Error("A named provider requires configuration.");
    const streamSimple = config.streamSimple;
    if (!streamSimple) {
      pi.registerProvider(nameOrProvider, config);
      return;
    }
    pi.registerProvider(nameOrProvider, {
      ...config,
      streamSimple(model, context, options) {
        // Pi 1.2 hands the provider a transcript context, not the system prompt, so
        // this records what a provider actually receives. The injected guidance is
        // observed below, on the prompt section this extension writes.
        const systemMessages = context.messages.filter((message) => message.role === "system");
        const systemPrompt = [
          ...systemMessages.map((message) => typeof message.content === "string"
            ? message.content
            : JSON.stringify(message.content)),
        ].filter(Boolean).join("\n");
        appendFileSync(evidencePath, JSON.stringify({ kind: "provider_context", systemPrompt }) + "\n");
        return streamSimple(model, context, options);
      },
    });
  }
  const observed: ExtensionAPI = {
    ...pi,
    registerProvider,
  };
  runtimeFixture(observed);
  // Pi renders the system prompt from mutable sections and does not hand it to the
  // provider, so observe the section this extension writes. Registration order is
  // handler order, so this recorder runs after the extension injected its text.
  observed.on("before_agent_start", async (event) => {
    const sections = event.systemPromptOptions?.sections;
    const guidance = sections && typeof sections === "object"
      ? (sections as Record<string, unknown>).matt_pocock_workflow
      : undefined;
    appendFileSync(evidencePath, JSON.stringify({
      kind: "prompt_section",
      guidance: typeof guidance === "string" ? guidance : "",
    }) + "\n");
  });
}
