/** Deterministic model fixture; the Pi runtime and its read/edit/write tools are real. */
import { appendFileSync, readFileSync } from "node:fs";
import { Type } from "typebox";
import { getCurrentSystemPrompt } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { installScriptedProvider } from "../../../tests/e2e/support/scripted.ts";

export default function fixture(pi: ExtensionAPI): void {
  const config = JSON.parse(readFileSync(process.env.PI_SDLC_SCRIPT!, "utf8"));
  const emit = (event: unknown) => appendFileSync(process.env.PI_SDLC_TRACE!, JSON.stringify(event) + "\n");
  pi.on("context_with_system", (event) => {
    emit({ kind: "provider-context", systemPrompt: getCurrentSystemPrompt(event.messages) });
  });
  pi.on("agent_settled", (event) => emit({ kind: "settled", aborted: event.aborted }));
  pi.registerTool({
    name: "sdlc_wait", label: "Wait for abort", description: "Offline acceptance wait",
    parameters: Type.Object({}), renderShell: "self", renderCall: () => undefined as never,
    async execute(_id, _args, signal) {
      await new Promise<void>((_resolve, reject) => {
        if (!signal || signal.aborted) return reject(new Error("Acceptance wait aborted"));
        signal.addEventListener("abort", () => reject(new Error("Acceptance wait aborted")), { once: true });
        emit({ kind: "wait-ready" });
      });
      return { content: [{ type: "text", text: "unreachable" }] };
    },
  });
  installScriptedProvider(pi, { provider: "sdlc-fixture", probe: "sdlc_probe", turns: config.turns });
}
