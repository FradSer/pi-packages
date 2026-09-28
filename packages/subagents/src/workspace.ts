/**
 * Durable per-Agent workspaces.
 *
 * Pi stores sessions under `~/.pi/agent/sessions/`, grouped by working
 * directory, and `--continue` opens the most recent session for the current
 * working directory. The working path is therefore the memory key: a stable
 * workspace per Agent is what makes Pi's own session storage usable as that
 * Agent's working memory, with Pi's compaction, branching, `/resume` picker, and
 * `/export` doing the work a bespoke scheme would have to rebuild.
 *
 * This is why a workspace is durable and per-Agent rather than per-task and
 * disposable. The previous per-task worktree was removed on completion, which
 * orphaned its session group every task — fragmentation that looks like amnesia
 * and also accumulates storage without bound.
 *
 * Layout: `~/.pi/agent/workspaces/<agent>/<project-slug>/`, a linked worktree of
 * the project repository. User scope rather than `<repo>/.pi/worktrees/` because
 * a cross-project Agent needs one home per project, and because durable state
 * does not belong inside a checkout. Durability also amortizes provisioning:
 * `node_modules`, virtualenvs, and build caches are paid once per workspace.
 *
 * Isolation of writes is a separate layer. A worktree separates the filesystem;
 * it does not confine what a `bash` grant can touch. Kernel write confinement is
 * the sandbox-profile layer and is not implemented here — see
 * docs/spec-agent-teams-three-package-split.md.
 */

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { getAgentDir } from "@earendil-works/pi-coding-agent";
import { safeFileName } from "@fradser/pi-kit";

export type WorkspaceIsolation = "isolated" | "shared";

export interface AgentWorkspace {
  /** Working directory handed to the child. */
  cwd: string;
  /** Whether the child got its own linked worktree. */
  isolation: "worktree" | "none";
  /** True when an existing workspace was reused rather than created. Reuse is
   * the normal case and is what preserves working memory. */
  reused: boolean;
  /** Branch backing an isolated workspace. */
  branch?: string;
  /** Repository the workspace is linked to. */
  repoRoot?: string;
  /** Why isolation was unavailable, when it was requested. Surfaced rather than
   * silently sharing the leader's tree. */
  reason?: string;
}

/** Root of all durable Agent workspaces. */
export function workspacesRoot(): string {
  return path.join(getAgentDir(), "workspaces");
}

/** A stable, filesystem-safe slug for one project, so the same repository always
 * resolves to the same workspace and therefore the same Pi session group. */
export function projectSlug(cwd: string): string {
  const resolved = safeRealpath(cwd);
  const readable = resolved
    .replace(/^[/\\]/, "")
    .replace(/[/\\:]+/g, "-")
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .slice(-120);
  // A readable suffix alone can collide across machines and mounts, so the hash
  // is what actually distinguishes two projects; the readable part is for humans.
  const digest = createHash("sha256").update(resolved).digest("hex").slice(0, 12);
  return `${readable || "project"}-${digest}`;
}

function safeRealpath(candidate: string): string {
  try {
    return fs.realpathSync(candidate);
  } catch {
    return path.resolve(candidate);
  }
}

/** The durable workspace path for one Agent in one project. */
export function agentWorkspacePath(agentName: string, cwd: string): string {
  return path.join(workspacesRoot(), safeFileName(agentName), projectSlug(cwd));
}

function runGit(cwd: string, args: string[]): { status: number | null; stdout: string; stderr: string } {
  const result = spawnSync("git", ["-C", cwd, ...args], { encoding: "utf-8" });
  return { status: result.status, stdout: result.stdout ?? "", stderr: result.stderr ?? "" };
}

/** Whether an existing directory is still a usable linked worktree. A workspace
 * whose repository was moved or pruned must be reported, not silently reused as
 * an ordinary directory that happens to have stale files. */
function isUsableWorktree(candidate: string): boolean {
  if (!fs.existsSync(path.join(candidate, ".git"))) return false;
  return runGit(candidate, ["rev-parse", "--is-inside-work-tree"]).status === 0;
}

/**
 * Resolve one Agent's durable workspace, creating it on first use.
 *
 * Falls back to the caller's cwd when isolation is impossible — a non-repository
 * working directory, or a repository with no commit to branch from — and says so
 * in `reason` rather than pretending the child is isolated.
 */
export function ensureAgentWorkspace(input: {
  agentName: string;
  cwd: string;
  isolation: WorkspaceIsolation;
}): AgentWorkspace {
  const shared = (reason?: string): AgentWorkspace => ({
    cwd: input.cwd,
    isolation: "none",
    reused: false,
    ...(reason ? { reason } : {}),
  });
  if (input.isolation === "shared") return shared();

  const target = agentWorkspacePath(input.agentName, input.cwd);
  if (isUsableWorktree(target)) {
    const branch = runGit(target, ["rev-parse", "--abbrev-ref", "HEAD"]).stdout.trim();
    const repoRoot = runGit(target, ["rev-parse", "--git-common-dir"]).stdout.trim();
    return {
      cwd: target,
      isolation: "worktree",
      reused: true,
      ...(branch ? { branch } : {}),
      ...(repoRoot ? { repoRoot: safeRealpath(path.resolve(target, repoRoot, "..")) } : {}),
    };
  }

  const toplevel = runGit(input.cwd, ["rev-parse", "--show-toplevel"]);
  if (toplevel.status !== 0) return shared("the working directory is not a git repository");
  const repoRoot = toplevel.stdout.trim();
  const head = runGit(repoRoot, ["rev-parse", "HEAD"]);
  if (head.status !== 0 || !head.stdout.trim()) {
    return shared("the repository has no commit to branch from");
  }

  const branch = `agent/${input.agentName}`;
  fs.mkdirSync(path.dirname(target), { recursive: true });
  // A durable branch means the Agent's workspace has continuity across attempts.
  // Reattach when it already exists; otherwise create it from the current HEAD.
  const branchExists = runGit(repoRoot, ["rev-parse", "--verify", `refs/heads/${branch}`]).status === 0;
  const add = branchExists
    ? runGit(repoRoot, ["worktree", "add", target, branch])
    : runGit(repoRoot, ["worktree", "add", target, "-b", branch, "HEAD"]);
  if (add.status !== 0) {
    return shared(
      `a linked worktree could not be created at ${target}: ${(add.stderr || add.stdout).trim()}`,
    );
  }
  return { cwd: target, isolation: "worktree", reused: false, branch, repoRoot: safeRealpath(repoRoot) };
}

/**
 * Explicitly retire one Agent workspace. Never called on completion: a durable
 * workspace is the Agent's home and its Pi session group, and deleting it would
 * destroy working memory.
 *
 * The directory is removed only after its work is committed to the branch, so
 * the record survives. A commit failure preserves the directory and reports it,
 * because removing it would destroy the only copy of the work.
 */
export function releaseAgentWorkspace(input: {
  agentName: string;
  cwd: string;
}): { ok: true; committed: boolean } | { ok: false; error: string } {
  const target = agentWorkspacePath(input.agentName, input.cwd);
  if (!isUsableWorktree(target)) {
    fs.rmSync(target, { recursive: true, force: true });
    return { ok: true, committed: false };
  }
  runGit(target, ["add", "-A"]);
  const commit = runGit(target, ["commit", "-m", `agent(${input.agentName}): preserve workspace before release`]);
  const committed = commit.status === 0;
  if (!committed && !/nothing to commit/i.test(`${commit.stderr ?? ""}${commit.stdout ?? ""}`)) {
    return {
      ok: false,
      error: `commit failed: ${(commit.stderr || commit.stdout).trim()}; workspace left in place at ${target} so the work is not lost`,
    };
  }
  const commonDir = runGit(target, ["rev-parse", "--git-common-dir"]).stdout.trim();
  const repoRoot = commonDir ? safeRealpath(path.resolve(target, commonDir, "..")) : undefined;
  const remove = repoRoot ? runGit(repoRoot, ["worktree", "remove", "--force", target]) : { status: 1, stderr: "unknown repository root", stdout: "" };
  if (remove.status !== 0) {
    return { ok: false, error: `worktree remove failed: ${(remove.stderr || remove.stdout).trim()}` };
  }
  if (repoRoot) runGit(repoRoot, ["worktree", "prune"]);
  return { ok: true, committed };
}

/**
 * Preserve a durable workspace at the end of an attempt: commit whatever is
 * uncommitted onto the Agent's branch and leave the directory in place.
 *
 * This is the opposite of `releaseAgentWorkspace` and is what completion calls.
 * Removing the directory would destroy the Agent's Pi session group, which is its
 * working memory, so completion never removes anything. Committing first means an
 * interrupted or crashed attempt still leaves its work retrievable on the branch.
 */
export function preserveAgentWorkspace(input: {
  agentName: string;
  cwd: string;
}): { ok: true; committed: boolean; branch?: string } | { ok: false; error: string } {
  if (!isUsableWorktree(input.cwd)) {
    return { ok: true, committed: false };
  }
  const branch = runGit(input.cwd, ["rev-parse", "--abbrev-ref", "HEAD"]).stdout.trim() || undefined;
  runGit(input.cwd, ["add", "-A"]);
  const commit = runGit(input.cwd, [
    "commit",
    "-m",
    `agent(${input.agentName}): preserve attempt output`,
  ]);
  const output = `${commit.stderr ?? ""}${commit.stdout ?? ""}`;
  if (commit.status === 0) return { ok: true, committed: true, ...(branch ? { branch } : {}) };
  if (/nothing to commit/i.test(output)) return { ok: true, committed: false, ...(branch ? { branch } : {}) };
  return {
    ok: false,
    error: `commit failed: ${output.trim()}; the workspace stays at ${input.cwd} so nothing is lost`,
  };
}
