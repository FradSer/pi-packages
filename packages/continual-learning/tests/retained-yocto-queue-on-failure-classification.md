# Retained yocto-queue-on failure: classification and unrun-arm account

Checked on 2026-10-07 by the successor session. All inspection was read-only.
No retained artifact, container, or frozen result was modified.

## Subject

Run root: `~/.cache/pi-continual-learning/docker/20261007T025657Z`.
Retained on-arm copy: `.../20261007T025657Z/handoff-retained-yocto-queue-on/`.
Command shape: `--cohort heldout --jev paired --memory-policy composed --jobs 1`.
Fixed source digest: `1af9118d7857e81542410e5f44dde74c2ba233cdc1baa6cbc6ed4d7d360758c0`.

## Integrity of the retained material

| Artifact | SHA256 | Handoff value | Match |
| --- | --- | --- | --- |
| `handoff-retained-yocto-queue-on/report.json` | `2bbf0a3df4172a7a334c6d464024c795b592584aecbc3950c7293c58516c1555` | `2bbf0a3d…c1555` | yes |
| `handoff-retained-yocto-queue-on/failure.txt` | `10d4a661a17120746466d39890cd5fa8fbef49cb8077fd5be32fb96b19e1f3b0` | not given | n/a |
| `yocto-queue-off/report.json` | `22bf43308550509a57708f4e67312f9a5bede72eb4399bf68194164d00b47f81` | `22bf4330…7f81` | yes |

The on-arm host directory `yocto-queue-on/` holds zero files. The complete
container-side results were copied later into `handoff-retained-yocto-queue-on/`.

## What the recorded failure is

The learning phase succeeded. `learning-session.jsonl` has 15 records. The
agent added one regression test to `test.js` and ran `pnpm test` as a
standalone invocation. The tool result shows 8 tests passed.
`report.json` records `checks.learningCommandNativeSuccess: true` and
`checks.regressionChanged: true`, and `independent-check.json` shows exit 0.

The consolidation phase failed. The parent receipt
`memory/runs/--work-yocto-queue--/learning-pipeline-receipt.json` records:

- `attempts[0]` selector, `outcome: applied`, 4 ms, 0 operations,
  diagnostic `empty Memory index; parent-routed explicit evidence`.
- `attempts[1]` memory, `outcome: failed`, `durationMs: 26984`,
  `operations: 0`, and no diagnostic or reason field.
- `totals` all zero, `usageAvailable: false`, `costAvailable: false`.

`report.json` then records `phaseObservations.memory.failedCheck:
"missing-supported-memory-judgment"`, `recall` unverified with reason
`memory-prerequisite-failed`, and `harness` failed with
`failedCheck: "phase-callback-error"`. `jevJudgments` is `[]`.
`failure.txt` traces the assert to `live_docker_projects.py:232` by way of
`live_docker_projects.py:404`.

## Cause 1 (primary): main-model transport failure in the generator child

The candidate generator is a real model child under
`memory/runs/--work-yocto-queue--/run_muxj3apt_04a4b8187e38ec86/`. Its
`stdout.jsonl` ends as follows, with provider `cli-proxy` and model
`opencode/deepseek-v4.1-flash`:

1. The model emits a thinking block that analyzes the task slice for durable
   knowledge and lists the private preference and the no-push constraint.
2. `{"type":"auto_retry_start","attempt":1,"maxAttempts":3,"delayMs":2000,
   "errorMessage":"Stream ended without finish_reason"}`
3. Three `agent_end` records with `"content":[]`, `stopReason: "error"`,
   `errorMessage: "Connection error."`, and zero usage.
4. `{"type":"auto_retry_end","success":false,"attempt":3,
   "finalError":"Connection error."}` followed by `agent_settled`.

The child produced no candidate. No candidate means no Jev request, because a
candidate must pass the structural and frozen-citation checks before any Jev
judgment. The receipt agrees: 0 operations, zero usage, empty `jevJudgments`.

Therefore the recorded failure is not a Jev semantic judgment error. Jev was
never called in this arm. The gate ID `missing-supported-memory-judgment` is a
misnomer here: it fires on the absence of any successful Jev memory judgment,
and an absent candidate also produces that absence.

The passed `yocto-queue-off` arm shows the same code path working with real
usage: memory `applied` in 43879 ms with 2 operations and 21300 total tokens,
and harness `applied` in 216454 ms with 1 operation. That arm ran with Jev
disabled, so `jevJudgments` is `[]` there for a different, expected reason.

## Gap found while checking: the receipt carries no stop or fallback reason

The requirement says a receipt must state the direction, the chosen Memory, the
stop or fallback reason, the applied result, the Jev latency, and the actual
version. The failed memory attempt records `outcome: failed` with no reason
field. The only recorded reason, `Connection error.`, lives in the child
session log and never reaches the parent receipt. Treat this as an open
compliance gap for the acceptance-condition trace, not as a Jev defect.

## Cause 2: why the other four arms never started

`tests/docker_experiment.py` `run_project` does this in order:

1. `output.mkdir(parents=True)` creates the host arm directory.
2. `docker run --detach --name cl-project-…` starts the container.
3. `docker exec … --container` runs the in-container verification, with a
   1800 s timeout.
4. It writes `runner-output.txt`.
5. In `finally` it copies the container results, writes `report.json`, and runs
   `docker rm --force`.

Observed state:

- `yocto-queue-on/` on the host exists and is empty. Step 4 and step 5 never
  wrote anything.
- Container `cl-project-yocto-queue-8cf61da7` still exists, started at
  `2026-10-07T03:06:29Z`, and runs only `sleep infinity`. The `docker rm
  --force` of step 5 never ran.
- The batch output root has no `summary.json`, although `main()` writes it
  after all arms finish.

The batch used `--jobs 1`, so the arm order was strictly sequential:
yocto-queue off, yocto-queue on, humanize off, humanize on, referencing off,
referencing on. `main()` catches a per-arm exception in `experiment()` and
records a failed report for that arm, so a failed arm does not stop the batch
by itself. The batch stopped because the host-side process ended during or just
after the on-arm container verification, before export and container cleanup.
The export handle was later unavailable and no host runner process was found.
The four later arms were never dispatched.

## Limitations

- No host-side proxy counter survives for the on arm. `summary.json`, with the
  `InferenceProxy` request and Jev request counts, died with the batch process.
  The Jev attempt count for the on arm therefore comes from the child session
  log and the receipt, not from a proxy count.
- The exact instant of the host process end is not recorded.
- The container-side run record holds no parent-level error reason.

## Consequences for the next steps

1. Do not attribute this failure to Jev semantics. Keep it as a failed
   infrastructure run and preserve it unchanged.
2. Keep the on-arm rerun out of any resumed cohort. A resumed experiment needs
   a new, separately recorded protocol.
3. Trace the receipt reason gap, and the gate-ID conflation, against the current
   source before any quality claim.