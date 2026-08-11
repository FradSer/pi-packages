---
name: start-hotfix
description: Begins a hotfix for a production issue using git-flow. This skill should be used when the user asks to "start a hotfix", "create hotfix branch", "fix a critical bug", "git flow hotfix start", or wants to begin a hotfix. Accepts either an explicit version or a natural-language description of the fix.
disable-model-invocation: true
---

## Workflow Execution

**Execute** the start-hotfix workflow.

Follow the pipeline in `../../references/gitflow-start-pipeline.md`:
- **Workflow Type**: `hotfix`
- **Arguments**: invocation args
