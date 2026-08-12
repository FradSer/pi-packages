# git-agent CLI Reference

Detailed command reference for `git-agent`.

## Core Commands

### 1. `git-agent commit`
Generates and creates atomic AI commits from repository changes.

```bash
# Basic invocation (auto-stages changes and splits into up to 5 atomic commits)
git-agent commit

# Specify intent
git-agent commit --intent "refactor auth token handling"

# Pre-staged files only (skip auto-staging)
git add src/auth.ts && git-agent commit --no-stage --intent "update auth token"

# Override model or gateway
git-agent commit --model claude-3-5-sonnet
git-agent commit --free

# Add custom trailers or co-authors
git-agent commit --co-author "Alice <alice@example.com>"
git-agent commit --trailer "Ticket: #123"
```

### 2. `git-agent related`
Query historical co-change relationships from git commit history. Read-only and offline.

```bash
# Query files that historically change together with specified file(s)
git-agent related src/components/Header.tsx

# Query test files related to specified file(s)
git-agent related --tests src/components/Header.tsx

# JSON output for tooling
git-agent related -o json src/components/Header.tsx
```

### 3. `git-agent init`
Initialize or optimize repository scopes and `.gitignore`.

```bash
# Re-derive commit scopes from git history
git-agent init --scope --force

# Re-derive .gitignore while preserving custom rules
git-agent init --gitignore
```

### 4. `git-agent status`
Check co-change index health (indexed commits, row count, database size). Read-only and offline.

```bash
git-agent status
```

---

## Configuration Precedence

1. CLI Flags (`--api-key`, `--model`, `--base-url`, `--free`, `--co-author`)
2. Agent Session Environment Variables (`PI_MODEL`, `CLAUDE_CODE_MODEL`, `CODEX_MODEL`, `MODEL`)
3. Git config (`git config --local git-agent.model`)
4. Global Config (`~/.config/git-agent/config.yml`)
5. Free Shared-Gateway Default (`--free` ignores config files and forces the free gateway)
