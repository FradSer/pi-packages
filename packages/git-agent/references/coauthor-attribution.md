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
