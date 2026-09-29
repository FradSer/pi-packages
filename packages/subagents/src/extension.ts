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
 *
 * Deliberately does not import the TUI. Terminal geometry would have to be bound
 * somewhere, and this file is loaded by every headless test as well as by Pi, so
 * importing pi-tui here executes theme code that throws outside a rendered
 * session. The row renderer is therefore optional: supplied by whichever caller is
 * painting, and absent otherwise, in which case Pi's own default is used.
 */

import { registerAgentTool } from "./agent-tool.ts";

export default function piSubagents(pi: Parameters<typeof registerAgentTool>[0]): void {
  registerAgentTool(pi);
  pi.on("session_start", async () => {
    pi.events.emit("pi-subagents:ready", {});
  });
}
