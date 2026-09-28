/**
 * `@fradser/pi-tasks` as a Pi extension.
 *
 * A separate file from `index.ts` on purpose. `index.ts` is this package's
 * library barrel and re-exports the store; Pi's extension loader requires a
 * `default` export function and a barrel has none, so pointing a manifest at
 * `index.ts` would fail to load. Anything that bundles this package must
 * reference this file, never the barrel.
 *
 * It registers exactly one tool and owns nothing else. Board changes are
 * announced through `pi.events` so a coordinator can notice and wake residents
 * without this package knowing what a resident is.
 */

import { registerTaskTool } from "./src/tool.ts";

export default function piTasks(pi: Parameters<typeof registerTaskTool>[0]): void {
  registerTaskTool(pi);
  pi.on("session_start", async () => {
    pi.events.emit("pi-tasks:ready", {});
  });
}
