/**
 * Real child spawn, over the configured install, and a real model turn.
 *
 * This is the manual, credentialed counterpart to the offline E2E. It is not part
 * of `pnpm test`: it needs a live provider, and the child costs a real model turn.
 *
 * Run it when the seam that the offline suites cannot reach needs checking by
 * hand — a child's output coming back to the leader. The offline E2E proves the
 * team path is selected; only this proves the result arrives.
 *
 *   PI_LIVE_CHILD_MODEL="provider/model" node .../live-child.ts  (via pi --extension)
 */
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { installScriptedProvider } from "../../../../tests/e2e/support/scripted.ts";

const REPORTS = "live-child-report";

export default function liveChild(pi: ExtensionAPI): void {
  // A resident is a role with a process attached, so the team spawn needs one
  // before it will start anything. Written here, at load, so it exists before
  // session_start and before the first turn — which is how a user adds a role.
  // Project scope, so the role does not land in the developer's own agent
  // directory. `.pi/` is already ignored, and the team spawn reports this path
  // when it cannot find a role.
  const dir = path.join(process.cwd(), ".pi", "agents");
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "realchild.md"), [
    "---",
    "description: Answers one short question and stops",
    "tools: []",
    "---",
    "Reply with exactly the text you are asked for, and nothing else.",
    "",
  ].join("\n"), "utf-8");

  installScriptedProvider(pi, {
    provider: "live-child",
    probe: "live_child_probe",
    turns: [
      { tool: "agent", args: {
        action: "start",
        name: "realchild",
        prompt: "Reply with exactly LIVE_CHILD_OK and nothing else. Do not use tools.",
        model: process.env.PI_LIVE_CHILD_MODEL,
        tools: [],
      } },
      // Polls rather than asserting immediately: the report is delivered when the
      // child's turn settles, and the first read is usually too early.
      { tool: "live_child_probe", args: { probe: "wait" } },
      { tool: "agent", args: { action: "list" } },
      { tool: "agent", args: { action: "stop", session: "$prev.agents.0.session" } },
    ],
  });
  pi.on("message_end", (event) => {
    const message = event.message as { role?: string; customType?: string; content?: unknown; details?: unknown };
    if (message.role === "custom" && message.customType === "agent-teams-report") {
      (globalThis as Record<string, unknown>)[REPORTS] = message.details;
    }
  });
}
