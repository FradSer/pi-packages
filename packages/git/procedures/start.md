# GitFlow — Start procedure

> **Inline procedure.** Embedded verbatim into the follow-up message by the
> `/git` menu ("Start feature / hotfix / release") via `pi.sendUserMessage` —
> it is not a skill. `{{PKG_DIR}}` is substituted with the package dir and
> `{{WORKFLOW_TYPE}}` with the branch type at send time.

## Workflow Execution

**Execute** the `{{WORKFLOW_TYPE}}` start workflow.

Follow the pipeline in `{{PKG_DIR}}/references/gitflow-start-pipeline.md`:
- **Workflow Type**: `{{WORKFLOW_TYPE}}`
- **Arguments**: invocation args (may be empty — Full-Auto Inference applies)
