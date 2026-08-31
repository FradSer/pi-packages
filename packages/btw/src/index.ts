/**
 * pi-btw-fradser — side questions for Pi.
 *
 * `/btw <question>` answers a quick side question in a full-width popup that
 * directly covers the main session input area, without interrupting the
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
import { createPiThemeStyle, notifyPi } from "@fradser/pi-kit";
import { buildConversationContext } from "./context";
import { createBtwOverlay } from "./overlay";
import { runBtw } from "./spawner";

const DEFAULT_MODEL_ENV = "BTW_MODEL";

export default function (pi: ExtensionAPI) {
  pi.registerCommand("btw", {
    description:
      "Ask a side question in a read-only popup — answers without interrupting the task and never enters the session history",
    handler: async (args, ctx) => {
      const question = args.trim();
      if (!question) {
        notifyPi(ctx.ui, "btw: empty question — usage: /btw <question>", "error");
        return;
      }
      if (ctx.mode !== "tui") {
        notifyPi(ctx.ui, "btw requires interactive (TUI) mode", "error");
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
          const style = createPiThemeStyle(theme);

          const overlay = createBtwOverlay(tui, style, {
            question,
            modelLabel: model,
            onCancel: () => done(undefined),
            onAsk: (q, history, signal) => {
              return runBtw({
                question: q,
                context,
                cwd: ctx.cwd,
                model,
                signal,
                history,
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
            margin: { bottom: 0 },
          },
        },
      );
    },
  });
}
