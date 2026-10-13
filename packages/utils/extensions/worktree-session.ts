/**
 * pi-utils-fradser — Claude Code-style git worktree session switching.
 *
 * Pi binds its built-in tools to the session cwd, so entering a worktree
 * creates a replacement session with that cwd instead of mutating process.cwd.
 */

import fs from "node:fs";
import path from "node:path";
import {
	keyHint,
	type ExtensionAPI,
	type ExtensionCommandContext,
	type ExtensionContext,
	type Theme,
} from "@earendil-works/pi-coding-agent";
import { SessionManager } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import {
	bindLifecycleRenderers,
	contentDetailLines,
	eventToolLifecycle,
	notifyPi,
	safeDisplayText,
	setOwnedTools,
} from "@fradser/pi-kit";
import { Type } from "typebox";
import {
	canonicalize,
	currentWorktreeRoot,
	isManagedWorktreesIgnored,
	listWorktrees,
	managedWorktreesDir,
	MANAGED_WORKTREES_SHELL_PATH,
	repoRoot,
	runGit,
	type WorktreeRecord,
} from "./git/worktrees.ts";
import { invalidateWorktreeRoots } from "./worktree-completion.ts";

export type { WorktreeRecord };

export const WORKTREE_SESSION_ENTRY = "pi-utils-worktree-session";

interface WorktreeToolResult {
	content: Array<{ text?: string; type: string }>;
}

/** Geometry bound once: every worktree row shares hint and wrapping. */
const rows = bindLifecycleRenderers({
	fit: truncateToWidth,
	visibleWidth,
	wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
	expandHint: () => keyHint("app.tools.expand", "to expand"),
});

function renderWorktreeToolResult(
	result: WorktreeToolResult,
	options: { expanded?: boolean },
	theme: Pick<Theme, "bold" | "fg" | "bg">,
	context: { isError?: boolean },
	subject: string,
): { invalidate: () => void; render: (width: number) => string[] } {
	const separator = subject.indexOf(" ");
	const action = separator === -1 ? subject : subject.slice(0, separator);
	const target = separator === -1 ? "" : subject.slice(separator + 1);
	return rows.result(() => eventToolLifecycle("worktree", target, {
		label: action,
		details: contentDetailLines(result),
	}))(result, options, theme, context);
}

export interface WorktreeSessionState {
	baseCommit: string;
	branch?: string;
	created: boolean;
	parentSession: string;
	path: string;
	repoRoot: string;
}

export interface EnterWorktreeRequest {
	name?: string;
	path?: string;
}

export interface CreatedEnterTarget {
	baseCommit: string;
	created: true;
	name: string;
	path: string;
	repoRoot: string;
}

export interface ExistingEnterTarget {
	baseCommit: string;
	created: false;
	name?: string;
	path: string;
	record?: WorktreeRecord;
	repoRoot: string;
}

export type EnterTarget = CreatedEnterTarget | ExistingEnterTarget;

function safeName(name: string): string | null {
	const normalized = name
		.trim()
		.replace(/[\\/]+/g, "-")
		.replace(/[^A-Za-z0-9._-]+/g, "-")
		.replace(/^-+|-+$/g, "");
	return normalized && normalized !== "." && normalized !== ".." ? normalized : null;
}

function resolvePathFrom(cwd: string, value: string): string {
	return canonicalize(path.isAbsolute(value) ? value : path.resolve(cwd, value));
}

function findRegisteredWorktree(cwd: string, value: string): WorktreeRecord | null {
	const target = resolvePathFrom(cwd, value);
	return listWorktrees(cwd).find((entry) => entry.root === target) ?? null;
}

function currentHead(cwd: string): string | null {
	const result = runGit(cwd, ["rev-parse", "HEAD"]);
	return result.status === 0 && result.stdout.trim() ? result.stdout.trim() : null;
}

export function resolveEnterTarget(
	cwd: string,
	request: EnterWorktreeRequest,
): EnterTarget | { error: string } {
	if (request.name && request.path) return { error: "provide either name or path, not both" };
	const entries = listWorktrees(cwd);
	// A session sitting on a bare repository has no checkout to branch from.
	// A linked worktree of a bare store still does, so only the session's own
	// cwd decides this.
	const onBareRepository =
		!currentWorktreeRoot(cwd) &&
		entries.some((entry) => entry.bare && entry.root === canonicalize(cwd));
	if (onBareRepository) return { error: "EnterWorktree requires a non-bare git repository" };
	const root = repoRoot(cwd, entries);
	if (!root) return { error: "EnterWorktree requires a non-bare git repository" };

	if (request.path) {
		const record = findRegisteredWorktree(cwd, request.path);
		if (!record) return { error: `path is not a registered git worktree: ${request.path}` };
		const baseCommit = currentHead(cwd);
		if (!baseCommit) return { error: "the current worktree has no commit" };
		return { created: false, path: record.root, record, repoRoot: root, baseCommit };
	}

	const name = safeName(request.name ?? `pi-${Date.now().toString(36)}`);
	if (!name) return { error: "worktree name is empty after sanitization" };
	const managedDir = managedWorktreesDir(root);
	if (!managedDir) return { error: "EnterWorktree requires a non-bare git repository" };
	const target = path.join(managedDir, name);
	const targetRoot = canonicalize(target);
	const existing = entries.find((entry) => entry.root === targetRoot);
	if (existing) {
		const baseCommit = currentHead(cwd);
		if (!baseCommit) return { error: "the current worktree has no commit" };
		return { created: false, name, path: existing.root, record: existing, repoRoot: root, baseCommit };
	}
	if (fs.existsSync(target)) return { error: `path exists but is not a registered git worktree: ${target}` };

	const baseCommit = currentHead(cwd);
	if (!baseCommit) return { error: "EnterWorktree requires at least one commit" };
	return { created: true, name, path: target, repoRoot: root, baseCommit };
}

function createWorktree(
	target: CreatedEnterTarget,
): WorktreeSessionState | { error: string } {
	const branch = `pi/worktree/${target.name}`;
	fs.mkdirSync(path.dirname(target.path), { recursive: true });
	const result = runGit(target.repoRoot, ["worktree", "add", target.path, "-b", branch, target.baseCommit]);
	if (result.status !== 0) {
		return { error: result.stderr.trim() || result.stdout.trim() || "git worktree add failed" };
	}
	// This session just changed the repository's worktree list.
	invalidateWorktreeRoots();
	return {
		baseCommit: target.baseCommit,
		branch,
		created: true,
		parentSession: "",
		path: canonicalize(target.path),
		repoRoot: target.repoRoot,
	};
}

function isWorktreeSessionState(data: unknown): data is WorktreeSessionState {
	if (!data || typeof data !== "object") return false;
	const value = data as Partial<WorktreeSessionState>;
	return (
		typeof value.baseCommit === "string" &&
		typeof value.created === "boolean" &&
		typeof value.parentSession === "string" &&
		typeof value.path === "string" &&
		typeof value.repoRoot === "string"
	);
}

export function readWorktreeSessionState(ctx: Pick<ExtensionContext, "sessionManager">): WorktreeSessionState | null {
	const branch = ctx.sessionManager.getBranch();
	for (let index = branch.length - 1; index >= 0; index -= 1) {
		const entry = branch[index];
		if (entry?.type !== "custom" || entry.customType !== WORKTREE_SESSION_ENTRY) continue;
		return isWorktreeSessionState(entry.data) ? entry.data : null;
	}
	return null;
}

function worktreeHasChanges(state: WorktreeSessionState): boolean {
	const status = runGit(state.path, ["status", "--porcelain", "--untracked-files=all"]);
	if (status.status !== 0 || status.stdout.trim()) return true;
	const commits = runGit(state.path, ["rev-list", "--count", `${state.baseCommit}..HEAD`]);
	return commits.status !== 0 || Number.parseInt(commits.stdout.trim(), 10) > 0;
}

function removeWorktree(state: WorktreeSessionState): string | null {
	const remove = runGit(state.repoRoot, ["worktree", "remove", "--force", state.path]);
	if (remove.status !== 0) return remove.stderr.trim() || remove.stdout.trim() || "worktree removal failed";
	invalidateWorktreeRoots();
	if (state.branch) {
		const branch = runGit(state.repoRoot, ["branch", "-D", state.branch]);
		if (branch.status !== 0) return branch.stderr.trim() || branch.stdout.trim() || "branch removal failed";
	}
	runGit(state.repoRoot, ["worktree", "prune"]);
	return null;
}

function formatTargetLabel(state: WorktreeSessionState): string {
	return `${state.path}${state.branch ? ` (${state.branch})` : ""}`;
}

async function switchIntoWorktree(ctx: ExtensionCommandContext, request: EnterWorktreeRequest): Promise<void> {
	const sourceSession = ctx.sessionManager.getSessionFile();
	if (!sourceSession) {
		notifyPi(ctx.ui, "EnterWorktree requires a persisted Pi session.", "error");
		return;
	}
	const target = resolveEnterTarget(ctx.cwd, request);
	if ("error" in target) {
		notifyPi(ctx.ui, target.error, "error");
		return;
	}
	if (canonicalize(ctx.cwd) === canonicalize(target.path)) {
		notifyPi(ctx.ui, "Already inside the requested worktree.", "info");
		return;
	}

	let state: WorktreeSessionState;
	if (target.created) {
		const created = createWorktree(target);
		if ("error" in created) {
			notifyPi(ctx.ui, created.error, "error");
			return;
		}
		state = created;
		// A worktree inside the repository leaves an untracked `.pi/` behind.
		// Report it; editing a user's .gitignore needs their say-so.
		if (!isManagedWorktreesIgnored(target.repoRoot)) {
			notifyPi(
				ctx.ui,
				`${MANAGED_WORKTREES_SHELL_PATH}/ is not git-ignored in this repository — add it to .gitignore or the linked worktree shows up as untracked in the parent checkout`,
				"warning",
			);
		}
	} else {
		state = {
			baseCommit: target.baseCommit,
			branch: target.record?.branch,
			created: false,
			parentSession: "",
			path: target.path,
			repoRoot: target.repoRoot,
		};
	}
	state.parentSession = sourceSession;

	let replacement: SessionManager;
	let replacementFile: string | undefined;
	let switchRequested = false;
	// UI handles are not session-bound getters; never access the old ctx after
	// switchSession has invalidated it, even when a host callback rejects.
	let outcomeUI = ctx.ui;
	try {
		replacement = SessionManager.forkFrom(sourceSession, state.path);
		replacementFile = replacement.getSessionFile() ?? undefined;
		if (!replacementFile) throw new Error("replacement session has no file");
		replacement.appendCustomEntry(WORKTREE_SESSION_ENTRY, state);
		switchRequested = true;
		const result = await ctx.switchSession(replacementFile, {
			withSession: async (next) => {
				outcomeUI = next.ui;
				notifyPi(next.ui, `Entered worktree: ${formatTargetLabel(state)}`, "info");
				await next.sendMessage({
					customType: "pi-utils-worktree-applied",
					content: `Entered worktree. Active cwd: ${state.path}. Continue the pending task here. Resolve all project paths, edits, writes, shell commands and delegated work against this cwd, not paths from the parent conversation. Other tools in the transition batch were not executed; retry needed operations here.`,
					display: false,
				}, { triggerTurn: true });
			},
		});
		if (result.cancelled) {
			// A cancelled replacement applied nothing, so the created worktree and
			// the forked session file are both this command's own leftovers.
			const cleanupError = state.created ? removeWorktree(state) : null;
			fs.rmSync(replacementFile, { force: true });
			if (cleanupError) {
				notifyPi(outcomeUI, `Cancelled, but worktree cleanup failed: ${cleanupError}`, "warning");
			}
		}
	} catch (error) {
		// switchSession may apply the new runtime before host rebinding fails.
		// Only a failure before the replacement was requested proves rollback is
		// safe; an ambiguous failure must preserve the checkout and its edits, but
		// a created worktree must never be left behind unreported either.
		if (!switchRequested) {
			const cleanupError = state.created ? removeWorktree(state) : null;
			if (replacementFile) fs.rmSync(replacementFile, { force: true });
			if (cleanupError) {
				notifyPi(outcomeUI, `Rollback failed, worktree left at ${state.path}: ${cleanupError}`, "warning");
			}
		} else if (state.created) {
			notifyPi(
				outcomeUI,
				`The session may not have switched; the created worktree is kept: ${formatTargetLabel(state)}. Remove it with \`git worktree remove --force ${state.path}\` if it is not in use.`,
				"warning",
			);
		}
		notifyPi(outcomeUI, error instanceof Error ? error.message : String(error), "error");
	}
}

/**
 * Pi runs an extension command immediately, even while the agent streams, and a
 * session replacement aborts the running turn. Wait for the session to settle so
 * the fork includes the finished turn and nothing is cut off by the switch.
 */
async function settleBeforeSwitching(ctx: ExtensionCommandContext): Promise<void> {
	if (ctx.isIdle()) return;
	notifyPi(ctx.ui, "Waiting for the current turn to finish before switching sessions…", "info");
	await ctx.waitForIdle();
}

async function switchOutOfWorktree(ctx: ExtensionCommandContext): Promise<void> {
	const state = readWorktreeSessionState(ctx);
	if (!state) {
		notifyPi(ctx.ui, "This session was not entered through EnterWorktree.", "warning");
		return;
	}
	if (!fs.existsSync(state.parentSession)) {
		notifyPi(ctx.ui, `Parent session no longer exists: ${state.parentSession}`, "error");
		return;
	}

	let remove = false;
	if (state.created && ctx.hasUI) {
		const dirty = worktreeHasChanges(state);
		const options = dirty
			? ["Keep worktree (changes detected)", "Remove worktree and branch anyway", "Cancel"]
			: ["Keep worktree", "Remove worktree and branch", "Cancel"];
		const choice = await ctx.ui.select(`Exit ${formatTargetLabel(state)}`, options);
		if (!choice || choice === "Cancel") return;
		remove = choice.startsWith("Remove ");
	}

	const result = await ctx.switchSession(state.parentSession, {
		withSession: async (parent) => {
			if (remove) {
				const error = removeWorktree(state);
				if (error) {
					notifyPi(parent.ui, `Returned to parent session, but cleanup failed: ${error}`, "warning");
					return;
				}
				notifyPi(parent.ui, `Exited worktree and removed: ${state.path}`, "info");
				return;
			}
			notifyPi(parent.ui, `Exited worktree; kept: ${state.path}`, "info");
		},
	});
	if (result.cancelled) return;
}

interface EnterWorktreeToolInput {
	name?: string;
	path?: string;
}

interface TransitionMessageOptions {
	deliverAs: "followUp";
	expandPromptTemplates: true;
}

function queueTransitionCommand(
	pi: Pick<ExtensionAPI, "sendUserMessage">,
	command: string,
): void {
	const sendUserMessage = pi.sendUserMessage as (
		content: string,
		options: TransitionMessageOptions,
	) => void;
	sendUserMessage(command, {
		deliverAs: "followUp",
		expandPromptTemplates: true,
	});
}

const enterWorktreeParameters = Type.Object({
	name: Type.Optional(Type.String({ description: "New managed worktree name" })),
	path: Type.Optional(Type.String({ description: "Existing registered worktree path" })),
});

export default function registerWorktreeSession(pi: ExtensionAPI): void {
	let transitionCallId: string | undefined;
	let pendingCommand: string | undefined;
	let pendingLabel: string | undefined;
	let transitionSignal: AbortSignal | undefined;
	/**
	 * One session switch at a time. Two commands that wait for the same turn would
	 * otherwise both proceed and start a replacement: the queued-transition flag
	 * covers tool requests, not a switch that is already running.
	 */
	let switchInFlight = false;

	function queueTransition(transition: "enter_worktree" | "exit_worktree", command: string, signal: AbortSignal | undefined): void {
		transitionSignal = signal;
		pendingCommand = command;
		pendingLabel = transition;
	}

	function setWorktreeToolActive(name: "enter_worktree" | "exit_worktree", active: boolean): void {
		// Only `name` is managed here: the sibling is left exactly as the snapshot
		// reports it, because its disclosure is decided by its own call site.
		// Declaring both as owned would erase the sibling on this write.
		setOwnedTools(pi, { owned: [name], toggled: [name], enabled: active });
	}

	function syncWorktreeTools(ctx: Pick<ExtensionContext, "sessionManager">): void {
		setWorktreeToolActive("exit_worktree", readWorktreeSessionState(ctx) !== null);
	}

	if (typeof pi.on === "function") {
		// Inspect the whole batch before parallel preflight: even tools preceding
		// enter_worktree in source order must not execute against the old cwd.
		pi.on("message_end", (event) => {
			if (event.message.role !== "assistant") return;
			const transition = event.message.content.find((part) =>
				part.type === "toolCall" && (part.name === "enter_worktree" || part.name === "exit_worktree"));
			transitionCallId = transition?.type === "toolCall" ? transition.id : undefined;
		});
		pi.on("tool_call", (event) => {
			if (pendingCommand || (transitionCallId && event.toolCallId !== transitionCallId)) {
				// Name the pending transition: an identical transition tool in the
				// same batch is queued behind the first one, not lost.
				const reason = pendingCommand && pendingLabel
					? `${pendingLabel} is already queued for this turn. This tool was not executed. Retry it only after the replacement session confirms its active cwd.`
					: "Worktree transition pending. This tool was not executed. Retry it only after the replacement session confirms its active cwd.";
				return { block: true, terminate: true, reason };
			}
		});
		pi.on("agent_settled", (_event, ctx) => {
			const command = transitionSignal?.aborted ? undefined : pendingCommand;
			const dropped = command === undefined ? pendingLabel : undefined;
			pendingCommand = undefined;
			pendingLabel = undefined;
			transitionSignal = undefined;
			transitionCallId = undefined;
			if (dropped) {
				// The model was told the transition was pending. An abort ends the
				// run without applying it, so the user is told instead of leaving
				// the model's expectation standing.
				notifyPi(ctx.ui, `Queued ${dropped} was dropped: the run ended before the session transition was applied`, "warning");
			}
			// Expanded slash commands dispatch immediately, even with followUp.
			// Wait for settlement so forkFrom includes all tool results and no
			// source-session tool execution can race session replacement.
			if (command) queueTransitionCommand(pi, command);
		});
		pi.on("session_start", async (_event, ctx) => {
			syncWorktreeTools(ctx);
		});

		pi.on("session_shutdown", async () => {
			setWorktreeToolActive("exit_worktree", false);
		});
	}

	/**
	 * Runs one worktree session switch at a time.
	 *
	 * A command runs even while the agent streams, and a second switch would race
	 * the first one's session replacement and can leave a replacement session
	 * running with nobody driving it. The slot is claimed before the first await,
	 * because two commands that start together must not both reach the wait.
	 */
	async function runExclusiveSwitch(ctx: ExtensionCommandContext, run: () => Promise<void>): Promise<void> {
		// A queued transition has not been applied yet; a second switch here would
		// race the first one's session replacement.
		if (pendingCommand) {
			notifyPi(ctx.ui, `A worktree transition (${pendingLabel ?? "pending"}) is queued and has not been applied yet — wait for it before starting another.`, "warning");
			return;
		}
		if (switchInFlight) {
			notifyPi(ctx.ui, "Another worktree session switch is still in progress — wait for it to finish before starting another.", "warning");
			return;
		}
		switchInFlight = true;
		try {
			await settleBeforeSwitching(ctx);
			if (pendingCommand) {
				notifyPi(ctx.ui, `A worktree transition (${pendingLabel ?? "pending"}) was queued while the turn finished — it has not been applied yet.`, "warning");
				return;
			}
			await run();
		} finally {
			switchInFlight = false;
		}
	}

	pi.registerCommand("enter-worktree", {
		description: "Create or enter a git worktree in a replacement Pi session",
		handler: async (args, ctx) => {
			let request: EnterWorktreeRequest;
			try {
				request = args.trim().startsWith("{") ? (JSON.parse(args) as EnterWorktreeRequest) : { name: args.trim() || undefined };
			} catch {
				notifyPi(ctx.ui, "Invalid EnterWorktree request JSON.", "error");
				return;
			}
			await runExclusiveSwitch(ctx, () => switchIntoWorktree(ctx, request));
		},
	});

	pi.registerCommand("exit-worktree", {
		description: "Return to the parent Pi session and optionally clean up its git worktree",
		handler: async (_args, ctx) => {
			await runExclusiveSwitch(ctx, () => switchOutOfWorktree(ctx));
		},
	});

	pi.registerTool({
		name: "enter_worktree",
		label: "Enter Worktree",
		promptSnippet: "Switch the current Pi session into an isolated git worktree.",
		description: "Queue a Pi session transition into a new or existing git worktree. The transition is applied by the enter-worktree command.",
		renderShell: "self",
		renderCall: () => rows.emptyCall(),
		renderResult(result, options, theme, context) {
			const params = context.args as EnterWorktreeToolInput;
			const target = params.name ?? params.path ?? "new worktree";
			return renderWorktreeToolResult(result, options, theme, context, `enter ${safeDisplayText(target)}`);
		},
		parameters: enterWorktreeParameters,
		async execute(_toolCallId, params: EnterWorktreeToolInput, signal) {
			queueTransition("enter_worktree", `/enter-worktree ${JSON.stringify(params)}`, signal);
			return {
				terminate: true,
				content: [{ type: "text", text: "Queued enter_worktree; the session transition is pending. Stop using the old cwd; work resumes after the replacement session confirms its active cwd." }],
				details: { status: "queued", transition: "enter_worktree", request: params },
			};
		},
	});

	pi.registerTool({
		name: "exit_worktree",
		label: "Exit Worktree",
		promptSnippet: "Return the current Pi session to its parent session and handle worktree cleanup.",
		description: "Queue a Pi session transition back to the parent session. Cleanup is selected by the user when the command runs.",
		renderShell: "self",
		renderCall: () => rows.emptyCall(),
		renderResult(result, options, theme, context) {
			return renderWorktreeToolResult(result, options, theme, context, "exit current worktree");
		},
		parameters: Type.Object({}),
		async execute(_toolCallId, _params, signal) {
			queueTransition("exit_worktree", "/exit-worktree", signal);
			return {
				terminate: true,
				content: [{ type: "text", text: "Queued exit_worktree; the session transition is pending. Do not run other tools until the parent session is active." }],
				details: { status: "queued", transition: "exit_worktree" },
			};
		},
	});

}
