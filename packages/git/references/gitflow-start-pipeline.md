# GitFlow Start Pipeline Reference

Shared pipeline for starting GitFlow branches (`feature`, `hotfix`, `release`).

## Pre-flight Invariants

CRITICAL: Verify working tree is clean (`git status --porcelain` is empty) before starting. Abort if dirty. See `invariants.md`.

---

## Phase 0: Resolve Target Branch Name or Version

Arguments (`invocation args`) are **optional**. If `invocation args` is empty or omitted, activate **Full-Auto Inference**:

### 1. Feature (`feature`)
- Turn `invocation args` into a concrete branch slug `NAME`:
  1. If `invocation args` is empty, auto-derive `NAME` from recent conversation topic, task description, or `git diff` / uncommitted context. If the derivation is ambiguous (no clear topic, or multiple plausible names), **call the `git_ask_name` tool** (`purpose: "feature"`, `default: <your best derivation>`) instead of guessing — a wrong branch name is cheaper to avoid than to rename.
  2. If `invocation args` is already a slug (lowercase, hyphen-separated, no spaces), use it directly.
  3. Otherwise, derive a concise kebab-case `NAME` (lowercase, words joined by hyphens, drop filler words, ≤5 words).
  4. Report: "Resolved feature branch: feature/<NAME> (from: invocation args)."

### 2. Hotfix (`hotfix`)
- Turn `invocation args` into a concrete next version `TARGET`:
  1. Get latest tag: `git tag --sort=-v:refname | head -1` (strip `v`). If no tags exist, treat latest as `0.0.0`.
  2. If `invocation args` is empty or a natural-language description, auto-bump the **patch** component of the latest tag (`x.y.Z+1`) — hotfixes are patch-level fixes by definition. If the natural-language description conflicts with the tag-derived bump (e.g. "minor hotfix"), **call `git_ask_name`** (`purpose: "hotfix"`, `default: <auto-bumped>`) to confirm the target.
  3. If `invocation args` is semver (`^v?\d+\.\d+\.\d+$`), use it directly as `TARGET`.
  4. Abort if `TARGET` is not strictly greater than the latest tag.
  5. Report: "Resolved hotfix version: <TARGET> (from: invocation args)."

### 3. Release (`release`)
- Turn `invocation args` into a concrete target version `TARGET`:
  1. Get latest tag: `git tag --sort=-v:refname | head -1` (strip `v`). If no tags exist, treat latest as `0.0.0`.
  2. If `invocation args` is semver (`^v?\d+\.\d+\.\d+$`), use it directly as `TARGET`.
  3. If `invocation args` is empty or a natural-language description, analyze commits since latest tag (`git log <latest-tag>..develop --oneline`) and choose bump:
     - **major** (X+1.0.0): breaking/incompatible changes.
     - **minor** (x.Y+1.0): new features/enhancements (default).
     - **patch** (x.y.Z+1): bug fixes only.
     If the commit analysis is ambiguous (mixed breaking/feature/bugfix signals), **call `git_ask_name`** (`purpose: "release"`, `default: <auto-chosen>`) so the bump level is the user's call.
  4. Abort if `TARGET` is not strictly greater than the latest tag.
  5. Report: "Resolved release version: <TARGET> (from: invocation args)."

---

## Phase 1: Start GitFlow Branch & Version Bump

1. Execute git-flow start command:
   ```bash
   git flow <type> start <NAME_OR_TARGET>
   ```
2. For `hotfix` and `release`:
   - Update project version files (`package.json`, `Cargo.toml`, `pyproject.toml`, `VERSION`, etc.) to `<TARGET>`.
   - Commit via the `/commit` skill with intent `chore: bump version to <TARGET>`.
3. Push branch to remote:
   ```bash
   git push -u origin <type>/<NAME_OR_TARGET>
   ```