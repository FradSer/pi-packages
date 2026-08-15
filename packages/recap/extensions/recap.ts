/**
 * @fradser/pi-recap — pure recap helpers (no pi runtime imports).
 *
 * Kept separate from the extension entry so these pure functions can be
 * unit-tested in isolation, mirroring how @fradser/pi-btw splits its
 * spawner/context modules from the extension entry point.
 */

/** Minimal structural view of a session message entry. */
export interface RecapSessionEntry {
  type: string;
  message?: {
    role?: string;
    content?: unknown;
  };
}

/** Extract the plain text from a message content (string or content-block array). */
export function extractMessageText(entry: RecapSessionEntry): string | undefined {
  if (entry.type !== "message") return undefined;
  const msg = entry.message;
  if (!msg) return undefined;
  const content = msg.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .filter(
        (part): part is { type?: string; text?: string } =>
          typeof part === "object" && part !== null && "type" in part,
      )
      .map((part) => (part.type === "text" && typeof part.text === "string" ? part.text : ""))
      .join("\n");
  }
  return undefined;
}

/**
 * Get the last user message and assistant message from the session branch.
 * Returns undefined when there aren't enough messages to generate a recap.
 */
export function getLastExchange(
  entries: RecapSessionEntry[],
): { user: string; assistant: string } | undefined {
  let lastUser: string | undefined;
  let lastAssistant: string | undefined;

  // Walk backwards: find the most recent user + assistant pair
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
 * Build the prompt for recap generation: summarise the last exchange in
 * one concise line (≤80 chars), starting with a present-tense verb.
 */
export function buildRecapPrompt(user: string, assistant: string): string {
  return [
    `You are generating a concise one-line session recap.`,
    `Summarise what the session is currently doing based on the last exchange below.`,
    `Rules:`,
    `- Output ONLY the recap text (no prefix, no quotes, no labels).`,
    `- Maximum 80 characters.`,
    `- Use the same language as the conversation.`,
    `- Start with a verb in present tense (e.g. "Fixing the login redirect bug" or "Refactoring the API client").`,
    `- Be specific enough to be useful, short enough to be scannable.`,
    ``,
    `=== Last user message ===`,
    user.slice(0, 500),
    ``,
    `=== Last assistant response ===`,
    assistant.slice(0, 500),
  ].join("\n");
}

/**
 * Parse the JSONL output of the child Pi process.
 * Extracts the last assistant message text from the event stream.
 */
export function parseRecapOutput(stdout: string): string {
  for (const line of stdout.split("\n").reverse()) {
    if (!line.trim()) continue;
    try {
      const event = JSON.parse(line) as {
        type?: string;
        message?: { role?: string; content?: Array<{ type?: string; text?: string }> };
      };
      if (event.type === "message_end" && event.message?.role === "assistant") {
        const parts = (event.message.content ?? [])
          .filter((part) => part.type === "text" && typeof part.text === "string")
          .map((part) => part.text as string)
          .join("");
        if (parts.trim()) return parts.trim();
      }
    } catch {
      continue;
    }
  }
  return "";
}