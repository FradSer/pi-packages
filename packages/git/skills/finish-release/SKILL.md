---
name: finish-release
description: Finalizes a release and merges it into main and develop with a tag using git-flow, then prunes stale branches and worktrees. This skill should be used when the user asks to "finish a release", "merge release branch", "complete release", "git flow release finish", or wants to finalize a release.
disable-model-invocation: true
---

## Workflow Execution

**Execute** the finish-release workflow.

Follow the pipeline in `../../references/gitflow-finish-pipeline.md`:
- **Workflow Type**: `release`
- **Arguments**: invocation args
