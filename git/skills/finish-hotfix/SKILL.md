---
name: finish-hotfix
description: Finalizes a hotfix and merges it into main and develop using git-flow, then prunes stale branches and worktrees. This skill should be used when the user asks to "finish a hotfix", "merge hotfix branch", "complete hotfix", "git flow hotfix finish", or wants to finalize a hotfix.
disable-model-invocation: true
---

## Workflow Execution

**Execute** the finish-hotfix workflow.

Follow the pipeline in `../../references/gitflow-finish-pipeline.md`:
- **Workflow Type**: `hotfix`
- **Arguments**: invocation args
