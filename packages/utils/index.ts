import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import registerContinue from "./extensions/continue.ts";
import registerEffort from "./extensions/effort.ts";
import registerInit from "./extensions/init.ts";
import registerSessions from "./extensions/sessions.ts";
import registerWorktree from "./extensions/worktree.ts";
import registerWorktreeCompletion from "./extensions/worktree-completion.ts";
import registerWorktreeSession from "./extensions/worktree-session.ts";

export default function utilsExtension(pi: ExtensionAPI): void {
	registerContinue(pi);
	registerEffort(pi);
	registerInit(pi);
	registerSessions(pi);
	registerWorktree(pi);
	registerWorktreeCompletion(pi);
	registerWorktreeSession(pi);
}
