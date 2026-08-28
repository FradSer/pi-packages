1. **See the current state** of the merge/rebase. Check git history, and the conflicting files.

2. **Find the primary sources** for each conflict. Understand deeply why each change was made, and what the original intent was. Read the commit messages, check the PRs, check original issues/tickets.

3. **Resolve each hunk.** Preserve both intents where possible. Where incompatible, pick the one matching the merge's stated goal and note the trade-off. Do **not** invent new behaviour. Always resolve; never `--abort`.

## CRITICAL: Preserve intent, never invent

Understand the original intent of each change before resolving it. Do **not** invent new behaviour; where intents conflict, pick the one matching the merge's stated goal and note the trade-off. Always resolve — never `--abort`.

4. Discover the project's **automated checks** and run them — typically typecheck, then tests, then format. Fix anything the merge broke.

5. **Finish the merge/rebase.** For a merge commit, use the repository's git-agent workflow rather than staging or committing directly. If rebasing, continue the rebase process until all commits are rebased.
