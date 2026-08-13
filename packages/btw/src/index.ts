/**
 * @fradser/btw — side questions for Pi.
 *
 * `/btw <question>` answers a quick side question in a full-width popup at
 * the bottom of the terminal (above the input box), without interrupting the
 * current task and without ever entering the session history.
 *
 * Improvements over Claude Code's /btw:
 *   1. Tool-capable: the side question runs in a child Pi process that CAN
 *      call read-only tools (read, grep, find, ls) to verify facts in the
 *      actual codebase — not just infer from conversation context.
 *   2. Strictly read-only: only read/grep/find/ls are allowed; bash, edit,
 *      and write are always excluded. A side question can never modify
 *      anything.
 *
 * Interaction: escape closes (or cancels while loading); ↑/↓ scroll,
 * pgup/pgdn page, home/end jump. Mouse-wheel scrolling is not available —
 * in pi's fullscreen TUI the wheel belongs to the chat viewport.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { buildConversationContext } from "./context";
import { createBtwOverlay, type BtwOverlayStyle } from "./overlay";
import { runBtw } from "./spawner";

const DEFAULT_MODEL_ENV = "BTW_MODEL";

function makeStyle(theme: {
  fg(color: string, text: string): string;
}): BtwOverlayStyle {
  return {
    accent: (s) => theme.fg("accent", s),
    muted: (s) => theme.fg("muted", s),
    dim: (s) => theme.fg("dim", s),
    border: (s) => theme.fg("border", s),
    success: (s) => theme.fg("success", s),
    error: (s) => theme.fg("error", s),
    fg: (color, s) => theme.fg(color, s),
  };
}

export default function (pi: ExtensionAPI) {
  pi.registerCommand("btw", {
    description:
      "Ask a side question in a read-only popup — answers without interrupting the task and never enters the session history",
    handler: async (args, ctx) => {
      const question = args.trim();
      if (!question) {
        ctx.ui.notify("btw: empty question — usage: /btw <question>", "error");
        return;
      }
      if (ctx.mode !== "tui") {
        ctx.ui.notify("btw requires interactive (TUI) mode", "error");
        return;
      }

      // Side question runs with the same model as the session, overridable via BTW_MODEL.
      let model: string | undefined;
      if (ctx.model) model = `${ctx.model.provider}/${ctx.model.id}`;
      const envModel = process.env[DEFAULT_MODEL_ENV];
      if (envModel) model = envModel;

      const context = buildConversationContext(ctx.sessionManager);

      await ctx.ui.custom<undefined>(
        (tui, theme, _kb, done) => {
          const style = makeStyle(theme);

          const overlay = createBtwOverlay(tui, style, {
            question,
            modelLabel: model,
            onCancel: () => done(undefined),
            onSpawn: (signal) => {
              const startedAt = Date.now();
              runBtw({ question, context, cwd: ctx.cwd, model, signal })
                .then((result) => {
                  if (result.timedOut) {
                    overlay.showError("The side question timed out. Try again or make the question more specific.");
                  } else if (result.exitCode !== 0 && !result.text) {
                    overlay.showError(
                      result.stderr.trim()
                        ? `The side question failed:\n${result.stderr.trim()}`
                        : `The side question failed with exit code ${result.exitCode}.`,
                    );
                  } else {
                    overlay.showAnswer(result.text || "(no answer)", {
                      usage: result.usage,
                      elapsedMs: Date.now() - startedAt,
                    });
                  }
                })
                .catch((error: unknown) => {
                  overlay.showError(error instanceof Error ? error.message : String(error));
                });
            },
          });

          return overlay;
        },
        {
          overlay: true,
          overlayOptions: {
            anchor: "bottom-center",
            width: "100%",
            maxHeight: "80%",
            margin: { bottom: 4 },
          },
        },
      );
    },
  });
}
