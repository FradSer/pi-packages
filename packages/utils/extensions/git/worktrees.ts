/**
 * Shared git worktree plumbing.
 *
 * The redirect (`worktree.ts`), the isolation filters (`worktree-completion.ts`)
 * and the session switcher (`worktree-session.ts`) all need the same three
 * facts: the canonical path of a candidate, the repository's worktree list, and
 * the single managed worktree directory they must agree on. Keeping one
 * porcelain parser and one `.pi/worktrees` definition here is what stops the
 * three layers from inventing different locations for the same worktree.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

/** The one managed worktree location, relative to the repository root. */
export const MANAGED_WORKTREES_DIR = path.join(".pi", "worktrees");

/** POSIX spelling of {@link MANAGED_WORKTREES_DIR}, for shell command text. */
export const MANAGED_WORKTREES_SHELL_PATH = ".pi/worktrees";

export interface WorktreeRecord {
	bare: boolean;
	branch?: string;
	root: string;
}

export interface GitResult {
	status: number | null;
	stderr: string;
	stdout: string;
}

export function runGit(cwd: string, args: string[]): GitResult {
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

/** Run git and return trimmed stdout, or null when the command did not succeed. */
export function gitOutput(cwd: string, args: string[]): string | null {
	const result = runGit(cwd, args);
	if (result.status !== 0) return null;
	const output = result.stdout.trim();
	return output ? output : null;
}

export function canonicalize(candidate: string): string {
	try {
		return fs.realpathSync(candidate);
	} catch {
		return path.resolve(candidate);
	}
}

/**
 * Realpath the deepest existing ancestor and append the non-existent remainder, so
 * candidates under symlinked directories still land in the canonical space even when
 * their leaf does not exist.
 *
 * Nothing is memoized: a symlink can be retargeted during a session, and a cached
 * answer would keep granting the old identity to a path that now resolves inside a
 * different worktree.
 */
export function canonicalizeBestEffort(candidate: string): string {
	let remainder = "";
	let current = candidate;
	for (;;) {
		try {
			// path.join keeps a root-level remainder from doubling the separator.
			return path.join(fs.realpathSync(current), remainder);
		} catch {
			const parent = path.dirname(current);
			if (parent === current) return candidate;
			remainder = path.join(path.sep + path.basename(current), remainder);
			current = parent;
		}
	}
}

export function isInside(candidate: string, root: string): boolean {
	return candidate === root || candidate.startsWith(`${root}${path.sep}`);
}

/** Parse `git worktree list --porcelain` into canonical roots. */
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
	const output = gitOutput(cwd, ["worktree", "list", "--porcelain"]);
	return output === null ? [] : parseWorktreeList(output);
}

export function currentWorktreeRoot(cwd: string): string | null {
	const top = gitOutput(cwd, ["rev-parse", "--show-toplevel"]);
	return top ? canonicalize(top) : null;
}

/**
 * The main checkout root: the first porcelain entry, which git always reports
 * first. Null outside a repository.
 */
export function mainWorktreeRoot(entries: WorktreeRecord[]): string | null {
	return entries[0]?.root ?? null;
}

/**
 * The repository root that owns every managed worktree. In a linked worktree
 * `rev-parse --show-toplevel` reports the linked root, so the main entry is
 * what keeps `.pi/worktrees` anchored to one repository.
 */
export function repoRoot(cwd: string, entries: WorktreeRecord[]): string | null {
	const main = mainWorktreeRoot(entries);
	if (main) return main;

	// A bare repository has no checkout; its own root still owns worktrees.
	const commonDir = gitOutput(cwd, ["rev-parse", "--git-common-dir"]);
	if (commonDir) {
		const gitDir = canonicalize(path.resolve(cwd, commonDir));
		if (path.basename(gitDir) === ".git") return path.dirname(gitDir);
	}
	return currentWorktreeRoot(cwd);
}

/** Absolute `.pi/worktrees` directory, or null outside a repository. */
export function managedWorktreesDir(root: string | null): string | null {
	return root ? path.join(root, MANAGED_WORKTREES_DIR) : null;
}

/**
 * True when git already ignores the managed worktree directory.
 *
 * Worktrees created inside the repository leave `.pi/` untracked in the parent
 * checkout otherwise, which is both noise and an accidental-commit risk. The
 * answer is advisory: callers notify instead of editing a user's .gitignore.
 */
export function isManagedWorktreesIgnored(cwd: string): boolean {
	return runGit(cwd, ["check-ignore", "-q", MANAGED_WORKTREES_SHELL_PATH]).status === 0;
}

/**
 * True when git accepts `branch` as a branch name. A sanitized worktree name is
 * a valid directory name, which is not the same as a valid ref: git rejects a
 * leading dot or a trailing `.lock`. Ask git instead of restating its rules, so
 * the check cannot drift from the branch `git worktree add -b` is handed.
 */
export function isValidBranchName(cwd: string, branch: string): boolean {
	return runGit(cwd, ["check-ref-format", "--branch", branch]).status === 0;
}

/**
 * True when `refs/heads/<branch>` already exists. A managed worktree is created
 * with `git worktree add -b <name>`, which refuses an existing branch, so a name
 * the user already used is refused before any directory is made.
 */
export function branchExists(cwd: string, branch: string): boolean {
	return runGit(cwd, ["show-ref", "--verify", "--quiet", `refs/heads/${branch}`]).status === 0;
}

/**
 * Repository root for a shell command running in `cwd`, or null when `cwd` is
 * not inside a repository. Used by the redirect so a command issued from a
 * subdirectory still targets the repository's own managed directory.
 */
export function repositoryRootFor(cwd: string): string | null {
	return repoRoot(cwd, listWorktrees(cwd));
}