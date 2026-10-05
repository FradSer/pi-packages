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
}
