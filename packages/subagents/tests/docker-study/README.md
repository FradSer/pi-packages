# Docker/native model studies

Run these only when real-model execution is explicitly requested.

## Compact hy4-dev smoke (lowest injected tokens)

This is the default entry for a quick real-model check of the current sources.
It uses Docker, Pi **1.5.0** and Magpie `hunyuan-eval/hy4-dev` with
`reasoning_effort: none` on every request. The host-only transparent proxy keeps
the upstream key outside the image: the container receives only a one-run token
through `STUDY_PROXY_TOKEN`, which the child also receives via the exact
`PI_TEAMMATE_ENV_ALLOW` opt-in. The real key and the user's `~/.pi/agent` are
never copied into the image or evidence.

```sh
uv run --python 3.13 packages/subagents/tests/docker-study/minimal.py --output /tmp/subagents-minimal
```

Read `../../features/docker-minimal-token.feature` for the scenario.
`minimal.ts` invokes the public intent executor with real native RPC children;
it does not stub provider replies. Each functional path runs once: four intent
tools, temporary/saved identities, next/steer, stop/restart, stale handles,
invalid identity combinations, read-only Memory refusal plus proposal,
write-granted Memory append plus index injection, and parent-model tool
selection with native TUI expansion/resize. The historical study's repeated
rounds and paired heldout quality arms are deliberately not run here.
Inspect `summary.json`, `metadata.json`, `study.json`, `notices.jsonl`,
`receipts.json`, native `child-*.jsonl` tool logs and `parent-tui.json`.
`summary.json` reports measured tokens, request count, wire reasoning state and
each functional check. A green result proves compact execution coverage, not
review quality, statistical benefit or general capability.

## Historical controlled Memory study

This is the explicit quality/learning study. It uses Docker, Pi **1.0.4** and
the user's configured `cli-proxy/opencode/deepseek-v4.1-flash`. The transparent
inference proxy retains upstream credentials outside the image/container. Its
expiring study token is never copied into evidence.

```sh
uv run --python 3.13 packages/subagents/tests/docker-study/run.py --output /tmp/subagents-study-104
uv run packages/subagents/tests/docker-study/score.py /tmp/subagents-study-104
```

Read `../../features/docker-memory-study.feature` for the scenarios. `study.ts` invokes the public intent
executor with real native RPC children; it does not stub provider replies.
`audit.ts` observes native tool calls/results and injected Memory indexes.
`parent-probe.py` separately lets the actual parent model select tools in a native
PTY and exercises expansion and narrow-width repaint. Parent tool selection is
not inferred from the direct-executor scenarios.

All authored identities, source fixtures, Memory and history belong to the
isolated study container. The script deletes only its own container and retains
its image and sanitized evidence. It does not edit real identities or histories.

The four paired heldout reviews are synthetic package-contract fixtures, not a
repository audit. Training requests a model-authored accepted capability with a
write grant; ordinary read-only reviewers can only propose candidates. Both
heldout arms use the same saved identity, standing instructions, source, contract,
prompt and effective tool grant. The control temporarily hides accepted Memory
while its child runs; the original is restored after confirmed closure. Each arm
uses a new parent history partition. Finding scores measure retention-assisted review,
not a general model-quality advantage. One run cannot establish statistical
benefit, especially when the control already finds every bug.

Inspect `metadata.json`, `study.json`, `receipts.json`, `spawns.json`, native
`child-*.jsonl` tool logs, `agents/` and `summary.json`. Report unanswered/failed
arms as missing coverage. Confirm full capability-body read results, rather than
counting index injection as retrieval. A proposal is never an accepted entry.
