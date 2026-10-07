/**
 * pi-utils-fradser — git worktree-aware @ completions.
 *
 * Wraps the built-in editor autocomplete provider and drops suggestions whose
 * paths resolve inside another git worktree: a session in main never sees
 * linked worktree contents, and a session inside a linked worktree never sees
 * sibling worktrees or the main checkout.
 */

import os from "node:os";
import path from "node:path";
import {
	isToolCallEventType,
	type ExtensionAPI,
} from "@earendil-works/pi-coding-agent";
import type {
	AutocompleteItem,
	AutocompleteProvider,
} from "@earendil-works/pi-tui";
import {
	canonicalize,
	canonicalizeBestEffort,
	gitOutput,
	isInside,
	listWorktrees,
	mainWorktreeRoot,
	managedWorktreesDir,
	MANAGED_WORKTREES_SHELL_PATH,
} from "./git/worktrees.ts";

export interface WorktreeRoots {
	currentRoot: string | null;
	foreignRoots: string[];
	managedWorktreeDir: string | null;
}

/**
 * Collect the current session's worktree root plus every other root reported
 * by `git worktree list --porcelain`. Outside a git repository both values are
 * empty/null and filtering is disabled.
 */
export function collectWorktreeRoots(cwd: string): WorktreeRoots {
	const entries = listWorktrees(cwd);
	if (entries.length === 0) return { currentRoot: null, foreignRoots: [], managedWorktreeDir: null };

	const topLevel = gitOutput(cwd, ["rev-parse", "--show-toplevel"]);
	let currentRoot = topLevel ? canonicalize(topLevel) : null;
	if (!currentRoot) {
		// A session opened at a bare repository has no toplevel; treat the bare
		// entry as current when the cwd sits on it.
		const canonicalCwd = canonicalizeBestEffort(cwd);
		currentRoot =
			entries.find((entry) => entry.bare && entry.root === canonicalCwd)?.root ??
			null;
	}
	const foreignRoots =
		currentRoot === null
			? []
			: entries
					.map((entry) => entry.root)
					.filter((root) => root !== currentRoot);

	return {
		currentRoot,
		foreignRoots,
		managedWorktreeDir: managedWorktreesDir(mainWorktreeRoot(entries)),
	};
}

/**
 * Strip @ prefix, surrounding quotes, and trailing slash into a plain path.
 * pi-tui wraps values verbatim in quotes without escaping, so no unquoting of
 * backslash sequences happens here (Windows separators stay intact).
 */
export function suggestionToPath(value: string): string {
	let candidate = value.startsWith("@") ? value.slice(1) : value;
	if (
		candidate.length >= 2 &&
		candidate.startsWith('"') &&
		candidate.endsWith('"')
	) {
		candidate = candidate.slice(1, -1);
	}
	return candidate.replace(/[\\/]+$/, "");
}

function isInsideManagedDir(candidate: string, root: string): boolean {
	const managed = managedWorktreesDir(root);
	return managed !== null && isInside(candidate, canonicalizeBestEffort(managed));
}

/** True when the suggestion resolves inside a non-current git worktree root or managed worktrees dir. */
export function isInForeignWorktree(
	value: string,
	basePath: string,
	roots: WorktreeRoots,
): boolean {
	if (!roots.currentRoot && roots.foreignRoots.length === 0 && !roots.managedWorktreeDir) {
		return false;
	}

	let candidate = suggestionToPath(value);
	if (!candidate) return false;

	if (candidate.startsWith("~/")) {
		candidate = path.join(os.homedir(), candidate.slice(2));
	}
	const base = canonicalizeBestEffort(basePath);
	const absolute = path.isAbsolute(candidate)
		? candidate
		: path.resolve(base, candidate);

	const canonicalAbsolute = canonicalizeBestEffort(absolute);

	// Inside the current worktree, hide the internal .pi/worktrees directory
	if (roots.currentRoot && isInsideManagedDir(canonicalAbsolute, roots.currentRoot)) {
		return true;
	}

	// Outside the current worktree, hide the repo's managed .pi/worktrees directory
	if (roots.managedWorktreeDir) {
		const canonicalManaged = canonicalizeBestEffort(roots.managedWorktreeDir);
		if (isInside(canonicalAbsolute, canonicalManaged)) {
			if (roots.currentRoot && isInside(canonicalAbsolute, roots.currentRoot)) {
				return false;
			}
			return true;
		}
	}

	for (const root of roots.foreignRoots) {
		if (isInside(canonicalAbsolute, root)) return true;
	}
	return false;
}

export function isItemInForeignWorktree<T extends AutocompleteItem>(
	item: T,
	basePath: string,
	roots: WorktreeRoots,
): boolean {
	if (isInForeignWorktree(item.value, basePath, roots)) return true;
	if (
		item.description &&
		isInForeignWorktree(item.description, basePath, roots)
	) {
		return true;
	}
	return false;
}

export function foreignWorktreeReadReason(filePath: string): string {
	return `Blocked read of a different git worktree: ${filePath}. Use enter_worktree to switch the Pi session to that registered worktree before reading its files.`;
}

export function filterForeignWorktreeItems<T extends AutocompleteItem>(
	items: T[],
	basePath: string,
	roots: WorktreeRoots,
): T[] {
	if (
		!roots.currentRoot &&
		roots.foreignRoots.length === 0 &&
		!roots.managedWorktreeDir
	) {
		return items;
	}
	return items.filter(
		(item) => !isItemInForeignWorktree(item, basePath, roots),
	);
}

export function filterForeignWorktreeSearchLines(
	text: string,
	basePath: string,
	roots: WorktreeRoots,
): string {
	if (
		!roots.currentRoot &&
		roots.foreignRoots.length === 0 &&
		!roots.managedWorktreeDir
	) {
		return text;
	}

	const lines = text.split("\n");
	const filtered: string[] = [];

	for (const line of lines) {
		// Matches lines like:
		// packages/foo/bar.ts
		// packages/foo/bar.ts:12: content
		// .pi/worktrees/foo/bar.ts
		// /absolute/path/to/.pi/worktrees/...
		const trimmed = line.trim();
		if (!trimmed) {
			filtered.push(line);
			continue;
		}

		// Check if line starts with a path (before any colon, space, or tab)
		const colonMatch = trimmed.match(/^([^:\s]+(?::\d+)*)/);
		const potentialPath = colonMatch ? colonMatch[1]?.split(":")[0] : trimmed.split(/\s+/)[0];

		if (potentialPath && isInForeignWorktree(potentialPath, basePath, roots)) {
			continue;
		}

		filtered.push(line);
	}

	return filtered.join("\n");
}

let cache: { cwd: string; roots: WorktreeRoots } | null = null;

/**
 * Live session cwd. Session replacement (EnterWorktree) swaps sessions without
 * re-loading extensions, so the captured session_start context goes stale;
 * every session_start refreshes the cwd the filter resolves against.
 */
let activeCwd: string | null = null;

/** Memoized discovery keyed by cwd: git runs at most once per session. */
export function getWorktreeRoots(cwd: string): WorktreeRoots {
	if (!cache || cache.cwd !== cwd) {
		cache = { cwd, roots: collectWorktreeRoots(cwd) };
	}
	return cache.roots;
}

function worktreeCompletionProvider(
	current: AutocompleteProvider,
): AutocompleteProvider {
	return {
		async getSuggestions(lines, cursorLine, cursorCol, options) {
			const result = await current.getSuggestions(
				lines,
				cursorLine,
				cursorCol,
				options,
			);
			if (!result || result.items.length === 0) return result;

			const cwd = activeCwd;
			if (!cwd) return result;
			const roots = getWorktreeRoots(cwd);
			if (
				!roots.currentRoot &&
				roots.foreignRoots.length === 0 &&
				!roots.managedWorktreeDir
			) {
				return result;
			}
			return {
				...result,
				items: filterForeignWorktreeItems(result.items, cwd, roots),
			};
		},
		applyCompletion(lines, cursorLine, cursorCol, item, prefix) {
			return current.applyCompletion(
				lines,
				cursorLine,
				cursorCol,
				item,
				prefix,
			);
		},
		shouldTriggerFileCompletion(lines, cursorLine, cursorCol) {
			return (
				current.shouldTriggerFileCompletion?.(
					lines,
					cursorLine,
					cursorCol,
				) ?? true
			);
		},
	};
}

/** Search tools whose result text is filtered back to the active worktree. */
const SEARCH_TOOLS = new Set(["fffind", "ffgrep", "find", "grep"]);

/** Exclude patterns every managed worktree directory is covered by. */
const MANAGED_EXCLUDE_PATTERNS = [
	`${MANAGED_WORKTREES_SHELL_PATH}/**`,
	MANAGED_WORKTREES_SHELL_PATH,
];

/**
 * True when the target tool actually declares an `exclude` parameter.
 *
 * The search tools belong to other packages, so this package may not assume
 * their input shape: writing an unknown key can fail schema validation. When
 * the declaration is unavailable, skip injection — the tool_result filter below
 * still keeps foreign paths out of the transcript.
 */
function acceptsExclude(pi: ExtensionAPI, toolName: string): boolean {
	const tools = pi.getAllTools?.();
	if (!Array.isArray(tools)) return false;
	const tool = tools.find((candidate) => candidate.name === toolName);
	const properties = (tool?.parameters as { properties?: Record<string, unknown> } | undefined)?.properties;
	return properties !== undefined && "exclude" in properties;
}

function withManagedWorktreeExclude(input: Record<string, unknown>): void {
	const existingExclude = input.exclude;
	if (Array.isArray(existingExclude)) {
		for (const pattern of MANAGED_EXCLUDE_PATTERNS) {
			if (!existingExclude.includes(pattern)) existingExclude.push(pattern);
		}
		return;
	}
	if (typeof existingExclude === "string") {
		const parts = existingExclude
			.split(",")
			.map((part) => part.trim())
			.filter(Boolean);
		for (const pattern of MANAGED_EXCLUDE_PATTERNS) {
			if (!parts.includes(pattern)) parts.push(pattern);
		}
		input.exclude = parts.join(",");
		return;
	}
	if (!existingExclude) input.exclude = MANAGED_EXCLUDE_PATTERNS.join(",");
}

export default function registerWorktreeCompletion(pi: ExtensionAPI): void {
	pi.on("session_start", (_event, ctx) => {
		activeCwd = ctx.cwd;
	});
	pi.on("resources_discover", (_event, ctx) => {
		activeCwd = ctx.cwd;
		// resources_discover runs after every session_start handler, so this
		// wrapper stays outermost even when another package replaces @ completion.
		// It must be registered on every bind because session replacement resets
		// the interactive autocomplete wrapper list.
		ctx.ui.addAutocompleteProvider(worktreeCompletionProvider);
	});
	pi.on("tool_call", (event, ctx) => {
		if (isToolCallEventType("read", event) || isToolCallEventType("edit", event) || isToolCallEventType("write", event)) {
			if (!isInForeignWorktree(event.input.path, ctx.cwd, getWorktreeRoots(ctx.cwd))) return;
			return { block: true, reason: event.toolName === "read"
				? foreignWorktreeReadReason(event.input.path)
				: `Blocked ${event.toolName} of a different git worktree: ${event.input.path}. Active cwd: ${ctx.cwd}. Resolve project paths inside the active worktree, or use enter_worktree to switch sessions first.` };
		}

		// Keep search tools from walking into other checkouts. The tool owns
		// its input schema, so only a declared `exclude` is written to.
		if (SEARCH_TOOLS.has(event.toolName)) {
			const roots = getWorktreeRoots(ctx.cwd);
			if (
				(roots.foreignRoots.length > 0 || roots.managedWorktreeDir) &&
				acceptsExclude(pi, event.toolName)
			) {
				withManagedWorktreeExclude(event.input as Record<string, unknown>);
			}
		}
	});

	pi.on("tool_result", (event, ctx) => {
		if (SEARCH_TOOLS.has(event.toolName)) {
			const roots = getWorktreeRoots(ctx.cwd);
			if (!roots.currentRoot && roots.foreignRoots.length === 0 && !roots.managedWorktreeDir) {
				return;
			}

			if (Array.isArray(event.content)) {
				let modified = false;
				const newContent = event.content.map((part) => {
					if (part.type === "text" && typeof part.text === "string") {
						const filtered = filterForeignWorktreeSearchLines(part.text, ctx.cwd, roots);
						if (filtered !== part.text) {
							modified = true;
							return { ...part, text: filtered };
						}
					}
					return part;
				});

				if (modified) {
					return { content: newContent };
				}
			}
		}
	});
}
