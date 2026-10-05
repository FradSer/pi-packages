/** Explicit child-only extension for model-to-parent intermediate messages. */

import type { AgentToolResult, ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { fileURLToPath } from "node:url";
import {
  MAX_PARENT_MESSAGE_BODY_BYTES,
  PARENT_MESSAGE_TOOL_NAME,
  parentMessageToolDetails,
  type ParentMessageRefusalCode,
  type ParentMessageResultDetails,
} from "./parent-message.ts";

export const PARENT_MESSAGE_EXTENSION_PATH = fileURLToPath(new URL("./parent-message-extension.ts", import.meta.url));
export const PARENT_MESSAGE_CAPABILITY_TOOLS: readonly string[] = [PARENT_MESSAGE_TOOL_NAME];

const PARENT_MESSAGE_PARAMS = {
  type: "object",
  properties: {
    message: {
      type: "string",
      description: "A bounded intermediate progress message for the parent agent.",
    },
  },
  required: ["message"],
  additionalProperties: false,
} as const;

const PARENT_MESSAGE_OUTPUT = {
  type: "object",
  anyOf: [
    {
      properties: {
        kind: { type: "string", const: "intermediate" },
        outcome: { type: "string", const: "emitted" },
        message: { type: "string" },
      },
      required: ["kind", "outcome", "message"],
      additionalProperties: false,
    },
    {
      properties: {
        kind: { type: "string", const: "intermediate" },
        outcome: { type: "string", const: "refused" },
        code: { type: "string", enum: ["invalid-arguments", "aborted"] },
        error: { type: "string" },
      },
      required: ["kind", "outcome", "code", "error"],
      additionalProperties: false,
    },
  ],
} as const;

function refusal(code: ParentMessageRefusalCode, error: string): AgentToolResult<ParentMessageResultDetails> & { structuredContent: ParentMessageResultDetails } {
  const details = { kind: "intermediate" as const, outcome: "refused" as const, code, error };
  return {
    content: [{ type: "text", text: `REFUSED · ${error}` }],
    details,
    structuredContent: details,
    isError: true,
  };
}

function validateParams(value: unknown): { ok: true; message: string } | { ok: false; error: string } {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return { ok: false, error: "agent_message requires an object with only a string message." };
  }
  const fields = value as Record<string, unknown>;
  if (Object.keys(fields).some(key => key !== "message")) {
    return { ok: false, error: "agent_message accepts only the message field." };
  }
  if (typeof fields.message !== "string" || fields.message.trim().length === 0) {
    return { ok: false, error: "agent_message requires a nonblank string message." };
  }
  if (Buffer.byteLength(fields.message, "utf8") > MAX_PARENT_MESSAGE_BODY_BYTES) {
    return { ok: false, error: `agent_message exceeds ${MAX_PARENT_MESSAGE_BODY_BYTES} UTF-8 bytes.` };
  }
  return { ok: true, message: fields.message };
}

export default function parentMessageExtension(pi: ExtensionAPI): void {
  pi.registerTool<typeof PARENT_MESSAGE_PARAMS, ParentMessageResultDetails>({
    name: PARENT_MESSAGE_TOOL_NAME,
    label: "Agent Message",
    promptSnippet: "Send bounded intermediate progress to the parent agent",
    description: `Send one intermediate progress message to the parent agent; maximum ${MAX_PARENT_MESSAGE_BODY_BYTES} UTF-8 bytes. This reports emitted only and never claims parent receipt.`,
    parameters: PARENT_MESSAGE_PARAMS,
    outputSchema: PARENT_MESSAGE_OUTPUT,
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: false, openWorldHint: false },
    async execute(_toolCallId, params, signal): Promise<AgentToolResult<ParentMessageResultDetails> & { structuredContent: ParentMessageResultDetails }> {
      if (signal?.aborted) return refusal("aborted", "agent_message was aborted before emission.");
      const validated = validateParams(params);
      if (!validated.ok) return refusal("invalid-arguments", validated.error);
      const details = parentMessageToolDetails(validated.message);
      return {
        content: [{ type: "text", text: "emitted" }],
        details,
        structuredContent: details,
      };
    },
  });
}
