/**
 * @fradser/pi-recap — pure recap generation helpers.
 */

import type { Api, AssistantMessage, Model, TextContent, UserMessage } from "@earendil-works/pi-ai";
import type { ModelRegistry } from "@earendil-works/pi-coding-agent";

/** Minimal structural view of a session message entry. */
export const RECAP_TIMEOUT_MS = 30_000;

export interface RecapSessionEntry {
  type: string;
  message?: {
    role?: string;
    content?: unknown;
  };
}

/** Extract plain text from a message content (string or content-block array). */
export function extractMessageText(entry: RecapSessionEntry): string | undefined {
  if (entry.type !== "message") return undefined;
  const msg = entry.message;
  if (!msg) return undefined;
  const content = msg.content;
  if (typeof content === "string") return content.trim() || undefined;
  if (Array.isArray(content)) {
    const text = content
      .filter(
        (part): part is { type?: string; text?: string } =>
          typeof part === "object" && part !== null && "type" in part,
      )
      .map((part) => (part.type === "text" && typeof part.text === "string" ? part.text : ""))
      .join("\n")
      .trim();
    return text || undefined;
  }
  return undefined;
}

/**
 * Get the last user message and assistant message from the session branch.
 * Returns undefined when there are not enough messages to generate a recap.
 */
export function getLastExchange(
  entries: RecapSessionEntry[],
): { user: string; assistant: string } | undefined {
  let lastUser: string | undefined;
  let lastAssistant: string | undefined;

  for (let i = entries.length - 1; i >= 0; i--) {
    const entry = entries[i];
    if (entry.type !== "message") continue;
    const msg = entry.message;
    if (!msg) continue;

    if (msg.role === "assistant" && !lastAssistant) {
      const text = extractMessageText(entry);
      if (text) lastAssistant = text;
    } else if (msg.role === "user" && !lastUser) {
      const text = extractMessageText(entry);
      if (text) lastUser = text;
    }

    if (lastUser && lastAssistant) break;
  }

  if (!lastUser || !lastAssistant) return undefined;
  return { user: lastUser, assistant: lastAssistant };
}

/**
 * Build the prompt for recap generation: summarise the last exchange while
 * maintaining continuity with the previous recap and respecting language preference.
 */
export function buildRecapPrompt(
  user: string,
  assistant: string,
  previousRecap?: string,
  language: string = "auto",
): string {
  let langRule = "- Use the same language as the conversation.";
  const l = language.toLowerCase();
  if (l === "zh" || l === "zh-cn" || l === "chinese") {
    langRule = "- Always output in Chinese (\u4E2D\u6587).";
  } else if (l === "en" || l === "english") {
    langRule = "- Always output in English.";
  } else if (l !== "auto") {
    langRule = `- Always output in ${language}.`;
  }

  const lines = [
    "You are an informative session recap generator.",
    "Summarise the latest session progress in one single-line recap of at most 120 characters.",
    "Include only the action, target, and result or current progress.",
    "Rules:",
    "- Maintain continuous context: update and advance the previous recap with the latest work done.",
    "- State the specific action, target components/files, and key outcome or current progress.",
    "- Output ONLY the summary text. No quotes, no markdown, no conversational filler, no prefixes.",
    "- Single line only (no newlines).",
    langRule,
    "- Be concrete and scannable rather than vague.",
    "- Do not explain, advise, greet, repeat the prompt, or mention this conversation."
  ];

  if (previousRecap && previousRecap.trim()) {
    lines.push(
      "",
      "=== Previous recap ===",
      previousRecap.trim(),
    );
  }

  lines.push(
    "",
    "=== Last user message ===",
    user.slice(0, 1000),
    "",
    "=== Last assistant response ===",
    assistant.slice(0, 1500),
  );

  return lines.join("\n");
}

/**
 * Clean and normalise the raw model output into a single scannable line.
 */
export function cleanRecapText(raw: string): string {
  if (!raw) return "";
  let text = raw.trim();
  // Strip code blocks or backticks
  text = text.replace(/^```[a-z]*\n?|```$/gi, "").trim();
  // Strip outer quotes
  text = text.replace(/^["'“‘`]+|["'”’`]+$/g, "").trim();
  // Strip common label prefixes like "※ Recap:", "recap:", "Summary:", "- ", "* "
  text = text.replace(/^(?:※\s*)?(?:recap|summary|status)\s*[:\uFF1A]\s*/i, "");
  text = text.replace(/^[-*•]\s*/, "");
  // Replace newlines and multi-spaces with single space
  text = text.replace(/\s+/g, " ").trim();
  // Strip trailing period if present
  text = text.replace(/[.\u3002]+$/, "");
  // Keep the display contract aligned with the prompt's hard limit.
  return text.slice(0, 120).trim();
}

/** Extract text from assistant message response. */
export function textFromResponse(message: AssistantMessage): string {
  if (!message || !message.content || !Array.isArray(message.content)) return "";
  const text = message.content
    .filter((part): part is TextContent => part.type === "text" && typeof part.text === "string")
    .map((part) => part.text)
    .join("\n")
    .trim();
  if (text) return text;

  return "";
}

/**
 * Generate a concise recap in-process using Pi's ModelRegistry.
 */
export async function generateRecap(
  registry: ModelRegistry,
  model: Model<Api>,
  user: string,
  assistant: string,
  previousRecap?: string,
  language: string = "auto",
  signal?: AbortSignal,
): Promise<string> {
  const auth = await registry.getApiKeyAndHeaders(model);
  if (!auth.ok) return "";

  const prompt = buildRecapPrompt(user, assistant, previousRecap, language);
  const message: UserMessage = {
    role: "user",
    content: [{ type: "text", text: prompt }],
    timestamp: Date.now(),
  };

  const controller = new AbortController();
  const abort = () => controller.abort();
  const timeout = setTimeout(abort, RECAP_TIMEOUT_MS);
  signal?.addEventListener("abort", abort, { once: true });

  try {
    const response = await registry.complete(
      model,
      {
        systemPrompt: "You generate ultra-concise, single-line session recaps.",
        messages: [message],
      },
      {
        apiKey: auth.apiKey,
        headers: auth.headers,
        signal: controller.signal,
        maxTokens: 96,
        temperature: 0,
        cacheRetention: "none",
      },
    );

    return cleanRecapText(textFromResponse(response));
  } catch {
    return "";
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
}
