/** Offline model only. Installed tools are discovered and executed by real Pi. */
import { appendFileSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createAssistantMessageEventStream, type AssistantMessage, type JsonObject, type Message } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const PROVIDER = "install-wiring";
const REPORT_PREFIX = "INSTALL_WIRING_REPORT ";
interface Turn { tool: string; args: JsonObject }

function valueFromResults(value: unknown, messages: Message[]): unknown {
  if (typeof value !== "string" || !value.startsWith("$prev.")) return value;
  for (const message of [...messages].reverse()) {
    if (message.role !== "toolResult") continue;
    let found: unknown = message.details;
    for (const key of value.slice(6).split(".")) {
      found = found && typeof found === "object" ? (found as Record<string, unknown>)[key] : undefined;
    }
    if (found !== undefined) return found;
  }
  throw new Error(`No real tool result supplies ${value}`);
}

export default function installWiringProvider(pi: ExtensionAPI): void {
  const root = resolve(process.env.HOME!, "..");
  const auth = JSON.parse(readFileSync(resolve(process.env.PI_CODING_AGENT_DIR!, "auth.json"), "utf8")) as Record<string, { key: string }>;
  const turns: Turn[] = process.env.INSTALL_WIRING_SCENARIO?.startsWith("smoke") ? [
    { tool: "create_task", args: { subject: "Isolated install smoke" } },
    { tool: "list_tasks", args: { claimable: true } },
    { tool: "update_task", args: { id: "$prev.id", status: "in_progress" } },
    { tool: "update_task", args: { id: "$prev.id", status: "completed", outcome: "success", result: "smoke passed" } },
    // A control the four task tools do not carry. Naming it as an extra property
    // keeps the negative surface on the real schema rather than on a removed verb.
    { tool: "update_task", args: { id: "$prev.id", action: "assign" } },
    ...(process.env.INSTALL_WIRING_SCENARIO === "smoke" ? [
      { tool: "message", args: { to: "nobody-here", body: "status?", kind: "inform" } },
    ] : []),
    { tool: "agent_start", args: { identity: "../escape", prompt: "Escape attempt" } },
    { tool: "agent_start", args: { label: "install-idle", prompt: "Wait for explicit input.",
      instructions: "Wait for explicit input.", tools: [], model: "install-wiring-child/deterministic" } },
    { tool: "agent_list", args: {} },
    { tool: "agent_stop", args: { session: "$prev.session" } },
    { tool: "agent_start", args: { label: "install-input", prompt: "Confirm the isolated input.",
      instructions: "Answer only the supplied input.", tools: [], model: "install-wiring-child/deterministic" } },
    { tool: "agent_stop", args: { session: "$prev.session" } },
  ] : [];

  // Record receipts after native tool execution, alongside the preload's actual
  // RPC responses. A pid or writable stdin cannot satisfy these assertions.
  pi.on("tool_result", async (event) => {
    if (!event.toolName.startsWith("agent_")) return;
    const details = event.details as Record<string, unknown> | undefined;
    appendFileSync(resolve(root, "rpc.jsonl"), JSON.stringify({
      kind: "tool-result", operation: event.toolName, name: details?.label ?? details?.name,
      disposition: details?.disposition, prompted: details?.prompted,
    }) + "\n");
    if (details?.label === "install-input" && details.disposition === "started") {
      // Observe the receipt first, then let the native child reach the loopback
      // model before the scripted stop. Never substitute this for the RPC ack:
      // the ordering assertion still compares the unaltered native records.
      const models = JSON.parse(readFileSync(resolve(process.env.PI_CODING_AGENT_DIR!, "models.json"), "utf8")) as {
        providers: Record<string, { baseUrl: string }>;
      };
      const accepted = await fetch(models.providers["install-wiring-child"]!.baseUrl + "/accepted", {
        signal: AbortSignal.timeout(15000),
      });
      if (!accepted.ok) throw new Error("Native child never reached the loopback model");
    }
  });

  pi.registerProvider(PROVIDER, {
    api: PROVIDER,
    apiKey: auth[PROVIDER]!.key,
    baseUrl: "http://127.0.0.1",
    models: [{ id: "deterministic", name: "Offline install wiring", reasoning: false,
      input: ["text"], contextWindow: 200000, maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model, context, options) {
      const results = context.messages.filter((message) => message.role === "toolResult");
      const pending = turns[results.length];
      const args = pending ? Object.fromEntries(Object.entries(pending.args).map(([key, value]) =>
        [key, valueFromResults(value, context.messages)])) as JsonObject : {};
      const report = {
        tools: pi.getAllTools().map(({ name, parameters, sourceInfo }) => ({ name, parameters, sourceInfo })),
        calls: results.map((message) => ({
          name: message.toolName, isError: message.isError,
          text: message.content.map((block) => block.type === "text" ? block.text : "").join("\n"),
          details: message.details ?? null,
        })),
      };
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id,
        timestamp: 1_700_000_000_000 + results.length,
        content: pending ? [{ type: "toolCall", id: `install-${results.length}`, name: pending.tool, arguments: args }]
          : [{ type: "text", text: REPORT_PREFIX + JSON.stringify(report) }],
        stopReason: options?.signal?.aborted ? "aborted" : pending ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      if (message.stopReason === "aborted") {
        message.errorMessage = "Offline fixture aborted";
        stream.push({ type: "error", reason: "aborted", error: message });
      } else {
        stream.push({ type: "start", partial: message });
        const block = message.content[0]!;
        if (block.type === "toolCall") {
          stream.push({ type: "toolcall_start", contentIndex: 0, partial: message });
          stream.push({ type: "toolcall_end", contentIndex: 0, toolCall: block, partial: message });
        } else if (block.type === "text") {
          stream.push({ type: "text_start", contentIndex: 0, partial: message });
          stream.push({ type: "text_delta", contentIndex: 0, delta: block.text, partial: message });
          stream.push({ type: "text_end", contentIndex: 0, content: block.text, partial: message });
        }
        stream.push({ type: "done", reason: pending ? "toolUse" : "stop", message });
      }
      stream.end(message);
      return stream;
    },
  });
}
