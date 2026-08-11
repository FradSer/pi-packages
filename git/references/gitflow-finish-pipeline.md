# GitFlow Finish Pipeline Reference

Shared 6-Phase pipeline for finishing GitFlow branches (`feature`, `hotfix`, `release`).

## Pre-flight Invariants

CRITICAL:
- Verify working tree is clean (`git status --porcelain` is empty) before finishing.
- Verify current branch matches `<type>/*` before finishing — wrong branch type merges to the wrong parent.
See `invariants.md`.

---

## Phase 1: Identify Target Name / Version

1. If `invocation args` is provided, use it as the target name or version (strip any leading `v` for versions).
2. Otherwise, extract from current branch: `git branch --show-current` (strip `<type>/` prefix and any leading `v`).
3. Store clean identifier `$NAME` or `$VERSION` (e.g. `dark-mode` or `1.2.0`).

## Phase 2: Pre-finish Checks

1. Identify project test commands (check `package.json`, `Cargo.toml`, `Makefile`, `pyproject.toml`, etc.).
2. Run test suite. **Abort immediately if tests fail.**

## Phase 3: Update Changelog

1. Get previous tag: `git tag --sort=-v:refname | head -1`.
2. Collect commits per `changelog-generation.md`.
3. Update `CHANGELOG.md` per `../examples/changelog.md`.
4. Commit via the `/commit` skill with intent `docs: update changelog for $NAME`.

## Phase 4: Execute GitFlow Finish & Push

### Feature (`feature`)
```bash
git flow feature finish $NAME
git push origin develop
```

### Hotfix (`hotfix`) & Release (`release`)
```bash
git flow <type> finish $VERSION --tagname "v$VERSION" -m "Release v$VERSION"
git push origin main develop --tags
```

## Phase 5: Post-Finish Workflow Finalization

1. **GitHub Release** (Release only):
   Extract changelog section for `v$VERSION` and publish via GitHub CLI:
   ```bash
   gh release create "v$VERSION" --title "v$VERSION" --notes "<changelog-section>" --verify-tag
   ```
2. **Switch Back to Develop** (Hotfix & Release):
   `git-flow-next` leaves the repository on `main` after finishing a hotfix or release. Return to `develop`:
   ```bash
   git checkout develop && git pull origin develop
   ```

## Phase 6: Workspace & Remote Cleanup

Reclaim stale branches and worktrees per `cleanup.md`:
1. `git fetch --prune`
2. `git worktree prune` (and surface survivors with `git worktree list`)
3. Confirm `<type>/$NAME` is deleted locally and on `origin`. Delete explicitly if a ref survived.
4. Sweep any leftover merged `feature/*`, `hotfix/*`, or `release/*` branches.