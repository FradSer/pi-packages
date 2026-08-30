/**
 * pi-utils-fradser — git worktree-aware @ completions.
 *
 * Wraps the built-in editor autocomplete provider and drops suggestions whose
 * paths resolve inside another git worktree: a session in main never sees
 * linked worktree contents, and a session inside a linked worktree never sees
 * sibling worktrees or the main checkout.
 */

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type {
	AutocompleteItem,
	AutocompleteProvider,
} from "@earendil-works/pi-tui";

export interface WorktreeRoots {
	currentRoot: string | null;
	foreignRoots: string[];
	managedWorktreeDir: string | null;
}

function canonicalize(candidate: string): string {
	try {
		return fs.realpathSync(candidate);
	} catch {
		return path.resolve(candidate);
	}
}

/**
 * Realpath the deepest existing ancestor and append the non-existent remainder,
 * so candidates under symlinked directories still land in the canonical space
 * even when their leaf does not exist.
 */
const canonicalCache = new Map<string, string>();

function canonicalizeBestEffort(candidate: string): string {
	const hit = canonicalCache.get(candidate);
	if (hit !== undefined) return hit;

	let remainder = "";
	let current = candidate;
	let resolved: string | null = null;
	for (;;) {
		try {
			resolved = `${fs.realpathSync(current)}${remainder}`;
			break;
		} catch {
			const parent = path.dirname(current);
			if (parent === current) break;
			remainder = `${path.sep}${path.basename(current)}${remainder}`;
			current = parent;
		}
	}
	if (resolved === null) return candidate;

	if (canonicalCache.size >= 1024) canonicalCache.clear();
	canonicalCache.set(candidate, resolved);
	return resolved;
}

function runGit(cwd: string, args: string[]): string | null {
	try {
		return execFileSync("git", args, {
			cwd,
			encoding: "utf-8",
			stdio: ["ignore", "pipe", "ignore"],
		}).trim();
	} catch {
		return null;
	}
}

/**
 * Collect the current session's worktree root plus every other root reported
 * by `git worktree list --porcelain`. Outside a git repository both values are
 * empty/null and filtering is disabled.
 */
export function collectWorktreeRoots(cwd: string): WorktreeRoots {
	const porcelain = runGit(cwd, ["worktree", "list", "--porcelain"]);
	if (!porcelain) return { currentRoot: null, foreignRoots: [], managedWorktreeDir: null };

	interface Entry {
		bare: boolean;
		root: string;
	}
	const entries: Entry[] = [];
	for (const line of porcelain.split("\n")) {
		if (line.startsWith("worktree ")) {
			entries.push({ bare: false, root: canonicalize(line.slice(9)) });
		} else if (line.trim() === "bare") {
			const last = entries[entries.length - 1];
			if (last) last.bare = true;
		}
	}

	const topLevel = runGit(cwd, ["rev-parse", "--show-toplevel"]);
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

	const mainRoot = entries[0]?.root ?? currentRoot;
	const managedWorktreeDir = mainRoot
		? path.join(mainRoot, ".pi", "worktrees")
		: null;

	return { currentRoot, foreignRoots, managedWorktreeDir };
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

function isInside(candidate: string, root: string): boolean {
	return candidate === root || candidate.startsWith(`${root}${path.sep}`);
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
	if (roots.currentRoot) {
		const ownManagedDir = canonicalizeBestEffort(
			path.join(roots.currentRoot, ".pi", "worktrees"),
		);
		if (isInside(canonicalAbsolute, ownManagedDir)) {
			return true;
		}
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
}
