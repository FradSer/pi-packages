/**
 * Live smoke over the *configured* install.
 *
 * Unlike the install-wiring probe this one calls the tools, so it proves the
 * tools are wired to a working runtime rather than merely registered. A tool that
 * appears in the surface but refuses everything is still broken.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { installScriptedProvider } from "../../../../tests/e2e/support/scripted.ts";

export default function liveSmoke(pi: ExtensionAPI): void {
  installScriptedProvider(pi, {
    provider: "live-smoke",
    probe: "live_smoke_probe",
    turns: [
      { tool: "task", args: { action: "create", subject: "Live smoke task", resources: ["firmware"] } },
      { tool: "task", args: { action: "list", claimable: true } },
      { tool: "task", args: { action: "update", id: "$prev.id", status: "in_progress" } },
      { tool: "task", args: { action: "complete", id: "$prev.id", outcome: "success", result: "smoke passed" } },
      // A removed verb must be refused by name, not silently ignored.
      { tool: "task", args: { action: "assign", id: "$prev.id" } },
      // The communication tool is live: it validates its recipient rather than
      // claiming success for an address that does not exist.
      { tool: "message", args: { to: "nobody-here", body: "status?", kind: "inform" } },
      { tool: "agent", args: { action: "start", name: "../escape" } },
    ],
  });
}
