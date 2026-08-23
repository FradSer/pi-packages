/**
 * Native `/continue` command and continuation keyword interception.
 *
 * Continuation is always evaluated against the active session branch:
 * - incomplete or failed turns retry silently from the current leaf;
 * - completed turns receive a visible continuation request;
 * - unseen entries written by another process are loaded before continuing;
 * - a leaf selected through session-tree navigation remains authoritative, even when
 *   the append-only session file still contains a failed abandoned branch.
 */

import fs from "node:fs";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "@earendil-works/pi-coding-agent";

export interface ContinuationTarget {
  promptText: string;
  isDirectContinuation: boolean;
}

interface SessionView {
  getEntry(id: string): unknown;
}

interface ContinuationHost {
  sendMessage(
    message: { customType: string; content: string; display: boolean },
    options?: { triggerTurn?: boolean },
  ): void | Promise<void>;
  sendUserMessage(
    content: string,
    options?: { deliverAs?: "steer" | "followUp" },
  ): void | Promise<void>;
}

const CONTINUE_SET = new Set(["continue", "继续", "繼續"]);
const CONTINUATION_MESSAGE_TYPE = "continue-extension";
const COMPLETED_CONTINUATION_PROMPT =
  "Please continue execution based on the suggestions, incomplete steps, or next actions from your previous response.";
const DIRECT_CONTINUATION_PROMPT = "Resume execution from the current context without repeating completed work.";

/** Check whether input is exactly a supported continuation keyword. */
export function isContinuationKeyword(rawInput: string): boolean {
  if (!rawInput) return false;

  const normalized = rawInput
    .trim()
    .toLowerCase()
    .replace(/^[\p{P}\p{S}\s]+|[\p{P}\p{S}\s]+$/gu, "");
  return CONTINUE_SET.has(normalized);
}

/**
 * Resolve continuation from the active branch only. This is intentionally based on
 * `getBranch()` rather than all persisted entries, so tree navigation determines the
 * task that is resumed.
 */
export function resolveContinuation(ctx: ExtensionContext, customArgs?: string): ContinuationTarget | null {
  const promptText = customArgs?.trim();
  if (promptText) {
    return { promptText, isDirectContinuation: false };
  }

  const lastMessage = findLastMessage(ctx);
  if (!lastMessage) return null;

  if (lastMessage.role === "assistant" && lastMessage.stopReason === "stop") {
    return {
      promptText: COMPLETED_CONTINUATION_PROMPT,
      isDirectContinuation: false,
    };
  }

  return {
    promptText: DIRECT_CONTINUATION_PROMPT,
    isDirectContinuation: true,
  };
}

function findLastMessage(ctx: ExtensionContext): { role: string; stopReason?: string } | null {
  const branch = ctx.sessionManager.getBranch();
  for (let index = branch.length - 1; index >= 0; index -= 1) {
    const entry = branch[index];
    if (entry.type === "message") return entry.message;
  }
  return null;
}

/**
 * Read the last valid persisted entry id. Invalid trailing lines are ignored because
 * a session may be observed while another process is appending to it.
 */
export function readDiskTipEntryId(sessionFile: string | undefined): string | null {
  if (!sessionFile) return null;

  let content: string;
  try {
    content = fs.readFileSync(sessionFile, "utf8");
  } catch {
    return null;
  }

  const lines = content.split("\n");
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index].trim();
    if (!line) continue;

    try {
      const entry = JSON.parse(line) as { id?: unknown; type?: unknown };
      if (typeof entry.id === "string" && entry.id && entry.type !== "session") {
        return entry.id;
      }
    } catch {
      // Ignore an incomplete line and continue looking for the last complete entry.
    }
  }

  return null;
}

/**
 * Decide whether persisted history must be loaded before appending a continuation.
 *
 * A known disk tip means the active session already has the complete append-only tree.
 * If its leaf differs, that is a user-selected tree node and the selected leaf is
 * authoritative. Only an unknown disk tip indicates that another process appended
 * history the active session has never loaded.
 */
export function needsSessionReload(sessionView: SessionView, diskTipEntryId: string | null): boolean {
  if (!diskTipEntryId) return false;
  return sessionView.getEntry(diskTipEntryId) === undefined;
}

function isDirectContinuationMarker(message: { role: string; customType?: string }): boolean {
  return message.role === "custom" && message.customType === CONTINUATION_MESSAGE_TYPE;
}

function isIncompleteAssistant(message: { role: string; stopReason?: string }): boolean {
  return message.role === "assistant" && message.stopReason !== "stop";
}

/** Remove only the marker and contiguous incomplete assistant attempts before it. */
export function stripDirectContinuationMessages<
  T extends { role: string; customType?: string; stopReason?: string },
>(messages: T[]): T[] {
  const filtered: T[] = [];
  for (const message of messages) {
    if (!isDirectContinuationMarker(message)) {
      filtered.push(message);
      continue;
    }

    while (filtered.length > 0 && isIncompleteAssistant(filtered[filtered.length - 1])) {
      filtered.pop();
    }
  }
  return filtered;
}

function sendDirectContinuation(host: ContinuationHost): void {
  host.sendMessage(
    {
      customType: CONTINUATION_MESSAGE_TYPE,
      content: "",
      display: false,
    },
    { triggerTurn: true },
  );
}

async function performContinuation(
  args: string | undefined,
  ctx: ExtensionContext,
  host: ContinuationHost,
): Promise<void> {
  const target = resolveContinuation(ctx, args);
  if (!target) {
    ctx.ui.notify("Cannot continue because there is no previous model request.", "error");
    return;
  }

  if (target.isDirectContinuation) {
    sendDirectContinuation(host);
    return;
  }

  await host.sendUserMessage(target.promptText);
}

export async function runContinuation(args: string, ctx: ExtensionCommandContext, pi: ExtensionAPI): Promise<void> {
  await ctx.waitForIdle();

  const sessionFile = ctx.sessionManager.getSessionFile();
  const diskTipEntryId = readDiskTipEntryId(sessionFile);

  // Preserve a known selected leaf. Reload only when the disk tip is unknown to the
  // active session, meaning another process appended entries we have never loaded.
  if (sessionFile && needsSessionReload(ctx.sessionManager, diskTipEntryId)) {
    await ctx.switchSession(sessionFile, {
      withSession: async (replacedCtx) => {
        await performContinuation(args, replacedCtx, replacedCtx);
      },
    });
    return;
  }

  await performContinuation(args, ctx, pi);
}

export default function registerContinue(pi: ExtensionAPI): void {
  pi.on("context", async (event) => ({
    messages: stripDirectContinuationMessages(event.messages),
  }));

  pi.on("input", async (event, ctx) => {
    if (!isContinuationKeyword(event.text)) return { action: "continue" };

    if (ctx.isIdle()) {
      type SendOptions = Parameters<ExtensionAPI["sendUserMessage"]>[1];
      const expandOptions = { expandPromptTemplates: true } as SendOptions & {
        expandPromptTemplates?: boolean;
      };
      await pi.sendUserMessage("/continue", expandOptions);
      return { action: "handled" };
    }

    sendDirectContinuation(pi);
    return { action: "handled" };
  });

  pi.registerCommand("continue", {
    description: "Resume incomplete work directly; continue completed work with a visible request",
    handler: async (args: string, ctx: ExtensionCommandContext) => {
      await runContinuation(args, ctx, pi);
    },
  });
}
