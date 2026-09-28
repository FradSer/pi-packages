/**
 * The Pi extension body for `@fradser/pi-tasks`.
 *
 * Lives in `src/` so `index.ts` can re-export it as the package's default export,
 * which is what lets one file serve as both the library entry and the extension
 * entry. A separate top-level extension file would split that, and the root
 * `index.ts` is what every other runtime package here loads.
 *
 * It registers exactly one tool and owns nothing else. Board changes are
 * announced through `pi.events` so a coordinator can notice and wake residents
 * without this package knowing what a resident is; with nobody subscribed the
 * emit is a no-op, which is the correct degradation.
 */

import { registerTaskTool } from "./tool.ts";

export default function piTasks(pi: Parameters<typeof registerTaskTool>[0]): void {
  registerTaskTool(pi);
  pi.on("session_start", async () => {
    pi.events.emit("pi-tasks:ready", {});
  });
}
