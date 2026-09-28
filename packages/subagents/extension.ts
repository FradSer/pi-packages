/**
 * `@fradser/pi-subagents` as a Pi extension.
 *
 * Separate from `index.ts` because that file is the library barrel and Pi's
 * extension loader requires a `default` export function, which a barrel does not
 * have. Anything bundling this package must reference this file, never the barrel.
 *
 * It registers exactly one tool and owns no other surface. A team runtime
 * publishes a richer spawn path through `setAgentHost`; without one, `agent`
 * falls back to the raw spawner, which is what makes this package usable alone.
 */

import { registerAgentTool } from "./src/agent-tool.ts";

export default function piSubagents(pi: Parameters<typeof registerAgentTool>[0]): void {
  registerAgentTool(pi);
  pi.on("session_start", async () => {
    pi.events.emit("pi-subagents:ready", {});
  });
}
