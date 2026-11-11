---
name: "project_github_actions_run_step_diagnosis.md"
description: "Workflow-run log download returned 403 'Must have admin rights to Repository' while the run's jobs endpoint exposed per-step conclusions; `git push` over SSH succeeded while `gh auth status` reported the default token invalid."
type: project
---
Observed: a workflow-run log download for run 43067575895 returned HTTP 403 with message `Must have admin rights to Repository.`, while the run's jobs endpoint returned the `release` job's per-step status and conclusion: step 10 `Run quality gate` completed failure, and steps 11 `Create Release Pull Request or Publish` and 12 `Retry publishing versioned packages` were skipped.

Conditions: `gh auth status` reported `X Failed to log in to github.com account FradSer (default)` and `The token in default is invalid`, while `git push origin main` over SSH succeeded (`1d3321e5..3a955990  main -> main`).

The repository API record reported `"private": false`, so repository visibility does not explain the 403; whether the denial comes from the invalid token or from missing admin rights is unresolved in this evidence.

How to apply: when a release run fails and its logs cannot be downloaded, read the jobs endpoint's per-step `status`/`conclusion` to find the failing step and the skipped publish steps before changing publish or trust configuration.