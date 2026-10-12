/**
 * pi-utils-fradser — native pi /effort command.
 *
 * Set the session thinking (reasoning effort) level without opening /model:
 *
 *   /effort             open a menu of the levels the current model supports
 *   /effort max         set the thinking level directly
 *
 * Accepted inline values are the canonical pi levels (off, minimal, low,
 * medium, high, xhigh, max) plus short aliases (min, med, xh, 0/none).
 * Unknown values are rejected with a hint instead of silently ignored.
 * pi.setThinkingLevel clamps to the model's capabilities, so a value a model
 * does not support degrades gracefully to the closest available level.
 */

import type { AutocompleteItem } from "@earendil-works/pi-tui";
import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { notifyPi } from "@fradser/pi-kit";

type ThinkingLevel = "off" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max";

const LEVELS: ThinkingLevel[] = ["off", "minimal", "low", "medium", "high", "xhigh", "max"];

const ALIASES: Record<string, ThinkingLevel> = {
  off: "off",
  none: "off",
  "0": "off",
  min: "minimal",
  minimal: "minimal",
  low: "low",
  med: "medium",
  medium: "medium",
  high: "high",
  xh: "xhigh",
  xhigh: "xhigh",
  max: "max",
};

/**
 * The levels the current model supports, mirroring pi's own
 * `getSupportedThinkingLevels` rule for any other pi version:
 * a model without reasoning only gets `off`; a `null` thinkingLevelMap entry
 * hides a level; `xhigh`/`max` are opt-in and additionally require an explicit
 * non-null map entry; other absent entries default to supported.
 *
 * `tests/test_effort_extension.py` pins this against the function pi exports,
 * so the copy cannot drift from the host it mirrors.
 */
function supportedLevels(ctx: ExtensionCommandContext): ThinkingLevel[] {
  const model = ctx.model;
  return model ? supportedThinkingLevelsFor(model) : LEVELS;
}

/**
 * The one implementation of the mirror rule, exported for the parity test that
 * pins it against the function pi itself exports.
 */
export function supportedThinkingLevelsFor(model: {
  reasoning?: boolean;
  thinkingLevelMap?: Record<string, unknown>;
}): ThinkingLevel[] {
  if (!model.reasoning) return ["off"];
  return LEVELS.filter((level) => {
    const mapped = model.thinkingLevelMap?.[level];
    if (mapped === null) return false;
    if (level === "xhigh" || level === "max") return mapped !== undefined;
    return true;
  });
}

/**
 * The level pi actually applied.
 *
 * `setThinkingLevel` clamps the request to the model's capabilities and returns
 * nothing, and the command context's `thinkingLevel` is a snapshot, so the
 * confirmation reads the live level back instead of repeating the request.
 */
function appliedLevel(pi: Pick<ExtensionAPI, "getThinkingLevel">): ThinkingLevel {
  return pi.getThinkingLevel();
}

export default function (pi: ExtensionAPI) {
  pi.registerCommand("effort", {
    description: "Set the thinking level: menu, or /effort <level> (off|minimal|low|medium|high|xhigh|max)",
    // Completions are model-independent: Pi offers argument completions without
    // a command context, so the menu is where model support is applied.
    getArgumentCompletions: (prefix: string): AutocompleteItem[] | null => {
      const tokens = Object.keys(ALIASES).filter((alias) => alias.startsWith(prefix.toLowerCase()));
      return tokens.map((alias) => ({ value: alias, label: alias }));
    },
    handler: async (args, ctx) => {
      const current = ctx.thinkingLevel ?? pi.getThinkingLevel();
      const raw = args.trim();

      if (raw) {
        const level = ALIASES[raw.toLowerCase()];
        if (!level) {
          notifyPi(
            ctx.ui,
            `Unknown thinking level "${raw}" — use one of: ${LEVELS.join(", ")} (or min/med/xh/0)`,
            "error",
          );
          return;
        }
        pi.setThinkingLevel(level);
        notifyPi(ctx.ui, `Thinking level set to ${appliedLevel(pi)}`, "info");
        return;
      }

      if (!ctx.hasUI) {
        notifyPi(ctx.ui, `Thinking level: ${current} — pass a level, e.g. /effort max`, "info");
        return;
      }

      const available = supportedLevels(ctx);
      const options = available.map((level) =>
        level === current ? `${level} (current)` : level,
      );

      const choice = await ctx.ui.select(
        `Thinking level (current: ${current})\n\nSet level:`,
        options,
      );
      if (!choice) return; // cancelled

      const selected = (choice.replace(" (current)", "") as ThinkingLevel);
      pi.setThinkingLevel(selected);
      notifyPi(ctx.ui, `Thinking level set to ${appliedLevel(pi)}`, "info");
    },
  });
}
