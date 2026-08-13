/**
 * @fradser/utils — native pi /effort command.
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
 * getSupportedThinkingLevels: a reasoning:false model only gets off; a null
 * thinkingLevelMap entry hides a level; xhigh/max are opt-in and additionally
 * require an explicit non-null map entry; absent entries for the other levels
 * default to supported.
 */
function supportedLevels(ctx: ExtensionCommandContext): ThinkingLevel[] {
  const model = ctx.model;
  if (!model) return LEVELS;
  if (model.reasoning === false) return ["off"];
  if (model.thinkingLevelMap) {
    return LEVELS.filter((level) => {
      const mapped = model.thinkingLevelMap?.[level];
      if (mapped === null) return false;
      if (level === "xhigh" || level === "max") return mapped !== undefined;
      return true;
    });
  }
  return LEVELS;
}

export default function (pi: ExtensionAPI) {
  pi.registerCommand("effort", {
    description: "Set the thinking level: menu, or /effort <level> (off|minimal|low|medium|high|xhigh|max)",
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
          ctx.ui.notify(
            `Unknown thinking level "${raw}" — use one of: ${LEVELS.join(", ")} (or min/med/xh/0)`,
            "error",
          );
          return;
        }
        pi.setThinkingLevel(level);
        ctx.ui.notify(`Thinking level set to ${level}`, "info");
        return;
      }

      if (!ctx.hasUI) {
        ctx.ui.notify(`Thinking level: ${current} — pass a level, e.g. /effort max`, "info");
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
      ctx.ui.notify(`Thinking level set to ${selected}`, "info");
    },
  });
}
