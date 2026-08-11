---
name: start-release
description: Begins a new version release using git-flow. This skill should be used when the user asks to "start a release", "create release branch", "prepare a release", "git flow release start", or wants to begin a new version release. Accepts either an explicit version or a natural-language description of the release.
disable-model-invocation: true
---

## Workflow Execution

**Execute** the start-release workflow.

Follow the pipeline in `../../references/gitflow-start-pipeline.md`:
- **Workflow Type**: `release`
- **Arguments**: invocation args
