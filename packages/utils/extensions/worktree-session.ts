/**
 * pi-utils-fradser — Claude Code-style git worktree session switching.
 *
 * Pi binds its built-in tools to the session cwd, so entering a worktree
 * creates a replacement session with that cwd instead of mutating process.cwd.
 */

import { spawnSync } from "node:child_process";
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
import { Text, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import {
	createToolLifecycleResultRenderer,
	eventToolLifecycle,
	formatToolErrorLine,
	notifyPi,
	safeDisplayText,
} from "@fradser/pi-kit";
import { Type } from "typebox";

export const WORKTREE_SESSION_ENTRY = "pi-utils-worktree-session";

interface WorktreeToolResult {
	content: Array<{ text?: string; type: string }>;
}

function worktreeToolText(result: WorktreeToolResult): string {
	return result.content.find((part) => part.type === "text")?.text ?? "";
}

function renderWorktreeToolResult(
	result: WorktreeToolResult,
	options: { expanded?: boolean },
	theme: Pick<Theme, "bold" | "fg" | "bg">,
	context: { isError?: boolean },
	subject: string,
): { invalidate: () => void; render: (width: number) => string[] } | Text {
	if (context.isError) {
		return new Text(theme.fg("error", formatToolErrorLine(worktreeToolText(result))), 0, 0);
	}
	const separator = subject.indexOf(" ");
	const action = separator === -1 ? subject : subject.slice(0, separator);
	const target = separator === -1 ? "" : subject.slice(separator + 1);
	return createToolLifecycleResultRenderer({
		createSpec: () => eventToolLifecycle("worktree", target, {
			label: action,
			details: worktreeToolText(result).split("\n").map((line) => line.trim()).filter(Boolean),
		}),
		expandHint: keyHint("app.tools.expand", "to expand"),
		fit: truncateToWidth,
		visibleWidth,
		renderError: (line, currentTheme) => new Text(currentTheme.fg("error", line), 0, 0),
	})(result, options, theme, context);
}

export interface WorktreeRecord {
	bare: boolean;
	branch?: string;
	root: string;
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

interface GitResult {
	status: number | null;
	stderr: string;
	stdout: string;
}

function runGit(cwd: string, args: string[]): GitResult {
	const result = spawnSync("git", ["-C", cwd, ...args], {
		encoding: "utf-8",
		stdio: ["ignore", "pipe", "pipe"],
	});
	return {
		status: result.status,
		stdout: result.stdout ?? "",
		stderr: result.stderr ?? "",
	};
}

function canonicalize(candidate: string): string {
	try {
		return fs.realpathSync(candidate);
	} catch {
		return path.resolve(candidate);
	}
}

export function parseWorktreeList(output: string): WorktreeRecord[] {
	const entries: WorktreeRecord[] = [];
	for (const line of output.split("\n")) {
		if (line.startsWith("worktree ")) {
			entries.push({ bare: false, root: canonicalize(line.slice(9)) });
			continue;
		}
		const current = entries[entries.length - 1];
		if (!current) continue;
		if (line.trim() === "bare") current.bare = true;
		if (line.startsWith("branch ")) current.branch = line.slice(7).replace(/^refs\/heads\//, "");
	}
	return entries;
}

export function listWorktrees(cwd: string): WorktreeRecord[] {
	const result = runGit(cwd, ["worktree", "list", "--porcelain"]);
	return result.status === 0 ? parseWorktreeList(result.stdout) : [];
}

function currentWorktreeRoot(cwd: string): string | null {
	const result = runGit(cwd, ["rev-parse", "--show-toplevel"]);
	return result.status === 0 && result.stdout.trim()
		? canonicalize(result.stdout.trim())
		: null;
}

function projectRoot(cwd: string, entries: WorktreeRecord[]): string | null {
	const current = currentWorktreeRoot(cwd);
	const canonicalCwd = canonicalize(cwd);
	if (!current && entries.some((entry) => entry.bare && entry.root === canonicalCwd)) return null;

	const commonDir = runGit(cwd, ["rev-parse", "--git-common-dir"]);
	if (commonDir.status === 0 && commonDir.stdout.trim()) {
		const gitDir = canonicalize(path.resolve(cwd, commonDir.stdout.trim()));
		if (path.basename(gitDir) === ".git") return path.dirname(gitDir);
	}
	return current ? entries.find((entry) => entry.root === current)?.root ?? current : null;
}

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
	const repoRoot = projectRoot(cwd, entries);
	if (!repoRoot) return { error: "EnterWorktree requires a non-bare git repository" };

	if (request.path) {
		const record = findRegisteredWorktree(cwd, request.path);
		if (!record) return { error: `path is not a registered git worktree: ${request.path}` };
		const baseCommit = currentHead(cwd);
		if (!baseCommit) return { error: "the current worktree has no commit" };
		return { created: false, path: record.root, record, repoRoot, baseCommit };
	}

	const name = safeName(request.name ?? `pi-${Date.now().toString(36)}`);
	if (!name) return { error: "worktree name is empty after sanitization" };
	const target = path.join(repoRoot, ".pi", "worktrees", name);
	const targetRoot = canonicalize(target);
	const existing = entries.find((entry) => entry.root === targetRoot);
	if (existing) {
		const baseCommit = currentHead(cwd);
		if (!baseCommit) return { error: "the current worktree has no commit" };
		return { created: false, name, path: existing.root, record: existing, repoRoot, baseCommit };
	}
	if (fs.existsSync(target)) return { error: `path exists but is not a registered git worktree: ${target}` };

	const baseCommit = currentHead(cwd);
	if (!baseCommit) return { error: "EnterWorktree requires at least one commit" };
	return { created: true, name, path: target, repoRoot, baseCommit };
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
	try {
		replacement = SessionManager.forkFrom(sourceSession, state.path);
		const replacementFile = replacement.getSessionFile();
		if (!replacementFile) throw new Error("replacement session has no file");
		replacement.appendCustomEntry(WORKTREE_SESSION_ENTRY, state);
		const result = await ctx.switchSession(replacementFile, {
			withSession: async (next) => {
				notifyPi(next.ui, `Entered worktree: ${formatTargetLabel(state)}`, "info");
			},
		});
		if (result.cancelled && state.created) {
			removeWorktree(state);
			fs.rmSync(replacementFile, { force: true });
		}
	} catch (error) {
		if (state.created) removeWorktree(state);
		notifyPi(ctx.ui, error instanceof Error ? error.message : String(error), "error");
	}
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
	function setWorktreeToolActive(name: "enter_worktree" | "exit_worktree", active: boolean): void {
		if (typeof pi.getActiveTools !== "function") return;
		const activeTools = pi.getActiveTools();
		const isActive = activeTools.includes(name);
		if (isActive === active) return;
		pi.setActiveTools(active ? [...activeTools, name] : activeTools.filter((tool) => tool !== name));
	}

	function syncWorktreeTools(ctx: Pick<ExtensionContext, "sessionManager">): void {
		setWorktreeToolActive("exit_worktree", readWorktreeSessionState(ctx) !== null);
	}

	if (typeof pi.on === "function") {
		pi.on("session_start", async (_event, ctx) => {
			syncWorktreeTools(ctx);
		});

		pi.on("session_shutdown", async () => {
			setWorktreeToolActive("exit_worktree", false);
		});
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
			await switchIntoWorktree(ctx, request);
		},
	});

	pi.registerCommand("exit-worktree", {
		description: "Return to the parent Pi session and optionally clean up its git worktree",
		handler: async (_args, ctx) => {
			await switchOutOfWorktree(ctx);
		},
	});

	pi.registerTool({
		name: "enter_worktree",
		label: "Enter Worktree",
		promptSnippet: "Switch the current Pi session into an isolated git worktree.",
		description: "Queue a Pi session transition into a new or existing git worktree. The transition is applied by the enter-worktree command.",
		renderShell: "self",
		renderCall: () => new Text("", 0, 0),
		renderResult(result, options, theme, context) {
			const params = context.args as EnterWorktreeToolInput;
			const target = params.name ?? params.path ?? "new worktree";
			return renderWorktreeToolResult(result, options, theme, context, `enter ${safeDisplayText(target)}`);
		},
		parameters: enterWorktreeParameters,
		async execute(_toolCallId, params: EnterWorktreeToolInput) {
			queueTransitionCommand(
				pi,
				`/enter-worktree ${JSON.stringify(params)}`,
			);
			return {
				content: [{ type: "text", text: "Queued enter_worktree; the session transition is pending." }],
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
		renderCall: () => new Text("", 0, 0),
		renderResult(result, options, theme, context) {
			return renderWorktreeToolResult(result, options, theme, context, "exit current worktree");
		},
		parameters: Type.Object({}),
		async execute() {
			queueTransitionCommand(pi, "/exit-worktree");
			return {
				content: [{ type: "text", text: "Queued exit_worktree; the session transition is pending." }],
				details: { status: "queued", transition: "exit_worktree" },
			};
		},
	});

}
