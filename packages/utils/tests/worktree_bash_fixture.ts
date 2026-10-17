// Offline provider fixture for the Docker worktree-creation acceptance. It is a
// test double for the model, not a user extension: it issues exactly one bash
// tool call, read from PI_WORKTREE_FIXTURE_COMMAND, so the real host tool runs
// the command the installed redirect produced.
import { createRequire } from "node:module";
import { existsSync, realpathSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default async function (pi: ExtensionAPI): Promise<void> {
  // Use the host's faux provider: its transcript format tracks the host SDK.
  const require = createRequire(realpathSync(process.argv[1]));
  const modulePath = require.resolve.paths("@earendil-works/pi-ai")!
    .map((base) => join(base, "@earendil-works/pi-ai/dist/providers/faux.js"))
    .find(existsSync);
  if (!modulePath) throw new Error("Host faux provider unavailable");
  const { fauxAssistantMessage, fauxProvider, fauxToolCall } = await import(pathToFileURL(modulePath).href);
  const command = process.env.PI_WORKTREE_FIXTURE_COMMAND ?? "";
  if (!command) throw new Error("PI_WORKTREE_FIXTURE_COMMAND is required");
  const enteredCommand = process.env.PI_WORKTREE_FIXTURE_ENTERED_COMMAND ?? "pwd > pi-worktree-cwd.txt";
  // A sibling tool in the same message proves the barrier on the real host.
  const siblingWrite = process.env.PI_WORKTREE_FIXTURE_SIBLING_WRITE ?? "";
  const provider = fauxProvider({ provider: "worktree-bash", models: [{ id: "test" }] });
  pi.registerProvider(provider.provider);
  pi.on("session_start", (_event, ctx) => {
    // A replacement session runs inside the created worktree, so its own cwd is
    // the proof that Pi moved: it writes that cwd from inside the worktree.
    if (ctx.cwd.replace(/\\/g, "/").includes("/.pi/worktrees/")) {
      provider.setResponses([
        fauxAssistantMessage([fauxToolCall("bash", { command: enteredCommand })]),
        fauxAssistantMessage("WORKTREE_ENTERED_DONE"),
      ]);
      return;
    }
    provider.setResponses([
      fauxAssistantMessage([
        fauxToolCall("bash", { command }),
        ...(siblingWrite ? [fauxToolCall("write", { path: siblingWrite, content: "wrong checkout" })] : []),
      ]),
      fauxAssistantMessage("WORKTREE_BASH_DONE"),
    ]);
  });
}
