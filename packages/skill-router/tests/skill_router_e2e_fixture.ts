/**
 * Scripted E2E fixture for the skill-router acceptance run.
 *
 * The extension, the registry, the materialized tree, the codemode sandbox, the
 * search and the tool call are all real; only the model is replaced, so the script
 * that searches and calls a skill tool is fixed rather than chosen. That keeps the
 * run deterministic without credentials while still exercising every real path.
 *
 * `pi --print` prints only the final assistant text, so the gate decision is
 * written to `PI_SKILL_ROUTER_TRACE` for the driver to read alongside the JSONL.
 */

import { appendFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import skillRouter from "../index.ts";

/** The script a real model would write: search the tools, then call the match. */
function discoveryScript(toolName: string): string {
  return [
    `const found = (await searchTools("seo audit", { limit: 5 })).map((entry) => entry.name);`,
    `const call = await tools.${toolName}({});`,
    `return JSON.stringify({ found, call });`,
  ].join("\n");
}

export default function (pi: ExtensionAPI): void {
  const trace = process.env.PI_SKILL_ROUTER_TRACE;
  const toolName = process.env.PI_SKILL_ROUTER_TOOL ?? "";
  const log = (data: unknown) => {
    if (trace) appendFileSync(trace, `${JSON.stringify(data)}\n`);
  };
  const assembly = process.env.PI_SKILL_ROUTER_ASSEMBLY ?? "codemode";

  skillRouter(pi);

  // Read the channel decision from the same event the host uses, rather than
  // inferring it from the answer.
  pi.on("before_agent_start", (event) => {
    const sections = "sections" in event.systemPromptOptions ? event.systemPromptOptions.sections : undefined;
    const suggestion = sections && typeof sections === "object" ? Reflect.get(sections, "skill_router") ?? null : null;
    log({ kind: "gate", assembly, activeTools: pi.getActiveTools(), tool: toolName, suggestion });
  });

  let turn = 0;
  pi.registerProvider("skill-router-e2e", {
    api: "skill-router-e2e",
    baseUrl: "http://127.0.0.1",
    apiKey: "fixture",
    models: [
      {
        id: "scripted",
        name: "Scripted skill-router E2E",
        reasoning: false,
        input: ["text"],
        contextWindow: 200000,
        maxTokens: 4096,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      },
    ],
    streamSimple(model) {
      const index = turn++;
      const content: AssistantMessage["content"] =
        index === 0 && assembly === "codemode"
          ? [{ type: "toolCall", id: `e2e-${index}`, name: "codemode", arguments: { code: discoveryScript(toolName) } }]
          : [{ type: "text", text: "E2E_SKILL_ROUTER_END" }];
      const message: AssistantMessage = {
        role: "assistant",
        api: model.api,
        provider: model.provider,
        model: model.id,
        timestamp: Date.now(),
        content,
        stopReason: content[0]?.type === "toolCall" ? "toolUse" : "stop",
        usage: { input: 10, output: 5, cacheRead: 0, cacheWrite: 0, totalTokens: 15, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: message.stopReason as "toolUse" | "stop", message });
      stream.end();
      return stream;
    },
  });
}