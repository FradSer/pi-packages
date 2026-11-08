/** Lifecycle evidence for the explicit real-model Goal Docker E2E. */
import { appendFileSync, writeFileSync } from "node:fs";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const GOAL_TOOLS = ["create_goal", "get_goal", "update_goal"];

export default function (pi: ExtensionAPI): void {
  const file = "/results/events.jsonl";
  writeFileSync(file, "");
  const write = (event: unknown) => appendFileSync(file, JSON.stringify(event) + "\n");
  const expose = () => {
    const all = typeof pi.getAllTools === "function" ? pi.getAllTools().map(tool => tool.name) : [];
    const ordinary = all.filter(name => !GOAL_TOOLS.includes(name) && name !== "agent_memory");
    pi.setActiveTools([...ordinary, "create_goal", "get_goal", "update_goal"]);
    write({ event: "ready-tools", tools: pi.getActiveTools() });
  };
  pi.on("session_start", () => {
    write({ event: "ready", initialTools: pi.getActiveTools() });
    expose();
  });
  pi.on("before_agent_start", expose);
  pi.on("message_end", event => {
    const message = event.message;
    if (message?.role === "assistant") write({ event: "message_end", message });
  });
  pi.on("tool_call", event => write({ event: "tool_call", name: event.toolName, id: event.toolCallId, args: event.input }));
  pi.on("tool_result", event => write({ event: "tool_result", name: event.toolName, id: event.toolCallId, error: event.isError, content: event.content, details: event.details }));
}
