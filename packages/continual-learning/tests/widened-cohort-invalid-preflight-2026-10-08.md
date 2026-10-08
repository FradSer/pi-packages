# Widened cohort invalid preflight, run stamp 20261008T101546Z

This run is rejected, not superseded. It did not implement the protocol it claims.

## Defect

`tests/docker_experiment.py` selected a per-project fixture file from
`PI_FIXED_MEMORIES_DIR` and wrote it into the container's agent configuration, but
it exported the seam environment variable `PI_FIXED_MEMORIES` only when
`PI_FIXED_MEMORIES_SOURCE` was set. With the directory alone, the extension never
saw the seam, so every arm ran the generator's own plan instead of the fixed one.

## Evidence

The Memory record names in the arms are the generator's, not the fixture's. The
fixture proposes `personal_report_preference.md`, `project_test_command.md` and
`build_workflow.md`. The `itsdangerous-off` arm wrote
`report_finish_preference.md` and `test_command.md`; other arms wrote
`no_git_push_policy.md`, `project_verification_rules.md` and `report_signoff.md`.

## Consequence

Per-project attribution requires one identical raw plan in both arms. This run has
none, so its off and on arms differ in the plan as well as the judge. Every count
from it is unattributable, and the fabricated marker `make build` appears in no arm
because the fixture that carries it never reached the pipeline.

## Decision

Record the counts as an invalid preflight, fix the environment condition, and run
the protocol again at one fixed revision. The arms are not rerun to improve a
result; they are rerun because they did not implement the pre-registered
configuration. The one observation that survives is that both cohorts finished with
0 of 6 projects passing, which is a property of that unattributable configuration.

## Kept for the record

Both cohort summaries, all twelve arm directories, and the absent-SDK arm
directories stay in place under
`~/.cache/pi-continual-learning/docker/20261008T101546Z-*`. Nothing was deleted and
no number was edited.
