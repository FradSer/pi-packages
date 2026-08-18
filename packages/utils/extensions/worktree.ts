/**
 * pi-utils-fradser — git worktree path redirect.
 *
 * Intercepts simple `git worktree add` bash tool calls and rewrites the target
 * path to live inside `.pi/worktrees/<name>`. Commands with shell constructs
 * or options outside Git's documented worktree-add syntax are left unchanged.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { isToolCallEventType } from "@earendil-works/pi-coding-agent";

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

function isAlreadyRedirected(path: string): boolean {
	return (
		path === ".pi/worktrees" ||
		path.startsWith(".pi/worktrees/") ||
		path === "./.pi/worktrees" ||
		path.startsWith("./.pi/worktrees/") ||
		path.endsWith("/.pi/worktrees") ||
		path.includes("/.pi/worktrees/")
	);
}

function worktreeName(path: string): string | null {
	const name = path.split("/").filter(Boolean).at(-1);
	return name && name !== "." && name !== ".." ? name : null;
}

function shellQuote(value: string): string {
	return /^[A-Za-z0-9_@%+=:,./-]+$/.test(value)
		? value
		: `'${value.replace(/'/g, `'"'"'`)}'`;
}

/**
 * Rewrites a simple `git worktree add` command. The implementation only
 * understands the options shown by `git worktree add -h`; all other command
 * forms are deliberately returned unchanged.
 */
export function rewriteWorktreeAddCommand(command: string): string {
	const tokens = tokenizeSimpleShell(command);
	if (!tokens || tokens.length < 4) return command;
	if (
		tokens[0]?.value !== "git" ||
		tokens[1]?.value !== "worktree" ||
		tokens[2]?.value !== "add"
	) {
		return command;
	}

	if (tokens.some((token) => token.hasUnsafeExpansion)) return command;

	let path: ShellToken | undefined;
	let commitIsh: ShellToken | undefined;
	let optionsEnded = false;

	for (let index = 3; index < tokens.length; index++) {
		const token = tokens[index];
		if (!token) return command;

		if (!path && !optionsEnded) {
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
					return command;
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
			if (token.value.startsWith("-")) return command;
		}

		if (!path) {
			path = token;
			continue;
		}
		if (!commitIsh) {
			commitIsh = token;
			continue;
		}
		return command;
	}

	if (!path || path.hasUnsafeExpansion || path.raw.startsWith("~"))
		return command;
	if (isAlreadyRedirected(path.value)) return command;

	const name = worktreeName(path.value);
	if (!name) return command;

	const targetPath = shellQuote(`.pi/worktrees/${name}`);
	return `mkdir -p .pi/worktrees && ${command.slice(0, path.start)}${targetPath}${command.slice(path.end)}`;
}

export default function (pi: ExtensionAPI) {
	pi.on("tool_call", async (event, ctx) => {
		if (!isToolCallEventType("bash", event)) return;

		const command = event.input.command || "";
		const rewritten = rewriteWorktreeAddCommand(command);
		if (rewritten === command) return;

		event.input.command = rewritten;
		ctx.ui.notify(
			"worktree path redirected to .pi/worktrees/ — linked worktrees stay inside the repo",
			"info",
		);
	});
}
