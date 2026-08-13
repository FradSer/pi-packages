# GitHub Pi Package

GitHub project operations with quality gates, TDD workflows, and comprehensive issue management. Native `/github` command menu — **no skill surface**.

**Version**: 0.7.6

## Installation

```bash
# published
pi install npm:@fradser/github
# or from this repo: pi install /path/to/pi-packages/packages/github
```

Workflows are invoked through the native `/github` menu (or `/github <keyword>` shorthand).

**Requirements:**
- GitHub CLI (`gh`) must be installed and authenticated
- Repository must have a GitHub remote
- Project must have lint, test, and build commands configured
- Git must support worktrees (Git 2.5+)

## Usage

Type `/github` to open the native menu:

```
GitHub workflows:
❯ 1. Create issue(s)
  2. Create pull request
  3. Resolve issue(s)
  4. Review PR
```

Shorthand — pass a workflow keyword on the command line to skip the menu:

```bash
/github create-issues "Add rate limiting"
/github create-pr Closes #456 --draft
/github resolve-issues 456
/github review-pr 123
/github review-pr https://github.com/owner/repo/pull/123 --auto-merge
```

Each selection embeds the full procedure (`procedures/*.md`) into a follow-up
message via `pi.sendUserMessage`, with reference docs under `references/`
resolved through the `{{PKG_DIR}}` placeholder. A short guidance block is
injected into the system prompt so natural-language requests ("create a PR",
"review PR #123") route straight to the procedures.

## Overview

The GitHub plugin automates GitHub operations including pull request creation, issue management, and quality validation. It ensures all PRs meet quality standards before submission and follows TDD principles with atomic commits and conventional commit formats.

**Every PR enters the review loop.** The create-pr procedure is the plugin's single PR-creating path, and it always hands off to the review-pr procedure once the PR exists. Other workflows — resolve-issues included — delegate to it rather than calling `gh pr create` themselves, so no PR can skip the quality gate or the loop:

```
create PR → baseline review → triage each comment skeptically
          → apply only verified fixes → commit + push
          → wait for the next review round
          ↺ until CI is green and every comment is triaged
          → summary + body rewrite → ask the user whether to merge
          → post-merge: prune stale head + sync main/develop
```

The loop is the default; opting out takes a deliberate act — passing `--no-monitor` to the create-pr workflow, or telling the agent directly that you only want the PR created or only want a baseline review. It is never skipped just because CI looks quiet: auto-review services and human reviewers comment on their own schedule, so a repo with no CI workflows still gets watched.

## Plugin Structure

Each workflow uses a phase-based procedure with detailed reference materials:

```
github/
├── extensions/
│   ├── menu.ts               # /github command menu + guidance injection
│   └── risky-gate.ts         # tool_call hook: model-generated option dialog for gh pr merge / worktree remove --force
├── procedures/
│   ├── create-issues.md      # Issue creation workflow (~534 tokens)
│   ├── create-pr.md          # PR creation workflow (~634 tokens)
│   ├── resolve-issues.md     # Issue resolution workflow (~591 tokens)
│   └── review-pr.md          # Review + CI/comment watch loop
├── references/
│   ├── create-issues/        # decision-logic, issue-structure, requirements
│   ├── create-pr/            # failure-resolution, pr-structure, requirements
│   ├── resolve-issues/       # requirements, workflow-details
│   ├── review-pr/            # review-loop, closeout
│   └── shared/               # auto-closing-keywords, quality-validation, ...
│       └── (symlinked from each per-workflow dir)
└── scripts/
    └── review-loop.sh        # CI/comment poll script
```

This architecture enables efficient context loading by keeping core workflows concise while providing comprehensive reference materials on demand.

## Workflows

### Create pull request

Creates comprehensive GitHub pull requests with quality validation and gates, then hands off to the review-pr workflow. This is the plugin's only PR-creating path.

**What it does:**
1. Validates repository status and GitHub authentication
2. Analyzes all commits in the branch (full history analysis)
3. Enforces atomic commits: each commit represents one complete, cohesive change
4. Runs comprehensive quality and security checks:
   - Lint validation
   - Test suite execution
   - Build verification
   - Security scanning for sensitive data
5. Validates commit messages follow conventional format:
   - **Format**: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
   - **Title**: lowercase, <50 chars, imperative mood, optional scope
   - **Body**: ≤72 chars per line, describes what and why
   - **Footer**: References issues with auto-closing keywords
6. Ensures all checks pass before PR creation
7. Creates comprehensive PR description with:
   - Summary of changes (1-3 bullet points)
   - Test plan checklist
   - Related issues and PRs
   - Quality validation status
8. Applies automated labels based on changes
9. Creates PR using GitHub CLI with proper metadata
10. Hands off to the review-pr workflow (unless `--no-monitor`)

**Usage:**
```bash
/github create-pr

# Create the PR but skip the review loop
/github create-pr --no-monitor

# Link an issue and open as draft
/github create-pr Closes #456 --draft
```

**Features:**
- **Quality gates**: All checks must pass before PR creation
- **Atomic commits**: Validates each commit is a logical unit
- **Conventional commits**: Enforces commit message standards
- **Comprehensive validation**: Lint, test, build, security
- **Auto-labeling**: Applies labels based on change types
- **Issue linking**: Automatically links related issues
- **Security scanning**: Checks for sensitive data exposure
- **Failure resolution**: Systematic process to fix issues
- **Review loop handoff**: Delegates to the review-pr workflow after creation

**Failure resolution process:**
When quality checks fail, the workflow:
1. Creates specific task lists for failures
2. Fixes issues systematically with validation
3. Re-runs checks until all pass

### Create issues

Creates GitHub issues following TDD principles with proper labels, scope, and auto-closing keywords.

**What it does:**
1. Analyzes repository context and existing issues
2. Determines issue type (epic, PR-scoped, or review issue)
3. Creates proper labels if they don't exist:
   - `priority:high` - High priority - this sprint
   - `priority:medium` - Medium priority - next sprint
   - `priority:low` - Low priority - backlog
4. Creates issues with required structure:
   - Title (≤70 chars, imperative, no emojis)
   - Proper labels
   - Detailed body with problem description
   - Acceptance criteria
   - Context and links
5. Applies auto-closing keywords for PR-scoped issues
6. Provides issue URLs and tracking information

**Usage:**
```bash
/github create-issues "Fix memory leak in auth service"
/github create-issues "Add rate limiting" "Update payment API" "Fix mobile layout"
```

**Features:**
- **TDD-first**: Follows test-driven development workflow
- **Branch-aware**: Decision tree based on current branch
- **Proper labeling**: Automatic label assignment
- **Scope determination**: Epic vs PR-scoped issues
- **Auto-closing**: Uses keywords (Closes, Fixes, Resolves)
- **Structured format**: Consistent issue templates

**Branch-based decision logic:**
- **On main/develop**: Create issue directly
- **On PR branch**: Ask "Must this be fixed before merge?" directly in the conversation
  - **Yes**: Comment in PR with detailed context
  - **No**: Create new issue for later with justification

**Issue types:**
1. **Epic issues**: Multi-PR initiatives (no auto-close keywords)
2. **PR-scoped issues**: Single PR resolution (use auto-close keywords)
3. **Review issues**: Non-blocking feedback from PR reviews

### Resolve issues

Resolves GitHub issues using isolated worktrees and TDD workflow with comprehensive quality validation.

**What it does:**
1. **Issue Selection**: Evaluates open issues and prioritizes next actionable item
2. **Worktree Setup**: Creates or reuses isolated worktree with descriptive branch name
3. **TDD Implementation**:
   - Plan implementation and assess architectural impact
   - Write failing tests (red phase)
   - Implement fixes
   - Refactor while keeping tests green
4. **Quality Validation**: Runs project-specific lint, test, and build commands for fast local feedback
5. **PR Creation**: Pushes the branch, then delegates to the create-pr workflow with the issue reference — which runs the authoritative quality gate and enters the review-pr loop. This workflow does not resume inline; the review-pr workflow owns the PR through merge, the post-merge worktree removal, and the switch/sync to `main`.
6. **Cleanup** (fallback only): The review-pr closeout removes the linked worktree and syncs `main` after a merge. This step runs only if that cleanup was skipped (e.g. "Don't merge", an interrupt, or a fresh session) — verify `git worktree list` first and `git worktree remove` on the `.pi/worktrees/` path only if the worktree persists

**Usage:**
```bash
/github resolve-issues
/github resolve-issues 456
```

**Features:**
- **Isolated worktrees**: Clean environment for each issue
- **TDD workflow**: Red → Green → Refactor cycle
- **Quality gates**: All checks must pass
- **Review loop**: Reaches the review-pr workflow via create-pr
- **Auto-cleanup**: review-pr closeout removes the worktree and syncs `main` after merge
- **Documentation**: Tracks all decisions and actions

### Review PR

Reviews a PR, then keeps a persistent watch over CI results and incoming reviewer comments until the PR settles. Reached automatically from the create-pr workflow; also usable standalone on any existing PR.

**What it does:**
1. Runs its own baseline review of the PR diff via an independent agent, treating the findings as the first comment batch
2. Launches one persistent background bash poll via `scripts/review-loop.sh` (bundled in the `@fradser/github` package — resolve from installed copy or `settings.json` relative-path checkout) polling CI and new comments, with the interval sized to the PR
3. On each event:
   - **CI failure** → fetches logs, fixes, commits + pushes (stops and reports for auth, secret, flaky, or infra failures)
   - **New comments** → spawns an independent skeptical triage agent with a clean context, which returns `fix` / `reject <reason>` / `escalate` per comment
4. Applies only the `fix` verdicts, replies to rejections, notifies on escalations
5. Commits + pushes each round, which triggers fresh CI that the same poll script re-emits — the loop continues
6. Hides resolved comments and resolves their threads
7. Once CI is green and every comment is triaged: asks the user in the conversation whether to merge and waits for the reply, then posts a summary comment, rewrites the PR body to link it
8. After merge: removes the linked worktree, cleans up the head branch when safe, switches to `main`, syncs `main`/`develop`, prunes stale locals

**Usage:**
```bash
/github review-pr 123
/github review-pr https://github.com/owner/repo/pull/123
/github review-pr 123 --auto-merge
```

**Features:**
- **Skeptical triage**: Comments are suggestions to consider, not orders — rejecting noise is the expected outcome
- **Independent context**: The triage agent never sees the authoring context, so it can't rationalize the diff
- **Persistent watch**: Survives across turns; a quiet comment queue is not a stop signal
- **Never auto-merges**: Merging always requires an explicit user choice
- **Post-merge hygiene**: Worktree removal + head cleanup + switch to `main` + sync `main`/`develop`

## Best Practices

### Create PR
- **Quality-first**: All checks must pass before PR creation
- **Atomic commits**: Each commit should be a logical unit
- **Conventional format**: Follow commit message standards
- **Small PRs**: Easier to review and merge
- **Issue linking**: Reference issues in commits for auto-closing
- **Review the PR**: Verify description accuracy before submission

### Create issues
- **Clear descriptions**: Provide specific problem statements
- **Acceptance criteria**: Define measurable completion conditions
- **TDD workflow**: Create issues before implementation
- **Proper scoping**: Distinguish between epics and PR-scoped issues
- **Label consistently**: Use priority and type labels
- **Link related items**: Connect issues to related work

### Resolve issues
- **Select wisely**: Prioritize the next actionable issue
- **Follow TDD**: Write tests before implementation
- **Use worktrees**: Keep environments isolated
- **Quality gates**: All checks must pass before PR
- **Clean up**: Remove worktrees after merge
- **Document**: Track decisions and lessons learned

## Workflow Integration

### Complete development workflow:
```bash
# 1. Create issue for feature
/github create-issues "Add OAuth authentication"

# 2. Resolve the issue
/github resolve-issues
# - Select the OAuth issue
# - Work in isolated worktree
# - Follow TDD cycle
# - Delegate to create-pr when complete

# 3. Or manual development — commit via your installed commit workflow

# 4. Create PR with quality gates
/github create-pr
# - All checks pass
# - PR description generated
# - Issues linked automatically

# 5. The review loop runs automatically from step 2 or 4
# - Baseline review, then watches CI and reviewer comments
# - Triages each comment, fixes what's verified, pushes
# - Repeats until CI is green and no comments remain
# - Asks whether to merge
```

Steps 2 and 4 both funnel through create-pr → review-pr, so no PR opens and gets walked away from unless you explicitly opt out.

## Requirements

- GitHub CLI (`gh`) must be installed
- GitHub CLI must be authenticated: `gh auth login`
- Repository must have a GitHub remote named `origin`
- Project must have configured lint, test, and build commands
- Git version 2.5+ for worktree support

## Troubleshooting

### create-pr fails quality checks

**Issue**: Lint, test, build, or security checks fail

**Solution**:
- Review failure output carefully
- Fix all issues systematically
- Re-run `/github create-pr` after all fixes
- Consider splitting large PRs if too many issues

### GitHub CLI not authenticated

**Issue**: `gh` commands fail with authentication error

**Solution**:
- Install GitHub CLI: `brew install gh` (macOS) or see [GitHub CLI installation](https://cli.github.com/)
- Authenticate: `gh auth login`
- Select appropriate authentication method
- Verify with: `gh auth status`
- Ensure repository remote: `git remote -v`

### PR description is incomplete

**Issue**: PR description missing context or details

**Solution**:
- Ensure commits follow conventional format
- Write descriptive commit messages
- Reference issues in commit messages
- Manually edit PR after creation if needed
- Check full commit history for context

### Worktree operations fail

**Issue**: `git worktree` commands fail

**Solution**:
- Update Git to version 2.5+
- Check worktree list: `git worktree list`
- Remove orphaned worktrees: `git worktree remove <path>`
- Clean up with: `git worktree prune`
- Ensure sufficient disk space

### Issue auto-closing doesn't work

**Issue**: Merged PR doesn't close linked issues

**Solution**:
- Use correct keywords: Closes, Fixes, Resolves
- Reference issue in PR or commit message
- Check GitHub repository permissions
- Verify issue exists and is open
- Manually close if needed and update process

## Safety Features

- **Protected branches**: Enforces PR workflow for main/develop
- **Quality gates**: All checks must pass before PR creation
- **Security scanning**: Detects sensitive data before commits
- **Atomic commits**: Validates each commit is a logical unit
- **Worktree isolation**: Prevents repository corruption
- **Atomic PR creation**: Either all succeeds or all fails

## Key Principles

- **TDD-First**: Test → Code → Refactor Cycle
- **Quality Gates**: All checks pass before PR
- **Atomic Commits**: One logical change per commit
- **Issue-Driven**: Work from well-defined issues
- **Collaborative**: Multi-agent review and validation
- **Clean Workflow**: Isolated worktrees, automated cleanup

## Author

Frad LEE (fradser@gmail.com)

## License

MIT
