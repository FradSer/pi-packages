/**
 * @fradser/pi-utils — native pi /continue command and continuation input interception.
 *
 * Intercepts plain text continuation requests ("continue" / "继续" / "繼續").
 *
 * Behavior matrix:
 *   - Interrupted, provider/API-failed, or truncated turn -> Direct continuation without adding continuation text to LLM context.
 *   - Normal completed turn -> Visible user message so the transcript and LLM context include the continuation request.
 *
 * Usage:
 *   /continue [optional extra prompt]
 *   or simply reply "continue" or "继续" in conversation.
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

export interface ContinuationTarget {
  promptText: string;
  isDirectContinuation: boolean;
  requiresUserAction?: boolean;
}

const CONTINUE_SET = new Set(["continue", "继续", "繼續"]);
const CONTINUATION_MESSAGE_TYPE = "continue-extension";
const TRANSIENT_PROVIDER_ERROR_PATTERN =
  /overloaded|rate.?limit|too many requests|\b429\b|\b5(?:00|02|03|04|24)\b|service.?unavailable|server.?error|internal.?error|provider.?returned.?error|network.?error|connection.?error|connection.?refused|connection.?lost|other side closed|fetch failed|getaddrinfo|ENOTFOUND|EAI_AGAIN|upstream.?connect|reset before headers|ECONNRESET|socket hang up|socket connection was closed|timed? out|timeout|terminated|websocket.?closed|websocket.?error|ended without|stream ended before|http2 request did not get a response|retry delay|you can retry your request|try your request again|please retry your request|ResourceExhausted/i;

/**
 * Check if the raw input matches the continuation keyword ("continue" / "继续").
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
 * whether the turn can continue directly (without a new user message) or needs
 * a visible user message.
 */
async function resolvePreflightFailure(ctx: ExtensionContext): Promise<string | null> {
  if (!ctx.model) {
    return "Cannot continue because no model is selected. Select a model before retrying.";
  }
  const hasConfiguredAuth = ctx.modelRegistry.hasConfiguredAuth(ctx.model);
  const resolvedAuth = hasConfiguredAuth
    ? true
    : (await ctx.modelRegistry.getProviderAuth(ctx.model.provider)) !== undefined;
  if (!resolvedAuth) {
    return `Cannot continue because no usable authentication is configured for ${ctx.model.provider}/${ctx.model.id}. Add credentials or switch providers before retrying.`;
  }
  return null;
}

function resolveLengthContinuation(
  message: Extract<ContinuationMessage, { role: "assistant" }>,
  contextWindow?: number,
): ContinuationDecision {
  const usage = message.usage;
  const inputTokens = (usage?.input ?? 0) + (usage?.cacheRead ?? 0);
  const likelyOverflow =
    usage?.output === 0 && contextWindow !== undefined && inputTokens >= contextWindow * 0.99;

  if (likelyOverflow) {
    return {
      promptText:
        "The previous model response produced no output because the context is full. Reduce context, compact the session, or switch to a larger-context model before continuing.",
      requiresUserAction: true,
    };
  }

  return {
    promptText:
      "The previous model response was truncated before completion. Inspect the current state and continue from the last completed step without repeating completed work.",
  };
}

interface ContinuationDecision {
  promptText: string;
  requiresUserAction?: boolean;
}

function resolveAssistantErrorContinuation(
  message: Extract<ContinuationMessage, { role: "assistant" }>,
  lastUserText: string | null,
): ContinuationDecision {
  const error = message.errorMessage?.trim() ?? "";
  const normalized = error.toLowerCase();
  const detail = error ? ` Provider detail: ${error.slice(0, 300)}` : " The provider did not return an error message.";

  if (/context overflow recovery failed|context[_ ]length[_ ]exceeded|context window|maximum context length|prompt is too long|too many tokens|token limit exceeded|request_too_large|reduce the length of the messages|input token count.*exceeds|maximum prompt length|exceeds the available context size|greater than the context length|range of input length should be/.test(normalized)) {
    return {
      promptText: "The previous model request failed because the context is too large. Reduce context, compact the session, or switch to a larger-context model; do not blindly repeat the same overflowing request.",
      requiresUserAction: true,
    };
  }
  if (/invalid[_ ]request|invalid parameter|malformed request|model_not_found|model .*not found|unknown model|does not exist|unsupported model|unsupported parameter/.test(normalized)) {
    return {
      promptText: "The previous model request was rejected as invalid or the selected model is unavailable. Fix the request or switch models before retrying.",
      requiresUserAction: true,
    };
  }
  if (/authentication failed|no api key|api key|unauthorized|invalid.*key|credentials.*expired|401\b|403\b|authheader requires a resolved api key|does not support deferred responses|cannot cancel deferred responses/.test(normalized)) {
    return {
      promptText: "The previous model request failed because provider authentication is unavailable. Fix the API key or login credentials, or switch providers, before retrying.",
      requiresUserAction: true,
    };
  }
  if (/insufficient_quota|quota|billing|out of budget|monthly usage limit|available balance/.test(normalized)) {
    return {
      promptText: "The previous model request failed because the provider quota or billing limit is exhausted. Resolve the account limit or switch providers before retrying.",
      requiresUserAction: true,
    };
  }
  if (/content_filter|content filtering|safety|moderation|refus|sensitive|policy|response incomplete: content_filter/.test(normalized)) {
    return {
      promptText: "The previous model request was blocked by provider safety or content policy. Rephrase the request safely or switch to another suitable model instead of repeating it unchanged.",
      requiresUserAction: true,
    };
  }

  const promptText = lastUserText
    ? `The previous model request failed.${detail} Inspect the error and current state, then retry the last request without repeating work that already completed.`
    : `The previous model request failed.${detail} Inspect the error and current state, then resume without repeating work that already completed.`;
  if (!error || TRANSIENT_PROVIDER_ERROR_PATTERN.test(error)) {
    return { promptText };
  }

  return {
    promptText: `${promptText} This error is not recognized as a transient provider failure; fix the reported problem before retrying.`,
    requiresUserAction: true,
  };
}

function resolvePendingContinuation(ctx: ExtensionContext): ContinuationDecision {
  const branch = ctx.sessionManager.getBranch();
  const lastAssistant = [...branch]
    .reverse()
    .find((entry) => entry.type === "message" && entry.message.role === "assistant");
  const toolCallCount =
    lastAssistant?.type === "message" && lastAssistant.message.role === "assistant"
      ? lastAssistant.message.content.filter((part) => part.type === "toolCall").length
      : 0;

  return {
    promptText:
      toolCallCount > 0
        ? "The previous turn ended before its tool results were completed. Inspect the current state and re-issue only the missing tool calls; do not repeat completed work."
        : "The previous model turn was incomplete. Inspect the current state and resume from the last completed step without repeating completed work.",
  };
}

function resolveToolErrorContinuation(message: Extract<ContinuationMessage, { role: "toolResult" }>): ContinuationDecision {
  const toolName = message.toolName ? ` (${message.toolName})` : "";
  const errorText = message.content
    ?.filter((part): part is { type: "text"; text: string } => part.type === "text" && typeof part.text === "string")
    .map((part) => part.text)
    .join(" ")
    .toLowerCase() ?? "";

  if (/response hit the output token limit|arguments may be truncated|re-issue the tool call/.test(errorText)) {
    return {
      promptText: `The previous tool${toolName} was not executed because the model response was truncated. Re-issue the tool call with complete arguments after checking the current state.`,
    };
  }

  if (/invalid|malformed|model .*not found|tool .*not found|unknown tool|schema|validation/.test(errorText)) {
    return {
      promptText: `The previous tool${toolName} request was invalid. Inspect the validation error, correct the arguments, and retry only the missing tool call.`,
    };
  }

  if (/blocked|denied|not allowed|permission|approval required|user rejected/.test(errorText)) {
    return {
      promptText: `The previous tool${toolName} was blocked or denied. Review the permission decision and choose a permitted alternative before retrying.`,
      requiresUserAction: true,
    };
  }

  return {
    promptText: `The previous step${toolName} was interrupted or encountered an error. Inspect the error details and current state, then resume execution from the interrupted step.`,
  };
}

type ContinuationMessage =
  | {
      role: "assistant";
      stopReason?: string;
      errorMessage?: string;
      usage?: { input?: number; output?: number; cacheRead?: number };
    }
  | { role: "user"; content: unknown }
  | { role: "toolResult"; isError: boolean; toolName?: string; content?: Array<{ type?: string; text?: string }> };

export function resolveContinuation(ctx: ExtensionContext, customArgs?: string): ContinuationTarget {
  const raw = customArgs?.trim();
  if (raw) {
    return { promptText: raw, isDirectContinuation: false };
  }

  const branch = ctx.sessionManager.getBranch();
  if (branch.length === 0) {
    return {
      promptText: "Cannot continue because there is no previous model request.",
      isDirectContinuation: false,
      requiresUserAction: true,
    };
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
    return {
      promptText: "Cannot continue because there is no previous model request.",
      isDirectContinuation: false,
      requiresUserAction: true,
    };
  }

  const msg = lastMessageEntry.message;

  // Case 1: Trailing message is a user prompt (assistant turn was aborted before saving entry)
  if (msg.role === "user") {
    const userText = getLastUserPrompt(ctx);
    return {
      promptText: userText ?? "Please resume execution from the last request.",
      isDirectContinuation: true,
    };
  }

  // Case 2: A failed assistant turn (abort, provider/API error, or truncation)
  if (msg.role === "assistant") {
    const lastUserText = getLastUserPrompt(ctx);

    if (msg.stopReason === "pending" || msg.stopReason === "toolUse") {
      const decision = resolvePendingContinuation(ctx);
      return {
        ...decision,
        isDirectContinuation: true,
      };
    }

    if (msg.stopReason === "aborted") {
      return {
        promptText:
          lastUserText ??
          "The previous turn was aborted. Please resume execution from where it was interrupted.",
        isDirectContinuation: true,
      };
    }

    if (msg.stopReason === "length") {
      const decision = resolveLengthContinuation(msg, ctx.model?.contextWindow);
      return {
        ...decision,
        isDirectContinuation: !decision.requiresUserAction,
      };
    }

    if (msg.stopReason === "deferred") {
      return {
        promptText:
          "The previous model response was deferred and is not complete. Poll or cancel the deferred request, or switch providers, before continuing.",
        isDirectContinuation: false,
        requiresUserAction: true,
      };
    }

    if (msg.stopReason === "error") {
      const decision = resolveAssistantErrorContinuation(msg, lastUserText);
      return {
        ...decision,
        isDirectContinuation: !decision.requiresUserAction,
      };
    }
  }

  // Case 3: Last message was a toolResult that failed or errored -> resume silently
  if (msg.role === "toolResult" && msg.isError) {
    const decision = resolveToolErrorContinuation(msg);
    return {
      ...decision,
      isDirectContinuation: !decision.requiresUserAction,
    };
  }

  // Only a normally stopped assistant turn is a completed model run. Every
  // other trailing message continues from the existing context directly.
  if (msg.role === "assistant" && msg.stopReason === "stop") {
    return {
      promptText: "Please continue execution based on the suggestions, incomplete steps, or next actions from your previous response.",
      isDirectContinuation: false,
    };
  }

  return {
    promptText: "Resume execution from the current context without repeating completed work.",
    isDirectContinuation: true,
  };
}

function isDirectContinuationMarker(message: { role: string; customType?: string }): boolean {
  return message.role === "custom" && message.customType === CONTINUATION_MESSAGE_TYPE;
}

function isIncompleteAssistant(message: { role: string; stopReason?: string }): boolean {
  return message.role === "assistant" && message.stopReason !== "stop";
}

export function stripDirectContinuationMessages<T extends { role: string; customType?: string; stopReason?: string }>(messages: T[]): T[] {
  const filtered: T[] = [];
  for (const message of messages) {
    if (isDirectContinuationMarker(message)) {
      const previous = filtered[filtered.length - 1];
      if (previous && isIncompleteAssistant(previous)) {
        filtered.pop();
      }
      continue;
    }
    filtered.push(message);
  }
  return filtered;
}

function sendDirectContinuation(pi: ExtensionAPI): void {
  pi.sendMessage(
    {
      customType: CONTINUATION_MESSAGE_TYPE,
      content: "",
      display: false,
    },
    {
      triggerTurn: true,
    },
  );
}

export default function (pi: ExtensionAPI) {
  // The hidden marker only starts the agent loop. The context hook removes it,
  // plus the immediately preceding incomplete assistant message, before the
  // provider request is assembled.
  pi.on("context", async (event) => ({
    messages: stripDirectContinuationMessages(event.messages),
  }));
  // 1. Intercept plain user input matching "continue" or "继续"
  pi.on("input", async (event, ctx) => {
    if (isContinuationKeyword(event.text)) {
      const preflightError = await resolvePreflightFailure(ctx);
      if (preflightError) {
        ctx.ui.notify(preflightError, "error");
        return { action: "handled" };
      }

      const target = resolveContinuation(ctx);
      const { promptText, isDirectContinuation } = target;

      if (target.requiresUserAction) {
        ctx.ui.notify(target.promptText, "error");
        return { action: "handled" };
      }

      if (isDirectContinuation) {
        // Direct continuation: trigger a model request without adding a user message.
        sendDirectContinuation(pi);
        return { action: "handled" };
      }

      // A normally completed turn is a new user request and remains visible.
      return {
        action: "transform",
        text: promptText,
      };
    }
    return { action: "continue" };
  });

  // 2. Register /continue slash command
  pi.registerCommand("continue", {
    description: "Resume incomplete work directly; continue completed work with a visible request",
    handler: async (args, ctx) => {
      await ctx.waitForIdle();
      const preflightError = await resolvePreflightFailure(ctx);
      if (preflightError) {
        ctx.ui.notify(preflightError, "error");
        return;
      }

      const target = resolveContinuation(ctx, args);
      const { promptText, isDirectContinuation } = target;

      if (target.requiresUserAction) {
        ctx.ui.notify(promptText, "error");
        return;
      }

      if (isDirectContinuation) {
        // Incomplete turn: direct continuation without a user message.
        sendDirectContinuation(pi);
      } else {
        // Normal completion: visible user message
        pi.sendUserMessage(promptText);
      }
    },
  });
}
