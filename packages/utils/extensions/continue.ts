/**
 * @fradser/utils — native pi /continue command and "continue" input interception.
 *
 * Resume execution from interrupted steps or prompt the LLM to continue based on
 * suggestions/next steps from the previous response.
 *
 * Usage:
 *   /continue [optional extra prompt]
 *   or simply reply "continue" in conversation.
 */

import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";

/**
 * Inspect the session history to construct a continuation prompt.
 */
function buildContinuationPrompt(ctx: ExtensionCommandContext): string {
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

  // Case 1: Last message was a toolResult that failed or errored
  if (msg.role === "toolResult" && msg.isError) {
    return "The previous step was interrupted or encountered an error. Please inspect the error details and system state, then resume execution from the interrupted step.";
  }

  // Case 2: Last message was an assistant message — continue based on suggestions / next steps
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
  pi.on("input", async (event, _ctx) => {
    const text = event.text.trim().toLowerCase();
    if (text === "continue") {
      return {
        action: "transform",
        text: "Please continue execution based on the suggestions, incomplete steps, or interrupted state from the previous response.",
      };
    }
    return { action: "continue" };
  });

  // 2. Register /continue slash command
  pi.registerCommand("continue", {
    description: "Resume from an interrupted step or continue execution based on the previous response",
    handler: async (args, ctx) => {
      await ctx.waitForIdle();
      const promptText = args.trim() || buildContinuationPrompt(ctx);
      pi.sendUserMessage(promptText);
    },
  });
}
