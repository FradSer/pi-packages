import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { isToolCallEventType } from "@earendil-works/pi-coding-agent";

/**
 * Rewrites a single `git worktree add` command to ensure the target path
 * is located inside `.pi/worktrees/<name>`.
 */
export function rewriteWorktreeAddCommand(command: string): string {
  if (!command.includes("git") || !command.includes("worktree")) {
    return command;
  }

  // Regex matching `git worktree add` invocations
  const worktreeAddRegex = /\bgit\s+worktree\s+add\b([^;\n&|]*)/g;

  return command.replace(worktreeAddRegex, (fullMatch, argsStr: string) => {
    // Split arguments while preserving quoted sections
    const args = argsStr.trim().split(/\s+/).filter(Boolean);
    if (args.length === 0) {
      return fullMatch;
    }

    // Collect flags and positional arguments
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

    // If already inside .pi/worktrees (or relative .pi/worktrees/...), no rewrite needed
    if (
      originalPath.startsWith(".pi/worktrees/") ||
      originalPath.includes("/.pi/worktrees/")
    ) {
      return fullMatch;
    }

    // Extract directory name (basename)
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
