# Resumed cohort protocol v2 (2026-10-07): second untuned project

Read @packages/continual-learning/tests/resumed-cohort-protocol-2026-10-07.md for
the purpose, the coverage map, the six measure definitions, and the stopping
rules. This file records only what differs.

## What is different

| Field | v1 | v2 |
| --- | --- | --- |
| Project | itsdangerous | iniconfig |
| Source tree | before the connection-retry fix | after the connection-retry fix |
| Purpose | baseline on an untuned project | exercise the retry fix on an untuned project |

The two projects are **not a controlled pair**: v1 ran without the retry fix, so
a difference between them cannot be attributed to the fix alone. This run is one
more data point, and it is the only place the retry fix meets a real provider.

## Preconditions checked before launch

- `pytest-dev/iniconfig` at `316fbfaf2752d89326e1e75b45cd070f5b5ace9a`.
- Pristine clone: `uv sync --python 3.13 --group dev` exit 0, then
  `uv run --no-sync pytest -q` reported 54 passed.
- Its tests live under `testing/`, not `tests/`.
- Same Jev and main-model pins, credentials, and request budget as v1.

## Cohort addition

| Field | Value |
| --- | --- |
| project | `iniconfig` (`pytest-dev/iniconfig`) |
| commit | `316fbfaf2752d89326e1e75b45cd070f5b5ace9a` |
| install | `uv sync --python 3.13 --group dev` |
| check | `uv run --no-sync pytest -q` |
| task file | `testing/test_iniconfig.py` |
| task behavior | unicode whitespace handling in continuation lines, matching the already covered value, key-name, and section-name stripping, with a distinct case |

## Command

```bash
uv run --no-project --python /opt/homebrew/bin/python3 \
  python packages/continual-learning/tests/live_docker_projects.py \
  --cohort resumed --project iniconfig --jev paired --memory-policy composed \
  --jobs 1 --output <new dir>
```

`--project iniconfig` limits the batch to two arms. The finished itsdangerous
arms are not rerun.

## Extra measurements for this run

1. Does any judgment telemetry record `failureKind: "connection"`?
2. Does any judgment record `retriedRequests`, and did the review still reach a
   decision (a recovered review) or stay a proposal?
3. Does the receipt keep the reason for any incomplete review?

## Stopping rules

Same as v1, plus: a recovered review is recorded as an availability observation,
not as evidence that Jev improves learning. Net benefit still needs all six
measures and cannot rest on one project.

## Launch record

| Field | Value |
| --- | --- |
| launched | 2026-10-07T04:29:33Z |
| PID | 7308, started in its own session by `start_new_session=True` |
| output root | `~/.cache/pi-continual-learning/docker/20261007T042933Z` |
| log | `~/.cache/pi-continual-learning/resumed-batch-20261007T042933Z.log` |
| pid file | `~/.cache/pi-continual-learning/resumed-batch-20261007T042933Z.pid` |
| launcher | `~/.cache/pi-continual-learning/launch-resumed-batch-v2.sh` |
| first log line | `{"stage": "building", "output": ".../20261007T042933Z"}` |