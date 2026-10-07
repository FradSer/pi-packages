# Resumed cohort protocol v3 (2026-10-07): third untuned project on the fixed code

Read @packages/continual-learning/tests/resumed-cohort-protocol-2026-10-07.md for
the purpose, coverage map, six measure definitions, and stopping rules. Only the
differences are recorded here.

## What is different from v2

| Field | v2 | v3 |
| --- | --- | --- |
| Project | iniconfig | pluggy |
| Code under test | connection-retry fix only | connection-retry fix **plus** the support instruction and the placeholder-aware guard |
| Purpose | second untuned data point | first real-run test of the two newest fixes |

The projects are **not a controlled pair** with the earlier runs: v1 ran before
the retry fix, v2 before the support instruction and guard fixes.

## Preconditions checked before launch

- `pytest-dev/pluggy` at `60b15251ee18560f781c557b6b9ef3de4d786bee`.
- Pristine clone: `uv sync --python 3.13 --group dev` exit 0, then
  `uv run --no-sync pytest -q` reported **202 passed**.
- Its tests live under `testing/`.
- Same Jev and main-model pins, credentials, and request budget as the earlier runs.

## Cohort addition

| Field | Value |
| --- | --- |
| project | `pluggy` (`pytest-dev/pluggy`) |
| commit | `60b15251ee18560f781c557b6b9ef3de4d786bee` |
| install | `uv sync --python 3.13 --group dev` |
| check | `uv run --no-sync pytest -q` |
| task file | `testing/test_pluginmanager.py` |
| task behavior | unregistering a plugin removes its implementations for later hook calls while a call already in progress keeps the implementations it started with |

## Command

```bash
uv run --no-project --python /opt/homebrew/bin/python3 \
  python packages/continual-learning/tests/live_docker_projects.py \
  --cohort resumed --project pluggy --jev paired --memory-policy composed \
  --jobs 1 --output <new dir>
```

## What this run can and cannot show

Can: whether the fixed Memory path now persists the private preference and the
verified command fact on a third untuned project, and whether the guard no longer
refuses a review on a project whose own sources contain placeholder credentials.

Cannot: net benefit on its own. One project and one pair cannot carry that, and
the recorded negative results still stand.

## Stopping rules

Same as v1, plus: do not rerun any finished arm, and record a stopped or refused
review with its distinct gate label rather than as a semantic judgment.

## Launch record

| Field | Value |
| --- | --- |
| launched | see the log and pid file below |
| output root | `~/.cache/pi-continual-learning/docker/20261007T0436Z-will-be-recorded` |
| launcher | `~/.cache/pi-continual-learning/launch-resumed-batch-v3.sh` |
