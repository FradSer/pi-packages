/**
 * The Pi extension body for `@fradser/pi-subagents`.
 *
 * Lives in `src/` so `index.ts` can re-export it as the package's default export,
 * which is what lets one file serve as both the library entry and the extension
 * entry. A separate top-level extension file would split that, and the root
 * `index.ts` is what every other runtime package here loads.
 *
 * It registers exactly one tool and owns no other surface. A team runtime
 * publishes a richer spawn path through `setAgentHost`; without one, `agent`
 * falls back to the raw spawner, which is what makes this package usable alone.
 */

import { registerAgentTool } from "./agent-tool.ts";

export default function piSubagents(pi: Parameters<typeof registerAgentTool>[0]): void {
  registerAgentTool(pi);
  pi.on("session_start", async () => {
    pi.events.emit("pi-subagents:ready", {});
  });
}
