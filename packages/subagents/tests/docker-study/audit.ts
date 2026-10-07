import fs from "node:fs";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
export default function audit(pi: ExtensionAPI): void {
  const file = `/results/child-${process.pid}.jsonl`;
  const write = (event: unknown) => fs.appendFileSync(file, JSON.stringify(event) + "\n");
  pi.on("before_agent_start", event => { const index = event.systemPrompt.indexOf("=== AGENT MEMORY");
    write({event:"system", memory:index >= 0 ? event.systemPrompt.slice(index) : "", tools:pi.getActiveTools()}); });
  pi.on("message_end", event => { const message=event.message; if(message.role === "assistant" || message.role === "custom") write({event:"message",message}); });
  pi.on("tool_call", event => { write({event:"call",tool:event.toolName,id:event.toolCallId,args:event.input}); });
  pi.on("tool_result", event => { write({event:"result",tool:event.toolName,id:event.toolCallId,error:event.isError,content:event.content,details:event.details}); });
}
