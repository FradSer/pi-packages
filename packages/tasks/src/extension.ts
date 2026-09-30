/**
 * The Pi extension body for `@fradser/pi-tasks`.
 *
 * Lives in `src/` so `index.ts` can re-export it as the package's default export,
 * which is what lets one file serve as both the library entry and the extension
 * entry. A separate top-level extension file would split that, and the root
 * `index.ts` is what every other runtime package here loads.
 *
 * It registers exactly one tool and owns nothing else. Board changes are announced
 * through `pi.events` so a coordinator can notice and wake residents without this
 * package knowing what a resident is; with nobody subscribed the emit is a no-op,
 * which is the correct degradation.
 *
 * Deliberately does not import the TUI. Terminal geometry reaches a row through
 * the same injection seam it does in @fradser/pi-subagents: this file is loaded
 * by every headless test as well as by Pi, so the library stays free of pi-tui
 * and the row renderer is supplied by whichever caller is painting. A caller
 * that supplies none gets Pi's own default rather than a row that cannot paint.
 */

import { registerTaskTool } from "./tool.ts";

export default function piTasks(pi: Parameters<typeof registerTaskTool>[0]): void {
  registerTaskTool(pi);
  pi.on("session_start", async () => {
    pi.events.emit("pi-tasks:ready", {});
  });
}
