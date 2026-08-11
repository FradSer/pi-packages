# Co-Author Attribution & Standard Commit Reference

Standard Git commit and co-author rules for GitFlow operations in the `git` package.

## 1. Conventional Commit Format

When committing version bumps, changelog updates, or branch changes, use standard Conventional Commits syntax:

```bash
git commit -m "<type>(<scope>): <short description>"
```

Common types:
- `chore`: version bumps, configuration updates
- `docs`: changelog updates, documentation changes
- `feat`: new features
- `fix`: bug fixes

## 2. Co-Author Attribution

If a co-author trailer is requested by user prompt or environment configuration, append standard `Co-Authored-By` footers using multi-line HEREDOC format:

```bash
git commit -m "$(cat <<'EOF'
<type>(<scope>): <description>

Co-Authored-By: Name <email>
EOF
)"
```
