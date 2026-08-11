import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { isToolCallEventType } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event, _ctx) => {
    if (isToolCallEventType("bash", event)) {
      const cmd = event.input.command || "";
      if (!cmd.includes("git")) return;

      // Escape hatch: manual fallback marker
      if (/(^|[;&|\s])GIT_SKILL_FALLBACK=1([;&|\s]|$)/.test(cmd)) {
        return;
      }

      // Command-position anchors
      const pos = "(?:^|[;&|\\n])\\s*(?:[A-Za-z_][A-Za-z_0-9]*=[^\\s]*\\s+)*";
      const end = "(?:[;&|\\s]|$)";

      const reCommit = new RegExp(`${pos}git\\s+commit${end}`);
      const reAdd = new RegExp(`${pos}git\\s+add${end}`);
      const reAgent = new RegExp(`${pos}git-agent\\s+commit${end}`);

      if (reCommit.test(cmd)) {
        return {
          block: true,
          reason:
            "Use the /commit or /commit-and-push skill (or git-agent CLI) instead of raw git add/git commit. It creates atomic AI commits with validation.",
        };
      }

      if (reAdd.test(cmd) && !reAgent.test(cmd)) {
        return {
          block: true,
          reason:
            "Use the /commit skill instead of raw git add. For folder-scoped staging, chain it with git-agent: git add <path> && git-agent commit --no-stage ...",
        };
      }
    }
  });
}
