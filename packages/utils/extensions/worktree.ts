/**
 * @fradser/utils — git worktree path redirect.
 *
 * Intercepts `git worktree add` bash tool calls and rewrites the target path
 * to live inside `.pi/worktrees/<name>` so linked worktrees stay inside the
 * repo instead of scattering sibling directories next to it. A path that is
 * already inside `.pi/worktrees/` is left untouched, and flags plus trailing
 * positional arguments (branch, start commit) are preserved.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { isToolCallEventType } from "@earendil-works/pi-coding-agent";

/**
 * Rewrites a single `git worktree add` command so its target path is
 * inside `.pi/worktrees/<name>`. Returns the input unchanged when the
 * command is not a `git worktree add` or the path is already redirected.
 */
export function rewriteWorktreeAddCommand(command: string): string {
  if (!command.includes("git") || !command.includes("worktree")) {
    return command;
  }

  const worktreeAddRegex = /\bgit\s+worktree\s+add\b([^;\n&|]*)/g;

  return command.replace(worktreeAddRegex, (fullMatch, argsStr: string) => {
    const args = argsStr.trim().split(/\s+/).filter(Boolean);
    if (args.length === 0) {
      return fullMatch;
    }

    const flags: string[] = [];
    const positional: string[] = [];

    let i = 0;
    while (i < args.length) {
      const arg = args[i];
      if (
        arg === "-b" ||
        arg === "-B" ||
        arg === "--reason" ||
        arg === "--lock"
      ) {
        flags.push(arg);
        if (i + 1 < args.length) {
          flags.push(args[i + 1]);
          i += 2;
          continue;
        }
      } else if (arg.startsWith("-")) {
        flags.push(arg);
      } else {
        positional.push(arg);
      }
      i++;
    }

    if (positional.length === 0) {
      return fullMatch;
    }

    const originalPath = positional[0];
    const restPositional = positional.slice(1);

    if (
      originalPath.startsWith(".pi/worktrees/") ||
      originalPath.includes("/.pi/worktrees/")
    ) {
      return fullMatch;
    }

    const basename = originalPath.split("/").filter(Boolean).pop() || "worktree";
    const targetPath = `.pi/worktrees/${basename}`;

    const newArgs = [...flags, targetPath, ...restPositional].join(" ");
    return `mkdir -p .pi/worktrees && git worktree add ${newArgs}`;
  });
}

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event, ctx) => {
    if (isToolCallEventType("bash", event)) {
      const cmd = event.input.command || "";
      if (cmd.includes("git") && cmd.includes("worktree") && cmd.includes("add")) {
        const rewritten = rewriteWorktreeAddCommand(cmd);
        if (rewritten !== cmd) {
          event.input.command = rewritten;
          ctx.ui.notify(
            "worktree path redirected to .pi/worktrees/ — linked worktrees stay inside the repo",
            "info",
          );
        }
      }
    }
  });
}
