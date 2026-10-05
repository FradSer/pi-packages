/**
 * pi-recap-fradser — pure recap generation helpers.
 */

import type {
  Api,
  AssistantMessage,
  Model,
  TextContent,
  UserMessage,
} from "@earendil-works/pi-ai";
import type { ModelRegistry } from "@earendil-works/pi-coding-agent";
import { extractTextContent } from "@fradser/pi-kit";

/** Wall-clock budget for one whole recap request, credentials included. */
export const RECAP_TIMEOUT_MS = 30_000;

/** Hard display limit, mirroring the "at most 120 characters" prompt rule. */
export const RECAP_TEXT_LIMIT = 120;

/** Minimal structural view of a session message entry. */
export interface RecapSessionEntry {
  type: string;
  customType?: string;
  data?: unknown;
  message?: {
    role?: string;
    content?: unknown;
    stopReason?: string;
    errorMessage?: string;
  };
}

/**
 * Extract the most recent saved recap from custom entries in the session branch.
 * Returns undefined when no persisted recap entry is found.
 */
export function extractLatestSavedRecap(
  entries: RecapSessionEntry[],
): string | undefined {
  if (!Array.isArray(entries)) return undefined;

  for (let i = entries.length - 1; i >= 0; i--) {
    const entry = entries[i];
    if (entry && entry.type === "custom" && entry.customType === "recap") {
      const data = entry.data as
        | { recap?: unknown; text?: unknown }
        | undefined;
      if (typeof data?.recap === "string" && data.recap.trim()) {
        return data.recap.trim();
      }
      if (typeof data?.text === "string" && data.text.trim()) {
        return data.text.trim();
      }
    }
  }

  return undefined;
}

/** Extract plain text from a message content (string or content-block array). */
export function extractMessageText(
  entry: RecapSessionEntry,
): string | undefined {
  if (entry.type !== "message") return undefined;
  const msg = entry.message;
  if (!msg) return undefined;
  return extractTextContent(msg.content).trim() || undefined;
}

/**
 * Get the last user message and assistant message from the session branch.
 * Returns undefined when there are not enough messages to generate a recap.
 */
export function getLastExchange(
  entries: RecapSessionEntry[],
): { user: string; assistant: string } | undefined {
  let pendingUser: string | undefined;
  let lastCompleteExchange: { user: string; assistant: string } | undefined;

  for (const entry of entries) {
    if (entry.type !== "message") continue;
    const msg = entry.message;
    if (!msg) continue;

    if (msg.role === "user") {
      pendingUser = extractMessageText(entry);
      continue;
    }

    if (msg.role !== "assistant") continue;

    // `toolUse` is an intermediate assistant message. A final answer is only
    // complete when the provider stopped normally (or when an older entry has
    // no stopReason field) and contains displayable text. Aborted, failed,
    // length-limited, and other incomplete responses must not borrow the last
    // answer from an earlier user request.
    const stopReason = msg.stopReason;
    if (stopReason === "toolUse") continue;
    const text = extractMessageText(entry);
    const failed = Boolean(msg.errorMessage) ||
      (stopReason !== undefined && stopReason !== "stop");
    if (failed || !text) {
      pendingUser = undefined;
      continue;
    }

    if (pendingUser) {
      lastCompleteExchange = { user: pendingUser, assistant: text };
    }
  }

  return lastCompleteExchange;
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

  const hasAssistantOutcome = assistant.trim().length > 0;
  // One rule per distinct failure mode. The evidence rules used to be four
  // near-duplicate lines; every recap paid for the redundancy and the model
  // weighed the repeated wording above the rule that actually applied.
  const lines = [
    "You are an informative session recap generator.",
    "Summarise the latest session progress in one single-line recap of at most 120 characters.",
    "Include only the action, target, and result or current progress.",
    "Rules:",
    "- One line naming the action, its target files or components, and the evidenced outcome or current progress.",
    "- Do not claim actions, files, connections, or results that are not evidenced; access, permission, or a referenced path is not evidence that a connection was made or a file inspected.",
    "- Advance the previous recap with the latest work done instead of restarting the summary.",
    "- Output only the summary text: no quotes, markdown, prefixes, explanations, advice, or greetings.",
    "- Be concrete and scannable; a specific short claim beats a vague long one.",
    langRule,
  ];

  if (!hasAssistantOutcome) {
    lines.push(
      "- The assistant has not reported an outcome yet: describe the work as starting, planned, or requested, never as completed or currently being debugged.",
    );
  }

  if (previousRecap?.trim()) {
    lines.push("", "=== Previous recap ===", previousRecap.trim());
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

/** Split text into user-perceived characters so a cap never breaks one in half. */
function toGraphemes(text: string): string[] {
  const Segmenter = Intl.Segmenter;
  if (typeof Segmenter !== "function") return Array.from(text);
  return Array.from(
    new Segmenter(undefined, { granularity: "grapheme" }).segment(text),
    (part) => part.segment,
  );
}

/**
 * Enforce the display contract without corrupting the text: cut on grapheme
 * boundaries so no astral character is split into a lone surrogate, then drop a
 * code span the cut opened but never closed, which the widget would otherwise
 * render with a literal backtick.
 */
function capRecapText(text: string, limit: number): string {
  const graphemes = toGraphemes(text);
  let capped = graphemes.length <= limit ? text : graphemes.slice(0, limit).join("");
  const backticks = capped.split("`").length - 1;
  if (backticks % 2 !== 0) {
    capped = capped.slice(0, capped.lastIndexOf("`")).trimEnd();
  }
  return capped.trim();
}

/**
 * Clean and normalise the raw model output into a single scannable line.
 */
export function cleanRecapText(raw: string): string {
  if (!raw) return "";
  let text = raw.trim();
  // Strip code blocks or backticks
  text = text.replace(/^```[a-z]*\n?|```$/gi, "").trim();
  // Strip quotes only when they wrap the complete summary. An inline code
  // marker at the start of a summary must remain paired for Markdown rendering.
  const outerQuotePairs: Array<[string, string]> = [
    ["\"", "\""],
    ["'", "'"],
    ["“", "”"],
    ["‘", "’"],
    ["`", "`"],
  ];
  for (const [opening, closing] of outerQuotePairs) {
    if (text.startsWith(opening) && text.endsWith(closing)) {
      text = text.slice(opening.length, -closing.length).trim();
      break;
    }
  }
  // Strip common label prefixes like "※ Recap:", "recap:", "Summary:", "- ", "* "
  text = text.replace(/^(?:※\s*)?(?:recap|summary|status)\s*[:\uFF1A]\s*/i, "");
  text = text.replace(/^※\s*/, "");
  text = text.replace(/^[-*•]\s*/, "");
  // Replace newlines and multi-spaces with single space
  text = text.replace(/\s+/g, " ").trim();
  // Strip trailing period if present
  text = text.replace(/[.\u3002]+$/, "");
  // Keep the display contract aligned with the prompt's hard limit.
  return capRecapText(text, RECAP_TEXT_LIMIT);
}

/** Reject empty labels and generic verb-plus-identifier output with no useful context. */
export function isInformativeRecap(text: string): boolean {
  const recap = text.trim();
  if (!recap) return false;

  const identifier = "[`'\"“”‘’]?[A-Za-z0-9_.\u4E00-\u9FFF:/-][A-Za-z0-9_.\u4E00-\u9FFF:/-]*[`'\"“”‘’]?";
  // The identifier must cover the languages this package is configured for: an
  // ASCII-only pattern let a bare Chinese object through the gate that rejects
  // the same shape in English.
  if (new RegExp(`^${identifier}$`).test(recap)) return false;

  const genericAction =
    "(?:fix(?:ed|ing)?|update(?:d|ing)?|adjust(?:ed|ing)?|improve(?:d|ing)?|refactor(?:ed|ing)?|\\u4fee\\u6b63|\\u4fee\\u590d|\\u4fee\\u6539|\\u66f4\\u65b0|\\u4f18\\u5316|\\u8c03\\u6574|\\u5904\\u7406|\\u6539\\u8fdb|\\u5b8c\\u5584)";
  // Two shapes carry no information: a generic verb followed by a bare name, and
  // a generic verb followed by nothing but its label.
  const genericWithName = new RegExp(
    `^${genericAction}\\s*[:\\uFF1A-]?\\s*${identifier}$`,
    "i",
  );
  const bareLabel = new RegExp(`^${genericAction}\\s*[:\\uFF1A-]+\\s*$`, "i");
  return !(genericWithName.test(recap) || bareLabel.test(recap));
}

/** Extract text from assistant message response. */
export function textFromResponse(message: AssistantMessage): string {
  if (!message?.content || !Array.isArray(message.content)) return "";
  const text = message.content
    .filter(
      (part): part is TextContent =>
        part.type === "text" && typeof part.text === "string",
    )
    .map((part) => part.text)
    .join("\n")
    .trim();
  if (text) return text;

  return "";
}

/**
 * Arm the request's single wall-clock boundary.
 *
 * The boundary is armed before credentials are requested, and it settles the
 * returned promise instead of only signalling the provider: credential lookup
 * takes no signal, and a provider that ignores one would otherwise leave the
 * caller awaiting a recap that can never arrive.
 */
function armRecapDeadline(
  signal: AbortSignal | undefined,
  timeoutMs: number,
): { controller: AbortController; settled: Promise<string>; dispose: () => void } {
  const controller = new AbortController();
  let release: (() => void) | undefined;
  const settled = new Promise<string>((resolve) => {
    release = () => resolve("");
  });
  const abort = () => {
    controller.abort();
    release?.();
  };
  const timer = setTimeout(abort, timeoutMs);
  signal?.addEventListener("abort", abort, { once: true });
  // A signal that aborted between the caller's check and this listener would
  // never fire it, so re-read the state once the handlers exist.
  if (signal?.aborted) abort();
  return {
    controller,
    settled,
    dispose: () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
    },
  };
}

/**
 * Generate a concise recap in-process using Pi's ModelRegistry.
 *
 * Always settles: a deadline, an external abort, and an uncooperative provider
 * all resolve to an empty recap instead of hanging the caller.
 */
export async function generateRecap(
  registry: ModelRegistry,
  model: Model<Api>,
  user: string,
  assistant: string,
  previousRecap?: string,
  language: string = "auto",
  signal?: AbortSignal,
  timeoutMs: number = RECAP_TIMEOUT_MS,
): Promise<string> {
  if (signal?.aborted) return "";
  const deadline = armRecapDeadline(signal, timeoutMs);
  const { controller } = deadline;

  try {
    const work = (async (): Promise<string> => {
      const auth = await registry.getApiKeyAndHeaders(model);
      if (!auth.ok || controller.signal.aborted) return "";

      const prompt = buildRecapPrompt(user, assistant, previousRecap, language);
      for (let attempt = 0; attempt < 2; attempt++) {
        const retryRule = attempt === 0
          ? ""
          : "\n\nPrevious output was rejected as empty or uninformative. Include the specific target, concrete work or progress, and evidenced outcome; do not return only a generic verb plus a name.";
        const message: UserMessage = {
          role: "user",
          content: [{ type: "text", text: `${prompt}${retryRule}` }],
          timestamp: Date.now(),
        };

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
              maxTokens: 512,
              temperature: 0,
              cacheRetention: "none",
            },
          );

          if (controller.signal.aborted) return "";
          const text = cleanRecapText(textFromResponse(response));
          if (isInformativeRecap(text)) return text;
        } catch {
          return "";
        }
      }
      return "";
    })();
    return await Promise.race([work, deadline.settled]);
  } finally {
    deadline.dispose();
  }
}

/** One recap request's identity, shared by generation and by startup restore. */
export function recapRequestKey(
  exchange: { user: string; assistant: string },
  model: Pick<Model<Api>, "provider" | "id">,
  language: string,
): string {
  return [
    exchange.user,
    exchange.assistant,
    model.provider,
    model.id,
    language,
  ].join("\u0000");
}

/** Outcome of the automatic-recap cost policy. */
export interface AutoRecapDecision {
  enabled: boolean;
  /** Present when automatic recapping is suppressed by policy, not by choice. */
  reason?: string;
}

/** Whether recapping this model needs an explicit opt-in. */
function needsRecapOptIn(model: Pick<Model<Api>, "reasoning">): boolean {
  return model.reasoning === true;
}

/**
 * Decide whether a settled turn may recap itself.
 *
 * An explicit `autoRecap` preference always wins. Otherwise a reasoning model
 * the user never chose for recaps is too expensive to run on every turn: its
 * reasoning budget is spent before any summary text exists, and the recap then
 * competes with the turn that paid for it. Such a model keeps manual
 * `/recap now`, the restored recap line, and the display — only the automatic
 * per-turn call is withheld until the user opts in or names a recap model.
 */
export function resolveAutoRecap(
  preference: boolean | undefined,
  model: Pick<Model<Api>, "reasoning"> | undefined,
  hasModelOverride: boolean,
): AutoRecapDecision {
  if (preference !== undefined) {
    return { enabled: preference };
  }
  if (model && !hasModelOverride && needsRecapOptIn(model)) {
    return {
      enabled: false,
      reason:
        "off by default for reasoning models; run /recap auto or choose a recap model",
    };
  }
  return { enabled: true };
}
