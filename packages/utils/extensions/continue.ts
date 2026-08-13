/**
 * @fradser/utils — native pi /continue command and multilingual continuation input interception.
 *
 * Intercepts continuation requests across multiple languages (English, Chinese, Japanese,
 * Korean, Spanish, French, German, Russian, Portuguese, Italian).
 *
 * Behavior matrix:
 *   - Interrupted / Aborted turn -> Silent resume (display: false) to avoid chat transcript clutter.
 *   - Normal Completed turn -> Visible message (display: true / sendUserMessage) so the transcript clearly shows the continuation prompt.
 *
 * Usage:
 *   /continue [optional extra prompt]
 *   or simply reply "continue", "继续", "続行", "계속", "continuar", etc. in conversation.
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

export interface ContinuationTarget {
  promptText: string;
  isInterrupted: boolean;
}

const MULTILINGUAL_CONTINUE_PATTERNS = [
  // English
  "continue",
  "go on",
  "proceed",
  "keep going",
  "resume",
  "carry on",
  // Chinese (Simplified & Traditional)
  "继续",
  "继续吧",
  "继续执行",
  "继续做",
  "继续完成",
  "继续往下",
  "下一步",
  "繼續",
  "繼續吧",
  "繼續執行",
  // Japanese
  "続行",
  "続けて",
  "つづけて",
  "続行して",
  "次へ",
  "つぎへ",
  // Korean
  "계속",
  "계속해",
  "계속 진행",
  "다음",
  // Spanish
  "continuar",
  "sigue",
  "adelante",
  // French
  "continuer",
  "poursuivre",
  // German
  "weitermachen",
  "fortfahren",
  "weiter",
  // Russian
  "продолжай",
  "продолжить",
  "дальше",
  // Portuguese
  "continuar",
  "prosseguir",
  // Italian
  "continua",
  "prosegui",
];

const CONTINUE_SET = new Set(MULTILINGUAL_CONTINUE_PATTERNS.map((p) => p.toLowerCase()));

/**
 * Check if the raw input matches a continuation keyword/phrase in any supported language.
 */
export function isContinuationKeyword(rawInput: string): boolean {
  if (!rawInput) return false;
  // Normalize: strip leading & trailing punctuation, symbols, and whitespace
  const normalized = rawInput
    .trim()
    .toLowerCase()
    .replace(/^[\p{P}\p{S}\s]+|[\p{P}\p{S}\s]+$/gu, "");
  return CONTINUE_SET.has(normalized);
}

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
 * Inspect the session history to construct a continuation prompt and determine
 * whether the turn was interrupted (requires silent resume) or completed (requires visible message).
 */
export function resolveContinuation(ctx: ExtensionContext, customArgs?: string): ContinuationTarget {
  const raw = customArgs?.trim();
  if (raw) {
    return { promptText: raw, isInterrupted: false };
  }

  const branch = ctx.sessionManager.getBranch();
  if (branch.length === 0) {
    return { promptText: "Please continue execution.", isInterrupted: false };
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
    return { promptText: "Please continue execution.", isInterrupted: false };
  }

  const msg = lastMessageEntry.message;

  // Case 1: Trailing message is a user prompt (assistant turn was aborted before saving entry)
  if (msg.role === "user") {
    const userText = getLastUserPrompt(ctx);
    return {
      promptText: userText ?? "Please resume execution from the last request.",
      isInterrupted: true,
    };
  }

  // Case 2: Most recent assistant message was aborted (stopReason === "aborted") -> re-run last user request directly & silently
  for (let i = branch.length - 1; i >= 0; i--) {
    const entry = branch[i];
    if (entry.type === "message" && entry.message.role === "assistant") {
      if (entry.message.stopReason === "aborted") {
        const lastUserText = getLastUserPrompt(ctx);
        return {
          promptText: lastUserText ?? "The previous turn was aborted. Please resume execution from where it was interrupted.",
          isInterrupted: true,
        };
      }
      break; // Only check the latest assistant message
    }
  }

  // Case 3: Last message was a toolResult that failed or errored -> resume silently
  if (msg.role === "toolResult" && msg.isError) {
    const toolName = msg.toolName ? ` (${msg.toolName})` : "";
    return {
      promptText: `The previous step${toolName} was interrupted or encountered an error. Please inspect the error details and system state, then resume execution from the interrupted step.`,
      isInterrupted: true,
    };
  }

  // Case 4: Last assistant message completed normally — prompt AI to continue based on suggestions (visible message)
  return {
    promptText: "Please continue execution based on the suggestions, incomplete steps, or next actions from your previous response.",
    isInterrupted: false,
  };
}

export default function (pi: ExtensionAPI) {
  // 1. Intercept plain user input matching multilingual continuation keywords
  pi.on("input", async (event, ctx) => {
    if (isContinuationKeyword(event.text)) {
      const { promptText, isInterrupted } = resolveContinuation(ctx);

      if (isInterrupted) {
        // Interrupted turn: silently trigger re-run without cluttering UI with duplicate prompt
        pi.sendMessage(
          {
            customType: "continue-extension",
            content: promptText,
            display: false,
          },
          {
            triggerTurn: true,
          },
        );
        return { action: "handled" };
      }

      // Completed task: user typed continuation keyword to proceed to next steps — transform and display visibly
      return {
        action: "transform",
        text: promptText,
      };
    }
    return { action: "continue" };
  });

  // 2. Register /continue slash command
  pi.registerCommand("continue", {
    description: "Resume from an interrupted step (silently) or continue execution based on previous response (visibly)",
    handler: async (args, ctx) => {
      await ctx.waitForIdle();
      const { promptText, isInterrupted } = resolveContinuation(ctx, args);

      if (isInterrupted) {
        // Interrupted: silent resume
        pi.sendMessage(
          {
            customType: "continue-extension",
            content: promptText,
            display: false,
          },
          {
            triggerTurn: true,
          },
        );
      } else {
        // Normal completion: visible user message
        pi.sendUserMessage(promptText);
      }
    },
  });
}
