/**
 * @fradser/utils — native pi /continue command and "continue" input interception.
 *
 * Resume execution from interrupted steps, re-run aborted requests directly,
 * or prompt the LLM to continue based on suggestions/next steps from the previous response.
 *
 * Usage:
 *   /continue [optional extra prompt]
 *   or simply reply "continue" in conversation.
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

/**
 * Find the text of the last user prompt in the active session branch.
 */
function getLastUserPrompt(ctx: ExtensionContext): string | null {
  const branch = ctx.sessionManager.getBranch();
  for (let i = branch.length - 1; i >= 0; i--) {
    const entry = branch[i];
    if (entry.type === "message" && entry.message.role === "user") {
      const content = entry.message.content;
      if (typeof content === "string" && content.trim()) {
        return content;
      }
      if (Array.isArray(content)) {
        const textParts = content
          .filter((c): c is { type: "text"; text: string } => c.type === "text")
          .map((c) => c.text)
          .join("\n")
          .trim();
        if (textParts) return textParts;
      }
    }
  }
  return null;
}

/**
 * Inspect the session history to construct a continuation prompt.
 */
function buildContinuationPrompt(ctx: ExtensionContext): string {
  const branch = ctx.sessionManager.getBranch();
  if (branch.length === 0) {
    return "Please continue execution.";
  }

  // Find the last message entry in the branch
  let lastMessageEntry = null;
  for (let i = branch.length - 1; i >= 0; i--) {
    const entry = branch[i];
    if (entry.type === "message") {
      lastMessageEntry = entry;
      break;
    }
  }

  if (!lastMessageEntry) {
    return "Please continue execution.";
  }

  const msg = lastMessageEntry.message;

  // Case 1: Trailing message is a user prompt (assistant turn was aborted before saving assistant entry)
  if (msg.role === "user") {
    const userText = getLastUserPrompt(ctx);
    if (userText) return userText;
  }

  // Case 2: Most recent assistant message was aborted (stopReason === "aborted") -> re-run last user request directly
  for (let i = branch.length - 1; i >= 0; i--) {
    const entry = branch[i];
    if (entry.type === "message" && entry.message.role === "assistant") {
      if (entry.message.stopReason === "aborted") {
        const lastUserText = getLastUserPrompt(ctx);
        if (lastUserText) return lastUserText;
        return "The previous turn was aborted. Please resume execution from where it was interrupted.";
      }
      break; // Only check the latest assistant message
    }
  }

  // Case 3: Last message was a toolResult that failed or errored
  if (msg.role === "toolResult" && msg.isError) {
    const toolName = msg.toolName ? ` (${msg.toolName})` : "";
    return `The previous step${toolName} was interrupted or encountered an error. Please inspect the error details and system state, then resume execution from the interrupted step.`;
  }

  // Case 4: Last assistant message completed normally — continue based on suggestions / next steps
  let lastAssistantText = "";
  for (let i = branch.length - 1; i >= 0; i--) {
    const entry = branch[i];
    if (entry.type === "message" && entry.message.role === "assistant") {
      const texts = entry.message.content
        ?.filter((c): c is { type: "text"; text: string } => c.type === "text")
        .map((c) => c.text)
        .join("\n");
      if (texts) {
        lastAssistantText = texts;
        break;
      }
    }
  }

  if (lastAssistantText) {
    return "Please continue execution based on the suggestions, incomplete steps, or next actions from your previous response.";
  }

  return "Please continue execution.";
}

export default function (pi: ExtensionAPI) {
  // 1. Intercept plain user input "continue"
  pi.on("input", async (event, ctx) => {
    const text = event.text.trim().toLowerCase();
    if (text === "continue") {
      return {
        action: "transform",
        text: buildContinuationPrompt(ctx),
      };
    }
    return { action: "continue" };
  });

  // 2. Register /continue slash command
  pi.registerCommand("continue", {
    description: "Resume from an interrupted step, re-run aborted requests, or continue execution based on previous response",
    handler: async (args, ctx) => {
      await ctx.waitForIdle();
      const promptText = args.trim() || buildContinuationPrompt(ctx);
      pi.sendUserMessage(promptText);
    },
  });
}
