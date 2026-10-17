import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import registerAutoname from "./extensions/autoname.ts";
import registerContinue from "./extensions/continue.ts";
import registerEffort from "./extensions/effort.ts";
import registerInit from "./extensions/init.ts";
import registerNpmPublishGuard from "./extensions/npm-publish-guard.ts";
import registerLiveSessions from "./extensions/live-sessions.ts";
import registerSessions from "./extensions/sessions.ts";
import registerWorktree from "./extensions/worktree.ts";
import registerWorktreeCompletion from "./extensions/worktree-completion.ts";
import registerWorktreeSession from "./extensions/worktree-session.ts";

export default function utilsExtension(pi: ExtensionAPI): void {
	registerAutoname(pi);
	registerContinue(pi);
	registerEffort(pi);
	registerInit(pi);
	registerLiveSessions(pi);
	registerSessions(pi);
	// The session switcher registers first: it owns the transition barrier the
	// redirect reserves when a bash command creates a worktree.
	const worktreeEntry = registerWorktreeSession(pi);
	registerWorktree(pi, worktreeEntry);
	registerWorktreeCompletion(pi);
	registerNpmPublishGuard(pi);
}
