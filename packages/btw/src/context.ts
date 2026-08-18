/**
 * btw context — builds a read-only excerpt of the recent conversation so the
 * side question can answer from what is already in the session (the same
 * guarantee Claude Code's /btw gives, minus the tool-calling limitation).
 */

import { extractTextContent } from "@fradser/pi-kit";

export const DEFAULT_MAX_MESSAGES = 4;
export const DEFAULT_MAX_CHARS = 4_000;

export interface BuildContextOptions {
  /** Maximum number of recent user/assistant messages to include. */
  maxMessages?: number;
  /** Maximum total excerpt length (keeps the tail — the most recent context). */
  maxChars?: number;
}

/** Minimal structural view of the session manager: only getBranch() is needed. */
export interface SessionManagerLike {
  getBranch(): unknown[];
}

type BranchEntry = {
  type?: string;
  message?: {
    role?: string;
    content?: unknown;
  };
};

/**
 * Build a compact, most-recent-first conversation excerpt from the current
 * session branch. Only user and assistant text messages are included.
 */
export function buildConversationContext(
  sessionManager: SessionManagerLike,
  options: BuildContextOptions = {},
): string {
  const maxMessages = options.maxMessages ?? DEFAULT_MAX_MESSAGES;
  const maxChars = options.maxChars ?? DEFAULT_MAX_CHARS;

  const entries = sessionManager.getBranch() as unknown as BranchEntry[];
  const parts: string[] = [];
  for (let i = entries.length - 1; i >= 0 && parts.length < maxMessages; i--) {
    const entry = entries[i];
    if (!entry || entry.type !== "message") continue;
    const msg = entry.message;
    if (!msg || (msg.role !== "user" && msg.role !== "assistant")) continue;
    const text = extractTextContent(msg.content).trim();
    if (!text) continue;
    parts.push(`[${msg.role}] ${text}`);
  }
  parts.reverse();

  const joined = parts.join("\n\n");
  if (joined.length <= maxChars) return joined;
  return `…${joined.slice(joined.length - maxChars)}`;
}
