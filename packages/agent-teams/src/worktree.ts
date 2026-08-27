/**
 * Teammate worktree isolation — run each spawned worker in a fresh git
 * worktree so parallel workers never collide on the same working tree.
 *
 * Layout: `<repoRoot>/.pi/worktrees/teammate-<taskId>/`, branch
 * `teammate/<taskId>`. On completion the worker's diff is captured against
 * the base commit, then the worktree directory is removed while the branch
 * stays so captured work remains retrievable.
 */

import { execFileSync, spawnSync } from "node:child_process";
import * as path from "node:path";

export interface WorktreeSetup {
  repoRoot: string;
  /** Absolute path of the worktree. */
  path: string;
  /** Working directory for the worker (worktree root). */
  cwd: string;
  branch: string;
  baseCommit: string;
}

export interface WorktreeDiff {
  /** Full patch of the worker's changes vs the base commit ("" when clean). */
  patch: string;
  /** `git diff --stat` summary ("" when clean). */
  diffStat: string;
}

export type WorktreeDiffResult = { ok: true; diff: WorktreeDiff } | { ok: false; error: string };

function runGit(cwd: string, args: string[]): { status: number | null; stdout: string; stderr: string } {
  const result = spawnSync("git", ["-C", cwd, ...args], { encoding: "utf-8" });
  return {
    status: result.status,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
  };
}

function safeTaskSegment(taskId: string): string {
  return taskId.replace(/[^\w.-]/g, "_");
}

/**
 * Create a worktree for a task, branched from the repo's current HEAD.
 * Returns an error string when the cwd is not a git repository or the
 * worktree could not be created.
 */
export function createWorktree(
  cwd: string,
  taskId: string,
): WorktreeSetup | { error: string } {
  const toplevel = runGit(cwd, ["rev-parse", "--show-toplevel"]);
  if (toplevel.status !== 0) {
    return { error: "worktree isolation requires a git repository" };
  }
  const repoRoot = toplevel.stdout.trim();
  const baseCommit = runGit(repoRoot, ["rev-parse", "HEAD"]);
  if (baseCommit.status !== 0 || !baseCommit.stdout.trim()) {
    return { error: "worktree isolation requires at least one commit" };
  }

  const safeId = safeTaskSegment(taskId);
  const worktreePath = path.join(repoRoot, ".pi", "worktrees", `teammate-${safeId}`);
  const branch = `teammate/${safeId}`;

  const add = runGit(repoRoot, ["worktree", "add", worktreePath, "-b", branch, "HEAD"]);
  if (add.status !== 0) {
    return { error: `failed to create worktree: ${add.stderr.trim() || add.stdout.trim()}` };
  }

  return {
    repoRoot,
    path: worktreePath,
    cwd: worktreePath,
    branch,
    baseCommit: baseCommit.stdout.trim(),
  };
}

/**
 * Capture the worker's changes in the worktree as a patch against the base
 * commit. The worktree is left untouched; call cleanupWorktree afterwards.
 */
export function captureWorktreeDiff(setup: WorktreeSetup): WorktreeDiffResult {
  try {
    execFileSync("git", ["-C", setup.path, "add", "-A"], { stdio: "ignore" });
    const stat = runGit(setup.path, ["diff", "--cached", "--stat", setup.baseCommit]);
    const patch = runGit(setup.path, ["diff", "--cached", setup.baseCommit]);
    if (stat.status !== 0 || patch.status !== 0) {
      return { ok: false, error: patch.stderr.trim() || stat.stderr.trim() || "git diff failed" };
    }
    return {
      ok: true,
      diff: {
        patch: patch.stdout ?? "",
        diffStat: stat.stdout?.trim() ?? "",
      },
    };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

/**
 * Commit any remaining worktree changes onto the branch. Staging alone dies
 * with the worktree directory; only a commit makes the kept branch carry the
 * captured work. A clean tree succeeds without a commit.
 */
function commitRemainingWork(setup: WorktreeSetup): { ok: boolean; error?: string } {
  const add = runGit(setup.path, ["add", "-A"]);
  if (add.status !== 0) return { ok: false, error: add.stderr.trim() || "git add failed" };
  const result = spawnSync("git", ["-C", setup.path, "commit", "-m", "agent-teams: capture teammate work"], { encoding: "utf-8" });
  if (result.status === 0) return { ok: true };
  const output = `${result.stderr ?? ""}${result.stdout ?? ""}`;
  if (/nothing to commit/i.test(output)) return { ok: true };
  return { ok: false, error: output.trim() || "git commit failed" };
}

/**
 * Remove the worktree directory but keep the branch: remaining changes are
 * committed first so the captured diff stays retrievable with
 * `git diff <baseCommit>..<branch>` after cleanup. Pass `{ deleteBranch: true }`
 * for teardowns where no work was captured (a failed spawn). When the commit
 * fails in keep-branch mode the directory is PRESERVED and returned in the
 * error — removing it would destroy the only copy of the work. Errors are
 * returned rather than thrown so task completion is never blocked by cleanup
 * failure.
 */
export function cleanupWorktree(
  setup: WorktreeSetup,
  options?: { deleteBranch?: boolean },
): { ok: boolean; error?: string } {
  const errors: string[] = [];
  if (!options?.deleteBranch) {
    const commit = commitRemainingWork(setup);
    if (!commit.ok) {
      return {
        ok: false,
        error: `commit: ${commit.error}; worktree left in place at ${setup.path} so the work is not lost`,
      };
    }
  }
  const remove = runGit(setup.repoRoot, ["worktree", "remove", "--force", setup.path]);
  if (remove.status !== 0) errors.push(`worktree remove: ${remove.stderr.trim()}`);
  if (options?.deleteBranch) {
    const branch = runGit(setup.repoRoot, ["branch", "-D", setup.branch]);
    if (branch.status !== 0) errors.push(`branch delete: ${branch.stderr.trim()}`);
  }
  try {
    runGit(setup.repoRoot, ["worktree", "prune"]);
  } catch {
    // Prune is best effort.
  }
  return errors.length > 0 ? { ok: false, error: errors.join("; ") } : { ok: true };
}

/** Best-effort cleanup used when a spawn fails before the worker starts:
 *  nothing was captured, so the empty branch goes too. */
export function discardWorktree(setup: WorktreeSetup): void {
  cleanupWorktree(setup, { deleteBranch: true });
}
