/**
 * Session context extraction — feeds the current session's user requests
 * and decisions into the commit flow.
 *
 * git-agent's commit message generator is conversation-blind: it only sees
 * `--intent` plus the git diff. This tool bridges that gap by reading the
 * live session entries (the same JSONL that persists the conversation) and
 * returning the recent user requests, so the agent can build a commit intent
 * grounded in what the user actually asked for — not a compressed one-liner.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

export const SessionContextParams = Type.Object({
  maxMessages: Type.Optional(
    Type.Integer({
      minimum: 1,
      maximum: 50,
      description: "Max recent user messages to include (default: 15)",
    }),
  ),
  tailChars: Type.Optional(
    Type.Integer({
      minimum: 50,
      maximum: 4000,
      description: "Per-message character cap (default: 600)",
    }),
  ),
});

type SessionEntry = { type?: string; message?: { role?: string; content?: unknown } };

function extractText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .filter(
        (part): part is { type: string; text: string } =>
          !!part &&
          typeof part === "object" &&
          (part as { type?: unknown }).type === "text" &&
          typeof (part as { text?: unknown }).text === "string",
      )
      .map((part) => part.text)
      .join("\n");
  }
  return "";
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "session_context",
    label: "Session Context",
    description: [
      "Extract recent user requests and decisions from the current session.",
      "Use before committing: build the commit intent from this context instead of a one-line summary,",
      "so the commit message reflects what the user asked for and why.",
    ].join(" "),
    parameters: SessionContextParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const entries = ctx.sessionManager.getEntries() as SessionEntry[];
      const max = params.maxMessages ?? 15;
      const tailChars = params.tailChars ?? 600;

      const userMessages: string[] = [];
      for (const entry of entries) {
        if (entry.type !== "message") continue;
        if (entry.message?.role !== "user") continue;
        const text = extractText(entry.message.content).trim();
        if (text) userMessages.push(text);
      }

      const recent = userMessages.slice(-max);
      if (recent.length === 0) {
        return {
          content: [{ type: "text", text: "No user messages found in the current session." }],
          details: { count: 0 },
        };
      }

      const lines: string[] = [
        "## Recent user requests (session context)",
        `Last ${recent.length} user message(s) — use these to build a detailed commit intent (what + why + verification):`,
        "",
      ];
      recent.forEach((message, index) => {
        const body = message.length > tailChars ? `${message.slice(0, tailChars)}... (truncated)` : message;
        lines.push(`### Request ${index + 1}`, body, "");
      });

      return {
        content: [{ type: "text", text: lines.join("\n") }],
        details: { count: recent.length },
      };
    },
  });
}
