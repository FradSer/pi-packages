/**
 * pi-utils-fradser — model-generated session names via /autoname.
 *
 * Pi's own `/name` is compiled into the interactive mode: submitting `/name`
 * with no argument and no name set answers "Usage: /name <name>". An extension
 * cannot replace it, because the built-in branch runs before extension
 * commands are consulted. `/autoname` is therefore the model-generated
 * counterpart rather than a silent argument:
 *
 *   /autoname                      name this session from the conversation
 *   /autoname release notes        name this session, steered by the argument
 *
 * The name is derived from the user's own requests only, so it reflects what
 * the session is for instead of the assistant's filler. An optional argument
 * becomes a hint for the model. Every failure — no model, no credentials, an
 * empty answer, a provider that never answers — resolves instead of hanging.
 */

import path from "node:path";
import type { ExtensionAPI, ModelRegistry } from "@earendil-works/pi-coding-agent";
import type { Api, AssistantMessage, ModelsSimpleStreamOptions, Model, TextContent, UserMessage } from "@earendil-works/pi-ai";
import { extractTextContent, notifyPi } from "@fradser/pi-kit";

/** Wall-clock budget for one whole name request, credentials included. */
export const AUTONAME_TIMEOUT_MS = 20_000;

/** Hard display limit, mirroring the "at most 4 words" prompt rule. */
export const AUTONAME_NAME_LIMIT = 60;

/**
 * Answer-token budget for one name request.
 *
 * Reasoning and the answer share one response budget on OpenAI-compatible
 * providers, so a budget of a few dozen tokens is spent entirely by reasoning
 * and the answer never starts. The request asks for no reasoning, but a model
 * that cannot disable it still needs room, so the budget covers a short answer
 * plus a thinking phase.
 */
export const AUTONAME_MAX_TOKENS = 1024;

/** Character budget for the session digest sent to the model. */
export const AUTONAME_DIGEST_LIMIT = 1200;

/** How many user requests the digest keeps. The first states the goal; the rest show progress. */
const AUTONAME_DIGEST_REQUESTS = 6;

/** Minimal structural view of one session branch entry. */
export interface AutonameSessionEntry {
  type: string;
  message?: {
    role?: string;
    content?: unknown;
    stopReason?: string;
  };
}

/**
 * Collect the user's own requests from a branch.
 *
 * Only user messages contribute. Assistant answers, tool results, and custom
 * entries describe how a reply was produced, not what the session is for, and
 * an injected fragment from a tool result must never steer the name.
 */
export function collectUserRequests(entries: AutonameSessionEntry[]): string[] {
  const requests: string[] = [];
  for (const entry of entries) {
    if (entry.type !== "message") continue;
    const message = entry.message;
    if (!message || message.role !== "user") continue;
    // A stopped user message is a real request; a user message that only
    // carries an image or an expanded template has no text to name from.
    const text = extractTextContent(message.content, " ").trim();
    if (text) requests.push(text);
  }
  return requests;
}

/**
 * Reduce a branch to a bounded digest of the user's requests.
 *
 * The first request usually states the goal, so it is kept whole; later ones
 * are clipped. The result is clipped again at the budget, because request text
 * is untrusted and can be arbitrarily long.
 */
export function buildDigest(
  entries: AutonameSessionEntry[],
  cwd: string,
  limit: number = AUTONAME_DIGEST_LIMIT,
): string {
  const requests = collectUserRequests(entries);
  const kept = requests.slice(0, AUTONAME_DIGEST_REQUESTS);
  const lines = kept.map((text, index) => {
    const budget = index === 0 ? Math.max(0, Math.floor(limit / 2)) : 160;
    return `${index + 1}. ${text.length > budget ? `${text.slice(0, budget)}...` : text}`;
  });

  const project = path.basename(cwd) || cwd;
  const header = `Project: ${project}\nRequests:`;
  const digest = [header, ...lines].join("\n");
  return digest.length > limit ? `${digest.slice(0, limit)}...` : digest;
}

/**
 * Reduce a model answer to a plain display name.
 *
 * A model answers in prose even when told not to: it wraps the name in quotes,
 * markdown emphasis, or a bullet, and may add a sentence of justification.
 * The session name is shown in a list, so the first line is kept, decoration is
 * stripped, and a long name is cut at a word boundary instead of mid-word.
 * Returns an empty string when nothing displayable survives.
 */
export function cleanSessionName(raw: string, limit: number = AUTONAME_NAME_LIMIT): string {
  const firstLine = raw.split(/\r?\n/).map((line) => line.trim()).find((line) => line.length > 0) ?? "";

  let name = firstLine
    // Headings and a "Name:" lead-in are decoration, not part of the name.
    .replace(/^#+\s*/, "")
    .replace(/^(?:name|session name)\s*[:\-—]\s*/i, "")
    // A single list bullet is removed before emphasis, so "**bold**" survives
    // long enough for the wrapper rules below to see both delimiters.
    .replace(/^[-*+>]\s*/, "")
    // Strip symmetric wrapping quotes and backticks.
    .replace(/^[`'"]+/, "")
    .replace(/[`'"]+$/, "")
    .replace(/^\*\*(.*)\*\*$/, "$1")
    .replace(/^\*(.*)\*$/, "$1")
    // Any leftover emphasis delimiter is now unbalanced and must go.
    .replace(/^[*_]+/, "")
    .replace(/[*_]+$/, "")
    .trim();

  if (!name) return "";

  if (name.length > limit) {
    const clipped = name.slice(0, limit);
    const lastSpace = clipped.lastIndexOf(" ");
    // Cutting at a word boundary needs a space inside the budget; a single
    // unbroken token is cut as-is rather than dropped for having no space.
    name = (lastSpace > limit / 2 ? clipped.slice(0, lastSpace) : clipped).trim();
  }

  // Drop trailing separator punctuation left after the cut.
  name = name.replace(/[\s.,;:!?\-—:]+$/, "").trim();
  return name;
}

/** Whether a response spent part of its budget on reasoning instead of an answer. */
export function hasThinking(message: AssistantMessage): boolean {
  if (!Array.isArray(message?.content)) return false;
  return message.content.some((part) => part.type === "thinking");
}

/** Pull the display text out of an assistant message. */
export function textFromResponse(message: AssistantMessage): string {
  if (!message?.content || !Array.isArray(message.content)) return "";
  return message.content
    .filter((part): part is TextContent => part.type === "text" && typeof part.text === "string")
    .map((part) => part.text)
    .join("\n")
    .trim();
}

/**
 * Rules every name request carries.
 *
 * A model otherwise answers with this conversation restated as a command: on
 * the same session, the previous rules produced "Fix Utils Auto Name" three
 * times in a row. Asking for the subject of the work, forbidding a leading
 * verb, and showing one good name against one bad name produced noun phrases
 * such as "Worktree root selection" instead.
 */
const NAME_RULES = `- Answer with the name only: no quotes, no punctuation at the end, no explanation.
- Use 2 to 4 words naming the subject of the work.
- Start with a noun. Never begin with a verb such as Fix, Repair, Debug, or Investigate.
- Never name the repository, the directory, the package, the model, or the assistant, not
even when the project name appears in the session context.
- Prefer the words a developer would use when searching for this work again.
- Write plain words. Do not use emoji.
- Good: "Worktree root selection". Bad: "Fix the utils package".`;

/** Build the one-shot request that turns a digest into a name. */
function buildPrompt(digest: string, hint: string | undefined): string {
  const lead = "Name this session for a list of past sessions.";
  const request = hint
    ? `${lead}\n\nThe user asked for: ${hint}\n\nSession context:\n${digest}`
    : `${lead}\n\nSession context:\n${digest}`;
  return `${request}\n\nRules:\n${NAME_RULES}`;
}

/** Why a name could not be produced, so the command can report the real cause. */
export type AutonameFailure = "aborted" | "no-credentials" | "provider" | "reasoning" | "timeout" | "unusable";

/** Result of one name request: a name, or the reason there is none. */
export type AutonameOutcome =
  | { ok: true; name: string }
  | { ok: false; reason: AutonameFailure; detail?: string };

/** Report each failure the way the user can act on it. */
export const FAILURE_MESSAGES: Record<AutonameFailure, string> = {
  aborted: "Name generation was cancelled — set one with /name <name>",
  "no-credentials": "The current model has no usable credentials — set one with /name <name>",
  provider: "The model could not produce a session name — set one with /name <name>",
  reasoning: "The model spent the whole answer on reasoning — set one with /name <name>",
  timeout: "Name generation timed out — set one with /name <name>",
  unusable: "The model returned no usable name — set one with /name <name>",
};

/**
 * Generate one session name in-process using Pi's ModelRegistry.
 *
 * Always settles: a deadline, an external abort, a provider error, and an
 * answer that survives no cleaning all resolve to a reported failure rather
 * than hanging the command. The deadline races the request instead of only
 * signalling it, because a provider that ignores its abort signal would
 * otherwise hold the command open forever.
 *
 * `sessionId` is forwarded on the request. Some gateways route on a
 * per-conversation header that the provider wrapper derives from it, and a
 * nested one-shot call without it is rejected as an unknown conversation.
 */
export async function generateSessionName(
  registry: ModelRegistry,
  model: Model<Api>,
  digest: string,
  hint?: string,
  signal?: AbortSignal,
  timeoutMs: number = AUTONAME_TIMEOUT_MS,
  sessionId?: string,
): Promise<AutonameOutcome> {
  if (signal?.aborted) return { ok: false, reason: "aborted" };

  const controller = new AbortController();

  // Both endings settle the race themselves: a provider that ignores its abort
  // signal must not hold the command open, and a caller's abort must not wait for
  // the deadline to be reported. The first caller of `settle` wins.
  let settle: (reason: AutonameFailure) => void = () => {};
  const settled = new Promise<AutonameOutcome>((resolve) => {
    settle = (reason) => resolve({ ok: false, reason });
  });
  const onAbort = (): void => {
    controller.abort();
    settle("aborted");
  };
  signal?.addEventListener("abort", onAbort, { once: true });

  const timer = setTimeout(() => {
    controller.abort();
    settle("timeout");
  }, timeoutMs);

  const work = (async (): Promise<AutonameOutcome> => {
    const auth = await registry.getApiKeyAndHeaders(model);
    if (!auth.ok) return { ok: false, reason: "no-credentials" };
    if (controller.signal.aborted) return { ok: false, reason: "aborted" };

    const message: UserMessage = {
      role: "user",
      content: [{ type: "text", text: buildPrompt(digest, hint) }],
      timestamp: Date.now(),
    };

    // The simple stream path is the one that translates a provider-neutral
    // `reasoning` level into the provider's own field. The raw completion path
    // cannot express it, so reasoning then runs at the provider default and can
    // consume the entire answer budget before any text arrives.
    //
    // Every adapter reads `"off"` as no reasoning and compares the clamped level
    // against it, but `SimpleStreamOptions` leaves `"off"` out of its declared
    // levels. The request therefore states it through one documented cast rather
    // than asking for the smallest thinking level instead.
    const maxTokens =
      model.maxTokens > 0 ? Math.min(AUTONAME_MAX_TOKENS, model.maxTokens) : AUTONAME_MAX_TOKENS;
    const requestOptions = {
      apiKey: auth.apiKey,
      headers: auth.headers,
      signal: controller.signal,
      ...(sessionId ? { sessionId } : {}),
      reasoning: "off",
      maxTokens,
      temperature: 0,
      cacheRetention: "none",
    } as unknown as ModelsSimpleStreamOptions;
    const response = await registry
      .streamSimple(
        model,
        {
          systemPrompt: "You write short, recognizable session display names.",
          messages: [message],
        },
        requestOptions,
      )
      .result();

    if (controller.signal.aborted) return { ok: false, reason: "aborted" };

    // A provider reports a rejected request as a message carrying
    // `stopReason: "error"`, not as a thrown error. Treating that as an answer
    // would blame the credentials for a routing or quota failure.
    if (response.stopReason === "error" || response.errorMessage) {
      return {
        ok: false,
        reason: "provider",
        detail: response.errorMessage ?? `stopReason: ${String(response.stopReason)}`,
      };
    }

    const name = cleanSessionName(textFromResponse(response));
    if (name) return { ok: true, name };
    // Reasoning that filled the budget is a different fault from an answer that
    // cleaned away to nothing, so each one names its own cause.
    return hasThinking(response) ? { ok: false, reason: "reasoning" } : { ok: false, reason: "unusable" };
  })().catch((error: unknown): AutonameOutcome => ({
    // A transport error must not reject: the race may already be lost to the
    // deadline, and a late rejection would then surface as an unhandled
    // rejection rather than as a reported failure.
    ok: false,
    reason: "provider",
    detail: error instanceof Error ? error.message : String(error),
  }));

  try {
    // The race, not just the abort signal, is what guarantees settlement.
    return await Promise.race([work, settled]);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
}

export default function (pi: ExtensionAPI) {
  pi.registerCommand("autoname", {
    description: "Name this session from the conversation using the current model",
    handler: async (args, ctx) => {
      const model = ctx.model;
      if (!model) {
        notifyPi(ctx.ui, "No current model to generate a session name with", "error");
        return;
      }

      const digest = buildDigest(ctx.sessionManager.getBranch(), ctx.cwd);
      const hint = args.trim() || undefined;
      const outcome = await generateSessionName(
        ctx.modelRegistry,
        model,
        digest,
        hint,
        ctx.signal,
        AUTONAME_TIMEOUT_MS,
        ctx.sessionManager.getSessionId(),
      );

      if (!outcome.ok) {
        notifyPi(ctx.ui, FAILURE_MESSAGES[outcome.reason], "error");
        return;
      }

      pi.setSessionName(outcome.name);
      notifyPi(ctx.ui, `Session name set to ${outcome.name}`, "info");
    },
  });
}