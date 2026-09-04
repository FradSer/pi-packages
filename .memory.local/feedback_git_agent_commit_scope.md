---
name: git-agent-commit-scope
description: Bare git-agent is the default autonomous workflow; explicit git-agent commit auto-stages the whole dirty tree, so scope it with exact staging plus --no-stage
type: feedback
---

`git-agent commit` without `--no-stage` auto-stages **every** uncommitted change in the repo and packs them into one commit, even when they belong to unrelated packages or leftover work. Observed behavior: when no scope covers the changed dirs, everything lands in a single commit.

**Why:**
Discovered when committing teammate work: the first auto-stage run swept 27 unrelated files (code-context, github, git, memory, utils, lark) into the teammate commit, producing a non-atomic commit that had to be `git reset --soft HEAD~1` and redone.

**How to apply:**
1. When committing a subset of the tree, stage exactly the target paths first, then commit with `--no-stage`: `git add <paths> && git-agent commit --no-stage --intent "..."`.
2. The validate-commit extension blocks bare `git add`, but allows the chain above (it checks for `git-agent commit` in the same command). Put the `git add` and `git-agent commit` in one bash invocation.
3. After the commit, verify scope with `git show --stat HEAD` — it must list only the intended files.
4. To fix an over-broad commit: `git reset --soft HEAD~1`, `git restore --staged <unrelated paths>`, then re-commit the remaining staged files with `--no-stage`.
5. **Hunk-level partial staging gets silently expanded to full worktree content** (2026-08-23, commit 47bf7bc): with another session concurrently editing the same repo, `git apply --cached` of selected hunks plus `git-agent commit --no-stage` still landed the FULL worktree diff for those two partially-staged files (+365/53 instead of +161/14). `--no-stage` leaves fully-unstaged files alone but "completes" files whose index diverges from their worktree. Remedy that worked: soft-reset, rebuild exact staging (full adds for pure files + cached hunk patch), then `cp` the two shared files' worktree versions aside, `git checkout-index -f` them so worktree == index, chain everything including the commit in one command, and `cp` the saved versions back after — leaving the concurrent session's remainder unstaged on top of the new HEAD.

**Related:** [[git-agent-session-context]] [[pi-package-conventions]]
