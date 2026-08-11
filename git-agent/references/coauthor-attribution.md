# Co-Author Attribution & Execution Ladder in git-agent

`git-agent` automatically handles model co-author attribution and commit generation.

## 1. Automatic Model Resolution

`git-agent` automatically inspects environment variables (`PI_MODEL`, `CLAUDE_CODE_MODEL`, `CODEX_MODEL`, `MODEL`) to infer the active model identity and attach standard `Co-Authored-By` trailers.

Manual `--co-author` flags may still be passed to override or append specific co-authors:
```bash
git-agent commit --intent "<intent>" --co-author "<co-author>"
```

To suppress co-author trailers entirely:
```bash
git-agent commit --no-attribution
```

---

## 2. Fallback Ladder (Binary Absent)

If `git-agent` binary is unavailable or fails due to network/auth issues:

1. **Auth / Gateway Retry**: Retry with `--free`:
   ```bash
   git-agent commit --free --intent "<intent>"
   ```
2. **Manual Fallback**: Execute raw `git commit` with Conventional Commits HEREDOC and prefix with `GIT_SKILL_FALLBACK=1` (required by PreToolUse hook):
   ```bash
   GIT_SKILL_FALLBACK=1 git add -A && git commit -m "$(cat <<'EOF'
   feat(scope): intent description

   Co-Authored-By: Claude <noreply@anthropic.com>
   EOF
   )"
   ```
