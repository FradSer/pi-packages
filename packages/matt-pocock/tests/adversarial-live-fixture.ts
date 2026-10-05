// Offline Pi v1.0 fixture for gateway and in-flight UI adversarial cases.
// State changes are driven through the real registered tool handlers while the
// real Pi selector/menu is open; no model service or user authentication is used.
import { appendFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage, type ToolCall } from "@earendil-works/pi-ai";
import type {
  AgentToolResult,
  AgentToolUpdateCallback,
  ExtensionAPI,
  ExtensionToolContext,
  RegisteredCommand,
} from "@earendil-works/pi-coding-agent";
import mattPocock from "../src/index.ts";

type Evidence = Record<string, unknown>;
type AnyExecute = (
  toolCallId: string,
  params: unknown,
  signal: AbortSignal | undefined,
  onUpdate: AgentToolUpdateCallback | undefined,
  ctx: ExtensionToolContext,
) => Promise<AgentToolResult>;

const evidencePath = process.env.PI_ADVERSARIAL_LIVE_EVIDENCE;
const testCase = process.env.PI_ADVERSARIAL_LIVE_CASE;
if (!evidencePath || !testCase) throw new Error("The adversarial live fixture requires a case and evidence path.");

function record(value: Evidence): void {
  appendFileSync(evidencePath!, JSON.stringify(value) + "\n");
}

function asExecute(execute: unknown): AnyExecute {
  if (typeof execute !== "function") throw new Error("The live fixture requires executable tools.");
  return execute as AnyExecute;
}

export default function adversarialLiveFixture(pi: ExtensionAPI): void {
  let activeExecute: AnyExecute | undefined;
  let workflowExecute: AnyExecute | undefined;
  let workflowContext: ExtensionToolContext | undefined;
  let mattCommand: RegisteredCommand["handler"] | undefined;

  const observed: ExtensionAPI = {
    ...pi,
    appendEntry(type, data) {
      record({ kind: "append", type, data });
      pi.appendEntry(type, data);
    },
    sendMessage(message, options) {
      if (message.customType === "matt-pocock-procedure") {
        record({ kind: "procedure", display: message.display, details: message.details, options });
      }
      pi.sendMessage(message, options);
    },
    registerTool(tool) {
      const original = tool.execute;
      if (tool.name === "matt_pocock_active") activeExecute = asExecute(original);
      if (tool.name === "matt_pocock_workflow") {
        workflowExecute = asExecute(original);
        pi.registerTool({
          ...tool,
          async execute(toolCallId, params, signal, onUpdate, ctx) {
            workflowContext = ctx;
            const result = await original(toolCallId, params, signal, onUpdate, ctx);
            if (testCase === "menu-complete") record({ kind: "menu_workflow_a", result });
            return result;
          },
        });
        return;
      }
      if (tool.name === "matt_pocock_ask" && testCase === "ask-complete") {
        pi.registerTool({
          ...tool,
          async execute(toolCallId, params, signal, onUpdate, ctx) {
            setTimeout(() => {
              const execute = activeExecute;
              if (!execute) {
                record({ kind: "replacement_error", message: "active tool was not captured" });
                return;
              }
              void execute("fixture-complete", { action: "complete" }, undefined, undefined, ctx)
                .then((result) => record({ kind: "replacement", result }))
                .catch((error: unknown) => record({ kind: "replacement_error", message: String(error) }));
            }, 100);
            const result = await original(toolCallId, params, signal, onUpdate, ctx);
            record({ kind: "ask_result", result });
            return result;
          },
        });
        return;
      }
      pi.registerTool(tool);
    },
    registerCommand(name, command) {
      if (name === "matt-pocock") mattCommand = command.handler;
      pi.registerCommand(name, command);
    },
  };

  mattPocock(observed);

  if (testCase === "menu-complete") {
    pi.registerCommand("adversarial-menu", {
      description: "Open the Matt Pocock menu while replacing its work item.",
      handler: async (_args, ctx) => {
        if (!mattCommand || !workflowExecute || !activeExecute || !workflowContext) throw new Error("The menu fixture was not fully registered.");
        const extensionContext = workflowContext;
        record({ kind: "menu_invoked" });
        setTimeout(() => {
          void (async () => {
            const cancelled = await activeExecute!("fixture-cancel-a", { action: "cancel", reason: "replace menu A" }, undefined, undefined, extensionContext);
            const started = await workflowExecute!("fixture-start-b", { mode: "workflow", route: "hard-bug" }, undefined, undefined, extensionContext);
            record({ kind: "menu_replacement", cancelled, started });
          })().catch((error: unknown) => record({ kind: "menu_replacement_error", message: String(error) }));
        }, 100);
        await mattCommand("", ctx);
        record({ kind: "menu_done" });
        const latest = [...ctx.sessionManager.getBranch()].reverse().find((entry) =>
          entry.type === "custom" && entry.customType === "matt-pocock-workflow");
        record({ kind: "menu_after", state: latest && latest.type === "custom" ? latest.data : undefined });
      },
    });
  }

  if (testCase === "human-reference") {
    pi.registerCommand("adversarial-reference", {
      description: "Start the user-only capability before its model reference.",
      handler: async (_args, ctx) => {
        if (!mattCommand) throw new Error("The reference fixture did not capture /matt-pocock.");
        await mattCommand("setup-matt-pocock-skills", ctx);
        record({ kind: "human_reference_started" });
      },
    });
  }

  const calls: (Pick<ToolCall, "name" | "arguments"> | undefined)[] = testCase === "reference"
    ? [{ name: "matt_pocock_workflow", arguments: { mode: "reference", capability: "setup-matt-pocock-skills", reference: "domain" } }]
    : testCase === "human-reference"
      ? [undefined, { name: "matt_pocock_workflow", arguments: { mode: "reference", capability: "setup-matt-pocock-skills", reference: "domain" } }]
      : testCase === "ask-complete"
      ? [
        { name: "matt_pocock_workflow", arguments: { mode: "workflow", route: "hard-bug" } },
        { name: "matt_pocock_ask", arguments: { question: "LIVE external replacement", options: ["A", "B"], timeout_seconds: 30 } },
      ]
      : testCase === "menu-complete"
        ? [{ name: "matt_pocock_workflow", arguments: { mode: "workflow", route: "hard-bug" } }]
        : [];
  let index = 0;
  pi.on("tool_execution_end", (event) => record({ kind: "tool_result", tool: event.toolName, ...event.result, isError: event.isError }));
  pi.registerProvider("matt-pocock-adversarial-live", {
    api: "matt-pocock-adversarial-live", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_ADVERSARIAL_LIVE_AUTH,
    models: [{ id: "deterministic", name: "Matt Pocock adversarial live", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const call = calls[index++];
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: call ? [{ type: "toolCall", id: `adversarial-live-${index}`, ...call }]
          : [{ type: "text", text: "ADVERSARIAL_LIVE_READY" }],
        stopReason: call ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: call ? "toolUse" : "stop", message });
      stream.end();
      return stream;
    },
  });
}
