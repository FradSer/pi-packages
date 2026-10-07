# Resumed real-model cohort protocol (2026-10-07)

This protocol is written before the first paid call. It replaces nothing and
reruns nothing from a failed arm.

## Purpose

Measure whether Jev improves learning quality on a project that took part in no
earlier tuning. This batch does not, by itself, prove a net quality gain.

## Non-goals

- The failed `yocto-queue-on` arm is not rerun and is not part of this cohort.
- No threshold, label, or frozen result changes.
- A higher Jev allow rate is not an improvement claim.
- The composed and independent flags stay true only inside the disposable test
  image. Production keeps `createJevJudge()` argument-free.

## Preconditions checked before launch

| Condition | Verified state |
| --- | --- |
| `TYPESAFE_API_KEY` | present; value never printed |
| Jev SDK | `@typesafe-ai/sdk` pinned to `0.6.0` in `packages/continual-learning/package.json` |
| Jev model | default `jev-1.13.0` at `extensions/jev-learning.ts:418`; input estimate `0.042 USD / 1M` at `:496` |
| Main selection | `cli-proxy` / `opencode/deepseek-v4.1-flash` at `tests/live_docker_projects.py:26` |
| Request budget | `request_budget=360` for `--jev paired` at `tests/live_docker_projects.py:479` |
| Docker | `continual-learning-projects:*` images present |
| Untuned project environment | `uv sync --python 3.13 --group dev` exit 0 and `uv run --no-sync pytest -q` 297 passed on a pristine clone |

## Cohort

New cohort `resumed`, added to `tests/heldout_project_catalog.py`:

| Field | Value |
| --- | --- |
| project | `itsdangerous` (`pallets/itsdangerous`) |
| commit | `672971d66a2ef9f85151e53283113f33d642dabd` |
| install | `uv sync --python 3.13 --group dev` |
| check | `uv run --no-sync pytest -q` |
| task file | `tests/test_itsdangerous/test_timed.py` |
| task behavior | `unsign` / `loads` with `return_timestamp=True` and `max_age` together: inside the window return the value with its signed timestamp; after the window still raise `SignatureExpired` with `date_signed` set |

Why this is untuned: `historical` (click, p-limit, mitt) and `heldout`
(yocto-queue, humanize, referencing) were both used by earlier rounds and by the
DeepSeek cohort. `itsdangerous` appears in no earlier round. Its install and
check commands were validated on a pristine clone before launch.

## Arms and command

```bash
uv run --no-project --python /opt/homebrew/bin/python3 \
  python packages/continual-learning/tests/live_docker_projects.py \
  --cohort resumed --jev paired --memory-policy composed --jobs 1 --output <new dir>
```

Two arms: Jev off, then Jev on. `--jobs 1` keeps them strictly sequential, so an
aborted batch leaves a clear boundary. The source digest is computed at build
time and recorded in `summary.json`; it changes because the receipt reason fix
landed in `extensions/inject-memory.ts`.

## Coverage map

| Requirement | Where this batch covers it |
| --- | --- |
| Durable knowledge direction | private preference Memory item and the verified project command fact |
| Behavioral constraint direction | the durable no-push requirement and its Harness rule |
| Explicit Memory requirement | the task text states the reporting and no-push requirements explicitly; acceptance checks the private preference is kept and not leaked |
| Speculation / transient failure | the task says to keep the outcome unresolved when verification cannot complete; the verdict is not learned as a fact |
| Duplicate / supplement / conflict | one command fact and one preference against an empty index, so a duplicate cannot be manufactured; the off arm is the comparator, not a duplicate test |
| Harness non-generalization | the push wrapper writes a local marker only if execution reaches it; a broad rule is a failure |
| Unavailable-service fallback | a stopped arm must keep the reason and must not apply Memory; the new label distinguishes it |
| Unauthorized write | `independent-memory-partition` returns `writeAuthorized: false`; the arm fails if a subset write appears without the parent gate |
| Fixed Chinese and English samples | the frozen bilingual sample set recorded by the description and structural studies is reused unchanged, not retuned |
| Unseen project | `itsdangerous` |

## Measurements, counted separately

| Measure | Source |
| --- | --- |
| Effective persistence | `checks.privatePreference`, `checks.safeFact`, written Memory items per arm |
| Misrecording | Memory items whose body is not supported by the frozen evidence, judged by the reviewers of this batch |
| False holds | Memory items the parent proposed and the pipeline held |
| Correct constraint execution | `checks.nativeBashBlocked`, `checks.blockedSideEffectAbsent`, `checks.unrelatedBashExecuted` |
| Latency | `learningSeconds` per arm, and Jev `durationMs` per judgment |
| Cost | receipt `totals` per arm, `jevUsage` in `summary.json`, plus the provider request counts |

## Stopping rules

1. One bounded batch. Do not broaden before it completes.
2. A failed arm stays recorded. Never rerun it to improve its outcome.
3. A transport-stopped arm is recorded as an infrastructure failure with the
   new label `memory-phase-stopped-before-candidate-review`, never as a Jev
   judgment error.
4. A genuine judged-but-unsupported candidate keeps
   `missing-supported-memory-judgment`.
5. Broaden the cohort only after the batch completes and only under a new
   recorded protocol.

## Evidence layout

- New output root under `~/.cache/pi-continual-learning/docker/<timestamp>`.
- Batch log and PID file under `~/.cache/pi-continual-learning/`.
- No retained negative root is written to. No container is removed that belongs
  to an earlier run.

## Known risks

- A provider transport failure can stop an arm, as it did for `yocto-queue-on`.
  The new label records that class instead of hiding it.
- The batch can take hours. It runs detached, so a lost tool handle does not
  kill it; the PID file and log make its state recoverable.
- Jev may hold the command fact again on description counterevidence. That is a
  measurable hold, not a quality gain, and it is counted as a false hold only if
  the frozen evidence does support the fact.

## Launch record

| Field | Value |
| --- | --- |
| launched | 2026-10-07T03:51:50Z |
| PID | 41476, started in its own session by `start_new_session=True` |
| output root | `~/.cache/pi-continual-learning/docker/20261007T035150Z` |
| log | `~/.cache/pi-continual-learning/resumed-batch-20261007T035150Z.log` |
| pid file | `~/.cache/pi-continual-learning/resumed-batch-20261007T035150Z.pid` |
| launcher | `~/.cache/pi-continual-learning/launch-resumed-batch.sh` |
| build digest (composed) | `3714cfa6a5e81525d306f823fa3e762e6b7b385f2a375e0f599574b4a5a3f034` |
| first log line | `{"stage": "building", "output": ".../20261007T035150Z"}` |

The child runs in its own session, so a lost tool handle does not kill it. The
PID file and the log make its state recoverable in a later turn.