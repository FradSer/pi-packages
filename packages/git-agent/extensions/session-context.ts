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
import { truncateTail, DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES } from "@earendil-works/pi-coding-agent";
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
  sinceLastCall: Type.Optional(
    Type.Boolean({
      description:
        "Only include user messages since the last session_context call or commit (default: true)",
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

function isContextOrCommitEntry(entry: SessionEntry): boolean {
  if (!entry) return false;

  if (entry.type === "tool_call" || entry.type === "tool_result") {
    const name = (entry as { name?: string }).name;
    if (name === "session_context") return true;
    if (name === "bash") {
      const args =
        (entry as { args?: { command?: string }; input?: { command?: string } }).args ||
        (entry as { input?: { command?: string } }).input;
      if (args?.command && typeof args.command === "string" && args.command.includes("git-agent commit")) {
        return true;
      }
    }
  }

  if (entry.type === "message" && entry.message) {
    const msg = entry.message as { role?: string; content?: unknown; toolCalls?: unknown[] };

    if (Array.isArray(msg.toolCalls)) {
      for (const call of msg.toolCalls) {
        if (call && typeof call === "object") {
          const name = (call as { name?: string }).name;
          if (name === "session_context") return true;
          if (name === "bash") {
            const args =
              (call as { args?: { command?: string }; input?: { command?: string } }).args ||
              (call as { input?: { command?: string } }).input;
            if (args?.command && typeof args.command === "string" && args.command.includes("git-agent commit")) {
              return true;
            }
          }
        }
      }
    }

    if (Array.isArray(msg.content)) {
      for (const part of msg.content) {
        if (part && typeof part === "object") {
          const type = (part as { type?: string }).type;
          const name = (part as { name?: string }).name;
          if (type === "toolCall" || type === "tool_use" || type === "tool_result") {
            if (name === "session_context") return true;
            if (name === "bash") {
              const args =
                (part as { args?: { command?: string }; input?: { command?: string } }).args ||
                (part as { input?: { command?: string } }).input;
              if (args?.command && typeof args.command === "string" && args.command.includes("git-agent commit")) {
                return true;
              }
            }
          }
        }
      }
    }
  }

  return false;
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "session_context",
    label: "Session Context",
    description: [
      "Extract recent user requests and decisions from the current session.",
      "Deduplicates automatically to only include requests since the last commit or context call.",
      "Use before committing: build the commit intent from this context instead of a one-line summary,",
      "so the commit message reflects what the user asked for and why.",
    ].join(" "),
    promptSnippet: "Extract recent user requests from the session to build a commit intent",
    promptGuidelines: [
      "Use session_context before committing to ground the commit intent in what the user actually asked for, not a one-line summary.",
    ],
    parameters: SessionContextParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const entries = (ctx.sessionManager.getEntries() as SessionEntry[]) ?? [];
      const max = params.maxMessages ?? 15;
      const tailChars = params.tailChars ?? 600;
      const sinceLastCall = params.sinceLastCall ?? true;

      const allUserMessages: { index: number; text: string }[] = [];
      for (let i = 0; i < entries.length; i++) {
        const entry = entries[i];
        if (entry.type !== "message") continue;
        if (entry.message?.role !== "user") continue;
        const text = extractText(entry.message.content).trim();
        if (text) allUserMessages.push({ index: i, text });
      }

      if (allUserMessages.length === 0) {
        return {
          content: [{ type: "text", text: "No user messages found in the current session." }],
          details: { count: 0 },
        };
      }

      let selectedUserMessages = allUserMessages;
      let isDeduplicated = false;

      if (sinceLastCall) {
        const lastUserIndex = allUserMessages[allUserMessages.length - 1].index;

        let maxPreviousCutoffIndex = -1;
        for (let i = 0; i < entries.length; i++) {
          if (i < lastUserIndex && isContextOrCommitEntry(entries[i])) {
            if (i > maxPreviousCutoffIndex) {
              maxPreviousCutoffIndex = i;
            }
          }
        }

        if (maxPreviousCutoffIndex >= 0) {
          const newMessages = allUserMessages.filter((m) => m.index > maxPreviousCutoffIndex);
          if (newMessages.length > 0) {
            selectedUserMessages = newMessages;
            isDeduplicated = true;
          }
        }
      }

      const recent = selectedUserMessages.slice(-max).map((m) => m.text);

      const lines: string[] = [
        "## Recent user requests (session context)",
        isDeduplicated
          ? `Showing ${recent.length} new user message(s) since last commit/context call — use these to build a detailed commit intent (what + why + verification):`
          : `Last ${recent.length} user message(s) — use these to build a detailed commit intent (what + why + verification):`,
        "",
      ];
      recent.forEach((message, index) => {
        const body = message.length > tailChars ? `${message.slice(0, tailChars)}... (truncated)` : message;
        lines.push(`### Request ${index + 1}`, body, "");
      });

      const text = lines.join("\n");
      const output =
        text.length <= DEFAULT_MAX_BYTES
          ? text
          : truncateTail(text, { maxLines: DEFAULT_MAX_LINES, maxBytes: DEFAULT_MAX_BYTES }).content;
      return {
        content: [{ type: "text", text: output }],
        details: { count: recent.length, deduplicated: isDeduplicated },
      };
    },
  });
}
