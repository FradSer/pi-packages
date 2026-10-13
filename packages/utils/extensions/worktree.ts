/**
 * pi-utils-fradser — git worktree path redirect.
 *
 * Intercepts simple `git worktree add` bash tool calls and rewrites the target
 * path to live inside the repository's `.pi/worktrees/<name>`. The bash tool
 * runs in the session cwd, so a command issued from a subdirectory is rewritten
 * to an absolute repository-root path; only a command already running at the
 * repository root keeps the short relative spelling. Commands with shell
 * constructs or options outside Git's documented worktree-add syntax are left
 * unchanged.
 */

import path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { isToolCallEventType } from "@earendil-works/pi-coding-agent";
import { notifyPi } from "@fradser/pi-kit";
import {
	canonicalize,
	isManagedWorktreesIgnored,
	MANAGED_WORKTREES_DIR,
	MANAGED_WORKTREES_SHELL_PATH,
	repositoryRootFor,
} from "./git/worktrees.ts";
import { invalidateWorktreeRoots } from "./worktree-completion.ts";

interface ShellToken {
	end: number;
	hasUnsafeExpansion: boolean;
	raw: string;
	start: number;
	value: string;
}

const BOOLEAN_OPTIONS = new Set([
	"-d",
	"-f",
	"-q",
	"--checkout",
	"--detach",
	"--force",
	"--guess-remote",
	"--lock",
	"--no-checkout",
	"--no-detach",
	"--no-force",
	"--no-guess-remote",
	"--no-lock",
	"--no-orphan",
	"--no-quiet",
	"--no-relative-paths",
	"--no-track",
	"--orphan",
	"--quiet",
	"--relative-paths",
	"--track",
]);

const VALUE_OPTIONS = new Set(["-b", "-B", "--reason"]);
const SHELL_OPERATORS = new Set([";", "&", "|", "<", ">", "(", ")"]);
const UNSAFE_UNQUOTED_EXPANSIONS = new Set(["*", "?", "[", "]", "{", "}"]);

/**
 * Tokenize the small shell subset this redirect supports. Rather than trying
 * to parse arbitrary shell, reject substitutions, control operators, and
 * unquoted glob expansions so the hook never changes their meaning.
 */
function tokenizeSimpleShell(command: string): ShellToken[] | null {
	if (command.includes("\n") || command.includes("\r")) return null;

	const tokens: ShellToken[] = [];
	let index = 0;

	while (index < command.length) {
		while (/\s/.test(command[index] ?? "")) index++;
		if (index === command.length) break;

		const start = index;
		let raw = "";
		let value = "";
		let hasUnsafeExpansion = false;

		while (index < command.length && !/\s/.test(command[index] ?? "")) {
			const char = command[index];
			if (!char) break;

			if (char === "\\") {
				const escaped = command[index + 1];
				if (!escaped || escaped === "\n" || escaped === "\r") return null;
				raw += `\\${escaped}`;
				value += escaped;
				index += 2;
				continue;
			}

			if (char === "'") {
				const closingQuote = command.indexOf("'", index + 1);
				if (closingQuote === -1) return null;
				const quoted = command.slice(index + 1, closingQuote);
				raw += command.slice(index, closingQuote + 1);
				value += quoted;
				index = closingQuote + 1;
				continue;
			}

			if (char === '"') {
				raw += char;
				index++;
				let closed = false;
				while (index < command.length) {
					const quoted = command[index];
					if (quoted === '"') {
						raw += quoted;
						index++;
						closed = true;
						break;
					}
					if (quoted === "$" || quoted === "`") return null;
					if (quoted === "\\") {
						const escaped = command[index + 1];
						if (!escaped || escaped === "\n" || escaped === "\r") return null;
						raw += `\\${escaped}`;
						value += '"$`\\'.includes(escaped) ? escaped : `\\${escaped}`;
						index += 2;
						continue;
					}
					raw += quoted;
					value += quoted;
					index++;
				}
				if (!closed) return null;
				continue;
			}

			if (char === "$" || char === "`" || SHELL_OPERATORS.has(char))
				return null;
			if (UNSAFE_UNQUOTED_EXPANSIONS.has(char)) hasUnsafeExpansion = true;
			raw += char;
			value += char;
			index++;
		}

		tokens.push({ end: index, hasUnsafeExpansion, raw, start, value });
	}

	return tokens;
}

function isAlreadyRedirected(candidate: string): boolean {
	const normalized = candidate.replace(/\\/g, "/").replace(/\/+$/, "");
	return (
		normalized === MANAGED_WORKTREES_SHELL_PATH ||
		normalized.startsWith(`${MANAGED_WORKTREES_SHELL_PATH}/`) ||
		normalized.endsWith(`/${MANAGED_WORKTREES_SHELL_PATH}`) ||
		normalized.includes(`/${MANAGED_WORKTREES_SHELL_PATH}/`)
	);
}

function worktreeName(candidate: string): string | null {
	const name = candidate.split("/").filter(Boolean).at(-1);
	return name && name !== "." && name !== ".." ? name : null;
}

function shellQuote(value: string): string {
	return /^[A-Za-z0-9_@%+=:,./-]+$/.test(value)
		? value
		: `'${value.replace(/'/g, `'"'"'`)}'`;
}

export interface WorktreeRedirectOptions {
	/**
	 * Directory the bash tool runs in. When it is not the repository root, the
	 * rewritten path is anchored to the absolute repository root so the
	 * worktree still lands in the one managed directory.
	 */
	cwd?: string;
}

export interface WorktreeRedirectPlan {
	/** The rewritten command text. */
	command: string;
	/** The worktree name the redirect used. */
	name: string;
	/** The directory the linked worktree actually lands in. */
	target: string;
}

/**
 * Plans the redirect for a simple `git worktree add` command, or returns null
 * when the command form is unsupported and must stay unchanged.
 *
 * The plan carries the directory it actually used: the short relative spelling
 * only holds for a command issued at the repository root, so a caller that
 * assumed it would misreport where the worktree landed.
 */
export function planWorktreeAddRedirect(
	command: string,
	options: WorktreeRedirectOptions = {},
): WorktreeRedirectPlan | null {
	const tokens = tokenizeSimpleShell(command);
	if (!tokens || tokens.length < 4) return null;
	if (
		tokens[0]?.value !== "git" ||
		tokens[1]?.value !== "worktree" ||
		tokens[2]?.value !== "add"
	) {
		return null;
	}

	if (tokens.some((token) => token.hasUnsafeExpansion)) return null;

	let pathToken: ShellToken | undefined;
	let commitIsh: ShellToken | undefined;
	let optionsEnded = false;

	for (let index = 3; index < tokens.length; index++) {
		const token = tokens[index];
		if (!token) return null;

		if (!pathToken && !optionsEnded) {
			if (token.value === "--") {
				optionsEnded = true;
				continue;
			}
			if (BOOLEAN_OPTIONS.has(token.value)) continue;
			if (VALUE_OPTIONS.has(token.value)) {
				const optionValue = tokens[++index];
				if (
					!optionValue ||
					optionValue.value === "--" ||
					optionValue.value.startsWith("-")
				) {
					return null;
				}
				continue;
			}
			if (
				(token.value.startsWith("--reason=") &&
					token.value.length > "--reason=".length) ||
				(token.value.startsWith("-b") && token.value.length > 2) ||
				(token.value.startsWith("-B") && token.value.length > 2)
			) {
				continue;
			}
			if (token.value.startsWith("-")) return null;
		}

		if (!pathToken) {
			pathToken = token;
			continue;
		}
		if (!commitIsh) {
			commitIsh = token;
			continue;
		}
		return null;
	}

	if (!pathToken || pathToken.hasUnsafeExpansion || pathToken.raw.startsWith("~"))
		return null;
	if (isAlreadyRedirected(pathToken.value)) return null;

	const name = worktreeName(pathToken.value);
	if (!name) return null;

	// The managed directory belongs to the repository, not to wherever the
	// command happened to run. Only a command already at the repository root
	// can keep the short relative spelling.
	const root = options.cwd ? repositoryRootFor(options.cwd) : null;
	const atRepositoryRoot =
		root !== null && options.cwd !== undefined && canonicalize(options.cwd) === canonicalize(root);
	const directory = atRepositoryRoot
		? MANAGED_WORKTREES_SHELL_PATH
		: root
			? path.join(root, MANAGED_WORKTREES_DIR)
			: MANAGED_WORKTREES_SHELL_PATH;

	const target = path.posix.join(directory, name);
	return {
		command: `mkdir -p ${shellQuote(directory)} && ${command.slice(0, pathToken.start)}${shellQuote(target)}${command.slice(pathToken.end)}`,
		name,
		target,
	};
}

/**
 * Rewrites a simple `git worktree add` command. The implementation only
 * understands the options shown by `git worktree add -h`; all other command
 * forms are deliberately returned unchanged.
 */
export function rewriteWorktreeAddCommand(
	command: string,
	options: WorktreeRedirectOptions = {},
): string {
	return planWorktreeAddRedirect(command, options)?.command ?? command;
}

export default function (pi: ExtensionAPI) {
	pi.on("tool_call", async (event, ctx) => {
		if (!isToolCallEventType("bash", event)) return;

		const command = event.input.command || "";
		const plan = planWorktreeAddRedirect(command, { cwd: ctx.cwd });
		if (!plan || plan.command === command) return;

		event.input.command = plan.command;
		// The command is about to change the repository's worktree list, so the
		// discovery memo for this session is stale from here on.
		invalidateWorktreeRoots();
		notifyPi(
			ctx.ui,
			`worktree path redirected to ${plan.target} — linked worktrees stay inside the repo`,
			"info",
		);
		// Never edit a user's .gitignore without being asked; report the
		// untracked-directory consequence instead.
		if (!isManagedWorktreesIgnored(ctx.cwd)) {
			notifyPi(
				ctx.ui,
				`${MANAGED_WORKTREES_SHELL_PATH}/ is not git-ignored here — add it to .gitignore or the linked worktree shows up as untracked in the parent checkout`,
				"warning",
			);
		}
	});
}
