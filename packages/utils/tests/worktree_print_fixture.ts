// Offline provider for exercising the installed pi --print host, not a user extension.
import { createRequire } from "node:module";
import { existsSync, realpathSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import registerWorktreeSession from "../extensions/worktree-session.ts";
import registerWorktreeCompletion from "../extensions/worktree-completion.ts";

export default async function (pi: ExtensionAPI): Promise<void> {
  // Use the host's faux provider: its transcript format tracks the host SDK.
  const require = createRequire(realpathSync(process.argv[1]));
  const modulePath = require.resolve.paths("@earendil-works/pi-ai")!
    .map((base) => join(base, "@earendil-works/pi-ai/dist/providers/faux.js"))
    .find(existsSync);
  if (!modulePath) throw new Error("Host faux provider unavailable");
  const { fauxAssistantMessage, fauxProvider, fauxToolCall } = await import(pathToFileURL(modulePath).href);
  registerWorktreeSession(pi);
  registerWorktreeCompletion(pi);
  const provider = fauxProvider({ provider: "worktree-live", models: [{ id: "test" }] });
  pi.registerProvider(provider.provider);
  pi.on("session_start", (_event, ctx) => {
    provider.setResponses(ctx.cwd.endsWith("/worktrees/live") ? [
      fauxAssistantMessage([
        fauxToolCall("edit", { path: "tracked.txt", edits: [{ oldText: "original", newText: "worktree" }] }),
        fauxToolCall("write", { path: "new.txt", content: "worktree only" }),
        fauxToolCall("bash", { command: "pwd > actual-cwd.txt" }),
      ]),
      fauxAssistantMessage("WORKTREE_PRINT_OK"),
    ] : [
      fauxAssistantMessage([
        fauxToolCall("write", { path: "leaked.txt", content: "wrong checkout" }),
        fauxToolCall("enter_worktree", { name: "live" }),
      ]),
      fauxAssistantMessage("ERROR: continued in parent session"),
    ]);
  });
}
